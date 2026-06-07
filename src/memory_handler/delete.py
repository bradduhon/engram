# Copyright (c) 2026 Brad Duhon. All Rights Reserved.
# Confidential and Proprietary.
# Unauthorized copying of this file is strictly prohibited.
from __future__ import annotations

import logging

from models import DeleteRequest, DeleteResponse
from vectors import delete_vectors, memory_key

logger = logging.getLogger(__name__)


def handle_delete(
    body: DeleteRequest,
    config: object,
    s3vectors_client: object,
) -> DeleteResponse:
    """Delete a single memory by ID from the vector table."""
    from config import Config  # local import to satisfy type checker

    cfg: Config = config  # type: ignore[assignment]

    key = memory_key(body.memory_id)

    delete_vectors(
        bucket=cfg.memory_bucket,
        index_name=cfg.vector_index_name,
        keys=[key],
        s3vectors_client=s3vectors_client,
    )

    logger.info("Deleted memory %s", body.memory_id)
    return DeleteResponse(deleted=True, id=body.memory_id)
