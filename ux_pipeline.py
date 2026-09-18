"""Expert UX critique: TypeSafe vs DeepSeek vs gpt-5-nano scoring real UI screens across
Usability, UI design, Accessibility, Design-system consistency, and Alignment/spacing.

Screens are real (captured live via the browser from tailwindcss.com, news.ycombinator.com,
github.com, vercel.com, linear.app — Mobbin MCP needed a paid plan we don't have). Since Jev
takes text only, each screen was converted to a structured text description by direct visual
inspection (the same "vision-extract, then judge" pattern as the invoice OCR pipeline) rather
than an automated vision-model call — this demo compares the three engines' JUDGMENT on an
identical text description, which is the fair, apples-to-apples way to include Jev at all.

There's no ground truth for subjective UX quality, so unlike the other audit tabs this one
doesn't score accuracy — it's a genuine side-by-side critique, not a right-answer test.
"""
import json
import os
import re
from pathlib import Path

import pipeline as P

ROOT = Path(__file__).parent
SCREENS = ROOT / "ui_screens"

VERDICT_CRITERIA = {
    "ship": "no significant issues — ready to ship as-is",
    "minor_revisions": "generally solid, but has a few specific issues worth fixing before shipping",
    "major_redesign": "fundamental problems in multiple dimensions that need a rework, not a tweak",
}

DIMENSIONS = ["usability", "ui_design", "accessibility", "design_system_consistency", "alignment_spacing"]
DIMENSION_INSTRUCTIONS = {
    "usability": "How usable is this screen — is the primary action clear, is the information architecture easy to follow, is cognitive load reasonable?",
    "ui_design": "How strong is the visual design — color use, typography hierarchy, visual polish?",
    "accessibility": "How accessible does this screen look — contrast, label clarity, focus/state visibility, choice overload?",
    "design_system_consistency": "How consistent and systematic does the design look — spacing scale, component reuse, coherent visual language?",
    "alignment_spacing": "How clean is the layout — alignment, whitespace balance, visual rhythm?",
}
SCORE_LEVELS = ["poor — clear problems", "weak — works but rough", "good — solid, minor nitpicks only", "excellent — exemplary"]


def list_screens():
    return sorted(p.name for p in SCREENS.glob("*.json"))


def load(name: str) -> dict:
    return json.loads((SCREENS / name).read_text())


def build_questions() -> dict:
    q = {
        dim: {"type": "score", "instructions": DIMENSION_INSTRUCTIONS[dim], "criteria": SCORE_LEVELS}
        for dim in DIMENSIONS
    }
    q["verdict"] = {
        "type": "choice",
        "instructions": "Given all five dimensions, what's the overall verdict on `screen`?",
        "criteria": VERDICT_CRITERIA,
    }
    return q


def classify(name: str) -> dict:
    screen = load(name)
    state = {"screen": screen}
    questions = build_questions()
    result = P.call_typesafe(state, questions)
    answers = result["answers"]
    usage = result.get("usage", {})
    scores = {dim: answers.get(dim, {}).get("score") for dim in DIMENSIONS}
    return {
        "file": name, "source_url": screen["source_url"], "screen_type": screen["screen_type"],
        "scores": scores,
        "verdict": answers.get("verdict", {}).get("choice"),
        "tokens": {"input": usage.get("input_tokens"), "output": usage.get("output_tokens")},
        "cost_usd": P.typesafe_cost(usage),
        "hallucinated": False,
    }


PROMPT = """You are an expert UI/UX designer critiquing a real screen from its structured description
(no image available — judge from this text description alone).

Screen: {screen}

Score each dimension 0-3 (0=poor, 1=weak, 2=good, 3=excellent): {dims}
Then give an overall verdict.

Respond with ONLY a JSON object, no markdown, no commentary:
{{"usability": <0-3>, "ui_design": <0-3>, "accessibility": <0-3>, "design_system_consistency": <0-3>, \
"alignment_spacing": <0-3>, "verdict": "<one of: {verdicts}>"}}"""


def _cost_deepseek(usage):
    from email_pipeline import DEEPSEEK_PRICE
    cache_hit = usage.get("prompt_cache_hit_tokens", 0)
    cache_miss = usage.get("prompt_cache_miss_tokens", usage.get("prompt_tokens", 0))
    completion = usage.get("completion_tokens", 0)
    return round(cache_hit * DEEPSEEK_PRICE["cache_hit_in"] + cache_miss * DEEPSEEK_PRICE["cache_miss_in"] + completion * DEEPSEEK_PRICE["out"], 6)


def _package(name, screen, parsed, tokens, cost_usd):
    scores = {dim: parsed.get(dim) for dim in DIMENSIONS}
    return {
        "file": name, "source_url": screen["source_url"], "screen_type": screen["screen_type"],
        "scores": scores, "verdict": parsed.get("verdict"),
        "tokens": tokens, "cost_usd": cost_usd,
        "hallucinated": parsed.get("verdict") not in VERDICT_CRITERIA,
    }


def classify_via_deepseek(name: str) -> dict:
    import urllib.request
    screen = load(name)
    prompt = PROMPT.format(screen=json.dumps(screen), dims=", ".join(DIMENSIONS), verdicts=", ".join(VERDICT_CRITERIA))
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
    usage = result.get("usage", {})
    return _package(name, screen, parsed, {"input": usage.get("prompt_tokens"), "output": usage.get("completion_tokens")}, _cost_deepseek(usage))


def classify_via_openai(name: str) -> dict:
    screen = load(name)
    prompt = PROMPT.format(screen=json.dumps(screen), dims=", ".join(DIMENSIONS), verdicts=", ".join(VERDICT_CRITERIA))
    parsed, usage = P.call_openai_json(prompt)
    return _package(name, screen, parsed, {"input": usage.get("prompt_tokens"), "output": usage.get("completion_tokens")}, P.openai_cost(usage))
