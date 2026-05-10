# Copyright (c) 2026 Engram Contributors. All Rights Reserved.
# Licensed under the MIT License. See LICENSE for details.

output "memory_handler_arn" {
  description = "Memory handler Lambda function ARN"
  value       = aws_lambda_function.memory_handler.arn
}

output "memory_handler_invoke_arn" {
  description = "Memory handler Lambda invoke ARN (for API Gateway integration)"
  value       = aws_lambda_function.memory_handler.invoke_arn
}

output "memory_handler_function_name" {
  description = "Memory handler Lambda function name"
  value       = aws_lambda_function.memory_handler.function_name
}

output "cert_rotator_arn" {
  description = "Cert rotator Lambda function ARN (for EventBridge target)"
  value       = aws_lambda_function.cert_rotator.arn
}

output "cert_rotator_function_name" {
  description = "Cert rotator Lambda function name"
  value       = aws_lambda_function.cert_rotator.function_name
}
