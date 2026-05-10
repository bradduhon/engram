# Phase 5: MCP Server

## Overview

Creates the local Python MCP server that Claude Code and claude.ai connect to. The server fetches the mTLS client cert from Secrets Manager on startup, exposes three MCP tools (store_memory, recall_memory, summarize_memories), and forwards requests to the API Gateway over mTLS. No Terraform resources in this phase -- it is pure Python code.

## Prerequisites

- Phase 4 complete: API Gateway reachable at `https://memory.<your-domain>` with mTLS
- Phase 2 complete: Secrets Manager populated with cert bundle and passphrase
- Local AWS credentials configured with `secretsmanager:GetSecretValue` on `engram/mcp-client-cert*`
- Python 3.12 installed locally
- `pip install mcp httpx boto3 pydantic` (or install from pyproject.toml extras)

## Resources Created

### Python Code -- `mcp_server/`

#### `mcp_server/__init__.py`
Empty file.

#### `mcp_server/cert_loader.py`

```python
from __future__ import annotations

import logging
import tempfile
from dataclasses import dataclass

import boto3

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class CertBundle:
    cert_pem: str
    key_pem: str
    passphrase: str


def load_client_cert(region: str) -> CertBundle:
    """Fetch the mTLS client cert bundle and passphrase from Secrets Manager.

    Returns the PEM strings. The private key is encrypted with the passphrase.
    """
    sm = boto3.client("secretsmanager", region_name=region)

    bundle_response = sm.get_secret_value(SecretId="engram/mcp-client-cert")
    passphrase_response = sm.get_secret_value(SecretId="engram/mcp-client-cert-passphrase")

    bundle_pem = bundle_response["SecretString"]
    passphrase = passphrase_response["SecretString"]

    # Split the bundle into cert (+ chain) and encrypted private key
    # The bundle format is: Certificate + CertificateChain + PrivateKey
    # Split on the private key marker
    key_marker = "-----BEGIN ENCRYPTED PRIVATE KEY-----"
    if key_marker not in bundle_pem:
        key_marker = "-----BEGIN RSA PRIVATE KEY-----"

    parts = bundle_pem.split(key_marker)
    cert_pem = parts[0].strip()
    key_pem = key_marker + parts[1]

    logger.info("Loaded client cert from Secrets Manager")

    return CertBundle(cert_pem=cert_pem, key_pem=key_pem, passphrase=passphrase)


def write_temp_cert_files(bundle: CertBundle) -> tuple[str, str]:
    """Write cert and decrypted key to temporary files for httpx.

    Returns (cert_path, key_path). Files are written to a secure temp directory.
    The caller is responsible for cleanup.

    Note: The key is written to a temp file because httpx requires file paths
    for client certs. The temp file is created with restrictive permissions.
    """
    import os
    import subprocess

    cert_file = tempfile.NamedTemporaryFile(
        mode="w", suffix=".crt", delete=False, prefix="engram-"
    )
    cert_file.write(bundle.cert_pem)
    cert_file.close()
    os.chmod(cert_file.name, 0o600)

    # Decrypt the private key using openssl
    key_encrypted_file = tempfile.NamedTemporaryFile(
        mode="w", suffix=".key.enc", delete=False, prefix="engram-"
    )
    key_encrypted_file.write(bundle.key_pem)
    key_encrypted_file.close()

    key_file = tempfile.NamedTemporaryFile(
        mode="w", suffix=".key", delete=False, prefix="engram-"
    )
    key_file.close()

    subprocess.run(
        [
            "openssl", "pkey",
            "-in", key_encrypted_file.name,
            "-out", key_file.name,
            "-passin", f"pass:{bundle.passphrase}",
        ],
        check=True,
        capture_output=True,
    )

    os.chmod(key_file.name, 0o600)
    os.unlink(key_encrypted_file.name)

    return cert_file.name, key_file.name
```

#### `mcp_server/api_client.py`

```python
from __future__ import annotations

import logging
from typing import Literal

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
        return response.json()

    def recall(self, payload: dict) -> dict:
        response = self._client.post(f"{self._base_url}/recall", json=payload)
        response.raise_for_status()
        return response.json()

    def summarize(self, payload: dict) -> dict:
        response = self._client.post(f"{self._base_url}/summarize", json=payload)
        response.raise_for_status()
        return response.json()

    def close(self) -> None:
        self._client.close()
```

#### `mcp_server/tools.py`

```python
from __future__ import annotations

from typing import Literal


# Tool input schemas for MCP registration
STORE_MEMORY_SCHEMA = {
    "type": "object",
    "properties": {
        "text": {"type": "string", "description": "The memory text to store"},
        "scope": {
            "type": "string",
            "enum": ["project", "global"],
            "description": "Memory scope: 'project' for project-specific, 'global' for cross-project",
        },
        "project_id": {
            "type": "string",
            "description": "Project identifier (required if scope is 'project')",
        },
        "conversation_id": {
            "type": "string",
            "description": "Current conversation identifier",
        },
        "trigger": {
            "type": "string",
            "description": "What triggered this store: 'explicit', 'session_end', 'compact_auto', 'compact_manual'",
            "default": "explicit",
        },
    },
    "required": ["text", "scope", "conversation_id"],
}

RECALL_MEMORY_SCHEMA = {
    "type": "object",
    "properties": {
        "query": {"type": "string", "description": "Semantic search query"},
        "project_id": {
            "type": "string",
            "description": "Project identifier. If provided, searches both project and global memories.",
        },
        "top_k": {
            "type": "integer",
            "description": "Number of results to return",
            "default": 5,
        },
        "scope_filter": {
            "type": "string",
            "enum": ["project", "global"],
            "description": "Filter results to a specific scope",
        },
    },
    "required": ["query"],
}

SUMMARIZE_MEMORIES_SCHEMA = {
    "type": "object",
    "properties": {
        "scope": {
            "type": "string",
            "enum": ["project", "global"],
            "description": "Which scope to summarize",
        },
        "project_id": {
            "type": "string",
            "description": "Project identifier (required if scope is 'project')",
        },
        "delete_originals": {
            "type": "boolean",
            "description": "Whether to delete the original memories after summarizing",
            "default": False,
        },
    },
    "required": ["scope"],
}
```

#### `mcp_server/server.py`

```python
from __future__ import annotations

import atexit
import json
import logging
import os
import sys

from mcp.server import Server
from mcp.server.stdio import stdio_server
from mcp.types import TextContent, Tool

from .api_client import MemoryAPIClient
from .cert_loader import load_client_cert, write_temp_cert_files
from .tools import RECALL_MEMORY_SCHEMA, STORE_MEMORY_SCHEMA, SUMMARIZE_MEMORIES_SCHEMA

logging.basicConfig(level=logging.INFO, stream=sys.stderr)
logger = logging.getLogger(__name__)

app = Server("engram-memory")


def create_api_client() -> MemoryAPIClient:
    """Initialize the mTLS API client with certs from Secrets Manager."""
    region = os.environ.get("AWS_REGION", "us-east-1")
    base_url = os.environ["MEMORY_API_URL"]

    bundle = load_client_cert(region)
    cert_path, key_path = write_temp_cert_files(bundle)

    # Register cleanup for temp cert files
    def cleanup() -> None:
        for path in (cert_path, key_path):
            try:
                os.unlink(path)
            except OSError:
                pass

    atexit.register(cleanup)

    return MemoryAPIClient(base_url, cert_path, key_path)


_client: MemoryAPIClient | None = None


def get_client() -> MemoryAPIClient:
    global _client
    if _client is None:
        _client = create_api_client()
    return _client


@app.list_tools()
async def list_tools() -> list[Tool]:
    return [
        Tool(
            name="store_memory",
            description="Store a memory for later recall. Use at session end, when explicitly asked to remember something, or for important decisions and preferences.",
            inputSchema=STORE_MEMORY_SCHEMA,
        ),
        Tool(
            name="recall_memory",
            description="Search stored memories by semantic similarity. Use to recall past decisions, preferences, context, and technical details.",
            inputSchema=RECALL_MEMORY_SCHEMA,
        ),
        Tool(
            name="summarize_memories",
            description="Compress multiple memories into a summary. Used by the daily automation; can also be triggered manually.",
            inputSchema=SUMMARIZE_MEMORIES_SCHEMA,
        ),
    ]


@app.call_tool()
async def call_tool(name: str, arguments: dict) -> list[TextContent]:
    client = get_client()

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

    except Exception as e:
        logger.exception("Tool %s failed", name)
        return [TextContent(type="text", text=f"Error: {e}")]


async def main() -> None:
    async with stdio_server() as (read_stream, write_stream):
        await app.run(read_stream, write_stream, app.create_initialization_options())


if __name__ == "__main__":
    import asyncio
    asyncio.run(main())
```

### Claude Code MCP Configuration

Add the `mcpServers` key to `~/.claude.json` (Claude Code's global config). Do not replace existing content.

```json
{
  "mcpServers": {
    "engram-memory": {
      "command": "python",
      "args": ["-m", "mcp_server.server"],
      "cwd": "<path-to-engram-repo>",
      "env": {
        "MEMORY_API_URL": "https://memory.<your-domain>"
      }
    }
  }
}
```

## Terraform Variables

None. No Terraform resources in this phase.

## Terraform Outputs

None.

## Security Controls

- **Secrets Manager access:** The local AWS CLI profile needs `secretsmanager:GetSecretValue` on exactly `engram/mcp-client-cert*` and `engram/mcp-client-cert-passphrase*`. Create a scoped IAM user or use SSO with a restrictive policy.
- **Private key in memory:** The cert bundle is fetched from Secrets Manager and written to temp files with `chmod 600` for httpx. Files are cleaned up on process exit via `atexit`. The key exists in process memory and temp files for the process lifetime only.
- **TLS verification:** httpx's `verify=True` (default) validates the server cert against system CA roots. Amazon Trust Services certs are trusted by default.
- **No credentials in config:** The MCP server config contains only the API URL and region. AWS credentials come from the environment (CLI profile, env vars, or instance metadata).
- **stderr logging:** All MCP server logs go to stderr, which appears in Claude Code's verbose log but not in Claude's context window.

## Implementation Steps

1. Create `mcp_server/__init__.py` (empty).
2. Create `mcp_server/cert_loader.py` with `load_client_cert` and `write_temp_cert_files`.
3. Create `mcp_server/api_client.py` with `MemoryAPIClient`.
4. Create `mcp_server/tools.py` with tool schemas.
5. Create `mcp_server/server.py` with MCP server entry point.
6. Install dependencies:
   ```bash
   pip install mcp httpx boto3 pydantic
   ```
7. Test the server starts and lists tools:
   ```bash
   cd <path-to-engram-repo>
   MEMORY_API_URL=https://memory.<your-domain> python -m mcp_server.server
   ```
   (It will wait for stdin input via the MCP stdio protocol.)
8. Add `mcpServers` key to `~/.claude.json` with the engram-memory server config.
9. Restart Claude Code and verify the three tools appear.
10. Test a round-trip: ask Claude to store a memory, then recall it.

## Acceptance Criteria

```bash
# Verify MCP server starts without errors
cd <path-to-engram-repo>
timeout 5 python -c "from mcp_server.server import app; print('Server module loads')" 2>&1
# Expected: "Server module loads"

# Verify cert loader works (requires AWS credentials)
python -c "
from mcp_server.cert_loader import load_client_cert
bundle = load_client_cert('us-east-1')
print(f'Cert loaded: {len(bundle.cert_pem)} bytes')
print(f'Key loaded: {len(bundle.key_pem)} bytes')
"
# Expected: non-zero byte counts

# Verify tools are listed in Claude Code
# (manual check: open Claude Code, verify store_memory/recall_memory/summarize_memories appear)

# Integration test: store and recall
# (manual check in Claude Code: "Remember that I prefer ECDSA P-256 for new certificates")
# Then in a new conversation: "What are my certificate preferences?"
# Expected: Claude uses recall_memory and retrieves the stored preference

# Run MCP unit tests
pytest tests/mcp/ -v
# Expected: all pass
```

## Notes

- The MCP server runs as a child process of Claude Code. It starts when Claude Code starts (or when the first tool call is made, depending on the MCP SDK version).
- If the server crashes, Claude Code will show an error and tools will be unavailable. Check stderr output in Claude Code's verbose logs.
- The `write_temp_cert_files` function creates temp files because httpx requires file paths for mTLS client certs. There is no way to pass PEM strings directly. The files are cleaned up on exit.
- For claude.ai (web), the MCP server configuration is different (uses the MCP settings in the Claude UI). The server code is the same.
- The `cwd` in the MCP config must point to the engram project root so `python -m mcp_server.server` resolves correctly. Alternatively, install the package with `pip install -e .` and use the absolute module path.
