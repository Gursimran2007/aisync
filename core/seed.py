"""Seed / demo data generator for AISync (HPL spare inventory).

Produces a realistic capital-spares portfolio for a petrochemical plant:
  * ~₹282 Cr of working capital blocked across ~17 spare lines
  * a mix of critical / essential / non-critical spares
  * ~27% of capital sitting in obsolete stock (no issue in >5 years)
  * intermittent, lumpy and steady consumption so the AI forecaster has real
    weekly-maintenance rhythm and momentum to learn.

Also writes a deliberately MESSY spare-issue Excel so the auto-mapping upload
demo has something to chew on.
"""
import random
from datetime import date, timedelta
from pathlib import Path
import pandas as pd
from . import db

random.seed(42)

# sku, name, equipment, criticality, unit_cost(₹), on_hand, base_daily,
# pattern, lead_days, reliability, last_issue_years_ago
CATALOG = [
    # ---- active spares ----
    ("CGC-ROTOR",  "Cracked Gas Compressor Rotor Assembly", "GB-201 Cracked Gas Compressor",
     "critical",     65_000_000,   3, 0.05, "intermittent", 210, 0.85, 0.25),
    ("FURN-COIL",  "Furnace Radiant Coil Section",          "BA-101 Cracking Furnace",
     "critical",      4_500_000,  60, 0.80, "intermittent", 120, 0.90, 0.15),
    ("HX-BUNDLE",  "Heat Exchanger Tube Bundle",            "EA-305 Quench Exchanger",
     "critical",      3_800_000,  55, 0.35, "intermittent", 150, 0.88, 0.20),
    ("MECH-SEAL",  "Mechanical Seal Cartridge (BB3)",       "Process Pumps (plant-wide)",
     "essential",       320_000, 650, 6.00, "regular_up",    45, 0.95, 0.02),
    ("CTRL-VALVE", "Control Valve Trim Set 3in",            "Flow control loops",
     "essential",       850_000, 330, 2.50, "regular",       60, 0.93, 0.03),
    ("HT-MOTOR",   "6.6kV HT Induction Motor",              "Large drives / compressors",
     "essential",     3_500_000,  60, 0.40, "intermittent", 120, 0.90, 0.10),
    ("DCS-IO",     "DCS Analog I/O Card",                   "Honeywell DCS",
     "essential",       180_000,1000, 8.00, "regular",       40, 0.94, 0.01),
    ("PUMP-BB3",   "Centrifugal Pump BB3 (bare shaft)",     "Charge / reflux pumps",
     "essential",     2_200_000,  75, 0.60, "intermittent",  90, 0.90, 0.05),
    ("BEARING",    "Antifriction Bearing Set",              "Rotating equipment (plant-wide)",
     "non-critical",     45_000,1440,12.00, "regular_up",    30, 0.96, 0.01),
    ("SW-GASKET",  "Spiral Wound Gasket (assorted)",        "Flanged joints (plant-wide)",
     "non-critical",      2_500, 4200,35.0, "regular",       21, 0.97, 0.01),
    ("RELIEF-VLV", "Pressure Safety / Relief Valve",        "Pressure systems",
     "essential",     4_800_000,  30, 0.15, "intermittent", 150, 0.90, 0.08),
    # ---- obsolete / dead stock (no issue in >5 yrs) ----
    ("STURB-BLADE","Steam Turbine Blade Set (Frame-5 legacy)","VK-401 Steam Turbine (decommissioned)",
     "essential",     9_000_000,  12, 0.0, "dead", 200, 0.85, 6.5),
    ("VFD-MOD",    "Legacy VFD Power Module (Gen-2)",       "Old variable-speed drives",
     "non-critical",  1_500_000,  65, 0.0, "dead",  90, 0.80, 5.8),
    ("BFLY-VLV",   "Butterfly Valve 24in (superseded spec)","Cooling water (old spec)",
     "non-critical",    650_000, 300, 0.0, "dead",  60, 0.85, 6.2),
    ("PT-XMTR",    "Pressure Transmitter (HART-legacy)",    "Field instruments (legacy)",
     "non-critical",    950_000, 150, 0.0, "dead",  45, 0.90, 5.5),
    ("RECIP-PISTON","Reciprocating Compressor Piston (old unit)","Decommissioned recip compressor",
     "non-critical",  3_200_000,  40, 0.0, "dead", 120, 0.80, 7.0),
    ("LEGACY-DCS", "Legacy DCS Controller (TDC-3000)",      "Obsolete control system",
     "non-critical",  2_200_000,  40, 0.0, "dead",  60, 0.75, 6.8),
]

START = date.today() - timedelta(days=120)


def _series(base, pattern, days=120):
    """Generate a spare-consumption (issue) history over `days` days.

    Plants run 24/7, but planned-maintenance windows cluster issues on certain
    weekdays — that mild weekly rhythm is what the AI forecaster learns.
    """
    out = []
    for i in range(days):
        d = START + timedelta(days=i)
        # planned maintenance leans to mid-week (Tue/Wed) shutof windows
        wk = 1.4 if d.weekday() in (1, 2) else (0.7 if d.weekday() >= 5 else 1.0)
        if pattern == "regular":
            q = max(0, round(random.gauss(base, base * 0.3) * wk))
        elif pattern == "regular_up":
            q = max(0, round(random.gauss(base + i * 0.03, base * 0.3) * wk))
        elif pattern == "intermittent":
            # a discrete issue every ~1/base days, size 1-2
            q = (1 + (1 if random.random() < 0.3 else 0)) \
                if random.random() < base else 0
        elif pattern == "lumpy":
            q = round(random.gauss(base * 8, base * 3)) if random.random() < 0.12 else 0
            q = max(0, q)
        else:                      # "dead" -> no movement
            q = 0
        if q > 0:
            out.append((d, q))
    return out


def seed_db(db_path=None):
    db.reset_db(db_path)
    products, sales, inv, sup = [], [], [], []
    for (sku, name, equip, crit, cost, oh, base, pat, lead, rel, last_yr) in CATALOG:
        series = _series(base, pat)
        if series:
            last_issue = series[-1][0].isoformat()
        else:
            last_issue = (date.today() - timedelta(days=int(last_yr * 365.25))).isoformat()
        products.append({"sku": sku, "name": name, "unit_cost": cost,
                         "criticality": crit, "equipment": equip,
                         "last_issue_date": last_issue})
        inv.append({"sku": sku, "stock": oh})
        sup.append({"sku": sku, "lead_time_days": lead, "reliability": rel})
        for d, q in series:
            sales.append({"sku": sku, "date": d.isoformat(), "qty": q})
    db.upsert_products(products, db_path)
    db.insert_sales(sales, db_path)
    db.upsert_inventory(inv, db_path)
    db.upsert_suppliers(sup, db_path)
    return {"products": len(products), "sales": len(sales)}


def write_messy_excel(path=None):
    """Messy spare-issue export: scrambled columns, odd headers, ₹, mixed dates."""
    path = Path(path or Path(__file__).resolve().parent.parent / "demo_messy.xlsx")
    rows = []
    fmts = ["%d-%m-%Y", "%d/%m/%Y", "%Y-%m-%d", "%d-%b-%Y"]
    for (sku, name, equip, crit, cost, oh, base, pat, lead, rel, last_yr) in CATALOG[:6]:
        for d, q in _series(base, pat if pat != "dead" else "intermittent", days=60):
            rows.append({
                "Material Desc": name,               # name (odd header)
                "Qty Issued": q,                     # qty (odd header)
                "Material Code": sku,                # sku (odd header)
                "Posting Dt": d.strftime(random.choice(fmts)),  # mixed dates
                "Unrestricted Stock": oh,            # stock (odd header)
                "Moving Avg Price": f"\u20b9{cost:,}",  # unit_cost with ₹
            })
    df = pd.DataFrame(rows)[["Material Desc", "Qty Issued", "Material Code",
                             "Posting Dt", "Unrestricted Stock", "Moving Avg Price"]]
    df.to_excel(path, index=False)
    return str(path)


if __name__ == "__main__":
    print(seed_db())
    print("messy excel:", write_messy_excel())
