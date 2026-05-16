#!/usr/bin/env bash
# Copyright (c) 2026 Brad Duhon. All Rights Reserved.
# Confidential and Proprietary.
# Unauthorized copying of this file is strictly prohibited.
#
# PostToolUse hook: inspect recall_memory results.
# Warns Claude when results are empty or best relevance_score < 0.6,
# prompting query expansion before proceeding.
#
# Receives Claude Code hook JSON on stdin:
#   { "tool_name": "...", "tool_input": {...}, "tool_response": { "content": [...] } }
# Writes warning text to stdout; Claude sees this as a system nudge.

set -euo pipefail

input=$(cat)

# Extract text content from the MCP tool response
response_text=$(printf '%s' "$input" | jq -r '.tool_response.content[0].text // ""' 2>/dev/null || true)

if [ -z "$response_text" ]; then
  exit 0
fi

total=$(printf '%s' "$response_text" | jq -r '.total // 0' 2>/dev/null || echo "0")

if [ "$total" = "0" ]; then
  printf 'ENGRAM NUDGE: recall_memory returned 0 results. Query was likely too narrow.\nExpand using: alternate terminology, resource ARNs, security standard names (FIPS/CIS/NIST), or the project directory name.\nDo NOT declare Zero-Knowledge without at least one expansion attempt.\n'
  exit 0
fi

# Check best relevance_score (highest = best match). Threshold: 0.6
best_score=$(printf '%s' "$response_text" | jq '[.memories[].relevance_score] | max // 0' 2>/dev/null || echo "0")
threshold="0.6"

if awk "BEGIN {exit !($best_score < $threshold)}"; then
  printf 'ENGRAM NUDGE: recall_memory best relevance_score=%.4f (< %.1f threshold). Results may be off-topic.\nConsider query expansion or a second recall with a higher top_k before proceeding.\n' "$best_score" "$threshold"
fi
