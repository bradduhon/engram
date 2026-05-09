# Copyright (c) 2026 Brad Duhon. All Rights Reserved.
# Confidential and Proprietary.
# Unauthorized copying of this file is strictly prohibited.

output "sns_topic_arn" {
  description = "Alerts SNS topic ARN"
  value       = aws_sns_topic.alerts.arn
}

output "scheduler_role_arn" {
  description = "EventBridge Scheduler IAM role ARN"
  value       = aws_iam_role.scheduler.arn
}
