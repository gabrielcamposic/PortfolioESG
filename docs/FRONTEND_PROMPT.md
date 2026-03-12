# PortfolioESG — Frontend Build Prompt

> **Use this prompt to start a new AI chat for building the frontend from scratch.**

---

## Context

I have a Python-based ESG portfolio analysis pipeline called **PortfolioESG**. It runs locally on macOS and publishes results via **GitHub Pages** (static site served from the repo root).

The backend was recently refactored across 4 phases (all complete). The pipeline produces all data files in `data/`, and `D_Publish.py` creates **symlinks** in `html/data/` pointing back to `data/`. The frontend's job is purely **render-only**: fetch pre-computed data from `html/data/` and display it. **Zero calculations in the browser.**

The old frontend was removed and backed up. We're building from scratch.

## Project Structure

```
PortfolioESG/
├── index.html                  ← Entry point (GitHub Pages serves from root)
├── html/
│   ├── css/                    ← To be created
│   ├── js/                     ← To be created
│   └── data/                   ← ~29 symlinks → data/ (DO NOT TOUCH)
├── engines/                    ← Backend Python scripts (DO NOT MODIFY)
├── data/                       ← Canonical data (DO NOT MODIFY)
├── parameters/                 ← Config files (DO NOT MODIFY)
└── docs/
    └── REFACTORING_PLAN.md     ← Full backend documentation
```

## Architectural Principles

1. **Render-only** — The frontend receives pre-computed data and displays it. No calculations, no transformations, no aggregations in JS. If a number isn't in the data, it should be added to the backend (D_Publish.py).
2. **Static site** — Pure HTML/CSS/JS. No build step, no npm, no bundler. Served via GitHub Pages from repo root.
3. **Data via fetch** — All data is loaded from `html/data/*.json` and `html/data/*.csv` via `fetch()`. The symlinks are transparent to the browser.
4. **Single-page with sections** — One `index.html` with collapsible/tabbed sections, not multi-page.
5. **Mobile-first responsive** — Must work well on phone screens.
6. **Portuguese (pt-BR)** — All UI text in Brazilian Portuguese.

## Data Contract — Files Available in `html/data/`

### Primary JSONs (fetch and render directly)

| File | Description | Key Fields |
|---|---|---|
| `dashboard_latest.json` | **Main dashboard data.** Consolidated model + real portfolio views. | `generated_at`, `model.meta.run_id`, `model.returns.*`, `model.risk.*`, `model.decision.verdict`, `model.composition.sector_exposure[]`, `real.meta.{history_start,history_end,observations}`, `real.portfolio.{sharpe,sortino,max_drawdown,calmar,annual_return,volatility}`, `real.relative.{beta,tracking_error,information_ratio}`, `real.structure.{hhi,n_assets}`, `real.performance.{YTD,3M,6M,12M,24M}.{portfolio,benchmark}` |
| `pipeline_latest.json` | Model portfolio projected onto real capital. Per-stock allocation. | `stocks[]`, `weights[]`, `rows[].{ticker,weight,current,projectedQty,projectedInvested,target,projectedBRL}`, `totals.{totalPct,totalCurrentSum,totalProjectedInvested,totalProjectedBRL}` |
| `ledger_positions.json` | Current real holdings with totals. | `total_current_market`, `total_invested_cash`, `total_unrealized_pnl`, `positions[].{ticker,symbol,net_qty,net_invested,current_price,target_price}` |
| `optimized_recommendation.json` | Rebalancing recommendation. | `decision` (HOLD/REBALANCE), `reason`, `excess_return_pct`, `comparison.{holdings,ideal,optimal}`, `transactions[].{symbol,action,shares,estimated_cost}` |
| `scored_targets.json` | Ticker → target price map. | `targets.{TICKER: price}`, `symbols[]` |
| `portfolio_diagnostics.json` | Latest run diagnostics snapshot. | `run_id`, `sharpe`, `sortino`, `max_drawdown`, `calmar`, `beta`, `annual_return`, `annual_volatility`, `hhi`, `n_assets` |
| `performance_attribution.json` | Brinson attribution snapshot. | `run_id`, `allocation_effect`, `selection_effect`, `interaction_effect`, `total_active_return` |
| `latest_run_summary.json` | Best portfolio details from GA optimizer. | `last_updated_run_id`, `scoring_run_id`, `best_portfolio_details.{stocks[],weights[],sharpe_forward,expected_return_annual_pct,expected_volatility_annual_pct,sector_exposure_list[]}` |

### Primary CSVs (fetch, parse with JS, render as tables/charts)

| File | Description | Columns |
|---|---|---|
| `portfolio_timeseries.csv` | Daily time series: portfolio vs benchmark values. | `run_id,date,portfolio_real_value,benchmark1_name,benchmark1_real_value,portfolio_daily_return,benchmark1_daily_return,portfolio_accum_return,benchmark1_accum_return,portfolio_composition` |
| `portfolio_history.csv` | Real holdings history (one row per position per day). | `date,symbol,qty,price,value,market_value,cost_basis,pnl,pnl_pct` |
| `scored_stocks.csv` | ESG scoring history (filter by latest `run_id`). | `run_id,Stock,Sector,CompositeScore,SharpeRatio,Upside,...` |
| `portfolio_results_db.csv` | Historical portfolio optimization runs. | `run_id,scoring_run_id,timestamp,stocks,weights,sharpe_forward,roi_percent,...` |

### Progress JSONs (for live pipeline status display)

| File | Description |
|---|---|
| `pipeline_progress.json` | Overall pipeline status |
| `download_progress.json` | A1 download progress |
| `scoring_progress.json` | A2 scoring progress |
| `portfolio_progress.json` | A3 optimization progress |

### Other CSVs (secondary, for drill-down views)

| File | Description |
|---|---|
| `sector_pe.csv` | P/E by sector over time |
| `correlation_matrix.csv` | Stock correlation matrix |
| `ledger.csv` | Full transaction ledger |
| `mis_model_history.csv` | Historical model portfolio runs (alias for portfolio_results_db.csv) |
| `mis_real_history.csv` | Historical diagnostics per run |
| `mis_real_attribution.csv` | Historical asset attribution per run |
| `tickers.txt` | Master ticker list with sectors |

## Dashboard Sections (suggested layout)

### 1. Header / Status Bar
- Last run timestamp and run_id (from `dashboard_latest.json → model.meta`)
- Pipeline status indicator (from `pipeline_progress.json`)
- Overall decision badge: **HOLD** or **REBALANCE** (from `dashboard_latest.json → model.decision.verdict`)

### 2. Portfolio Overview (2-column: Model vs Real)
- **Model side** (left): Expected return, volatility, Sharpe forward, sector pie chart
- **Real side** (right): Realized return, volatility, Sharpe, Sortino, max drawdown
- Source: `dashboard_latest.json`

### 3. Performance Chart
- Line chart: portfolio value vs benchmark over time
- Source: `portfolio_timeseries.csv` (columns: `date`, `portfolio_accum_return`, `benchmark1_accum_return`)
- Performance windows table (YTD, 3M, 6M, 12M, 24M) from `dashboard_latest.json → real.performance`

### 4. Current Holdings
- Table: symbol, qty, current price, invested, market value, P&L, P&L%
- Source: `ledger_positions.json → positions[]`
- Totals row from `total_current_market`, `total_invested_cash`, `total_unrealized_pnl`

### 5. Model Portfolio & Rebalancing
- Model allocation table: ticker, weight%, projected qty, projected value
- Source: `pipeline_latest.json → rows[]`
- Rebalancing recommendation: decision, reason, excess return
- Transactions to execute (if REBALANCE)
- Source: `optimized_recommendation.json`

### 6. Risk & Diagnostics
- Key metrics cards: Beta, Tracking Error, Information Ratio, HHI, Calmar
- Source: `dashboard_latest.json → real.relative`, `real.structure`, `portfolio_diagnostics.json`

### 7. ESG Scoring (collapsible)
- Top scored stocks table with composite score, sector, Sharpe
- Source: `scored_stocks.csv` (filter latest run_id)

### 8. History (collapsible)
- Historical portfolio runs table
- Source: `portfolio_results_db.csv`

## Technical Preferences

- **Charts**: Use [Chart.js](https://www.chartjs.org/) via CDN — lightweight, no build step
- **CSS**: Custom CSS, no framework. Clean, modern, dark-theme friendly
- **CSV parsing**: Simple JS parser or [PapaParse](https://www.papaparse.com/) via CDN
- **No frameworks**: No React, Vue, Angular. Vanilla JS only.
- **File organization**:
  - `index.html` — Structure and sections
  - `html/css/styles.css` — All styles
  - `html/js/app.js` — Main entry point, section orchestration
  - `html/js/data.js` — Data fetching and caching layer
  - `html/js/charts.js` — Chart rendering functions
  - `html/js/tables.js` — Table rendering functions

## What NOT to Do

- Do NOT modify anything in `engines/`, `data/`, `parameters/`, `shared_tools/`
- Do NOT create a build step or use npm/node
- Do NOT perform calculations in JS — if a derived metric is needed, add it to `D_Publish.py` instead
- Do NOT duplicate data files — `html/data/` symlinks are the only data source
- Do NOT hardcode data values — everything must be fetched dynamically

## How to Test Locally

```bash
cd /Users/gabrielcampos/PortfolioESG
python3 -m http.server 8000
# Open http://localhost:8000
```

## Reference

- Full backend documentation: `docs/REFACTORING_PLAN.md`
- Backend pipeline map, data formats, and all 4 refactoring phases are documented there
- The `backups/refactor_20260303/frontend_old/` directory contains the old frontend for visual reference (not for code reuse)

