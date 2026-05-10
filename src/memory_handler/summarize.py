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
from vectors import build_key_prefix, delete_vectors, list_vectors, put_vector

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
    """List recent memories, compress via Haiku, write summary, optionally delete originals."""
    prefix = build_key_prefix(body.scope, body.project_id)

    results = list_vectors(
        bucket=config.memory_bucket,
        index_name=config.vector_index_name,
        s3vectors_client=s3vectors_client,
        key_prefix=prefix,
    )

    scope_results = [r for r in results if r.metadata.get("type") == "memory"]

    if not scope_results:
        return SummarizeResponse(
            summary_id="",
            pruned_count=0,
            summary_token_count=0,
            scope=body.scope,
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
    summary_key = f"{prefix}/summary-{summary_id}"
    summary_embedding = get_embedding(summary_text, bedrock_client, config.embed_model_id)
    created_at = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())

    put_vector(
        bucket=config.memory_bucket,
        index_name=config.vector_index_name,
        key=summary_key,
        vector=summary_embedding,
        metadata={
            "text": summary_text,
            "scope": body.scope,
            "project_id": body.project_id or "",
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

    logger.info("Created summary %s from %d memories", summary_id, len(scope_results))

    return SummarizeResponse(
        summary_id=summary_id,
        pruned_count=len(scope_results),
        summary_token_count=summary_token_count,
        scope=body.scope,
    )
