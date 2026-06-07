# Copyright (c) 2026 Engram Contributors. All Rights Reserved.
# Licensed under the MIT License. See LICENSE for details.
from __future__ import annotations

import json
import logging
import time
import uuid

from config import Config
from embeddings import get_embedding
from models import SummarizeRequest, SummarizeResponse
from vectors import delete_vectors, list_vectors, parse_tags, put_vector

logger = logging.getLogger(__name__)

SUMMARIZE_PROMPT = """You are a memory compression assistant. Given a list of memory entries,
produce a single concise summary that preserves all important decisions, preferences,
technical context, and action items. Remove redundancy. Output only the summary text."""


def handle_summarize(
    body: SummarizeRequest,
    config: Config,
    bedrock_client: object,
    s3vectors_client: object,
) -> SummarizeResponse:
    """List memories, optionally filtered by tag_filter, compress via Haiku, write summary."""
    all_vectors = list_vectors(
        bucket=config.memory_bucket,
        index_name=config.vector_index_name,
        s3vectors_client=s3vectors_client,
    )

    # Filter to type=memory only; apply tag_filter if specified (all tags must match)
    tag_filter_set = set(body.tag_filter)
    scope_results = [
        r for r in all_vectors
        if r.metadata.get("type") == "memory"
        and (not tag_filter_set or tag_filter_set.issubset(set(parse_tags(r.metadata))))
    ]

    if not scope_results:
        return SummarizeResponse(
            summary_id="",
            pruned_count=0,
            summary_token_count=0,
        )

    memory_texts = [r.metadata.get("text", "") for r in scope_results]
    combined = "\n---\n".join(memory_texts)

    haiku_response = bedrock_client.invoke_model(  # type: ignore[union-attr]
        modelId=config.haiku_model_id,
        body=json.dumps({
            "anthropic_version": "bedrock-2023-05-31",
            "max_tokens": 1024,
            "messages": [
                {"role": "user", "content": f"{SUMMARIZE_PROMPT}\n\nMemories:\n{combined}"}
            ],
        }),
    )

    haiku_result = json.loads(haiku_response["body"].read())
    summary_text: str = haiku_result["content"][0]["text"]
    summary_token_count = len(summary_text.split())

    summary_id = str(uuid.uuid4())
    summary_key = f"memories/summary-{summary_id}"
    summary_embedding = get_embedding(summary_text, bedrock_client, config.embed_model_id)
    created_at = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())

    # Carry forward tag_filter as summary tags so the summary is retrievable by the same filters
    summary_tags = list(body.tag_filter) if body.tag_filter else []

    put_vector(
        bucket=config.memory_bucket,
        index_name=config.vector_index_name,
        key=summary_key,
        vector=summary_embedding,
        metadata={
            "text": summary_text,
            "tags": ",".join(summary_tags),
            "conversation_id": "",
            "trigger": "summarizer",
            "type": "summary",
            "created_at": created_at,
            "token_count": str(summary_token_count),
        },
        s3vectors_client=s3vectors_client,
    )

    if body.delete_originals:
        original_keys = [r.key for r in scope_results]
        delete_vectors(
            bucket=config.memory_bucket,
            index_name=config.vector_index_name,
            keys=original_keys,
            s3vectors_client=s3vectors_client,
        )
        logger.info("Deleted %d original memories after summarization", len(original_keys))

    logger.info("Created summary %s from %d memories (tag_filter=%s)", summary_id, len(scope_results), body.tag_filter)

    return SummarizeResponse(
        summary_id=summary_id,
        pruned_count=len(scope_results),
        summary_token_count=summary_token_count,
    )
