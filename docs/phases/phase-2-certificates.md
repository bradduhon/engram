# Phase 2: Certificate Infrastructure

## Overview

Creates the ACM certificates for mTLS (server and client), DNS validation records in Route53, and Secrets Manager secret shells for the exported client cert bundle and passphrase. The client cert is an ACM exportable public certificate -- its private key can be retrieved via the `ExportCertificate` API for use by the MCP server and PostCompact hook.

## Prerequisites

- Phase 1 complete: S3 bucket exists, VPC and networking deployed
- Route53 hosted zone for `<your-domain>` exists and is authoritative
- Route53 hosted zone ID known

## Resources Created

### Terraform -- `modules/certificates`

File: `terraform/modules/certificates/main.tf`

| Resource | Type | Key Config |
|----------|------|------------|
| `aws_acm_certificate.server` | ACM cert | Domain: `memory.<your-domain>`, validation: DNS |
| `aws_acm_certificate.client` | ACM cert | Domain: `mcp-client.<your-domain>`, validation: DNS, `key_algorithm = "RSA_2048"` |
| `aws_route53_record.server_validation` | Route53 | CNAME for server cert DNS validation |
| `aws_route53_record.client_validation` | Route53 | CNAME for client cert DNS validation |
| `aws_acm_certificate_validation.server` | Validation | Waits for server cert to be ISSUED |
| `aws_acm_certificate_validation.client` | Validation | Waits for client cert to be ISSUED |
| `aws_secretsmanager_secret.client_cert` | Secret shell | Name: `engram/mcp-client-cert` |
| `aws_secretsmanager_secret.client_cert_passphrase` | Secret shell | Name: `engram/mcp-client-cert-passphrase` |

**ACM exportable cert note:** As of 2026, Terraform's `aws_acm_certificate` may not expose an `exportable` option. If not supported:

1. Create the client cert via AWS CLI instead:
   ```bash
   aws acm request-certificate \
     --domain-name mcp-client.<your-domain> \
     --validation-method DNS \
     --key-algorithm RSA_2048 \
     --options CertificateTransparencyLoggingPreference=ENABLED
   ```
   The exportable flag may be set via a separate API option or console setting.

2. Import the resulting cert ARN into Terraform as a data source:
   ```hcl
   data "aws_acm_certificate" "client" {
     domain   = "mcp-client.<your-domain>"
     statuses = ["ISSUED"]
   }
   ```

3. Reference `data.aws_acm_certificate.client.arn` wherever the client cert ARN is needed.

The server cert (`memory.<your-domain>`) is a standard non-exportable ACM cert and is fully supported by Terraform.

### Shell Scripts

**`scripts/export-client-cert.sh`**

Run after certs are ISSUED and Secrets Manager shells exist. Exports the client cert private key and stores in Secrets Manager.

```bash
#!/bin/bash
set -euo pipefail

CLIENT_CERT_ARN="$1"  # Pass as argument or set from terraform output

# Generate a strong random passphrase
PASSPHRASE=$(openssl rand -base64 32)

# Store passphrase in Secrets Manager first
aws secretsmanager put-secret-value \
  --secret-id engram/mcp-client-cert-passphrase \
  --secret-string "$PASSPHRASE"

# Export the certificate bundle (cert + chain + encrypted private key)
BUNDLE=$(aws acm export-certificate \
  --certificate-arn "$CLIENT_CERT_ARN" \
  --passphrase "$(echo -n "$PASSPHRASE" | base64)" \
  | jq -r '"\(.Certificate)\(.CertificateChain)\(.PrivateKey)"')

# Store the bundle in Secrets Manager
aws secretsmanager put-secret-value \
  --secret-id engram/mcp-client-cert \
  --secret-string "$BUNDLE"

# Clean up
unset PASSPHRASE BUNDLE

echo "Client cert exported and stored in Secrets Manager"
echo "  Secret: engram/mcp-client-cert"
echo "  Passphrase: engram/mcp-client-cert-passphrase"
```

## Terraform Variables

### `modules/certificates`

| Variable | Type | Description |
|----------|------|-------------|
| `domain_name` | `string` | Base domain (default: `"<your-domain>"`) |
| `server_subdomain` | `string` | API subdomain (default: `"memory"`) |
| `client_subdomain` | `string` | Client cert subdomain (default: `"mcp-client"`) |
| `route53_zone_id` | `string` | Route53 hosted zone ID for DNS validation |

## Terraform Outputs

### `modules/certificates`

| Output | Description | Used By |
|--------|-------------|---------|
| `server_cert_arn` | ARN of the server ACM cert | Phase 4 (API Gateway custom domain) |
| `client_cert_arn` | ARN of the client ACM cert | Phase 3 (cert rotator IAM policy), Phase 7 (hook setup) |
| `client_cert_secret_arn` | ARN of the cert bundle secret | Phase 3 (Lambda IAM), Phase 5 (MCP server config) |
| `client_cert_passphrase_secret_arn` | ARN of the passphrase secret | Phase 3 (Lambda IAM), Phase 5 (MCP server config) |

## Security Controls

- **DNS validation:** No manual approval needed. Route53 records prove domain ownership.
- **Exportable cert cost:** $15 one-time per FQDN. Renews automatically by ACM. Re-export needed after renewal (handled by cert rotator Lambda in Phase 3/6).
- **Passphrase generation:** 32 bytes from `openssl rand`, base64 encoded. Stored in Secrets Manager, never in code or TF state.
- **Secret shells:** Terraform creates empty `aws_secretsmanager_secret` resources. Values are populated out-of-band by `scripts/export-client-cert.sh`. This keeps the private key material out of Terraform state entirely.
- **Secret recovery:** `recovery_window_in_days = 7` (default). Prevents accidental permanent deletion.
- **No wildcard certs:** Each cert is for a specific FQDN. No `*.<your-domain>`.

## Implementation Steps

1. Determine your Route53 hosted zone ID:
   ```bash
   aws route53 list-hosted-zones-by-name --dns-name <your-domain> \
     --query 'HostedZones[0].Id' --output text
   ```

2. Create `terraform/modules/certificates/variables.tf` with the variables listed above.

3. Create `terraform/modules/certificates/main.tf`:
   - Server cert: `aws_acm_certificate` with `domain_name = "memory.<your-domain>"`, `validation_method = "DNS"`
   - Client cert: either `aws_acm_certificate` (if exportable supported) or note to create via CLI
   - DNS validation records using `for_each` on `domain_validation_options`
   - Validation resources to wait for ISSUED status
   - Secrets Manager secrets (shells only, no `secret_string`)

4. Create `terraform/modules/certificates/outputs.tf` with all outputs listed above.

5. Wire in `terraform/main.tf`:
   ```hcl
   module "certificates" {
     source           = "./modules/certificates"
     route53_zone_id  = var.route53_zone_id
   }
   ```

6. Add `route53_zone_id` to `terraform/variables.tf`.

7. Run `terraform apply -target=module.certificates`.

8. If the client cert was created via CLI (not Terraform), add the `data.aws_acm_certificate.client` data source.

9. Wait for both certs to reach ISSUED status (DNS validation propagation may take a few minutes).

10. Run `scripts/export-client-cert.sh <client-cert-arn>` to export the private key and populate Secrets Manager.

11. Verify secrets are populated:
    ```bash
    aws secretsmanager get-secret-value --secret-id engram/mcp-client-cert \
      --query 'SecretString' --output text | head -1
    # Expected: -----BEGIN CERTIFICATE-----
    ```

## Acceptance Criteria

```bash
# Verify server cert is ISSUED
aws acm describe-certificate \
  --certificate-arn $(terraform -chdir=terraform output -raw server_cert_arn) \
  --query 'Certificate.Status' --output text
# Expected: ISSUED

# Verify client cert is ISSUED
aws acm describe-certificate \
  --certificate-arn $(terraform -chdir=terraform output -raw client_cert_arn) \
  --query 'Certificate.Status' --output text
# Expected: ISSUED

# Verify Secrets Manager secrets exist and are populated
aws secretsmanager describe-secret --secret-id engram/mcp-client-cert \
  --query 'Name' --output text
# Expected: engram/mcp-client-cert

aws secretsmanager get-secret-value --secret-id engram/mcp-client-cert-passphrase \
  --query 'SecretString' --output text | wc -c
# Expected: > 0 (passphrase is populated)

# Terraform validation
cd terraform && terraform validate
```

## Notes

- ACM certs in `us-east-1` are required for API Gateway custom domains. If using a different region, the server cert must still be in `us-east-1`.
- The exportable client cert costs $15. This is a one-time charge per FQDN. ACM handles renewal automatically, but the renewed cert must be re-exported (Phase 6 automates this with EventBridge + cert rotator Lambda).
- DNS validation records are CNAMEs that ACM uses to prove domain ownership. They must remain in Route53 for automatic renewal to work.
- The client cert's key algorithm is RSA 2048 (ACM default for exportable certs). ECDSA is not supported for exportable ACM certs as of this writing.
