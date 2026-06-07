# Copyright (c) 2026 Engram Contributors. All Rights Reserved.
# Licensed under the MIT License. See LICENSE for details.
from __future__ import annotations

import logging
import time

from config import Config
from embeddings import get_embedding
from models import MemoryResult, RecallRequest, RecallResponse
from vectors import apply_weights, parse_tags, query_vectors

logger = logging.getLogger(__name__)

# Fetch this many candidates before weight re-ranking. Capped at 500 (S3 Vectors limit).
_CANDIDATE_MULTIPLIER = 5
_MAX_CANDIDATES = 500


def handle_recall(
    body: RecallRequest,
    config: Config,
    bedrock_client: object,
    s3vectors_client: object,
) -> RecallResponse:
    """Embed query, fetch candidates, apply weight re-ranking, return top_k."""
    start_ms = int(time.time() * 1000)

    query_embedding = get_embedding(body.query, bedrock_client, config.embed_model_id)

    fetch_k = min(body.top_k * _CANDIDATE_MULTIPLIER, _MAX_CANDIDATES)
    raw_results = query_vectors(
        bucket=config.memory_bucket,
        index_name=config.vector_index_name,
        query_vector=query_embedding,
        top_k=fetch_k,
        s3vectors_client=s3vectors_client,
    )

    weighted = apply_weights(raw_results, body.weights)[:body.top_k]

    memories = [
        MemoryResult(
            id=r.key.split("/")[-1],
            text=r.metadata.get("text", ""),
            score=r.score,
            relevance_score=round(weighted_score, 4),
            tags=parse_tags(r.metadata),
            created_at=r.metadata.get("created_at", ""),
            type=r.metadata.get("type", "memory"),
        )
        for r, weighted_score in weighted
    ]

    elapsed_ms = int(time.time() * 1000) - start_ms
    logger.info("Recalled %d memories in %dms (weights=%s)", len(memories), elapsed_ms, list(body.weights.keys()))

    return RecallResponse(
        memories=memories,
        total=len(memories),
        query_ms=elapsed_ms,
    )
