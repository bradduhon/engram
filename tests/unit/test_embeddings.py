# Copyright (c) 2026 Engram Contributors. All Rights Reserved.
# Licensed under the MIT License. See LICENSE for details.
from __future__ import annotations

import json
from io import BytesIO
from unittest.mock import MagicMock

import pytest

from embeddings import EXPECTED_DIMENSIONS, get_embedding


def _mock_bedrock(vector: list[float]) -> MagicMock:
    client = MagicMock()
    client.invoke_model.return_value = {
        "body": BytesIO(json.dumps({"embedding": vector}).encode())
    }
    return client


class TestGetEmbedding:
    def test_get_embedding_returns_correct_vector(self) -> None:
        vector = [0.1] * EXPECTED_DIMENSIONS
        client = _mock_bedrock(vector)

        result = get_embedding("test text", client, "amazon.titan-embed-text-v2:0")

        assert result == vector
        client.invoke_model.assert_called_once()
        call_kwargs = client.invoke_model.call_args
        body = json.loads(call_kwargs.kwargs["body"])
        assert body["inputText"] == "test text"
        assert body["dimensions"] == EXPECTED_DIMENSIONS
        assert body["normalize"] is True

    def test_get_embedding_wrong_dimensions_raises(self) -> None:
        short_vector = [0.1] * 512
        client = _mock_bedrock(short_vector)

        with pytest.raises(AssertionError, match="Expected 1024 dimensions"):
            get_embedding("test", client, "amazon.titan-embed-text-v2:0")

    def test_get_embedding_passes_model_id(self) -> None:
        vector = [0.0] * EXPECTED_DIMENSIONS
        client = _mock_bedrock(vector)
        model_id = "amazon.titan-embed-text-v2:0"

        get_embedding("text", client, model_id)

        client.invoke_model.assert_called_once_with(
            modelId=model_id,
            body=json.dumps({
                "inputText": "text",
                "dimensions": EXPECTED_DIMENSIONS,
                "normalize": True,
            }),
        )
