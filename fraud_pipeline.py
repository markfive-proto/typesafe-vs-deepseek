"""Fraud/risk triage: TypeSafe vs DeepSeek vs gpt-5-nano scoring transaction risk and routing
decisions from structured telemetry (amount, geo-velocity, device signal, account age).
"""
import json
import os
import re
from pathlib import Path

import pipeline as P

ROOT = Path(__file__).parent
TXNS = ROOT / "fraud_transactions"

ROUTE_CRITERIA = {
    "approve": "low risk — process immediately, no friction",
    "step_up": "medium/uncertain risk — require step-up authentication (OTP/biometric) before completing",
    "block": "high/critical risk — decline the transaction and flag the session",
}


def list_transactions():
    return sorted(p.name for p in TXNS.glob("*.json"))


def load(name: str) -> dict:
    return json.loads((TXNS / name).read_text())


def build_questions() -> dict:
    return {
        "risk_score": {
            "type": "score",
            "instructions": "How risky is `transaction`, given its geo-velocity, device signal, account age, and merchant category?",
            "criteria": ["low — normal pattern", "medium — one notable signal", "high — multiple risk signals", "critical — clear fraud indicators"],
        },
        "route": {
            "type": "choice",
            "instructions": "Given the risk assessment, how should this transaction be routed?",
            "criteria": ROUTE_CRITERIA,
        },
    }


def classify(name: str) -> dict:
    txn = load(name)
    state = {"transaction": {k: v for k, v in txn.items() if k != "ground_truth"}}
    questions = build_questions()
    result = P.call_typesafe(state, questions)
    answers = result["answers"]
    usage = result.get("usage", {})
    return {
        "file": name,
        "ground_truth": txn["ground_truth"],
        "risk_score": answers.get("risk_score", {}).get("score"),
        "route": answers.get("route", {}).get("choice"),
        "route_confidence": answers.get("route", {}).get("confidence"),
        "tokens": {"input": usage.get("input_tokens"), "output": usage.get("output_tokens")},
        "cost_usd": P.typesafe_cost(usage),
        "hallucinated": False,
    }


PROMPT = """Assess fraud risk for this transaction and decide how to route it.

Transaction: {txn}

Routing options: {routes}

Respond with ONLY a JSON object, no markdown, no commentary:
{{"risk_score": <0-3, 0=low 3=critical>, "route": "<one of: approve, step_up, block>"}}"""


def classify_via_deepseek(name: str) -> dict:
    import urllib.request
    txn = load(name)
    txn_data = {k: v for k, v in txn.items() if k != "ground_truth"}
    prompt = PROMPT.format(txn=json.dumps(txn_data), routes=", ".join(ROUTE_CRITERIA))
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
        "file": name, "ground_truth": txn["ground_truth"],
        "risk_score": parsed.get("risk_score"), "route": parsed.get("route"),
        "tokens": {"input": usage.get("prompt_tokens"), "output": usage.get("completion_tokens")},
        "cost_usd": round(cost, 6),
        "hallucinated": parsed.get("route") not in ROUTE_CRITERIA,
    }


def classify_via_openai(name: str) -> dict:
    txn = load(name)
    txn_data = {k: v for k, v in txn.items() if k != "ground_truth"}
    prompt = PROMPT.format(txn=json.dumps(txn_data), routes=", ".join(ROUTE_CRITERIA))
    parsed, usage = P.call_openai_json(prompt)
    return {
        "file": name, "ground_truth": txn["ground_truth"],
        "risk_score": parsed.get("risk_score"), "route": parsed.get("route"),
        "tokens": {"input": usage.get("prompt_tokens"), "output": usage.get("completion_tokens")},
        "cost_usd": P.openai_cost(usage),
        "hallucinated": parsed.get("route") not in ROUTE_CRITERIA,
    }
