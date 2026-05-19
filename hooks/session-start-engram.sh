#!/usr/bin/env bash
# Copyright (c) 2026 Brad Duhon. All Rights Reserved.
# Confidential and Proprietary.
# Unauthorized copying of this file is strictly prohibited.
#
# UserPromptSubmit hook — fires on the first user message of a session.
# Calls the Engram recall API directly via mTLS and injects memory content
# into the system-reminder. Claude receives loaded context without needing
# to call any MCP tools.
#
# Required environment variable:
#   MEMORY_API_URL  -- base URL of the engram API (e.g. https://engram.brad-duhon.com)
#                      Set in ~/.claude/settings.json under the hook's env block.

set -euo pipefail

CERT_DIR="$HOME/.claude/certs"

# ── Helpers ──────────────────────────────────────────────────────────────────

recall() {
  local payload="$1"
  curl --silent --show-error \
    --cert    "$CERT_DIR/client.crt" \
    --key     <(age -d -i "$CERT_DIR/age-identity.txt" "$CERT_DIR/client.key.age") \
    --cacert  "$CERT_DIR/amazon-trust-services-ca.pem" \
    --max-time 10 \
    -H "Content-Type: application/json" \
    -d "$payload" \
    "${MEMORY_API_URL}/recall" 2>/dev/null || echo '{"memories":[]}'
}

format_memories() {
  local json="$1"
  echo "$json" | jq -r '
    .memories[]
    | "[\(.scope | ascii_upcase)] \(.text | gsub("\n"; " "))"
  ' 2>/dev/null || true
}

# ── Project ID ────────────────────────────────────────────────────────────────

PROJECT_ID=""
if git_root=$(git rev-parse --show-toplevel 2>/dev/null); then
  PROJECT_ID=$(basename "$git_root")
fi

# ── Recall ────────────────────────────────────────────────────────────────────

PROJECT_JSON='{"memories":[]}'
GLOBAL_JSON='{"memories":[]}'

if [[ -n "$PROJECT_ID" ]]; then
  PROJECT_PAYLOAD=$(jq -n \
    --arg q  "project state decisions status architecture ${PROJECT_ID}" \
    --arg pid "$PROJECT_ID" \
    '{"query": $q, "top_k": 8, "project_id": $pid}')
  PROJECT_JSON=$(recall "$PROJECT_PAYLOAD")
fi

GLOBAL_PAYLOAD=$(jq -n \
  --arg q "active projects priorities conventions decisions" \
  '{"query": $q, "top_k": 3, "scope_filter": "global"}')
GLOBAL_JSON=$(recall "$GLOBAL_PAYLOAD")

PROJECT_COUNT=$(echo "$PROJECT_JSON" | jq '.memories | length' 2>/dev/null || echo 0)
GLOBAL_COUNT=$(echo "$GLOBAL_JSON"  | jq '.memories | length' 2>/dev/null || echo 0)

# ── Output ────────────────────────────────────────────────────────────────────

echo "[ENGRAM CONTEXT — ${PROJECT_COUNT} project memories, ${GLOBAL_COUNT} global memories]"

if [[ "$PROJECT_COUNT" -gt 0 ]]; then
  echo ""
  echo "Project memories (${PROJECT_ID}):"
  format_memories "$PROJECT_JSON" | nl -ba -w2 -s". "
fi

if [[ "$GLOBAL_COUNT" -gt 0 ]]; then
  echo ""
  echo "Global memories:"
  format_memories "$GLOBAL_JSON" | nl -ba -w2 -s". "
fi

echo ""
echo "[END ENGRAM CONTEXT — recall complete, no tool calls required]"
