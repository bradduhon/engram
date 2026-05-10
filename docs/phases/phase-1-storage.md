# Phase 1: Storage Foundation

## Overview

Creates the S3 memory bucket with SSE-KMS encryption and vector table index, the VPC with private subnets, the S3 Gateway Endpoint, and security groups. This phase establishes the data layer and network foundation that all compute and API resources depend on.

## Prerequisites

- Phase 0 complete: `terraform init` succeeds with remote S3 backend
- Amazon Trust Services root CA PEM file downloaded (public, from https://www.amazontrust.com/repository/)

## Resources Created

### Terraform -- `modules/storage`

File: `terraform/modules/storage/main.tf`

| Resource | Type | Key Config |
|----------|------|------------|
| `aws_s3_bucket.memory` | S3 bucket | Name: `engram-memory-{account_id}` |
| `aws_s3_bucket_versioning.memory` | Versioning | `status = "Enabled"` |
| `aws_s3_bucket_server_side_encryption_configuration.memory` | Encryption | SSE-KMS, `aws/s3` managed key |
| `aws_s3_bucket_public_access_block.memory` | Public access | All four settings `true` |
| `aws_s3_bucket_policy.memory` | Bucket policy | Deny non-VPC-endpoint access |
| `aws_s3_object.truststore` | Object | Upload `mtls/truststore.pem` |

**Bucket policy pattern:**

```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Sid": "DenyNonVPCEndpoint",
      "Effect": "Deny",
      "Principal": "*",
      "Action": "s3:*",
      "Resource": [
        "arn:aws:s3:::engram-memory-{account_id}",
        "arn:aws:s3:::engram-memory-{account_id}/*"
      ],
      "Condition": {
        "StringNotEquals": {
          "aws:SourceVpce": "{s3_gateway_endpoint_id}"
        }
      }
    }
  ]
}
```

**Important:** This policy blocks all non-VPC access, including from the AWS console and CLI outside the VPC. The Terraform apply itself uses the S3 Gateway Endpoint (Lambda in VPC). For initial truststore upload and manual operations, either:
- Temporarily omit the bucket policy during first apply, upload truststore, then add the policy
- Or add a condition exempting the deploying IAM role: `"StringNotEquals": {"aws:PrincipalArn": "{deployer_role_arn}"}`

The phase doc recommends the second approach (exempting the deployer role) for operational convenience.

### Terraform -- `modules/networking`

File: `terraform/modules/networking/main.tf`

| Resource | Type | Key Config |
|----------|------|------------|
| `aws_vpc.main` | VPC | CIDR: `10.0.0.0/16`, name: `engram-vpc`, `enable_dns_support = true`, `enable_dns_hostnames = true` |
| `aws_subnet.private` | Subnets (x2) | Two AZs (e.g., `us-east-1a`, `us-east-1b`), CIDRs: `10.0.1.0/24`, `10.0.2.0/24` |
| `aws_route_table.private` | Route table | Associated with VPC |
| `aws_route_table_association.private` | Associations (x2) | One per subnet |
| `aws_vpc_endpoint.s3_gateway` | S3 Gateway Endpoint | Service: `com.amazonaws.{region}.s3`, route table association |
| `aws_security_group.lambda` | SG | Name: `engram-lambda-sg`. Egress: allow all (restricted further in Phase 3). No ingress. |
| `aws_security_group.bedrock_endpoint` | SG | Name: `engram-bedrock-endpoint-sg`. Inbound: 443 from `engram-lambda-sg`. No other ingress. |

**Why two subnets:** Lambda VPC configuration requires at least two subnets in different AZs for availability, even though this is a single-user service.

**DNS settings:** `enable_dns_support` and `enable_dns_hostnames` must be `true` for VPC Interface Endpoints (Bedrock, added in Phase 3) to resolve correctly.

### Shell Scripts

**`scripts/create-vector-index.sh`**

S3 Vector Tables do not have a Terraform resource yet. This script creates the vector index via the AWS CLI.

```bash
#!/bin/bash
set -euo pipefail

ACCOUNT_ID=$(aws sts get-caller-identity --query Account --output text)
BUCKET="engram-memory-${ACCOUNT_ID}"

aws s3vectors create-index \
  --bucket "$BUCKET" \
  --index-name memories \
  --dimension 1024 \
  --distance-metric COSINE

echo "Vector index 'memories' created on bucket $BUCKET"
```

**`scripts/upload-truststore.sh`**

```bash
#!/bin/bash
set -euo pipefail

ACCOUNT_ID=$(aws sts get-caller-identity --query Account --output text)
BUCKET="engram-memory-${ACCOUNT_ID}"

# Download Amazon Trust Services root CAs
curl -s https://www.amazontrust.com/repository/AmazonRootCA1.pem > /tmp/truststore.pem
curl -s https://www.amazontrust.com/repository/AmazonRootCA2.pem >> /tmp/truststore.pem
curl -s https://www.amazontrust.com/repository/AmazonRootCA3.pem >> /tmp/truststore.pem
curl -s https://www.amazontrust.com/repository/AmazonRootCA4.pem >> /tmp/truststore.pem

aws s3 cp /tmp/truststore.pem "s3://${BUCKET}/mtls/truststore.pem"
rm /tmp/truststore.pem

echo "Truststore uploaded to s3://${BUCKET}/mtls/truststore.pem"
```

Note: The truststore can also be uploaded via the `aws_s3_object` Terraform resource if the PEM file is checked into the repo (it is public CA material, not sensitive). The script approach is provided as an alternative.

## Terraform Variables

### `modules/storage`

| Variable | Type | Description |
|----------|------|-------------|
| `account_id` | `string` | AWS account ID for bucket naming |
| `vpc_endpoint_id` | `string` | S3 Gateway Endpoint ID for bucket policy |
| `deployer_role_arn` | `string` | IAM ARN exempted from VPC-endpoint-only bucket policy |
| `truststore_source` | `string` | Local path to truststore PEM file (if using `aws_s3_object`) |

### `modules/networking`

| Variable | Type | Description |
|----------|------|-------------|
| `aws_region` | `string` | AWS region |
| `vpc_cidr` | `string` | VPC CIDR block (default: `"10.0.0.0/16"`) |
| `private_subnet_cidrs` | `list(string)` | Subnet CIDRs (default: `["10.0.1.0/24", "10.0.2.0/24"]`) |
| `availability_zones` | `list(string)` | AZs for subnets (default: `["us-east-1a", "us-east-1b"]`) |

## Terraform Outputs

### `modules/storage`

| Output | Description | Used By |
|--------|-------------|---------|
| `bucket_id` | S3 bucket ID | Phase 2 (certificates), Phase 3 (Lambda env var) |
| `bucket_arn` | S3 bucket ARN | Phase 3 (IAM policy) |
| `bucket_name` | S3 bucket name | Phase 3 (Lambda env var) |
| `truststore_s3_uri` | Full S3 URI of truststore PEM | Phase 4 (API Gateway mTLS config) |

### `modules/networking`

| Output | Description | Used By |
|--------|-------------|---------|
| `vpc_id` | VPC ID | Phase 3 (Lambda VPC config, Bedrock endpoint) |
| `private_subnet_ids` | List of private subnet IDs | Phase 3 (Lambda VPC config) |
| `s3_gateway_endpoint_id` | S3 Gateway Endpoint ID | `modules/storage` bucket policy |
| `lambda_security_group_id` | Lambda SG ID | Phase 3 (Lambda VPC config) |
| `bedrock_endpoint_security_group_id` | Bedrock endpoint SG ID | Phase 3 (Bedrock VPC endpoint) |
| `private_route_table_id` | Route table ID | Reference |

## Security Controls

- **S3 bucket:** All public access blocked. Versioning prevents accidental data loss. SSE-KMS encryption at rest.
- **Bucket policy:** Denies all S3 operations not sourced from the VPC Gateway Endpoint (with deployer role exemption for initial setup and operational access).
- **VPC:** No internet gateway, no NAT gateway. Private subnets only. Lambda has no path to the public internet.
- **Security groups:** Lambda SG has no ingress rules. Bedrock endpoint SG allows inbound 443 only from the Lambda SG.
- **Truststore:** Contains only public Amazon Trust Services CA certificates. Not sensitive material.

## Implementation Steps

1. Create `terraform/modules/networking/variables.tf` with the variables listed above.
2. Create `terraform/modules/networking/main.tf` with VPC, subnets, route table, associations, S3 Gateway Endpoint, and both security groups.
3. Create `terraform/modules/networking/outputs.tf` with all outputs listed above.
4. Create `terraform/modules/storage/variables.tf` with the variables listed above.
5. Create `terraform/modules/storage/main.tf` with S3 bucket, versioning, encryption, public access block, bucket policy, and truststore object upload.
6. Create `terraform/modules/storage/outputs.tf` with all outputs listed above.
7. Wire both modules in `terraform/main.tf`:
   ```hcl
   module "networking" {
     source = "./modules/networking"
     aws_region = var.aws_region
   }

   module "storage" {
     source           = "./modules/storage"
     account_id       = data.aws_caller_identity.current.account_id
     vpc_endpoint_id  = module.networking.s3_gateway_endpoint_id
     deployer_role_arn = data.aws_caller_identity.current.arn
   }
   ```
8. Add `data.aws_caller_identity.current` and `data.aws_region.current` to `terraform/data.tf`.
9. Run `terraform apply -target=module.networking -target=module.storage`.
10. Run `scripts/create-vector-index.sh` to create the S3 Vector Table index.
11. Run `scripts/upload-truststore.sh` if not using the `aws_s3_object` approach.

## Acceptance Criteria

```bash
# Verify bucket exists and has correct encryption
ACCOUNT_ID=$(aws sts get-caller-identity --query Account --output text)
aws s3api get-bucket-encryption --bucket engram-memory-${ACCOUNT_ID}
# Expected: SSE-KMS with aws/s3 key

# Verify versioning
aws s3api get-bucket-versioning --bucket engram-memory-${ACCOUNT_ID}
# Expected: {"Status": "Enabled"}

# Verify public access is blocked
aws s3api get-public-access-block --bucket engram-memory-${ACCOUNT_ID}
# Expected: all four settings true

# Verify truststore uploaded
aws s3 ls s3://engram-memory-${ACCOUNT_ID}/mtls/truststore.pem
# Expected: file listed

# Verify VPC and endpoints
VPC_ID=$(aws ec2 describe-vpcs --filters Name=tag:Name,Values=engram-vpc --query 'Vpcs[0].VpcId' --output text)
aws ec2 describe-vpc-endpoints --filters Name=vpc-id,Values=${VPC_ID} Name=service-name,Values=com.amazonaws.us-east-1.s3
# Expected: one Gateway endpoint

# Verify vector index
aws s3vectors describe-index --bucket engram-memory-${ACCOUNT_ID} --index-name memories
# Expected: index with dimension 1024, COSINE metric

# Terraform validation
cd terraform && terraform validate
# Expected: "Success! The configuration is valid."
```

## Notes

- The `aws s3vectors` CLI commands may require a recent AWS CLI version. Verify with `aws s3vectors help`.
- The S3 Gateway Endpoint is free. No hourly or data transfer charges.
- The bucket policy's VPC endpoint restriction means `aws s3` CLI commands from outside the VPC will be denied unless the deployer role exemption is in place. This is intentional for production but may be inconvenient during development.
- If you need to access the bucket from outside the VPC during development, keep the deployer role exemption. Remove it once the system is stable if you want maximum lockdown.
