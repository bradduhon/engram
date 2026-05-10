# Engram Memory

You have persistent memory via three MCP tools: `store_memory`, `recall_memory`, `summarize_memories`.

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

## Session Start

Call `recall_memory` before responding to the first message.

- Query: derive from the opening message or inferred session topic
- `top_k`: 5
- Include `project_id` if in a project
- If in a project, also recall without `project_id` (captures global preferences)
- Incorporate results silently. Do not announce or narrate the recall.

---

## During Conversation

### Recall

Call `recall_memory` (top_k: 3) before proposing an architecture, design, or tooling choice, and whenever the topic shifts domain or a new technology is introduced. Query the new context, not the session opener. Incorporate silently.

### Store

Call `store_memory` when a decision with rationale, a preference, a constraint, or significant technical context is established, or when the user explicitly requests it. Skip if already stored this session.

---

## Session End

Before your final response, or when the conversation is clearly winding down, store a summary of what was accomplished or decided.

- `text`: concise summary, 500 tokens max
- `scope`: `"project"` or `"global"` per session context
- Do not store a summary if nothing meaningful occurred

---

## Summarize

Call `summarize_memories` when:

- The user asks to compress or summarize memories
- You notice recall results are redundant or fragmented across many entries

Pass `delete_originals: true` only when the user explicitly asks to prune.

---

## Do NOT Store

- Routine messages or pleasantries
- Widely known facts or documentation
- Command outputs
- Commands (unless the user explicitly requests it)
- Entire file contents
- Anything with no value in a future session
