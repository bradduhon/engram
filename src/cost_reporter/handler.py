# Copyright (c) 2026 Brad Duhon. All Rights Reserved.
# Confidential and Proprietary.
# Unauthorized copying of this file is strictly prohibited.
from __future__ import annotations

import json
import logging
import os
from datetime import date, timedelta
from typing import Any

import boto3

logger = logging.getLogger(__name__)
logger.setLevel(os.environ.get("LOG_LEVEL", "INFO"))

# Cost Explorer is a global service but its endpoint lives in us-east-1.
_ce_client = boto3.client("ce", region_name="us-east-1")
_sns_client = boto3.client("sns", region_name=os.environ.get("AWS_REGION", "us-east-1"))

_SNS_TOPIC_ARN = os.environ["SNS_TOPIC_ARN"]


def _get_daily_cost(start: date, end: date) -> float:
    """Return total unblended cost in USD for the given date range (exclusive end)."""
    response = _ce_client.get_cost_and_usage(
        TimePeriod={
            "Start": start.isoformat(),
            "End": end.isoformat(),
        },
        Granularity="DAILY",
        Metrics=["UnblendedCost"],
    )
    total = sum(
        float(group["Total"]["UnblendedCost"]["Amount"])
        for group in response.get("ResultsByTime", [])
    )
    return total


def handler(event: dict[str, Any], context: object) -> dict[str, Any]:
    """Fetch yesterday's and the day-before-yesterday's cost, publish delta to SNS."""
    today = date.today()
    yesterday = today - timedelta(days=1)
    day_before = today - timedelta(days=2)

    try:
        yesterday_cost = _get_daily_cost(yesterday, today)
        day_before_cost = _get_daily_cost(day_before, yesterday)
    except Exception:
        logger.exception("Failed to retrieve Cost Explorer data")
        raise

    delta = yesterday_cost - day_before_cost
    delta_sign = "+" if delta >= 0 else ""

    message = (
        f"Engram Daily Cost Report ({yesterday.isoformat()})\n"
        f"Current Cost: ${yesterday_cost:.2f}\n"
        f"Cost increase since last report: {delta_sign}${delta:.2f}"
    )

    logger.info(
        "Publishing cost report",
        extra={
            "yesterday_cost": yesterday_cost,
            "day_before_cost": day_before_cost,
            "delta": delta,
        },
    )

    _sns_client.publish(
        TopicArn=_SNS_TOPIC_ARN,
        Subject=f"Engram Daily Cost Report -- {yesterday.isoformat()}",
        Message=message,
    )

    return {"statusCode": 200, "body": json.dumps({"published": True, "cost": yesterday_cost})}
