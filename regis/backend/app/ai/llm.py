"""
Single Claude client wrapper. Sonnet for all V1 AI (PRD §12).

Kept deliberately thin: the deterministic engines own correctness; the LLM only
(a) turns free text into questionnaire answers, (b) classifies/extracts documents,
(c) phrases grounded facts, (d) synthesizes RAG answers. Every call is closed-book
where grounding matters. `available()` lets callers fall back to deterministic
behaviour when no API key is set.
"""
from __future__ import annotations

import json
from typing import Any

from app.core.config import get_settings


def available() -> bool:
    return bool(get_settings().anthropic_api_key)


def _client():
    from anthropic import Anthropic
    return Anthropic(api_key=get_settings().anthropic_api_key)


def complete(system: str, user: str, *, max_tokens: int = 1024, temperature: float = 0.0) -> str:
    """Single-shot completion. Raises if no key — callers should gate on available()."""
    if not available():
        raise RuntimeError("No Anthropic API key configured (REGIS_ANTHROPIC_API_KEY).")
    msg = _client().messages.create(
        model=get_settings().anthropic_model,
        max_tokens=max_tokens, temperature=temperature,
        system=system, messages=[{"role": "user", "content": user}],
    )
    return "".join(block.text for block in msg.content if block.type == "text")


def complete_json(system: str, user: str, *, max_tokens: int = 1024) -> dict[str, Any]:
    """Strict-JSON completion; parses the model's response into a dict."""
    raw = complete(system + "\n\nRespond with valid JSON only.", user, max_tokens=max_tokens)
    raw = raw.strip().removeprefix("```json").removeprefix("```").removesuffix("```").strip()
    return json.loads(raw)
