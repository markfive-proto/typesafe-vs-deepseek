"""PDF/XLSX invoice extraction: TypeSafe multi-question pipeline vs DeepSeek-flash direct JSON, same task.

Born-digital PDFs/XLSX carry real text — no OCR/vision needed at all, just a native
text extraction library, then the same candidate-regex + TypeSafe Choice pattern
used for the photo invoices.
"""
import json
import os
import re
import urllib.request
from pathlib import Path

import openpyxl
import pdfplumber

import pipeline as P
from email_pipeline import DEEPSEEK_PRICE

ROOT = Path(__file__).parent
DOCS = ROOT / "invoice_docs"
GROUND_TRUTH = json.loads((DOCS / "ground_truth.json").read_text()) if (DOCS / "ground_truth.json").exists() else {}

CATEGORY_CRITERIA = {
    "goods": "physical products sold, priced per unit/quantity. Not billed on a recurring schedule (that's utilities_subscription).",
    "services": "professional/consulting/legal/design labor, billed per hour or per engagement. Not a physical item (goods) and not a recurring flat-rate subscription (utilities_subscription).",
    "utilities_subscription": "recurring hosting, utility, or subscription billing at a flat or usage-based recurring rate. Not a one-time purchase of goods or a one-off services engagement.",
}


def _grounded(value, source_text: str) -> bool:
    """Is `value` actually present in the source text, or did the model invent it?"""
    if value is None:
        return False
    needle = re.sub(r"[$,]", "", str(value)).strip().lower()
    haystack = re.sub(r"[$,]", "", source_text).lower()
    return needle in haystack


def extract_lines(path: Path) -> list[str]:
    if path.suffix.lower() == ".pdf":
        with pdfplumber.open(path) as pdf:
            text = "\n".join(page.extract_text() or "" for page in pdf.pages)
        return [l.strip() for l in text.splitlines() if l.strip()]
    if path.suffix.lower() == ".xlsx":
        wb = openpyxl.load_workbook(path, data_only=True)
        ws = wb.active
        lines = []
        for row in ws.iter_rows(values_only=True):
            cells = [str(c) for c in row if c is not None and str(c).strip()]
            if cells:
                lines.append("  ".join(cells))
        return lines
    raise ValueError(f"unsupported doc type: {path.suffix}")


def build_questions(lines: list[str], totals: list[str], dates: list[str], invnums: list[str]) -> dict:
    q = {}
    for i in range(len(lines)):
        q[f"line_{i}_type"] = {
            "type": "choice",
            "instructions": f"Classify `lines[{i}]` in an invoice.",
            "criteria": {
                "line_item": "A product/service row: description plus quantity or price/amount",
                "header_field": "Vendor name, invoice title, address",
                "total_field": "Subtotal, tax, invoice total",
                "noise": "Column labels (Qty/Price/Amount/Description), blank/stray text",
            },
        }
    if totals:
        q["total_amount"] = {
            "type": "choice",
            "instructions": "Which candidate in `totals` is the final invoice total / amount due (not a subtotal or tax line)?",
            "criteria": {t: f"the value {t}" for t in totals},
        }
    if dates:
        q["invoice_date"] = {
            "type": "choice",
            "instructions": "Which candidate in `dates` is the invoice's issue date?",
            "criteria": {d: f"the date {d}" for d in dates},
        }
    if invnums:
        q["invoice_number"] = {
            "type": "choice",
            "instructions": "Which candidate in `invoice_numbers` is the invoice number/ID?",
            "criteria": {n: f"the value {n}" for n in invnums},
        }
    q["category"] = {
        "type": "choice",
        "instructions": "What category of invoice is this, based on `lines`?",
        "criteria": CATEGORY_CRITERIA,
    }
    return q


def classify(name: str) -> dict:
    path = DOCS / name
    lines = extract_lines(path)
    totals = P.candidates(lines, P.MONEY_RE)
    dates = P.candidates(lines, P.DATE_RE)
    invnums = P.candidates(lines, re.compile(r"\bINV-\d{4,}\b"))
    state = {"lines": lines, "totals": totals, "dates": dates, "invoice_numbers": invnums}
    questions = build_questions(lines, totals, dates, invnums)
    result = P.call_typesafe(state, questions)
    answers = result["answers"]
    usage = result.get("usage", {})

    line_items = [lines[i] for i in range(len(lines)) if answers.get(f"line_{i}_type", {}).get("choice") == "line_item"]
    gt = GROUND_TRUTH.get(name, {})
    return {
        "file": name,
        "ground_truth": {"category": gt.get("category"), "total": gt.get("total"), "invoice_number": gt.get("invoice_number")},
        "category": answers.get("category", {}).get("choice"),
        "invoice_number": answers.get("invoice_number", {}).get("choice"),
        "invoice_date": answers.get("invoice_date", {}).get("choice"),
        "total_amount": answers.get("total_amount", {}).get("choice"),
        "total_confidence": answers.get("total_amount", {}).get("confidence"),
        "line_items": line_items,
        "tokens": {"input": usage.get("input_tokens"), "output": usage.get("output_tokens")},
        "cost_usd": P.typesafe_cost(usage),
        # Choice only ever returns a candidate value it was handed — structurally can't invent one.
        "hallucinated": False,
    }


DEEPSEEK_PROMPT = """Extract structured data from this invoice text.

Respond with ONLY a JSON object, no markdown, no commentary:
{{"category": "<one of: {categories}>", "invoice_number": "<string>", "total": <number>}}

Invoice text:
{text}"""


def classify_via_deepseek(name: str) -> dict:
    path = DOCS / name
    lines = extract_lines(path)
    text = "\n".join(lines)
    prompt = DEEPSEEK_PROMPT.format(categories=", ".join(CATEGORY_CRITERIA), text=text)
    req = urllib.request.Request(
        P.DEEPSEEK_URL,
        data=json.dumps({
            "model": "deepseek-flash",
            "messages": [{"role": "user", "content": prompt}],
            "response_format": {"type": "json_object"},
        }).encode(),
        headers={"Authorization": f"Bearer {os.environ['DEEPSEEK_API_KEY']}", "Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=60) as resp:
        result = json.load(resp)
    content = result["choices"][0]["message"]["content"]
    try:
        parsed = json.loads(content)
    except json.JSONDecodeError:
        m = re.search(r"\{.*\}", content, re.S)
        parsed = json.loads(m.group()) if m else {}

    usage = result.get("usage", {})
    cache_hit = usage.get("prompt_cache_hit_tokens", 0)
    cache_miss = usage.get("prompt_cache_miss_tokens", usage.get("prompt_tokens", 0))
    completion = usage.get("completion_tokens", 0)
    cost = cache_hit * DEEPSEEK_PRICE["cache_hit_in"] + cache_miss * DEEPSEEK_PRICE["cache_miss_in"] + completion * DEEPSEEK_PRICE["out"]

    gt = GROUND_TRUTH.get(name, {})
    hallucinated = (
        parsed.get("category") not in CATEGORY_CRITERIA
        or not _grounded(parsed.get("invoice_number"), text)
        or not _grounded(parsed.get("total"), text)
    )
    return {
        "file": name,
        "ground_truth": {"category": gt.get("category"), "total": gt.get("total"), "invoice_number": gt.get("invoice_number")},
        "category": parsed.get("category"),
        "invoice_number": parsed.get("invoice_number"),
        "total_amount": parsed.get("total"),
        "tokens": {"input": usage.get("prompt_tokens"), "output": usage.get("completion_tokens")},
        "cost_usd": round(cost, 6),
        "hallucinated": hallucinated,
    }


def classify_via_openai(name: str) -> dict:
    path = DOCS / name
    lines = extract_lines(path)
    text = "\n".join(lines)
    prompt = DEEPSEEK_PROMPT.format(categories=", ".join(CATEGORY_CRITERIA), text=text)
    parsed, usage = P.call_openai_json(prompt)
    gt = GROUND_TRUTH.get(name, {})
    hallucinated = (
        parsed.get("category") not in CATEGORY_CRITERIA
        or not _grounded(parsed.get("invoice_number"), text)
        or not _grounded(parsed.get("total"), text)
    )
    return {
        "file": name,
        "ground_truth": {"category": gt.get("category"), "total": gt.get("total"), "invoice_number": gt.get("invoice_number")},
        "category": parsed.get("category"),
        "invoice_number": parsed.get("invoice_number"),
        "total_amount": parsed.get("total"),
        "tokens": {"input": usage.get("prompt_tokens"), "output": usage.get("completion_tokens")},
        "cost_usd": P.openai_cost(usage),
        "hallucinated": hallucinated,
    }
