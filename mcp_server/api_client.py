# Copyright (c) 2026 Engram Contributors. All Rights Reserved.
# Licensed under the MIT License. See LICENSE for details.
from __future__ import annotations

import logging

import httpx

logger = logging.getLogger(__name__)


class MemoryAPIClient:
    """mTLS HTTPS client for the engram memory API."""

    def __init__(self, base_url: str, cert_path: str, key_path: str) -> None:
        self._base_url = base_url.rstrip("/")
        self._client = httpx.Client(
            cert=(cert_path, key_path),
            verify=True,
            timeout=30.0,
        )

    def store(self, payload: dict) -> dict:
        response = self._client.post(f"{self._base_url}/store", json=payload)
        response.raise_for_status()
        return response.json()  # type: ignore[no-any-return]

    def recall(self, payload: dict) -> dict:
        response = self._client.post(f"{self._base_url}/recall", json=payload)
        response.raise_for_status()
        return response.json()  # type: ignore[no-any-return]

    def summarize(self, payload: dict) -> dict:
        response = self._client.post(f"{self._base_url}/summarize", json=payload)
        response.raise_for_status()
        return response.json()  # type: ignore[no-any-return]

    def close(self) -> None:
        self._client.close()
