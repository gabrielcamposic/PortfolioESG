# PortfolioESG — Continuation Prompt

Paste this at the start of a new chat to resume implementation.

---

## Context

I'm refactoring **PortfolioESG**, a Python pipeline for ESG stock portfolio analysis that runs on macOS and publishes results via GitHub Pages. The project lives at `/Users/gabrielcampos/PortfolioESG`.

## What was done

1. **Backend refactoring phases 1–4** are complete (documented in `docs/REFACTORING_PLAN.md`).
2. **Frontend rebuild** started: `html/sections/1_portfolio.html` exists with 8 metric cards + a line chart, but the metrics are inconsistent (different data sources, methodologies, and asset universes). The old frontend sections (`01_header.html` through `08_history.html`) will be replaced.
3. **Metrics audit** was completed and documented in `docs/METRICS_REFERENCE.md` — it lists every metric, its formula, source, and the 6 inconsistencies found.
4. **Fix plan** was written and approved: `docs/D_PUBLISH_METRICS_PLAN.md` — this is the master document for the next implementation.

## What needs to be done now

Read `docs/D_PUBLISH_METRICS_PLAN.md` first. It contains:
- 3 pre-requisites (T1, T2, T3) — fix ticker normalization in B4/B2 and exclude weekends
- 4 changes (Mudanças 1–4) — new D_Publish step for real daily returns, compute real metrics, restructure dashboard JSON, update frontend
- Implementation order (Steps 1–9)
- Success criteria

**Start from Step 1** in the "Ordem de implementação" table.

## Key files to read before starting

| File | Why |
|---|---|
| `docs/D_PUBLISH_METRICS_PLAN.md` | The full implementation plan — READ THIS FIRST |
| `docs/METRICS_REFERENCE.md` | Detailed diagnosis of each metric's formula and source |
| `docs/REFACTORING_PLAN.md` | Architecture principles and pipeline map |
| `engines/D_Publish.py` | The publisher script to modify (Mudanças 1–3) |
| `engines/B4_Portfolio_History.py` | Portfolio history generator to fix (T1, T3) |
| `engines/B2_Consolidate_Ledger.py` | Ledger consolidator to fix (T2) |
| `engines/B12_Transactions_Ledger.py` | May share normalization logic with B2 |
| `parameters/tickers.txt` | Ticker mappings (BrokerName column) — may need new entries |
| `data/ledger.csv` | All 42 transactions — reference for ticker variants |
| `html/sections/1_portfolio.html` | Current frontend to update (Mudança 4) |

## Project structure

```
engines/run_all.sh          — Master orchestrator (A→B→C→D)
engines/A_Portfolio.sh      — Sub-orchestrator A (A1→A2→A3→A4)
engines/B_Ledger.sh         — Sub-orchestrator B (B1→B2→B4)
engines/D_Publish.py        — Publisher (generates html/data/ for frontend)
data/                       — Canonical data source
data/results/               — Engine outputs
html/data/                  — Symlinks to data/ (frontend window)
html/sections/              — Standalone frontend sections
shared_tools/               — Shared utilities (path_utils, shared_utils)
parameters/                 — Config files per engine
docs/                       — All documentation
```

## Rules

1. **Render-only frontend** — No calculations in JS beyond formatting and composing `∏(1+r)` for the chart. If a derived metric is needed, add it to D_Publish.py.
2. **No frameworks** — Vanilla JS, Chart.js, PapaParse only. No npm, no bundler.
3. **data/ is the single source of truth** — html/data/ contains only symlinks.
4. **Validate with run_all.sh** after backend changes. Full run takes ~30 minutes.
5. **Portuguese (pt-BR)** for UI labels, English for code/docs.
6. **The CSV `portfolio_real_daily.csv` must NOT contain accumulated indices (base 100).** Only daily returns. The frontend computes the accumulated index dynamically for whatever start date the user selects.

## Testing

A local HTTP server runs on port 8000 serving from `html/`:
```
http://localhost:8000/sections/1_portfolio.html
```
Start one if not running: `cd html && python3 -m http.server 8000`

