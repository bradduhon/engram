# Copyright (c) 2026 Brad Duhon. All Rights Reserved.
# Confidential and Proprietary.
# Unauthorized copying of this file is strictly prohibited.

terraform {
  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 6.0"
    }
  }
}

locals {
  memory_handler_name = "engram-memory-handler"
  cert_rotator_name   = "engram-cert-rotator"
  memory_handler_role = "engram-memory-handler-role"
  cert_rotator_role   = "engram-cert-rotator-role"

  # Official AWS Lambda Powertools layer (extras variant includes pydantic v2).
  # Account 017000801446 is the AWS-owned Powertools publisher account.
  # Pin the version; bump here when upgrading Powertools.
  powertools_layer_arn = "arn:aws:lambda:${var.aws_region}:017000801446:layer:AWSLambdaPowertoolsPythonV3-python312-arm64:${var.powertools_layer_version}"
}

# ---------------------------------------------------------------------------
# Bedrock Interface Endpoint
# Placed in compute (not networking) to avoid circular dependency:
# the endpoint policy references the memory handler IAM role created here.
# ---------------------------------------------------------------------------

resource "aws_vpc_endpoint" "bedrock" {
  vpc_id              = var.vpc_id
  service_name        = "com.amazonaws.${var.aws_region}.bedrock-runtime"
  vpc_endpoint_type   = "Interface"
  subnet_ids          = var.private_subnet_ids
  security_group_ids  = [var.bedrock_endpoint_security_group_id]
  private_dns_enabled = true

  tags = merge(var.tags, { Name = "engram-bedrock-endpoint" })
}

resource "aws_vpc_endpoint_policy" "bedrock" {
  vpc_endpoint_id = aws_vpc_endpoint.bedrock.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Sid    = "AllowSpecificModels"
        Effect = "Allow"
        Principal = {
          AWS = aws_iam_role.memory_handler.arn
        }
        Action = "bedrock:InvokeModel"
        Resource = [
          "arn:aws:bedrock:${var.aws_region}::foundation-model/amazon.titan-embed-text-v2:0",
          "arn:aws:bedrock:${var.aws_region}::foundation-model/anthropic.claude-haiku-4-5-20251001"
        ]
      }
    ]
  })
}

resource "aws_vpc_endpoint" "s3vectors" {
  vpc_id              = var.vpc_id
  service_name        = "com.amazonaws.${var.aws_region}.s3vectors"
  vpc_endpoint_type   = "Interface"
  subnet_ids          = var.private_subnet_ids
  security_group_ids  = [var.bedrock_endpoint_security_group_id]
  private_dns_enabled = true

  tags = merge(var.tags, { Name = "engram-s3vectors-endpoint" })
}

resource "aws_vpc_endpoint_policy" "s3vectors" {
  vpc_endpoint_id = aws_vpc_endpoint.s3vectors.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Sid    = "AllowMemoryHandlerVectorOps"
        Effect = "Allow"
        Principal = {
          AWS = aws_iam_role.memory_handler.arn
        }
        Action = [
          "s3vectors:PutVectors",
          "s3vectors:QueryVectors",
          "s3vectors:GetVectors",
          "s3vectors:DeleteVectors"
        ]
        Resource = [
          var.vector_bucket_arn,
          "${var.vector_bucket_arn}/index/*"
        ]
      }
    ]
  })
}

# ---------------------------------------------------------------------------
# Memory handler IAM role
# ---------------------------------------------------------------------------

resource "aws_iam_role" "memory_handler" {
  name = local.memory_handler_role

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect    = "Allow"
      Principal = { Service = "lambda.amazonaws.com" }
      Action    = "sts:AssumeRole"
    }]
  })

  tags = merge(var.tags, { Name = local.memory_handler_role })
}

resource "aws_iam_role_policy" "memory_handler" {
  name = "engram-memory-handler-policy"
  role = aws_iam_role.memory_handler.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Sid    = "BedrockEmbedOnly"
        Effect = "Allow"
        Action = ["bedrock:InvokeModel"]
        Resource = "arn:aws:bedrock:${var.aws_region}::foundation-model/amazon.titan-embed-text-v2:0"
      },
      {
        Sid    = "BedrockHaikuSummarize"
        Effect = "Allow"
        Action = ["bedrock:InvokeModel"]
        Resource = "arn:aws:bedrock:${var.aws_region}::foundation-model/anthropic.claude-haiku-4-5-20251001"
      },
      {
        # S3 Vectors operations. Resource ARN uses s3vectors service prefix.
        Sid    = "S3VectorOps"
        Effect = "Allow"
        Action = [
          "s3vectors:PutVectors",
          "s3vectors:QueryVectors",
          "s3vectors:GetVectors",
          "s3vectors:DeleteVectors"
        ]
        Resource = [
          var.vector_bucket_arn,
          "${var.vector_bucket_arn}/index/*"
        ]
      },
      {
        Sid    = "Logging"
        Effect = "Allow"
        Action = [
          "logs:CreateLogGroup",
          "logs:CreateLogStream",
          "logs:PutLogEvents"
        ]
        Resource = "arn:aws:logs:${var.aws_region}:${var.account_id}:log-group:/aws/lambda/${local.memory_handler_name}:*"
      },
      {
        # ENI management for Lambda VPC execution. AWS does not support
        # resource-level restrictions on these actions.
        Sid    = "VPCNetworkInterface"
        Effect = "Allow"
        Action = [
          "ec2:CreateNetworkInterface",
          "ec2:DescribeNetworkInterfaces",
          "ec2:DeleteNetworkInterface"
        ]
        Resource = "*" # tfsec-ignore: aws-iam-no-policy-wildcards
      },
      {
        Sid    = "XRayPutTrace"
        Effect = "Allow"
        Action = [
          "xray:PutTraceSegments",
          "xray:PutTelemetryRecords"
        ]
        Resource = "*" # tfsec-ignore: aws-iam-no-policy-wildcards -- X-Ray has no resource-level support
      },
      {
        Sid    = "DenyBedrockAdmin"
        Effect = "Deny"
        Action = [
          "bedrock:ListFoundationModels",
          "bedrock:GetFoundationModel",
          "bedrock:CreateModelCustomizationJob"
        ]
        Resource = "*"
      }
    ]
  })
}

# ---------------------------------------------------------------------------
# Cert rotator IAM role
# ---------------------------------------------------------------------------

resource "aws_iam_role" "cert_rotator" {
  name = local.cert_rotator_role

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect    = "Allow"
      Principal = { Service = "lambda.amazonaws.com" }
      Action    = "sts:AssumeRole"
    }]
  })

  tags = merge(var.tags, { Name = local.cert_rotator_role })
}

resource "aws_iam_role_policy" "cert_rotator" {
  name = "engram-cert-rotator-policy"
  role = aws_iam_role.cert_rotator.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Sid      = "ACMExport"
        Effect   = "Allow"
        Action   = ["acm:ExportCertificate"]
        Resource = var.client_cert_arn
      },
      {
        Sid      = "ACMDescribe"
        Effect   = "Allow"
        Action   = ["acm:DescribeCertificate"]
        Resource = var.client_cert_arn
      },
      {
        Sid    = "SecretsReadPassphrase"
        Effect = "Allow"
        Action = ["secretsmanager:GetSecretValue"]
        # Wildcard suffix required: SM appends a 6-char random suffix to secret ARNs.
        Resource = "${var.client_cert_passphrase_secret_arn}*"
      },
      {
        Sid    = "SecretsUpdateCert"
        Effect = "Allow"
        Action = ["secretsmanager:PutSecretValue"]
        Resource = "${var.client_cert_secret_arn}*"
      },
      {
        Sid    = "Logging"
        Effect = "Allow"
        Action = [
          "logs:CreateLogGroup",
          "logs:CreateLogStream",
          "logs:PutLogEvents"
        ]
        Resource = "arn:aws:logs:${var.aws_region}:${var.account_id}:log-group:/aws/lambda/${local.cert_rotator_name}:*"
      },
      {
        Sid      = "SNSPublish"
        Effect   = "Allow"
        Action   = ["sns:Publish"]
        Resource = "arn:aws:sns:${var.aws_region}:${var.account_id}:engram-alerts"
      },
      {
        Sid    = "DenyBedrockAdmin"
        Effect = "Deny"
        Action = [
          "bedrock:ListFoundationModels",
          "bedrock:GetFoundationModel",
          "bedrock:CreateModelCustomizationJob"
        ]
        Resource = "*"
      }
    ]
  })
}

# ---------------------------------------------------------------------------
# CloudWatch log groups (pre-created to control retention)
# ---------------------------------------------------------------------------

resource "aws_cloudwatch_log_group" "memory_handler" {
  name              = "/aws/lambda/${local.memory_handler_name}"
  retention_in_days = 30

  tags = var.tags
}

resource "aws_cloudwatch_log_group" "cert_rotator" {
  name              = "/aws/lambda/${local.cert_rotator_name}"
  retention_in_days = 30

  tags = var.tags
}

# ---------------------------------------------------------------------------
# Lambda deployment packages
# Dependencies (pydantic, powertools) are supplied via the Powertools layer.
# No build step required -- just zip the source.
# ---------------------------------------------------------------------------

data "archive_file" "memory_handler" {
  type        = "zip"
  source_dir  = "${path.module}/../../../src/memory_handler"
  output_path = "${path.module}/memory_handler.zip"
}

data "archive_file" "cert_rotator" {
  type        = "zip"
  source_dir  = "${path.module}/../../../src/cert_rotator"
  output_path = "${path.module}/cert_rotator.zip"
}

# ---------------------------------------------------------------------------
# Lambda functions
# ---------------------------------------------------------------------------

resource "aws_lambda_function" "memory_handler" {
  function_name    = local.memory_handler_name
  role             = aws_iam_role.memory_handler.arn
  runtime          = "python3.12"
  architectures    = ["arm64"]
  handler          = "handler.handler"
  filename         = data.archive_file.memory_handler.output_path
  source_code_hash = data.archive_file.memory_handler.output_base64sha256
  memory_size      = 512
  timeout          = 30

  layers = [local.powertools_layer_arn]

  tracing_config {
    mode = "Active"
  }

  vpc_config {
    subnet_ids         = var.private_subnet_ids
    security_group_ids = [var.lambda_security_group_id]
  }

  environment {
    variables = {
      MEMORY_BUCKET           = var.vector_bucket_name
      VECTOR_INDEX_NAME       = var.vector_index_name
      POWERTOOLS_SERVICE_NAME = local.memory_handler_name
      LOG_LEVEL               = "INFO"
      # S3 Vectors uses api.aws domain; explicit endpoint required for VPC routing.
      S3VECTORS_ENDPOINT_URL  = "https://s3vectors.${var.aws_region}.api.aws"
    }
  }

  depends_on = [
    aws_cloudwatch_log_group.memory_handler,
    aws_iam_role_policy.memory_handler,
  ]

  tags = merge(var.tags, { Name = local.memory_handler_name })
}

resource "aws_lambda_function" "cert_rotator" {
  function_name    = local.cert_rotator_name
  role             = aws_iam_role.cert_rotator.arn
  runtime          = "python3.12"
  architectures    = ["arm64"]
  handler          = "handler.handler"
  filename         = data.archive_file.cert_rotator.output_path
  source_code_hash = data.archive_file.cert_rotator.output_base64sha256
  memory_size      = 128
  timeout          = 30

  # Cert rotator calls ACM + Secrets Manager via public endpoints -- no VPC needed.

  environment {
    variables = {
      CLIENT_CERT_ARN           = var.client_cert_arn
      CERT_SECRET_ID            = var.client_cert_secret_arn
      PASSPHRASE_SECRET_ID      = var.client_cert_passphrase_secret_arn
      POWERTOOLS_SERVICE_NAME   = local.cert_rotator_name
      LOG_LEVEL                 = "INFO"
      # SNS_TOPIC_ARN wired in Phase 6 when the SNS topic is created.
    }
  }

  depends_on = [
    aws_cloudwatch_log_group.cert_rotator,
    aws_iam_role_policy.cert_rotator,
  ]

  tags = merge(var.tags, { Name = local.cert_rotator_name })
}
