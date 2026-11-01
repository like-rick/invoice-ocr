"""Rule-based field extraction for Chinese VAT invoices / receipts.

Input: OCR text lines in reading order.
Output: dict of structured fields; missing fields are None.
Deliberately deterministic (no LLM): cheap, fast, predictable.
"""
from __future__ import annotations

import re

MONEY_RE = re.compile(r"[¥￥]\s*([0-9][0-9,]*\.[0-9]{2})")
DATE_RE = re.compile(r"(\d{4})\s*年\s*(\d{1,2})\s*月\s*(\d{1,2})\s*日")
LONG_DIGITS_RE = re.compile(r"\d{8,20}")


def _money_values(line: str) -> list[float]:
    return [float(m.replace(",", "")) for m in MONEY_RE.findall(line)]


def _after_label(line: str, label: str) -> str | None:
    if label in line:
        tail = line.split(label, 1)[1].strip(" ：:").strip()
        return tail or None
    return None


def _normalize(lines: list[str]) -> list[str]:
    """Merge OCR-split label characters (e.g. 合 / 计 on separate lines)."""
    out: list[str] = []
    i = 0
    while i < len(lines):
        if lines[i].strip() == "合" and i + 1 < len(lines) and lines[i + 1].strip() == "计":
            out.append("合计")
            i += 2
        else:
            out.append(lines[i])
            i += 1
    return out


def extract_fields(raw_lines: list[str]) -> dict:
    lines = _normalize(raw_lines)
    fields: dict = {
        "invoice_code": None,
        "invoice_number": None,
        "issue_date": None,
        "buyer_name": None,
        "seller_name": None,
        "amount_excl_tax": None,
        "tax_amount": None,
        "total_amount": None,
        "currency": "CNY",
    }
    names: list[str] = []

    for i, line in enumerate(lines):
        # --- identifiers -------------------------------------------------
        v = _after_label(line, "发票代码")
        if v and fields["invoice_code"] is None:
            m = LONG_DIGITS_RE.search(v)
            if m:
                fields["invoice_code"] = m.group(0)
        v = _after_label(line, "发票号码")
        if v and fields["invoice_number"] is None:
            m = LONG_DIGITS_RE.search(v)
            if m:
                fields["invoice_number"] = m.group(0)

        # --- date ---------------------------------------------------------
        if fields["issue_date"] is None and "开票日期" in line:
            m = DATE_RE.search(line) or (DATE_RE.search(lines[i + 1]) if i + 1 < len(lines) else None)
            if m:
                fields["issue_date"] = f"{m.group(1)}-{int(m.group(2)):02d}-{int(m.group(3)):02d}"

        # --- party names (buyer first, seller second on VAT invoices) -----
        if "名称" in line:
            v = _after_label(line, "名称")
            if v:
                # strip a trailing tax-id that OCR may have merged into the line
                v = re.split(r"纳税人识别号", v)[0].strip()
                if v and v not in names:
                    names.append(v)

        # --- totals --------------------------------------------------------
        if "价税合计" in line:
            vals = _money_values(line)
            if not vals and i + 1 < len(lines):
                vals = _money_values(lines[i + 1])
            if vals and fields["total_amount"] is None:
                fields["total_amount"] = vals[-1]
        elif "合计" in line:
            # money may sit on the label line or on the next few bare lines
            vals = _money_values(line)
            j = i + 1
            while len(vals) < 2 and j < len(lines) and j <= i + 4:
                nxt = lines[j]
                if any(k in nxt for k in ("价税合计", "名称", "销售方", "购买方")):
                    break
                vals += _money_values(nxt)
                j += 1
            if len(vals) >= 2:
                if fields["amount_excl_tax"] is None:
                    fields["amount_excl_tax"] = vals[0]
                if fields["tax_amount"] is None:
                    fields["tax_amount"] = vals[1]
            elif len(vals) == 1 and fields["amount_excl_tax"] is None:
                fields["amount_excl_tax"] = vals[0]

    if names:
        fields["buyer_name"] = names[0]
    if len(names) > 1:
        fields["seller_name"] = names[1]

    # Fallback: a standalone 20-digit number is a fully-digital e-invoice number
    if fields["invoice_number"] is None:
        for line in lines:
            for m in re.finditer(r"(?<!\d)(\d{20})(?!\d)", line):
                fields["invoice_number"] = m.group(1)
                break
            if fields["invoice_number"]:
                break

    # Fallback: explicitly labeled 金额 / 税额 values anywhere in the text
    if fields["amount_excl_tax"] is None or fields["tax_amount"] is None:
        for line in lines:
            vals = _money_values(line)
            if not vals:
                continue
            if fields["amount_excl_tax"] is None and "金额" in line and "价税" not in line:
                fields["amount_excl_tax"] = vals[0]
            if fields["tax_amount"] is None and "税额" in line:
                fields["tax_amount"] = vals[0]

    # Fallback: derive missing tax/total by arithmetic
    if fields["amount_excl_tax"] is not None and fields["total_amount"] is not None and fields["tax_amount"] is None:
        fields["tax_amount"] = round(fields["total_amount"] - fields["amount_excl_tax"], 2)
    if fields["amount_excl_tax"] is not None and fields["tax_amount"] is not None and fields["total_amount"] is None:
        fields["total_amount"] = round(fields["amount_excl_tax"] + fields["tax_amount"], 2)

    return fields
