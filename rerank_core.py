"""Corpus-agnostic reranking: TypeSafe (all N questions in one call) vs DeepSeek-flash vs
gpt-5-nano (each ranking all N candidates in one generative pass). Used by both the emails
corpus (retrieval_pipeline.py) and the AI-infra KB corpus (kb_pipeline.py).
"""
import json
import re

import pipeline as P

RANK_PROMPT = """Rank these {n} candidates by relevance to the query below.

Query: {query}

Judge each candidate by its actual central subject, not by surface keyword overlap with
the query — two topics can share vocabulary while answering a different question.

Candidates (id: snippet):
{candidates}

Respond with ONLY a JSON object mapping each candidate id to a relevance score \
from 0.0 (not relevant) to 1.0 (highly relevant): {{"0": <score>, "1": <score>, ...}}"""


def _precision(ranked: list[dict], relevant_files: set[str]) -> tuple[int, float]:
    k = len(relevant_files)
    top_k = {r["file"] for r in ranked[:k]}
    precision = len(top_k & relevant_files) / k if k else 0
    return k, round(precision, 3)


def rerank_typesafe(query_key: str, query_text: str, candidates: list[dict], relevant_files: set[str]) -> dict:
    state = {"query": query_text, "candidates": [c["snippet"] for c in candidates]}
    questions = {
        f"rel_{i}": {
            "type": "score",
            "instructions": f"How relevant is `candidates[{i}]` to `query`? Judge by the candidate's actual central subject, not by surface keyword overlap.",
            "criteria": [
                "not relevant — a different topic entirely",
                "somewhat relevant — related field, but a different central subject than query asks for",
                "relevant — matches query's topic, though not the clearest example",
                "highly relevant — a clear, central example of exactly what query asks for",
            ],
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
    k, precision = _precision(ranked, relevant_files)

    return {
        "query": query_key,
        "ranked": ranked[:10],
        "relevant_count": k,
        "precision_at_k": precision,
        "num_questions": len(questions),
        "tokens": {"input": usage.get("input_tokens"), "output": usage.get("output_tokens")},
        "cost_usd": P.typesafe_cost(usage),
        # every question was pinned to `candidates[i]` — no slot for the model to name a candidate that doesn't exist.
        "hallucinated": False,
        "hallucinated_count": 0,
    }


def _parse_ranked_scores(scores: dict, candidates: list[dict]) -> tuple[list[dict], int]:
    """Returns (ranked list, count of returned ids that don't map to a real candidate — invented ids)."""
    valid, invalid = [], 0
    for key, score in scores.items():
        if isinstance(key, str) and key.isdigit() and int(key) < len(candidates):
            valid.append({"file": candidates[int(key)]["file"], "score": float(score)})
        else:
            invalid += 1
    return sorted(valid, key=lambda x: -x["score"]), invalid


def rerank_deepseek(query_key: str, query_text: str, candidates: list[dict], relevant_files: set[str]) -> dict:
    import os
    import urllib.request

    listing = "\n".join(f"{i}: {c['snippet']}" for i, c in enumerate(candidates))
    prompt = RANK_PROMPT.format(n=len(candidates), query=query_text, candidates=listing)
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
    ranked, hallucinated_count = _parse_ranked_scores(scores, candidates)
    k, precision = _precision(ranked, relevant_files)

    usage = result.get("usage", {})
    from email_pipeline import DEEPSEEK_PRICE
    cache_hit = usage.get("prompt_cache_hit_tokens", 0)
    cache_miss = usage.get("prompt_cache_miss_tokens", usage.get("prompt_tokens", 0))
    completion = usage.get("completion_tokens", 0)
    cost = cache_hit * DEEPSEEK_PRICE["cache_hit_in"] + cache_miss * DEEPSEEK_PRICE["cache_miss_in"] + completion * DEEPSEEK_PRICE["out"]

    return {
        "query": query_key,
        "ranked": ranked[:10],
        "relevant_count": k,
        "precision_at_k": precision,
        "tokens": {"input": usage.get("prompt_tokens"), "output": usage.get("completion_tokens")},
        "cost_usd": round(cost, 6),
        # ids the model returned that don't correspond to any real candidate it was shown — invented references.
        "hallucinated": hallucinated_count > 0,
        "hallucinated_count": hallucinated_count,
    }


def rerank_openai(query_key: str, query_text: str, candidates: list[dict], relevant_files: set[str]) -> dict:
    listing = "\n".join(f"{i}: {c['snippet']}" for i, c in enumerate(candidates))
    prompt = RANK_PROMPT.format(n=len(candidates), query=query_text, candidates=listing)
    parsed_content, usage = P.call_openai_json(prompt)
    ranked, hallucinated_count = _parse_ranked_scores(parsed_content, candidates)
    k, precision = _precision(ranked, relevant_files)
    return {
        "query": query_key,
        "ranked": ranked[:10],
        "relevant_count": k,
        "precision_at_k": precision,
        "tokens": {"input": usage.get("prompt_tokens"), "output": usage.get("completion_tokens")},
        "cost_usd": P.openai_cost(usage),
        "hallucinated": hallucinated_count > 0,
        "hallucinated_count": hallucinated_count,
    }
