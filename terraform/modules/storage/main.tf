# Copyright (c) 2026 Engram Contributors. All Rights Reserved.
# Licensed under the MIT License. See LICENSE for details.

terraform {
  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 6.0"
    }
  }
}

locals {
  artifacts_bucket_name = "engram-artifacts-${var.account_id}"
  memory_bucket_name    = "engram-memory-${var.account_id}"
}

# ---------------------------------------------------------------------------
# Artifacts bucket (regular S3) -- mTLS truststore and operational files
# ---------------------------------------------------------------------------

resource "aws_s3_bucket" "artifacts" {
  bucket = local.artifacts_bucket_name

  lifecycle {
    prevent_destroy = true
  }

  tags = merge(var.tags, { Name = local.artifacts_bucket_name })
}

resource "aws_s3_bucket_versioning" "artifacts" {
  bucket = aws_s3_bucket.artifacts.id

  versioning_configuration {
    status = "Enabled"
  }
}

resource "aws_s3_bucket_server_side_encryption_configuration" "artifacts" {
  bucket = aws_s3_bucket.artifacts.id

  rule {
    apply_server_side_encryption_by_default {
      sse_algorithm = "aws:kms"
      # aws/s3 AWS-managed key -- rotation and key policy managed by AWS.
    }
    bucket_key_enabled = true
  }
}

resource "aws_s3_bucket_public_access_block" "artifacts" {
  bucket = aws_s3_bucket.artifacts.id

  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}

resource "aws_s3_bucket_policy" "artifacts" {
  bucket = aws_s3_bucket.artifacts.id

  depends_on = [aws_s3_bucket_public_access_block.artifacts]

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        # API Gateway reads the truststore PEM from S3 using a service principal.
        # It does not traverse the VPC endpoint and is not from this account's
        # IAM principals, so it must be explicitly allowed before the deny fires.
        Sid    = "AllowAPIGatewayTruststore"
        Effect = "Allow"
        Principal = {
          Service = "apigateway.amazonaws.com"
        }
        Action   = "s3:GetObject"
        Resource = "arn:aws:s3:::${local.artifacts_bucket_name}/mtls/truststore.pem"
      },
      {
        # Deny access from external AWS accounts. Same-account SSO session ARNs
        # have rotating suffixes, so account-level matching is used instead of
        # exact principal ARNs. API Gateway service principal is excluded via the
        # explicit Allow above (Allow wins over Deny for same-account service principals).
        Sid       = "DenyExternalAccounts"
        Effect    = "Deny"
        Principal = "*"
        Action    = "s3:*"
        Resource = [
          "arn:aws:s3:::${local.artifacts_bucket_name}",
          "arn:aws:s3:::${local.artifacts_bucket_name}/*"
        ]
        Condition = {
          StringNotEquals = {
            "aws:PrincipalAccount" = var.deployer_account_id
          }
        }
      },
      {
        Sid       = "DenyInsecureTransport"
        Effect    = "Deny"
        Principal = "*"
        Action    = "s3:*"
        Resource = [
          "arn:aws:s3:::${local.artifacts_bucket_name}",
          "arn:aws:s3:::${local.artifacts_bucket_name}/*"
        ]
        Condition = {
          Bool = {
            "aws:SecureTransport" = "false"
          }
        }
      }
    ]
  })
}

# ---------------------------------------------------------------------------
# S3 Vectors vector bucket -- long-term memory storage
# ---------------------------------------------------------------------------

resource "aws_s3vectors_vector_bucket" "memory" {
  vector_bucket_name = local.memory_bucket_name

  encryption_configuration {
    # S3 Vectors aws:kms requires an explicit kmsKeyArn (no aws/s3 shorthand).
    # Using AES256 (service-managed encryption) until a CMK is provisioned.
    sse_type = "AES256"
  }

  tags = merge(var.tags, { Name = local.memory_bucket_name })
}

# Vector index: Titan Embed v2 max output is 1024-dim float32 vectors.
# Valid dimensions: 256, 512, 1024.
resource "aws_s3vectors_index" "memories" {
  vector_bucket_name = aws_s3vectors_vector_bucket.memory.vector_bucket_name
  index_name         = "memories"
  data_type          = "float32"
  dimension          = 1024
  distance_metric    = "cosine"
}

# Restrict vector bucket access to this account only.
# S3 Vectors does not use the standard S3 Gateway Endpoint; a separate
# Interface Endpoint is added in Phase 3 once Lambda is in the VPC.
resource "aws_s3vectors_vector_bucket_policy" "memory" {
  vector_bucket_arn = aws_s3vectors_vector_bucket.memory.vector_bucket_arn

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Sid       = "DenyExternalAccounts"
        Effect    = "Deny"
        Principal = "*"
        Action    = "s3vectors:*"
        Resource = [
          "${aws_s3vectors_vector_bucket.memory.vector_bucket_arn}",
          "${aws_s3vectors_vector_bucket.memory.vector_bucket_arn}/index/*"
        ]
        Condition = {
          StringNotEquals = {
            "aws:PrincipalAccount" = var.deployer_account_id
          }
        }
      }
    ]
  })
}
