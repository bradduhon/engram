# Changelog

All notable changes to Engram are documented here.

---

## [0.10.0] — 2026-06-07

### Added
- `prompt-context-engram.sh` — `UserPromptSubmit` hook that fires on every message after the first. Classifies the prompt, skips affirmations and short continuations, and injects a `[ENGRAM MID-SESSION CONTEXT]` block via direct mTLS recall when the topic shifts.
- `compact-reminder.sh` — `PostCompact` hook replacing `post-compact-memory.sh`. Injects a re-orientation block after context compaction: security invariants, IAM blast-radius gates, hard stops, and a `recall_memory` instruction.
- `hooks/store-hygiene-gate.sh` — `PreToolUse` hook on `store_memory`. Deterministically blocks (exit 2) session-completion/task-noise anti-patterns and sub-8-word text. Emits a non-blocking confirmation reminder for all other calls.
- `skills/hygiene/SKILL.md` — `/hygiene` slash command. Classifies candidates (STATE / DECISION / RULE / DISCOVERY / QUIRK), applies a generalizability test, enforces single-state-entry-per-project, filters anti-patterns, and outputs a proposed `store_memory` call for confirmation. Symlinked into `~/.claude/skills/hygiene`.
- `rules/memory.md` — Engram store/recall protocol moved into the repo and symlinked to `~/.claude/rules/memory.md`. Mandates `/hygiene` before `store_memory` and defines the three-iteration recall depth protocol.
- `CHANGELOG.md`, `Features.md` — version history and feature log added to the repo.

### Removed
- `post-compact-memory.sh` — stored compact summaries automatically. Removed: compaction summaries are Claude's compression artifacts; signal-to-noise is low and storage decisions should be deliberate.

### Changed
- `README.md` — full restructure. Hook, skill, and rule sections include "What you get" blocks distinguishing deterministic gains from probabilistic gains. Tags section replaces stale scope/project_id model. Symlink setup documented.
- `Engram.md` — tool count corrected (three → five). Store section gates through `/hygiene`. Session End no longer instructs auto-storage. Do NOT Store list expanded to match hygiene skill anti-patterns.
- `~/.claude/CLAUDE.md` (global) — fixed typo `recall_memort` → `recall_memory`. `store_memory` directive now gates through `/hygiene`.

### Fixed
- `scripts/migrate_to_flat_keys.py` — S3 Vectors `GetVectors` does not return raw float values; switched to Bedrock Titan Embed v2 re-embedding from stored metadata `text` field. 72 vectors migrated, smoke test passing.

---

## [0.9.0] — 2026-05-18

### Fixed
- `fix(recall)`: enforce scope/project_id filter in vector query — prevents cross-scope result bleed when recalling project-scoped memories.

---

## [0.8.0] — 2026-05-15

### Added
- Documented the LLM enforcement problem in README: CLAUDE.md directives are advisory; the `UserPromptSubmit` hook is unconditional.
- Missing API routes for `delete` and `search_related_findings` added to README.
- `session-start-engram.sh` and `recall-confidence-check.sh` hooks shipped and documented.

### Changed
- README restructured: hooks section expanded to explain the two-layer enforcement model (direct recall injection + PostToolUse quality gate).
- `Engram.md`: removed redundant session-start section.

---

## [0.7.0] — 2026-05-13

### Added
- `delete_memory` tool in Lambda handler and MCP server.
- `smoke_test.py` for end-to-end mTLS store/recall/search_related verification.

---

## [0.6.0] — 2026-05-11

### Changed
- Documented two-step `terraform apply` requirement for removing Lambda from a VPC (ENI release timing gotcha).

---

## [0.5.0] — 2026-05-10

### Removed
- VPC layer: networking module deleted, four Interface Endpoints eliminated (~$58/month savings). Lambda communicates with Bedrock, S3 Vectors, and Secrets Manager over public endpoints, controlled by IAM and resource policies.

### Added
- VPC reference commit (`5e2eaea`) preserved in README for users who prefer full network isolation.

---

## [0.4.0] — 2026-05-10

### Fixed
- MCP server global availability: corrected `pyproject.toml` build backend and package discovery so the server is importable from any working directory after `pip install -e`.

---

## [0.3.0] — 2026-05-09

### Changed
- `Engram.md`: added mid-conversation recall trigger; reduced token footprint.

### Removed
- `docs/phases/` spec files — content superseded by GitHub issues.

---

## [0.2.0] — 2026-05-09

### Added
- Complete Engram implementation: Phases 3–7.
  - Phase 3: Lambda memory handler (store/recall/summarize via Bedrock Titan Embed v2 + S3 Vectors).
  - Phase 4: API Gateway with mTLS, custom domain, cert pinning.
  - Phase 5: MCP server (local child process, stdio transport).
  - Phase 6: Observability — CloudWatch alarms, SNS, EventBridge daily summarizer.
  - Phase 7: PostCompact hook with age-encrypted private key.
- `cert_rotator` Lambda: ACM cert re-export to Secrets Manager on renewal via EventBridge.
- Fixed MCP server config location (`~/.claude.json`, not `mcp_servers.json`).
- Switched MCP server cert loading from Secrets Manager to local age-encrypted key.

---

## [0.1.0] — 2026-05-09

### Added
- Initial commit: Terraform bootstrap, implementation spec, Phase 1–2 infrastructure (storage, certificates modules).
