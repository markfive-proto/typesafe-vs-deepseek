"""Generate synthetic design screens (Figma-style scene-graph JSON) for a design-system
audit demo: brand-token compliance, naming convention, breaking-change risk, review-comment
triage, and brief-match — all as structured metadata, no pixels involved.
"""
import json
import random
from pathlib import Path

random.seed(21)
ROOT = Path(__file__).parent
OUT = ROOT / "design_screens"
OUT.mkdir(exist_ok=True)

BRAND_COLORS = {
    "ink": "#1C1A17", "surface": "#F7F5F0", "accent-teal": "#2A5D50",
    "accent-purple": "#6D3FAE", "accent-blue": "#1F6FB2", "warn": "#A8501C",
}
OFFBRAND_COLORS = ["#3366CC", "#FF0000", "#00FF00", "#808080", "#FFD700", "#111111"]

BRAND_FONTS = ["Fraunces", "IBM Plex Sans", "IBM Plex Mono"]
OFFBRAND_FONTS = ["Arial", "Helvetica", "Roboto", "Times New Roman"]

SPACING_SCALE = [4, 8, 12, 16, 20, 24, 32, 40, 48, 64]
OFFBRAND_SPACING = [5, 10, 15, 22, 30, 45, 70]

GOOD_NAMES = [
    "button-primary", "button-secondary", "header-nav", "card-title", "card-body",
    "input-email", "input-password", "badge-status", "icon-close", "divider-section",
    "nav-item", "hero-heading", "hero-subhead", "footer-links", "trust-badge",
    "cta-urgency", "price-tag", "avatar-user", "toast-success", "modal-title",
]
BAD_NAMES = ["Rectangle 12", "Group 7", "Layer 3 copy", "Frame 44", "asdasd", "Ellipse 2", "Untitled Layer"]

LAYER_TYPES = ["button", "text", "icon", "image", "container", "nav-item", "card", "input", "badge", "divider"]

SCREENS = [
    ("Login", "Build a login screen that feels fast and trustworthy, minimal fields.", ["input-email", "input-password", "button-primary", "trust-badge"]),
    ("Checkout", "Build a checkout screen emphasizing trust and urgency with one clear primary CTA.", ["trust-badge", "cta-urgency", "button-primary", "price-tag"]),
    ("Dashboard", "Build a dashboard surfacing the 3 most important metrics at a glance.", ["card-title", "card-body", "badge-status"]),
    ("Settings", "Build a settings screen organized into clear sections.", ["divider-section", "nav-item", "button-secondary"]),
    ("Pricing", "Build a pricing page that makes the recommended plan obvious.", ["price-tag", "badge-status", "button-primary", "cta-urgency"]),
    ("Onboarding", "Build a welcoming first-run onboarding flow.", ["hero-heading", "hero-subhead", "button-primary"]),
    ("Search results", "Build a search results screen that's easy to scan.", ["card-title", "card-body", "icon-close"]),
    ("Profile", "Build a profile screen showing identity and status clearly.", ["avatar-user", "badge-status", "button-secondary"]),
    ("Notification", "Build a success confirmation moment.", ["toast-success", "icon-close"]),
    ("Modal confirm", "Build a destructive-action confirmation modal.", ["modal-title", "button-primary", "button-secondary"]),
    ("Footer", "Build a footer with clear link groups.", ["footer-links", "divider-section"]),
    ("Nav bar", "Build a primary navigation bar.", ["header-nav", "nav-item", "avatar-user"]),
]

COMMENT_TEMPLATES = {
    "color": ["The CTA blue looks off-brand, feels too saturated.", "That warning badge color doesn't match our palette.", "Background feels like the wrong shade."],
    "spacing": ["Feels cramped near the footer, needs more breathing room.", "Too much whitespace between the header and content.", "Padding on the card looks inconsistent."],
    "typography": ["Font weight looks wrong on the heading.", "Body text feels like the wrong typeface.", "Line height on the subhead is too tight."],
    "layout": ["This breaks on tablet width, elements overlap.", "The CTA is buried below the fold.", "Card grid doesn't align to the same columns."],
    "copy": ["Typo in the button label.", "This copy doesn't match our tone of voice.", "Headline is too long for the space."],
    "other": ["Looks great overall, ship it.", "Nice work on this one, no notes.", "Minor polish only, approve as-is."],
}


def make_layer(good: bool, name_pool):
    name = random.choice(GOOD_NAMES if good else BAD_NAMES) if random.random() < (0.85 if good else 0.6) else random.choice(name_pool)
    hex_ = random.choice(list(BRAND_COLORS.values())) if good or random.random() < 0.7 else random.choice(OFFBRAND_COLORS)
    font = random.choice(BRAND_FONTS) if good or random.random() < 0.7 else random.choice(OFFBRAND_FONTS)
    spacing = random.choice(SPACING_SCALE) if good or random.random() < 0.7 else random.choice(OFFBRAND_SPACING)
    return {"name": name, "type": random.choice(LAYER_TYPES), "hex": hex_, "font": font, "spacing_px": spacing}


def layer_compliant(layer: dict) -> bool:
    name_ok = layer["name"] in GOOD_NAMES
    hex_ok = layer["hex"] in BRAND_COLORS.values()
    font_ok = layer["font"] in BRAND_FONTS
    spacing_ok = layer["spacing_px"] in SPACING_SCALE
    return name_ok and hex_ok and font_ok and spacing_ok


manifest = {}
for i, (title, brief, required) in enumerate(SCREENS * 2, start=1):  # 24 screens
    mostly_good = random.random() < 0.55
    n_layers = random.randint(5, 7)
    layers = [make_layer(mostly_good and random.random() < 0.75, required) for _ in range(n_layers)]
    # guarantee brief's required elements show up in >= half the screens, missing in the rest (real ground truth)
    fulfilled = random.random() < 0.6
    if fulfilled:
        layers += [{"name": r, "type": "layer", "hex": random.choice(list(BRAND_COLORS.values())),
                    "font": random.choice(BRAND_FONTS), "spacing_px": random.choice(SPACING_SCALE)} for r in required]

    prev_layers = [dict(l) for l in layers]
    breaking = random.random() < 0.35
    if breaking:
        removed = random.randint(1, min(2, len(prev_layers)))
        for _ in range(removed):
            idx = random.randrange(len(layers))
            layers.pop(idx)
    else:
        # a harmless tweak: one layer's spacing nudges slightly, nothing removed/retyped
        if layers:
            layers[0] = dict(layers[0])
            layers[0]["spacing_px"] = random.choice(SPACING_SCALE)

    category = random.choice(list(COMMENT_TEMPLATES))
    comment = random.choice(COMMENT_TEMPLATES[category])

    present_names = {l["name"] for l in layers}
    brief_match_fraction = round(len(present_names & set(required)) / len(required), 2)

    screen = {
        "title": f"{title} v{i}",
        "brief": brief,
        "required_elements": required,
        "review_comment": comment,
        "layers": layers,
        "prev_layers": prev_layers,
        "ground_truth": {
            "all_layers_compliant": all(layer_compliant(l) for l in layers),
            "noncompliant_layers": [l["name"] for l in layers if not layer_compliant(l)],
            "breaking_change": breaking,
            "comment_category": category,
            "brief_match_fraction": brief_match_fraction,
        },
    }
    fname = f"{i:02d}_screen.json"
    (OUT / fname).write_text(json.dumps(screen, indent=2))
    manifest[fname] = screen["ground_truth"]

(OUT / "brand_tokens.json").write_text(json.dumps({
    "colors": BRAND_COLORS, "fonts": BRAND_FONTS, "spacing_scale": SPACING_SCALE,
    "naming_rule": "lowercase-kebab-case describing the layer's role (e.g. 'button-primary', 'card-title') — not a generic default name like 'Rectangle 12' or 'Group 7'",
}, indent=2))

print(f"wrote {len(manifest)} screens + brand_tokens.json to {OUT}")
