"""Thin wrapper around RapidOCR (ONNX) — small models, low RAM.

The engine is created lazily on first use and kept as a singleton so the
models stay loaded between requests (cold start pays the load cost once).
"""
from __future__ import annotations

import io
import threading

import numpy as np
from PIL import Image

_engine = None
_lock = threading.Lock()


def _get_engine():
    global _engine
    if _engine is None:
        with _lock:
            if _engine is None:
                from rapidocr_onnxruntime import RapidOCR

                _engine = RapidOCR()
    return _engine


def _load_image(data: bytes, content_type: str | None) -> Image.Image:
    """Decode an uploaded file (image or first page of a PDF) to RGB."""
    if content_type == "application/pdf" or data[:4] == b"%PDF":
        import fitz  # PyMuPDF

        doc = fitz.open(stream=data, filetype="pdf")
        try:
            page = doc.load_page(0)
            pix = page.get_pixmap(dpi=200)
            return Image.frombytes("RGB", (pix.width, pix.height), pix.samples)
        finally:
            doc.close()
    return Image.open(io.BytesIO(data)).convert("RGB")


def ocr_upload(data: bytes, content_type: str | None) -> tuple[list[str], float]:
    """Run OCR; returns (text lines in reading order, mean confidence)."""
    img = _load_image(data, content_type)
    arr = np.asarray(img)
    engine = _get_engine()
    result, _ = engine(arr)
    if not result:
        return [], 0.0
    items = []
    for box, text, score in result:
        y = min(p[1] for p in box)
        x = min(p[0] for p in box)
        items.append((y, x, text, float(score)))
    # group into visual rows (12px tolerance) then left-to-right
    items.sort(key=lambda t: (round(t[0] / 12), t[1]))
    lines = [t[2] for t in items]
    mean_conf = sum(t[3] for t in items) / len(items) if items else 0.0
    return lines, round(mean_conf, 4)
