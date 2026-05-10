# Copyright (c) 2026 Engram Contributors. All Rights Reserved.
# Licensed under the MIT License. See LICENSE for details.
from __future__ import annotations

import os
import re

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
_sm_client = boto3.client("secretsmanager", region_name=_region)
_config = Config.from_env()

# Cached trusted cert PEM -- loaded once per Lambda container lifetime.
_trusted_cert_pem: str | None = None


def _get_trusted_cert_pem() -> str:
    """Fetch and cache the trusted client cert PEM from Secrets Manager.

    The bundle stored at CLIENT_CERT_SECRET_ID is: leaf cert + chain + encrypted key.
    We extract only the first PEM certificate block (the leaf cert) for comparison.
    """
    global _trusted_cert_pem
    if _trusted_cert_pem is None:
        secret = _sm_client.get_secret_value(SecretId=_config.client_cert_secret_id)
        bundle: str = secret["SecretString"]
        match = re.search(r"(-----BEGIN CERTIFICATE-----.*?-----END CERTIFICATE-----)", bundle, re.DOTALL)
        if not match:
            raise ValueError("No certificate found in client cert secret bundle")
        _trusted_cert_pem = match.group(1).strip()
    return _trusted_cert_pem


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


_FORBIDDEN: dict = {
    "statusCode": 403,
    "headers": {"Content-Type": "application/json"},
    "body": '{"message":"Forbidden"}',
}


def _assert_mtls_cert(event: dict) -> dict | None:
    """Return a 403 response dict if the presented client cert does not exactly match
    the trusted cert stored in Secrets Manager, else None.

    API Gateway HTTP API (payload format 2.0) passes the client cert PEM in
    event["requestContext"]["authentication"]["clientCert"]["clientCertPem"].
    We compare it byte-for-byte against the leaf cert extracted from the bundle
    in Secrets Manager, providing direct certificate pinning that ensures only
    the exact ACM cert exported for this deployment is accepted -- even though
    the truststore trusts any cert signed by the Amazon RSA 2048 M04 CA.
    """
    try:
        auth_ctx = (event.get("requestContext") or {}).get("authentication") or {}
        client_cert = auth_ctx.get("clientCert") or {}
        presented_pem = (client_cert.get("clientCertPem") or "").strip()
    except Exception:
        logger.exception("Failed to extract client cert from requestContext")
        return _FORBIDDEN

    if not presented_pem:
        logger.warning("mTLS clientCert missing from requestContext")
        return _FORBIDDEN

    try:
        trusted_pem = _get_trusted_cert_pem()
    except Exception:
        logger.exception("Failed to load trusted cert from Secrets Manager")
        return _FORBIDDEN

    if presented_pem != trusted_pem:
        logger.warning("mTLS cert mismatch: presented cert does not match trusted cert")
        return _FORBIDDEN

    return None


@tracer.capture_lambda_handler
@logger.inject_lambda_context(log_event=False)
def handler(event: dict, context: LambdaContext) -> dict:
    """Lambda entry point. Routes POST /store, /recall, /summarize via Powertools resolver."""
    rejection = _assert_mtls_cert(event)
    if rejection is not None:
        return rejection
    return app.resolve(event, context)
