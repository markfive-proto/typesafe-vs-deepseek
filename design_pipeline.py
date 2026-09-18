"""Design-system audit: TypeSafe vs DeepSeek vs gpt-5-nano on structured Figma-style scene-graph
JSON (layer metadata — hex/font/spacing/name — never pixels). One call bundles five checks per
screen: brand-token compliance, naming convention, breaking-change risk, review-comment triage,
and brief-match scoring.
"""
import json
import os
import re
from pathlib import Path

import pipeline as P

ROOT = Path(__file__).parent
SCREENS = ROOT / "design_screens"
BRAND = json.loads((SCREENS / "brand_tokens.json").read_text()) if (SCREENS / "brand_tokens.json").exists() else {}

COMMENT_CRITERIA = {
    "color": "the comment is about a color/palette choice being off-brand or wrong",
    "spacing": "the comment is about spacing, padding, or whitespace feeling off",
    "typography": "the comment is about font, weight, or type-related issues",
    "layout": "the comment is about structural/responsive layout problems",
    "copy": "the comment is about wording, typos, or tone of the text itself",
    "other": "positive feedback, approval, or anything not covered above",
}


def list_screens():
    return sorted(p.name for p in SCREENS.glob("*_screen.json"))


def load_screen(name: str) -> dict:
    return json.loads((SCREENS / name).read_text())


def build_questions(screen: dict) -> dict:
    layers = screen["layers"]
    q = {}
    for i, layer in enumerate(layers):
        q[f"layer_{i}_compliant"] = {
            "type": "noul",
            "instructions": (
                f"Is `layers[{i}]` fully compliant with `brand`? It must use an approved color "
                "(exact hex match), an approved font, an on-scale spacing value, AND a name that "
                "follows the naming rule — all four, not just some."
            ),
        }
    q["breaking_change"] = {
        "type": "noul",
        "instructions": "Comparing `layers` (current) against `prev_layers` (previous version), is this a breaking layout change — a layer removed or fundamentally changed, not just a minor value tweak?",
    }
    q["comment_category"] = {
        "type": "choice",
        "instructions": "Classify `review_comment` into the category it's actually about.",
        "criteria": COMMENT_CRITERIA,
    }
    q["brief_match"] = {
        "type": "score",
        "instructions": "How well do `layers` fulfill `brief`, given the elements it implies are needed (`required_elements`)?",
        "criteria": ["none of the required elements present", "some present", "most present", "all required elements present"],
    }
    return q


def classify(name: str) -> dict:
    screen = load_screen(name)
    state = {
        "brand": BRAND, "layers": screen["layers"], "prev_layers": screen["prev_layers"],
        "review_comment": screen["review_comment"], "brief": screen["brief"], "required_elements": screen["required_elements"],
    }
    questions = build_questions(screen)
    result = P.call_typesafe(state, questions)
    answers = result["answers"]
    usage = result.get("usage", {})

    layers = screen["layers"]
    noncompliant = [layers[i]["name"] for i in range(len(layers)) if (answers.get(f"layer_{i}_compliant", {}).get("noul") or 0) < 0.5]

    return {
        "file": name,
        "title": screen["title"],
        "ground_truth": screen["ground_truth"],
        "all_layers_compliant": len(noncompliant) == 0,
        "noncompliant_layers": noncompliant,
        "breaking_change": (answers.get("breaking_change", {}).get("noul") or 0) > 0.5,
        "comment_category": answers.get("comment_category", {}).get("choice"),
        "brief_match": answers.get("brief_match", {}).get("score"),
        "tokens": {"input": usage.get("input_tokens"), "output": usage.get("output_tokens")},
        "cost_usd": P.typesafe_cost(usage),
        # Noul/Choice here only ever reference layers/categories it was actually given — structurally grounded.
        "hallucinated": any(n not in {l["name"] for l in layers} for n in noncompliant),
    }


PROMPT = """Audit this design screen's layer metadata (never pixels — this is structured data).

Brand tokens: {brand}

Layers (current): {layers}
Layers (previous version): {prev_layers}
Review comment: {comment}
Brief: {brief}
Required elements the brief implies: {required}

Check each current layer for FULL compliance (approved hex color AND approved font AND
on-scale spacing AND a name following the naming rule — all four).

Respond with ONLY a JSON object, no markdown, no commentary:
{{"noncompliant_layers": ["<layer name>", ...], "breaking_change": <true|false>, \
"comment_category": "<one of: color, spacing, typography, layout, copy, other>", \
"brief_match_fraction": <0.0-1.0>}}"""


def classify_via_deepseek(name: str) -> dict:
    import urllib.request
    screen = load_screen(name)
    prompt = PROMPT.format(
        brand=json.dumps(BRAND), layers=json.dumps(screen["layers"]), prev_layers=json.dumps(screen["prev_layers"]),
        comment=screen["review_comment"], brief=screen["brief"], required=json.dumps(screen["required_elements"]),
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

    return _package(name, screen, parsed, {"input": usage.get("prompt_tokens"), "output": usage.get("completion_tokens")}, round(cost, 6))


def classify_via_openai(name: str) -> dict:
    screen = load_screen(name)
    prompt = PROMPT.format(
        brand=json.dumps(BRAND), layers=json.dumps(screen["layers"]), prev_layers=json.dumps(screen["prev_layers"]),
        comment=screen["review_comment"], brief=screen["brief"], required=json.dumps(screen["required_elements"]),
    )
    parsed, usage = P.call_openai_json(prompt)
    return _package(name, screen, parsed, {"input": usage.get("prompt_tokens"), "output": usage.get("completion_tokens")}, P.openai_cost(usage))


def _package(name, screen, parsed, tokens, cost_usd) -> dict:
    layer_names = {l["name"] for l in screen["layers"]}
    noncompliant = [n for n in (parsed.get("noncompliant_layers") or []) if isinstance(n, str)]
    invented = [n for n in noncompliant if n not in layer_names]
    return {
        "file": name,
        "title": screen["title"],
        "ground_truth": screen["ground_truth"],
        "all_layers_compliant": len(noncompliant) == 0,
        "noncompliant_layers": noncompliant,
        "breaking_change": bool(parsed.get("breaking_change")),
        "comment_category": parsed.get("comment_category"),
        "brief_match": parsed.get("brief_match_fraction"),
        "tokens": tokens,
        "cost_usd": cost_usd,
        "hallucinated": bool(invented) or parsed.get("comment_category") not in COMMENT_CRITERIA,
    }
