"""LLM-generated narrative insight for reports.

Mirrors a production pattern: LLM calls are unreliable, so every
integration must degrade gracefully. Three failure modes are handled
explicitly — no API key, an API/network error, and an unparseable
response — all falling back to a safe default rather than raising.
"""

from __future__ import annotations

import os
from typing import Any, TypedDict

FALLBACK_INSIGHT: dict[str, Any] = {
    "summary": "AI narrative unavailable this run.",
    "watch_items": [],
}

SYSTEM_PROMPT = (
    "You are a senior data analyst at a telecom company writing a short, "
    "factual narrative for an internal ops report. Use only the numbers "
    "given in the data. Do not invent figures."
)

INSIGHT_SCHEMA = {
    "type": "object",
    "properties": {
        "summary": {"type": "string", "description": "2-3 sentence summary of what stands out"},
        "watch_items": {
            "type": "array",
            "items": {"type": "string"},
            "description": "Up to 3 short (<=12 word) items worth watching",
        },
    },
    "required": ["summary", "watch_items"],
    "additionalProperties": False,
}


class Insight(TypedDict):
    summary: str
    watch_items: list[str]


def _client():
    if not os.environ.get("ANTHROPIC_API_KEY"):
        return None
    import anthropic

    return anthropic.Anthropic()


def generate_insight(stats: dict[str, Any]) -> Insight:
    """Generate a narrative insight from report stats, degrading gracefully on failure."""
    client = _client()
    if client is None:
        return dict(FALLBACK_INSIGHT)  # type: ignore[return-value]

    try:
        response = client.messages.create(
            model="claude-opus-5",
            max_tokens=1024,
            output_config={
                "effort": "low",
                "format": {"type": "json_schema", "schema": INSIGHT_SCHEMA},
            },
            system=SYSTEM_PROMPT,
            messages=[{"role": "user", "content": f"DATA:\n{stats}"}],
        )
    except Exception:  # LLM calls must never crash the report pipeline
        return dict(FALLBACK_INSIGHT)  # type: ignore[return-value]

    if response.stop_reason == "refusal":
        return dict(FALLBACK_INSIGHT)  # type: ignore[return-value]

    text_block = next((b for b in response.content if b.type == "text"), None)
    if text_block is None:
        return dict(FALLBACK_INSIGHT)  # type: ignore[return-value]

    import json

    try:
        result = json.loads(text_block.text)
    except json.JSONDecodeError:
        return dict(FALLBACK_INSIGHT)  # type: ignore[return-value]

    for key, default in FALLBACK_INSIGHT.items():
        result.setdefault(key, default)
    return result
