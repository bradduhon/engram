# Engram Memory

You have persistent memory via five MCP tools: `store_memory`, `recall_memory`, `search_related_findings`, `summarize_memories`, `delete_memory`.

---

## Field Reference

| Field | Tool | Notes |
|---|---|---|
| `text` | store | Required. Concise, self-contained statement |
| `scope` | store, summarize | `"project"` if in a Claude Code Project, else `"global"` |
| `project_id` | store, recall, summarize | Required when scope is `"project"`. Use the git repo name or root directory name |
| `conversation_id` | store | Required. Use `<project_id>-<YYYYMMDD>` or `global-<YYYYMMDD>` |
| `top_k` | recall | Number of results to return |
| `trigger` | store | `"explicit"` for manual stores, omit otherwise |

---

## Relevance Score Semantics

Each `recall_memory` result includes two score fields:

| Field | Meaning | Range | Better |
|---|---|---|---|
| `score` | Cosine distance from S3 Vectors | 0–2 | Lower |
| `relevance_score` | Normalized similarity: `1 - (score / 2)` | 0–1 | Higher |

**Confidence thresholds:**
- `relevance_score ≥ 0.8` — Strong match. Use the result directly.
- `0.6 ≤ relevance_score < 0.8` — Soft match. Cross-reference with a second query or call `search_related_findings` on the best result to retrieve temporal context.
- `relevance_score < 0.6` — Weak match. Expand query before proceeding.

A PostToolUse hook automatically outputs a nudge when results are empty or best score < 0.6.

---

## During Conversation

### Recall

Call `recall_memory` (top_k: 3) before proposing an architecture, design, or tooling choice, and whenever the topic shifts domain or a new technology is introduced. Query the new context, not the session opener. Incorporate silently.

### Search Related Findings

Call `search_related_findings` when a recall result scores 0.6–0.8 and you need surrounding context from the same session. Pass the `id` from the best `MemoryResult` plus its `scope` and `project_id`.

### Store

Before calling `store_memory`, run `/hygiene`. The hygiene skill classifies the content (STATE / DECISION / RULE / DISCOVERY / QUIRK), applies the generalizability test, checks for an existing state entry to update rather than create, and blocks anti-patterns. It outputs a proposed `store_memory` call for confirmation before executing.

Direct `store_memory` calls are acceptable only when the user explicitly requests it and the content is clearly high-signal.

**Rationale Capture**: For architectural shifts, store the "Why" — trade-offs considered, alternatives rejected, and the driver (Security/Cost/Performance). This supports future "Lab" article generation.

---

## Session End

Do **not** auto-store a session summary. Compaction summaries and end-of-session wrap-ups are compression artifacts — low signal and stale within the same session.

Instead, run `/hygiene` for any decision, rule, or discovery that emerged during the session that would be useful in a future conversation. If nothing clears the hygiene filter, store nothing.

---

## Summarize

Call `summarize_memories` when:

- The user asks to compress or summarize memories
- You notice recall results are redundant or fragmented across many entries

Pass `delete_originals: true` only when the user explicitly asks to prune.

---

## Do NOT Store

- Session completions, "GROUP COMPLETE," "NEXT SESSION: …," or end-of-session wrap-ups
- Backlog snapshots: bullet lists of upcoming tasks with no architectural content
- PR/commit announcements without architectural rationale
- Command outputs (raw CLI output without interpreted significance)
- Restatements of documentation already in README, Engram.md, or CLAUDE.md
- Routine messages or pleasantries
- Entire file contents
- Anything that would be stale or irrelevant within 2 weeks without a project refresh

When uncertain, run `/hygiene` — it applies the full classification and generalizability gate before deciding whether to call `store_memory`.
