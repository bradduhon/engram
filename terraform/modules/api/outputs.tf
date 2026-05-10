# Copyright (c) 2026 Engram Contributors. All Rights Reserved.
# Licensed under the MIT License. See LICENSE for details.

output "api_id" {
  description = "API Gateway HTTP API ID"
  value       = aws_apigatewayv2_api.memory.id
}

output "api_endpoint" {
  description = "Default API Gateway endpoint URL (use custom_domain_url for mTLS access)"
  value       = aws_apigatewayv2_api.memory.api_endpoint
}

output "custom_domain_target" {
  description = "API Gateway regional domain name -- create an A/CNAME record pointing server_domain_name here"
  value       = aws_apigatewayv2_domain_name.memory.domain_name_configuration[0].target_domain_name
}

output "custom_domain_url" {
  description = "HTTPS URL for the custom domain entry point (used by MCP server and hook script)"
  value       = "https://${var.server_domain_name}"
}

output "execution_arn" {
  description = "API Gateway execution ARN prefix -- used in Lambda resource policy source_arn"
  value       = aws_apigatewayv2_api.memory.execution_arn
}
