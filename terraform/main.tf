# Copyright (c) 2026 Brad Duhon. All Rights Reserved.
# Confidential and Proprietary.
# Unauthorized copying of this file is strictly prohibited.

# Phase 1: VPC, subnets, S3 Gateway Endpoint, security groups
module "networking" {
  source = "./modules/networking"

  aws_region = var.aws_region
  tags       = {}
}

# Phase 1: Artifacts S3 bucket (truststore), S3 Vectors bucket + index
module "storage" {
  source = "./modules/storage"

  account_id          = local.account_id
  vpc_endpoint_id     = module.networking.s3_gateway_endpoint_id
  deployer_account_id = local.account_id
  tags                = {}
}

# Phase 2: ACM certificates, Secrets Manager shells
module "certificates" {
  source = "./modules/certificates"

  server_domain_name = var.server_domain_name
  client_domain_name = var.client_domain_name
  tags               = {}
}

# Phase 3: Lambda functions, IAM roles, Bedrock VPC endpoint
module "compute" {
  source = "./modules/compute"

  vector_bucket_name                 = module.storage.vector_bucket_name
  vector_bucket_arn                  = module.storage.vector_bucket_arn
  vpc_id                             = module.networking.vpc_id
  private_subnet_ids                 = module.networking.private_subnet_ids
  lambda_security_group_id           = module.networking.lambda_security_group_id
  bedrock_endpoint_security_group_id = module.networking.bedrock_endpoint_security_group_id
  client_cert_arn                    = module.certificates.client_cert_arn
  client_cert_secret_arn             = module.certificates.client_cert_secret_arn
  client_cert_passphrase_secret_arn  = module.certificates.client_cert_passphrase_secret_arn
  aws_region                         = var.aws_region
  account_id                         = local.account_id
  tags                               = {}
}

# Phase 4: API Gateway, custom domain, mTLS, routes
module "api" {
  source = "./modules/api"

  server_cert_arn      = module.certificates.server_cert_arn
  truststore_s3_uri    = module.storage.truststore_s3_uri
  lambda_invoke_arn    = module.compute.memory_handler_invoke_arn
  lambda_function_name = module.compute.memory_handler_function_name
  route53_zone_id      = var.route53_zone_id
  server_domain_name   = var.server_domain_name
  tags                 = {}
}

# Phase 6: CloudWatch alarms, SNS, EventBridge scheduler
# module "observability" { ... }
