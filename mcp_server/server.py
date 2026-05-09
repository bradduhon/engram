# Copyright (c) 2026 Brad Duhon. All Rights Reserved.
# Confidential and Proprietary.
# Unauthorized copying of this file is strictly prohibited.
from __future__ import annotations

import atexit
import json
import logging
import os
import sys

from mcp.server import Server
from mcp.server.stdio import stdio_server
from mcp.types import TextContent, Tool

from mcp_server.api_client import MemoryAPIClient
from mcp_server.cert_loader import load_client_cert, write_temp_cert_files
from mcp_server.tools import RECALL_MEMORY_SCHEMA, STORE_MEMORY_SCHEMA, SUMMARIZE_MEMORIES_SCHEMA

logging.basicConfig(level=logging.INFO, stream=sys.stderr)
logger = logging.getLogger(__name__)

app = Server("engram-memory")


def _create_api_client() -> MemoryAPIClient:
    """Initialize the mTLS API client with certs from Secrets Manager."""
    region = os.environ.get("AWS_REGION", "us-east-1")
    base_url = os.environ["MEMORY_API_URL"]

    bundle = load_client_cert(region)
    cert_path, key_path = write_temp_cert_files(bundle)

    def _cleanup() -> None:
        for path in (cert_path, key_path):
            try:
                os.unlink(path)
            except OSError:
                pass

    atexit.register(_cleanup)

    return MemoryAPIClient(base_url, cert_path, key_path)


_client: MemoryAPIClient | None = None


def _get_client() -> MemoryAPIClient:
    global _client
    if _client is None:
        _client = _create_api_client()
    return _client


@app.list_tools()
async def list_tools() -> list[Tool]:
    return [
        Tool(
            name="store_memory",
            description=(
                "Store a memory for later recall. Use at session end, when explicitly asked "
                "to remember something, or for important decisions and preferences."
            ),
            inputSchema=STORE_MEMORY_SCHEMA,
        ),
        Tool(
            name="recall_memory",
            description=(
                "Search stored memories by semantic similarity. Use to recall past decisions, "
                "preferences, context, and technical details."
            ),
            inputSchema=RECALL_MEMORY_SCHEMA,
        ),
        Tool(
            name="summarize_memories",
            description=(
                "Compress multiple memories into a summary. Used by the daily automation; "
                "can also be triggered manually."
            ),
            inputSchema=SUMMARIZE_MEMORIES_SCHEMA,
        ),
    ]


@app.call_tool()
async def call_tool(name: str, arguments: dict) -> list[TextContent]:
    client = _get_client()

    try:
        if name == "store_memory":
            result = client.store(arguments)
        elif name == "recall_memory":
            result = client.recall(arguments)
        elif name == "summarize_memories":
            result = client.summarize(arguments)
        else:
            return [TextContent(type="text", text=f"Unknown tool: {name}")]

        return [TextContent(type="text", text=json.dumps(result, indent=2))]

    except Exception as exc:
        logger.exception("Tool %s failed", name)
        return [TextContent(type="text", text=f"Error calling {name}: {type(exc).__name__}")]


async def main() -> None:
    async with stdio_server() as (read_stream, write_stream):
        await app.run(read_stream, write_stream, app.create_initialization_options())


if __name__ == "__main__":
    import asyncio

    asyncio.run(main())
