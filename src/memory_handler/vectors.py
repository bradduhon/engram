# Copyright (c) 2026 Engram Contributors. All Rights Reserved.
# Licensed under the MIT License. See LICENSE for details.
from __future__ import annotations

import logging
from dataclasses import dataclass

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class VectorResult:
    key: str
    score: float
    metadata: dict[str, str]


def build_key_prefix(scope: str, project_id: str | None) -> str:
    """Build the S3 key prefix for a memory scope."""
    if scope == "project" and project_id:
        return f"project/{project_id}/memories"
    return "global/memories"


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
    vector, making it suitable for bulk operations like summarization.
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
