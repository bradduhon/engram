# engram

A personal memory layer for Agentic AI that persists context across many AI interfaces. Secured at the transport layer and living entirely in your own infrastructure.

## What It Does

Engram gives Claude persistent, semantically-searchable memory across all conversations. You store memories explicitly ("remember this") or automatically via the PostCompact hook when Claude's context window compresses. On any future conversation you can recall past decisions, preferences, and project context by semantic similarity, not keyword search.

## Architecture

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
    |-- Bedrock Titan Embed v2      (public endpoint)
    |-- S3 Vectors                  (public endpoint)
    +-- Secrets Manager             (public endpoint)
```

Lambda communicates with AWS services over their public endpoints. Access is controlled by IAM policies and resource policies.

> **VPC deployment reference:** If you prefer full network isolation (Lambda in a private VPC with Interface Endpoints for Bedrock, S3 Vectors, and Secrets Manager), the last commit with that configuration is [`5e2eaea`](https://github.com/bradduhon/engram/commit/5e2eaea). That architecture costs ~$58/month in VPC endpoint fees but keeps all compute traffic off the public internet.

**mTLS two-layer approach:**
1. **API Gateway truststore** - contains the Amazon RSA 2048 M04 intermediate CA and self-signed Amazon Root CA 1. API Gateway validates that the client cert was signed by a trusted CA before routing to Lambda.
2. **Lambda cert pinning** - after API Gateway validates the chain, the Lambda handler fetches the exact leaf cert PEM from Secrets Manager and compares it byte-for-byte against the cert presented by the client (available in `requestContext.authentication.clientCert.clientCertPem`). This ensures only the specific ACM cert exported for this deployment is accepted, even though the truststore would technically trust any cert signed by Amazon RSA 2048 M04.

## Prerequisites

### Tools

Install these before starting:

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

# jq and curl (used by the PostCompact hook)
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
5. Repeat for **Titan Embeddings v2** (`amazon.titan-embed-text-v2:0`) if not already enabled, Titan models are generally approved immediately without a use case form.

You can also navigate directly to the model pages:
- **Haiku 4.5:** `Amazon Bedrock > Model catalog > Claude Haiku 4.5 > Submit use case details`
- **Titan Embed v2:** `Amazon Bedrock > Model catalog > Titan Embeddings v2 > Request access`

### Python (local MCP server only)

The MCP server must be installed as a package so it is importable from any working directory. Claude Code spawns the server globally, and relying on `cwd` alone is not reliable across projects.

```bash
cd <path-to-engram-repo>
pip install -e ".[mcp-server]"
```

---

## Deployment

### Step 1: Bootstrap Terraform state backend

This creates the S3 bucket and DynamoDB table used as the remote state backend. Run once.

```bash
cd terraform/bootstrap

cat > terraform.tfvars <<EOF
aws_region  = "us-east-1"           # your target region
aws_profile = "default"             # your AWS CLI profile name
EOF

terraform init
terraform apply
```

Note the outputs, you need `state_bucket_name` and `lock_table_name`.

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
# Still in terraform/
cat > terraform.tfvars <<EOF
aws_region         = "us-east-1"
aws_profile        = "default"
server_domain_name = "memory.<your-domain>"       # e.g. memory.example.com
client_domain_name = "mcp-client.<your-domain>"   # e.g. mcp-client.example.com
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

Point `memory.<your-domain>` at that value. This is a one-time step regardless of DNS provider.

### Step 5: Export the client certificate and build the truststore

The mTLS client certificate is managed by ACM. This step:
- Exports the cert bundle (cert + chain + encrypted key) into Secrets Manager for use by the MCP server and Lambda cert pinning
- Builds the mTLS truststore (Amazon RSA 2048 M04 intermediate + self-signed Amazon Root CA 1) and uploads it to S3
- Outputs the S3 object version ID needed to tell API Gateway to reload the truststore

```bash
cd ..   # engram project root

# Get the client cert ARN from Terraform output
CLIENT_CERT_ARN=$(terraform -chdir=terraform output -raw client_cert_arn)

python scripts/export_client_cert.py "$CLIENT_CERT_ARN" \
  --profile <aws-profile> \
  [--region us-east-1]
```

The script will print output like:

```
Next steps:
  1. Set in terraform.tfvars:  truststore_version = "abc123..."
  2. Run:                       terraform apply -var-file=terraform.tfvars
  3. Run:                       ./hooks/setup-certs.sh <profile> [region]
```

Add the `truststore_version` value to `terraform/terraform.tfvars` and apply:

```bash
# Edit terraform/terraform.tfvars to add:
#   truststore_version = "<version-id-from-script-output>"

cd terraform
terraform apply -var-file=terraform.tfvars
```

This `truststore_version` tells API Gateway the exact S3 object version to read as the truststore. On cert renewal, repeat this step and update the version in `terraform.tfvars`.

> **Why this matters:** API Gateway caches the truststore from S3. Without updating `truststore_version`, a renewed cert may not take effect in the API Gateway mTLS layer.

Required AWS permissions:
- `acm:ExportCertificate` on the client cert ARN
- `secretsmanager:PutSecretValue` on `engram/mcp-client-cert*` secrets
- `s3:PutObject` on `engram-artifacts-<account-id>/mtls/truststore.pem`

### Step 6: Set up local certificate storage

Run once to create age-encrypted local certs used by the MCP server and PostCompact hook:

```bash
./hooks/setup-certs.sh <aws-profile> [aws-region]

# Example:
./hooks/setup-certs.sh my-aws-profile us-east-1
```

`aws-region` defaults to `us-east-1` if omitted. Requires `secretsmanager:GetSecretValue` on `engram/mcp-client-cert*` secrets.

This creates:

```
~/.claude/certs/
  age-identity.txt              # age decryption key (chmod 600, never rotated)
  client.crt                    # mTLS client certificate (chmod 600)
  client.key.age                # mTLS private key, age-encrypted (chmod 600)
  amazon-trust-services-ca.pem  # Amazon root CA bundle (chmod 600)
```

The plaintext private key is never written to disk. It is decrypted from Secrets Manager and piped directly into `age` for encryption.

### Step 7: Configure the MCP server

Add the `mcpServers` key to `~/.claude.json` (Claude Code's primary config file, in your home directory):

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

Use the full path to the Python interpreter from the virtualenv where you ran `pip install -e ".[mcp-server]"`. Do not use a bare `python` command -- Claude Code may resolve it against a different environment.

`~/.claude.json` likely already exists with other Claude Code settings. Add the `mcpServers` key without replacing the file contents.

> **Note:** The `cwd` field is not required when the package is installed via `pip install -e`. Omit it. If included and the working directory is wrong for any reason, it causes the server to fail silently in projects other than the engram repo.

Restart Claude Code. Verify the three tools appear:

```
store_memory
recall_memory
summarize_memories
```

You can check in Claude Code by asking: "What memory tools do you have?"

### Step 7b: Configure Claude to use memory automatically

Add the following to the top of your global `~/.claude/CLAUDE.md` (create it if it doesn't exist):

```markdown
# Memory

You have access to an Engram memory MCP server with three tools: `store_memory`, `recall_memory`, and `summarize_memories`. These tools persist context across all conversations, sessions, and projects. Behavior is defined in [Engram.md](<absolute-path-to-engram-repo>/Engram.md).
```

Replace `<absolute-path-to-engram-repo>` with the actual path where you cloned this repo (e.g. `/home/user/engram`).

`Engram.md` ships with this project and defines when Claude stores, recalls, and summarizes, without user prompting.

### Step 8: Configure the PostCompact hook

Add to `~/.claude/settings.json`:

```json
{
  "hooks": {
    "PostCompact": [
      {
        "matcher": "auto|manual",
        "hooks": [
          {
            "type": "command",
            "command": "<absolute-path-to-engram-repo>/hooks/post-compact-memory.sh",
            "timeout": 15,
            "env": {
              "MEMORY_API_URL": "https://memory.<your-domain>"
            }
          }
        ]
      }
    ]
  }
}
```

### Step 9: Confirm SNS alert subscription

Check the inbox for your `alert_email` and confirm the SNS subscription. This enables CloudWatch alarm notifications for Lambda errors, throttles, and high latency.

---

## Verification

```bash
# Confirm age decryption works
age -d -i ~/.claude/certs/age-identity.txt ~/.claude/certs/client.key.age | head -1
# Expected: -----BEGIN PRIVATE KEY-----

# Store a test memory via mTLS
curl --silent \
  --cert ~/.claude/certs/client.crt \
  --key <(age -d -i ~/.claude/certs/age-identity.txt ~/.claude/certs/client.key.age) \
  --cacert ~/.claude/certs/amazon-trust-services-ca.pem \
  -X POST "https://memory.<your-domain>/store" \
  -H "Content-Type: application/json" \
  -d '{"text":"engram setup verification","scope":"global","conversation_id":"setup-verify"}'
# Expected: {"stored": true, ...}

# Recall the memory
curl --silent \
  --cert ~/.claude/certs/client.crt \
  --key <(age -d -i ~/.claude/certs/age-identity.txt ~/.claude/certs/client.key.age) \
  --cacert ~/.claude/certs/amazon-trust-services-ca.pem \
  -X POST "https://memory.<your-domain>/recall" \
  -H "Content-Type: application/json" \
  -d '{"query":"setup verification"}' | jq '.memories[0].text'
# Expected: "engram setup verification"

# Confirm unauthenticated requests are rejected
curl -s -o /dev/null -w "%{http_code}" \
  -X POST "https://memory.<your-domain>/store" \
  -H "Content-Type: application/json" \
  -d '{"text":"should fail","scope":"global","conversation_id":"test"}'
# Expected: 000 (TLS handshake fails, server requires a client cert,
#           so no HTTP connection is established. This is stronger than 403.)
```

---

## Using the MCP Tools

Once the MCP server is running, Claude Code has three tools available.

### store_memory

Store something for later retrieval. Claude calls this automatically at session end or when you ask it to remember something.

**Ask Claude:**

```
Remember that we use us-east-1 for all new infrastructure.
```

```
Save that the database migration window is every Tuesday at 2 AM UTC.
```

**Direct tool call (if you want to be explicit):**

```
Use store_memory to save: "Project XYZ uses Postgres 15 with row-level security enabled on the users table"
with scope "project" and project_id "xyz-backend"
```

### recall_memory

Search memories by semantic similarity. Claude uses this at the start of sessions or when you reference past context.

**Ask Claude:**

```
What do you remember about our database setup?
```

```
Recall any memories about our deployment process.
```

```
What have we decided about authentication in this project?
```

**Direct tool call:**

```
Use recall_memory to search for "infrastructure decisions" with project_id "xyz-backend"
```

The tool searches both project-scoped and global memories when `project_id` is provided.

### summarize_memories

Compress many memories into a concise summary. The EventBridge scheduler runs this daily at 2:00 AM UTC automatically. You can also trigger it manually:

**Ask Claude:**

```
Summarize and compress all global memories.
```

```
Summarize project memories for project_id "xyz-backend" and delete the originals.
```

### Automatic Memory via PostCompact

The PostCompact hook fires whenever Claude Code compresses the conversation context (automatically or when you run `/compact`). It extracts the summary from the compaction event and stores it as a memory with `trigger: compact_auto` or `trigger: compact_manual`.

This means Claude builds memory passively over the lifetime of every conversation, without any explicit action from you.

---

## Scopes

Memories are stored in one of two scopes:

| Scope | When to use | Searchable across |
|-------|-------------|-------------------|
| `global` | Cross-project preferences, personal style, general decisions | All conversations |
| `project` | Project-specific context, decisions, architecture | Conversations in that project |

When recalling with a `project_id`, the service searches both the project scope and global scope and returns the combined top results.

---

## Cert Rotation

ACM auto-renews the client certificate before expiry. When it does:

1. EventBridge triggers the cert rotator Lambda, which re-exports the bundle to Secrets Manager automatically. The Lambda cert pinning in the memory handler picks up the new cert on its next cold start.
2. Re-run `export_client_cert.py` to rebuild the truststore with the renewed cert's chain and get the new S3 version ID:

```bash
CLIENT_CERT_ARN=$(terraform -chdir=terraform output -raw client_cert_arn)
python scripts/export_client_cert.py "$CLIENT_CERT_ARN" --profile <aws-profile>
```

3. Update `truststore_version` in `terraform/terraform.tfvars` with the printed version ID and apply:

```bash
# Edit terraform/terraform.tfvars: truststore_version = "<new-version-id>"
cd terraform && terraform apply -var-file=terraform.tfvars
```

4. Refresh local certs:

```bash
./hooks/setup-certs.sh <aws-profile> [aws-region]
```

The `age-identity.txt` file is never rotated. Only `client.crt` and `client.key.age` are overwritten.

---

## Security

| Layer | Control |
|-------|---------|
| Transport (layer 1) | mTLS, API Gateway validates client cert chain against a truststore containing the Amazon RSA 2048 M04 intermediate CA and self-signed Amazon Root CA 1 |
| Transport (layer 2) | Lambda cert pinning, handler fetches the exact leaf cert PEM from Secrets Manager and compares it byte-for-byte against `requestContext.authentication.clientCert.clientCertPem`. Only the specific ACM cert exported for this deployment is accepted |
| Network | Lambda outside VPC; AWS service access via public endpoints. IAM least-privilege enforced on all service calls |
| S3 access | Bucket policy denies requests from external AWS accounts. TLS enforced via `aws:SecureTransport` deny |
| Data at rest | SSE-KMS (aws/s3 managed key). Secrets Manager default encryption |
| Private key (server) | Held in Secrets Manager, fetched to MCP server process memory, written to a `0o600` temp file for the httpx connection lifetime only |
| Private key (hook) | age-encrypted on disk. Decrypted via process substitution, plaintext exists only in a kernel pipe buffer, never as a named file |
| IAM | Scoped to exact actions and resource ARNs. Explicit deny on Bedrock admin APIs |
| Blast radius | Lambda reserved concurrency = 10. API Gateway throttle = 100 burst / 50 steady |

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
    setup-certs.sh          # One-time local cert setup (age-encrypted key)
    post-compact-memory.sh  # PostCompact hook
  scripts/
    export_client_cert.py   # Export ACM client cert into Secrets Manager
```
