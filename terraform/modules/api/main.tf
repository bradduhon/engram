# Copyright (c) 2026 Brad Duhon. All Rights Reserved.
# Confidential and Proprietary.
# Unauthorized copying of this file is strictly prohibited.

# ---------------------------------------------------------------------------
# HTTP API
# ---------------------------------------------------------------------------

resource "aws_apigatewayv2_api" "memory" {
  name          = "engram-memory-api"
  protocol_type = "HTTP"

  tags = merge(var.tags, { Name = "engram-memory-api" })
}

# ---------------------------------------------------------------------------
# Access log group
# ---------------------------------------------------------------------------

resource "aws_cloudwatch_log_group" "apigw" {
  name              = "/aws/apigateway/engram-memory-api"
  retention_in_days = var.api_log_retention_days

  tags = var.tags
}

# ---------------------------------------------------------------------------
# Stage
# ---------------------------------------------------------------------------

resource "aws_apigatewayv2_stage" "default" {
  api_id      = aws_apigatewayv2_api.memory.id
  name        = "$default"
  auto_deploy = true

  default_route_settings {
    throttling_burst_limit = 100
    throttling_rate_limit  = 50
  }

  access_log_settings {
    destination_arn = aws_cloudwatch_log_group.apigw.arn
    format = jsonencode({
      requestId          = "$context.requestId"
      ip                 = "$context.identity.sourceIp"
      requestTime        = "$context.requestTime"
      httpMethod         = "$context.httpMethod"
      routeKey           = "$context.routeKey"
      status             = "$context.status"
      protocol           = "$context.protocol"
      responseLength     = "$context.responseLength"
      integrationLatency = "$context.integrationLatency"
    })
  }

  tags = merge(var.tags, { Name = "engram-memory-api-default-stage" })
}

# ---------------------------------------------------------------------------
# Lambda integration
# ---------------------------------------------------------------------------

resource "aws_apigatewayv2_integration" "lambda" {
  api_id                 = aws_apigatewayv2_api.memory.id
  integration_type       = "AWS_PROXY"
  integration_uri        = var.lambda_invoke_arn
  payload_format_version = "2.0"
}

# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------

resource "aws_apigatewayv2_route" "store" {
  api_id    = aws_apigatewayv2_api.memory.id
  route_key = "POST /store"
  target    = "integrations/${aws_apigatewayv2_integration.lambda.id}"
}

resource "aws_apigatewayv2_route" "recall" {
  api_id    = aws_apigatewayv2_api.memory.id
  route_key = "POST /recall"
  target    = "integrations/${aws_apigatewayv2_integration.lambda.id}"
}

resource "aws_apigatewayv2_route" "summarize" {
  api_id    = aws_apigatewayv2_api.memory.id
  route_key = "POST /summarize"
  target    = "integrations/${aws_apigatewayv2_integration.lambda.id}"
}

# ---------------------------------------------------------------------------
# Lambda resource-based policy -- allow API Gateway to invoke
# ---------------------------------------------------------------------------

resource "aws_lambda_permission" "apigw" {
  statement_id  = "AllowAPIGatewayInvoke"
  action        = "lambda:InvokeFunction"
  function_name = var.lambda_function_name
  principal     = "apigateway.amazonaws.com"
  source_arn    = "${aws_apigatewayv2_api.memory.execution_arn}/*/*"
}

# ---------------------------------------------------------------------------
# Custom domain with mTLS
# ---------------------------------------------------------------------------

resource "aws_apigatewayv2_domain_name" "memory" {
  domain_name = var.server_domain_name

  domain_name_configuration {
    certificate_arn = var.server_cert_arn
    endpoint_type   = "REGIONAL"
    security_policy = "TLS_1_2"
  }

  mutual_tls_authentication {
    truststore_uri = var.truststore_s3_uri
  }

  tags = merge(var.tags, { Name = "engram-memory-domain" })
}

resource "aws_apigatewayv2_api_mapping" "memory" {
  api_id      = aws_apigatewayv2_api.memory.id
  domain_name = aws_apigatewayv2_domain_name.memory.id
  stage       = aws_apigatewayv2_stage.default.id
}

# ---------------------------------------------------------------------------
# Route53 alias record
# ---------------------------------------------------------------------------

resource "aws_route53_record" "api" {
  zone_id = var.route53_zone_id
  name    = var.server_domain_name
  type    = "A"

  alias {
    name                   = aws_apigatewayv2_domain_name.memory.domain_name_configuration[0].target_domain_name
    zone_id                = aws_apigatewayv2_domain_name.memory.domain_name_configuration[0].hosted_zone_id
    evaluate_target_health = false
  }
}
