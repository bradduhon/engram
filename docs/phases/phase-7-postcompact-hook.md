# Phase 7: PostCompact Hook

## Overview

Creates the Claude Code PostCompact hook that captures compaction summaries and pushes them to the memory service via mTLS curl. The private key is protected at rest with age encryption -- decrypted inline via process substitution so plaintext never exists as a named file on disk. No Terraform resources in this phase.

## Prerequisites

- Phase 4 complete: API Gateway reachable at `https://memory.<your-domain>` with mTLS
- Phase 2 complete: Secrets Manager populated with cert bundle and passphrase
- `age` CLI installed (`apt install age` or from https://github.com/FiloSottile/age, BSD-3 license)
- `jq` and `curl` installed
- `openssl` installed (for key decryption during setup)

## Resources Created

### Shell Scripts

#### `hooks/setup-certs.sh`

One-time setup script. Fetches the client cert from Secrets Manager, extracts the certificate (public), decrypts the private key and pipes it directly into age encryption. The plaintext private key never touches disk.

```bash
#!/bin/bash
set -euo pipefail

CERT_DIR="$HOME/.claude/certs"
mkdir -p "$CERT_DIR"
chmod 700 "$CERT_DIR"

# Step 1: Generate age identity if not exists
if [ ! -f "$CERT_DIR/age-identity.txt" ]; then
  age-keygen -o "$CERT_DIR/age-identity.txt" 2>/dev/null
  chmod 600 "$CERT_DIR/age-identity.txt"
  echo "Generated new age identity at $CERT_DIR/age-identity.txt"
fi

# Extract the age public key (recipient) from the identity file
AGE_RECIPIENT=$(grep -o 'age1[a-z0-9]*' "$CERT_DIR/age-identity.txt")

# Step 2: Fetch cert bundle from Secrets Manager
BUNDLE=$(aws secretsmanager get-secret-value \
  --secret-id engram/mcp-client-cert \
  --query SecretString --output text)

PASSPHRASE=$(aws secretsmanager get-secret-value \
  --secret-id engram/mcp-client-cert-passphrase \
  --query SecretString --output text)

# Step 3: Extract cert (public, not encrypted)
echo "$BUNDLE" | openssl x509 -out "$CERT_DIR/client.crt"
chmod 600 "$CERT_DIR/client.crt"

# Step 4: Decrypt private key from PEM bundle, pipe directly into age
# The plaintext key never touches disk -- it flows through a pipe
echo "$BUNDLE" | openssl pkey -passin "pass:$PASSPHRASE" \
  | age -r "$AGE_RECIPIENT" -o "$CERT_DIR/client.key.age"
chmod 600 "$CERT_DIR/client.key.age"

# Step 5: Download Amazon Trust Services CA bundle
curl -s https://www.amazontrust.com/repository/AmazonRootCA1.pem \
  > "$CERT_DIR/amazon-trust-services-ca.pem"
chmod 600 "$CERT_DIR/amazon-trust-services-ca.pem"

# Clean up shell variables
unset BUNDLE PASSPHRASE AGE_RECIPIENT

echo ""
echo "Cert setup complete:"
echo "  $CERT_DIR/client.crt            -- mTLS client certificate (public)"
echo "  $CERT_DIR/client.key.age        -- mTLS private key (age-encrypted)"
echo "  $CERT_DIR/age-identity.txt      -- age decryption identity"
echo "  $CERT_DIR/amazon-trust-services-ca.pem -- CA bundle for server verification"
echo ""
echo "No plaintext private key exists on disk."
```

**File layout after setup:**

```
~/.claude/certs/
  age-identity.txt              # age private key (chmod 600)
  client.crt                    # mTLS client certificate (chmod 600)
  client.key.age                # mTLS private key, age-encrypted (chmod 600)
  amazon-trust-services-ca.pem  # Amazon root CA bundle (chmod 600)
```

Note: `client.key` (plaintext) does **not** exist. Only `client.key.age`.

#### `hooks/post-compact-memory.sh`

The PostCompact hook script. Reads compaction JSON from stdin, builds a store_memory payload, and posts to the API via mTLS. The private key is decrypted via process substitution -- the plaintext exists only in a pipe file descriptor.

```bash
#!/bin/bash
set -euo pipefail

# Read PostCompact JSON from stdin
INPUT=$(cat)

# Extract compacted summary and session metadata
SUMMARY=$(echo "$INPUT"    | jq -r '.summary // empty')
SESSION_ID=$(echo "$INPUT" | jq -r '.session_id // "unknown"')
PROJECT_ID=$(echo "$INPUT" | jq -r '.project_id // empty')
TRIGGER=$(echo "$INPUT"    | jq -r '.trigger // "auto"')

# Nothing to store if summary is empty
if [ -z "$SUMMARY" ]; then
  exit 0
fi

# Determine scope
if [ -n "$PROJECT_ID" ] && [ "$PROJECT_ID" != "null" ]; then
  SCOPE="project"
else
  SCOPE="global"
  PROJECT_ID="null"
fi

# Build the store_memory payload
PAYLOAD=$(jq -n \
  --arg text            "$SUMMARY" \
  --arg scope           "$SCOPE" \
  --arg project_id      "$PROJECT_ID" \
  --arg conversation_id "$SESSION_ID" \
  --arg trigger         "compact_$TRIGGER" \
  '{
    text:            $text,
    scope:           $scope,
    project_id:      (if $project_id == "null" then null else $project_id end),
    conversation_id: $conversation_id,
    trigger:         $trigger
  }')

# POST to memory service via mTLS
# Key decryption via process substitution: plaintext exists only in /dev/fd/N
RESPONSE=$(curl --silent --show-error \
  --cert    "$HOME/.claude/certs/client.crt" \
  --key     <(age -d -i "$HOME/.claude/certs/age-identity.txt" "$HOME/.claude/certs/client.key.age") \
  --cacert  "$HOME/.claude/certs/amazon-trust-services-ca.pem" \
  --max-time 10 \
  -H "Content-Type: application/json" \
  -d "$PAYLOAD" \
  "https://memory.<your-domain>/store")

# Log result to stderr (appears in Claude Code verbose log, not Claude's context)
STATUS=$(echo "$RESPONSE" | jq -r '.stored // false')
if [ "$STATUS" = "true" ]; then
  echo "PostCompact memory stored (trigger: compact_$TRIGGER, scope: $SCOPE)" >&2
else
  echo "Warning: PostCompact memory store returned unexpected response: $RESPONSE" >&2
fi

# Always exit 0 -- never block compaction on a memory write failure
exit 0
```

### Claude Code Settings

File: `~/.claude/settings.json`

Add the PostCompact hook configuration:

```json
{
  "hooks": {
    "PostCompact": [
      {
        "matcher": "auto|manual",
        "hooks": [
          {
            "type": "command",
            "command": "~/.claude/hooks/post-compact-memory.sh",
            "timeout": 15
          }
        ]
      }
    ]
  }
}
```

**Matcher values:**
- `auto` -- fires on automatic compaction (context limit approached)
- `manual` -- fires on `/compact` command
- `auto|manual` -- fires on both (recommended)

## Security Controls

- **age encryption at rest:** The private key is stored as `client.key.age`, encrypted with the age identity's public key. Without `age-identity.txt`, the file is opaque binary.
- **Process substitution decryption:** `<(age -d ...)` creates a file descriptor (e.g., `/dev/fd/63`) that curl reads from. The plaintext key exists only in kernel pipe buffers, never as a named file on the filesystem. When curl closes the fd, the plaintext is gone.
- **Defense-in-depth over chmod 600 alone:** age encryption protects against:
  - Backup systems that capture `~/.claude/certs/` contents
  - Other processes on the same machine (root can read chmod 600 files; age-encrypted content requires the identity)
  - Accidental inclusion in dotfile syncing tools (Dropbox, rsync, etc.)
- **age identity is not the mTLS key:** If `age-identity.txt` is compromised, the attacker still needs `client.key.age` from the same filesystem. If both are compromised, the machine is compromised to a degree where chmod 600 on a plaintext key would also fail.
- **age identity does not rotate:** It is a local encryption wrapper, independent of the mTLS cert lifecycle. Re-running `setup-certs.sh` re-encrypts the new cert's key with the same identity.
- **Hook always exits 0:** Memory write failures never block compaction. Errors are logged to stderr.
- **Timeout:** 15 seconds in settings.json, 10 seconds on the curl call. Tight bounds prevent hanging.
- **No AWS SDK dependency:** The hook uses curl directly. No boto3, no AWS CLI at runtime.

## Implementation Steps

1. Install age:
   ```bash
   sudo apt install age
   # Or: download from https://github.com/FiloSottile/age/releases
   age --version
   ```

2. Create the source-controlled hook scripts:
   - Create `hooks/setup-certs.sh` with the content above
   - Create `hooks/post-compact-memory.sh` with the content above
   - `chmod +x hooks/setup-certs.sh hooks/post-compact-memory.sh`

3. Run the one-time cert setup:
   ```bash
   ./hooks/setup-certs.sh
   ```
   Verify the output shows all four files created with no errors.

4. Verify age round-trip:
   ```bash
   age -d -i ~/.claude/certs/age-identity.txt ~/.claude/certs/client.key.age | head -1
   # Expected: -----BEGIN PRIVATE KEY-----
   ```

5. Install the hook script to `~/.claude/hooks/`:
   ```bash
   mkdir -p ~/.claude/hooks
   cp hooks/post-compact-memory.sh ~/.claude/hooks/
   chmod +x ~/.claude/hooks/post-compact-memory.sh
   ```

6. Smoke test the hook manually:
   ```bash
   echo '{"summary":"test compact memory from phase 7","session_id":"test-phase7","project_id":null,"trigger":"manual"}' \
     | ~/.claude/hooks/post-compact-memory.sh
   ```
   Check stderr output for success message. Verify the memory appears in S3.

7. Add PostCompact hook to `~/.claude/settings.json`. If the file already exists, merge the `hooks` key. If not, create it with the content above.

8. Verify in Claude Code:
   - Open a conversation with enough context to trigger compaction, or run `/compact`
   - Check stderr logs for the "PostCompact memory stored" message
   - Verify the memory appears in S3 with `trigger: compact_manual` or `trigger: compact_auto`

## Acceptance Criteria

```bash
# Verify age is installed
age --version
# Expected: version string

# Verify cert files exist with correct permissions
ls -la ~/.claude/certs/
# Expected:
#   drwx------ (700) .
#   -rw------- (600) age-identity.txt
#   -rw------- (600) client.crt
#   -rw------- (600) client.key.age
#   -rw------- (600) amazon-trust-services-ca.pem

# Verify NO plaintext key exists
test ! -f ~/.claude/certs/client.key && echo "PASS: no plaintext key on disk"
# Expected: PASS

# Verify age decryption works
age -d -i ~/.claude/certs/age-identity.txt ~/.claude/certs/client.key.age | head -1
# Expected: -----BEGIN PRIVATE KEY-----

# Verify hook script is executable
test -x ~/.claude/hooks/post-compact-memory.sh && echo "PASS: hook is executable"
# Expected: PASS

# Smoke test: store a memory via the hook
echo '{"summary":"acceptance test - phase 7 postcompact hook","session_id":"acceptance-7","project_id":null,"trigger":"manual"}' \
  | ~/.claude/hooks/post-compact-memory.sh 2>&1
# Expected stderr: PostCompact memory stored (trigger: compact_manual, scope: global)

# Verify the stored memory is recallable
curl --silent \
  --cert ~/.claude/certs/client.crt \
  --key <(age -d -i ~/.claude/certs/age-identity.txt ~/.claude/certs/client.key.age) \
  --cacert ~/.claude/certs/amazon-trust-services-ca.pem \
  -X POST https://memory.<your-domain>/recall \
  -H "Content-Type: application/json" \
  -d '{"query":"phase 7 postcompact hook test"}' \
  | jq '.memories[0].text'
# Expected: contains "acceptance test - phase 7 postcompact hook"

# Verify settings.json has the hook configured
jq '.hooks.PostCompact' ~/.claude/settings.json
# Expected: non-null array with the post-compact-memory.sh command
```

## Key Rotation Procedure

When ACM renews the client cert (annually), the EventBridge cert rotator Lambda updates Secrets Manager automatically. To update the local age-encrypted key:

1. Re-run the setup script:
   ```bash
   ./hooks/setup-certs.sh
   ```
2. The script fetches the new bundle from Secrets Manager, re-encrypts with the same age identity.
3. `client.crt` and `client.key.age` are overwritten. `age-identity.txt` is unchanged.
4. No changes needed to the hook script or settings.json.

If `age-identity.txt` is lost:
1. Re-run `setup-certs.sh` -- it generates a new age identity automatically.
2. The old `client.key.age` becomes unrecoverable, but the private key can always be re-exported from Secrets Manager.

## Notes

- Process substitution `<(...)` requires bash (not sh/dash). The shebang line uses `#!/bin/bash`. Verify that `~/.claude/hooks/` scripts run under bash in Claude Code's hook executor.
- On systems where `/dev/fd/` is not available (some restricted containers), process substitution may fail. In that case, fall back to a named pipe or a temp file with immediate cleanup. This is unlikely on WSL/Linux.
- The hook script does not use `tool_name` in the payload because it posts directly to `/store` (path-based routing). The Lambda routes by path, not by body field.
- The age identity file (`age-identity.txt`) contains a single line like `AGE-SECRET-KEY-1...`. Back it up if convenient, but losing it is a minor inconvenience (re-run setup), not a security incident.
- If you want to test the hook without triggering compaction, pipe test JSON directly as shown in the smoke test step.
