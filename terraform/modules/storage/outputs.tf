# Copyright (c) 2026 Brad Duhon. All Rights Reserved.
# Confidential and Proprietary.
# Unauthorized copying of this file is strictly prohibited.

output "artifacts_bucket_id" {
  description = "Artifacts S3 bucket ID"
  value       = aws_s3_bucket.artifacts.id
}

output "artifacts_bucket_arn" {
  description = "Artifacts S3 bucket ARN -- used in Lambda IAM policy"
  value       = aws_s3_bucket.artifacts.arn
}

output "artifacts_bucket_name" {
  description = "Artifacts S3 bucket name -- passed as Lambda env var"
  value       = aws_s3_bucket.artifacts.bucket
}

output "truststore_s3_uri" {
  description = "S3 URI of the mTLS truststore PEM -- used in Phase 4 API Gateway mTLS config"
  value       = "s3://${aws_s3_bucket.artifacts.bucket}/mtls/truststore.pem"
}

output "vector_bucket_name" {
  description = "S3 Vectors vector bucket name -- passed as Lambda env var"
  value       = aws_s3vectors_vector_bucket.memory.vector_bucket_name
}

output "vector_bucket_arn" {
  description = "S3 Vectors vector bucket ARN -- used in Lambda IAM policy"
  value       = aws_s3vectors_vector_bucket.memory.vector_bucket_arn
}

output "vector_index_name" {
  description = "S3 Vectors index name -- passed as Lambda env var"
  value       = aws_s3vectors_index.memories.index_name
}
