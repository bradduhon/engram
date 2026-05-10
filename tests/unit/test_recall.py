# Copyright (c) 2026 Engram Contributors. All Rights Reserved.
# Licensed under the MIT License. See LICENSE for details.
from __future__ import annotations

import json
from io import BytesIO
from unittest.mock import MagicMock

from config import Config
from models import RecallRequest, RecallResponse
from recall import handle_recall
from vectors import VectorResult

_CONFIG = Config(
    memory_bucket="test-bucket",
    vector_index_name="memories",
    embed_model_id="amazon.titan-embed-text-v2:0",
    haiku_model_id="anthropic.claude-haiku-4-5-20251001-v1:0",
    aws_region="us-east-1",
    client_cert_secret_id="engram/mcp-client-cert",
)


def _bedrock_client() -> MagicMock:
    client = MagicMock()
    client.invoke_model.return_value = {
        "body": BytesIO(json.dumps({"embedding": [0.1] * 1024}).encode())
    }
    return client


def _s3vectors_client(results: list[VectorResult] | None = None) -> MagicMock:
    client = MagicMock()
    raw = [
        {
            "key": r.key,
            "distance": r.score,
            "metadata": r.metadata,
        }
        for r in (results or [])
    ]
    client.query_vectors.return_value = {"vectors": raw}
    return client


class TestHandleRecall:
    def test_handle_recall_returns_recall_response(self) -> None:
        s3v = _s3vectors_client([
            VectorResult(
                key="global/memories/abc",
                score=0.92,
                metadata={"text": "a memory", "scope": "global", "created_at": "2026-01-01T00:00:00Z", "type": "memory"},
            )
        ])
        req = RecallRequest(query="find something")
        result = handle_recall(req, _CONFIG, _bedrock_client(), s3v)

        assert isinstance(result, RecallResponse)
        assert result.total == 1
        assert result.memories[0].text == "a memory"
        assert result.memories[0].score == 0.92

    def test_handle_recall_empty_results(self) -> None:
        s3v = _s3vectors_client([])
        req = RecallRequest(query="nothing here")
        result = handle_recall(req, _CONFIG, _bedrock_client(), s3v)

        assert result.total == 0
        assert result.memories == []

    def test_handle_recall_memory_id_extracted_from_key(self) -> None:
        memory_id = "550e8400-e29b-41d4-a716-446655440000"
        s3v = _s3vectors_client([
            VectorResult(
                key=f"global/memories/{memory_id}",
                score=0.8,
                metadata={"text": "x", "scope": "global", "created_at": "", "type": "memory"},
            )
        ])
        req = RecallRequest(query="q")
        result = handle_recall(req, _CONFIG, _bedrock_client(), s3v)

        assert result.memories[0].id == memory_id

    def test_handle_recall_uses_top_k(self) -> None:
        s3v = _s3vectors_client([])
        req = RecallRequest(query="q", top_k=3)
        handle_recall(req, _CONFIG, _bedrock_client(), s3v)

        call_kwargs = s3v.query_vectors.call_args.kwargs
        assert call_kwargs["topK"] == 3

    def test_handle_recall_query_ms_is_nonnegative(self) -> None:
        s3v = _s3vectors_client([])
        result = handle_recall(RecallRequest(query="q"), _CONFIG, _bedrock_client(), s3v)
        assert result.query_ms >= 0
