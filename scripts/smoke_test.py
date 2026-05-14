#! /usr/bin/env python3
# Copyright (c) 2026 Brad Duhon. All Rights Reserved.
# Confidential and Proprietary.
# Unauthorized copying of this file is strictly prohibited.
from __future__ import annotations

import os
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "mcp_server"))

import httpx

from cert_loader import load_client_cert, write_temp_cert_files


def main() -> None:
    base_url = os.environ.get("MEMORY_API_URL", "").rstrip("/")
    if not base_url:
        print("ERROR: MEMORY_API_URL is not set", file=sys.stderr)
        sys.exit(1)

    args = sys.argv[1:]
    bundle = load_client_cert()
    cert_path, key_path = write_temp_cert_files(bundle)

    try:
        client = httpx.Client(cert=(cert_path, key_path), verify=True, timeout=30.0)

        if args and args[0] == "delete":
            _delete(client, base_url, args[1:])
        else:
            print(f"==> Smoke test: {base_url}")
            _run(client, base_url)
    finally:
        for path in (cert_path, key_path):
            try:
                os.unlink(path)
            except OSError:
                pass


def _delete(client: httpx.Client, base_url: str, memory_ids: list[str]) -> None:
    """Delete one or more memories by ID. Usage: smoke_test.py delete <id:scope> ..."""
    if not memory_ids:
        print("Usage: smoke_test.py delete <memory_id:scope> [<memory_id:scope> ...]")
        print("  scope is 'global' or 'project'")
        sys.exit(1)

    for entry in memory_ids:
        if ":" not in entry:
            print(f"ERROR: expected <memory_id:scope>, got '{entry}'", file=sys.stderr)
            sys.exit(1)
        memory_id, scope = entry.split(":", 1)
        r = client.post(f"{base_url}/delete", json={"memory_id": memory_id, "scope": scope})
        r.raise_for_status()
        result = r.json()
        print(f"deleted {memory_id[:8]}  {result}")


def _run(client: httpx.Client, base_url: str) -> None:
    conversation_id = f"smoke-test-{time.strftime('%Y%m%d')}"

    # 1. /store
    print("[1/3] POST /store")
    r = client.post(f"{base_url}/store", json={
        "text": f"smoke-test memory {time.strftime('%Y%m%dT%H%M%SZ')}",
        "scope": "global",
        "conversation_id": conversation_id,
        "trigger": "explicit",
    })
    r.raise_for_status()
    stored = r.json()
    assert stored.get("stored") is True, f"expected stored=true: {stored}"
    memory_id: str = stored["id"]
    print(f"    OK  id={memory_id}")

    # 2. /recall
    print("[2/3] POST /recall")
    r = client.post(f"{base_url}/recall", json={"query": "smoke-test memory", "top_k": 3})
    r.raise_for_status()
    recalled = r.json()
    assert recalled.get("total", 0) > 0, f"expected results, got 0: {recalled}"
    best = recalled["memories"][0]
    assert "relevance_score" in best, f"MemoryResult missing relevance_score: {best}"
    print(f"    OK  total={recalled['total']} best_relevance={best['relevance_score']:.4f}")

    # 3. /search_related
    print("[3/3] POST /search_related")
    r = client.post(f"{base_url}/search_related", json={
        "memory_id": memory_id,
        "scope": "global",
        "window_minutes": 5,
    })
    r.raise_for_status()
    related = r.json()
    assert "anchor_id" in related, f"missing anchor_id: {related}"
    print(f"    OK  anchor_id={related['anchor_id']} neighbors={related['total']}")

    print("\nPASS: all endpoints healthy")


if __name__ == "__main__":
    main()
