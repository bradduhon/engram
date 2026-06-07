# Copyright (c) 2026 Engram Contributors. All Rights Reserved.
# Licensed under the MIT License. See LICENSE for details.
from __future__ import annotations

import json
import re
from io import BytesIO
from unittest.mock import MagicMock

from config import Config
from models import StoreRequest, StoreResponse
from store import handle_store

_CONFIG = Config(
    memory_bucket="test-bucket",
    vector_index_name="memories",
    embed_model_id="amazon.titan-embed-text-v2:0",
    haiku_model_id="anthropic.claude-haiku-4-5-20251001-v1:0",
    aws_region="us-east-1",
    client_cert_secret_id="engram/mcp-client-cert",
)


def _bedrock_client(vector: list[float] | None = None) -> MagicMock:
    v = vector or [0.1] * 1024
    client = MagicMock()
    client.invoke_model.return_value = {
        "body": BytesIO(json.dumps({"embedding": v}).encode())
    }
    return client


def _s3vectors_client() -> MagicMock:
    client = MagicMock()
    client.put_vectors.return_value = {}
    return client


class TestHandleStore:
    def test_handle_store_returns_stored_true(self) -> None:
        req = StoreRequest(text="remember this")
        result = handle_store(req, _CONFIG, _bedrock_client(), _s3vectors_client())

        assert isinstance(result, StoreResponse)
        assert result.stored is True

    def test_handle_store_token_count_matches_word_count(self) -> None:
        req = StoreRequest(text="one two three four")
        result = handle_store(req, _CONFIG, _bedrock_client(), _s3vectors_client())

        assert result.token_count == 4

    def test_handle_store_calls_put_vectors(self) -> None:
        s3v = _s3vectors_client()
        req = StoreRequest(text="test")
        handle_store(req, _CONFIG, _bedrock_client(), s3v)

        s3v.put_vectors.assert_called_once()
        call_kwargs = s3v.put_vectors.call_args.kwargs
        assert call_kwargs["vectorBucketName"] == "test-bucket"
        assert call_kwargs["indexName"] == "memories"

    def test_handle_store_uses_flat_key(self) -> None:
        s3v = _s3vectors_client()
        req = StoreRequest(text="test")
        handle_store(req, _CONFIG, _bedrock_client(), s3v)

        call_kwargs = s3v.put_vectors.call_args.kwargs
        key = call_kwargs["vectors"][0]["key"]
        assert key.startswith("memories/")
        # No scope prefix in key
        assert "global" not in key
        assert "project" not in key

    def test_handle_store_id_is_uuid(self) -> None:
        req = StoreRequest(text="test")
        result = handle_store(req, _CONFIG, _bedrock_client(), _s3vectors_client())

        assert re.match(r"^[0-9a-f-]{36}$", result.id)

    def test_handle_store_tags_returned_in_response(self) -> None:
        req = StoreRequest(text="test", tags=["project:engram", "scope:global"])
        result = handle_store(req, _CONFIG, _bedrock_client(), _s3vectors_client())

        assert "project:engram" in result.tags
        assert "scope:global" in result.tags

    def test_handle_store_memory_type_injected_as_tag(self) -> None:
        req = StoreRequest(text="test", memory_type="decision")
        result = handle_store(req, _CONFIG, _bedrock_client(), _s3vectors_client())

        assert "memory_type:decision" in result.tags

    def test_handle_store_memory_type_tag_not_duplicated(self) -> None:
        req = StoreRequest(text="test", tags=["memory_type:decision"], memory_type="decision")
        result = handle_store(req, _CONFIG, _bedrock_client(), _s3vectors_client())

        assert result.tags.count("memory_type:decision") == 1

    def test_handle_store_metadata_contains_expected_fields(self) -> None:
        s3v = _s3vectors_client()
        req = StoreRequest(
            text="my memory",
            tags=["scope:global"],
            conversation_id="conv-123",
            trigger="compact_auto",
        )
        handle_store(req, _CONFIG, _bedrock_client(), s3v)

        metadata = s3v.put_vectors.call_args.kwargs["vectors"][0]["metadata"]
        assert metadata["text"] == "my memory"
        assert "scope:global" in metadata["tags"]
        assert metadata["conversation_id"] == "conv-123"
        assert metadata["trigger"] == "compact_auto"
        assert metadata["type"] == "memory"
        assert "created_at" in metadata
