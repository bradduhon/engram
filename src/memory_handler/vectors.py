# Copyright (c) 2026 Brad Duhon. All Rights Reserved.
# Confidential and Proprietary.
# Unauthorized copying of this file is strictly prohibited.
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
        "bucketName": bucket,
        "indexName": index_name,
        "queryVector": {"float32": query_vector},
        "topK": top_k,
        "returnMetadata": True,
    }
    if filter_expression:
        kwargs["filter"] = filter_expression

    response = s3vectors_client.query_vectors(**kwargs)  # type: ignore[union-attr]

    return [
        VectorResult(
            key=v["key"],
            score=v["score"],
            metadata=v.get("metadata", {}),
        )
        for v in response.get("vectors", [])
    ]


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
