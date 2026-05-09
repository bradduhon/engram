# Copyright (c) 2026 Brad Duhon. All Rights Reserved.
# Confidential and Proprietary.
# Unauthorized copying of this file is strictly prohibited.

# ---------------------------------------------------------------------------
# SNS alerts topic
# ---------------------------------------------------------------------------

resource "aws_sns_topic" "alerts" {
  name = "engram-alerts"

  tags = merge(var.tags, { Name = "engram-alerts" })
}

resource "aws_sns_topic_subscription" "email" {
  topic_arn = aws_sns_topic.alerts.arn
  protocol  = "email"
  endpoint  = var.alert_email
}

# ---------------------------------------------------------------------------
# CloudWatch alarms -- memory handler Lambda
# ---------------------------------------------------------------------------

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

  tags = var.tags
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

  tags = var.tags
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

  tags = var.tags
}

# ---------------------------------------------------------------------------
# EventBridge Scheduler -- daily memory summarizer (02:00 UTC)
# ---------------------------------------------------------------------------

resource "aws_iam_role" "scheduler" {
  name = "engram-scheduler-role"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect    = "Allow"
      Principal = { Service = "scheduler.amazonaws.com" }
      Action    = "sts:AssumeRole"
      Condition = {
        StringEquals = {
          "aws:SourceAccount" = var.account_id
        }
      }
    }]
  })

  tags = merge(var.tags, { Name = "engram-scheduler-role" })
}

resource "aws_iam_role_policy" "scheduler" {
  name = "engram-scheduler-policy"
  role = aws_iam_role.scheduler.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Sid      = "InvokeMemoryHandler"
      Effect   = "Allow"
      Action   = ["lambda:InvokeFunction"]
      Resource = var.memory_handler_arn
    }]
  })
}

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

    # Direct Lambda invocation bypasses API Gateway mTLS. Trust boundary is the
    # scheduler IAM role + Lambda resource policy (source_arn scoped to this account).
    input = jsonencode({
      version        = "2.0"
      rawPath        = "/summarize"
      requestContext = {
        http = {
          method = "POST"
          path   = "/summarize"
        }
        stage = "$default"
      }
      headers = {
        "content-type" = "application/json"
      }
      body = jsonencode({
        scope            = "global"
        delete_originals = false
      })
      isBase64Encoded = false
    })
  }
}

resource "aws_lambda_permission" "scheduler" {
  statement_id  = "AllowSchedulerInvoke"
  action        = "lambda:InvokeFunction"
  function_name = var.memory_handler_function_name
  principal     = "scheduler.amazonaws.com"
  source_arn    = "arn:aws:scheduler:${var.aws_region}:${var.account_id}:schedule/default/engram-daily-summarize"
}

# ---------------------------------------------------------------------------
# EventBridge rule -- ACM cert expiry -> cert rotator
# ---------------------------------------------------------------------------

resource "aws_cloudwatch_event_rule" "cert_expiry" {
  name        = "engram-cert-expiry"
  description = "Trigger cert rotation when the ACM client cert approaches expiration"

  event_pattern = jsonencode({
    source      = ["aws.acm"]
    detail-type = ["ACM Certificate Approaching Expiration"]
    detail = {
      CertificateArn = [var.client_cert_arn]
    }
  })

  tags = merge(var.tags, { Name = "engram-cert-expiry" })
}

resource "aws_cloudwatch_event_target" "cert_rotation" {
  rule      = aws_cloudwatch_event_rule.cert_expiry.name
  target_id = "cert-rotator"
  arn       = var.cert_rotator_arn
}

resource "aws_lambda_permission" "cert_expiry" {
  statement_id  = "AllowEventBridgeCertExpiry"
  action        = "lambda:InvokeFunction"
  function_name = var.cert_rotator_function_name
  principal     = "events.amazonaws.com"
  source_arn    = aws_cloudwatch_event_rule.cert_expiry.arn
}
