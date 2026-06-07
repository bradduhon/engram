#!/usr/bin/env python3
# Copyright (c) 2026 Engram Contributors. All Rights Reserved.
# Licensed under the MIT License. See LICENSE for details.
"""Migrate prefix-based vector keys to flat key structure with tag injection.

Transforms:
    global/memories/{uuid}              -> memories/{uuid}     tags: ["scope:global"]
    project/{id}/memories/{uuid}        -> memories/{uuid}     tags: ["scope:project", "project:{id}"]
    global/memories/summary-{uuid}      -> memories/summary-{uuid}  tags: ["scope:global"]
    project/{id}/memories/summary-{id} -> memories/summary-{uuid}  tags: ["scope:project", "project:{id}"]

Also injects memory_type and other existing metadata fields as tags where applicable.
Skips keys already in flat format (memories/{uuid}).

Usage:
    # Step 1: backup first (always)
    python scripts/backup_vectors.py --output engram_backup_premigration.json

    # Step 2: dry run to preview
    python scripts/migrate_to_flat_keys.py --dry-run

    # Step 3: execute
    python scripts/migrate_to_flat_keys.py

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
import re

import boto3

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)

_PUT_BATCH = 500
_EMBED_MODEL = "amazon.titan-embed-text-v2:0"

# Matches: global/memories/{uuid-or-summary-uuid}
_GLOBAL_RE = re.compile(r"^global/memories/(.+)$")
# Matches: project/{project_id}/memories/{uuid-or-summary-uuid}
_PROJECT_RE = re.compile(r"^project/([^/]+)/memories/(.+)$")
# Already flat
_FLAT_RE = re.compile(r"^memories/(.+)$")


def _derive_tags(old_key: str, metadata: dict[str, str]) -> list[str] | None:
    """Return the tag list for this key, or None if already migrated (flat key)."""
    if _FLAT_RE.match(old_key):
        return None  # already migrated

    tags: list[str] = []

    m = _GLOBAL_RE.match(old_key)
    if m:
        tags.append("scope:global")

    m = _PROJECT_RE.match(old_key)
    if m:
        project_id = m.group(1)
        tags.extend(["scope:project", f"project:{project_id}"])

    # Carry forward memory_type as a tag if present
    mem_type = metadata.get("memory_type", "")
    if mem_type:
        tags.append(f"memory_type:{mem_type}")

    return tags


def _new_key(old_key: str) -> str:
    m = _GLOBAL_RE.match(old_key)
    if m:
        return f"memories/{m.group(1)}"
    m = _PROJECT_RE.match(old_key)
    if m:
        return f"memories/{m.group(2)}"
    return old_key  # already flat, no change


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true",
                        help="Print plan without making changes")
    args = parser.parse_args()

    region = os.environ.get("AWS_REGION", "us-east-1")
    bucket = os.environ["MEMORY_BUCKET"]
    index_name = os.environ.get("VECTOR_INDEX_NAME", "memories")

    client = boto3.client(
        "s3vectors",
        region_name=region,
        endpoint_url=os.environ.get("S3VECTORS_ENDPOINT_URL"),
    )
    bedrock = boto3.client("bedrock-runtime", region_name=region)

    # --- Step 1: list all vectors ---
    logger.info("Listing all vectors ...")
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

    logger.info("Found %d total vectors.", len(all_keys))

    # --- Step 2: classify ---
    to_migrate: list[str] = []
    already_flat: list[str] = []
    for key in all_keys:
        if _FLAT_RE.match(key):
            already_flat.append(key)
        else:
            to_migrate.append(key)

    logger.info("%d already flat (skip), %d to migrate.", len(already_flat), len(to_migrate))

    if not to_migrate:
        logger.info("Nothing to do.")
        return

    if args.dry_run:
        for key in to_migrate:
            meta = all_metadata[key]
            new_k = _new_key(key)
            tags = _derive_tags(key, meta)
            logger.info("  %s -> %s  tags=%s", key, new_k, tags)
        logger.info("Dry run complete. %d vectors would be migrated.", len(to_migrate))
        return

    # --- Step 3: re-embed text via Bedrock (S3 Vectors does not expose raw float values) ---
    logger.info("Re-embedding %d vectors via Bedrock Titan Embed v2 ...", len(to_migrate))
    key_to_vector: dict[str, list[float]] = {}
    for i, key in enumerate(to_migrate, 1):
        text = all_metadata[key].get("text", "")
        if not text:
            logger.warning("  [%d/%d] No text in metadata for %s -- skipping", i, len(to_migrate), key)
            continue
        resp = bedrock.invoke_model(
            modelId=_EMBED_MODEL,
            body=json.dumps({"inputText": text, "dimensions": 1024, "normalize": True}),
        )
        body = json.loads(resp["body"].read())
        key_to_vector[key] = body["embedding"]
        if i % 10 == 0 or i == len(to_migrate):
            logger.info("  embedded %d/%d", i, len(to_migrate))

    # --- Step 4: put at new keys ---
    logger.info("Writing %d vectors at new flat keys ...", len(to_migrate))
    new_payloads: list[dict] = []
    old_keys_for_deletion: list[str] = []

    for old_key in to_migrate:
        vec = key_to_vector.get(old_key)
        if not vec:
            logger.warning("No embedding retrieved for %s -- skipping", old_key)
            continue

        meta = dict(all_metadata[old_key])  # copy
        tags = _derive_tags(old_key, meta)
        meta["tags"] = ",".join(tags) if tags else ""

        new_payloads.append({
            "key": _new_key(old_key),
            "data": {"float32": vec},
            "metadata": meta,
        })
        old_keys_for_deletion.append(old_key)

    for i in range(0, len(new_payloads), _PUT_BATCH):
        batch = new_payloads[i : i + _PUT_BATCH]
        client.put_vectors(
            vectorBucketName=bucket,
            indexName=index_name,
            vectors=batch,
        )
        logger.info("  put %d/%d", min(i + _PUT_BATCH, len(new_payloads)), len(new_payloads))

    # --- Step 5: delete old keys ---
    logger.info("Deleting %d old-format keys ...", len(old_keys_for_deletion))
    for i in range(0, len(old_keys_for_deletion), _PUT_BATCH):
        batch = old_keys_for_deletion[i : i + _PUT_BATCH]
        client.delete_vectors(
            vectorBucketName=bucket,
            indexName=index_name,
            keys=batch,
        )
        logger.info("  deleted %d/%d", min(i + _PUT_BATCH, len(old_keys_for_deletion)), len(old_keys_for_deletion))

    logger.info("Migration complete: %d vectors migrated.", len(old_keys_for_deletion))
    logger.info("Verify with: python scripts/migrate_to_flat_keys.py --dry-run (should show 0 to migrate)")


if __name__ == "__main__":
    main()
