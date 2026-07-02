# AISync — AI-Based Spare Inventory Optimization (HPL)

An enterprise console that turns a petrochemical plant's spare-parts master
(SAP-style) into **working-capital decisions**. Built for the Haldia
Petrochemicals use case: hundreds of crores blocked in capital spares, a large
share of it obsolete, and no criticality-aware way to decide what to trim.

Every number shown is **computed from the plant's own consumption and stock
data — never guessed** — so finance can sign off on it.

## Run

```bash
cd aisync-spares
pip install -r requirements.txt          # streamlit, pandas, numpy, openpyxl
streamlit run app.py
```

In the app: create a plant workspace → sidebar **Load HPL demo data** → explore
all eight pages. Under **Spare Master & Data → Upload SAP export** you can
generate a deliberately messy sample export and watch the auto-mapping detect
every column despite odd headers, ₹ signs and mixed date formats.

CLI smoke test (no UI):

```bash
python -m core.seed        # seeds the HPL demo catalog + writes demo_messy.xlsx
```

> Note: needs a working Python with pandas. On this machine the Homebrew 3.14
> is broken (pyexpat); use `/opt/anaconda3/bin/python3`.

## What it does (the eight pages)

| Page | What it answers |
|---|---|
| **Executive Dashboard** | How much working capital is blocked (₹Cr), how much is realistically releasable, capital by criticality, high shutdown-risk lines |
| **Obsolete Detection** | Which spare lines have had no issue in >5 years — dead capital for redeployment / resale / write-down |
| **Consumption Forecast** | Per-spare neural forecast: trend %/month, weekly maintenance rhythm, momentum |
| **Criticality Optimizer** | What to reorder, worst shutdown-risk first, under a procurement budget; insurance-spare minimums |
| **Predictive Maintenance** | Spares whose consumption is accelerating — an early equipment-failure signal |
| **Spare Master & Data** | Record issues/receipts, set stock counts, upload SAP exports with auto column-mapping |
| **Ask AISync** | Grounded Q&A over the plant's real numbers (TF-IDF fact cards, no LLM, cannot hallucinate) |
| **Implementation Roadmap** | The 5-phase SAP-integrated rollout |

## The optimization model

- **Criticality-based service levels** (`core/engine.py`) — critical 99%,
  essential 95%, non-critical 90%. Critical spares get deeper safety stock;
  non-critical consumables are trimmed hardest.
- **Insurance spares** (`core/spares.py`) — ultra-expensive critical units
  (≥ ₹1 Cr, e.g. a cracked-gas-compressor rotor) are held to a strategic
  minimum of 2, never demand-forecast, never flagged excess.
- **Obsolescence** — no issue in >5 years ⇒ dead capital (critical strategic
  spares exempt). Whole-line value counted as releasable.
- **Excess** — on-hand above the AI-optimal max level on non-critical /
  essential lines only.
- **Shutdown-risk score** — criticality weight × stockout-risk weight; drives
  the procurement priority order.
- **Predictive maintenance** — consumption momentum or trend above +12%
  flags the served equipment for early intervention.

## The AI forecaster (`core/ai_forecast.py`)

A from-scratch, numpy-only MLP (1 hidden layer, Adam) trained on the **whole
plant at once** — each spare normalized by its own level so slow movers borrow
the weekly maintenance rhythm learned from fast movers (cross-SKU pooling).
Features: day-of-week one-hot, lag-1/lag-7, week/month averages, trend
position. Intermittent/lumpy capital-spare series (≥60% zero days) route
automatically to **Croston's method** (`core/forecast.py`), which is
purpose-built for spare-parts demand. No paid APIs; fully inspectable.

## Data ingestion

Any SAP/Excel/CSV export → **auto column-mapping** (`core/mapping.py`,
`core/adapters/tabular.py`): header synonyms + value-type inference, shown
with confidence and user-correctable. Handles scrambled column order,
"Material Code" / "Posting Dt" style headers, ₹-prefixed prices, mixed date
formats.

Normalized schema (single source of truth):
`products(sku, name, unit_cost, criticality, equipment, last_issue_date)` ·
`sales(sku, date, qty)` (spare issues) · `inventory(sku, on_hand)` ·
`suppliers(sku, lead_time_days, reliability)`

## Multi-plant, auth, persistence

- Each workspace's data is scoped by row-level multi-tenancy — one deployment
  can serve many plants/sites.
- Passwords hashed (pbkdf2-sha256, 200k rounds, per-user salt); 30-day session
  tokens.
- Storage: local SQLite by default; set `TURSO_DATABASE_URL` +
  `TURSO_AUTH_TOKEN` for a free hosted DB that survives restarts (writes are
  batched into single HTTP pipelines for low latency). See `DEPLOY.md`.

## Layout

```
core/
  schema.py  db.py  mapping.py  forecast.py  ai_forecast.py  reorder.py
  cashflow.py  engine.py  spares.py  assistant.py  auth.py  seed.py
  adapters/  base.py tabular.py manual.py ...
app.py            # the 8-page AISync console
```
