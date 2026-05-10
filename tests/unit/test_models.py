# Copyright (c) 2026 Engram Contributors. All Rights Reserved.
# Licensed under the MIT License. See LICENSE for details.
from __future__ import annotations

import pytest
from pydantic import ValidationError

from models import RecallRequest, StoreRequest, SummarizeRequest


class TestStoreRequest:
    def test_store_request_global_scope_valid(self) -> None:
        req = StoreRequest(text="hello", scope="global", conversation_id="c1")
        assert req.text == "hello"
        assert req.scope == "global"
        assert req.project_id is None
        assert req.trigger == "explicit"

    def test_store_request_project_scope_with_project_id_valid(self) -> None:
        req = StoreRequest(text="hello", scope="project", project_id="p1", conversation_id="c1")
        assert req.project_id == "p1"

    def test_store_request_project_scope_missing_project_id_raises(self) -> None:
        with pytest.raises(ValidationError, match="project_id is required"):
            StoreRequest(text="hello", scope="project", conversation_id="c1")

    def test_store_request_invalid_scope_raises(self) -> None:
        with pytest.raises(ValidationError):
            StoreRequest(text="hello", scope="unknown", conversation_id="c1")  # type: ignore[arg-type]

    def test_store_request_custom_trigger(self) -> None:
        req = StoreRequest(text="x", scope="global", conversation_id="c1", trigger="compact_auto")
        assert req.trigger == "compact_auto"


class TestRecallRequest:
    def test_recall_request_minimal(self) -> None:
        req = RecallRequest(query="what is the db schema?")
        assert req.top_k == 5
        assert req.project_id is None
        assert req.scope_filter is None

    def test_recall_request_with_project_id(self) -> None:
        req = RecallRequest(query="auth decisions", project_id="proj-x", top_k=10)
        assert req.project_id == "proj-x"
        assert req.top_k == 10

    def test_recall_request_missing_query_raises(self) -> None:
        with pytest.raises(ValidationError):
            RecallRequest()  # type: ignore[call-arg]

    def test_recall_request_scope_filter(self) -> None:
        req = RecallRequest(query="q", scope_filter="global")
        assert req.scope_filter == "global"


class TestSummarizeRequest:
    def test_summarize_request_global(self) -> None:
        req = SummarizeRequest(scope="global")
        assert req.delete_originals is False

    def test_summarize_request_project_with_delete(self) -> None:
        req = SummarizeRequest(scope="project", project_id="p1", delete_originals=True)
        assert req.delete_originals is True

    def test_summarize_request_missing_scope_raises(self) -> None:
        with pytest.raises(ValidationError):
            SummarizeRequest()  # type: ignore[call-arg]
