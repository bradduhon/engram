# Copyright (c) 2026 Engram Contributors. All Rights Reserved.
# Licensed under the MIT License. See LICENSE for details.
from __future__ import annotations

from unittest.mock import MagicMock

from vectors import VectorResult, apply_weights, delete_vectors, list_vectors, memory_key, parse_tags, put_vector, query_vectors


class TestMemoryKey:
    def test_flat_key_format(self) -> None:
        assert memory_key("abc-123") == "memories/abc-123"

    def test_summary_key_format(self) -> None:
        assert memory_key("summary-xyz") == "memories/summary-xyz"


class TestParseTags:
    def test_parses_comma_separated_tags(self) -> None:
        meta = {"tags": "project:engram,scope:global,memory_type:decision"}
        assert parse_tags(meta) == ["project:engram", "scope:global", "memory_type:decision"]

    def test_empty_tags_field_returns_empty_list(self) -> None:
        assert parse_tags({"tags": ""}) == []

    def test_missing_tags_field_returns_empty_list(self) -> None:
        assert parse_tags({}) == []

    def test_strips_whitespace(self) -> None:
        assert parse_tags({"tags": " a , b "}) == ["a", "b"]


class TestApplyWeights:
    def _vr(self, key: str, score: float, tags: str) -> VectorResult:
        return VectorResult(key=key, score=score, metadata={"tags": tags})

    def test_no_weights_preserves_base_relevance_order(self) -> None:
        r1 = self._vr("memories/r1", score=0.2, tags="")  # base=0.9
        r2 = self._vr("memories/r2", score=0.8, tags="")  # base=0.6
        ranked = apply_weights([r1, r2], {})
        assert ranked[0][0].key == "memories/r1"

    def test_matching_tag_boosts_score(self) -> None:
        # r1: score=0.5, base=0.75; no matching tag -> 0.75
        # r2: score=0.8, base=0.6; weight 2.0 on project:engram -> 1.2
        r1 = self._vr("memories/r1", score=0.5, tags="scope:global")
        r2 = self._vr("memories/r2", score=0.8, tags="project:engram")
        ranked = apply_weights([r1, r2], {"project:engram": 2.0})
        assert ranked[0][0].key == "memories/r2"
        assert abs(ranked[0][1] - 1.2) < 0.001
        assert abs(ranked[1][1] - 0.75) < 0.001

    def test_multiple_weights_multiply(self) -> None:
        r = self._vr("memories/r", score=0.0, tags="project:engram,memory_type:decision")
        # base=1.0; project:engram weight=1.5; memory_type:decision weight=1.2 -> 1.8
        ranked = apply_weights([r], {"project:engram": 1.5, "memory_type:decision": 1.2})
        assert abs(ranked[0][1] - 1.8) < 0.001

    def test_non_matching_weight_not_applied(self) -> None:
        r = self._vr("memories/r", score=0.0, tags="scope:global")
        ranked = apply_weights([r], {"project:engram": 5.0})
        # Only scope:global tag, project:engram not present -> no multiplier -> base=1.0
        assert abs(ranked[0][1] - 1.0) < 0.001

    def test_suppression_weight_below_1(self) -> None:
        r1 = self._vr("memories/r1", score=0.2, tags="memory_type:task")  # base=0.9 * 0.5 = 0.45
        r2 = self._vr("memories/r2", score=0.5, tags="memory_type:decision")  # base=0.75
        ranked = apply_weights([r1, r2], {"memory_type:task": 0.5})
        assert ranked[0][0].key == "memories/r2"

    def test_old_vector_no_tags_gets_base_score(self) -> None:
        """Pre-migration vectors with no tags field should not error and get unmodified base score."""
        r = VectorResult(key="global/memories/old", score=0.4, metadata={"scope": "global"})
        ranked = apply_weights([r], {"project:engram": 2.0})
        assert abs(ranked[0][1] - 0.8) < 0.001  # base = 1 - 0.4/2 = 0.8

    def test_empty_results_returns_empty(self) -> None:
        assert apply_weights([], {"project:engram": 1.5}) == []

    def test_returns_sorted_descending(self) -> None:
        vectors = [
            self._vr("memories/a", score=0.6, tags=""),   # base=0.7
            self._vr("memories/b", score=0.2, tags=""),   # base=0.9
            self._vr("memories/c", score=0.4, tags=""),   # base=0.8
        ]
        ranked = apply_weights(vectors, {})
        scores = [s for _, s in ranked]
        assert scores == sorted(scores, reverse=True)


class TestPutVector:
    def test_put_vector_calls_client_correctly(self) -> None:
        client = MagicMock()
        vector = [0.1] * 1024
        metadata = {"text": "hello", "tags": "scope:global"}

        put_vector(
            bucket="my-bucket",
            index_name="memories",
            key="memories/abc123",
            vector=vector,
            metadata=metadata,
            s3vectors_client=client,
        )

        client.put_vectors.assert_called_once_with(
            vectorBucketName="my-bucket",
            indexName="memories",
            vectors=[{
                "key": "memories/abc123",
                "data": {"float32": vector},
                "metadata": metadata,
            }],
        )


class TestQueryVectors:
    def test_query_vectors_returns_vector_results(self) -> None:
        client = MagicMock()
        client.query_vectors.return_value = {
            "vectors": [
                {"key": "memories/id1", "distance": 0.95, "metadata": {"text": "memory 1"}},
                {"key": "memories/id2", "distance": 0.88, "metadata": {"text": "memory 2"}},
            ]
        }
        query = [0.0] * 1024

        results = query_vectors("bucket", "memories", query, top_k=5, s3vectors_client=client)

        assert len(results) == 2
        assert isinstance(results[0], VectorResult)
        assert results[0].key == "memories/id1"
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
                {"key": "memories/id1", "metadata": {"text": "m1"}},
                {"key": "memories/id2", "metadata": {"text": "m2"}},
            ]
        }

        results = list_vectors("bucket", "memories", client)

        assert len(results) == 2
        assert results[0].key == "memories/id1"
        assert results[0].metadata["text"] == "m1"
        assert results[0].score == 0.0

    def test_list_vectors_filters_by_prefix(self) -> None:
        client = MagicMock()
        client.list_vectors.return_value = {
            "vectors": [
                {"key": "memories/id1", "metadata": {}},
                {"key": "other/id2", "metadata": {}},
            ]
        }

        results = list_vectors("bucket", "memories", client, key_prefix="memories")

        assert len(results) == 1
        assert results[0].key == "memories/id1"

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
        keys = ["memories/id1", "memories/id2"]

        delete_vectors("bucket", "memories", keys, client)

        client.delete_vectors.assert_called_once_with(
            vectorBucketName="bucket",
            indexName="memories",
            keys=keys,
        )
