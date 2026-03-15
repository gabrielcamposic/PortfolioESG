# PortfolioESG — Continuation Prompt

Paste this at the start of a new chat to resume implementation.

---

## Context

I'm building **PortfolioESG**, a Python pipeline for ESG stock portfolio analysis that runs on macOS and publishes results as a static site. The project lives at `/Users/gabrielcampos/PortfolioESG`.

## What was done (all complete ✅)

1. **Backend refactoring phases 1–4** — Documented in `docs/REFACTORING_PLAN.md`.
2. **Metrics alignment** — All 6 inconsistencies (A–F) fixed. Real TWR, benchmark, CDI, alpha all derive from the same daily series (`portfolio_real_daily.csv`). HHI corrected from model→real. Documented in `docs/D_PUBLISH_METRICS_PLAN.md`.
3. **Frontend page `1_portfolio.html`** — 9 metric cards (Patrimônio, Retorno R$, Retorno Corretora, Retorno %, TWR, % CDI, Volatilidade, Ibovespa, Alpha) in 5-column grid + line chart (base 100) + performance windows table + bar chart. Uses `dashboard_latest.json` + `portfolio_real_daily.csv`.
4. **Frontend page `2_risk.html`** — 3 risk KPI cards (Tracking Error, Information Ratio, HHI) + time-windowed table (All/YTD/3M/6M/12M/24M) + concentration bar chart. Uses `dashboard_latest.json` + `ledger_positions.json`. Plan: `docs/2_RISK_PAGE_PLAN.md`.
5. **Metrics reference** — Every metric documented with formula, source, and worked calculation example using real data. File: `docs/METRICS_REFERENCE.md`.
6. **Broker return analysis & implementation** — Full analysis in `docs/BROKER_RETURN_PLAN.md`. Implemented Modified Dietz monthly return with cash tracking from Ágora statement PDFs. Parser: `engines/B13_Cash_Parser.py` → `data/cash_movements.csv`. Computation: `engines/D_Publish.py → _compute_broker_return()`. Frontend: "Retorno Corretora" card in Row 1.

## What needs to be done now

**Evaluate the Modified Dietz results.** The current implementation shows +33.19% total vs broker's −2.66%. The gap is documented in `docs/METRICS_REFERENCE.md` (section "Retorno Corretora"). Main causes: Yahoo vs B3 prices, Modified Dietz day-weighting amplification in months with large deposits, and unknown broker methodology. Next steps could include:
- Trying an alternative formula (daily quota method instead of monthly Dietz)
- Using settlement dates (T+2) instead of trade dates
- Sourcing B3 official prices

## Key files

| File | Purpose |
|---|---|
| `docs/BROKER_RETURN_PLAN.md` | Full analysis + implementation plan (completed) |
| `docs/METRICS_REFERENCE.md` | All metrics documented with formulas and calculation examples |
| `docs/2_RISK_PAGE_PLAN.md` | Risk page plan (completed) |
| `engines/D_Publish.py` | Publisher script — all frontend data flows through here |
| `engines/B13_Cash_Parser.py` | Ágora statement PDF parser → `data/cash_movements.csv` |
| `data/ledger.csv` | All 43 transactions (trade_date, side, ticker, qty, price, total_cost) |
| `data/cash_movements.csv` | External cash flows: deposits, withdrawals, dividends, fund transfers |
| `data/portfolio_history.csv` | Daily per-position values (date, symbol, qty, price, value, market_value) |
| `data/results/portfolio_real_daily.csv` | Daily TWR returns (portfolio_return, benchmark_return, cdi_return) |
| `data/results/dashboard_latest.json` | Consolidated JSON consumed by frontend (includes `real.broker_return`) |
| `data/ledger_positions.json` | Current positions snapshot (9 positions, R$2,961.55 total) |
| `html/sections/1_portfolio.html` | Portfolio page (9 cards in 5-col grid + chart + table) |
| `html/sections/2_risk.html` | Risk page (3 cards + table + concentration chart) |

## Critical context for the broker return implementation

### Portfolio timeline
```
Oct 17: First purchase. 3 stocks, R$987.88
Nov 03: Bought more of same 3 stocks, R$923.23
Nov 10-11: SOLD EVERYTHING. Zero positions until Jan 2.
  → Cash from sales (~R$1,937) sat in brokerage earning 0%
  → portfolio_history.csv has NO rows for Nov 11 – Jan 1
Jan 02: New portfolio. 6 stocks, R$977.03 (partially funded from Nov cash)
Feb 02: Major deposit. 4 more stocks, R$1,962.35
Feb 19: Sold AXIA6 for R$318.42
Mar 13: Current. 9 positions, R$2,961.55
```

### The zero-position gap is the key challenge
`portfolio_history.csv` has data only for dates with positions (Oct 17 – Nov 10, Jan 2 – present). The broker tracks the full account including the zero-position period (Nov 11 – Jan 1) where cash earned 0%. D_Publish needs to detect this gap and fill it with 0% return months.

### Data limitations
- `ledger.csv` has stock transactions but NOT external deposits/withdrawals from the bank. The heuristic `external_deposit = buy_cost - max(available_cash, 0)` is an approximation.
- Yahoo Finance prices may differ ±0.5% from B3 official prices the broker uses.
- Settlement is T+2 in Brazil; broker may use settlement dates, we use trade dates.

## Project structure

```
engines/run_all.sh          — Master orchestrator (A→B→C→D)
engines/D_Publish.py        — Publisher (generates html/data/ for frontend)
data/                       — Canonical data source
data/results/               — Engine outputs
html/data/                  — Symlinks to data/ (frontend reads from here)
html/sections/              — Standalone frontend pages
docs/                       — All documentation
```

## Rules

1. **Render-only frontend** — No calculations in JS beyond formatting and composing `∏(1+r)` for charts. If a derived metric is needed, add it to D_Publish.py.
2. **No frameworks** — Vanilla JS, Chart.js, PapaParse only. No npm, no bundler.
3. **data/ is the single source of truth** — html/data/ contains only symlinks.
4. **Portuguese (pt-BR)** for UI labels, English for code/docs.
5. **Dark theme** — Same CSS variables as existing pages.

## Testing

```bash
cd /Users/gabrielcampos/PortfolioESG
python3 engines/D_Publish.py          # Regenerate dashboard JSON
cd html && python3 -m http.server 8000  # Serve frontend
# Visit http://localhost:8000/sections/1_portfolio.html
# Visit http://localhost:8000/sections/2_risk.html
```
