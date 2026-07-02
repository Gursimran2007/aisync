"""Spare-inventory optimization layer for HPL (AISync).

Sits on top of engine.build_report() and reframes its retail output into the
capital-spares world the HPL pitch describes:

  * working capital blocked in spares (in crore)
  * obsolete / dead stock detection (no movement in >5 years)
  * criticality-based safety stock (critical spares protected, non-critical trimmed)
  * shutdown-risk scoring (criticality x stockout risk)
  * predictive-maintenance signal (accelerating consumption -> likely failures)

All numbers are COMPUTED from the plant's real data — never guessed — so the
same grounding guarantee the assistant relies on holds for spares too.
"""
from __future__ import annotations
from datetime import date, datetime

from .engine import build_report, CRITICALITY_SERVICE
from .assistant import answer as _answer, _tok

OBSOLETE_YEARS = 5          # no issue in >5 yrs => dead capital (HPL: 27% of stock)
CRIT_WEIGHT = {"critical": 3, "essential": 2, "non-critical": 1}
RISK_WEIGHT = {"high": 3, "medium": 2, "low": 1}
CRIT_ORDER = {"critical": 0, "essential": 1, "non-critical": 2}
DEAD_RATE = 0.02            # effectively-zero daily consumption

# Ultra-expensive critical spares (a cracked-gas-compressor rotor) are held as
# strategic INSURANCE, not to satisfy demand. You keep 1-2 on site so a single
# failure can't idle the train — you never "demand-forecast" them and never
# call the stock excess. Below: what qualifies and the strategic minimum.
INSURANCE_COST = 1e7        # >= ₹1 Cr/unit
INSURANCE_MIN = 2           # target spares held per critical train


# ---- money formatting (Indian crore scale) -------------------------------
def inr(x: float) -> str:
    return f"\u20b9{x:,.0f}"


def cr(x: float) -> str:
    """Rupees -> '₹XX.XX Cr' (1 crore = 1e7)."""
    return f"\u20b9{x / 1e7:,.2f} Cr"


def lakh(x: float) -> str:
    return f"\u20b9{x / 1e5:,.1f} L"


# ---- helpers -------------------------------------------------------------
def _age_years(last_issue_date):
    if not last_issue_date:
        return None
    try:
        d = datetime.fromisoformat(str(last_issue_date)[:10]).date()
    except ValueError:
        return None
    return (date.today() - d).days / 365.25


def _shutdown_label(score):
    return "high" if score >= 6 else "medium" if score >= 3 else "low"


# ---- the enrichment pass -------------------------------------------------
def analyze(report=None, service_by_sku=None, db_path=None):
    """Return report rows enriched with spare-optimization fields.

    Each row gains: capital, age_years, obsolete, dead, optimal_stock,
    excess_units, excess_value, release_value, shutdown_score, shutdown_risk.
    """
    if report is None:
        report = build_report(service_by_sku=service_by_sku, db_path=db_path)
    rows = []
    for r in report:
        on_hand = float(r["on_hand"] or 0)
        cost = float(r["unit_cost"] or 0)
        rate = float(r["reorder"]["daily_rate"] or 0)
        crit = (r.get("criticality") or "essential").lower()
        capital = on_hand * cost
        age = _age_years(r.get("last_issue_date"))

        # Dead = holding stock but essentially never consumed. Critical spares
        # are strategic insurance (a compressor rotor may sit for years by
        # design) — never call them dead just for low movement.
        dead = on_hand > 0 and rate <= DEAD_RATE and crit != "critical"
        # Obsolete = no movement in >OBSOLETE_YEARS, or dead with a stale date.
        obsolete = (age is not None and age >= OBSOLETE_YEARS and crit != "critical") \
                   or (dead and (age is None or age >= 2))

        # Insurance spare: an ultra-expensive critical unit held to a strategic
        # minimum, not a demand forecast. Its "reorder need" and risk key off
        # how many we hold vs the min, and it can never be flagged excess.
        insurance = crit == "critical" and cost >= INSURANCE_COST

        optimal = float(r["reorder"].get("max_level", 0) or 0)
        if insurance:
            reco_qty = max(INSURANCE_MIN - int(on_hand), 0)
            risk = ("high" if on_hand < 1 else
                    "medium" if on_hand < INSURANCE_MIN else "low")
            excess_units = 0.0
        else:
            reco_qty = int(r["reorder"]["suggested_qty"])
            risk = r["reorder"]["stockout_risk"]
            # Only non-critical/essential lines can hold releasable excess;
            # critical strategic stock is never trimmed.
            excess_units = (max(on_hand - optimal, 0.0)
                            if not obsolete and crit != "critical" else 0.0)
        excess_value = excess_units * cost
        # Capital we could release: whole line if obsolete, else the excess
        # above the AI-optimal max level.
        release_value = capital if obsolete else excess_value

        score = CRIT_WEIGHT.get(crit, 2) * RISK_WEIGHT.get(risk, 1)

        rows.append({
            **r,
            "capital": capital,
            "age_years": age,
            "obsolete": obsolete,
            "dead": dead,
            "insurance": insurance,
            "optimal_stock": optimal,
            "reco_qty": reco_qty,
            "risk": risk,
            "excess_units": excess_units,
            "excess_value": excess_value,
            "release_value": release_value,
            "shutdown_score": score,
            "shutdown_risk": _shutdown_label(score),
        })
    return rows


# ---- portfolio roll-up (the executive KPIs) ------------------------------
def portfolio(rows):
    total_capital = sum(r["capital"] for r in rows)
    obsolete_value = sum(r["capital"] for r in rows if r["obsolete"])
    excess_value = sum(r["excess_value"] for r in rows if not r["obsolete"])
    release = obsolete_value + excess_value

    by_crit = {"critical": 0.0, "essential": 0.0, "non-critical": 0.0}
    cnt_crit = {"critical": 0, "essential": 0, "non-critical": 0}
    for r in rows:
        c = r.get("criticality", "essential")
        by_crit[c] = by_crit.get(c, 0.0) + r["capital"]
        cnt_crit[c] = cnt_crit.get(c, 0) + 1

    critical_at_risk = [r for r in rows
                        if r.get("criticality") == "critical"
                        and r["risk"] in ("high", "medium")]
    shutdown_exposed = [r for r in rows if r["shutdown_risk"] == "high"]

    return {
        "n_spares": len(rows),
        "total_capital": total_capital,
        "obsolete_value": obsolete_value,
        "obsolete_pct": (obsolete_value / total_capital * 100) if total_capital else 0,
        "excess_value": excess_value,
        "release_opportunity": release,
        "release_pct": (release / total_capital * 100) if total_capital else 0,
        "by_criticality": by_crit,
        "count_by_criticality": cnt_crit,
        "n_obsolete": sum(1 for r in rows if r["obsolete"]),
        "critical_at_risk": critical_at_risk,
        "shutdown_exposed": shutdown_exposed,
    }


def obsolete_rows(rows):
    return sorted([r for r in rows if r["obsolete"]],
                  key=lambda r: -r["capital"])


def reorder_rows(rows):
    """Spares that need replenishment, worst shutdown risk first."""
    need = [r for r in rows if r["reco_qty"] > 0]
    return sorted(need, key=lambda r: (-r["shutdown_score"], -r["reco_qty"]))


def excess_rows(rows):
    return sorted([r for r in rows if not r["obsolete"] and r["excess_value"] > 0],
                  key=lambda r: -r["excess_value"])


def predictive_maintenance(rows, min_momentum=12.0):
    """Spares whose consumption is accelerating — an early signal that the
    equipment they serve is heading toward failure. Reorder BEFORE breakdown."""
    out = []
    for r in rows:
        a = r["forecast"].get("ai_analysis")
        if not a:
            continue
        mom = a.get("momentum_pct", 0) or 0
        trend = a.get("trend_pct_month", 0) or 0
        if mom >= min_momentum or trend >= min_momentum:
            out.append({**r, "momentum_pct": mom, "trend_pct_month": trend})
    return sorted(out, key=lambda r: -(r["momentum_pct"] + r["trend_pct_month"]))


# ---- grounded Q&A facts for the "Ask AISync" page ------------------------
def build_facts(rows=None, db_path=None):
    """Spare-domain fact cards for the grounded assistant (reuses its TF-IDF)."""
    if rows is None:
        rows = analyze(db_path=db_path)
    pf = portfolio(rows)
    cards = []

    cards.append({
        "keywords": "total capital blocked working spares inventory value "
                    "how much money tied crore overall plant",
        "answer": (
            f"**{cr(pf['total_capital'])}** of working capital is currently "
            f"blocked across {pf['n_spares']} spare line(s). Of that, "
            f"**{cr(pf['release_opportunity'])}** ({pf['release_pct']:.0f}%) is a "
            f"realistic optimization opportunity without hurting reliability."),
    })
    cards.append({
        "keywords": "release opportunity working capital free up save reduce "
                    "optimization potential how much crore unlock",
        "answer": (
            f"AISync estimates **{cr(pf['release_opportunity'])}** can be released "
            f"— {cr(pf['obsolete_value'])} in obsolete/dead stock plus "
            f"{cr(pf['excess_value'])} in excess above AI-optimal levels."),
    })
    cards.append({
        "keywords": "obsolete dead stock old five years not moving unused "
                    "which spares spare parts lines list write off redeploy scrap "
                    "27 percent",
        "answer": (
            f"**{pf['n_obsolete']} spare line(s)** worth **{cr(pf['obsolete_value'])}** "
            f"({pf['obsolete_pct']:.0f}% of capital) show no movement in over "
            f"{OBSOLETE_YEARS} years — candidates for redeployment, resale or "
            f"write-down."),
    })
    cards.append({
        "keywords": "critical spares risk shutdown reliability stockout "
                    "essential non-critical criticality mix breakdown",
        "answer": (
            f"Capital by criticality — critical {cr(pf['by_criticality']['critical'])}, "
            f"essential {cr(pf['by_criticality']['essential'])}, non-critical "
            f"{cr(pf['by_criticality']['non-critical'])}. "
            f"{len(pf['critical_at_risk'])} critical spare(s) are running below a "
            f"safe level — reorder these first to avoid a shutdown."),
    })

    need = reorder_rows(rows)
    if need:
        top = ", ".join(f"{r['name'] or r['sku']} ({int(r['reco_qty'])})"
                        for r in need[:5])
        spend = sum(r['reco_qty'] * r['unit_cost'] for r in need)
        cards.append({
            "keywords": "reorder restock buy replenish order what need procure "
                        "purchase running low safety stock",
            "answer": (
                f"{len(need)} spare(s) need replenishment. Highest shutdown-risk "
                f"first: **{top}**. Estimated procurement value: {cr(spend)}."),
        })

    # per-spare consumption cards (so "forecast for pump seal" works)
    for r in rows:
        name = r["name"] or r["sku"]
        rate = float(r["reorder"]["daily_rate"] or 0)
        a = r["forecast"].get("ai_analysis")
        trend = (f", {a['trend_dir']} {a['trend_pct_month']:+.0f}%/mo"
                 if a else "")
        cards.append({
            "scope": set(_tok(f"{name} {r['sku']} {r.get('equipment','')}")),
            "keywords": f"{name} {r['sku']} {r.get('equipment','')} consumption "
                        f"forecast usage demand rate per day cover stock",
            "answer": (
                f"**{name}** ({r.get('criticality','essential')}, "
                f"{r.get('equipment','') or 'unassigned equipment'}): AI forecasts "
                f"~{rate:.2f} unit/day{trend}. On hand {int(r['on_hand'])}, "
                f"AI-optimal max {int(r['optimal_stock'])}, capital "
                f"{cr(r['capital'])}."),
        })
    return cards


def answer(question, rows=None, db_path=None):
    return _answer(question, cards=build_facts(rows=rows, db_path=db_path))
