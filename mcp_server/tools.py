# Copyright (c) 2026 Brad Duhon. All Rights Reserved.
# Confidential and Proprietary.
# Unauthorized copying of this file is strictly prohibited.
from __future__ import annotations

STORE_MEMORY_SCHEMA: dict = {
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
            "description": (
                "What triggered this store: 'explicit', 'session_end', "
                "'compact_auto', 'compact_manual'"
            ),
            "default": "explicit",
        },
    },
    "required": ["text", "scope", "conversation_id"],
}

RECALL_MEMORY_SCHEMA: dict = {
    "type": "object",
    "properties": {
        "query": {"type": "string", "description": "Semantic search query"},
        "project_id": {
            "type": "string",
            "description": (
                "Project identifier. If provided, searches both project and global memories."
            ),
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

SUMMARIZE_MEMORIES_SCHEMA: dict = {
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
