# Copyright (c) 2026 Engram Contributors. All Rights Reserved.
# Licensed under the MIT License. See LICENSE for details.
from __future__ import annotations

import pytest
from pydantic import ValidationError

from models import RecallRequest, StoreRequest, SummarizeRequest


class TestStoreRequest:
    def test_store_request_minimal_valid(self) -> None:
        req = StoreRequest(text="hello")
        assert req.text == "hello"
        assert req.tags == []
        assert req.trigger == "explicit"
        assert req.memory_type == "context"

    def test_store_request_with_tags(self) -> None:
        req = StoreRequest(text="hello", tags=["project:engram", "scope:global"])
        assert req.tags == ["project:engram", "scope:global"]

    def test_store_request_with_memory_type(self) -> None:
        req = StoreRequest(text="x", memory_type="decision")
        assert req.memory_type == "decision"

    def test_store_request_invalid_memory_type_raises(self) -> None:
        with pytest.raises(ValidationError):
            StoreRequest(text="x", memory_type="unknown")  # type: ignore[arg-type]

    def test_store_request_missing_text_raises(self) -> None:
        with pytest.raises(ValidationError):
            StoreRequest()  # type: ignore[call-arg]

    def test_store_request_custom_trigger(self) -> None:
        req = StoreRequest(text="x", trigger="compact_auto")
        assert req.trigger == "compact_auto"

    def test_store_request_conversation_id_defaults_to_unknown(self) -> None:
        req = StoreRequest(text="x")
        assert req.conversation_id == "unknown"


class TestRecallRequest:
    def test_recall_request_minimal(self) -> None:
        req = RecallRequest(query="what is the db schema?")
        assert req.top_k == 5
        assert req.weights == {}

    def test_recall_request_with_weights(self) -> None:
        req = RecallRequest(query="auth decisions", weights={"project:engram": 1.5, "memory_type:decision": 1.2})
        assert req.weights["project:engram"] == 1.5
        assert req.weights["memory_type:decision"] == 1.2

    def test_recall_request_missing_query_raises(self) -> None:
        with pytest.raises(ValidationError):
            RecallRequest()  # type: ignore[call-arg]

    def test_recall_request_custom_top_k(self) -> None:
        req = RecallRequest(query="q", top_k=10)
        assert req.top_k == 10


class TestSummarizeRequest:
    def test_summarize_request_defaults(self) -> None:
        req = SummarizeRequest()
        assert req.tag_filter == []
        assert req.delete_originals is False

    def test_summarize_request_with_tag_filter(self) -> None:
        req = SummarizeRequest(tag_filter=["scope:global"], delete_originals=True)
        assert req.tag_filter == ["scope:global"]
        assert req.delete_originals is True
