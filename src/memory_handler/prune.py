# Copyright (c) 2026 Engram Contributors. All Rights Reserved.
# Licensed under the MIT License. See LICENSE for details.
from __future__ import annotations

import logging
import time
from datetime import datetime, timezone

from config import Config
from models import PruneRequest, PruneResponse
from vectors import delete_vectors, list_vectors, parse_tags

logger = logging.getLogger(__name__)


def handle_prune(
    body: PruneRequest,
    config: Config,
    s3vectors_client: object,
) -> PruneResponse:
    """Delete memories by type and age, optionally scoped to a tag_filter subset.

    Lists all vectors, filters to those whose memory_type is in the requested set
    and whose created_at is older than older_than_days. If tag_filter is provided,
    only memories with ALL matching tags are eligible.

    Existing memories that predate memory_type (no memory_type in metadata)
    are treated as type='context' and are not pruned by default.
    """
    all_vectors = list_vectors(
        bucket=config.memory_bucket,
        index_name=config.vector_index_name,
        s3vectors_client=s3vectors_client,
    )

    cutoff_ts = time.time() - (body.older_than_days * 86400)
    target_types = set(body.memory_types)
    tag_filter_set = set(body.tag_filter)
    candidates: list[str] = []

    for v in all_vectors:
        meta = v.metadata

        # Type filter
        mem_type = meta.get("memory_type", "context")
        if mem_type not in target_types:
            continue

        # Tag filter (all tags must be present)
        if tag_filter_set and not tag_filter_set.issubset(set(parse_tags(meta))):
            continue

        # Age filter
        created_at_str = meta.get("created_at", "")
        try:
            created_ts = datetime.strptime(created_at_str, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc).timestamp()
        except ValueError:
            continue
        if created_ts < cutoff_ts:
            candidates.append(v.key)

    deleted = 0
    if not body.dry_run and candidates:
        for i in range(0, len(candidates), 500):
            batch = candidates[i : i + 500]
            delete_vectors(
                bucket=config.memory_bucket,
                index_name=config.vector_index_name,
                keys=batch,
                s3vectors_client=s3vectors_client,
            )
            deleted += len(batch)
        logger.info(
            "Pruned %d memories (types=%s, tag_filter=%s, older_than_days=%d)",
            deleted, target_types, body.tag_filter, body.older_than_days,
        )
    else:
        deleted = 0
        logger.info(
            "Dry run: %d prune candidates (types=%s, tag_filter=%s)",
            len(candidates), target_types, body.tag_filter,
        )

    memory_ids = [k.split("/")[-1] for k in candidates]
    return PruneResponse(deleted=deleted, dry_run=body.dry_run, candidates=memory_ids)
