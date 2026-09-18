"""Generate synthetic payment transactions for the fraud/risk-triage demo — amount, geo-velocity,
device trust signal, merchant category, account age — with injected fraud patterns and ground
truth computed directly from the same rules used in the prompt.
"""
import json
import random
from pathlib import Path

random.seed(33)
ROOT = Path(__file__).parent
OUT = ROOT / "fraud_transactions"
OUT.mkdir(exist_ok=True)

MERCHANTS = ["Electronics Superstore", "Gift Card Kiosk", "Grocery Co-op", "Airline Ticketing",
             "Streaming Service", "Coffee Shop", "Crypto Exchange", "Luxury Watch Retailer",
             "Pharmacy", "Home Improvement", "Ride Share", "Wire Transfer Service"]
COUNTRIES = ["US", "US", "US", "GB", "DE", "SG", "NG", "RU", "BR", "VN"]
DEVICE_NOTES = [
    "known device, 40 prior transactions, no flags",
    "new device, first transaction on this account",
    "device fingerprint changed twice in past hour",
    "known device, biometric confirmed",
    "device reports emulator characteristics",
    "known device, but SIM swapped 2 hours ago",
]


def make_txn(idx: int) -> dict:
    account_age_days = random.choice([2, 5, 14, 45, 120, 400, 900, 1800])
    billing_country = random.choice(COUNTRIES[:3])
    ip_country = billing_country if random.random() < 0.7 else random.choice(COUNTRIES)
    geo_velocity_kmh = random.choice([0, 0, 0, 40, 300, 850, 4200, 9000])
    amount = round(random.uniform(8, 4500), 2)
    merchant = random.choice(MERCHANTS)
    device_note = random.choice(DEVICE_NOTES)

    risk_points = 0
    if ip_country != billing_country: risk_points += 1
    if geo_velocity_kmh > 800: risk_points += 2
    if account_age_days < 7: risk_points += 1
    if "emulator" in device_note or "SIM swapped" in device_note or "changed twice" in device_note: risk_points += 2
    if merchant in ("Gift Card Kiosk", "Crypto Exchange", "Wire Transfer Service") and amount > 1000: risk_points += 1
    if amount > 3000: risk_points += 1

    if risk_points >= 5:
        risk_level, route = "critical", "block"
    elif risk_points >= 3:
        risk_level, route = "high", "step_up"
    elif risk_points >= 1:
        risk_level, route = "medium", "step_up" if risk_points >= 2 else "approve"
    else:
        risk_level, route = "low", "approve"

    return {
        "transaction_id": f"txn_{idx:04d}",
        "amount_usd": amount,
        "merchant_category": merchant,
        "billing_country": billing_country,
        "ip_country": ip_country,
        "geo_velocity_kmh": geo_velocity_kmh,
        "account_age_days": account_age_days,
        "device_note": device_note,
        "ground_truth": {"risk_level": risk_level, "route": route, "risk_points": risk_points},
    }


manifest = {}
for i in range(1, 31):
    txn = make_txn(i)
    fname = f"{i:02d}_txn.json"
    (OUT / fname).write_text(json.dumps(txn, indent=2))
    manifest[fname] = txn["ground_truth"]

print(f"wrote {len(manifest)} transactions to {OUT}")
