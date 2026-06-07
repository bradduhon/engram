#!/usr/bin/env bash
# Copyright (c) 2026 Brad Duhon. All Rights Reserved.
# Confidential and Proprietary.
# Unauthorized copying of this file is strictly prohibited.
#
# PreToolUse hook — fires before every mcp__engram-memory__store_memory call.
# Blocks obvious anti-patterns. Exits non-zero to cancel the tool call.
#
# Claude Code passes the tool input as JSON on stdin:
#   { "tool_name": "mcp__engram-memory__store_memory", "tool_input": { "text": "...", ... } }

set -euo pipefail

INPUT=$(cat)
TEXT=$(echo "$INPUT" | jq -r '.tool_input.text // ""' 2>/dev/null || true)

if [[ -z "$TEXT" ]]; then
  exit 0
fi

# ── Anti-pattern filter ───────────────────────────────────────────────────────
# Block session completions, group markers, backlog snapshots, and PR noise.

ANTI_PATTERN_RE='(session (complete|end|summary|wrap)|group [a-z] complete|next session[: ]|\[backlog\]|pr merged|pushed to (main|master)|task complete|wrapped up today|completed (today|this session)|all (tasks|steps) (done|complete))'

if echo "$TEXT" | grep -qiE "$ANTI_PATTERN_RE"; then
  cat <<'EOF'

╔══════════════════════════════════════════════════════════════╗
║           ENGRAM HYGIENE GATE — store_memory BLOCKED         ║
╚══════════════════════════════════════════════════════════════╝

Text matches a session-completion or task-noise anti-pattern.
These are not stored — they are low-signal and stale within the session.

If this memory is genuinely high-signal, run /hygiene first.
/hygiene will classify it, apply the generalizability test, and
produce a revised store_memory call for your confirmation.

EOF
  exit 2
fi

# ── Token floor ───────────────────────────────────────────────────────────────
# Memories under 8 words are almost always insufficient context.

WORD_COUNT=$(echo "$TEXT" | wc -w | tr -d ' ')
if [[ "$WORD_COUNT" -lt 8 ]]; then
  cat <<EOF

╔══════════════════════════════════════════════════════════════╗
║           ENGRAM HYGIENE GATE — store_memory BLOCKED         ║
╚══════════════════════════════════════════════════════════════╝

Text is too short ($WORD_COUNT words) to be a self-contained memory.
A memory must be interpretable without the current conversation context.

Run /hygiene to expand and classify before storing.

EOF
  exit 2
fi

# ── Hygiene reminder (non-blocking) ──────────────────────────────────────────
# For everything that passes the filter, inject a lightweight reminder
# so Claude confirms the hygiene gate was intentionally cleared.

cat <<'EOF'

[ENGRAM] store_memory pre-check: confirm /hygiene was run for this entry.
If not, cancel this call and run /hygiene first.

EOF

exit 0
