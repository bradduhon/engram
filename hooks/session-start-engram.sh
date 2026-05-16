#!/usr/bin/env bash
# Copyright (c) 2026 Brad Duhon. All Rights Reserved.
# Confidential and Proprietary.
# Unauthorized copying of this file is strictly prohibited.
#
# SessionStart hook — injects a mandatory Engram recall directive.
# Claude MUST execute these MCP calls before responding to the user.

set -euo pipefail

# Derive project_id from git root directory name
PROJECT_ID=""
if git_root=$(git rev-parse --show-toplevel 2>/dev/null); then
  PROJECT_ID=$(basename "$git_root")
fi

cat <<DIRECTIVE
[MANDATORY — ENGRAM SESSION INITIALIZATION]

You MUST execute the following Engram MCP recall calls BEFORE responding to the user's first message. This is not optional. Do not skip, defer, or summarize without calling.

Step 1 — Project recall (run first if project is detected):
DIRECTIVE

if [[ -n "$PROJECT_ID" ]]; then
cat <<DIRECTIVE
  Call: mcp__engram-memory__recall_memory
    query: "project state decisions status architecture ${PROJECT_ID}"
    top_k: 8
    project_id: "${PROJECT_ID}"

Step 2 — Global recall:
  Call: mcp__engram-memory__recall_memory
    query: "active projects priorities conventions decisions"
    top_k: 3
    scope_filter: "global"
DIRECTIVE
else
cat <<DIRECTIVE
  No git project detected. Run global recall only:
  Call: mcp__engram-memory__recall_memory
    query: "active projects priorities conventions decisions"
    top_k: 5
    scope_filter: "global"
DIRECTIVE
fi

cat <<DIRECTIVE

Step 3 — Report context status:
  After recall completes, output a one-line Context Status before proceeding:
  [Context: Engram loaded — N project memories, M global memories]
  OR if recall returned nothing:
  [Context: Zero-Knowledge — no Engram results for ${PROJECT_ID:-this session}]

FAILURE TO EXECUTE THESE CALLS IS A VIOLATION OF SESSION PROTOCOL.
[END MANDATORY DIRECTIVE]
DIRECTIVE
