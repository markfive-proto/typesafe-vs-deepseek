"""API security guardrail: TypeSafe vs DeepSeek vs gpt-5-nano detecting SQLi, prompt injection,
and PII leaks in request payloads — textbook detector-eval patterns, defensive use.
"""
import json
import os
import re
from pathlib import Path

import pipeline as P

ROOT = Path(__file__).parent
REQUESTS = ROOT / "security_requests"

CATEGORY_CRITERIA = {
    "benign": "normal request/message with no security concern",
    "sqli": "contains SQL injection syntax (quotes breaking out of a query, UNION/DROP/OR 1=1 patterns)",
    "prompt_injection": "attempts to override system instructions, extract the system prompt, or hijack the assistant's behavior",
    "pii_leak": "contains sensitive personal data (SSN, full card number, passport, home address) being sent inline",
}


def list_requests():
    return sorted(p.name for p in REQUESTS.glob("*.json"))


def load(name: str) -> dict:
    return json.loads((REQUESTS / name).read_text())


def build_questions() -> dict:
    return {
        "threat_category": {
            "type": "choice",
            "instructions": "Classify `payload` into the single category that best describes it.",
            "criteria": CATEGORY_CRITERIA,
        },
        "is_sqli": {"type": "noul", "instructions": "Does `payload` contain SQL injection syntax?"},
        "is_prompt_injection": {"type": "noul", "instructions": "Does `payload` attempt to override or hijack system/assistant instructions?"},
        "contains_pii": {"type": "noul", "instructions": "Does `payload` contain sensitive personal data (SSN, full card number, passport, home address) sent inline?"},
    }


def classify(name: str) -> dict:
    req = load(name)
    state = {"payload": req["payload"]}
    questions = build_questions()
    result = P.call_typesafe(state, questions)
    answers = result["answers"]
    usage = result.get("usage", {})
    return {
        "file": name,
        "ground_truth": req["ground_truth"],
        "threat_category": answers.get("threat_category", {}).get("choice"),
        "is_sqli": (answers.get("is_sqli", {}).get("noul") or 0) > 0.5,
        "is_prompt_injection": (answers.get("is_prompt_injection", {}).get("noul") or 0) > 0.5,
        "contains_pii": (answers.get("contains_pii", {}).get("noul") or 0) > 0.5,
        "tokens": {"input": usage.get("input_tokens"), "output": usage.get("output_tokens")},
        "cost_usd": P.typesafe_cost(usage),
        "hallucinated": False,
    }


PROMPT = """Classify this API request/message for security threats.

Payload: {payload}

Categories: {categories}

Respond with ONLY a JSON object, no markdown, no commentary:
{{"threat_category": "<one of: {cat_keys}>", "is_sqli": <true|false>, "is_prompt_injection": <true|false>, "contains_pii": <true|false>}}"""


def classify_via_deepseek(name: str) -> dict:
    import urllib.request
    req = load(name)
    prompt = PROMPT.format(payload=req["payload"], categories=json.dumps(CATEGORY_CRITERIA), cat_keys=", ".join(CATEGORY_CRITERIA))
    r = urllib.request.Request(
        P.DEEPSEEK_URL,
        data=json.dumps({
            "model": "deepseek-flash",
            "messages": [{"role": "user", "content": prompt}],
            "response_format": {"type": "json_object"},
        }).encode(),
        headers={"Authorization": f"Bearer {os.environ['DEEPSEEK_API_KEY']}", "Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(r, timeout=60) as resp:
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
        "file": name, "ground_truth": req["ground_truth"],
        "threat_category": parsed.get("threat_category"),
        "is_sqli": bool(parsed.get("is_sqli")), "is_prompt_injection": bool(parsed.get("is_prompt_injection")),
        "contains_pii": bool(parsed.get("contains_pii")),
        "tokens": {"input": usage.get("prompt_tokens"), "output": usage.get("completion_tokens")},
        "cost_usd": round(cost, 6),
        "hallucinated": parsed.get("threat_category") not in CATEGORY_CRITERIA,
    }


def classify_via_openai(name: str) -> dict:
    req = load(name)
    prompt = PROMPT.format(payload=req["payload"], categories=json.dumps(CATEGORY_CRITERIA), cat_keys=", ".join(CATEGORY_CRITERIA))
    parsed, usage = P.call_openai_json(prompt)
    return {
        "file": name, "ground_truth": req["ground_truth"],
        "threat_category": parsed.get("threat_category"),
        "is_sqli": bool(parsed.get("is_sqli")), "is_prompt_injection": bool(parsed.get("is_prompt_injection")),
        "contains_pii": bool(parsed.get("contains_pii")),
        "tokens": {"input": usage.get("prompt_tokens"), "output": usage.get("completion_tokens")},
        "cost_usd": P.openai_cost(usage),
        "hallucinated": parsed.get("threat_category") not in CATEGORY_CRITERIA,
    }
