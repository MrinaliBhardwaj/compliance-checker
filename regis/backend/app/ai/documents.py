"""
Document classification + extraction (the engine's `classify_and_extract` seam).

Pipeline (spec §4): MIME route -> OCR if scanned -> LLM strict-JSON extraction to
the canonical schema -> {doc_type, classification_confidence, fields}. The
deterministic validation / dedupe / completeness all run AFTER this, on the result.

AI SUGGESTS; the human confirms the link (Maker-Checker unchanged).
"""
from __future__ import annotations

from app.ai import llm, ocr
from app.engines.document_intelligence import COMMON_FIELDS, TYPE_FIELDS, DocType

_SYSTEM = (
    "You classify an Indian NBFC compliance document and extract structured fields. "
    "Choose exactly one document type from this set: "
    + ", ".join(t.value for t in DocType) + ". "
    "Return JSON: {\"doc_type\": <TYPE>, \"classification_confidence\": <0..1>, "
    "\"fields\": {<field>: {\"value\": ..., \"confidence\": <0..1>}}}. "
    "Only use fields relevant to the type. Do not invent values; omit unknown fields."
)


def classify_and_extract(file_bytes: bytes, mime: str, hint: dict | None = None) -> dict:
    """
    Returns {doc_type, classification_confidence, fields}. Requires a configured
    model; the upload job catches the no-key case and parks the document as
    `unprocessed` for manual classification rather than blocking the upload.
    """
    if not llm.available():
        raise RuntimeError(
            "Document AI requires REGIS_ANTHROPIC_API_KEY. Document saved as "
            "'unprocessed' for manual classification.")

    text, ocr_conf = ocr.extract_text(file_bytes, mime)
    expected = ", ".join(COMMON_FIELDS + sum(TYPE_FIELDS.values(), []))
    hint_line = f"\nThe user uploaded this against: {hint}" if hint else ""
    user = (f"Candidate fields: {expected}.{hint_line}\n\nDocument text:\n{text[:8000]}")

    result = llm.complete_json(_SYSTEM, user, max_tokens=1500)
    result.setdefault("fields", {})
    result["_ocr_confidence"] = ocr_conf
    return result
