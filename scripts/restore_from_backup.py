#!/usr/bin/env python3
# Copyright (c) 2026 Engram Contributors. All Rights Reserved.
# Licensed under the MIT License. See LICENSE for details.
"""Restore all vectors from a backup JSON produced by backup_vectors.py.

Usage:
    python scripts/restore_from_backup.py --input engram_backup_TIMESTAMP.json [--dry-run]

Env vars required:
    MEMORY_BUCKET        S3 Vectors bucket name
    VECTOR_INDEX_NAME    Index name (default: memories)
    AWS_REGION           (default: us-east-1)

WARNING: re-puts all vectors at their original keys. If keys were remapped by the
migration script, this restores the original key names. Intended for disaster recovery
only -- run after a failed migration to return the index to its pre-migration state.
"""
from __future__ import annotations

import argparse
import json
import logging
import os

import boto3

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)

_PUT_BATCH = 500  # S3 Vectors PutVectors limit


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", required=True, help="Backup JSON file path")
    parser.add_argument("--dry-run", action="store_true", help="Print what would be restored without writing")
    args = parser.parse_args()

    with open(args.input) as f:
        records: list[dict] = json.load(f)

    logger.info("Loaded %d records from %s", len(records), args.input)

    if args.dry_run:
        for r in records:
            logger.info("  would restore key=%s metadata_keys=%s vector_len=%d",
                        r["key"], list(r.get("metadata", {}).keys()), len(r.get("vector", [])))
        logger.info("Dry run complete. No writes performed.")
        return

    region = os.environ.get("AWS_REGION", "us-east-1")
    bucket = os.environ["MEMORY_BUCKET"]
    index_name = os.environ.get("VECTOR_INDEX_NAME", "memories")

    client = boto3.client(
        "s3vectors",
        region_name=region,
        endpoint_url=os.environ.get("S3VECTORS_ENDPOINT_URL"),
    )

    restored = 0
    for i in range(0, len(records), _PUT_BATCH):
        batch = records[i : i + _PUT_BATCH]
        vectors_payload = [
            {
                "key": r["key"],
                "data": {"float32": r["vector"]},
                "metadata": r["metadata"],
            }
            for r in batch
            if r.get("vector")  # skip records where embedding retrieval failed
        ]
        if vectors_payload:
            client.put_vectors(
                vectorBucketName=bucket,
                indexName=index_name,
                vectors=vectors_payload,
            )
            restored += len(vectors_payload)
            logger.info("  restored %d/%d", min(i + _PUT_BATCH, len(records)), len(records))

    logger.info("Restore complete: %d vectors written.", restored)


if __name__ == "__main__":
    main()
