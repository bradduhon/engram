# Copyright (c) 2026 Engram Contributors. All Rights Reserved.
# Licensed under the MIT License. See LICENSE for details.
from __future__ import annotations

import json
from io import BytesIO
from unittest.mock import MagicMock

from config import Config
from models import RecallRequest, RecallResponse
from recall import _CANDIDATE_MULTIPLIER, handle_recall
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
                key="memories/abc",
                score=0.92,
                metadata={"text": "a memory", "tags": "scope:global", "created_at": "2026-01-01T00:00:00Z", "type": "memory"},
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
                key=f"memories/{memory_id}",
                score=0.8,
                metadata={"text": "x", "tags": "", "created_at": "", "type": "memory"},
            )
        ])
        req = RecallRequest(query="q")
        result = handle_recall(req, _CONFIG, _bedrock_client(), s3v)

        assert result.memories[0].id == memory_id

    def test_handle_recall_fetches_candidate_multiplier_times_top_k(self) -> None:
        s3v = _s3vectors_client([])
        req = RecallRequest(query="q", top_k=3)
        handle_recall(req, _CONFIG, _bedrock_client(), s3v)

        call_kwargs = s3v.query_vectors.call_args.kwargs
        assert call_kwargs["topK"] == 3 * _CANDIDATE_MULTIPLIER

    def test_handle_recall_caps_candidates_at_500(self) -> None:
        s3v = _s3vectors_client([])
        req = RecallRequest(query="q", top_k=200)
        handle_recall(req, _CONFIG, _bedrock_client(), s3v)

        call_kwargs = s3v.query_vectors.call_args.kwargs
        assert call_kwargs["topK"] == 500

    def test_handle_recall_no_filter_expression_sent(self) -> None:
        """Weighted recall never sends S3 Vectors filter — re-ranking is client-side."""
        s3v = _s3vectors_client([])
        handle_recall(RecallRequest(query="q"), _CONFIG, _bedrock_client(), s3v)
        call_kwargs = s3v.query_vectors.call_args.kwargs
        assert "filter" not in call_kwargs

    def test_handle_recall_tags_returned_in_result(self) -> None:
        s3v = _s3vectors_client([
            VectorResult(
                key="memories/abc",
                score=0.5,
                metadata={"text": "x", "tags": "project:engram,scope:project", "created_at": "", "type": "memory"},
            )
        ])
        result = handle_recall(RecallRequest(query="q"), _CONFIG, _bedrock_client(), s3v)

        assert "project:engram" in result.memories[0].tags
        assert "scope:project" in result.memories[0].tags

    def test_handle_recall_weight_boosts_matching_memory(self) -> None:
        """Memory with matching tag should rank above higher-similarity memory without it."""
        # low_sim has better cosine similarity (lower distance) but no matching tag
        # high_weight has worse similarity but a matching tag with 2x weight
        low_sim = VectorResult(
            key="memories/low-sim",
            score=0.1,  # distance=0.1, base_relevance=0.95
            metadata={"text": "generic", "tags": "scope:global", "created_at": "", "type": "memory"},
        )
        high_weight = VectorResult(
            key="memories/high-weight",
            score=0.5,  # distance=0.5, base_relevance=0.75; with weight 2.0 -> 1.5
            metadata={"text": "project specific", "tags": "project:engram,scope:project", "created_at": "", "type": "memory"},
        )
        s3v = _s3vectors_client([low_sim, high_weight])
        req = RecallRequest(query="q", weights={"project:engram": 2.0}, top_k=2)
        result = handle_recall(req, _CONFIG, _bedrock_client(), s3v)

        assert result.memories[0].id == "high-weight"
        assert result.memories[1].id == "low-sim"

    def test_handle_recall_no_weights_returns_by_base_relevance(self) -> None:
        """Without weights, ordering should follow raw cosine similarity (lower distance = first)."""
        r1 = VectorResult(key="memories/r1", score=0.2, metadata={"text": "a", "tags": "", "created_at": "", "type": "memory"})
        r2 = VectorResult(key="memories/r2", score=0.8, metadata={"text": "b", "tags": "", "created_at": "", "type": "memory"})
        s3v = _s3vectors_client([r1, r2])
        result = handle_recall(RecallRequest(query="q"), _CONFIG, _bedrock_client(), s3v)

        assert result.memories[0].id == "r1"
        assert result.memories[1].id == "r2"

    def test_handle_recall_query_ms_is_nonnegative(self) -> None:
        s3v = _s3vectors_client([])
        result = handle_recall(RecallRequest(query="q"), _CONFIG, _bedrock_client(), s3v)
        assert result.query_ms >= 0
