# Copyright (c) 2026 Engram Contributors. All Rights Reserved.
# Licensed under the MIT License. See LICENSE for details.
from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, model_validator


class StoreRequest(BaseModel):
    text: str
    scope: Literal["project", "global"]
    project_id: str | None = None
    conversation_id: str
    trigger: str = "explicit"

    @model_validator(mode="after")
    def project_id_required_for_project_scope(self) -> StoreRequest:
        if self.scope == "project" and not self.project_id:
            raise ValueError("project_id is required when scope is 'project'")
        return self


class StoreResponse(BaseModel):
    stored: bool
    id: str
    scope: str
    token_count: int


class RecallRequest(BaseModel):
    query: str
    project_id: str | None = None
    top_k: int = 5
    scope_filter: Literal["project", "global"] | None = None


class MemoryResult(BaseModel):
    id: str
    text: str
    score: float
    relevance_score: float  # Normalized similarity: 1 - (cosine_distance / 2), range 0-1. Higher = better.
    scope: str
    created_at: str
    type: str


class RecallResponse(BaseModel):
    memories: list[MemoryResult]
    total: int
    query_ms: int


class DeleteRequest(BaseModel):
    memory_id: str
    scope: Literal["project", "global"]
    project_id: str | None = None

    @model_validator(mode="after")
    def project_id_required_for_project_scope(self) -> DeleteRequest:
        if self.scope == "project" and not self.project_id:
            raise ValueError("project_id is required when scope is 'project'")
        return self


class DeleteResponse(BaseModel):
    deleted: bool
    id: str


class SearchRelatedRequest(BaseModel):
    memory_id: str
    scope: Literal["project", "global"]
    project_id: str | None = None
    window_minutes: int = 5

    @model_validator(mode="after")
    def project_id_required_for_project_scope(self) -> SearchRelatedRequest:
        if self.scope == "project" and not self.project_id:
            raise ValueError("project_id is required when scope is 'project'")
        return self


class SearchRelatedResponse(BaseModel):
    anchor_id: str
    neighbors: list[MemoryResult]
    total: int


class SummarizeRequest(BaseModel):
    scope: Literal["project", "global"]
    project_id: str | None = None
    delete_originals: bool = False


class SummarizeResponse(BaseModel):
    summary_id: str
    pruned_count: int
    summary_token_count: int
    scope: str
