# Copyright (c) 2026 Engram Contributors. All Rights Reserved.
# Licensed under the MIT License. See LICENSE for details.
from __future__ import annotations

STORE_MEMORY_SCHEMA: dict = {
    "type": "object",
    "properties": {
        "text": {"type": "string", "description": "The memory text to store"},
        "tags": {
            "type": "array",
            "items": {"type": "string"},
            "description": (
                "Tag list for this memory. Use namespaced tags: 'project:engram', "
                "'scope:global', 'scope:project', 'technology:terraform', etc. "
                "memory_type tag is auto-injected from the memory_type field."
            ),
            "default": [],
        },
        "trigger": {
            "type": "string",
            "description": (
                "What triggered this store: 'explicit', 'session_end', "
                "'compact_auto', 'compact_manual'"
            ),
            "default": "explicit",
        },
        "memory_type": {
            "type": "string",
            "enum": ["task", "decision", "discovery", "rule", "preference", "context"],
            "description": (
                "Classify the memory: 'task' for completed work items (prunable), "
                "'decision' for architectural/design choices, 'discovery' for learned facts, "
                "'rule' for enforced standards, 'preference' for user preferences, "
                "'context' for general context (default)."
            ),
            "default": "context",
        },
    },
    "required": ["text"],
}

RECALL_MEMORY_SCHEMA: dict = {
    "type": "object",
    "properties": {
        "query": {"type": "string", "description": "Semantic search query"},
        "top_k": {
            "type": "integer",
            "description": "Number of results to return",
            "default": 5,
        },
        "weights": {
            "type": "object",
            "additionalProperties": {"type": "number"},
            "description": (
                "Tag weight multipliers for re-ranking. Keys are tag strings (e.g. 'project:engram', "
                "'memory_type:decision'). Values > 1.0 boost matching memories; < 1.0 suppress. "
                "Example: {\"project:engram\": 1.5, \"memory_type:decision\": 1.2}"
            ),
            "default": {},
        },
    },
    "required": ["query"],
}

SUMMARIZE_MEMORIES_SCHEMA: dict = {
    "type": "object",
    "properties": {
        "tag_filter": {
            "type": "array",
            "items": {"type": "string"},
            "description": (
                "If provided, only summarize memories that have ALL matching tags. "
                "Empty list summarizes all memories."
            ),
            "default": [],
        },
        "delete_originals": {
            "type": "boolean",
            "description": "Whether to delete the original memories after summarizing",
            "default": False,
        },
    },
    "required": [],
}

DELETE_MEMORY_SCHEMA: dict = {
    "type": "object",
    "properties": {
        "memory_id": {
            "type": "string",
            "description": "The ID of the memory to delete (UUID from recall_memory result)",
        },
    },
    "required": ["memory_id"],
}

PRUNE_MEMORIES_SCHEMA: dict = {
    "type": "object",
    "properties": {
        "tag_filter": {
            "type": "array",
            "items": {"type": "string"},
            "description": (
                "If provided, only prune memories that have ALL matching tags. "
                "Example: [\"scope:project\", \"project:engram\"] to prune only engram project memories."
            ),
            "default": [],
        },
        "older_than_days": {
            "type": "integer",
            "description": "Only prune memories older than this many days",
            "default": 30,
        },
        "memory_types": {
            "type": "array",
            "items": {"type": "string", "enum": ["task", "decision", "discovery", "rule", "preference", "context"]},
            "description": "Memory types eligible for pruning. Defaults to ['task'] only.",
            "default": ["task"],
        },
        "dry_run": {
            "type": "boolean",
            "description": "If true, return candidates without deleting. Always run dry_run=true first.",
            "default": True,
        },
    },
    "required": [],
}

SEARCH_RELATED_FINDINGS_SCHEMA: dict = {
    "type": "object",
    "properties": {
        "memory_id": {
            "type": "string",
            "description": "The ID of the anchor memory (UUID from recall_memory result)",
        },
        "window_minutes": {
            "type": "integer",
            "description": "Time window in minutes around the anchor memory to search for neighbors",
            "default": 5,
        },
    },
    "required": ["memory_id"],
}
