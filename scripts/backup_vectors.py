#!/usr/bin/env python3
# Copyright (c) 2026 Engram Contributors. All Rights Reserved.
# Licensed under the MIT License. See LICENSE for details.
"""Full vector backup: dumps all keys, metadata, and float32 embeddings to JSON.

Usage:
    python scripts/backup_vectors.py [--output backup_TIMESTAMP.json]

Env vars required:
    MEMORY_BUCKET        S3 Vectors bucket name
    VECTOR_INDEX_NAME    Index name (default: memories)
    AWS_REGION           (default: us-east-1)
"""
from __future__ import annotations

import argparse
import json
import logging
import os
import time

import boto3

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--output",
        default=f"engram_backup_{time.strftime('%Y%m%dT%H%M%SZ', time.gmtime())}.json",
    )
    args = parser.parse_args()

    region = os.environ.get("AWS_REGION", "us-east-1")
    bucket = os.environ["MEMORY_BUCKET"]
    index_name = os.environ.get("VECTOR_INDEX_NAME", "memories")

    client = boto3.client(
        "s3vectors",
        region_name=region,
        endpoint_url=os.environ.get("S3VECTORS_ENDPOINT_URL"),
    )

    # --- Step 1: list all keys + metadata ---
    logger.info("Listing all vectors in %s/%s ...", bucket, index_name)
    all_keys: list[str] = []
    all_metadata: dict[str, dict] = {}
    next_token: str | None = None

    while True:
        kwargs: dict = {
            "vectorBucketName": bucket,
            "indexName": index_name,
            "returnMetadata": True,
        }
        if next_token:
            kwargs["nextToken"] = next_token
        resp = client.list_vectors(**kwargs)
        for v in resp.get("vectors", []):
            all_keys.append(v["key"])
            all_metadata[v["key"]] = v.get("metadata", {})
        next_token = resp.get("nextToken")
        if not next_token:
            break

    logger.info("Found %d vectors. Fetching embeddings in batches of 100 ...", len(all_keys))

    # --- Step 2: get_vectors in batches to retrieve float32 embeddings ---
    records: list[dict] = []
    batch_size = 100  # S3 Vectors GetVectors limit
    for i in range(0, len(all_keys), batch_size):
        batch = all_keys[i : i + batch_size]
        resp = client.get_vectors(
            vectorBucketName=bucket,
            indexName=index_name,
            keys=batch,
            returnMetadata=True,
        )
        for v in resp.get("vectors", []):
            key = v["key"]
            records.append({
                "key": key,
                "metadata": all_metadata.get(key, v.get("metadata", {})),
                "vector": v.get("data", {}).get("float32", []),
            })
        logger.info("  fetched %d/%d", min(i + batch_size, len(all_keys)), len(all_keys))

    with open(args.output, "w") as f:
        json.dump(records, f, indent=2)

    logger.info("Backup complete: %d records written to %s", len(records), args.output)


if __name__ == "__main__":
    main()
