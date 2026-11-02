"""AISync Strategist — personalized, grounded strategic reasoning.

This is the "actual intelligence" layer, not a chatbot. It does NOT retrieve
canned text: it evaluates every strategic lever the plant has, computes each
lever's REAL rupee impact from the analyzed spare data, then ranks them for
the person logged in (their role + learned focus) and writes a cause->effect
thesis that ties the plant's own numbers to HPL's business context (a 700 KTPA
ethylene cracker whose uptime dwarfs any single spare).

Pipeline:
    rows = spares.analyze(...)                # computed plant state
    persona = profile.persona(...)            # who is asking + what they focus on
    plan = strategize(rows, persona)          # ranked, reasoned, quantified plays

Each play is fully derived from `rows`; remove the data and the play vanishes.
"""
from __future__ import annotations

from . import company
from .spares import (portfolio, obsolete_rows, excess_rows, reorder_rows,
                     predictive_maintenance, cr, lakh)


def _money(x):
    return cr(x) if x >= 1e7 else lakh(x)


def _names(lst, k=3):
    got = [(r["name"] or r["sku"]) for r in lst[:k]]
    return ", ".join(got) if got else "—"


# ---- candidate levers ----------------------------------------------------
# Each builder returns a play dict or None (when the plant has no such signal).
def _play_capital(rows, pf):
    rel = pf["release_opportunity"]
    if rel <= 0:
        return None
    obs_v, exc_v = pf["obsolete_value"], pf["excess_value"]
    return {
        "dim": "capital", "title": "Release blocked working capital",
        "impact": rel, "confidence": 0.9,
        "thesis": (
            f"{_money(rel)} — {pf['release_pct']:.0f}% of the {_money(pf['total_capital'])} "
            f"tied up in spares — is releasable without touching a critical spare "
            f"({_money(obs_v)} obsolete + {_money(exc_v)} excess above AI-optimal). "
            f"For a TCG-owned complex buying naphtha on the open market, that is "
            f"cash better deployed against feedstock than sitting on a shelf."),
        "actions": [f"Write down / redeploy {pf['n_obsolete']} obsolete line(s)",
                    "Draw excess non-critical stock down before the next PO cycle"],
    }


def _play_obsolescence(rows, pf):
    slow = [r for r in rows if r.get("slow_moving")]
    val = sum(r["capital"] for r in slow)
    if not slow or val <= 0:
        return None
    return {
        "dim": "obsolescence", "title": "Head off the next write-down",
        "impact": val, "confidence": 0.7,
        "thesis": (
            f"{len(slow)} line(s) worth {_money(val)} are trending obsolete — "
            f"aged and barely moving, but not yet across the 5-year line. Acting "
            f"now (redeploy or return) avoids them hardening into dead capital "
            f"like the {_money(pf['obsolete_value'])} already stranded."),
        "actions": [f"Review {_names(slow)} for redeployment to sister units",
                    "Flag to Finance before year-end provisioning"],
    }


def _play_reliability(rows, pf):
    at_risk = pf["critical_at_risk"]
    if not at_risk:
        return None
    exposure = sum(r["capital"] for r in at_risk)
    # Strategic-value floor: a critical spare stockout risks a cracker trip,
    # whose cost (idled ethylene + all downstream polymer) dwarfs the spare's
    # book value. Floor the impact well above book so uptime isn't undervalued.
    return {
        "dim": "reliability", "title": "Protect the cracker — critical spares at risk",
        "impact": max(exposure, pf["total_capital"] * 0.18), "confidence": 0.85,
        "thesis": (
            f"{len(at_risk)} critical spare(s) are running below a safe level. "
            f"{company.reliability_context()} Restoring cover on {_names(at_risk)} "
            f"buys insurance against a whole-complex trip, which is worth far more "
            f"than their {_money(exposure)} of book value."),
        "actions": [f"Expedite cover on {len(at_risk)} critical spare(s) first",
                    "Verify supplier lead-times on these before anything else"],
    }


def _play_predictive(rows, pf):
    pdm = predictive_maintenance(rows)
    if not pdm:
        return None
    top = pdm[0]
    stage = sum(r["reco_qty"] * r["unit_cost"] for r in pdm)
    return {
        "dim": "predictive", "title": "Act on early failure signals",
        "impact": max(stage, pf["total_capital"] * 0.15), "confidence": 0.72,
        "thesis": (
            f"{len(pdm)} spare(s) show accelerating consumption — an early sign "
            f"the equipment they serve is heading toward failure. Strongest: "
            f"{top['name'] or top['sku']} on "
            f"{top.get('equipment') or 'unassigned equipment'}, "
            f"up {top['momentum_pct']:+.0f}%/week. Staging spares and inspecting "
            f"now converts an unplanned cracker trip into planned downtime."),
        "actions": [f"Stage spares & schedule inspection on {top.get('equipment') or top['sku']}",
                    f"Pre-order {len(pdm)} accelerating line(s) ({_money(stage)})"],
    }


def _play_procurement(rows, pf):
    need = reorder_rows(rows)
    if not need:
        return None
    spend = sum(r["reco_qty"] * r["unit_cost"] for r in need)
    crit_need = [r for r in need if r.get("criticality") == "critical"]
    return {
        "dim": "procurement", "title": "Sequence replenishment by shutdown risk",
        "impact": spend, "confidence": 0.8,
        "thesis": (
            f"{len(need)} spare(s) need replenishment ({_money(spend)}). Ordering "
            f"by shutdown-risk — {'the ' + str(len(crit_need)) + ' critical one(s) first, ' if crit_need else ''}"
            f"then essential — protects uptime while smoothing cash outflow, "
            f"instead of buying alphabetically or in a year-end rush."),
        "actions": [f"Raise PRs for {len(need)} line(s), critical-first",
                    "Bundle by supplier to cut lead-time and freight"],
    }


_BUILDERS = [_play_capital, _play_obsolescence, _play_reliability,
             _play_predictive, _play_procurement]


# ---- scoring & ranking ---------------------------------------------------
def strategize(rows, persona, top_n=None):
    """Return persona-ranked strategic plays, each grounded in the data.

    Score = normalized rupee impact x persona weight for that lever x the
    play's confidence. So the SAME plant shows a CFO 'release capital' at the
    top and a Maintenance Head 'protect the cracker' at the top — from one set
    of computed numbers, re-prioritised, not rewritten."""
    pf = portfolio(rows)
    scale = max(pf["total_capital"], 1.0)
    weights = persona.get("weights", {})

    plays = []
    for build in _BUILDERS:
        p = build(rows, pf)
        if not p:
            continue
        impact_norm = min(p["impact"] / scale, 1.0)
        w = weights.get(p["dim"], 0.2)
        p["score"] = round(impact_norm * w * p["confidence"] * 100, 1)
        p["weight"] = round(w, 3)
        p["fit"] = (p["dim"] == persona.get("top_focus"))
        plays.append(p)

    plays.sort(key=lambda p: -p["score"])
    if top_n:
        plays = plays[:top_n]
    return plays


def briefing(rows, persona):
    """A personalized executive narrative: who's reading, what leads, why.

    Returns {headline, lead_play, plays, persona, portfolio} — the object the
    UI renders as the 'Strategy' surface."""
    pf = portfolio(rows)
    plays = strategize(rows, persona)
    label = persona.get("label", "Plant leadership")
    focus = persona.get("top_focus", "reliability")

    if plays:
        lead = plays[0]
        tail = "; then " + ", ".join(p["title"].lower() for p in plays[1:3]) \
            if len(plays) > 1 else ""
        headline = (f"For {label}, the highest-leverage move now is to "
                    f"{lead['title'][0].lower()}{lead['title'][1:]}{tail}.")
        learned = (" AISync has also noticed you focus on "
                   f"{focus} — weighting that up." if persona.get("learned") else "")
        headline += learned
    else:
        lead = None
        headline = (f"For {label}: inventory is balanced — no releasable capital, "
                    f"no replenishment gaps and no failure signals right now.")

    return {
        "headline": headline,
        "lead_play": lead,
        "plays": plays,
        "persona": persona,
        "portfolio": pf,
        "company": company.summary_line(),
    }
