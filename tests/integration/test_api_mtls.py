# Copyright (c) 2026 Engram Contributors. All Rights Reserved.
# Licensed under the MIT License. See LICENSE for details.
from __future__ import annotations

import os

import pytest


@pytest.mark.integration
class TestMTLSConnectivity:
    """Live mTLS round-trip tests. Require deployed infrastructure.

    Run with: pytest tests/integration/ --run-integration
    Set MEMORY_API_URL to the deployed API Gateway custom domain.
    Local certs must be initialized via hooks/setup-certs.sh.
    """

    def test_unauthenticated_store_returns_403(self) -> None:
        import httpx

        base_url = os.environ["MEMORY_API_URL"]
        response = httpx.post(
            f"{base_url}/store",
            json={"text": "should fail", "scope": "global", "conversation_id": "test"},
            verify=True,
        )
        assert response.status_code == 403

    def test_store_and_recall_round_trip(self) -> None:
        from pathlib import Path

        import pyrage

        cert_dir = Path.home() / ".claude" / "certs"
        base_url = os.environ["MEMORY_API_URL"]

        identity = pyrage.x25519.Identity.from_str(
            (cert_dir / "age-identity.txt").read_text().strip()
        )
        key_pem = pyrage.decrypt((cert_dir / "client.key.age").read_bytes(), [identity]).decode()

        import tempfile

        with tempfile.NamedTemporaryFile(mode="w", suffix=".key", delete=False) as kf:
            kf.write(key_pem)
            key_path = kf.name

        try:
            client = __import__("httpx").Client(
                cert=(str(cert_dir / "client.crt"), key_path),
                verify=str(cert_dir / "amazon-trust-services-ca.pem"),
                timeout=15.0,
            )

            store_resp = client.post(
                f"{base_url}/store",
                json={
                    "text": "integration test memory",
                    "scope": "global",
                    "conversation_id": "integration-test",
                    "trigger": "explicit",
                },
            )
            assert store_resp.status_code == 200
            assert store_resp.json()["stored"] is True

            recall_resp = client.post(
                f"{base_url}/recall",
                json={"query": "integration test memory"},
            )
            assert recall_resp.status_code == 200
            memories = recall_resp.json()["memories"]
            assert len(memories) > 0
            assert any("integration test" in m["text"] for m in memories)
        finally:
            os.unlink(key_path)
