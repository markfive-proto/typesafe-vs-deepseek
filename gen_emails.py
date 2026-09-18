"""Generate 50 synthetic sample emails as .md files for the classifier demo."""
import random
from pathlib import Path

random.seed(7)
ROOT = Path(__file__).parent
OUT = ROOT / "emails_samples"
OUT.mkdir(exist_ok=True)

NAMES = ["Alex Chen", "Priya Nair", "Jordan Blake", "Mei Tanaka", "Sam Okafor",
         "Lucia Ramos", "Ivan Petrov", "Grace Lin", "Noah Weiss", "Fatima Ali"]
COMPANIES = ["Northwind Labs", "Cobalt Systems", "Vertex Studio", "Harbor & Co",
             "Loom Digital", "Ridgeline Partners", "Fernway", "Attic Robotics"]
PRODUCTS = ["Nimbus Pro", "TrailRunner boots", "AeroDesk chair", "CloudSync",
            "the Q3 report", "FocusFlow", "the invoice tool", "BrightRoute API"]

TEMPLATES = [
    ("work", lambda: (
        f"Status update: {random.choice(PRODUCTS)}",
        random.choice(NAMES),
        f"""Hey team,

Quick update on {random.choice(PRODUCTS)}. We closed out the sprint with
{random.randint(3, 14)} tickets done, {random.randint(0, 3)} carried over.

Blockers: {random.choice(["none", "waiting on design review", "staging env flaky", "need sign-off from legal"])}.

Standup moved to {random.choice(["10am", "2pm", "9:30am"])} tomorrow, same link.

{random.choice(NAMES)}
"""
    )),
    ("personal", lambda: (
        f"{random.choice(['Dinner Saturday?', 'Long time no see', 'Trip photos', 'Quick catch up?'])}",
        random.choice(NAMES),
        f"""Hey!

{random.choice([
    "Been way too long, are you free this weekend?",
    "Finally sorting through photos from the trip, sending a few over.",
    "Happy birthday for last week, sorry I'm late!",
    "Saw this and thought of you, made me laugh.",
])}

Let me know when works for you.

{random.choice(NAMES)}
"""
    )),
    ("newsletter", lambda: (
        f"{random.choice(COMPANIES)} Digest — Issue #{random.randint(12, 210)}",
        f"{random.choice(COMPANIES)} Newsletter",
        f"""This week in the industry:

- {random.choice(PRODUCTS)} hits {random.randint(10, 900)}k users
- {random.choice(['Interest rates hold steady', 'New privacy law passes', 'Layoffs continue at big tech', 'Open-source project hits 1.0'])}
- Reader poll: {random.randint(40, 90)}% want more deep dives

Read the full issue on our site. Unsubscribe anytime.
"""
    )),
    ("promotional", lambda: (
        f"{random.choice(['⚡ Flash sale', 'Last chance', 'Your cart is waiting', 'New drop'])}: {random.randint(10, 70)}% off {random.choice(PRODUCTS)}",
        random.choice(COMPANIES),
        f"""For a limited time, save {random.randint(10, 70)}% on {random.choice(PRODUCTS)}.

Use code SAVE{random.randint(10, 70)} at checkout. Offer ends {random.choice(['tonight', 'this Friday', 'in 48 hours'])}.

Shop now — link in this email.
"""
    )),
    ("spam", lambda: (
        random.choice([
            "You've WON a prize!!! Claim now",
            "URGENT: verify your account or lose access",
            "Re: your loan pre-approval",
            "Hot singles near you",
        ]),
        random.choice(["security@totally-real-bank.co", "prizes@claim-now.biz", "no-reply@urgent-verify.ru"]),
        f"""Congratulations! You have been selected to receive ${random.randint(500, 90000)}.

Click the link below within 24 hours and enter your bank details to claim
your reward. This offer is not available anywhere else.

CLAIM NOW: http://totally-legit-prize-claim.example/{random.randint(1000,9999)}
"""
    )),
    ("transactional", lambda: (
        f"{random.choice(['Your receipt from', 'Order confirmed —', 'Shipped:', 'Payment received —'])} {random.choice(COMPANIES)}",
        f"{random.choice(COMPANIES)} Orders",
        f"""Order #{random.randint(10000,99999)} confirmed.

Item: {random.choice(PRODUCTS)}
Total: ${random.randint(12, 480)}.{random.randint(0,99):02d}
{random.choice(['Estimated delivery', 'Billed to card ending', 'Next charge'])}: {random.choice(['3-5 business days', '4821', random.choice(['Oct 1', 'Nov 3', 'Dec 12'])])}

Questions? Reply to this email.
"""
    )),
    ("support_urgent", lambda: (
        f"{random.choice(['URGENT:', 'Production down —', 'Action needed:', 'Escalation:'])} {random.choice(PRODUCTS)} {random.choice(['outage', 'billing error', 'data mismatch', 'login broken'])}",
        random.choice(NAMES),
        f"""We're seeing {random.choice(['500 errors', 'failed logins', 'a billing discrepancy', 'missing data'])}
on {random.choice(PRODUCTS)} since {random.choice(['this morning', '20 minutes ago', 'last night'])}.

Affected: {random.choice(['all customers', 'EU region', 'about 12% of accounts', 'enterprise tier'])}.
Need this looked at ASAP, customers are asking.

{random.choice(NAMES)}
"""
    )),
]

count = 0
per_cat = 50 // len(TEMPLATES)
remainder = 50 - per_cat * len(TEMPLATES)

for idx, (label, gen) in enumerate(TEMPLATES):
    n = per_cat + (1 if idx < remainder else 0)
    for _ in range(n):
        count += 1
        subject, sender, body = gen()
        date = f"2026-{random.randint(1,9):02d}-{random.randint(1,28):02d}"
        md = f"""---
from: {sender}
subject: {subject}
date: {date}
---

{body}"""
        (OUT / f"{count:02d}_{label}.md").write_text(md)

print(f"wrote {count} sample emails to {OUT}")
