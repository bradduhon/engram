# Phase 6: Automation & Observability

## Overview

Creates CloudWatch alarms for error/latency/throttle monitoring, SNS topic for alert notifications, EventBridge Scheduler for daily memory summarization, and EventBridge rule for ACM cert expiry automation. After this phase, the service is self-maintaining (daily compression, cert rotation) and observable.

## Prerequisites

- Phase 3 complete: Lambda functions deployed (memory handler + cert rotator)
- Phase 4 complete: API Gateway deployed with access logging
- SNS subscription email address known

## Resources Created

### Terraform -- `modules/observability`

File: `terraform/modules/observability/main.tf`

| Resource | Type | Key Config |
|----------|------|------------|
| `aws_sns_topic.alerts` | SNS topic | Name: `engram-alerts` |
| `aws_sns_topic_subscription.email` | Subscription | Protocol: `email`, endpoint: operator email |
| `aws_cloudwatch_metric_alarm.errors` | Alarm | Metric: `Errors`, threshold: 1, period: 300s |
| `aws_cloudwatch_metric_alarm.duration_p99` | Alarm | Metric: `Duration`, statistic: p99, threshold: 20000ms |
| `aws_cloudwatch_metric_alarm.throttles` | Alarm | Metric: `Throttles`, threshold: 1, period: 300s |
| `aws_scheduler_schedule.daily_summarize` | EventBridge Scheduler | Cron: `cron(0 2 * * ? *)`, target: memory handler Lambda |
| `aws_iam_role.scheduler` | IAM role | Assume: `scheduler.amazonaws.com`, allow: `lambda:InvokeFunction` |
| `aws_cloudwatch_event_rule.cert_expiry` | EventBridge rule | Source: `aws.acm`, detail-type: `ACM Certificate Approaching Expiration` |
| `aws_cloudwatch_event_target.cert_rotation` | EventBridge target | Target: cert rotator Lambda |
| `aws_lambda_permission.cert_expiry` | Permission | Allow EventBridge to invoke cert rotator |
| `aws_lambda_permission.scheduler` | Permission | Allow EventBridge Scheduler to invoke memory handler |

### CloudWatch Alarms

```hcl
resource "aws_cloudwatch_metric_alarm" "errors" {
  alarm_name          = "engram-memory-handler-errors"
  comparison_operator = "GreaterThanThreshold"
  evaluation_periods  = 1
  metric_name         = "Errors"
  namespace           = "AWS/Lambda"
  period              = 300
  statistic           = "Sum"
  threshold           = 0
  treat_missing_data  = "notBreaching"
  alarm_actions       = [aws_sns_topic.alerts.arn]

  dimensions = {
    FunctionName = var.memory_handler_function_name
  }
}

resource "aws_cloudwatch_metric_alarm" "duration_p99" {
  alarm_name          = "engram-memory-handler-duration-p99"
  comparison_operator = "GreaterThanThreshold"
  evaluation_periods  = 1
  metric_name         = "Duration"
  namespace           = "AWS/Lambda"
  period              = 300
  extended_statistic  = "p99"
  threshold           = 20000
  treat_missing_data  = "notBreaching"
  alarm_actions       = [aws_sns_topic.alerts.arn]

  dimensions = {
    FunctionName = var.memory_handler_function_name
  }
}

resource "aws_cloudwatch_metric_alarm" "throttles" {
  alarm_name          = "engram-memory-handler-throttles"
  comparison_operator = "GreaterThanThreshold"
  evaluation_periods  = 1
  metric_name         = "Throttles"
  namespace           = "AWS/Lambda"
  period              = 300
  statistic           = "Sum"
  threshold           = 0
  treat_missing_data  = "notBreaching"
  alarm_actions       = [aws_sns_topic.alerts.arn]

  dimensions = {
    FunctionName = var.memory_handler_function_name
  }
}
```

### EventBridge Scheduler -- Daily Summarizer

```hcl
resource "aws_scheduler_schedule" "daily_summarize" {
  name       = "engram-daily-summarize"
  group_name = "default"

  flexible_time_window {
    mode = "OFF"
  }

  schedule_expression          = "cron(0 2 * * ? *)"
  schedule_expression_timezone = "UTC"

  target {
    arn      = var.memory_handler_arn
    role_arn = aws_iam_role.scheduler.arn

    input = jsonencode({
      requestContext = {
        http = { path = "/summarize" }
      }
      body = jsonencode({
        scope             = "global"
        delete_originals  = false
      })
    })
  }
}
```

Note: The scheduler invokes Lambda directly (not through API Gateway), bypassing mTLS entirely. The trust boundary is the EventBridge Scheduler IAM role and the Lambda resource policy, which limits direct invocations to AWS service principals with scoped roles.

### EventBridge Rule -- Cert Expiry

```hcl
resource "aws_cloudwatch_event_rule" "cert_expiry" {
  name        = "engram-cert-expiry"
  description = "Trigger cert rotation when ACM cert approaches expiration"

  event_pattern = jsonencode({
    source      = ["aws.acm"]
    detail-type = ["ACM Certificate Approaching Expiration"]
    detail = {
      CertificateArn = [var.client_cert_arn]
    }
  })
}

resource "aws_cloudwatch_event_target" "cert_rotation" {
  rule      = aws_cloudwatch_event_rule.cert_expiry.name
  target_id = "cert-rotator"
  arn       = var.cert_rotator_arn
}
```

## Terraform Variables

### `modules/observability`

| Variable | Type | Description |
|----------|------|-------------|
| `memory_handler_function_name` | `string` | Memory handler Lambda name (for alarms) |
| `memory_handler_arn` | `string` | Memory handler Lambda ARN (for scheduler target) |
| `cert_rotator_arn` | `string` | Cert rotator Lambda ARN (for EventBridge target) |
| `cert_rotator_function_name` | `string` | Cert rotator Lambda name (for permission) |
| `client_cert_arn` | `string` | ACM client cert ARN (for expiry event filter) |
| `alert_email` | `string` | Email for SNS alarm notifications |
| `account_id` | `string` | AWS account ID |
| `aws_region` | `string` | AWS region |

## Terraform Outputs

### `modules/observability`

| Output | Description | Used By |
|--------|-------------|---------|
| `sns_topic_arn` | Alerts SNS topic ARN | Reference |
| `scheduler_role_arn` | EventBridge Scheduler IAM role ARN | Reference |

## Security Controls

- **SNS topic:** No public access. Subscription requires email confirmation.
- **Scheduler IAM role:** Allows only `lambda:InvokeFunction` on the memory handler Lambda. No other actions.
- **Cert expiry event filter:** Scoped to the specific client cert ARN. Other ACM cert events are ignored.
- **`treat_missing_data = "notBreaching"`:** Prevents false alarms when no Lambda invocations occur (e.g., overnight, weekends). Missing data points are treated as "OK".
- **Scheduler direct invocation:** The daily summarizer invokes Lambda directly, bypassing API Gateway mTLS. The trust boundary is the EventBridge Scheduler IAM role and Lambda resource policy.

## Implementation Steps

1. Create `terraform/modules/observability/variables.tf` with the variables listed above.

2. Create `terraform/modules/observability/main.tf` with all resources listed above.

3. Create `terraform/modules/observability/outputs.tf`.

4. Wire in `terraform/main.tf`:
   ```hcl
   module "observability" {
     source                        = "./modules/observability"
     memory_handler_function_name  = module.compute.memory_handler_function_name
     memory_handler_arn            = module.compute.memory_handler_arn
     cert_rotator_arn              = module.compute.cert_rotator_arn
     cert_rotator_function_name    = module.compute.cert_rotator_function_name
     client_cert_arn               = module.certificates.client_cert_arn
     alert_email                   = var.alert_email
     account_id                    = data.aws_caller_identity.current.account_id
     aws_region                    = data.aws_region.current.name
   }
   ```

5. Add `alert_email` to `terraform/variables.tf`.

6. Run `terraform apply -target=module.observability`.

7. Confirm the SNS subscription email (check inbox for the confirmation link).

8. Add the system prompt instruction for session-end memory storage. This goes in Claude's system prompt (project-level or global instructions):
   ```
   At the end of every conversation, before your final response, call store_memory
   with a concise summary covering: decisions made, preferences expressed,
   technical context established, and any action items. Use scope: project if
   inside a Claude Project, otherwise scope: global.
   ```

## Acceptance Criteria

```bash
# Verify alarms exist
aws cloudwatch describe-alarms --alarm-name-prefix engram \
  --query 'MetricAlarms[].AlarmName'
# Expected: ["engram-memory-handler-errors", "engram-memory-handler-duration-p99", "engram-memory-handler-throttles"]

# Verify SNS topic
aws sns list-topics --query 'Topics[?contains(TopicArn, `engram-alerts`)]'
# Expected: one topic ARN

# Verify scheduler
aws scheduler get-schedule --name engram-daily-summarize \
  --query 'ScheduleExpression'
# Expected: "cron(0 2 * * ? *)"

# Verify cert expiry rule
aws events describe-rule --name engram-cert-expiry \
  --query 'State'
# Expected: "ENABLED"

# Trigger a test alarm (optional -- invoke Lambda with an intentionally bad payload)
aws lambda invoke --function-name engram-memory-handler \
  --payload '{"requestContext":{"http":{"path":"/bad"}},"headers":{}}' \
  /tmp/test-alarm.json
# Then check SNS for the error alarm notification

# Terraform validation
cd terraform && terraform validate
```

## Notes

- The SNS email subscription requires manual confirmation. Check the inbox for the `alert_email` address and click the confirmation link after `terraform apply`.
- The daily summarizer runs at 02:00 UTC. Adjust the cron expression if a different time is preferred.
- EventBridge Scheduler (not EventBridge Rules) is used for the daily summarizer because Scheduler supports one-time and recurring schedules with IAM role targeting, which is simpler than creating an EventBridge rule + target + permission.
- The cert expiry event fires ~45 days before the cert expires. ACM renews the cert ~60 days before expiry, so the rotation Lambda may fire before or after automatic renewal. The rotation Lambda is idempotent -- re-exporting an already-renewed cert is harmless.
- Consider adding a `project`-scoped daily summarizer in the future. The current scheduler only summarizes `global` memories. Project-scoped summarization requires knowing which projects have active memories, which adds complexity.
