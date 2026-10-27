"""
AI layer — the engines' stubbed seams, wired to real providers here.

Hard rule (PRD §1.3, §7): all AI is assistive, read-only, human-confirmed. Nothing
in this package writes a terminal compliance state or takes an external action. The
deterministic engines never import a provider directly — they call these interfaces,
which degrade gracefully when no model/key is configured (so tests and local dev run
offline).
"""
