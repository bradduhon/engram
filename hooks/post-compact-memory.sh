#!/bin/bash
# Copyright (c) 2026 Brad Duhon. All Rights Reserved.
# Confidential and Proprietary.
# Unauthorized copying of this file is strictly prohibited.
#
# Claude Code PostCompact hook. Reads the compaction JSON from stdin and
# pushes the summary to the engram memory service via mTLS. The private
# key is decrypted inline via process substitution -- plaintext exists
# only in a kernel pipe buffer (fd), never as a named file on disk.
#
# Always exits 0 -- never blocks compaction on a memory write failure.
set -euo pipefail

CERT_DIR="$HOME/.claude/certs"

# Read PostCompact JSON from stdin
INPUT=$(cat)

# Extract fields
SUMMARY=$(echo "$INPUT"    | jq -r '.summary // empty')
SESSION_ID=$(echo "$INPUT" | jq -r '.session_id // "unknown"')
PROJECT_ID=$(echo "$INPUT" | jq -r '.project_id // empty')
TRIGGER=$(echo "$INPUT"    | jq -r '.trigger // "auto"')

# Nothing to store if summary is empty
if [ -z "$SUMMARY" ]; then
  exit 0
fi

# Determine scope
if [ -n "$PROJECT_ID" ] && [ "$PROJECT_ID" != "null" ]; then
  SCOPE="project"
else
  SCOPE="global"
  PROJECT_ID="null"
fi

# Build the store_memory payload
PAYLOAD=$(jq -n \
  --arg text            "$SUMMARY" \
  --arg scope           "$SCOPE" \
  --arg project_id      "$PROJECT_ID" \
  --arg conversation_id "$SESSION_ID" \
  --arg trigger         "compact_${TRIGGER}" \
  '{
    text:            $text,
    scope:           $scope,
    project_id:      (if $project_id == "null" then null else $project_id end),
    conversation_id: $conversation_id,
    trigger:         $trigger
  }')

# POST to memory service via mTLS.
# Process substitution <(...) creates an anonymous fd that curl reads as
# the key file. Plaintext exists only in the pipe buffer; closed when curl exits.
RESPONSE=$(curl --silent --show-error \
  --cert    "$CERT_DIR/client.crt" \
  --key     <(age -d -i "$CERT_DIR/age-identity.txt" "$CERT_DIR/client.key.age") \
  --cacert  "$CERT_DIR/amazon-trust-services-ca.pem" \
  --max-time 10 \
  -H "Content-Type: application/json" \
  -d "$PAYLOAD" \
  "https://memory.brad-duhon.com/store" 2>&1) || true

# Log result to stderr (Claude Code verbose log only -- not in Claude's context)
STATUS=$(echo "$RESPONSE" | jq -r '.stored // false' 2>/dev/null || echo "false")
if [ "$STATUS" = "true" ]; then
  echo "PostCompact memory stored (trigger: compact_${TRIGGER}, scope: ${SCOPE})" >&2
else
  echo "Warning: PostCompact memory store failed or returned unexpected response: $RESPONSE" >&2
fi

# Always exit 0 -- memory write failures must not block compaction
exit 0
