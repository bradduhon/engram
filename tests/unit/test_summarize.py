# Copyright (c) 2026 Engram Contributors. All Rights Reserved.
# Licensed under the MIT License. See LICENSE for details.
from __future__ import annotations

import json
from io import BytesIO
from unittest.mock import MagicMock

from config import Config
from models import SummarizeRequest, SummarizeResponse
from summarize import handle_summarize
from vectors import VectorResult

_CONFIG = Config(
    memory_bucket="test-bucket",
    vector_index_name="memories",
    embed_model_id="amazon.titan-embed-text-v2:0",
    haiku_model_id="anthropic.claude-haiku-4-5-20251001-v1:0",
    aws_region="us-east-1",
    client_cert_secret_id="engram/mcp-client-cert",
)


def _bedrock_client(summary_text: str = "Compressed summary.") -> MagicMock:
    client = MagicMock()

    def _invoke_model(modelId: str, body: str) -> dict:
        if "titan" in modelId.lower() or "embed" in modelId.lower():
            return {"body": BytesIO(json.dumps({"embedding": [0.1] * 1024}).encode())}
        return {
            "body": BytesIO(json.dumps({
                "content": [{"text": summary_text}]
            }).encode())
        }

    client.invoke_model.side_effect = _invoke_model
    return client


def _s3vectors_with_memories(memories: list[VectorResult]) -> MagicMock:
    client = MagicMock()
    client.list_vectors.return_value = {
        "vectors": [
            {"key": m.key, "metadata": m.metadata}
            for m in memories
        ]
    }
    client.put_vectors.return_value = {}
    client.delete_vectors.return_value = {}
    return client


_MEMORIES = [
    VectorResult(
        key="memories/id1",
        score=0.9,
        metadata={"text": "memory one", "tags": "scope:global", "type": "memory", "created_at": ""},
    ),
    VectorResult(
        key="memories/id2",
        score=0.8,
        metadata={"text": "memory two", "tags": "scope:global", "type": "memory", "created_at": ""},
    ),
]


class TestHandleSummarize:
    def test_handle_summarize_returns_summary_response(self) -> None:
        s3v = _s3vectors_with_memories(_MEMORIES)
        req = SummarizeRequest()
        result = handle_summarize(req, _CONFIG, _bedrock_client(), s3v)

        assert isinstance(result, SummarizeResponse)
        assert result.pruned_count == 2
        assert result.summary_id != ""

    def test_handle_summarize_no_memories_returns_empty(self) -> None:
        s3v = _s3vectors_with_memories([])
        req = SummarizeRequest()
        result = handle_summarize(req, _CONFIG, _bedrock_client(), s3v)

        assert result.pruned_count == 0
        assert result.summary_id == ""
        assert result.summary_token_count == 0

    def test_handle_summarize_skips_existing_summaries(self) -> None:
        memories_with_summary = _MEMORIES + [
            VectorResult(
                key="memories/summary-xyz",
                score=0.7,
                metadata={"text": "old summary", "tags": "scope:global", "type": "summary", "created_at": ""},
            )
        ]
        s3v = _s3vectors_with_memories(memories_with_summary)
        req = SummarizeRequest()
        result = handle_summarize(req, _CONFIG, _bedrock_client(), s3v)

        assert result.pruned_count == 2

    def test_handle_summarize_delete_originals_calls_delete_vectors(self) -> None:
        s3v = _s3vectors_with_memories(_MEMORIES)
        req = SummarizeRequest(delete_originals=True)
        handle_summarize(req, _CONFIG, _bedrock_client(), s3v)

        s3v.delete_vectors.assert_called_once()
        call_kwargs = s3v.delete_vectors.call_args.kwargs
        assert set(call_kwargs["keys"]) == {"memories/id1", "memories/id2"}

    def test_handle_summarize_no_delete_without_flag(self) -> None:
        s3v = _s3vectors_with_memories(_MEMORIES)
        req = SummarizeRequest(delete_originals=False)
        handle_summarize(req, _CONFIG, _bedrock_client(), s3v)

        s3v.delete_vectors.assert_not_called()

    def test_handle_summarize_summary_token_count_matches_word_count(self) -> None:
        summary_text = "one two three"
        s3v = _s3vectors_with_memories(_MEMORIES)
        req = SummarizeRequest()
        result = handle_summarize(req, _CONFIG, _bedrock_client(summary_text), s3v)

        assert result.summary_token_count == 3

    def test_handle_summarize_tag_filter_limits_scope(self) -> None:
        mixed = [
            VectorResult(
                key="memories/global-id",
                score=0.9,
                metadata={"text": "global memory", "tags": "scope:global", "type": "memory", "created_at": ""},
            ),
            VectorResult(
                key="memories/proj-id",
                score=0.8,
                metadata={"text": "project memory", "tags": "scope:project,project:proj-1", "type": "memory", "created_at": ""},
            ),
        ]
        s3v = _s3vectors_with_memories(mixed)
        req = SummarizeRequest(tag_filter=["scope:project", "project:proj-1"])
        result = handle_summarize(req, _CONFIG, _bedrock_client(), s3v)

        assert result.pruned_count == 1

    def test_handle_summarize_summary_stored_at_flat_key(self) -> None:
        s3v = _s3vectors_with_memories(_MEMORIES)
        req = SummarizeRequest()
        handle_summarize(req, _CONFIG, _bedrock_client(), s3v)

        call_kwargs = s3v.put_vectors.call_args.kwargs
        key = call_kwargs["vectors"][0]["key"]
        assert key.startswith("memories/summary-")
