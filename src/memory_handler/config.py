# Copyright (c) 2026 Brad Duhon. All Rights Reserved.
# Confidential and Proprietary.
# Unauthorized copying of this file is strictly prohibited.
from __future__ import annotations

import os
from dataclasses import dataclass


@dataclass(frozen=True)
class Config:
    memory_bucket: str
    vector_index_name: str
    embed_model_id: str
    haiku_model_id: str
    aws_region: str

    @classmethod
    def from_env(cls) -> Config:
        return cls(
            memory_bucket=os.environ["MEMORY_BUCKET"],
            vector_index_name=os.environ.get("VECTOR_INDEX_NAME", "memories"),
            embed_model_id=os.environ.get("EMBED_MODEL_ID", "amazon.titan-embed-text-v2:0"),
            haiku_model_id=os.environ.get("HAIKU_MODEL_ID", "anthropic.claude-haiku-4-5-20251001"),
            aws_region=os.environ.get("AWS_REGION", "us-east-1"),
        )
