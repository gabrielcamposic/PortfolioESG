# PortfolioESG — Frontend Build Plan

**Início:** 2026-03-12  
**Última atualização:** 2026-03-12  
**Estratégia:** Standalone HTML sections → visual validation → assembly into single-page dashboard.

---

## Approach

Build the frontend **one section at a time** as standalone HTML files in `html/sections/`. Each file:
- Is self-contained (own `<style>`, `<script>`, CDN imports)
- Fetches real data from `html/data/` via `fetch()`
- Uses the **final stack**: Chart.js, PapaParse, vanilla JS (no frameworks)
- Opens directly in the browser for visual validation
- Contains the exact code that will be assembled into `index.html`

**Test locally:** `python3 -m http.server 8000` → `localhost:8000/html/sections/XX_name.html`

**When all sections are validated:** assemble into `index.html` + shared CSS/JS files.

---

## Tech Stack

| Tool | Purpose | Source |
|---|---|---|
| [Chart.js 4.x](https://www.chartjs.org/) | Charts (line, pie, bar) | CDN |
| [PapaParse 5.x](https://www.papaparse.com/) | CSV parsing | CDN |
| Vanilla JS | Logic, DOM, fetch | — |
| Custom CSS | Styling, dark theme, responsive | — |

---

## Sections

### Section 01 — Header / Status Bar ❌

**File:** `html/sections/01_header.html`  
**Data sources:** `dashboard_latest.json`, `pipeline_progress.json`  
**Displays:**
- Last run timestamp and `run_id`
- Pipeline status indicator (idle / running / error)
- Overall decision badge: **HOLD** or **REBALANCE** with color coding
- Total portfolio value (from `ledger_positions.json → total_current_market`)

**Key fields:**
- `dashboard_latest.json → model.meta.run_id`, `model.meta.timestamp`
- `dashboard_latest.json → model.decision.verdict`
- `pipeline_progress.json → status`
- `ledger_positions.json → total_current_market`

---

### Section 02 — Portfolio Overview (Model vs Real) ❌

**File:** `html/sections/02_overview.html`  
**Data sources:** `dashboard_latest.json`  
**Displays:**
- Two-column layout: Model (left) vs Real (right)
- **Model:** Expected return, volatility, Sharpe forward, sector pie chart
- **Real:** Realized return, volatility, Sharpe, Sortino, max drawdown, Calmar
- Sector exposure pie chart (from `model.composition.sector_exposure[]`)

**Key fields:**
- `model.returns.historical_annual`, `model.risk.volatility_annual`, `model.risk.sharpe`
- `real.portfolio.annual_return`, `real.portfolio.volatility`, `real.portfolio.sharpe`
- `real.portfolio.sortino`, `real.portfolio.max_drawdown`, `real.portfolio.calmar`
- `model.composition.sector_exposure[].{sector, pct}`

---

### Section 03 — Performance Chart ❌

**File:** `html/sections/03_performance_chart.html`  
**Data sources:** `portfolio_timeseries.csv`, `dashboard_latest.json`  
**Displays:**
- Line chart: portfolio accumulated return vs benchmark over time (Chart.js)
- Performance windows table: YTD, 3M, 6M, 12M, 24M (portfolio vs benchmark)

**Key fields:**
- CSV columns: `date`, `portfolio_accum_return`, `benchmark1_accum_return`
- `dashboard_latest.json → real.performance.{YTD,3M,6M,12M,24M}.{portfolio,benchmark}`

**Notes:**
- CSV has ~2700 rows; may need to downsample for chart rendering (every Nth point)
- PapaParse for CSV parsing

---

### Section 04 — Current Holdings ❌

**File:** `html/sections/04_holdings.html`  
**Data sources:** `ledger_positions.json`, `scored_targets.json`  
**Displays:**
- Table: symbol, qty, avg cost, current price, target price, invested, market value, P&L, P&L%
- Color-coded P&L (green positive, red negative)
- Totals row: total invested, total market value, total unrealized P&L

**Key fields:**
- `ledger_positions.json → positions[].{ticker, symbol, net_qty, net_invested, current_price, target_price}`
- `ledger_positions.json → total_current_market, total_invested_cash, total_unrealized_pnl`
- Derived (render-only): `market_value = net_qty × current_price`, `pnl = market_value - net_invested`, `pnl_pct = pnl / net_invested`

---

### Section 05 — Model Portfolio & Rebalancing ❌

**File:** `html/sections/05_rebalancing.html`  
**Data sources:** `pipeline_latest.json`, `optimized_recommendation.json`  
**Displays:**
- Model allocation table: ticker, weight%, projected qty, projected value
- Rebalancing decision badge + reason + excess return %
- Transactions table (if REBALANCE): symbol, action (BUY/SELL), shares, estimated cost

**Key fields:**
- `pipeline_latest.json → rows[].{ticker, weight, current, projectedQty, projectedInvested, target}`
- `pipeline_latest.json → totals.*`
- `optimized_recommendation.json → decision, reason, excess_return_pct`
- `optimized_recommendation.json → transactions[].{symbol, action, shares, estimated_cost}`

---

### Section 06 — Risk & Diagnostics ❌

**File:** `html/sections/06_risk.html`  
**Data sources:** `dashboard_latest.json`, `performance_attribution.json`  
**Displays:**
- Metric cards: Beta, Tracking Error, Information Ratio, HHI, Calmar, Correlation
- Brinson attribution breakdown: Allocation, Selection, Interaction, Total Active Return
- Portfolio structure: n_assets, top3, top5 concentration

**Key fields:**
- `dashboard_latest.json → real.relative.{beta, tracking_error, information_ratio, correlation}`
- `dashboard_latest.json → real.structure.{hhi, top3, top5, n_assets}`
- `performance_attribution.json → allocation_effect, selection_effect, interaction_effect, total_active_return`

---

### Section 07 — ESG Scoring (collapsible) ❌

**File:** `html/sections/07_scoring.html`  
**Data sources:** `scored_stocks.csv`  
**Displays:**
- Table: Stock, Sector, CompositeScore, SharpeRatio, Upside
- Filtered to latest `run_id` only
- Sorted by CompositeScore descending
- Top stocks highlighted

**Key fields:**
- CSV columns: `run_id, Stock, Sector, CompositeScore, SharpeRatio, Upside`
- Filter: `run_id == max(run_id)`

---

### Section 08 — History (collapsible) ❌

**File:** `html/sections/08_history.html`  
**Data sources:** `portfolio_results_db.csv`  
**Displays:**
- Table: run_id, timestamp, stocks (count), sharpe_forward, roi_percent
- Most recent runs first
- Expandable rows showing stock list per run (optional)

**Key fields:**
- CSV columns: `run_id, scoring_run_id, timestamp, stocks, weights, sharpe_forward, roi_percent`

---

### Final Assembly ❌

**File:** `index.html` + `html/css/styles.css` + `html/js/{app,data,charts,tables}.js`  
**Depends on:** All 8 sections validated ✅  
**Task:**
- Extract shared CSS into `styles.css`
- Extract shared JS (data fetching, formatters) into modules
- Combine all sections into single `index.html` with collapsible/tabbed layout
- Mobile-responsive final testing

---

## Progress Tracker

| # | Section | Status | Date | Notes |
|---|---|---|---|---|
| 01 | Header / Status Bar | ❌ | — | |
| 02 | Portfolio Overview | ❌ | — | |
| 03 | Performance Chart | ❌ | — | |
| 04 | Current Holdings | ❌ | — | |
| 05 | Model & Rebalancing | ❌ | — | |
| 06 | Risk & Diagnostics | ❌ | — | |
| 07 | ESG Scoring | ❌ | — | |
| 08 | History | ❌ | — | |
| 09 | Final Assembly | ❌ | — | Depends on 01–08 ✅ |

---

## Data Contract Reference

All data is served from `html/data/` (symlinks to `data/`).  
Full schema documentation: `docs/FRONTEND_PROMPT.md`  
Backend documentation: `docs/REFACTORING_PLAN.md`

### JSON files used by sections

| File | Used by sections |
|---|---|
| `dashboard_latest.json` | 01, 02, 03, 06 |
| `pipeline_progress.json` | 01 |
| `ledger_positions.json` | 01, 04 |
| `pipeline_latest.json` | 05 |
| `optimized_recommendation.json` | 05 |
| `scored_targets.json` | 04 |
| `performance_attribution.json` | 06 |
| `latest_run_summary.json` | (backup for 02 if needed) |
| `portfolio_diagnostics.json` | (backup for 06 if needed) |

### CSV files used by sections

| File | Used by sections |
|---|---|
| `portfolio_timeseries.csv` | 03 |
| `scored_stocks.csv` | 07 |
| `portfolio_results_db.csv` | 08 |

---

## Rules

1. **Render-only** — No calculations in JS beyond simple formatting (`×`, `÷` for display). If a derived metric is needed, add it to `D_Publish.py`.
2. **No frameworks** — Vanilla JS, Chart.js, PapaParse only.
3. **No build step** — No npm, no bundler. CDN imports only.
4. **Portuguese (pt-BR)** — All UI labels in Brazilian Portuguese.
5. **Dark theme** — Clean, modern, dark background.
6. **Mobile-first** — All sections must work on phone screens.
7. **Don't touch backend** — `engines/`, `data/`, `parameters/`, `shared_tools/` are read-only.

---

## How to Continue in a New Chat

Paste this as context:

> I'm building the frontend for PortfolioESG, a Python-based ESG portfolio analysis pipeline. The build plan is in `docs/FRONTEND_BUILD_PLAN.md`. Read that file first — it has the full section list, progress tracker, data sources per section, and rules. The sections are standalone HTML files in `html/sections/` that fetch data from `html/data/` (symlinks). Test with `python3 -m http.server 8000`. Resume from the first ❌ section in the progress tracker.

