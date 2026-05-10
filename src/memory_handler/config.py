# Copyright (c) 2026 Engram Contributors. All Rights Reserved.
# Licensed under the MIT License. See LICENSE for details.
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
    client_cert_secret_id: str

    @classmethod
    def from_env(cls) -> Config:
        return cls(
            memory_bucket=os.environ["MEMORY_BUCKET"],
            vector_index_name=os.environ.get("VECTOR_INDEX_NAME", "memories"),
            embed_model_id=os.environ.get("EMBED_MODEL_ID", "amazon.titan-embed-text-v2:0"),
            haiku_model_id=os.environ.get("HAIKU_MODEL_ID", "us.anthropic.claude-haiku-4-5-20251001-v1:0"),
            aws_region=os.environ.get("AWS_REGION", "us-east-1"),
            client_cert_secret_id=os.environ["CLIENT_CERT_SECRET_ID"],
        )
