"""Generate synthetic bank-statement-line vs ERP-ledger-line pairs for the reconciliation demo —
exact matches, fuzzy matches (FX rounding, fees, truncated names), and real mismatches."""
import json
import random
from pathlib import Path

random.seed(44)
ROOT = Path(__file__).parent
OUT = ROOT / "recon_pairs"
OUT.mkdir(exist_ok=True)

VENDORS = [
    ("Amazon Web Services", "AMZN WEB SVCS", "AWS*INV"),
    ("Northwind Supply Co", "NORTHWIND SUPPLY", "NW SUPPLY CO"),
    ("Ridgeline Legal Partners", "RIDGELINE LEGAL", "RIDGELINE LLP"),
    ("Cobalt Systems Inc", "COBALT SYS INC", "COBALT-SYS"),
    ("Fernway Retail", "FERNWAY RETAIL LLC", "FERNWAY*RETAIL"),
    ("BrightRoute Hosting", "BRIGHTROUTE HOST", "BRIGHTROUTE INC"),
]

CASES = ["exact", "fx_rounding", "banking_fee", "timing", "mismatched_vendor"]


def make_pair(idx: int) -> dict:
    vendor_full, bank_name, ledger_name = random.choice(VENDORS)
    base_amount = round(random.uniform(50, 8000), 2)
    case = random.choice(CASES)

    bank = {"description": bank_name, "amount": base_amount, "date": f"2026-0{random.randint(1,9)}-{random.randint(1,28):02d}"}
    ledger = {"description": ledger_name, "amount": base_amount, "date": bank["date"]}

    if case == "fx_rounding":
        ledger["amount"] = round(base_amount * random.uniform(0.995, 1.005), 2)
    elif case == "banking_fee":
        bank["amount"] = round(base_amount + random.uniform(0.5, 12), 2)
    elif case == "timing":
        d = int(bank["date"].split("-")[-1])
        ledger["date"] = bank["date"].rsplit("-", 1)[0] + f"-{min(d+1, 28):02d}"
    elif case == "mismatched_vendor":
        other_vendor = random.choice([v for v in VENDORS if v[0] != vendor_full])
        ledger["description"] = other_vendor[2]
        ledger["amount"] = round(random.uniform(50, 8000), 2)

    is_match = case != "mismatched_vendor"
    reason = "none" if case == "exact" else case

    return {
        "pair_id": f"pair_{idx:04d}",
        "bank_line": bank,
        "ledger_line": ledger,
        "ground_truth": {"is_match": is_match, "discrepancy_reason": reason},
    }


manifest = {}
for i in range(1, 31):
    pair = make_pair(i)
    fname = f"{i:02d}_pair.json"
    (OUT / fname).write_text(json.dumps(pair, indent=2))
    manifest[fname] = pair["ground_truth"]

print(f"wrote {len(manifest)} pairs to {OUT}")
