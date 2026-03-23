"""LLM tool schema helpers for scenarios that use LLM-based inference."""

from __future__ import annotations


def tool_schema(name: str, description: str, parameters: dict | None = None) -> dict:
    """Build an OpenAI-compatible function tool schema."""
    params = parameters or {}
    return {
        "type": "function",
        "function": {
            "name": name,
            "description": description,
            "parameters": {
                "type": "object",
                "properties": params,
                "required": list(params.keys()),
            },
        },
    }
