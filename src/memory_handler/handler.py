# Copyright (c) 2026 Brad Duhon. All Rights Reserved.
# Confidential and Proprietary.
# Unauthorized copying of this file is strictly prohibited.
from __future__ import annotations

import os

import boto3
from aws_lambda_powertools import Logger, Tracer
from aws_lambda_powertools.event_handler import APIGatewayHttpResolver
from aws_lambda_powertools.utilities.typing import LambdaContext

from config import Config
from models import RecallRequest, StoreRequest, SummarizeRequest
from recall import handle_recall
from store import handle_store
from summarize import handle_summarize

logger = Logger()
tracer = Tracer()
app = APIGatewayHttpResolver()

_region = os.environ.get("AWS_REGION", "us-east-1")
_bedrock_client = boto3.client("bedrock-runtime", region_name=_region)
_s3vectors_client = boto3.client(
    "s3vectors",
    region_name=_region,
    endpoint_url=os.environ.get("S3VECTORS_ENDPOINT_URL"),
)
_config = Config.from_env()


@app.post("/store")
def store_memory() -> dict:
    body = app.current_event.json_body
    result = handle_store(StoreRequest(**body), _config, _bedrock_client, _s3vectors_client)
    return result.model_dump()


@app.post("/recall")
def recall_memory() -> dict:
    body = app.current_event.json_body
    result = handle_recall(RecallRequest(**body), _config, _bedrock_client, _s3vectors_client)
    return result.model_dump()


@app.post("/summarize")
def summarize_memories() -> dict:
    body = app.current_event.json_body
    result = handle_summarize(SummarizeRequest(**body), _config, _bedrock_client, _s3vectors_client)
    return result.model_dump()


@tracer.capture_lambda_handler
@logger.inject_lambda_context(log_event=False)
def handler(event: dict, context: LambdaContext) -> dict:
    """Lambda entry point. Routes POST /store, /recall, /summarize via Powertools resolver."""
    return app.resolve(event, context)
