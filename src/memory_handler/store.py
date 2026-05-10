# Copyright (c) 2026 Engram Contributors. All Rights Reserved.
# Licensed under the MIT License. See LICENSE for details.
from __future__ import annotations

import logging
import time
import uuid

from config import Config
from embeddings import get_embedding
from models import StoreRequest, StoreResponse
from vectors import build_key_prefix, put_vector

logger = logging.getLogger(__name__)


def handle_store(
    body: StoreRequest,
    config: Config,
    bedrock_client: object,
    s3vectors_client: object,
) -> StoreResponse:
    """Embed text and write to vector table."""
    memory_id = str(uuid.uuid4())
    prefix = build_key_prefix(body.scope, body.project_id)
    key = f"{prefix}/{memory_id}"
    token_count = len(body.text.split())

    embedding = get_embedding(body.text, bedrock_client, config.embed_model_id)

    created_at = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())

    metadata = {
        "text": body.text,
        "scope": body.scope,
        "project_id": body.project_id or "",
        "conversation_id": body.conversation_id,
        "trigger": body.trigger,
        "type": "memory",
        "created_at": created_at,
        "token_count": str(token_count),
    }

    put_vector(
        bucket=config.memory_bucket,
        index_name=config.vector_index_name,
        key=key,
        vector=embedding,
        metadata=metadata,
        s3vectors_client=s3vectors_client,
    )

    logger.info("Stored memory %s (scope=%s, trigger=%s)", memory_id, body.scope, body.trigger)

    return StoreResponse(
        stored=True,
        id=memory_id,
        scope=body.scope,
        token_count=token_count,
    )
