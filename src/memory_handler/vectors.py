# Copyright (c) 2026 Engram Contributors. All Rights Reserved.
# Licensed under the MIT License. See LICENSE for details.
from __future__ import annotations

import logging
from dataclasses import dataclass

logger = logging.getLogger(__name__)

_MEMORIES_PREFIX = "memories"


@dataclass(frozen=True)
class VectorResult:
    key: str
    score: float
    metadata: dict[str, str]


def memory_key(memory_id: str) -> str:
    """Build the flat S3 key for a memory."""
    return f"{_MEMORIES_PREFIX}/{memory_id}"


def parse_tags(metadata: dict[str, str]) -> list[str]:
    """Extract tags list from metadata. Handles missing or empty tags field."""
    raw = metadata.get("tags", "")
    return [t.strip() for t in raw.split(",") if t.strip()] if raw else []


def apply_weights(
    results: list[VectorResult],
    weights: dict[str, float],
) -> list[tuple[VectorResult, float]]:
    """Re-rank results by multiplying base relevance by matching tag weight multipliers.

    Base relevance: 1.0 - (cosine_distance / 2), range 0-1.
    For each matching tag in weights, multiply the base score by that weight.
    Vectors missing a tag get no multiplier (neutral 1.0) for that weight.
    Returns (result, weighted_relevance_score) pairs sorted descending.
    """
    scored: list[tuple[float, VectorResult]] = []
    for r in results:
        tags = set(parse_tags(r.metadata))
        base = 1.0 - (r.score / 2.0)
        multiplier = 1.0
        for tag, w in weights.items():
            if tag in tags:
                multiplier *= w
        scored.append((base * multiplier, r))
    scored.sort(key=lambda x: x[0], reverse=True)
    return [(r, s) for s, r in scored]


def put_vector(
    bucket: str,
    index_name: str,
    key: str,
    vector: list[float],
    metadata: dict[str, str],
    s3vectors_client: object,
) -> None:
    """Insert a vector with metadata into the S3 Vector Table."""
    s3vectors_client.put_vectors(  # type: ignore[union-attr]
        vectorBucketName=bucket,
        indexName=index_name,
        vectors=[{
            "key": key,
            "data": {"float32": vector},
            "metadata": metadata,
        }],
    )


def query_vectors(
    bucket: str,
    index_name: str,
    query_vector: list[float],
    top_k: int,
    s3vectors_client: object,
    filter_expression: dict | None = None,
) -> list[VectorResult]:
    """Query the S3 Vector Table for nearest neighbors."""
    kwargs: dict = {
        "vectorBucketName": bucket,
        "indexName": index_name,
        "queryVector": {"float32": query_vector},
        "topK": top_k,
        "returnMetadata": True,
        "returnDistance": True,
    }
    if filter_expression:
        kwargs["filter"] = filter_expression

    response = s3vectors_client.query_vectors(**kwargs)  # type: ignore[union-attr]

    return [
        VectorResult(
            key=v["key"],
            score=v.get("distance", 0.0),
            metadata=v.get("metadata", {}),
        )
        for v in response.get("vectors", [])
    ]


def list_vectors(
    bucket: str,
    index_name: str,
    s3vectors_client: object,
    key_prefix: str | None = None,
) -> list[VectorResult]:
    """List all vectors in the index, optionally filtered by key prefix.

    Uses the S3 Vectors ListVectors paginated API. Does not require a query
    vector — suitable for bulk operations like summarization and pruning.
    """
    results: list[VectorResult] = []
    next_token: str | None = None

    while True:
        kwargs: dict = {
            "vectorBucketName": bucket,
            "indexName": index_name,
            "returnMetadata": True,
        }
        if next_token:
            kwargs["nextToken"] = next_token

        response = s3vectors_client.list_vectors(**kwargs)  # type: ignore[union-attr]

        for v in response.get("vectors", []):
            key: str = v["key"]
            if key_prefix and not key.startswith(key_prefix):
                continue
            results.append(VectorResult(
                key=key,
                score=0.0,
                metadata=v.get("metadata", {}),
            ))

        next_token = response.get("nextToken")
        if not next_token:
            break

    return results


def delete_vectors(
    bucket: str,
    index_name: str,
    keys: list[str],
    s3vectors_client: object,
) -> None:
    """Delete vectors by key from the S3 Vector Table."""
    s3vectors_client.delete_vectors(  # type: ignore[union-attr]
        vectorBucketName=bucket,
        indexName=index_name,
        keys=keys,
    )
