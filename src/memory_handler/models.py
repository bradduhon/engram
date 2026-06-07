# Copyright (c) 2026 Engram Contributors. All Rights Reserved.
# Licensed under the MIT License. See LICENSE for details.
from __future__ import annotations

from typing import Literal

from pydantic import BaseModel


class StoreRequest(BaseModel):
    text: str
    tags: list[str] = []
    conversation_id: str = "unknown"
    trigger: str = "explicit"
    memory_type: Literal["task", "decision", "discovery", "rule", "preference", "context"] = "context"


class StoreResponse(BaseModel):
    stored: bool
    id: str
    tags: list[str]
    token_count: int


class RecallRequest(BaseModel):
    query: str
    top_k: int = 5
    weights: dict[str, float] = {}


class MemoryResult(BaseModel):
    id: str
    text: str
    score: float
    relevance_score: float  # Weighted relevance: base_relevance * tag weight multipliers. Higher = better.
    tags: list[str]
    created_at: str
    type: str


class RecallResponse(BaseModel):
    memories: list[MemoryResult]
    total: int
    query_ms: int


class DeleteRequest(BaseModel):
    memory_id: str


class DeleteResponse(BaseModel):
    deleted: bool
    id: str


class SearchRelatedRequest(BaseModel):
    memory_id: str
    window_minutes: int = 5


class SearchRelatedResponse(BaseModel):
    anchor_id: str
    neighbors: list[MemoryResult]
    total: int


class SummarizeRequest(BaseModel):
    tag_filter: list[str] = []  # If provided, only summarize memories with ALL matching tags
    delete_originals: bool = False


class SummarizeResponse(BaseModel):
    summary_id: str
    pruned_count: int
    summary_token_count: int


class PruneRequest(BaseModel):
    tag_filter: list[str] = []  # If provided, only prune memories with ALL matching tags
    older_than_days: int = 30
    memory_types: list[Literal["task", "decision", "discovery", "rule", "preference", "context"]] = ["task"]
    dry_run: bool = False


class PruneResponse(BaseModel):
    deleted: int
    dry_run: bool
    candidates: list[str]  # memory IDs that were (or would be) deleted
