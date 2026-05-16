# engram

A personal memory layer for agentic AI that persists context across conversations, sessions, and projects. Secured with mTLS at the transport layer and deployed entirely in your own AWS infrastructure.

## Why Engram Exists

Agentic AI tools like Claude Code lose all context when a session ends. Every new conversation starts from zero. Engram solves this by giving Claude persistent, semantically-searchable memory backed by vector embeddings. You store memories explicitly or automatically, and on any future conversation Claude can recall past decisions, preferences, project state, and architectural rationale by semantic similarity rather than keyword matching.

The result: Claude remembers what you decided last week, why you chose a specific architecture, and what trade-offs you considered, across every project on your machine.

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
    |-- S3 Vectors                  (semantic search index)
    +-- Secrets Manager             (cert pinning reference)
```

1. Claude Code spawns the MCP server as a local child process via stdio.
2. The MCP server exposes five tools (`store_memory`, `recall_memory`, `search_related_findings`, `summarize_memories`, `delete_memory`) that Claude can call like any other tool.
3. Each API call is authenticated with mTLS. The client certificate is an ACM exportable cert; the private key is age-encrypted at rest and decrypted only into process memory.
4. The Lambda handler generates vector embeddings via Bedrock Titan Embed v2 and stores/queries them in S3 Vector Tables.
5. Lambda additionally pins the exact leaf certificate, rejecting any client cert that wasn't explicitly exported for this deployment, even if signed by the same CA.

Lambda communicates with AWS services over their public endpoints. Access is controlled by IAM policies and resource policies, not network isolation.

> **VPC deployment reference:** If you prefer full network isolation (Lambda in a private VPC with Interface Endpoints for Bedrock, S3 Vectors, and Secrets Manager), the last commit with that configuration is [`5e2eaea`](https://github.com/bradduhon/engram/commit/5e2eaea). That architecture costs ~$58/month in VPC endpoint fees.

## The Enforcement Problem

**Claude Code will, by default, not use Engram at session start.** This is not a configuration gap — it is a fundamental property of how large language models process instructions.

CLAUDE.md instructions, however explicit, are treated as preferences. The model weighs them against its training priors at inference time. A directive like "call recall_memory before responding" competes with the model's strong prior to respond immediately. The prior wins — consistently — unless every available enforcement surface is saturated simultaneously.

There is no `PreResponse` hook in Claude Code's event model. No mechanism exists to block the model from generating text before a tool call completes. The hook architecture fires on tool events only, not on text generation events. This means you cannot mechanically gate a response behind a tool call. You can only increase the probability of compliance through redundant, overlapping instructions.

Engram addresses this with three layers working in parallel:

| Layer | Mechanism | What it does |
|-------|-----------|--------------|
| 1 — Load-order gate | `[HARD REQUIREMENT]` block at line 1 of `~/.claude/CLAUDE.md` | First instruction the model reads. Refusal-framed: "DO NOT generate any response until..." |
| 2 — Context injection | `SessionStart` hook injects a mandatory recall directive into conversation context | Repeats the requirement at runtime, immediately before the first user message |
| 3 — Quality enforcement | `PostToolUse` hook on `recall_memory` | Fires after every recall call, validates relevance scores, forces query expansion below 0.6 |

Even with all three layers active, compliance is probabilistic. The model can still violate the gate. What the layered approach does is make violation the path of higher resistance — it requires the model to ignore instructions in CLAUDE.md, the injected context directive, and the structural framing of the HARD REQUIREMENT block simultaneously.

If you observe the session gate being skipped, the cause is almost always one of:
- The `[HARD REQUIREMENT]` block is not at the top of the global CLAUDE.md (it must precede all other content)
- The SessionStart hook failed silently (check `MEMORY_API_URL` is set in `~/.claude/settings.json` env block)
- The MCP server is down or the tool is not auto-allowed in permissions

---

## Hooks and Automation

Engram ships three Claude Code hooks that automate memory operations without user intervention. Each hook is wired in `~/.claude/settings.json` and references scripts in this repository's `hooks/` directory.

### SessionStart Hook — `session-start-engram.sh`

**Event:** `SessionStart` (fires once when Claude Code launches a new session)

Injects a mandatory directive into the conversation context that instructs Claude to call `recall_memory` via MCP before responding to the first message. If a git project is detected, it requests project-scoped memories (top_k=8) first, then global memories (top_k=3). If no project is detected, it requests global memories only (top_k=5).

This is the mechanism that makes Claude actually use Engram at session start. Without it, CLAUDE.md instructions alone are unreliably followed.

### PostCompact Hook — `post-compact-memory.sh`

**Event:** `PostCompact` (fires when Claude Code compresses the conversation context, either automatically or via `/compact`)

Reads the compaction summary from stdin and stores it as a memory via the Engram API over mTLS. The private key is decrypted inline via process substitution so plaintext exists only in a kernel pipe buffer, never as a named file. Memories are tagged with `trigger: compact_auto` or `trigger: compact_manual` and scoped to the current project or global.

This means Claude builds memory passively over the lifetime of every conversation without any explicit action from the user.

### PostToolUse Hook — `recall-confidence-check.sh`

**Event:** `PostToolUse` (fires after `recall_memory` returns results)

Inspects the recall response and nudges Claude when results are empty or when the best relevance score is below 0.6. The nudge instructs Claude to expand the query with alternate terminology, resource ARNs, or security standard names before declaring zero-knowledge. This enforces the recall protocol defined in `Engram.md` at the hook level rather than relying on CLAUDE.md instructions.

## MCP Tools

Once the MCP server is running, Claude Code has five tools available:

| Tool | Purpose |
|------|---------|
| `store_memory` | Persist a memory with scope (project or global), project_id, and conversation_id |
| `recall_memory` | Search memories by semantic similarity. Returns relevance scores and timestamps |
| `search_related_findings` | Retrieve temporal context around a specific memory result (same-session neighbors) |
| `summarize_memories` | Compress many memories into a concise summary. Optionally delete originals |
| `delete_memory` | Remove a specific memory by ID |

### Scopes

| Scope | When to use | Searchable across |
|-------|-------------|-------------------|
| `global` | Cross-project preferences, personal style, general decisions | All conversations |
| `project` | Project-specific context, decisions, architecture | Conversations in that project |

When recalling with a `project_id`, the service searches both the project scope and global scope and returns the combined top results.

### Automatic Memory via PostCompact

The PostCompact hook fires whenever Claude Code compresses the conversation context. It extracts the summary and stores it as a memory automatically. This means context accumulates passively across every conversation without explicit user action.

---

## Prerequisites

### Tools

```bash
# AWS CLI v2
aws --version

# Terraform >= 1.5
terraform -version

# Python 3.12+
python3 --version

# age (key encryption for local cert storage)
# Ubuntu/Debian:
sudo apt install age
# or from https://github.com/FiloSottile/age/releases

# jq and curl (used by hooks)
sudo apt install jq curl
```

### AWS Account

You need:
- An AWS account with a CLI profile configured (`aws configure`)
- Permissions to create: IAM roles, Lambda, ACM certificates, API Gateway, S3, Secrets Manager, Bedrock, CloudWatch, SNS, EventBridge
- Bedrock model access enabled in your target region for:
  - `amazon.titan-embed-text-v2:0`
  - `anthropic.claude-haiku-4-5-20251001-v1:0`
- A domain name with a DNS zone you control (Route53 or any external provider)

#### Enabling Bedrock Model Access

Anthropic requires first-time customers to submit use case details before invoking any Claude model. This is a one-time step per AWS account (or once at the organization management account). The information is shared with Anthropic.

1. Open the [Amazon Bedrock Model Catalog](https://console.aws.amazon.com/bedrock/home#/model-catalog) in your target region.
2. Search for **Claude Haiku 4.5** and click **Submit use case details**.
3. Fill in the form:
   - **Company Name:** Your full name, or "Self/Individual Developer"
   - **Company Website:** Your personal portfolio, GitHub profile (`https://github.com/<you>`), or `https://aws.amazon.com`
   - **Industry:** Technology, or Personal Project/Education
   - **Intended users:** Internal users (employees, staff, team members)
   - **Use Case Description:**
     ```
     This implementation leverages Claude models via Amazon Bedrock as the
     intelligence layer within a serverless memory microservice designed to
     provide persistent, semantically-searchable context across agentic AI
     interactions. The architecture addresses a fundamental limitation in
     current agentic workflows, the absence of durable, queryable memory
     that survives across sessions, interfaces, and deployments.
     ```
4. Submit. Access is typically granted within minutes.
5. Repeat for **Titan Embeddings v2** (`amazon.titan-embed-text-v2:0`) if not already enabled. Titan models are generally approved immediately without a use case form.

### Python (MCP server)

The MCP server must be installed as a package so it is importable from any working directory. Claude Code spawns the server globally, and relying on `cwd` alone is not reliable across projects.

```bash
cd <path-to-engram-repo>
pip install -e ".[mcp-server]"
```

---

## Deployment

### Step 1: Bootstrap Terraform state backend

Creates the S3 bucket and DynamoDB table used as the remote state backend. Run once.

```bash
cd terraform/bootstrap

cat > terraform.tfvars <<EOF
aws_region  = "us-east-1"
aws_profile = "default"
EOF

terraform init
terraform apply
```

Note the outputs: `state_bucket_name` and `lock_table_name`.

### Step 2: Configure the remote backend

```bash
cd ..   # back to terraform/
cp backend.hcl.example backend.hcl
```

Edit `backend.hcl`:

```hcl
bucket         = "<state_bucket_name from Step 1>"
key            = "engram/terraform.tfstate"
region         = "us-east-1"
dynamodb_table = "<lock_table_name from Step 1>"
profile        = "default"
```

Initialize with the remote backend:

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
alert_email        = "<your-email-address>"
EOF
```

> **Note on DNS:** The DNS A/CNAME record for `server_domain_name` is not created automatically. After `terraform apply` completes, run `terraform output custom_domain_target` to get the API Gateway regional domain name, then create the record in your DNS provider. See Step 4 below.

### Step 4: Deploy infrastructure

```bash
terraform apply
```

**Terraform will pause** at `aws_acm_certificate_validation` after creating the two ACM certificates. This is expected. While it waits, open a second terminal:

```bash
cd terraform/

# Get the CNAME records to add to your DNS zone
terraform output -json server_cert_validation_records
terraform output -json client_cert_validation_records
```

Add all CNAME records to your DNS zone (Route53, Cloudflare, etc.). ACM will issue the certificates within 1-5 minutes of DNS propagation, and Terraform will resume automatically.

After `terraform apply` completes, all infrastructure is live:
- API Gateway with mTLS at `https://memory.<your-domain>`
- Lambda memory handler
- S3 Vectors index for semantic search
- CloudWatch alarms and SNS alerts
- EventBridge daily summarizer (2:00 AM UTC)

**Manual DNS step (required):** Create an A or CNAME record in your DNS provider pointing `server_domain_name` to the API Gateway regional domain:

```bash
terraform output custom_domain_target
# e.g. d-xxxxxxxxxx.execute-api.us-east-1.amazonaws.com
```

Point `memory.<your-domain>` at that value. One-time step.

### Step 5: Export the client certificate and build the truststore

This step:
- Exports the cert bundle (cert + chain + encrypted key) into Secrets Manager for the MCP server and Lambda cert pinning
- Builds the mTLS truststore (Amazon RSA 2048 M04 intermediate + self-signed Amazon Root CA 1) and uploads it to S3
- Outputs the S3 object version ID needed to tell API Gateway to reload the truststore

```bash
cd ..   # engram project root

CLIENT_CERT_ARN=$(terraform -chdir=terraform output -raw client_cert_arn)

python scripts/export_client_cert.py "$CLIENT_CERT_ARN" --profile <aws-profile> [--region us-east-1]
```

The script will print:

```
Next steps:
  1. Set in terraform.tfvars:  truststore_version = "abc123..."
  2. Run:                       terraform apply -var-file=terraform.tfvars
  3. Run:                       ./scripts/setup-certs.sh <profile> [region]
```

Add the `truststore_version` value to `terraform/terraform.tfvars` and apply:

```bash
cd terraform
terraform apply -var-file=terraform.tfvars
```

This `truststore_version` tells API Gateway the exact S3 object version to read as the truststore. On cert renewal, repeat this step and update the version in `terraform.tfvars`.

### Step 6: Set up local certificate storage

Run once to create age-encrypted local certs used by the MCP server and PostCompact hook:

```bash
./scripts/setup-certs.sh <aws-profile> [aws-region]
```

`aws-region` defaults to `us-east-1` if omitted. Requires `secretsmanager:GetSecretValue` on `engram/mcp-client-cert*` secrets.

Creates:

```
~/.claude/certs/
  age-identity.txt              # age decryption key (chmod 600, never rotated)
  client.crt                    # mTLS client certificate (chmod 600)
  client.key.age                # mTLS private key, age-encrypted (chmod 600)
  amazon-trust-services-ca.pem  # Amazon root CA bundle (chmod 600)
```

The plaintext private key is never written to disk. It is decrypted from Secrets Manager and piped directly into `age` for encryption.

### Step 7: Confirm SNS alert subscription

Check the inbox for your `alert_email` and confirm the SNS subscription. This enables CloudWatch alarm notifications for Lambda errors, throttles, and high latency.

---

## Post-Deployment Configuration

These steps configure Claude Code to use Engram across all projects.

### Configure the MCP server

Add the `mcpServers` key to `~/.claude.json` (Claude Code's primary config file):

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

Use the full path to the Python interpreter from the virtualenv where you ran `pip install -e ".[mcp-server]"`. Do not use a bare `python` command; Claude Code may resolve it against a different environment.

`~/.claude.json` likely already exists. Add the `mcpServers` key without replacing the file contents.

> **Note:** The `cwd` field is not required when the package is installed via `pip install -e`. Omit it. If included and the working directory is wrong, the server fails silently in projects other than the engram repo.

### Configure CLAUDE.md

Add the following to your global `~/.claude/CLAUDE.md`:

```markdown
# Memory

You have access to an Engram memory MCP server with tools: `store_memory`, `recall_memory`, `search_related_findings`, `summarize_memories`, `delete_memory`. These tools persist context across all conversations, sessions, and projects. Behavior is defined in [Engram.md](<absolute-path-to-engram-repo>/Engram.md).
```

Replace `<absolute-path-to-engram-repo>` with the actual path (e.g. `/home/user/engram`).

`Engram.md` ships with this project and defines when Claude stores, recalls, and summarizes without user prompting.

### Configure global permissions

Add all Engram MCP tools to the `permissions.allow` array in `~/.claude/settings.json` so Claude can call them without prompting in every project:

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

Without this, Claude will ask for permission on every MCP call or silently skip them.

### Configure hooks

Add the following hook entries to `~/.claude/settings.json`. All hook scripts live in this repository's `hooks/` directory; reference them by absolute path.

Replace `<absolute-path-to-engram-repo>` with the actual path (e.g. `/home/user/engram`).

```json
{
  "env": {
    "MEMORY_API_URL": "https://memory.<your-domain>"
  },
  "hooks": {
    "SessionStart": [
      {
        "matcher": "",
        "hooks": [
          {
            "type": "command",
            "command": "bash <absolute-path-to-engram-repo>/hooks/session-start-engram.sh",
            "timeout": 15
          }
        ]
      }
    ],
    "PostToolUse": [
      {
        "matcher": "mcp__engram-memory__recall_memory",
        "hooks": [
          {
            "type": "command",
            "command": "bash <absolute-path-to-engram-repo>/hooks/recall-confidence-check.sh",
            "timeout": 10
          }
        ]
      }
    ],
    "PostCompact": [
      {
        "matcher": "auto|manual",
        "hooks": [
          {
            "type": "command",
            "command": "<absolute-path-to-engram-repo>/hooks/post-compact-memory.sh",
            "timeout": 15
          }
        ]
      }
    ]
  }
}
```

> **Note:** The `MEMORY_API_URL` env var is required by `post-compact-memory.sh` (it calls the API directly over mTLS). The SessionStart and recall-confidence-check hooks do not use it; they operate on Claude's context and MCP tool output respectively.

> **Note:** If you already have other hooks configured (e.g. `PreToolUse`, other `PostToolUse` matchers), merge the Engram entries into your existing arrays rather than replacing them.

### Verify the installation

Restart Claude Code. On the first session you should see Claude execute `recall_memory` calls before responding to your message. Verify:

1. The SessionStart hook fires (Claude reports a `[Context: ...]` status line)
2. The MCP tools are available (ask Claude: "What memory tools do you have?")
3. Store and recall work end-to-end:

```bash
# Store a test memory via mTLS (from terminal)
curl --silent \
  --cert ~/.claude/certs/client.crt \
  --key <(age -d -i ~/.claude/certs/age-identity.txt ~/.claude/certs/client.key.age) \
  --cacert ~/.claude/certs/amazon-trust-services-ca.pem \
  -X POST "https://memory.<your-domain>/store" \
  -H "Content-Type: application/json" \
  -d '{"text":"engram setup verification","scope":"global","conversation_id":"setup-verify"}'

# Recall it
curl --silent \
  --cert ~/.claude/certs/client.crt \
  --key <(age -d -i ~/.claude/certs/age-identity.txt ~/.claude/certs/client.key.age) \
  --cacert ~/.claude/certs/amazon-trust-services-ca.pem \
  -X POST "https://memory.<your-domain>/recall" \
  -H "Content-Type: application/json" \
  -d '{"query":"setup verification"}' | jq '.memories[0].text'

# Confirm unauthenticated requests are rejected (expects TLS handshake failure)
curl -s -o /dev/null -w "%{http_code}" \
  -X POST "https://memory.<your-domain>/store" \
  -H "Content-Type: application/json" \
  -d '{"text":"should fail","scope":"global","conversation_id":"test"}'
# Expected: 000 (no HTTP connection established — mTLS rejected the request)
```

Or use the smoke test script for end-to-end verification:

```bash
MEMORY_API_URL=https://memory.<your-domain> python3 scripts/smoke_test.py
```

---

## Cert Rotation

ACM auto-renews the client certificate before expiry. When it does:

1. EventBridge triggers the cert rotator Lambda, which re-exports the bundle to Secrets Manager automatically. Lambda cert pinning picks up the new cert on its next cold start.
2. Re-run `export_client_cert.py` to rebuild the truststore:

```bash
CLIENT_CERT_ARN=$(terraform -chdir=terraform output -raw client_cert_arn)
python scripts/export_client_cert.py "$CLIENT_CERT_ARN" --profile <aws-profile>
```

3. Update `truststore_version` in `terraform/terraform.tfvars` with the printed version ID and apply:

```bash
cd terraform && terraform apply -var-file=terraform.tfvars
```

4. Refresh local certs:

```bash
./scripts/setup-certs.sh <aws-profile> [aws-region]
```

The `age-identity.txt` file is never rotated. Only `client.crt` and `client.key.age` are overwritten.

---

## Security

| Layer | Control |
|-------|---------|
| Transport (layer 1) | mTLS via API Gateway. Client cert chain validated against truststore containing Amazon RSA 2048 M04 intermediate CA and self-signed Amazon Root CA 1 |
| Transport (layer 2) | Lambda cert pinning. Handler fetches exact leaf cert PEM from Secrets Manager and compares byte-for-byte against `requestContext.authentication.clientCert.clientCertPem` |
| Network | Lambda outside VPC. AWS service access via public endpoints. IAM least-privilege on all service calls |
| S3 access | Bucket policy denies requests from external AWS accounts. TLS enforced via `aws:SecureTransport` deny |
| Data at rest | SSE-KMS (aws/s3 managed key). Secrets Manager default encryption |
| Private key (server) | Held in Secrets Manager, fetched to MCP server process memory, written to a `0o600` temp file for the httpx connection lifetime only |
| Private key (hook) | age-encrypted on disk. Decrypted via process substitution; plaintext exists only in a kernel pipe buffer, never as a named file |
| IAM | Scoped to exact actions and resource ARNs. Explicit deny on Bedrock admin APIs |
| Blast radius | Lambda reserved concurrency = 10. API Gateway throttle = 100 burst / 50 steady |

---

## Known Operational Gotchas

### Removing Lambda from a VPC requires a two-step apply

If you re-add VPC config to Lambda and later want to remove it, Terraform will attempt to modify the Lambda and destroy the networking resources in parallel. Lambda hyperplane ENIs are held `in-use` by AWS for up to 45+ minutes after removal, which causes subnet and security group destroys to time out.

Prevent this by staging the apply:

```bash
# Step 1: detach Lambda from VPC first, wait for ENIs to release
terraform apply -target=module.compute

# Step 2: destroy networking resources once Lambda is fully detached
terraform apply
```

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
    main.tf           # Root module, wires all modules
  src/
    memory_handler/   # Lambda: store/recall/summarize via Bedrock + S3 Vectors
    cert_rotator/     # Lambda: ACM cert re-export to Secrets Manager on renewal
  mcp_server/         # Local MCP server (runs as Claude Code child process)
  hooks/
    session-start-engram.sh     # SessionStart hook: injects recall directive
    post-compact-memory.sh      # PostCompact hook: stores compaction summaries
    recall-confidence-check.sh  # PostToolUse hook: validates recall quality
  scripts/
    export_client_cert.py       # Export ACM client cert into Secrets Manager
    setup-certs.sh              # One-time local cert setup (age-encrypted key)
    smoke_test.py               # End-to-end mTLS verification
  Engram.md                     # Behavioral contract for Claude memory usage
```
