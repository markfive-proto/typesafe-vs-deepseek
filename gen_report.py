"""Render invoices.json into a single static HTML report."""
import json
import re
from pathlib import Path
from html import escape

ROOT = Path(__file__).parent
DATA = json.loads((ROOT / "invoices.json").read_text())


def parse_amount(s):
    if not s:
        return None
    m = re.search(r"[\d,]+\.\d{2}", s)
    return float(m.group().replace(",", "")) if m else None


rows = []
amounts = []
confs = []
for inv in DATA:
    amt = parse_amount(inv.get("total_amount"))
    if amt is not None:
        amounts.append(amt)
    if inv.get("total_confidence") is not None:
        confs.append(inv["total_confidence"])
    rows.append(inv)

total_sum = sum(amounts)
avg_conf = (sum(confs) / len(confs)) if confs else 0

CAT_LABEL = {
    "goods": "Goods",
    "services": "Services",
    "utilities_subscription": "Utilities / Subscription",
    "other": "Other",
    None: "Unclassified",
}


def conf_class(c):
    if c is None:
        return "conf-none"
    if c >= 0.85:
        return "conf-high"
    if c >= 0.6:
        return "conf-mid"
    return "conf-low"


def conf_label(c):
    return "—" if c is None else f"{round(c * 100)}%"


card_html = []
for inv in rows:
    err = inv.get("error")
    if err:
        card_html.append(f"""
        <article class="card card-error">
          <div class="card-head">
            <h3>{escape(inv['file'])}</h3>
            <span class="pill pill-error">OCR/API failed</span>
          </div>
          <p class="error-msg">{escape(err)}</p>
        </article>""")
        continue

    items = inv.get("line_items") or []
    items_html = "".join(f"<li>{escape(x)}</li>" for x in items) if items else "<li class='empty'>none detected</li>"
    amt = inv.get("total_amount") or "—"
    conf = inv.get("total_confidence")

    card_html.append(f"""
        <article class="card">
          <div class="card-head">
            <div>
              <h3>{escape(inv.get('vendor_guess') or inv['file'])}</h3>
              <p class="file-name">{escape(inv['file'])}</p>
            </div>
            <span class="pill {conf_class(conf)}">{conf_label(conf)} conf.</span>
          </div>
          <dl class="fields">
            <div><dt>Category</dt><dd>{escape(CAT_LABEL.get(inv.get('category'), inv.get('category') or '—'))}</dd></div>
            <div><dt>Invoice #</dt><dd class="num">{escape(inv.get('invoice_number') or '—')}</dd></div>
            <div><dt>Date</dt><dd class="num">{escape(inv.get('invoice_date') or '—')}</dd></div>
            <div><dt>Total</dt><dd class="num total">{escape(amt)}</dd></div>
          </dl>
          <div class="items">
            <h4>Line items ({len(items)})</h4>
            <ul>{items_html}</ul>
          </div>
        </article>""")

html_out = f"""<title>Invoice Ledger</title>
<style>
:root {{
  --bg: #f7f5f0;
  --surface: #ffffff;
  --ink: #1c1a17;
  --muted: #736b5c;
  --border: #e6ded0;
  --accent: #2a5d50;
  --accent-soft: #e4efe9;
  --warn: #a8501c;
  --warn-soft: #f6e6d9;
  --bad: #9c3b3b;
  --bad-soft: #f5e3e1;
}}
@media (prefers-color-scheme: dark) {{
  :root:not([data-theme="light"]) {{
    --bg: #15130f;
    --surface: #1e1b16;
    --ink: #ede6d9;
    --muted: #a89b85;
    --border: #35301f;
    --accent: #5fa38d;
    --accent-soft: #223a32;
    --warn: #e0925a;
    --warn-soft: #3a2a1c;
    --bad: #d97b7b;
    --bad-soft: #3a2222;
  }}
}}
:root[data-theme="dark"] {{
  --bg: #15130f;
  --surface: #1e1b16;
  --ink: #ede6d9;
  --muted: #a89b85;
  --border: #35301f;
  --accent: #5fa38d;
  --accent-soft: #223a32;
  --warn: #e0925a;
  --warn-soft: #3a2a1c;
  --bad: #d97b7b;
  --bad-soft: #3a2222;
}}

* {{ box-sizing: border-box; }}
body {{
  margin: 0;
  background: var(--bg);
  color: var(--ink);
  font-family: "IBM Plex Sans", -apple-system, sans-serif;
  padding: 32px 16px 48px;
}}
.wrap {{ max-width: 980px; margin: 0 auto; }}

header.top {{
  display: flex;
  flex-wrap: wrap;
  gap: 24px;
  justify-content: space-between;
  align-items: flex-end;
  border-bottom: 2px solid var(--ink);
  padding-bottom: 20px;
  margin-bottom: 28px;
}}
header.top h1 {{
  font-family: "Fraunces", Georgia, serif;
  font-size: clamp(2rem, 5vw, 2.8rem);
  font-weight: 600;
  margin: 0 0 4px;
  text-wrap: balance;
}}
header.top p.sub {{ margin: 0; color: var(--muted); font-size: 0.95rem; }}

.stats {{ display: flex; gap: 12px; flex-wrap: wrap; }}
.stat {{
  background: var(--surface);
  border: 1px solid var(--border);
  border-radius: 10px;
  padding: 12px 18px;
  min-width: 130px;
}}
.stat .n {{
  font-family: "IBM Plex Mono", monospace;
  font-variant-numeric: tabular-nums;
  font-size: 1.5rem;
  font-weight: 600;
  color: var(--accent);
}}
.stat .l {{ font-size: 0.72rem; text-transform: uppercase; letter-spacing: 0.06em; color: var(--muted); }}

.grid {{
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(300px, 1fr));
  gap: 16px;
}}
.card {{
  background: var(--surface);
  border: 1px solid var(--border);
  border-radius: 12px;
  padding: 18px 20px;
  display: flex;
  flex-direction: column;
  gap: 14px;
}}
.card-error {{ border-color: var(--bad); }}
.card-head {{ display: flex; justify-content: space-between; align-items: flex-start; gap: 10px; }}
.card-head h3 {{
  font-family: "Fraunces", Georgia, serif;
  font-size: 1.1rem;
  font-weight: 600;
  margin: 0;
  text-wrap: balance;
}}
.file-name {{ margin: 2px 0 0; font-size: 0.75rem; color: var(--muted); word-break: break-all; }}

.pill {{
  flex: none;
  font-size: 0.72rem;
  font-weight: 600;
  padding: 3px 9px;
  border-radius: 99px;
  white-space: nowrap;
}}
.conf-high {{ background: var(--accent-soft); color: var(--accent); }}
.conf-mid  {{ background: var(--warn-soft); color: var(--warn); }}
.conf-low  {{ background: var(--bad-soft); color: var(--bad); }}
.conf-none {{ background: var(--border); color: var(--muted); }}
.pill-error {{ background: var(--bad-soft); color: var(--bad); }}

.fields {{
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 10px 16px;
  margin: 0;
  border-top: 1px solid var(--border);
  border-bottom: 1px solid var(--border);
  padding: 12px 0;
}}
.fields dt {{ font-size: 0.68rem; text-transform: uppercase; letter-spacing: 0.05em; color: var(--muted); margin: 0 0 2px; }}
.fields dd {{ margin: 0; font-size: 0.9rem; }}
.fields dd.num {{ font-family: "IBM Plex Mono", monospace; font-variant-numeric: tabular-nums; }}
.fields dd.total {{ font-weight: 600; color: var(--accent); }}

.items h4 {{ margin: 0 0 8px; font-size: 0.78rem; text-transform: uppercase; letter-spacing: 0.05em; color: var(--muted); }}
.items ul {{ margin: 0; padding: 0 0 0 18px; font-size: 0.85rem; line-height: 1.55; }}
.items li.empty {{ list-style: none; padding-left: -18px; margin-left: -18px; color: var(--muted); font-style: italic; }}
.error-msg {{ font-size: 0.85rem; color: var(--bad); margin: 0; }}

footer {{ margin-top: 36px; font-size: 0.78rem; color: var(--muted); border-top: 1px solid var(--border); padding-top: 14px; }}
footer code {{ font-family: "IBM Plex Mono", monospace; background: var(--accent-soft); color: var(--accent); padding: 1px 5px; border-radius: 4px; }}
</style>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link href="https://fonts.googleapis.com/css2?family=Fraunces:wght@500;600&family=IBM+Plex+Sans:wght@400;500;600&family=IBM+Plex+Mono:wght@400;500&display=swap" rel="stylesheet">

<div class="wrap">
  <header class="top">
    <div>
      <h1>Invoice Ledger</h1>
      <p class="sub">{len(rows)} invoices · OCR (Vision.framework) → TypeSafe Jev classification &amp; extraction</p>
    </div>
    <div class="stats">
      <div class="stat"><div class="n">{len(rows)}</div><div class="l">Invoices</div></div>
      <div class="stat"><div class="n">${total_sum:,.2f}</div><div class="l">Total detected</div></div>
      <div class="stat"><div class="n">{round(avg_conf * 100)}%</div><div class="l">Avg. total confidence</div></div>
    </div>
  </header>

  <section class="grid">
    {"".join(card_html)}
  </section>

  <footer>
    Pipeline: <code>ocr.swift</code> (native Vision OCR, no deps) → <code>pipeline.py</code>
    (TypeSafe <code>Choice</code> questions classify each OCR line as line-item / header / total / noise,
    and pick invoice number / date / total from regex-found candidates) → this report.
    Multi-column tables can interleave in OCR line order — verify totals against the source image.
  </footer>
</div>
"""

(ROOT / "report.html").write_text(html_out)
print("wrote report.html")
