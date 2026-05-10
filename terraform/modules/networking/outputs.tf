# Copyright (c) 2026 Engram Contributors. All Rights Reserved.
# Licensed under the MIT License. See LICENSE for details.

output "vpc_id" {
  description = "VPC ID"
  value       = aws_vpc.main.id
}

output "private_subnet_ids" {
  description = "List of private subnet IDs"
  value       = aws_subnet.private[*].id
}

output "s3_gateway_endpoint_id" {
  description = "S3 Gateway Endpoint ID -- passed to storage module for bucket policy"
  value       = aws_vpc_endpoint.s3_gateway.id
}

output "lambda_security_group_id" {
  description = "Lambda security group ID"
  value       = aws_security_group.lambda.id
}

output "bedrock_endpoint_security_group_id" {
  description = "Bedrock endpoint security group ID"
  value       = aws_security_group.bedrock_endpoint.id
}

output "private_route_table_id" {
  description = "Private route table ID"
  value       = aws_route_table.private.id
}
