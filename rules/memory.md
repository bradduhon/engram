# Engram Memory Protocol

## Storing — MANDATORY pre-condition

**Never call `store_memory` directly.** Always run `/hygiene` first.

`/hygiene` classifies the content (STATE / DECISION / RULE / DISCOVERY / QUIRK),
applies the generalizability test, checks for an existing state entry to update,
and blocks anti-patterns before producing the final `store_memory` call.

The only exception is an explicit user instruction to store a specific value verbatim.

A `PreToolUse` hook (`store-hygiene-gate.sh`) enforces this at the call layer:
- Anti-pattern matches (session completions, task noise, PR announcements) are **blocked** (exit 2).
- All other calls emit a confirmation reminder. If you have not run `/hygiene`, cancel the call and run it now.

## Recalling — depth requirement

You must not accept shallow results. When searching for context:

1. **Initial Search**: Call `recall_memory(query, top_k=5)`.
2. **Confidence Check**: Do these results contain the RATIONALE or the DECISION for this specific technical path?
3. **Recursive Expansion**: If ambiguous or insufficient:
    - Generate 3 semantic variants (e.g. if 'PKI' failed, try 'FIPS-compliant key rotation' or 'ServerlessHSM secret management').
    - Re-run with higher `top_k` or call `search_related_findings` on the best result.
4. **Failure State**: After 3 iterations with no context: "NO HISTORICAL CONTEXT FOUND. Proceeding with Zero-Knowledge Implementation based on CIS Benchmarks."
