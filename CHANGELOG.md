# Changelog

All notable changes to Engram are documented here.

---

## [Unreleased] — 2026-06-07

### Added
- `prompt-context-engram.sh` — `UserPromptSubmit` hook that fires on every message after the first. Classifies the prompt, skips affirmations and short continuations, and injects a `[ENGRAM MID-SESSION CONTEXT]` block via direct mTLS recall when the topic shifts. Complements `session-start-engram.sh` by narrowing recall to the specific content of each new prompt rather than broad project context.
- `compact-reminder.sh` — `PostCompact` hook that replaces `post-compact-memory.sh`. Injects a re-orientation block after context compaction: security invariants, IAM blast-radius gates, hard stops, and an instruction to call `recall_memory` before continuing.
- `skills/hygiene/SKILL.md` — `/hygiene` slash command. Gates all `store_memory` calls through a classification step (STATE / DECISION / RULE / DISCOVERY / QUIRK), a generalizability test for rules and discoveries, a single-state-entry enforcement check (recall existing state entry first, propose update-in-place rather than new entry), and an anti-pattern filter. Outputs a proposed `store_memory` block for user confirmation before executing. Symlinked into `~/.claude/skills/hygiene`.

### Removed
- `post-compact-memory.sh` — PostCompact hook that stored compaction summaries as memories. Removed because compaction summaries are Claude's compression artifacts, not curated knowledge: signal-to-noise is low, content is often stale within the same session, and storage decisions should be deliberate (via `/hygiene`), not automatic.

### Changed
- `README.md` — Documented `prompt-context-engram.sh` (previously untracked). Replaced `post-compact-memory.sh` documentation with `compact-reminder.sh`. Removed "Automatic Memory via PostCompact" section. Updated hooks configuration example and directory structure.
- `Engram.md` — Tool count corrected (three → five). `Store` section now gates all calls through `/hygiene`. `Session End` reversed: no longer instructs auto-storage of summaries; delegates to `/hygiene` instead. `Do NOT Store` list expanded to match hygiene skill anti-patterns (session completions, backlog snapshots, PR announcements, 2-week staleness test).
- `~/.claude/CLAUDE.md` (global) — Fixed typo `recall_memort` → `recall_memory`. `store_memory` directive now gates through `/hygiene`.

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
