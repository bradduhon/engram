# Copyright (c) 2026 Engram Contributors. All Rights Reserved.
# Licensed under the MIT License. See LICENSE for details.
from __future__ import annotations

import logging

import httpx

logger = logging.getLogger(__name__)


class MemoryAPIClient:
    """Async mTLS HTTPS client for the engram memory API.

    Uses httpx.AsyncClient to avoid blocking the MCP server's asyncio event loop
    during API calls. The sync httpx.Client would block all concurrent MCP protocol
    messages for the full duration of each HTTP request.
    """

    def __init__(self, base_url: str, cert_path: str, key_path: str) -> None:
        self._base_url = base_url.rstrip("/")
        self._client = httpx.AsyncClient(
            cert=(cert_path, key_path),
            verify=True,
            timeout=30.0,
        )

    async def store(self, payload: dict) -> dict:
        response = await self._client.post(f"{self._base_url}/store", json=payload)
        response.raise_for_status()
        return response.json()  # type: ignore[no-any-return]

    async def recall(self, payload: dict) -> dict:
        response = await self._client.post(f"{self._base_url}/recall", json=payload)
        response.raise_for_status()
        return response.json()  # type: ignore[no-any-return]

    async def summarize(self, payload: dict) -> dict:
        response = await self._client.post(f"{self._base_url}/summarize", json=payload)
        response.raise_for_status()
        return response.json()  # type: ignore[no-any-return]

    async def delete(self, payload: dict) -> dict:
        response = await self._client.post(f"{self._base_url}/delete", json=payload)
        response.raise_for_status()
        return response.json()  # type: ignore[no-any-return]

    async def search_related(self, payload: dict) -> dict:
        response = await self._client.post(f"{self._base_url}/search_related", json=payload)
        response.raise_for_status()
        return response.json()  # type: ignore[no-any-return]

    async def prune(self, payload: dict) -> dict:
        response = await self._client.post(f"{self._base_url}/prune", json=payload)
        response.raise_for_status()
        return response.json()  # type: ignore[no-any-return]

    async def close(self) -> None:
        await self._client.aclose()
