output "state_bucket_name" {
  description = "Name of the Terraform state S3 bucket -- use in terraform/providers.tf backend block"
  value       = aws_s3_bucket.tfstate.id
}

output "state_bucket_arn" {
  description = "ARN of the Terraform state S3 bucket"
  value       = aws_s3_bucket.tfstate.arn
}

output "lock_table_name" {
  description = "Name of the DynamoDB lock table -- use in terraform/providers.tf backend block"
  value       = aws_dynamodb_table.tflock.name
}

output "aws_region" {
  description = "AWS region these resources were deployed to"
  value       = data.aws_region.current.name
}

output "account_id" {
  description = "AWS account ID"
  value       = data.aws_caller_identity.current.account_id
}
