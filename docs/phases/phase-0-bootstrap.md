# Phase 0: Bootstrap TF State Backend

## Overview

Creates the S3 bucket and DynamoDB table that store Terraform state and locks for all subsequent phases. This is a separate Terraform root module with local state, run exactly once.

## Prerequisites

- AWS CLI configured with credentials that have S3 and DynamoDB permissions
- Terraform >= 1.5 installed
- AWS account ID known (referenced as `{account_id}` throughout)

## Resources Created

### Terraform

All resources in `terraform/bootstrap/`.

| Resource | Type | Name | File |
|----------|------|------|------|
| State bucket | `aws_s3_bucket` | `engram-tfstate-{account_id}` | `terraform/bootstrap/main.tf` |
| Bucket versioning | `aws_s3_bucket_versioning` | (attached to state bucket) | `terraform/bootstrap/main.tf` |
| Bucket encryption | `aws_s3_bucket_server_side_encryption_configuration` | SSE-S3 (AES256) | `terraform/bootstrap/main.tf` |
| Block public access | `aws_s3_bucket_public_access_block` | all four settings `true` | `terraform/bootstrap/main.tf` |
| Bucket policy | `aws_s3_bucket_policy` | restrict to deploying principal | `terraform/bootstrap/main.tf` |
| Lock table | `aws_dynamodb_table` | `engram-tflock` | `terraform/bootstrap/main.tf` |

### Data Sources

| Data Source | Purpose |
|-------------|---------|
| `data.aws_caller_identity.current` | Derive account ID for bucket name |
| `data.aws_region.current` | Derive region |

## Terraform Variables

| Variable | Type | Description | Default |
|----------|------|-------------|---------|
| `aws_region` | `string` | AWS region for state resources | `"us-east-1"` |

## Terraform Outputs

| Output | Description | Used By |
|--------|-------------|---------|
| `state_bucket_name` | Name of the state bucket | `terraform/providers.tf` backend config |
| `state_bucket_arn` | ARN of the state bucket | Reference only |
| `lock_table_name` | Name of the DynamoDB lock table | `terraform/providers.tf` backend config |

## Security Controls

- S3 bucket: versioning enabled, SSE-S3 encryption, all public access blocked
- Bucket policy: restricts `s3:*` to the current caller identity (deploying IAM principal) only
- DynamoDB: uses default encryption (AWS owned key)
- This is the only phase requiring broad IAM permissions. All subsequent phases use scoped roles.
- State file may contain sensitive values from later phases. The bucket policy and block-public-access settings protect it.

## Implementation Steps

1. Create `terraform/bootstrap/providers.tf`:
   ```hcl
   terraform {
     required_version = ">= 1.5"
     required_providers {
       aws = {
         source  = "hashicorp/aws"
         version = "~> 5.0"
       }
     }
     # Local state -- this module bootstraps the remote backend
   }

   provider "aws" {
     region = var.aws_region
     default_tags {
       tags = {
         Project   = "engram"
         ManagedBy = "terraform"
       }
     }
   }
   ```

2. Create `terraform/bootstrap/variables.tf`:
   ```hcl
   variable "aws_region" {
     description = "AWS region for state backend resources"
     type        = string
     default     = "us-east-1"
   }
   ```

3. Create `terraform/bootstrap/main.tf` with all resources listed above. Key details:
   - Bucket name: `"engram-tfstate-${data.aws_caller_identity.current.account_id}"`
   - DynamoDB table: partition key `LockID` (type `S`), billing mode `PAY_PER_REQUEST`
   - Bucket policy: allow `s3:GetObject`, `s3:PutObject`, `s3:ListBucket`, `s3:DeleteObject` for `data.aws_caller_identity.current.arn` only

4. Create `terraform/bootstrap/outputs.tf` with all outputs listed above.

5. Create `terraform/providers.tf` (the main root module's backend config):
   ```hcl
   terraform {
     required_version = ">= 1.5"
     required_providers {
       aws = {
         source  = "hashicorp/aws"
         version = "~> 5.0"
       }
     }
     backend "s3" {
       bucket         = "engram-tfstate-ACCOUNT_ID_HERE"
       key            = "engram/terraform.tfstate"
       region         = "us-east-1"
       dynamodb_table = "engram-tflock"
       encrypt        = true
     }
   }

   provider "aws" {
     region = var.aws_region
     default_tags {
       tags = {
         Project   = "engram"
         ManagedBy = "terraform"
       }
     }
   }
   ```
   Note: The `bucket` value in the backend block must be a literal string (no interpolation). After running `terraform apply` in `bootstrap/`, replace `ACCOUNT_ID_HERE` with the actual account ID from the bootstrap output.

6. Create stub files for the root module: `terraform/variables.tf`, `terraform/outputs.tf`, `terraform/locals.tf`, `terraform/data.tf`, `terraform/main.tf` (empty or with `data.aws_caller_identity.current` and `data.aws_region.current`).

## Acceptance Criteria

```bash
# Deploy bootstrap
cd terraform/bootstrap
terraform init
terraform apply -auto-approve

# Verify resources exist
aws s3api head-bucket --bucket engram-tfstate-$(aws sts get-caller-identity --query Account --output text)
aws dynamodb describe-table --table-name engram-tflock --query Table.TableStatus
# Expected: "ACTIVE"

# Initialize main root module with remote backend
cd ../
# (after updating providers.tf with actual account ID)
terraform init
# Expected: "Terraform has been successfully initialized!"

# Verify state is remote
terraform state list
# Expected: empty (no resources yet), but no errors
```

## Notes

- The bootstrap state file (`terraform/bootstrap/terraform.tfstate`) is local. It can be committed to the repo since it contains no secrets, or it can be stored elsewhere. It is only needed if the state bucket or lock table need modification.
- If the state bucket already exists from a prior attempt, `terraform import` the existing resources rather than recreating.
- The DynamoDB table uses `PAY_PER_REQUEST` billing since lock operations are infrequent.
