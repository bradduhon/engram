# Copyright (c) 2026 Brad Duhon. All Rights Reserved.
# Confidential and Proprietary.
# Unauthorized copying of this file is strictly prohibited.
from __future__ import annotations

import logging
import time

from config import Config
from embeddings import get_embedding
from models import MemoryResult, RecallRequest, RecallResponse
from vectors import query_vectors

logger = logging.getLogger(__name__)


def handle_recall(
    body: RecallRequest,
    config: Config,
    bedrock_client: object,
    s3vectors_client: object,
) -> RecallResponse:
    """Embed query and search vector table for nearest memories."""
    start_ms = int(time.time() * 1000)

    query_embedding = get_embedding(body.query, bedrock_client, config.embed_model_id)

    results = query_vectors(
        bucket=config.memory_bucket,
        index_name=config.vector_index_name,
        query_vector=query_embedding,
        top_k=body.top_k,
        s3vectors_client=s3vectors_client,
    )

    memories = [
        MemoryResult(
            id=r.key.split("/")[-1],
            text=r.metadata.get("text", ""),
            score=r.score,
            scope=r.metadata.get("scope", "global"),
            created_at=r.metadata.get("created_at", ""),
            type=r.metadata.get("type", "memory"),
        )
        for r in results
    ]

    elapsed_ms = int(time.time() * 1000) - start_ms
    logger.info("Recalled %d memories in %dms", len(memories), elapsed_ms)

    return RecallResponse(
        memories=memories,
        total=len(memories),
        query_ms=elapsed_ms,
    )
