# engram

A personal memory layer for agentic AI that persists context across conversations, sessions, and projects. Secured with mTLS and deployed entirely in your own AWS infrastructure.

---

## How It Works

```
Claude Code
    |  stdio (MCP protocol)
    v
mcp_server/   (runs locally on your machine)
    |  mTLS HTTPS (client cert + CA chain validation)
    v
API Gateway HTTP API  (custom domain, mTLS enforced)
    |  Lambda proxy  (cert pinning enforced in handler)
    v
engram-memory-handler Lambda  (Python 3.12, arm64)
    |-- Bedrock Titan Embed v2      (vector embeddings)
    |-- S3 Vectors                  (semantic search + flat key storage)
    +-- Secrets Manager             (cert pinning reference)
```

Claude Code spawns the MCP server locally. The MCP server exposes five tools (`store_memory`, `recall_memory`, `search_related_findings`, `summarize_memories`, `delete_memory`) over mTLS. Each memory is stored as a flat key (`memories/{uuid}`) in S3 Vectors with arbitrary tags in metadata (e.g. `scope:project`, `project:engram`, `memory_type:decision`). Recall uses weighted tag boosting to surface the most relevant results.

> **VPC reference:** The last commit with full VPC isolation (Lambda + Interface Endpoints) is [`5e2eaea`](https://github.com/bradduhon/engram/commit/5e2eaea). That architecture costs ~$58/month in endpoint fees.

---

## The Enforcement Problem

CLAUDE.md instructions are treated as preferences — the model weighs them against its training priors at inference time. A directive like "call recall_memory before responding" competes with the model's prior to respond immediately, and the prior can win.

**Engram solves this with hooks.** The `UserPromptSubmit` hook calls the Engram recall API directly over mTLS and injects results into the system-reminder before Claude processes the message. The `PreToolUse` hook on `store_memory` blocks anti-patterns before they execute. Claude receives context as data, not instructions — compliance is not required.

| Layer | Hook | Enforcement |
|---|---|---|
| Session load | `session-start-engram.sh` | Recall fires unconditionally at session open |
| Mid-session | `prompt-context-engram.sh` | Recall fires on topic shift, every message |
| Recall quality | `recall-confidence-check.sh` | Forces query expansion on low-confidence results |
| Storage gate | `store-hygiene-gate.sh` | Blocks anti-patterns before `store_memory` executes |
| Post-compact | `compact-reminder.sh` | Re-orientation block after context compression |

---

## Hooks

All hooks live in `hooks/` and are wired in `~/.claude/settings.json` by absolute path.

### `session-start-engram.sh` — UserPromptSubmit

Fires on the first user message of each session. Calls the Engram recall API directly over mTLS, detects the current git project, boosts project-tagged memories via weighted recall, and injects a `[ENGRAM CONTEXT]` block into the system-reminder. No MCP tool call from Claude is required.

**What you get:** Without this hook, every session starts with zero memory context — Claude must be told what the project is, what decisions were made, and what was decided last time. With it, that context is present before Claude's first token. The recall executes via bash, not via Claude, so it is not subject to model compliance — it either succeeds (API up, certs valid) or fails (infra issue). There is no path where Claude "decides not to recall."

### `prompt-context-engram.sh` — UserPromptSubmit

Fires on every subsequent message. Classifies the prompt (skips affirmations and short continuations), extracts a keyword query, and injects a `[ENGRAM MID-SESSION CONTEXT]` block when the topic shifts.

**What you get:** Without this hook, session-start context is the only automatic recall — if you shift from Terraform to PKI mid-session, Claude has no mechanism to load PKI memories without an explicit tool call. With it, each substantive message triggers a fresh recall keyed to that message's content. The injection happens before Claude processes the message, so the new context lands before the response, not after. This is also bash-executed and not subject to model compliance.

### `recall-confidence-check.sh` — PostToolUse

Fires after any `recall_memory` MCP call. Inspects the relevance scores and emits a nudge when results are empty or the best score is below 0.6.

**What you get:** Without this hook, Claude accepts whatever `recall_memory` returns and proceeds. A 0.4-score result may be used as if it were authoritative. With it, low-confidence results trigger an explicit instruction to expand the query with semantic variants. This is probabilistic — the nudge increases the likelihood Claude retries with a better query, but does not guarantee it. The concrete gain is that weak recall is surfaced rather than silently accepted.

### `store-hygiene-gate.sh` — PreToolUse

Fires before every `store_memory` call. Blocks (exit 2) on session-completion and task-noise anti-patterns and on text under 8 words. Emits a non-blocking confirmation reminder for all other calls.

**What you get:** The anti-pattern block is deterministic — a memory matching the regex cannot be stored regardless of Claude's intent. The tool call is cancelled at the hook layer before it reaches the API. The confirmation reminder for non-blocked calls is probabilistic: it increases the likelihood Claude verifies `/hygiene` was run, but does not enforce it. Together, the hook eliminates the worst categories of noise mechanically and raises the bar for everything else.

### `compact-reminder.sh` — PostCompact

Fires after Claude Code compresses the conversation context. Injects a re-orientation block with security invariants, IAM blast-radius gates, hard stops, and an instruction to call `recall_memory` before continuing.

**What you get:** After compaction, Claude's working context is replaced with a summary. Without this hook, security invariants and project conventions that were in the prior context are gone until Claude re-encounters them. With it, the invariants are re-injected immediately as the first thing in the new context window. The recall instruction is probabilistic — Claude is more likely to recall project context post-compact, but it is an instruction rather than a forced tool call.

---

## Memory Quality — `/hygiene`

`skills/hygiene/SKILL.md` is a Claude Code slash command (`/hygiene`) that gates every `store_memory` call through:

1. **Classification** — STATE / DECISION / RULE / DISCOVERY / QUIRK
2. **Generalizability test** — abstracts rules/discoveries to the broadest actionable pattern with the specific incident as a citation
3. **Single state entry enforcement** — recalls existing project state entry first; proposes update-in-place rather than a new entry
4. **Anti-pattern filter** — blocks session completions, backlog snapshots, PR announcements, command dumps

Outputs a proposed `store_memory` call with all fields for user confirmation before executing.

**What you get:** Without `/hygiene`, store decisions are ad-hoc — Claude chooses what to store, how to phrase it, and whether to create a new entry or update an existing one, with no consistent gate. With it, every candidate memory is classified, tested for appropriate abstraction level, and confirmed before storage. The single-state-entry check is the concrete gain: it prevents the proliferation of redundant "session complete" and "project state as of" entries that degrade recall quality over time. The generalizability test converts incident-specific lessons into reusable patterns. Both are applied at the point of storage, before the memory exists in the index.

The `store-hygiene-gate.sh` hook is the mechanical fallback — it blocks the most obvious violations even when `/hygiene` is skipped. The rule file (`rules/memory.md`) is the written directive. Together they form three layers: written instruction, probabilistic reminder, deterministic block.

The skill is symlinked into `~/.claude/skills/hygiene` for global availability.

---

## Memory Protocol — `rules/memory.md`

A global rule file (symlinked from `rules/memory.md` to `~/.claude/rules/memory.md`) that is loaded into every Claude Code session. Defines:

- **Store gate:** `/hygiene` is mandatory before `store_memory`. Direct calls are only acceptable on explicit user instruction.
- **Recall depth:** Initial search at top_k=5, confidence check against relevance scores, recursive expansion with semantic variants if results are weak, explicit zero-knowledge declaration after 3 failed iterations.

**What you get:** Without the rule file, the only written guidance is in CLAUDE.md — which is treated as a preference, not a constraint. The rule file is loaded separately and more prominently, increasing the probability Claude applies the hygiene gate and the recall depth protocol without being reminded each session. This is probabilistic gain: a more specific, always-present directive produces more consistent behavior than a general CLAUDE.md entry.

---

## MCP Tools

| Tool | Purpose |
|---|---|
| `store_memory` | Persist a memory with tags, conversation_id, and memory_type |
| `recall_memory` | Semantic search with optional tag weight boosting |
| `search_related_findings` | Retrieve temporal context around a specific memory result |
| `summarize_memories` | Compress many memories into a concise summary. Optionally delete originals |
| `delete_memory` | Remove a specific memory by ID |

### Tags

Memories use an arbitrary tag set rather than fixed scopes. Common conventions:

| Tag | Meaning |
|---|---|
| `scope:global` | Applies across all projects |
| `scope:project` | Tied to a specific project |
| `project:<id>` | Project identifier (e.g. `project:engram`) |
| `memory_type:decision` | Architectural or design choice |
| `memory_type:rule` | Behavioral constraint or pattern |
| `memory_type:discovery` | Non-obvious finding about a system or tool |

When recalling, pass `weights` to boost matching tags (e.g. `{"project:engram": 1.5}` surfaces project memories first without hard-filtering global ones).

---

## Prerequisites

```bash
# AWS CLI v2
aws --version

# Terraform >= 1.5
terraform -version

# Python 3.12+
python3 --version

# age (private key encryption)
sudo apt install age   # or https://github.com/FiloSottile/age/releases

# jq and curl (used by hooks)
sudo apt install jq curl
```

**AWS account requirements:**
- CLI profile configured (`aws configure` or SSO)
- Permissions to create: IAM roles, Lambda, ACM certificates, API Gateway, S3, Secrets Manager, Bedrock, CloudWatch, SNS, EventBridge
- Bedrock model access for `amazon.titan-embed-text-v2:0` and `anthropic.claude-haiku-4-5-20251001-v1:0`
- A domain name with a DNS zone you control

**Enabling Bedrock model access:** Open the [Bedrock Model Catalog](https://console.aws.amazon.com/bedrock/home#/model-catalog), find Claude Haiku 4.5, click "Submit use case details", and fill in the form. Titan Embeddings v2 is typically approved immediately without a form.

**Install the MCP server package:**

```bash
cd <path-to-engram-repo>
pip install -e ".[mcp-server]"
```

Use the full path to this virtualenv's Python interpreter when configuring `~/.claude.json`. Claude Code spawns the server globally — a bare `python` may resolve to the wrong environment.

---

## Deployment

### Step 1: Bootstrap Terraform state backend

Run once. Creates the S3 bucket and DynamoDB table for remote state.

```bash
cd terraform/bootstrap

cat > terraform.tfvars <<EOF
aws_region  = "us-east-1"
aws_profile = "default"
EOF

terraform init && terraform apply
```

Note the outputs: `state_bucket_name` and `lock_table_name`.

### Step 2: Configure the remote backend

```bash
cd ..   # terraform/
cp backend.hcl.example backend.hcl
```

Edit `backend.hcl`:

```hcl
bucket         = "<state_bucket_name>"
key            = "engram/terraform.tfstate"
region         = "us-east-1"
dynamodb_table = "<lock_table_name>"
profile        = "default"
```

```bash
terraform init -backend-config=backend.hcl
```

### Step 3: Configure variables

```bash
cat > terraform.tfvars <<EOF
aws_region         = "us-east-1"
aws_profile        = "default"
server_domain_name = "memory.<your-domain>"
client_domain_name = "mcp-client.<your-domain>"
alert_email        = "<your-email>"
EOF
```

### Step 4: Deploy infrastructure

```bash
terraform apply
```

Terraform will pause at `aws_acm_certificate_validation`. While it waits, retrieve the DNS validation records and add them to your zone:

```bash
terraform output -json server_cert_validation_records
terraform output -json client_cert_validation_records
```

After ACM issues the certs (1-5 minutes), Terraform resumes. When complete, manually create the DNS A/CNAME record:

```bash
terraform output custom_domain_target
# Point memory.<your-domain> at this value
```

### Step 5: Export the client certificate

Exports the cert bundle to Secrets Manager and builds the mTLS truststore in S3.

```bash
cd ..   # engram root
CLIENT_CERT_ARN=$(terraform -chdir=terraform output -raw client_cert_arn)
python scripts/export_client_cert.py "$CLIENT_CERT_ARN" --profile <aws-profile>
```

Add the printed `truststore_version` to `terraform/terraform.tfvars`, then apply:

```bash
cd terraform && terraform apply
```

### Step 6: Set up local certificate storage

```bash
./scripts/setup-certs.sh <aws-profile> [aws-region]
```

Creates `~/.claude/certs/` with the age-encrypted private key, client cert, and CA bundle. The plaintext key is never written to disk.

### Step 7: Confirm SNS alert subscription

Check your `alert_email` inbox and confirm the SNS subscription for CloudWatch alarm notifications.

---

## Post-Deployment Configuration

### MCP server (`~/.claude.json`)

```json
{
  "mcpServers": {
    "engram-memory": {
      "command": "<absolute-path-to-venv>/bin/python",
      "args": ["-m", "mcp_server.server"],
      "env": {
        "MEMORY_API_URL": "https://memory.<your-domain>"
      }
    }
  }
}
```

### CLAUDE.md (`~/.claude/CLAUDE.md`)

```markdown
# Memory

You have access to an Engram memory MCP server with tools: `store_memory`, `recall_memory`,
`search_related_findings`, `summarize_memories`, `delete_memory`. Behavior is defined in
[Engram.md](<absolute-path-to-engram-repo>/Engram.md).
```

### Permissions (`~/.claude/settings.json`)

```json
{
  "permissions": {
    "allow": [
      "mcp__engram-memory__store_memory",
      "mcp__engram-memory__recall_memory",
      "mcp__engram-memory__search_related_findings",
      "mcp__engram-memory__summarize_memories",
      "mcp__engram-memory__delete_memory"
    ]
  }
}
```

### Hooks (`~/.claude/settings.json`)

```json
{
  "env": {
    "MEMORY_API_URL": "https://memory.<your-domain>"
  },
  "hooks": {
    "UserPromptSubmit": [
      {
        "matcher": "",
        "hooks": [{
          "type": "command",
          "command": "bash <repo>/hooks/session-start-engram.sh",
          "timeout": 15
        }]
      },
      {
        "matcher": "",
        "hooks": [{
          "type": "command",
          "command": "bash <repo>/hooks/prompt-context-engram.sh",
          "timeout": 10
        }]
      }
    ],
    "PreToolUse": [
      {
        "matcher": "mcp__engram-memory__store_memory",
        "hooks": [{
          "type": "command",
          "command": "bash <repo>/hooks/store-hygiene-gate.sh",
          "timeout": 5
        }]
      }
    ],
    "PostToolUse": [
      {
        "matcher": "mcp__engram-memory__recall_memory",
        "hooks": [{
          "type": "command",
          "command": "bash <repo>/hooks/recall-confidence-check.sh",
          "timeout": 10
        }]
      }
    ],
    "PostCompact": [
      {
        "matcher": "auto|manual",
        "hooks": [{
          "type": "command",
          "command": "bash <repo>/hooks/compact-reminder.sh",
          "timeout": 15
        }]
      }
    ]
  }
}
```

`MEMORY_API_URL` is required by `session-start-engram.sh` and `prompt-context-engram.sh`. The other hooks do not use it. If you have existing hook entries, merge these into your arrays rather than replacing them.

### Symlinks

```bash
ln -s <repo>/skills/hygiene ~/.claude/skills/hygiene
ln -s <repo>/rules/memory.md ~/.claude/rules/memory.md
```

### Verify

```bash
MEMORY_API_URL=https://memory.<your-domain> python3 scripts/smoke_test.py
```

On the first session message, the `[ENGRAM CONTEXT]` block appears in the system-reminder. No tool call from Claude required.

---

## Cert Rotation

ACM auto-renews. When the cert rotates:

1. EventBridge triggers the cert rotator Lambda — it re-exports the bundle to Secrets Manager automatically.
2. Rebuild the truststore:
   ```bash
   CLIENT_CERT_ARN=$(terraform -chdir=terraform output -raw client_cert_arn)
   python scripts/export_client_cert.py "$CLIENT_CERT_ARN" --profile <aws-profile>
   ```
3. Update `truststore_version` in `terraform.tfvars` and apply:
   ```bash
   cd terraform && terraform apply
   ```
4. Refresh local certs:
   ```bash
   ./scripts/setup-certs.sh <aws-profile> [aws-region]
   ```

`age-identity.txt` is never rotated. Only `client.crt` and `client.key.age` are overwritten.

---

## Security

| Layer | Control |
|---|---|
| Transport (layer 1) | mTLS via API Gateway. Truststore: Amazon RSA 2048 M04 intermediate + Amazon Root CA 1 |
| Transport (layer 2) | Lambda cert pinning — compares leaf cert byte-for-byte against Secrets Manager reference |
| Network | Lambda outside VPC. Access via AWS public endpoints, controlled by IAM and resource policies |
| S3 | Bucket policy denies external account requests. TLS enforced via `aws:SecureTransport` deny |
| Data at rest | SSE-KMS (`aws/s3`). Secrets Manager default encryption |
| Private key (MCP server) | Fetched to process memory; written to a `0o600` temp file for the connection lifetime only |
| Private key (hooks) | age-encrypted on disk; decrypted via process substitution — plaintext in kernel pipe buffer only |
| IAM | Scoped to exact actions and ARNs. Explicit deny on Bedrock admin APIs |
| Blast radius | Lambda concurrency = 10. API Gateway: 100 burst / 50 steady |

---

## Directory Structure

```
engram/
  terraform/
    bootstrap/        # One-time TF state backend (local state, run once)
    modules/
      storage/        # S3 artifacts bucket, S3 Vectors bucket + index
      certificates/   # ACM server + client certs, Secrets Manager shells
      compute/        # Lambda functions, IAM roles
      api/            # API Gateway, custom domain, mTLS, routes
      observability/  # CloudWatch alarms, SNS, EventBridge scheduler
    main.tf           # Root module
  src/
    memory_handler/   # Lambda: store/recall/summarize/prune via Bedrock + S3 Vectors
    cert_rotator/     # Lambda: ACM cert re-export to Secrets Manager on renewal
  mcp_server/         # Local MCP server (Claude Code child process, stdio transport)
  hooks/
    session-start-engram.sh     # UserPromptSubmit: session-open recall + context injection
    prompt-context-engram.sh    # UserPromptSubmit: mid-session recall on topic shift
    store-hygiene-gate.sh       # PreToolUse: blocks anti-patterns before store_memory
    recall-confidence-check.sh  # PostToolUse: forces query expansion on low-confidence results
    compact-reminder.sh         # PostCompact: re-orientation block + security invariants
  rules/
    memory.md                   # Store/recall protocol — symlinked: ~/.claude/rules/memory.md
  skills/
    hygiene/
      SKILL.md                  # /hygiene slash command — symlinked: ~/.claude/skills/hygiene
  scripts/
    export_client_cert.py       # Export ACM client cert into Secrets Manager + build truststore
    setup-certs.sh              # One-time local cert setup (age-encrypted key)
    smoke_test.py               # End-to-end mTLS store/recall/search_related verification
    migrate_to_flat_keys.py     # One-time migration: prefix keys -> flat keys with tag injection
    backup_vectors.py           # Backup all vectors to JSON before migrations
    restore_from_backup.py      # Restore vectors from backup JSON
    bulk_delete.py              # Content-addressed bulk delete by index from backup
  Engram.md                     # Claude behavioral contract: when/how to store, recall, gate
  CHANGELOG.md                  # Version history
  Features.md                   # Feature backlog and completed work log
```
