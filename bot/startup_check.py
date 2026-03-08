"""Startup probe: verify that the configured API endpoint supports tool calling."""

from __future__ import annotations

import logging

import anthropic

logger = logging.getLogger(__name__)

_PROBE_TOOL = {
    "name": "probe",
    "description": "No-op probe for capability testing.",
    "input_schema": {
        "type": "object",
        "properties": {"value": {"type": "string"}},
        "required": ["value"],
    },
}


async def check_tool_calling() -> bool:
    """Return True if the API endpoint correctly handles tool-use requests."""
    client = anthropic.AsyncAnthropic()
    try:
        response = await client.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=64,
            tools=[_PROBE_TOOL],
            tool_choice={"type": "any"},
            messages=[{"role": "user", "content": "ping"}],
            timeout=30.0,
        )
    except Exception as exc:
        logger.error("Tool calling probe failed: %s", exc)
        return False

    ok = response.stop_reason == "tool_use" and any(
        getattr(b, "type", None) == "tool_use" for b in response.content
    )
    if not ok:
        logger.error(
            "Unexpected probe result: stop_reason=%r content=%r",
            response.stop_reason,
            response.content,
        )
    return ok
