"""Reranking demo over the 100-file AI-infra knowledge base. Thin wrapper over rerank_core,
same pattern as retrieval_pipeline.py but a different corpus and query set.
"""
import json
from pathlib import Path

import rerank_core as core

ROOT = Path(__file__).parent
KB_DOCS = ROOT / "kb_docs"
_GROUND_TRUTH = json.loads((KB_DOCS / "ground_truth.json").read_text()) if (KB_DOCS / "ground_truth.json").exists() else {}

QUERIES = {
    "AI products": {
        "text": "Find docs describing AI-powered products built directly for end users to use — chatbots, copilots, generation tools, consumer or business-facing applications.",
        "relevant_category": "products",
    },
    "agent harness": {
        "text": "Find docs about the developer-facing orchestration layer that builds and runs an AI agent itself — its tool-use loop, memory management, multi-agent coordination, and guardrails.",
        "relevant_category": "harness",
    },
    "inference runtime": {
        "text": "Find docs about the systems-level infrastructure that physically serves a trained model's inference: GPU scheduling, request batching, KV cache management, quantization, autoscaling.",
        "relevant_category": "runtime",
    },
    "model evaluation": {
        "text": "Find docs about measuring and testing model or agent output quality and correctness: benchmarks, judge models, test suites, red-teaming, calibration.",
        "relevant_category": "eval",
    },
    "observability": {
        "text": "Find docs about watching and debugging an AI system's live production traffic after it has shipped: request tracing, dashboards, alerting, session replay, audit logs.",
        "relevant_category": "observability",
    },
}


def ground_truth(name: str) -> str | None:
    """Ground truth lives in a separate manifest, never in the filename or doc content itself."""
    return _GROUND_TRUTH.get(name)


def load_candidates() -> list[dict]:
    files = sorted(p.name for p in KB_DOCS.glob("*.md"))
    out = []
    for f in files:
        text = (KB_DOCS / f).read_text()
        out.append({"file": f, "snippet": text.strip()[:280]})
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
