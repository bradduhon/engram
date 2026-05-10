# Copyright (c) 2026 Engram Contributors. All Rights Reserved.
# Licensed under the MIT License. See LICENSE for details.

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
      version = "2.0"
      rawPath = "/summarize"
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
# Cost reporter Lambda -- daily AWS cost delta published to SNS
# ---------------------------------------------------------------------------

data "archive_file" "cost_reporter" {
  type        = "zip"
  source_dir  = "${path.module}/../../../src/cost_reporter"
  output_path = "${path.module}/cost_reporter.zip"
}

resource "aws_cloudwatch_log_group" "cost_reporter" {
  name              = "/aws/lambda/engram-cost-reporter"
  retention_in_days = 30

  tags = merge(var.tags, { Name = "engram-cost-reporter-logs" })
}

resource "aws_iam_role" "cost_reporter" {
  name = "engram-cost-reporter-role"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect    = "Allow"
      Principal = { Service = "lambda.amazonaws.com" }
      Action    = "sts:AssumeRole"
      Condition = {
        StringEquals = { "aws:SourceAccount" = var.account_id }
      }
    }]
  })

  tags = merge(var.tags, { Name = "engram-cost-reporter-role" })
}

resource "aws_iam_role_policy" "cost_reporter" {
  name = "engram-cost-reporter-policy"
  role = aws_iam_role.cost_reporter.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Sid      = "CostExplorerRead"
        Effect   = "Allow"
        Action   = ["ce:GetCostAndUsage"]
        Resource = ["*"]
        # Cost Explorer does not support resource-level ARN scoping.
      },
      {
        Sid      = "PublishToAlerts"
        Effect   = "Allow"
        Action   = ["sns:Publish"]
        Resource = [aws_sns_topic.alerts.arn]
      },
      {
        Sid    = "CloudWatchLogs"
        Effect = "Allow"
        Action = [
          "logs:CreateLogStream",
          "logs:PutLogEvents",
        ]
        Resource = ["${aws_cloudwatch_log_group.cost_reporter.arn}:*"]
      },
    ]
  })
}

resource "aws_lambda_function" "cost_reporter" {
  function_name    = "engram-cost-reporter"
  role             = aws_iam_role.cost_reporter.arn
  runtime          = "python3.12"
  architectures    = ["arm64"]
  handler          = "handler.handler"
  filename         = data.archive_file.cost_reporter.output_path
  source_code_hash = data.archive_file.cost_reporter.output_base64sha256
  memory_size      = 128
  timeout          = 30

  environment {
    variables = {
      SNS_TOPIC_ARN = aws_sns_topic.alerts.arn
      LOG_LEVEL     = "INFO"
    }
  }

  depends_on = [
    aws_cloudwatch_log_group.cost_reporter,
    aws_iam_role_policy.cost_reporter,
  ]

  tags = merge(var.tags, { Name = "engram-cost-reporter" })
}

resource "aws_iam_role_policy" "scheduler_cost_reporter" {
  name = "engram-scheduler-cost-reporter-policy"
  role = aws_iam_role.scheduler.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Sid      = "InvokeCostReporter"
      Effect   = "Allow"
      Action   = ["lambda:InvokeFunction"]
      Resource = aws_lambda_function.cost_reporter.arn
    }]
  })
}

resource "aws_scheduler_schedule" "daily_cost_report" {
  name       = "engram-daily-cost-report"
  group_name = "default"

  flexible_time_window {
    mode = "OFF"
  }

  schedule_expression          = "cron(0 8 * * ? *)"
  schedule_expression_timezone = "UTC"

  target {
    arn      = aws_lambda_function.cost_reporter.arn
    role_arn = aws_iam_role.scheduler.arn
    input    = jsonencode({})
  }
}

resource "aws_lambda_permission" "scheduler_cost_reporter" {
  statement_id  = "AllowSchedulerInvokeCostReporter"
  action        = "lambda:InvokeFunction"
  function_name = aws_lambda_function.cost_reporter.function_name
  principal     = "scheduler.amazonaws.com"
  source_arn    = "arn:aws:scheduler:${var.aws_region}:${var.account_id}:schedule/default/engram-daily-cost-report"
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
