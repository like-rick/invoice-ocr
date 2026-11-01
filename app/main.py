"""C1 — Invoice / receipt OCR to structured JSON.

POST /v1/ocr   (multipart file upload; header X-API-Key when API_KEY is set)
GET  /health
"""
from __future__ import annotations

import os
import time

from fastapi import Depends, FastAPI, File, Header, HTTPException, UploadFile

from .extract import extract_fields
from .ocr_engine import ocr_upload

API_KEY = os.environ.get("API_KEY", "")
MAX_BYTES = 10 * 1024 * 1024
ALLOWED_TYPES = {"image/jpeg", "image/png", "image/webp", "image/bmp", "application/pdf"}

app = FastAPI(title="Invoice OCR API", version="0.1.0")


def require_key(x_api_key: str | None = Header(default=None)):
    if API_KEY and x_api_key != API_KEY:
        raise HTTPException(status_code=401, detail="invalid or missing API key")


@app.get("/health")
def health():
    return {"status": "ok"}


@app.post("/v1/ocr", dependencies=[Depends(require_key)])
async def ocr(file: UploadFile = File(...)):
    if file.content_type and file.content_type not in ALLOWED_TYPES:
        raise HTTPException(status_code=415, detail=f"unsupported content type: {file.content_type}")
    data = await file.read()
    if len(data) > MAX_BYTES:
        raise HTTPException(status_code=413, detail="file too large (max 10 MB)")
    if not data:
        raise HTTPException(status_code=400, detail="empty file")
    t0 = time.time()
    try:
        lines, conf = ocr_upload(data, file.content_type)
    except Exception as e:  # decode / render errors surface as 422
        raise HTTPException(status_code=422, detail=f"could not process file: {e}") from e
    fields = extract_fields(lines)
    return {
        "ok": True,
        "fields": fields,
        "raw_text": lines,
        "mean_confidence": conf,
        "elapsed_ms": int((time.time() - t0) * 1000),
    }
