# Copyright (c) 2026 Brad Duhon. All Rights Reserved.
# Confidential and Proprietary.
# Unauthorized copying of this file is strictly prohibited.
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
    scope: str
    created_at: str
    type: str


class RecallResponse(BaseModel):
    memories: list[MemoryResult]
    total: int
    query_ms: int


class SummarizeRequest(BaseModel):
    scope: Literal["project", "global"]
    project_id: str | None = None
    delete_originals: bool = False


class SummarizeResponse(BaseModel):
    summary_id: str
    pruned_count: int
    summary_token_count: int
    scope: str
