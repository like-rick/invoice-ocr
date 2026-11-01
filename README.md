# C1 — Invoice OCR API （发票/收据 OCR → 结构化 JSON)

Upload a Chinese VAT invoice or receipt (image or PDF) and get structured
fields back as JSON: invoice number, date, buyer/seller names,
amount / tax / total, plus the raw OCR text.

## API

- `GET /health` → `{"status": "ok"}`
- `POST /v1/ocr` — multipart form field `file` (jpg/png/webp/bmp/pdf, ≤10 MB)
  - Header `X-API-Key: <key>` required when the `API_KEY` env var is set.

Example response:

```json
{
  "ok": true,
  "fields": {
    "invoice_code": "011002200711",
    "invoice_number": "83746512",
    "issue_date": "2026-10-28",
    "buyer_name": "北京云启科技有限公司",
    "seller_name": "上海明州信息技术有限公司",
    "amount_excl_tax": 943.40,
    "tax_amount": 56.60,
    "total_amount": 1000.00,
    "currency": "CNY"
  },
  "raw_text": ["..."],
  "mean_confidence": 0.99,
  "elapsed_ms": 850
}
```

## Run locally

```bash
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
API_KEY=demo .venv/bin/uvicorn app.main:app --port 8000
curl -H "X-API-Key: demo" -F file=@tests/test_invoice.png localhost:8000/v1/ocr
```

## Deploy on Railway

1. New Project → deploy this directory (GitHub repo or `railway up`).
2. Start command comes from `Procfile` (uvicorn on `$PORT`).
3. Set env var `API_KEY` to a secret of your choice.
4. Trial plan (1 GB RAM) fits the OCR engine; the post-trial Free plan
   (0.5 GB) is tight — measure before relying on it.
