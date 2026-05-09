# Copyright (c) 2026 Brad Duhon. All Rights Reserved.
# Confidential and Proprietary.
# Unauthorized copying of this file is strictly prohibited.

output "api_id" {
  description = "API Gateway HTTP API ID"
  value       = aws_apigatewayv2_api.memory.id
}

output "api_endpoint" {
  description = "Default API Gateway endpoint URL (use custom_domain_url for mTLS access)"
  value       = aws_apigatewayv2_api.memory.api_endpoint
}

output "custom_domain_url" {
  description = "HTTPS URL for the custom domain entry point (used by MCP server and hook script)"
  value       = "https://${var.server_domain_name}"
}

output "execution_arn" {
  description = "API Gateway execution ARN prefix -- used in Lambda resource policy source_arn"
  value       = aws_apigatewayv2_api.memory.execution_arn
}
