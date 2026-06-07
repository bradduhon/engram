#!/usr/bin/env bash
# Copyright (c) 2026 Brad Duhon. All Rights Reserved.
# Confidential and Proprietary.
# Unauthorized copying of this file is strictly prohibited.
#
# UserPromptSubmit hook -- fires on every user message after the first.
# Classifies the prompt; skips affirmations and short continuations.
# For substantive requests and assertions, extracts a keyword query,
# calls Engram recall, and injects relevant memories as context.
#
# Required environment variable:
#   MEMORY_API_URL  -- base URL of the engram API (e.g. https://engram.example.com)
#                      Set in ~/.claude/settings.json under the hook's env block.

set -euo pipefail

CERT_DIR="$HOME/.claude/certs"

# ── Read prompt from stdin ────────────────────────────────────────────────────

INPUT=$(cat)
PROMPT=$(echo "$INPUT" | jq -r '.prompt // ""')

if [[ -z "$PROMPT" ]]; then
  exit 0
fi

# ── Affirmation / continuation detection -- skip Engram ──────────────────────

WORD_COUNT=$(echo "$PROMPT" | wc -w | tr -d ' ')

if [[ "$WORD_COUNT" -le 8 ]]; then
  AFFIRMATION_PATTERN="^[[:space:]]*(yes|no|ok|okay|sure|yep|nope|yup|go ahead|do it|proceed|continue|done|got it|looks good|perfect|correct|exactly|sounds good|agreed|makes sense|that works|keep going|carry on|good|great|nice|alright|right|true|false|thanks|thank you|go|stop|wait|hold on|never mind|skip it)[[:space:]\.!]*$"
  if echo "$PROMPT" | grep -iqE "$AFFIRMATION_PATTERN"; then
    exit 0
  fi
  if ! echo "$PROMPT" | grep -qiE "(fix|add|change|update|implement|write|show|explain|why|how|what|where|when|help|debug|review|check|find|create|remove|delete|deploy|run|build|test|refactor|investigate|analyze|describe|list|compare|difference|problem|issue|error|fail|broken|doesn't|won't|can't|isn't|aren't)"; then
    exit 0
  fi
fi

# ── Extract keyword query ─────────────────────────────────────────────────────

QUERY=$(echo "$PROMPT" | python3 - <<'PYEOF'
import sys, re

STOP = {
    'the','a','an','is','are','was','were','be','been','being',
    'i','my','we','our','you','your','it','its','they','their','them',
    'to','of','in','on','for','with','and','or','but','not','that','this',
    'can','do','does','did','how','what','why','where','when','which',
    'would','could','should','have','has','had','will','just','so','if',
    'at','by','from','as','up','about','into','than','then','he','she',
    'his','her','let','get','got','go','now','here','there','also','too',
    'very','some','any','all','more','only','other','same','such',
    'want','need','make','take','use','used','using','re','ve','ll','d',
}

text = sys.stdin.read().lower()
words = re.findall(r"[a-zA-Z][a-zA-Z0-9_\-\.]{1,}", text)
filtered = [w for w in words if w not in STOP]
seen = set()
unique = []
for w in filtered:
    if w not in seen:
        seen.add(w)
        unique.append(w)
print(' '.join(unique[:10]))
PYEOF
)

if [[ -z "$QUERY" ]]; then
  exit 0
fi

# ── Project ID + weights ──────────────────────────────────────────────────────

PROJECT_ID=""
if git_root=$(git rev-parse --show-toplevel 2>/dev/null); then
  PROJECT_ID=$(basename "$git_root")
fi

if [[ -n "$PROJECT_ID" ]]; then
  WEIGHTS=$(jq -n --arg pid "$PROJECT_ID" '{("project:" + $pid): 1.5}')
else
  WEIGHTS='{}'
fi

# ── Recall ────────────────────────────────────────────────────────────────────

PAYLOAD=$(jq -n \
  --arg q       "$QUERY" \
  --argjson w   "$WEIGHTS" \
  '{"query": $q, "top_k": 3, "weights": $w}')

RESPONSE=$(curl --silent --show-error \
  --cert    "$CERT_DIR/client.crt" \
  --key     <(age -d -i "$CERT_DIR/age-identity.txt" "$CERT_DIR/client.key.age") \
  --cacert  "$CERT_DIR/amazon-trust-services-ca.pem" \
  --max-time 8 \
  -H "Content-Type: application/json" \
  -d "$PAYLOAD" \
  "${MEMORY_API_URL}/recall" 2>/dev/null || echo '{"memories":[]}')

MEMORY_COUNT=$(echo "$RESPONSE" | jq '.memories | length' 2>/dev/null || echo 0)

if [[ "$MEMORY_COUNT" -eq 0 ]]; then
  exit 0
fi

# ── Output ────────────────────────────────────────────────────────────────────

echo "[ENGRAM PROMPT CONTEXT — query: \"$QUERY\", ${MEMORY_COUNT} memories]"
echo ""
echo "$RESPONSE" | jq -r '
  .memories[]
  | (if (.tags | map(select(startswith("project:"))) | length) > 0
     then "PROJECT"
     else "GLOBAL"
     end) as $label
  | "[\($label)] \(.text | gsub("\n"; " "))"
' 2>/dev/null | nl -ba -w2 -s". "
echo ""
echo "[END ENGRAM PROMPT CONTEXT]"
