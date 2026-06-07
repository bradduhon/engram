# Features

This is where Features will be logged to work on with Claude. When a feature is finished, move it from the `New Features` section, to the `Completed Features` section, include the branch and commit id it was fixed on as well as a description on the technical implementation.

## New Features

## Completed Features

### 2026.06.07 - Engram should be more dynamic than project and global scopes

**Branch:** `feature/abac-tags` — PR #12

**Implementation:** Replaced the two-scope (`global` / `project`) model with flat S3 Vector keys (`memories/{uuid}`) and an arbitrary tag set stored in metadata (e.g. `scope:project`, `project:engram`, `memory_type:decision`). Recall uses a `weights` dict to multiply base cosine relevance for matching tags — soft boosting without hard filtering. Migration script re-embeds all 72 existing vectors via Bedrock Titan Embed v2 (S3 Vectors does not expose raw float values via GetVectors) and writes them at flat keys with injected tags. `POST /prune` route added for bulk tag-filtered deletion.

### 2026.06.07 - We need a way to organically cleanup memories that no longer have long term purpose

**Branch:** `feature/abac-tags` — PR #12

**Implementation:** `/hygiene` slash command (`skills/hygiene/SKILL.md`) classifies candidate memories (STATE / DECISION / RULE / DISCOVERY / QUIRK), applies a generalizability test to rules and discoveries, enforces a single rolling state entry per project (recall before creating), and blocks anti-patterns (session completions, backlog snapshots, PR announcements). Replaces `post-compact-memory.sh` which stored compact summaries wholesale.