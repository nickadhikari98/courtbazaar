"""Shared file-metadata detection — currently just page counting.

Extracted out of server.py's /files/upload so hearings.py's document upload
(POST /hearing-requests/{id}/documents) can compute the same real page_count
at upload time instead of the two upload flows drifting apart (db.files had
this from day one; db.hearing_documents never did, which is why hearing
uploads showed no page count at all)."""
import logging

logger = logging.getLogger(__name__)


def detect_page_count(filename: str, content_type: str, data: bytes) -> int:
    page_count = 1
    try:
        fn = (filename or "").lower()
        ct = (content_type or "").lower()
        if "pdf" in ct or fn.endswith(".pdf"):
            import io as _io
            page_count = 0
            # 1) Try PyPDF2 (works for normal PDFs with structure intact)
            try:
                from PyPDF2 import PdfReader
                reader = PdfReader(_io.BytesIO(data))
                page_count = len(reader.pages)
            except Exception as e:
                logger.warning(f"PyPDF2 page count failed: {e}")
            # 2) Fallback to pdfinfo / pdf2image for scanned or malformed PDFs
            if page_count == 0:
                try:
                    from pdf2image.pdf2image import pdfinfo_from_bytes
                    info = pdfinfo_from_bytes(data, userpw=None)
                    page_count = int(info.get("Pages", 0))
                except Exception as e:
                    logger.warning(f"pdfinfo fallback failed: {e}")
            # 3) Last-resort: count "/Type /Page" markers in raw bytes
            if page_count == 0:
                try:
                    page_count = max(1, data.count(b"/Type /Page") - data.count(b"/Type /Pages"))
                except Exception:
                    page_count = 1
            page_count = max(1, page_count)
        elif "tiff" in ct or fn.endswith((".tif", ".tiff")):
            # Multi-page TIFF support
            try:
                from PIL import Image
                import io as _io
                img = Image.open(_io.BytesIO(data))
                page_count = getattr(img, "n_frames", 1) or 1
            except Exception:
                page_count = 1
        elif "image" in ct or any(fn.endswith(e) for e in [".jpg", ".jpeg", ".png", ".bmp", ".webp", ".heic", ".heif"]):
            page_count = 1
        elif "officedocument" in ct or fn.endswith((".docx", ".doc")):
            try:
                from docx import Document
                import io as _io
                doc = Document(_io.BytesIO(data))
                total_chars = sum(len(p.text) for p in doc.paragraphs)
                page_count = max(1, total_chars // 3000)
            except Exception:
                page_count = max(1, len(data) // 50000)
    except Exception as e:
        logger.error(f"Page count detection failed: {e}")
        page_count = 1
    return page_count
