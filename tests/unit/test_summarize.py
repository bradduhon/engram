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
        # Haiku response
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


_GLOBAL_MEMORIES = [
    VectorResult(
        key="global/memories/id1",
        score=0.9,
        metadata={"text": "memory one", "scope": "global", "type": "memory", "created_at": ""},
    ),
    VectorResult(
        key="global/memories/id2",
        score=0.8,
        metadata={"text": "memory two", "scope": "global", "type": "memory", "created_at": ""},
    ),
]


class TestHandleSummarize:
    def test_handle_summarize_returns_summary_response(self) -> None:
        s3v = _s3vectors_with_memories(_GLOBAL_MEMORIES)
        req = SummarizeRequest(scope="global")
        result = handle_summarize(req, _CONFIG, _bedrock_client(), s3v)

        assert isinstance(result, SummarizeResponse)
        assert result.pruned_count == 2
        assert result.scope == "global"
        assert result.summary_id != ""

    def test_handle_summarize_no_memories_returns_empty(self) -> None:
        s3v = _s3vectors_with_memories([])
        req = SummarizeRequest(scope="global")
        result = handle_summarize(req, _CONFIG, _bedrock_client(), s3v)

        assert result.pruned_count == 0
        assert result.summary_id == ""
        assert result.summary_token_count == 0

    def test_handle_summarize_skips_existing_summaries(self) -> None:
        memories_with_summary = _GLOBAL_MEMORIES + [
            VectorResult(
                key="global/memories/summary-xyz",
                score=0.7,
                metadata={"text": "old summary", "scope": "global", "type": "summary", "created_at": ""},
            )
        ]
        s3v = _s3vectors_with_memories(memories_with_summary)
        req = SummarizeRequest(scope="global")
        result = handle_summarize(req, _CONFIG, _bedrock_client(), s3v)

        # Only the 2 "memory" type entries are summarized, not the existing summary
        assert result.pruned_count == 2

    def test_handle_summarize_delete_originals_calls_delete_vectors(self) -> None:
        s3v = _s3vectors_with_memories(_GLOBAL_MEMORIES)
        req = SummarizeRequest(scope="global", delete_originals=True)
        handle_summarize(req, _CONFIG, _bedrock_client(), s3v)

        s3v.delete_vectors.assert_called_once()
        call_kwargs = s3v.delete_vectors.call_args.kwargs
        assert set(call_kwargs["keys"]) == {"global/memories/id1", "global/memories/id2"}

    def test_handle_summarize_no_delete_without_flag(self) -> None:
        s3v = _s3vectors_with_memories(_GLOBAL_MEMORIES)
        req = SummarizeRequest(scope="global", delete_originals=False)
        handle_summarize(req, _CONFIG, _bedrock_client(), s3v)

        s3v.delete_vectors.assert_not_called()

    def test_handle_summarize_summary_token_count_matches_word_count(self) -> None:
        summary_text = "one two three"
        s3v = _s3vectors_with_memories(_GLOBAL_MEMORIES)
        req = SummarizeRequest(scope="global")
        result = handle_summarize(req, _CONFIG, _bedrock_client(summary_text), s3v)

        assert result.summary_token_count == 3

    def test_handle_summarize_project_scope_filters_by_prefix(self) -> None:
        project_memories = [
            VectorResult(
                key="project/proj-1/memories/id3",
                score=0.9,
                metadata={"text": "proj memory", "scope": "project", "type": "memory", "created_at": ""},
            )
        ]
        s3v = _s3vectors_with_memories(project_memories)
        req = SummarizeRequest(scope="project", project_id="proj-1")
        result = handle_summarize(req, _CONFIG, _bedrock_client(), s3v)

        assert result.pruned_count == 1
