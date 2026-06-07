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
#   MEMORY_API_URL  -- base URL of the engram API (e.g. https://engram.your-domain.com)
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
    | (if (.tags | map(select(startswith("project:"))) | length) > 0
       then "PROJECT"
       else "GLOBAL"
       end) as $label
    | "[\($label)] \(.text | gsub("\n"; " "))"
  ' 2>/dev/null || true
}

# ── Project ID ────────────────────────────────────────────────────────────────

PROJECT_ID=""
if git_root=$(git rev-parse --show-toplevel 2>/dev/null); then
  PROJECT_ID=$(basename "$git_root")
fi

# ── Build weights: boost current project memories to surface first ─────────────

if [[ -n "$PROJECT_ID" ]]; then
  WEIGHTS=$(jq -n \
    --arg pid "$PROJECT_ID" \
    '{("project:" + $pid): 1.5, "scope:project": 1.2}')
else
  WEIGHTS='{}'
fi

# ── Recall — single call with weight boosting ─────────────────────────────────

PAYLOAD=$(jq -n \
  --arg q       "project state decisions status architecture priorities conventions" \
  --argjson w   "$WEIGHTS" \
  '{"query": $q, "top_k": 10, "weights": $w}')

RESPONSE=$(recall "$PAYLOAD")
MEMORY_COUNT=$(echo "$RESPONSE" | jq '.memories | length' 2>/dev/null || echo 0)

# ── Output ────────────────────────────────────────────────────────────────────

echo "[ENGRAM CONTEXT — ${MEMORY_COUNT} memories]"

if [[ "$MEMORY_COUNT" -gt 0 ]]; then
  echo ""
  format_memories "$RESPONSE" | nl -ba -w2 -s". "
fi

echo ""
echo "[END ENGRAM CONTEXT — recall complete, no tool calls required]"
