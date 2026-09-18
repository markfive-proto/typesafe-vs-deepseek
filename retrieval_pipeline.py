"""Reranking demo over the 50-email corpus. Thin wrapper over rerank_core's corpus-agnostic
TypeSafe/DeepSeek/OpenAI rerankers — see rerank_core.py for the actual mechanics.
"""
import re
from pathlib import Path

from email_pipeline import EMAILS, ground_truth
import rerank_core as core

QUERIES = {
    "urgent incident": {
        "text": (
            "Find emails about an active production incident or outage that needs immediate "
            "attention from the recipient's own team. NOT a marketing email using urgency "
            "language ('act now', 'ends tonight') — that's promotional, not a real incident."
        ),
        "relevant_category": "support_urgent",
    },
    "scam / phishing": {
        "text": (
            "Find emails that are unsolicited scams or phishing attempts asking for money or "
            "bank/account details, from a sender with no real relationship to the recipient. "
            "NOT a legitimate marketing email offering a real discount code from a known "
            "brand — that's promotional, even if it also uses urgency language."
        ),
        "relevant_category": "spam",
    },
    "editorial digest": {
        "text": (
            "Find emails that are a recurring editorial newsletter/digest with curated "
            "industry news the recipient subscribed to. NOT a receipt or order confirmation "
            "(transactional), and NOT a sales pitch for a specific product (promotional)."
        ),
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


def _relevant_files(query_key: str, candidates: list[dict]) -> set[str]:
    category = QUERIES[query_key]["relevant_category"]
    return {c["file"] for c in candidates if ground_truth(c["file"]) == category}


def rerank_typesafe(query_key: str) -> dict:
    candidates = load_candidates()
    return core.rerank_typesafe(query_key, QUERIES[query_key]["text"], candidates, _relevant_files(query_key, candidates))


def rerank_deepseek(query_key: str) -> dict:
    candidates = load_candidates()
    return core.rerank_deepseek(query_key, QUERIES[query_key]["text"], candidates, _relevant_files(query_key, candidates))


def rerank_openai(query_key: str) -> dict:
    candidates = load_candidates()
    return core.rerank_openai(query_key, QUERIES[query_key]["text"], candidates, _relevant_files(query_key, candidates))
