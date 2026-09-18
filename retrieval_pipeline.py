"""Reranking demo: TypeSafe answers N relevance questions in ONE call (true intra-request
parallelism) vs DeepSeek-flash ranking all N candidates in one generative pass.

Ground truth: each sample email's true category is encoded in its filename
(`email_pipeline.ground_truth`), so a query mapped to a category gives a known
relevant set to score precision against.
"""
import json
import os
import re
from pathlib import Path

import pipeline as P
from email_pipeline import EMAILS, ground_truth, DEEPSEEK_PRICE

QUERIES = {
    "urgent incident": {
        "text": "Find emails about an active production incident or outage that needs immediate attention.",
        "relevant_category": "support_urgent",
    },
    "scam / phishing": {
        "text": "Find emails that are unsolicited scams or phishing attempts asking for money or bank details.",
        "relevant_category": "spam",
    },
    "editorial digest": {
        "text": "Find emails that are a recurring editorial newsletter/digest the recipient subscribed to.",
        "relevant_category": "newsletter",
    },
}


def load_candidates() -> list[dict]:
    files = sorted(p.name for p in EMAILS.glob("*.md"))
    out = []
    for f in files:
        text = (EMAILS / f).read_text()
        body = re.sub(r"^---[\s\S]*?---", "", text).strip()
        out.append({"file": f, "snippet": body[:220]})
    return out


def rerank_typesafe(query_key: str) -> dict:
    q = QUERIES[query_key]
    candidates = load_candidates()
    state = {"query": q["text"], "candidates": [c["snippet"] for c in candidates]}
    questions = {
        f"rel_{i}": {
            "type": "score",
            "instructions": f"How relevant is `candidates[{i}]` to `query`?",
            "criteria": ["not relevant", "somewhat relevant", "relevant", "highly relevant"],
        }
        for i in range(len(candidates))
    }
    result = P.call_typesafe(state, questions)
    answers = result["answers"]
    usage = result.get("usage", {})

    ranked = sorted(
        ({"file": candidates[i]["file"], "score": answers.get(f"rel_{i}", {}).get("score", 0)} for i in range(len(candidates))),
        key=lambda x: -x["score"],
    )
    relevant_set = {c["file"] for c in candidates if ground_truth(c["file"]) == q["relevant_category"]}
    k = len(relevant_set)
    top_k = {r["file"] for r in ranked[:k]}
    precision = len(top_k & relevant_set) / k if k else 0

    return {
        "query": query_key,
        "ranked": ranked[:10],
        "relevant_count": k,
        "precision_at_k": round(precision, 3),
        "num_questions": len(questions),
        "tokens": {"input": usage.get("input_tokens"), "output": usage.get("output_tokens")},
        "cost_usd": P.typesafe_cost(usage),
    }


DEEPSEEK_PROMPT = """Rank these {n} candidate emails by relevance to the query below.

Query: {query}

Candidates (id: snippet):
{candidates}

Respond with ONLY a JSON object mapping each candidate id to a relevance score \
from 0.0 (not relevant) to 1.0 (highly relevant): {{"0": <score>, "1": <score>, ...}}"""


def rerank_deepseek(query_key: str) -> dict:
    q = QUERIES[query_key]
    candidates = load_candidates()
    listing = "\n".join(f"{i}: {c['snippet']}" for i, c in enumerate(candidates))
    prompt = DEEPSEEK_PROMPT.format(n=len(candidates), query=q["text"], candidates=listing)

    import urllib.request
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
    with urllib.request.urlopen(req, timeout=120) as resp:
        result = json.load(resp)
    content = result["choices"][0]["message"]["content"]
    try:
        scores = json.loads(content)
    except json.JSONDecodeError:
        m = re.search(r"\{.*\}", content, re.S)
        scores = json.loads(m.group()) if m else {}

    ranked = sorted(
        ({"file": candidates[int(i)]["file"], "score": float(s)} for i, s in scores.items() if i.isdigit() and int(i) < len(candidates)),
        key=lambda x: -x["score"],
    )
    relevant_set = {c["file"] for c in candidates if ground_truth(c["file"]) == q["relevant_category"]}
    k = len(relevant_set)
    top_k = {r["file"] for r in ranked[:k]}
    precision = len(top_k & relevant_set) / k if k else 0

    usage = result.get("usage", {})
    cache_hit = usage.get("prompt_cache_hit_tokens", 0)
    cache_miss = usage.get("prompt_cache_miss_tokens", usage.get("prompt_tokens", 0))
    completion = usage.get("completion_tokens", 0)
    cost = cache_hit * DEEPSEEK_PRICE["cache_hit_in"] + cache_miss * DEEPSEEK_PRICE["cache_miss_in"] + completion * DEEPSEEK_PRICE["out"]

    return {
        "query": query_key,
        "ranked": ranked[:10],
        "relevant_count": k,
        "precision_at_k": round(precision, 3),
        "tokens": {"input": usage.get("prompt_tokens"), "output": usage.get("completion_tokens")},
        "cost_usd": round(cost, 6),
    }
