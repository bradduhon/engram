# Copyright (c) 2026 Engram Contributors. All Rights Reserved.
# Licensed under the MIT License. See LICENSE for details.
from __future__ import annotations

import logging
import time
import uuid

from config import Config
from embeddings import get_embedding
from models import StoreRequest, StoreResponse
from vectors import memory_key, put_vector

logger = logging.getLogger(__name__)


def handle_store(
    body: StoreRequest,
    config: Config,
    bedrock_client: object,
    s3vectors_client: object,
) -> StoreResponse:
    """Embed text and write to vector table with flat key and tag metadata."""
    memory_id = str(uuid.uuid4())
    key = memory_key(memory_id)
    token_count = len(body.text.split())

    embedding = get_embedding(body.text, bedrock_client, config.embed_model_id)

    created_at = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())

    # Merge memory_type into tags if not already present
    tags = list(body.tags)
    mem_type_tag = f"memory_type:{body.memory_type}"
    if mem_type_tag not in tags:
        tags.append(mem_type_tag)

    metadata = {
        "text": body.text,
        "tags": ",".join(tags),
        "conversation_id": body.conversation_id,
        "trigger": body.trigger,
        "type": "memory",
        "memory_type": body.memory_type,
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

    logger.info("Stored memory %s (tags=%s, trigger=%s)", memory_id, tags, body.trigger)

    return StoreResponse(
        stored=True,
        id=memory_id,
        tags=tags,
        token_count=token_count,
    )
