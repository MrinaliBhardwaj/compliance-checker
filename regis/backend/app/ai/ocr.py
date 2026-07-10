"""
OCR adapter (spec §4). Text-PDF -> direct text; scanned -> Tesseract; office ->
native extraction. Returns (text, mean_confidence). Cloud-OCR can be slotted in
behind this same signature. Dependencies are optional; absence yields empty text
with confidence 0.0 so the OCR-quality gate routes the doc to manual review.
"""
from __future__ import annotations


def extract_text(file_bytes: bytes, mime: str) -> tuple[str, float]:
    mime = (mime or "").lower()
    try:
        if "pdf" in mime:
            return _pdf(file_bytes)
        if mime.startswith("image/"):
            return _image(file_bytes)
        if "word" in mime or mime.endswith("document"):
            return _docx(file_bytes)
    except Exception:
        return "", 0.0
    return "", 0.0


def _pdf(b: bytes) -> tuple[str, float]:
    try:
        import io

        from pypdf import PdfReader  # type: ignore
        reader = PdfReader(io.BytesIO(b))
        text = "\n".join((p.extract_text() or "") for p in reader.pages)
        if text.strip():
            return text, 0.95  # embedded text-PDF: high confidence, no OCR needed
    except Exception:
        pass
    return _image(b)  # fall back to rasterize + OCR


def _image(b: bytes) -> tuple[str, float]:
    try:
        import io

        import pytesseract  # type: ignore
        from PIL import Image  # type: ignore
        img = Image.open(io.BytesIO(b))
        data = pytesseract.image_to_data(img, output_type=pytesseract.Output.DICT)
        confs = [int(c) for c in data.get("conf", []) if str(c).lstrip("-").isdigit() and int(c) >= 0]
        text = " ".join(w for w in data.get("text", []) if w.strip())
        mean = (sum(confs) / len(confs) / 100.0) if confs else 0.0
        return text, mean
    except Exception:
        return "", 0.0


def _docx(b: bytes) -> tuple[str, float]:
    try:
        import io

        import docx  # type: ignore
        d = docx.Document(io.BytesIO(b))
        return "\n".join(p.text for p in d.paragraphs), 0.95
    except Exception:
        return "", 0.0
