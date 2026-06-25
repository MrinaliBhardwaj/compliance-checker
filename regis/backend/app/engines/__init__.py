"""
Deterministic compliance engines (Phase 1).

These modules are ported VERBATIM from the verified reference implementations in
`/Compliance docs`. They are pure functions over dict/JSON inputs — no DB, no I/O.
The AI/LLM/OCR/RAG seams live in `app.ai` and are injected, never hardcoded here.

The golden outputs these reproduce (locked as regression tests in tests/golden):
  - applicability:  A=69/1/39/22, B=100/1/13/26, C=61/27/18
  - instances (B):  367 dated, 21 event-driven, 3 continuous, 92 working-day-adjusted
  - extraction:     clean -> 99 applicable downstream
  - documents:      192 evidence mapped, 3 OTHER (98.4%)
  - copilot:        admin 18 vs preparer 13; structured 0.97; unverified 0.70 provisional
"""
