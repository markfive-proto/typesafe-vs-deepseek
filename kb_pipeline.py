"""Reranking demo over the 100-file AI-infra knowledge base. Thin wrapper over rerank_core,
same pattern as retrieval_pipeline.py but a different corpus and query set.
"""
import re
from pathlib import Path

import rerank_core as core

ROOT = Path(__file__).parent
KB_DOCS = ROOT / "kb_docs"

QUERIES = {
    "AI products": {
        "text": "Find docs describing AI-powered products built for end users (not internal infra).",
        "relevant_category": "products",
    },
    "agent harness": {
        "text": "Find docs about harness/orchestration tooling that runs and manages AI agents.",
        "relevant_category": "harness",
    },
    "inference runtime": {
        "text": "Find docs about the runtime infrastructure that serves model inference (GPUs, batching, caching).",
        "relevant_category": "runtime",
    },
    "model evaluation": {
        "text": "Find docs about evaluating model or agent quality, benchmarks, and testing.",
        "relevant_category": "eval",
    },
    "observability": {
        "text": "Find docs about monitoring, logging, tracing, and debugging AI systems in production.",
        "relevant_category": "observability",
    },
}


def ground_truth(name: str) -> str | None:
    """Filenames are `NNN_<category>.md`."""
    m = re.match(r"^\d+_(.+)\.md$", name)
    return m.group(1) if m else None


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
