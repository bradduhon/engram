# Copyright (c) 2026 Engram Contributors. All Rights Reserved.
# Licensed under the MIT License. See LICENSE for details.
from __future__ import annotations

import json
import logging

logger = logging.getLogger(__name__)

EXPECTED_DIMENSIONS = 1024


def get_embedding(text: str, bedrock_client: object, model_id: str) -> list[float]:
    """Generate a 1024-dimensional embedding vector using Titan Embed v2."""
    response = bedrock_client.invoke_model(  # type: ignore[union-attr]
        modelId=model_id,
        body=json.dumps({
            "inputText": text,
            "dimensions": EXPECTED_DIMENSIONS,
            "normalize": True,
        }),
    )
    result = json.loads(response["body"].read())
    embedding: list[float] = result["embedding"]

    assert len(embedding) == EXPECTED_DIMENSIONS, (
        f"Expected {EXPECTED_DIMENSIONS} dimensions, got {len(embedding)}"
    )

    return embedding
