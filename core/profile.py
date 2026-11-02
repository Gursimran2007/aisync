"""Per-login personalization: role persona + behavioural learning.

Two layers, blended into one set of "focus weights" the strategist and
assistant use to re-rank and re-frame advice for whoever is logged in:

  1. ROLE  — an explicit persona the user picks (Plant Manager, Maintenance
     Head, Finance/CFO, Procurement). Sets a starting emphasis across the five
     strategic dimensions.
  2. LEARNING — every page the user opens and every question they ask logs a
     lightweight signal. Over time these observed interests nudge the weights
     toward what this specific person actually cares about.

Both persist in the per-user `settings` table (settings.shop_id == the user's
id), so nothing new has to be migrated and it works on Turso unchanged.
"""
from __future__ import annotations
import json

from . import db

# The five levers the strategist reasons over. Every weight map is over these.
DIMENSIONS = ["capital", "reliability", "predictive", "procurement", "obsolescence"]

# Explicit role personas -> starting emphasis. Numbers are relative weights;
# they are normalised before use, so only the ratios matter.
ROLES = {
    "plant_manager": {
        "label": "Plant Manager",
        "blurb": "Balances uptime and capital — reliability first, cash a close second.",
        "weights": {"capital": 1.0, "reliability": 1.3, "predictive": 1.1,
                    "procurement": 0.9, "obsolescence": 0.8},
    },
    "maintenance_head": {
        "label": "Maintenance Head",
        "blurb": "Lives and dies by equipment uptime — failure signals lead everything.",
        "weights": {"capital": 0.5, "reliability": 1.5, "predictive": 1.6,
                    "procurement": 1.0, "obsolescence": 0.5},
    },
    "finance": {
        "label": "Finance / CFO",
        "blurb": "Chases blocked working capital and write-down risk first.",
        "weights": {"capital": 1.6, "reliability": 0.8, "predictive": 0.6,
                    "procurement": 0.9, "obsolescence": 1.4},
    },
    "procurement": {
        "label": "Procurement Lead",
        "blurb": "Optimises what to buy, when, and from whom — timing and spend.",
        "weights": {"capital": 1.0, "reliability": 1.0, "predictive": 0.9,
                    "procurement": 1.6, "obsolescence": 1.0},
    },
}
DEFAULT_ROLE = "plant_manager"

# Maps an in-app topic (page key or question theme) to the dimension it feeds,
# so browsing/asking teaches the persona what this user focuses on.
TOPIC_DIMENSION = {
    "dash": "reliability", "obs": "obsolescence", "fcast": "predictive",
    "opt": "capital", "pdm": "predictive", "master": "procurement",
    "ask": "reliability", "road": "capital",
    # question themes (from the assistant)
    "capital": "capital", "obsolete": "obsolescence", "excess": "capital",
    "reorder": "procurement", "forecast": "predictive",
    "maintenance": "predictive", "risk": "reliability", "shutdown": "reliability",
}

_ROLE_KEY = "ai_role"
_SIGNAL_KEY = "ai_signals"
_LEARN_STRENGTH = 0.6      # how far learned focus can pull the role baseline


# ---- role ----------------------------------------------------------------
def get_role(db_path=None) -> str:
    r = db.get_setting(_ROLE_KEY, DEFAULT_ROLE, db_path=db_path)
    return r if r in ROLES else DEFAULT_ROLE


def set_role(role, db_path=None):
    if role in ROLES:
        db.set_setting(_ROLE_KEY, role, db_path=db_path)


def role_meta(role=None, db_path=None):
    return ROLES[get_role(db_path) if role is None else role]


# ---- learning signals ----------------------------------------------------
def _load_signals(db_path=None) -> dict:
    raw = db.get_setting(_SIGNAL_KEY, "{}", db_path=db_path)
    try:
        d = json.loads(raw)
        return {k: float(v) for k, v in d.items()} if isinstance(d, dict) else {}
    except (ValueError, TypeError):
        return {}


def log_signal(topic, db_path=None, weight=1.0):
    """Record that the user engaged with `topic` (a page key or question theme).

    Signals decay slightly each time so the persona tracks *recent* focus
    rather than accumulating forever — a user who shifts from cost-cutting to
    reliability is followed, not anchored to their history."""
    dim = TOPIC_DIMENSION.get(topic)
    if dim is None:
        return
    sig = _load_signals(db_path=db_path)
    for k in list(sig):
        sig[k] *= 0.97                      # gentle decay of prior focus
    sig[dim] = sig.get(dim, 0.0) + weight
    db.set_setting(_SIGNAL_KEY, json.dumps(sig), db_path=db_path)


def learned_weights(db_path=None) -> dict:
    """Signals -> normalised focus over DIMENSIONS (sums to 1, or empty)."""
    sig = _load_signals(db_path=db_path)
    tot = sum(sig.get(d, 0.0) for d in DIMENSIONS)
    if tot <= 0:
        return {}
    return {d: sig.get(d, 0.0) / tot for d in DIMENSIONS}


# ---- the blended persona the rest of the app consumes --------------------
def persona(db_path=None) -> dict:
    """Effective persona = role baseline nudged by learned behaviour.

    Returns {role, label, blurb, weights (normalised), learned (bool),
    top_focus} — the single object the strategist and assistant read."""
    role = get_role(db_path=db_path)
    meta = ROLES[role]
    base = meta["weights"]
    btot = sum(base.values()) or 1.0
    base_n = {d: base.get(d, 0.0) / btot for d in DIMENSIONS}

    learned = learned_weights(db_path=db_path)
    if learned:
        # convex blend: role stays the anchor, behaviour pulls it a bit
        eff = {d: (1 - _LEARN_STRENGTH) * base_n[d] + _LEARN_STRENGTH * learned[d]
               for d in DIMENSIONS}
    else:
        eff = base_n
    etot = sum(eff.values()) or 1.0
    eff = {d: v / etot for d, v in eff.items()}
    top = max(eff, key=eff.get)
    return {
        "role": role,
        "label": meta["label"],
        "blurb": meta["blurb"],
        "weights": eff,
        "learned": bool(learned),
        "top_focus": top,
    }
