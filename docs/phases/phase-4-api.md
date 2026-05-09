# Phase 4: API Layer

## Overview

Creates the API Gateway HTTP API with a custom domain, mTLS authentication, route definitions, and Lambda proxy integration. After this phase, the service is reachable over the internet via `https://memory.brad-duhon.com` with mTLS enforcement.

## Prerequisites

- Phase 1 complete: S3 bucket with truststore PEM at `mtls/truststore.pem`
- Phase 2 complete: ACM server cert ISSUED for `memory.brad-duhon.com`
- Phase 3 complete: Lambda function `engram-memory-handler` deployed and invocable

## Resources Created

### Terraform -- `modules/api`

File: `terraform/modules/api/main.tf`

| Resource | Type | Key Config |
|----------|------|------------|
| `aws_apigatewayv2_api.memory` | HTTP API | Name: `engram-memory-api`, protocol: `HTTP` |
| `aws_apigatewayv2_domain_name.memory` | Custom domain | Domain: `memory.brad-duhon.com`, cert ARN, mTLS truststore |
| `aws_apigatewayv2_api_mapping.memory` | API mapping | Maps domain to API stage |
| `aws_apigatewayv2_stage.default` | Stage | Name: `$default`, auto-deploy: `true`, throttling, access logging |
| `aws_apigatewayv2_integration.lambda` | Integration | Lambda proxy, payload format v2 |
| `aws_apigatewayv2_route.store` | Route | `POST /store` |
| `aws_apigatewayv2_route.recall` | Route | `POST /recall` |
| `aws_apigatewayv2_route.summarize` | Route | `POST /summarize` |
| `aws_lambda_permission.apigw` | Permission | Allow API Gateway to invoke Lambda |
| `aws_route53_record.api` | DNS | A alias record for the custom domain |
| `aws_cloudwatch_log_group.apigw` | Log group | Access logging for API Gateway |

### mTLS Configuration

The `aws_apigatewayv2_domain_name` resource includes the mTLS block:

```hcl
resource "aws_apigatewayv2_domain_name" "memory" {
  domain_name = "memory.brad-duhon.com"

  domain_name_configuration {
    certificate_arn = var.server_cert_arn
    endpoint_type   = "REGIONAL"
    security_policy = "TLS_1_2"
  }

  mutual_tls_authentication {
    truststore_uri = var.truststore_s3_uri
  }
}
```

API Gateway validates the client certificate chain against the truststore (Amazon Trust Services root CAs) before the request reaches Lambda. Invalid or missing client certs result in a 403 at the API Gateway level.

### Stage Throttling

```hcl
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
      requestId      = "$context.requestId"
      ip             = "$context.identity.sourceIp"
      requestTime    = "$context.requestTime"
      httpMethod     = "$context.httpMethod"
      routeKey       = "$context.routeKey"
      status         = "$context.status"
      protocol       = "$context.protocol"
      responseLength = "$context.responseLength"
      integrationLatency = "$context.integrationLatency"
    })
  }
}
```

### Lambda Permission

```hcl
resource "aws_lambda_permission" "apigw" {
  statement_id  = "AllowAPIGatewayInvoke"
  action        = "lambda:InvokeFunction"
  function_name = var.lambda_function_name
  principal     = "apigateway.amazonaws.com"
  source_arn    = "${aws_apigatewayv2_api.memory.execution_arn}/*/*"
}
```

### Route53 A Record

```hcl
resource "aws_route53_record" "api" {
  zone_id = var.route53_zone_id
  name    = "memory.brad-duhon.com"
  type    = "A"

  alias {
    name                   = aws_apigatewayv2_domain_name.memory.domain_name_configuration[0].target_domain_name
    zone_id                = aws_apigatewayv2_domain_name.memory.domain_name_configuration[0].hosted_zone_id
    evaluate_target_health = false
  }
}
```

## Terraform Variables

### `modules/api`

| Variable | Type | Description |
|----------|------|-------------|
| `server_cert_arn` | `string` | ACM server cert ARN for custom domain |
| `truststore_s3_uri` | `string` | S3 URI of truststore PEM (e.g., `s3://engram-memory-.../mtls/truststore.pem`) |
| `lambda_invoke_arn` | `string` | Lambda invoke ARN for integration |
| `lambda_function_name` | `string` | Lambda function name for permission |
| `route53_zone_id` | `string` | Route53 hosted zone ID |
| `api_log_retention_days` | `number` | Access log retention (default: `30`) |

## Terraform Outputs

### `modules/api`

| Output | Description | Used By |
|--------|-------------|---------|
| `api_id` | API Gateway ID | Phase 6 (observability, optional) |
| `api_endpoint` | Default API endpoint URL | Reference (not used directly; custom domain is the entry point) |
| `custom_domain_url` | `https://memory.brad-duhon.com` | Phase 5 (MCP server config), Phase 7 (hook script) |

## Security Controls

- **mTLS enforcement:** API Gateway rejects any request without a valid client certificate signed by Amazon Trust Services. This is the primary authentication layer.
- **TLS 1.2 minimum:** `security_policy = "TLS_1_2"` on the domain. TLS 1.3 is used when the client supports it.
- **No API keys:** mTLS replaces API keys. No `x-api-key` header needed.
- **No CORS:** No browser clients access this API. CORS is not configured.
- **Lambda permission:** Scoped to this specific API Gateway's execution ARN.
- **Access logging:** All requests logged to CloudWatch with request ID, route, status, and latency. No request bodies logged.
- **Throttling:** 100 burst / 50 steady RPS. Single-user service; higher limits indicate abuse or misconfiguration.

## Implementation Steps

1. Create `terraform/modules/api/variables.tf` with the variables listed above.

2. Create `terraform/modules/api/main.tf` with all resources listed above.

3. Create `terraform/modules/api/outputs.tf` with all outputs listed above.

4. Wire in `terraform/main.tf`:
   ```hcl
   module "api" {
     source               = "./modules/api"
     server_cert_arn      = module.certificates.server_cert_arn
     truststore_s3_uri    = module.storage.truststore_s3_uri
     lambda_invoke_arn    = module.compute.memory_handler_invoke_arn
     lambda_function_name = module.compute.memory_handler_function_name
     route53_zone_id      = var.route53_zone_id
   }
   ```

5. Run `terraform apply -target=module.api`.

6. Wait for DNS propagation (the A record alias may take a few minutes).

7. Test mTLS end-to-end using the exported client cert.

## Acceptance Criteria

```bash
# Verify API Gateway exists
aws apigatewayv2 get-apis --query 'Items[?Name==`engram-memory-api`].ApiId' --output text
# Expected: an API ID

# Verify custom domain
aws apigatewayv2 get-domain-name --domain-name memory.brad-duhon.com \
  --query 'MutualTlsAuthentication.TruststoreUri'
# Expected: s3://engram-memory-.../mtls/truststore.pem

# Verify DNS resolves
dig memory.brad-duhon.com +short
# Expected: API Gateway domain name

# mTLS test -- successful auth (requires exported client cert files)
# Using age-encrypted key from Phase 7, or plaintext key for testing:
curl --cert /tmp/client.crt --key /tmp/client.key \
  --cacert /tmp/amazon-trust-services-ca.pem \
  -X POST https://memory.brad-duhon.com/store \
  -H "Content-Type: application/json" \
  -d '{"text":"e2e api test","scope":"global","conversation_id":"e2e-1"}'
# Expected: {"stored": true, "id": "...", "scope": "global", ...}

# mTLS test -- no client cert (should be rejected)
curl -X POST https://memory.brad-duhon.com/store \
  -H "Content-Type: application/json" \
  -d '{"text":"should fail","scope":"global","conversation_id":"fail-1"}' \
  -w "\n%{http_code}\n"
# Expected: 403

# mTLS test -- recall
curl --cert /tmp/client.crt --key /tmp/client.key \
  --cacert /tmp/amazon-trust-services-ca.pem \
  -X POST https://memory.brad-duhon.com/recall \
  -H "Content-Type: application/json" \
  -d '{"query":"api test"}'
# Expected: {"memories": [...], "total": ..., "query_ms": ...}

# Terraform validation
cd terraform && terraform validate
```

## Notes

- The `$default` stage with `auto_deploy = true` means any route changes take effect immediately. No manual deployment step needed.
- The truststore PEM in S3 must be accessible by API Gateway. The bucket policy's VPC-endpoint-only restriction may block API Gateway's access. If so, add a condition allowing the `apigateway.amazonaws.com` service principal to read the truststore object, or add the truststore to a separate public-read object (it contains only public CA certs). This is a common gotcha with mTLS + VPC-locked buckets.
- If the truststore fails validation, API Gateway returns a 500 on domain creation. Check CloudWatch for the API Gateway service error.
- The `integrationLatency` in access logs measures Lambda execution time. This is useful for identifying slow invocations without querying Lambda-specific metrics.
