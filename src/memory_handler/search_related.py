# Copyright (c) 2026 Brad Duhon. All Rights Reserved.
# Confidential and Proprietary.
# Unauthorized copying of this file is strictly prohibited.
from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone

from models import MemoryResult, SearchRelatedRequest, SearchRelatedResponse
from vectors import VectorResult, build_key_prefix, list_vectors

logger = logging.getLogger(__name__)

_TS_FORMAT = "%Y-%m-%dT%H:%M:%SZ"


def _parse_ts(ts: str) -> datetime | None:
    try:
        return datetime.strptime(ts, _TS_FORMAT).replace(tzinfo=timezone.utc)
    except ValueError:
        return None


def handle_search_related(
    body: SearchRelatedRequest,
    config: object,
    s3vectors_client: object,
) -> SearchRelatedResponse:
    """Return memories stored within window_minutes of the anchor memory."""
    from config import Config  # local import to satisfy type checker

    cfg: Config = config  # type: ignore[assignment]

    prefix = build_key_prefix(body.scope, body.project_id)
    all_vectors: list[VectorResult] = list_vectors(
        bucket=cfg.memory_bucket,
        index_name=cfg.vector_index_name,
        s3vectors_client=s3vectors_client,
        key_prefix=prefix,
    )

    anchor_ts: datetime | None = None
    for v in all_vectors:
        if v.key.split("/")[-1] == body.memory_id:
            anchor_ts = _parse_ts(v.metadata.get("created_at", ""))
            break

    if anchor_ts is None:
        logger.warning("Anchor memory %s not found in prefix %s", body.memory_id, prefix)
        return SearchRelatedResponse(anchor_id=body.memory_id, neighbors=[], total=0)

    delta = timedelta(minutes=body.window_minutes)
    low = anchor_ts - delta
    high = anchor_ts + delta

    neighbors: list[MemoryResult] = []
    for v in all_vectors:
        vid = v.key.split("/")[-1]
        if vid == body.memory_id:
            continue
        vts = _parse_ts(v.metadata.get("created_at", ""))
        if vts and low <= vts <= high:
            neighbors.append(
                MemoryResult(
                    id=vid,
                    text=v.metadata.get("text", ""),
                    score=0.0,
                    relevance_score=0.0,
                    scope=v.metadata.get("scope", body.scope),
                    created_at=v.metadata.get("created_at", ""),
                    type=v.metadata.get("type", "memory"),
                )
            )

    neighbors.sort(key=lambda m: m.created_at)
    logger.info("search_related anchor=%s window=%dm neighbors=%d", body.memory_id, body.window_minutes, len(neighbors))

    return SearchRelatedResponse(anchor_id=body.memory_id, neighbors=neighbors, total=len(neighbors))
