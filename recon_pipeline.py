"""Bank vs ERP reconciliation: TypeSafe vs DeepSeek vs gpt-5-nano fuzzy-matching statement lines
against ledger lines and explaining the discrepancy type when they don't line up exactly.
"""
import json
import os
import re
from pathlib import Path

import pipeline as P

ROOT = Path(__file__).parent
PAIRS = ROOT / "recon_pairs"

REASON_CRITERIA = {
    "none": "amounts, dates, and descriptions effectively match — this is the same transaction",
    "fx_rounding": "small amount difference consistent with currency conversion rounding",
    "banking_fee": "bank amount is slightly higher than ledger amount, consistent with a wire/processing fee",
    "timing": "descriptions and amounts match but dates differ by a day or two (posting delay)",
    "mismatched_vendor": "this is actually a different vendor/transaction, not the same payment at all",
}


def list_pairs():
    return sorted(p.name for p in PAIRS.glob("*.json"))


def load(name: str) -> dict:
    return json.loads((PAIRS / name).read_text())


def build_questions() -> dict:
    return {
        "is_match": {
            "type": "noul",
            "instructions": "Do `bank_line` and `ledger_line` represent the same underlying transaction (even if amounts/dates/descriptions differ slightly)?",
        },
        "discrepancy_reason": {
            "type": "choice",
            "instructions": "What best explains any difference between `bank_line` and `ledger_line`?",
            "criteria": REASON_CRITERIA,
        },
    }


def classify(name: str) -> dict:
    pair = load(name)
    state = {"bank_line": pair["bank_line"], "ledger_line": pair["ledger_line"]}
    questions = build_questions()
    result = P.call_typesafe(state, questions)
    answers = result["answers"]
    usage = result.get("usage", {})
    return {
        "file": name,
        "ground_truth": pair["ground_truth"],
        "is_match": (answers.get("is_match", {}).get("noul") or 0) > 0.5,
        "discrepancy_reason": answers.get("discrepancy_reason", {}).get("choice"),
        "tokens": {"input": usage.get("input_tokens"), "output": usage.get("output_tokens")},
        "cost_usd": P.typesafe_cost(usage),
        "hallucinated": False,
    }


PROMPT = """Compare these two financial records and decide if they represent the same transaction.

Bank line: {bank}
Ledger line: {ledger}

Possible discrepancy reasons: {reasons}

Respond with ONLY a JSON object, no markdown, no commentary:
{{"is_match": <true|false>, "discrepancy_reason": "<one of: {reason_keys}>"}}"""


def classify_via_deepseek(name: str) -> dict:
    import urllib.request
    pair = load(name)
    prompt = PROMPT.format(
        bank=json.dumps(pair["bank_line"]), ledger=json.dumps(pair["ledger_line"]),
        reasons=json.dumps(REASON_CRITERIA), reason_keys=", ".join(REASON_CRITERIA),
    )
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

    from email_pipeline import DEEPSEEK_PRICE
    usage = result.get("usage", {})
    cache_hit = usage.get("prompt_cache_hit_tokens", 0)
    cache_miss = usage.get("prompt_cache_miss_tokens", usage.get("prompt_tokens", 0))
    completion = usage.get("completion_tokens", 0)
    cost = cache_hit * DEEPSEEK_PRICE["cache_hit_in"] + cache_miss * DEEPSEEK_PRICE["cache_miss_in"] + completion * DEEPSEEK_PRICE["out"]

    return {
        "file": name, "ground_truth": pair["ground_truth"],
        "is_match": bool(parsed.get("is_match")), "discrepancy_reason": parsed.get("discrepancy_reason"),
        "tokens": {"input": usage.get("prompt_tokens"), "output": usage.get("completion_tokens")},
        "cost_usd": round(cost, 6),
        "hallucinated": parsed.get("discrepancy_reason") not in REASON_CRITERIA,
    }


def classify_via_openai(name: str) -> dict:
    pair = load(name)
    prompt = PROMPT.format(
        bank=json.dumps(pair["bank_line"]), ledger=json.dumps(pair["ledger_line"]),
        reasons=json.dumps(REASON_CRITERIA), reason_keys=", ".join(REASON_CRITERIA),
    )
    parsed, usage = P.call_openai_json(prompt)
    return {
        "file": name, "ground_truth": pair["ground_truth"],
        "is_match": bool(parsed.get("is_match")), "discrepancy_reason": parsed.get("discrepancy_reason"),
        "tokens": {"input": usage.get("prompt_tokens"), "output": usage.get("completion_tokens")},
        "cost_usd": P.openai_cost(usage),
        "hallucinated": parsed.get("discrepancy_reason") not in REASON_CRITERIA,
    }
