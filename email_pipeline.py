"""Email classification: TypeSafe Jev vs DeepSeek-flash direct prompt-and-parse, same task, for a speed/token/cost comparison."""
import json
import os
import re
import urllib.request
from pathlib import Path

import pipeline as P

ROOT = Path(__file__).parent
EMAILS = ROOT / "emails_samples"

# deepseek-flash off-peak pricing, per token (https://api-docs.deepseek.com/quick_start/pricing)
DEEPSEEK_PRICE = {"cache_hit_in": 0.003e-6, "cache_miss_in": 0.15e-6, "out": 0.6e-6}


def ground_truth(name: str) -> str | None:
    """Sample filenames are `NN_<category>.md` — the label is the generator's ground truth."""
    m = re.match(r"^\d+_(.+)\.md$", name)
    return m.group(1) if m else None

CATEGORY_CRITERIA = {
    "work": "internal team/project communication: status updates, meetings, requests from colleagues",
    "personal": "message from a friend or family member, no business purpose",
    "newsletter": "recurring editorial digest/roundup the recipient subscribed to",
    "promotional": "marketing/sales pitch, discount codes, product launches",
    "spam": "unsolicited scam/phishing: prize claims, fake urgency, requests for bank/account details",
    "transactional": "receipt, order confirmation, shipping notice, payment/billing notice",
    "support_urgent": "an active incident, outage, or urgent support/escalation request",
}


def build_questions() -> dict:
    return {
        "category": {
            "type": "choice",
            "instructions": "Classify `email` into the single best-fitting category.",
            "criteria": CATEGORY_CRITERIA,
        },
        "urgency": {
            "type": "score",
            "instructions": "How urgently does `email` need attention/action?",
            "criteria": ["none — no action needed", "low — can wait weeks", "medium — this week", "high — today", "critical — immediately"],
        },
        "needs_reply": {
            "type": "noul",
            "instructions": "Does `email` expect a reply from the recipient?",
        },
    }


def classify(name: str) -> dict:
    text = (EMAILS / name).read_text()
    state = {"email": text}
    questions = build_questions()
    result = P.call_typesafe(state, questions)
    answers = result["answers"]
    usage = result.get("usage", {})

    urgency_answer = answers.get("urgency", {})
    urgency_score = urgency_answer.get("score")
    legend = urgency_answer.get("legend") or {}
    urgency_label = legend.get(str(round(urgency_score))) if urgency_score is not None else None

    return {
        "file": name,
        "ground_truth": ground_truth(name),
        "category": answers.get("category", {}).get("choice"),
        "category_confidence": answers.get("category", {}).get("confidence"),
        "urgency": urgency_score,
        "urgency_label": urgency_label,
        "needs_reply": answers.get("needs_reply", {}).get("noul"),
        "tokens": {"input": usage.get("input_tokens"), "output": usage.get("output_tokens")},
        "cost_usd": P.typesafe_cost(usage),
    }


DEEPSEEK_PROMPT = """Classify this email for a mail client.

Category — pick exactly one: {categories}

Also rate urgency from 0-4 (0=none/no action needed, 1=low/can wait weeks, \
2=medium/this week, 3=high/today, 4=critical/immediately), and whether it \
expects a reply from the recipient.

Respond with ONLY a JSON object, no markdown, no commentary:
{{"category": "<one of the categories above>", "urgency": <0-4 integer>, "needs_reply": <true|false>}}

Email:
{email}"""


def classify_via_deepseek(name: str) -> dict:
    """Same classification task, done by prompting deepseek-flash directly and parsing its JSON."""
    text = (EMAILS / name).read_text()
    prompt = DEEPSEEK_PROMPT.format(categories=", ".join(CATEGORY_CRITERIA), email=text)
    req = urllib.request.Request(
        P.DEEPSEEK_URL,
        data=json.dumps({
            "model": "deepseek-flash",
            "messages": [{"role": "user", "content": prompt}],
            "response_format": {"type": "json_object"},
        }).encode(),
        headers={
            "Authorization": f"Bearer {os.environ['DEEPSEEK_API_KEY']}",
            "Content-Type": "application/json",
        },
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

    return {
        "file": name,
        "ground_truth": ground_truth(name),
        "category": parsed.get("category"),
        "urgency": parsed.get("urgency"),
        "needs_reply": parsed.get("needs_reply"),
        "tokens": {"input": usage.get("prompt_tokens"), "output": usage.get("completion_tokens")},
        "cost_usd": round(cost, 6),
    }
