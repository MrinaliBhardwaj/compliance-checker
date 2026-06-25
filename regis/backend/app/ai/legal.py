"""
Legal-update summarization seam (optional). Turns a raw circular/notification into
a plain-language summary + impact note. Content team reviews before publish (the
publish action IS the human gate). No key -> caller must supply a summary; matching
and review still work deterministically.
"""
from __future__ import annotations

from app.ai import llm

_SYSTEM = (
    "You summarize an Indian NBFC regulatory circular for a compliance officer. "
    "Return JSON: {\"summary\": <plain-language, 3-4 sentences>, "
    "\"impact_note\": <what the NBFC must do differently>}. "
    "Do not give legal advice or definitive compliance verdicts; describe the change only."
)


def available() -> bool:
    return llm.available()


def summarize(raw_text: str) -> dict:
    """Returns {summary, impact_note}. Requires a model; gate on available()."""
    if not llm.available():
        raise RuntimeError("Legal summarization requires REGIS_ANTHROPIC_API_KEY.")
    return llm.complete_json(_SYSTEM, raw_text[:12000], max_tokens=800)
