"""Real OCR + PDF analysis pipeline using Tesseract + PyPDF2 + pdf2image.
Feeds extracted text into the Doc Intelligence engine for accurate scoring."""
import io
import logging
from typing import Tuple, Optional

logger = logging.getLogger(__name__)


def extract_pdf_text(data: bytes) -> Tuple[str, int]:
    """Extract text from PDF using PyPDF2. Returns (text, page_count)."""
    try:
        from PyPDF2 import PdfReader
        reader = PdfReader(io.BytesIO(data))
        page_count = len(reader.pages)
        chunks = []
        for i, page in enumerate(reader.pages):
            try:
                t = page.extract_text() or ""
                chunks.append(t)
            except Exception:
                chunks.append("")
        return "\n".join(chunks), page_count
    except Exception as e:
        logger.error(f"PDF extract failed: {e}")
        return "", 0


def ocr_image(data: bytes) -> str:
    """Run Tesseract OCR on an image bytes."""
    try:
        from PIL import Image
        import pytesseract
        img = Image.open(io.BytesIO(data))
        return pytesseract.image_to_string(img, lang="eng")
    except Exception as e:
        logger.error(f"OCR image failed: {e}")
        return ""


def ocr_pdf_pages(data: bytes, max_pages: int = 5) -> str:
    """Convert PDF pages to images and run OCR. Heavy, so limit pages."""
    try:
        from pdf2image import convert_from_bytes
        import pytesseract
        images = convert_from_bytes(data, dpi=150, first_page=1, last_page=max_pages)
        out = []
        for img in images:
            out.append(pytesseract.image_to_string(img, lang="eng"))
        return "\n\n".join(out)
    except Exception as e:
        logger.error(f"OCR PDF failed: {e}")
        return ""


def analyze_document(data: bytes, content_type: str, filename: str = "") -> dict:
    """Analyze a document and return text + heuristic scores.
    Returns: { text: str, page_count: int, has_text_layer: bool, char_count: int,
               ocr_used: bool, page_numbers_detected: int, image_ratio_estimate: float }"""
    text = ""
    page_count = 0
    ocr_used = False
    has_text_layer = False

    ct = (content_type or "").lower()
    if "pdf" in ct or filename.lower().endswith(".pdf"):
        text, page_count = extract_pdf_text(data)
        if text and len(text.strip()) > 50:
            has_text_layer = True
        else:
            # Likely scanned PDF — run OCR on first few pages
            text = ocr_pdf_pages(data, max_pages=5)
            ocr_used = True
    elif "image" in ct or any(filename.lower().endswith(e) for e in [".jpg", ".jpeg", ".png", ".tiff", ".bmp"]):
        text = ocr_image(data)
        ocr_used = True
        page_count = 1
    else:
        try:
            text = data.decode("utf-8", errors="ignore")[:50000]
        except Exception:
            text = ""

    char_count = len(text)
    # Heuristic: detect page numbers (look for "Page X", "X of Y", or standalone numbers)
    import re
    page_num_hits = len(re.findall(r"(?:Page\s+\d+|^\s*\d+\s*$|\d+\s*of\s*\d+)", text, re.IGNORECASE | re.MULTILINE))

    return {
        "text": text[:8000],  # truncate for LLM context
        "text_preview": text[:500],
        "page_count": page_count,
        "has_text_layer": has_text_layer,
        "char_count": char_count,
        "ocr_used": ocr_used,
        "page_numbers_detected": page_num_hits,
    }
