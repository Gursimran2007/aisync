"""Grounded company profile for Haldia Petrochemicals Ltd (HPL).

Every figure here is a PUBLIC, verifiable fact about HPL (capacity, product
slate, ownership, site) — sourced from HPL's own site, Wikipedia and 2026
trade-press coverage. The strategist and the assistant read this so their
advice is framed in the plant's real business context (a 700 KTPA ethylene
cracker whose uptime is worth far more than any spare on the shelf), not as
generic inventory tips.

Nothing here is invented: derived numbers (e.g. per-day ethylene throughput)
are simple arithmetic on the stated annual capacity and are labelled as such.
"""
from __future__ import annotations

# ---- verifiable public facts ---------------------------------------------
PROFILE = {
    "legal_name": "Haldia Petrochemicals Limited",
    "short": "HPL",
    "site": "Haldia, West Bengal (≈125 km from Kolkata)",
    "hq": "Kolkata, West Bengal, India",
    "owner": "The Chatterjee Group (TCG)",
    "since": 1984,                     # commercial production
    "feedstock": "Naphtha (Middle East + local refiners)",
    "ethylene_ktpa": 700,             # ethylene-equivalent cracker capacity
    "downstream_ktpa": 1700,          # total downstream product output
    "products_ktpa": {                 # stated nameplate capacities
        "LLDPE": 386, "HDPE": 334, "Polypropylene": 341, "Benzene": 132,
    },
    "other_products": ["Butadiene", "LPG", "Pyrolysis gasoline", "CBFS"],
    "export_countries": 50,           # exports to 50+ countries
    "industries": ["packaging", "agriculture", "infrastructure", "automotive"],
    "trading_arm": "TCG Singapore petrochemicals trading",
}


def throughput_per_day() -> float:
    """Ethylene tonnes/day the cracker turns out at nameplate (700 KTPA/365).

    This is the number that makes reliability matter: every day the cracker is
    tripped, roughly this much saleable ethylene — and all the polymer made
    from it — simply doesn't get produced."""
    return PROFILE["ethylene_ktpa"] * 1000 / 365.0


def summary_line() -> str:
    p = PROFILE
    return (f"{p['legal_name']} ({p['short']}) — a naphtha-based cracker at "
            f"{p['site']}, running since {p['since']}, owned by {p['owner']}. "
            f"A {p['ethylene_ktpa']} KTPA ethylene cracker feeds "
            f">{p['downstream_ktpa']} KTPA of polymers & chemicals "
            f"(LLDPE, HDPE, PP, benzene, butadiene), exported to "
            f"{p['export_countries']}+ countries.")


def reliability_context() -> str:
    """One line the strategist uses to justify protecting critical spares."""
    return (f"HPL's cracker pushes ~{throughput_per_day():,.0f} T/day of "
            f"ethylene; an unplanned trip idles that throughput and every "
            f"downstream polymer line, so a stocked-out critical spare is a "
            f"whole-complex risk, not a line-item.")


def facts_cards():
    """Company fact cards for the grounded assistant (same shape as spares)."""
    p = PROFILE
    prod = ", ".join(f"{k} {v} KTPA" for k, v in p["products_ktpa"].items())
    return [
        {
            "keywords": "company about hpl haldia petrochemicals who profile "
                        "plant site owner tcg history background overview what is",
            "answer": (
                f"**{p['legal_name']} ({p['short']})** is a naphtha-based "
                f"petrochemical complex at {p['site']}, in commercial production "
                f"since {p['since']} and owned by {p['owner']} (HQ {p['hq']}). "
                f"Its cracker has a {p['ethylene_ktpa']} KTPA ethylene capacity "
                f"feeding >{p['downstream_ktpa']} KTPA of downstream product."),
        },
        {
            "keywords": "products make produce polymer output lldpe hdpe "
                        "polypropylene pp benzene butadiene capacity ktpa slate "
                        "what does company manufacture sell",
            "answer": (
                f"HPL's product slate (nameplate): {prod}, plus "
                f"{', '.join(p['other_products'])}. Total downstream output is "
                f">{p['downstream_ktpa']} KTPA, exported to "
                f"{p['export_countries']}+ countries across "
                f"{', '.join(p['industries'])}."),
        },
        {
            "keywords": "cracker capacity ethylene throughput tonnes per day "
                        "uptime downtime shutdown trip cost reliability why "
                        "critical spare matters production",
            "answer": (
                f"The cracker runs {p['ethylene_ktpa']} KTPA of ethylene — about "
                f"**{throughput_per_day():,.0f} tonnes/day**. {reliability_context()}"),
        },
        {
            "keywords": "feedstock naphtha supply raw material sourcing middle "
                        "east refiners procurement input",
            "answer": (
                f"HPL's cracker runs on **{p['feedstock']}**. Feedstock and "
                f"critical-spare availability are the two levers that keep the "
                f"complex running — AISync manages the spare side."),
        },
    ]
