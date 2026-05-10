# Copyright (c) 2026 Engram Contributors. All Rights Reserved.
# Licensed under the MIT License. See LICENSE for details.
from __future__ import annotations

import pytest

from mcp_server.tools import RECALL_MEMORY_SCHEMA, STORE_MEMORY_SCHEMA, SUMMARIZE_MEMORIES_SCHEMA


class TestStoreMemorySchema:
    def test_required_fields(self) -> None:
        assert set(STORE_MEMORY_SCHEMA["required"]) == {"text", "scope", "conversation_id"}

    def test_scope_enum(self) -> None:
        assert STORE_MEMORY_SCHEMA["properties"]["scope"]["enum"] == ["project", "global"]

    def test_trigger_has_default(self) -> None:
        assert STORE_MEMORY_SCHEMA["properties"]["trigger"]["default"] == "explicit"

    def test_optional_project_id_present(self) -> None:
        assert "project_id" in STORE_MEMORY_SCHEMA["properties"]
        assert "project_id" not in STORE_MEMORY_SCHEMA["required"]


class TestRecallMemorySchema:
    def test_required_fields(self) -> None:
        assert RECALL_MEMORY_SCHEMA["required"] == ["query"]

    def test_top_k_has_default(self) -> None:
        assert RECALL_MEMORY_SCHEMA["properties"]["top_k"]["default"] == 5

    def test_scope_filter_enum(self) -> None:
        assert set(RECALL_MEMORY_SCHEMA["properties"]["scope_filter"]["enum"]) == {"project", "global"}

    def test_optional_fields_not_required(self) -> None:
        required = set(RECALL_MEMORY_SCHEMA["required"])
        for field in ("project_id", "top_k", "scope_filter"):
            assert field not in required


class TestSummarizeMemoriesSchema:
    def test_required_fields(self) -> None:
        assert SUMMARIZE_MEMORIES_SCHEMA["required"] == ["scope"]

    def test_scope_enum(self) -> None:
        assert set(SUMMARIZE_MEMORIES_SCHEMA["properties"]["scope"]["enum"]) == {"project", "global"}

    def test_delete_originals_default_false(self) -> None:
        assert SUMMARIZE_MEMORIES_SCHEMA["properties"]["delete_originals"]["default"] is False

    def test_optional_project_id_present(self) -> None:
        assert "project_id" in SUMMARIZE_MEMORIES_SCHEMA["properties"]
        assert "project_id" not in SUMMARIZE_MEMORIES_SCHEMA["required"]
