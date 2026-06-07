# Copyright (c) 2026 Engram Contributors. All Rights Reserved.
# Licensed under the MIT License. See LICENSE for details.
from __future__ import annotations

import logging
import time

from config import Config
from embeddings import get_embedding
from models import MemoryResult, RecallRequest, RecallResponse
from vectors import query_vectors

logger = logging.getLogger(__name__)


def _build_filter(scope_filter: str | None, project_id: str | None) -> dict | None:
    """Build an S3 Vectors metadata filter from recall scope parameters."""
    if scope_filter == "global":
        return {"equals": {"key": "scope", "value": "global"}}
    if scope_filter == "project" or project_id:
        conditions: list[dict] = [{"equals": {"key": "scope", "value": "project"}}]
        if project_id:
            conditions.append({"equals": {"key": "project_id", "value": project_id}})
        return {"and": conditions} if len(conditions) > 1 else conditions[0]
    return None


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
        filter_expression=_build_filter(body.scope_filter, body.project_id),
    )

    memories = [
        MemoryResult(
            id=r.key.split("/")[-1],
            text=r.metadata.get("text", ""),
            score=r.score,
            relevance_score=round(1.0 - (r.score / 2.0), 4),
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
