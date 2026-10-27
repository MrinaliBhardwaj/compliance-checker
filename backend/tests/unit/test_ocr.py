"""Unit tests — text extraction for uploaded evidence (the `ocr` extra)."""

import io
import shutil

import pytest

from app.ai import ocr


def test_text_pdf_is_extracted():
    from reportlab.pdfgen import canvas

    buf = io.BytesIO()
    c = canvas.Canvas(buf)
    c.drawString(72, 720, "TDS challan ITNS 281 for July 2026")
    c.save()
    text, conf = ocr.extract_text(buf.getvalue(), "application/pdf")
    assert "ITNS 281" in text and conf > 0.9


def test_docx_is_extracted():
    import docx

    d = docx.Document()
    d.add_paragraph("Board resolution approving the annual return")
    buf = io.BytesIO()
    d.save(buf)
    text, conf = ocr.extract_text(
        buf.getvalue(),
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    )
    assert "Board resolution" in text and conf > 0.9


@pytest.mark.skipif(shutil.which("tesseract") is None, reason="tesseract binary not installed")
def test_image_is_ocrd():
    from PIL import Image, ImageDraw, ImageFont

    img = Image.new("RGB", (900, 120), "white")
    try:
        font = ImageFont.truetype("DejaVuSans.ttf", 48)
    except OSError:
        font = ImageFont.load_default()
    ImageDraw.Draw(img).text((20, 30), "CHALLAN 281", fill="black", font=font)
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    text, conf = ocr.extract_text(buf.getvalue(), "image/png")
    assert "CHALLAN" in text.upper() and conf > 0
