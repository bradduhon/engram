# Copyright (c) 2026 Engram Contributors. All Rights Reserved.
# Licensed under the MIT License. See LICENSE for details.
from __future__ import annotations

from unittest.mock import MagicMock

from vectors import VectorResult, build_key_prefix, delete_vectors, list_vectors, put_vector, query_vectors


class TestBuildKeyPrefix:
    def test_global_scope(self) -> None:
        assert build_key_prefix("global", None) == "global/memories"

    def test_global_scope_ignores_project_id(self) -> None:
        assert build_key_prefix("global", "p1") == "global/memories"

    def test_project_scope_with_project_id(self) -> None:
        assert build_key_prefix("project", "my-proj") == "project/my-proj/memories"

    def test_project_scope_without_project_id_falls_back(self) -> None:
        assert build_key_prefix("project", None) == "global/memories"


class TestPutVector:
    def test_put_vector_calls_client_correctly(self) -> None:
        client = MagicMock()
        vector = [0.1] * 1024
        metadata = {"text": "hello", "scope": "global"}

        put_vector(
            bucket="my-bucket",
            index_name="memories",
            key="global/memories/abc123",
            vector=vector,
            metadata=metadata,
            s3vectors_client=client,
        )

        client.put_vectors.assert_called_once_with(
            vectorBucketName="my-bucket",
            indexName="memories",
            vectors=[{
                "key": "global/memories/abc123",
                "data": {"float32": vector},
                "metadata": metadata,
            }],
        )


class TestQueryVectors:
    def test_query_vectors_returns_vector_results(self) -> None:
        client = MagicMock()
        client.query_vectors.return_value = {
            "vectors": [
                {"key": "global/memories/id1", "distance": 0.95, "metadata": {"text": "memory 1"}},
                {"key": "global/memories/id2", "distance": 0.88, "metadata": {"text": "memory 2"}},
            ]
        }
        query = [0.0] * 1024

        results = query_vectors("bucket", "memories", query, top_k=5, s3vectors_client=client)

        assert len(results) == 2
        assert isinstance(results[0], VectorResult)
        assert results[0].key == "global/memories/id1"
        assert results[0].score == 0.95
        assert results[0].metadata["text"] == "memory 1"

    def test_query_vectors_empty_response(self) -> None:
        client = MagicMock()
        client.query_vectors.return_value = {"vectors": []}

        results = query_vectors("bucket", "memories", [0.0] * 1024, top_k=5, s3vectors_client=client)

        assert results == []

    def test_query_vectors_passes_top_k(self) -> None:
        client = MagicMock()
        client.query_vectors.return_value = {"vectors": []}
        query = [0.1] * 1024

        query_vectors("bucket", "memories", query, top_k=10, s3vectors_client=client)

        call_kwargs = client.query_vectors.call_args.kwargs
        assert call_kwargs["topK"] == 10

    def test_query_vectors_missing_metadata_uses_empty_dict(self) -> None:
        client = MagicMock()
        client.query_vectors.return_value = {
            "vectors": [{"key": "k", "distance": 0.5}]
        }

        results = query_vectors("b", "i", [0.0] * 1024, top_k=5, s3vectors_client=client)

        assert results[0].metadata == {}


class TestListVectors:
    def test_list_vectors_returns_all(self) -> None:
        client = MagicMock()
        client.list_vectors.return_value = {
            "vectors": [
                {"key": "global/memories/id1", "metadata": {"text": "m1"}},
                {"key": "global/memories/id2", "metadata": {"text": "m2"}},
            ]
        }

        results = list_vectors("bucket", "memories", client)

        assert len(results) == 2
        assert results[0].key == "global/memories/id1"
        assert results[0].metadata["text"] == "m1"
        assert results[0].score == 0.0

    def test_list_vectors_filters_by_prefix(self) -> None:
        client = MagicMock()
        client.list_vectors.return_value = {
            "vectors": [
                {"key": "global/memories/id1", "metadata": {}},
                {"key": "project/proj-1/memories/id2", "metadata": {}},
            ]
        }

        results = list_vectors("bucket", "memories", client, key_prefix="global/memories")

        assert len(results) == 1
        assert results[0].key == "global/memories/id1"

    def test_list_vectors_paginates(self) -> None:
        client = MagicMock()
        client.list_vectors.side_effect = [
            {"vectors": [{"key": "k1", "metadata": {}}], "nextToken": "tok"},
            {"vectors": [{"key": "k2", "metadata": {}}]},
        ]

        results = list_vectors("bucket", "memories", client)

        assert len(results) == 2
        assert client.list_vectors.call_count == 2

    def test_list_vectors_empty(self) -> None:
        client = MagicMock()
        client.list_vectors.return_value = {"vectors": []}

        results = list_vectors("bucket", "memories", client)

        assert results == []


class TestDeleteVectors:
    def test_delete_vectors_calls_client_correctly(self) -> None:
        client = MagicMock()
        keys = ["global/memories/id1", "global/memories/id2"]

        delete_vectors("bucket", "memories", keys, client)

        client.delete_vectors.assert_called_once_with(
            vectorBucketName="bucket",
            indexName="memories",
            keys=keys,
        )
