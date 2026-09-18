"""Batch invoice pipeline: DeepSeek vision OCR -> TypeSafe classification/extraction -> one HTML report.

ponytail: OCR is line-by-line text, not table-structure aware, so multi-column
line-item tables (qty/price/amount in separate visual columns) can interleave.
Upgrade path: ask DeepSeek for bounding boxes / a markdown table instead of
plain lines and reconstruct rows before handing text to TypeSafe.
"""
import base64
import json
import mimetypes
import os
import re
import sys
import urllib.request
from pathlib import Path

ROOT = Path(__file__).parent
SAMPLES = ROOT / "invoice_samples"
API_URL = "https://api.typesafe.ai/v1/systemone"
DEEPSEEK_URL = "https://api.deepseek.com/v1/chat/completions"

# Jev 1.13: $42 per billion input tokens, output tokens free (https://docs.typesafe.ai/models.md)
TYPESAFE_PRICE_PER_INPUT_TOKEN = 42 / 1e9


def typesafe_cost(usage: dict) -> float:
    return round(usage.get("input_tokens", 0) * TYPESAFE_PRICE_PER_INPUT_TOKEN, 6)


def load_env():
    """Loads .env for local dev. On Vercel, TYPESAFE_API_KEY/DEEPSEEK_API_KEY come from
    project environment variables instead — there's no .env file in the deployment."""
    env_file = ROOT / ".env"
    if not env_file.exists():
        return
    for line in env_file.read_text().splitlines():
        if "=" in line and not line.startswith("#"):
            k, v = line.split("=", 1)
            os.environ.setdefault(k.strip(), v.strip())


def ocr(image_path: Path) -> list[str]:
    """OCR via DeepSeek vision (deepseek-flash)."""
    data = base64.b64encode(image_path.read_bytes()).decode()
    mime = mimetypes.guess_type(str(image_path))[0] or "image/png"
    req = urllib.request.Request(
        DEEPSEEK_URL,
        data=json.dumps({
            "model": "deepseek-flash",
            "messages": [{
                "role": "user",
                "content": [
                    {
                        "type": "text",
                        "text": (
                            "Transcribe every piece of text visible in this document image, "
                            "verbatim, top to bottom. One fragment per line. No commentary, "
                            "no markdown formatting, just the raw transcribed lines."
                        ),
                    },
                    {"type": "image_url", "image_url": {"url": f"data:{mime};base64,{data}", "detail": "high"}},
                ],
            }],
        }).encode(),
        headers={
            "Authorization": f"Bearer {os.environ['DEEPSEEK_API_KEY']}",
            "Content-Type": "application/json",
        },
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=60) as resp:
        result = json.load(resp)
    text = result["choices"][0]["message"]["content"]
    return [l.strip() for l in text.splitlines() if l.strip()]


MONEY_RE = re.compile(r"\$?\d[\d,]*\.\d{1,2}")
DATE_RE = re.compile(r"\b\d{1,2}[/-]\d{1,2}[/-]\d{2,4}\b")
INVNUM_RE = re.compile(r"\b[A-Z]{0,4}[-#]?\d{3,}\b")


def candidates(lines: list[str], pattern: re.Pattern) -> list[str]:
    found = []
    for l in lines:
        found.extend(pattern.findall(l))
    return sorted(set(found))


def call_typesafe(state: dict, questions: dict) -> dict:
    req = urllib.request.Request(
        API_URL,
        data=json.dumps({"state": state, "model": "jev-latest", "questions": questions}).encode(),
        headers={
            "Authorization": f"Bearer {os.environ['TYPESAFE_API_KEY']}",
            "Content-Type": "application/json",
        },
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=60) as resp:
        return json.load(resp)


def build_questions(lines: list[str], totals: list[str], dates: list[str], invnums: list[str]) -> dict:
    q = {}
    for i in range(len(lines)):
        q[f"line_{i}_type"] = {
            "type": "choice",
            "instructions": f"Classify `lines[{i}]` in an OCR'd invoice.",
            "criteria": {
                "line_item": "A product/service row: has a description plus a quantity or price/amount",
                "header_field": "Vendor name, address, invoice title, 'Invoice To' block, notes, terms",
                "total_field": "Subtotal, discount, tax/GST, invoice total, amount due",
                "noise": "Table column labels (Qty/Price/Amount/Description), stray characters, template placeholders",
            },
        }
    if totals:
        q["total_amount"] = {
            "type": "choice",
            "instructions": (
                "Which candidate in `totals` is the final invoice total / amount due "
                "(not a subtotal, discount, or single line-item amount)?"
            ),
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
            "instructions": "Which candidate in `invoice_numbers` is the invoice number/ID (not a phone, zip, or amount)?",
            "criteria": {n: f"the value {n}" for n in invnums},
        }
    q["category"] = {
        "type": "choice",
        "instructions": "What category of invoice is this, based on `lines`?",
        "criteria": {
            "goods": "physical products sold",
            "services": "professional/consulting/legal/freelance services",
            "utilities_subscription": "recurring utility, hosting, or subscription billing",
            "other": "doesn't clearly fit the above",
        },
    }
    return q


def process(image_path: Path) -> dict:
    lines = ocr(image_path)
    totals = candidates(lines, MONEY_RE)
    dates = candidates(lines, DATE_RE)
    invnums = candidates(lines, INVNUM_RE)
    state = {"lines": lines, "totals": totals, "dates": dates, "invoice_numbers": invnums}
    questions = build_questions(lines, totals, dates, invnums)
    result = call_typesafe(state, questions)
    answers = result["answers"]

    line_items = [
        lines[i] for i in range(len(lines))
        if answers.get(f"line_{i}_type", {}).get("choice") == "line_item"
    ]
    return {
        "file": image_path.name,
        "vendor_guess": lines[0] if lines else "",
        "category": answers.get("category", {}).get("choice"),
        "invoice_number": answers.get("invoice_number", {}).get("choice"),
        "invoice_date": answers.get("invoice_date", {}).get("choice"),
        "total_amount": answers.get("total_amount", {}).get("choice"),
        "total_confidence": answers.get("total_amount", {}).get("confidence"),
        "line_items": line_items,
    }


def main():
    load_env()
    images = sorted([p for p in SAMPLES.glob("*") if p.suffix.lower() in (".png", ".jpg", ".jpeg")])
    if not images:
        print(f"no images in {SAMPLES}", file=sys.stderr)
        sys.exit(1)
    results = []
    for img in images:
        print(f"processing {img.name}...", file=sys.stderr)
        try:
            results.append(process(img))
        except Exception as e:
            results.append({"file": img.name, "error": str(e)})
    out = ROOT / "invoices.json"
    out.write_text(json.dumps(results, indent=2))
    print(f"wrote {out}")


if __name__ == "__main__":
    main()
