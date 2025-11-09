import os
import json
import pandas as pd


def load_param_value(param_file, param_name):
    with open(param_file, 'r') as f:
        for line in f:
            line = line.strip()
            if line.startswith('#') or '=' not in line:
                continue
            key, value = line.split('=', 1)
            if key.strip() == param_name:
                return os.path.expanduser(value.strip())
    raise KeyError(f"{param_name} not found in {param_file}")


# Parameter files - resolve relative to repository (script) root so engines work
# regardless of where the repo is cloned (no hard-coded /Users/... paths).
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
REPO_ROOT = os.path.abspath(os.path.join(SCRIPT_DIR, '..'))
ANAPAR_FILE = os.path.join(REPO_ROOT, 'parameters', 'anapar.txt')
PORTPAR_FILE = os.path.join(REPO_ROOT, 'parameters', 'portpar.txt')
PATHS_FILE = os.path.join(REPO_ROOT, 'parameters', 'paths.txt')

# Load parameters
PORTFOLIO_DB = load_param_value(PORTPAR_FILE, 'PORTFOLIO_RESULTS_DB_FILE')
STOCK_DB = load_param_value(PATHS_FILE, 'FINDB_FILE')
initial_value = float(load_param_value(PORTPAR_FILE, 'initial_investment'))
with open(ANAPAR_FILE, 'r') as f:
    for line in f:
        if line.strip().startswith('OUTPUT_CSV'):
            OUTPUT_CSV = os.path.expanduser(line.split('=', 1)[1].strip())
        elif line.strip().startswith('BENCHMARK_TICKERS'):
            BENCHMARK_TICKERS = [ticker.strip() for ticker in line.split('=', 1)[1].split(',')]
    if 'OUTPUT_CSV' not in locals():
        raise KeyError("OUTPUT_CSV not found in anapar.txt")
    if 'BENCHMARK_TICKERS' not in locals():
        raise KeyError("BENCHMARK_TICKERS not found in anapar.txt")
if len(BENCHMARK_TICKERS) != 2:
    raise ValueError("Exactly two benchmark tickers must be specified in BENCHMARK_TICKERS.")

# Load latest portfolio
portfolios = pd.read_csv(PORTFOLIO_DB)
latest_row = portfolios.sort_values('run_id').iloc[-1]
# Build portfolio dict from stocks and weights columns
stocks = [s.strip() for s in latest_row['stocks'].split(',')]
weights_list = [float(w.strip()) for w in latest_row['weights'].split(',')]
portfolio = dict(zip(stocks, weights_list))
run_id = latest_row['run_id']

# Load stock data
stock_df = pd.read_csv(STOCK_DB, parse_dates=['Date'])

# Pivot stock data for fast lookup (keep all stocks, not just portfolio)
stock_prices = stock_df.pivot(index='Date', columns='Stock', values='Close')

# Align dates (use all available dates in stock_prices)
dates = stock_prices.index

# Calculate portfolio value (start at initial_value)
weights = pd.Series(portfolio)
portfolio_prices = stock_prices[portfolio.keys()]
stock_returns = portfolio_prices.pct_change(fill_method=None)
portfolio_daily_return = (stock_returns * weights).sum(axis=1)
portfolio_daily_return.iloc[0] = 0.0  # Ensure first row is zero
portfolio_real_value = initial_value * (1 + portfolio_daily_return).cumprod()

bench1, bench2 = BENCHMARK_TICKERS
if bench1 not in stock_prices.columns:
    raise ValueError(f"Benchmark ticker {bench1} not found in stock data.")
if bench2 not in stock_prices.columns:
    raise ValueError(f"Benchmark ticker {bench2} not found in stock data.")

bench1_prices = stock_prices[bench1].sort_index().ffill()
bench2_prices = stock_prices[bench2].sort_index().ffill()
portfolio_real_value_full = portfolio_real_value

bench1_first = bench1_prices.first_valid_index()
bench2_first = bench2_prices.first_valid_index()
portfolio_first = portfolio_real_value_full.first_valid_index()
start_date = max(d for d in [bench1_first, bench2_first, portfolio_first] if d is not None)

bench1_prices = bench1_prices.loc[start_date:]
bench2_prices = bench2_prices.loc[start_date:]
portfolio_real_value = portfolio_real_value_full.loc[start_date:]
portfolio_daily_return = portfolio_daily_return.loc[start_date:]
dates = portfolio_real_value.index
portfolio_prices = portfolio_prices.loc[start_date:]
stock_returns = stock_returns.loc[start_date:]

bench1_daily_return = bench1_prices.pct_change(fill_method=None)
bench2_daily_return = bench2_prices.pct_change(fill_method=None)
bench1_real_value = bench1_prices
bench2_real_value = bench2_prices

# Ensure first value of daily returns is zero after date alignment
portfolio_daily_return.iloc[0] = 0.0
bench1_daily_return.iloc[0] = 0.0
bench2_daily_return.iloc[0] = 0.0

# Accumulated return series (base 1000 for comparability)
portfolio_accum_return = 1000 * (1 + portfolio_daily_return).cumprod()
bench1_accum_return = 1000 * (1 + bench1_daily_return).cumprod()
bench2_accum_return = 1000 * (1 + bench2_daily_return).cumprod()

# Portfolio composition per day: {stock: {"weight": w, "value": v}}
portfolio_compositions = []
for idx, date in enumerate(dates):
    comp = {}
    for stock in portfolio.keys():
        comp[stock] = {
            "weight": portfolio[stock],
            "value": float(portfolio_prices.loc[date, stock]) if not pd.isna(portfolio_prices.loc[date, stock]) else None
        }
    portfolio_compositions.append(json.dumps(comp))

# --- PERFORMANCE ATTRIBUTION ANALYSIS (Brinson-Fachler) ---
# Calculate attribution effects: Stock Selection, Allocation, and Interaction
attribution_results = None
try:
    # Load scored stocks to get sector information
    SCORED_STOCKS_FILE = load_param_value(PORTPAR_FILE, 'SCORED_STOCKS_DB_FILE')
    scored_df = pd.read_csv(SCORED_STOCKS_FILE)
    latest_scored_run = scored_df['run_id'].max()
    scored_latest = scored_df[scored_df['run_id'] == latest_scored_run][['Stock', 'Sector']].set_index('Stock')

    # Map portfolio stocks to sectors
    portfolio_sectors = {}
    for stock in portfolio.keys():
        if stock in scored_latest.index:
            portfolio_sectors[stock] = scored_latest.loc[stock, 'Sector']

    if len(portfolio_sectors) > 0:
        # Calculate portfolio sector weights
        port_sector_weights = {}
        for stock, weight in portfolio.items():
            sector = portfolio_sectors.get(stock, 'Unknown')
            port_sector_weights[sector] = port_sector_weights.get(sector, 0) + weight

        # Calculate portfolio sector returns (last 12 months)
        twelve_months_ago = dates.max() - pd.DateOffset(months=12)
        recent_dates = dates[dates >= twelve_months_ago]

        port_sector_returns = {}
        for sector in port_sector_weights.keys():
            sector_stocks = [s for s, sec in portfolio_sectors.items() if sec == sector]
            if sector_stocks:
                sector_stock_returns = stock_returns.loc[recent_dates, sector_stocks]
                # Weight by portfolio weights within sector
                sector_weights_norm = {s: portfolio[s] / port_sector_weights[sector] for s in sector_stocks}
                sector_return = sum((sector_stock_returns[s] * sector_weights_norm[s]).sum() for s in sector_stocks) / len(recent_dates)
                port_sector_returns[sector] = sector_return

        # Calculate benchmark sector weights and returns using all scored stocks as proxy
        # Get all stocks from benchmark that are in scored_latest
        bench_stocks = [s for s in stock_prices.columns if s in scored_latest.index and s != bench1 and s != bench2]

        if len(bench_stocks) > 0:
            # Use equal weighting as benchmark proxy
            bench_weight = 1.0 / len(bench_stocks)
            bench_sector_weights = {}
            bench_sector_stocks = {}

            for stock in bench_stocks:
                sector = scored_latest.loc[stock, 'Sector']
                bench_sector_weights[sector] = bench_sector_weights.get(sector, 0) + bench_weight
                if sector not in bench_sector_stocks:
                    bench_sector_stocks[sector] = []
                bench_sector_stocks[sector].append(stock)

            # Calculate benchmark sector returns
            bench_sector_returns = {}
            for sector, stocks_list in bench_sector_stocks.items():
                available_stocks = [s for s in stocks_list if s in stock_returns.columns]
                if available_stocks:
                    try:
                        # Select only available columns to avoid unexpected errors
                        cols = [c for c in available_stocks if c in stock_returns.columns]
                        if not cols:
                            bench_sector_returns[sector] = 0.0
                        else:
                            # Reindex to recent_dates to ensure alignment, then compute row-wise mean
                            df_cols = stock_returns[cols]
                            df_slice = df_cols.reindex(index=recent_dates)
                            if df_slice.dropna(how='all').empty:
                                bench_sector_returns[sector] = 0.0
                            else:
                                sector_returns = df_slice.mean(axis=1)
                                mean_val = sector_returns.mean()
                                bench_sector_returns[sector] = float(mean_val) if not pd.isna(mean_val) else 0.0
                    except Exception:
                        # On any unexpected error, fall back to zero for robustness
                        bench_sector_returns[sector] = 0.0

            # Calculate portfolio and benchmark total returns
            portfolio_return = portfolio_daily_return.loc[recent_dates].mean() * 252  # Annualized
            benchmark_return = bench1_daily_return.loc[recent_dates].mean() * 252  # Annualized

            # Brinson-Fachler Attribution
            all_sectors = set(list(port_sector_weights.keys()) + list(bench_sector_weights.keys()))

            allocation_effect = 0
            selection_effect = 0
            interaction_effect = 0

            for sector in all_sectors:
                w_p = port_sector_weights.get(sector, 0)  # Portfolio weight in sector
                w_b = bench_sector_weights.get(sector, 0)  # Benchmark weight in sector
                r_p = port_sector_returns.get(sector, 0) * 252  # Portfolio sector return (annualized)
                r_b = bench_sector_returns.get(sector, 0) * 252  # Benchmark sector return (annualized)

                # Allocation Effect: (w_p - w_b) * (r_b - benchmark_return)
                allocation_effect += (w_p - w_b) * (r_b - benchmark_return)

                # Selection Effect: w_b * (r_p - r_b)
                selection_effect += w_b * (r_p - r_b)

                # Interaction Effect: (w_p - w_b) * (r_p - r_b)
                interaction_effect += (w_p - w_b) * (r_p - r_b)

            attribution_results = {
                'allocation_effect': float(allocation_effect * 100),  # Convert to percentage
                'selection_effect': float(selection_effect * 100),
                'interaction_effect': float(interaction_effect * 100),
                'total_active_return': float((portfolio_return - benchmark_return) * 100)
            }

except Exception as e:
    print(f"Warning: Could not calculate performance attribution: {e}")
    attribution_results = None

output = pd.DataFrame({
    'run_id': run_id,
    'date': dates,
    'portfolio_real_value': portfolio_real_value.values,
    'benchmark1_name': bench1,
    'benchmark1_real_value': bench1_real_value.values,
    'benchmark2_name': bench2,
    'benchmark2_real_value': bench2_real_value.values,
    'portfolio_daily_return': portfolio_daily_return.values,
    'benchmark1_daily_return': bench1_daily_return.values,
    'benchmark2_daily_return': bench2_daily_return.values,
    'portfolio_accum_return': portfolio_accum_return.values,
    'benchmark1_accum_return': bench1_accum_return.values,
    'benchmark2_accum_return': bench2_accum_return.values,
    'portfolio_composition': portfolio_compositions
})

# === Momentum & Valuation Metrics ===
# numpy is already imported above via pandas/numpy in other modules; import once here
import numpy as np  # explicit local import kept for clarity in this module

def compute_momentum_val_metrics(stock_df, portfolio, benchmark_df, financials_df, logger):
    metrics = {}

    try:
        # Momentum (3m, 6m, 12m)
        stock_df = stock_df.pivot(index='Date', columns='Stock', values='Close').dropna()
        returns_3m = stock_df.pct_change(63, fill_method=None).iloc[-1]
        returns_6m = stock_df.pct_change(126, fill_method=None).iloc[-1]
        returns_12m = stock_df.pct_change(252, fill_method=None).iloc[-1]

        momentum_signal = (returns_3m + returns_6m + returns_12m) / 3
        metrics['momentum_signal_strength'] = np.nansum(momentum_signal * pd.Series(portfolio))

        # Forward P/E implied upside
        pe_portfolio = np.nansum(financials_df.set_index('Stock')['forwardPE'] * pd.Series(portfolio))
        pe_benchmark = financials_df['forwardPE'].mean()  # benchmark médio
        metrics['forward_pe_implied_upside'] = (pe_benchmark - pe_portfolio) / pe_portfolio

        # Dividend yield ponderado
        if 'dividendYield' in financials_df.columns:
            dy_portfolio = np.nansum(financials_df.set_index('Stock')['dividendYield'] * pd.Series(portfolio))
            metrics['weighted_dividend_yield'] = dy_portfolio
        else:
            metrics['weighted_dividend_yield'] = np.nan
    except Exception:
        logger.warning("Failed to compute momentum/valuation metrics")
    return metrics


# === Practical Diagnostics ===
def compute_practical_diagnostics(portfolio_df, portfolio_timeseries, benchmark_series, logger):
    metrics = {}

    try:
        # Turnover
        if len(portfolio_df) > 1:
            weights_now = np.array([float(w) for w in portfolio_df.iloc[-1]['weights'].split(',')])
            weights_prev = np.array([float(w) for w in portfolio_df.iloc[-2]['weights'].split(',')])
            metrics['turnover'] = 0.5 * np.sum(np.abs(weights_now - weights_prev))
        else:
            metrics['turnover'] = 0.0

        # Liquidity screen (peso vs volume médio diário)
        metrics['liquidity_score'] = (portfolio_timeseries['avg_volume'] / portfolio_timeseries['portfolio_weight']).mean()

        # Tracking error e Information Ratio
        merged = pd.DataFrame({
            'portfolio': portfolio_timeseries['portfolio_value'].pct_change(),
            'benchmark': benchmark_series.pct_change()
        }).dropna()
        excess_returns = merged['portfolio'] - merged['benchmark']
        metrics['tracking_error'] = excess_returns.std() * np.sqrt(252)
        metrics['information_ratio'] = excess_returns.mean() / metrics['tracking_error']
    except Exception:
        logger.warning("Failed to compute diagnostics metrics")
    return metrics

output.to_csv(OUTPUT_CSV, index=False)

html_data_dir = os.path.expanduser('~/PortfolioESG/html/data')
os.makedirs(html_data_dir, exist_ok=True)
output.to_csv(os.path.join(html_data_dir, 'portfolio_timeseries.csv'), index=False)

# Save attribution results to JSON
if attribution_results is not None:
    attribution_file = os.path.join(html_data_dir, 'performance_attribution.json')
    with open(attribution_file, 'w') as f:
        json.dump(attribution_results, f, indent=4)
    print(f"Performance attribution saved to {attribution_file}")

# === Portfolio Diagnostics & Metrics ===
# numpy already in use above; keep single import
import numpy as np

# Load financials and liquidity data
financials_path = os.path.expanduser('~/PortfolioESG/data/findb/FinancialsDB.csv')
financials_df = pd.read_csv(financials_path)
financials_df = financials_df.set_index('Stock')

# Helper: get portfolio weights as Series
weights_series = pd.Series(portfolio)

# --- Momentum Signal Strength (weighted average of 3m/6m/12m momentum) ---
try:
    price_pivot = stock_df.pivot(index='Date', columns='Stock', values='Close').sort_index()
    returns_3m = price_pivot.pct_change(63, fill_method=None).iloc[-1]
    returns_6m = price_pivot.pct_change(126, fill_method=None).iloc[-1]
    returns_12m = price_pivot.pct_change(252, fill_method=None).iloc[-1]
    momentum_signal = (returns_3m + returns_6m + returns_12m) / 3
    # Only use stocks in portfolio
    momentum_signal = momentum_signal[weights_series.index]
    momentum_signal_strength = float(np.nansum(momentum_signal * weights_series))
except Exception:
    momentum_signal_strength = None

# --- Forward P/E Implied Upside (portfolio vs. benchmark) ---
try:
    pe_portfolio = np.nansum(financials_df.loc[weights_series.index]['forwardPE'] * weights_series)
    # Use all stocks in financials as benchmark proxy
    pe_benchmark = financials_df['forwardPE'].mean()
    forward_pe_implied_upside = float((pe_benchmark - pe_portfolio) / pe_portfolio) if pe_portfolio else None
except Exception:
    forward_pe_implied_upside = None

# --- Weighted Dividend Yield ---
try:
    if 'dividendYield' in financials_df.columns:
        dy_portfolio = np.nansum(financials_df.loc[weights_series.index]['dividendYield'].fillna(0) * weights_series)
        weighted_dividend_yield = float(dy_portfolio)
    else:
        weighted_dividend_yield = None
except Exception:
    weighted_dividend_yield = None

# --- Turnover (between last two portfolio weights) ---
try:
    if len(portfolios) > 1:
        prev_row = portfolios.sort_values('run_id').iloc[-2]
        prev_weights = pd.Series([float(w.strip()) for w in prev_row['weights'].split(',')], index=[s.strip() for s in prev_row['stocks'].split(',')])
        # Align indices
        prev_weights = prev_weights.reindex(weights_series.index).fillna(0)
        turnover = float(0.5 * np.sum(np.abs(weights_series - prev_weights)))
    else:
        turnover = 0.0
except Exception:
    turnover = None

# --- Liquidity Screen (portfolio weight vs. average daily volume) ---
try:
    avg_volumes = financials_df.loc[weights_series.index]['averageVolume']
    liquidity_score = float((avg_volumes / weights_series).mean()) if not weights_series.isnull().all() else None
except Exception:
    liquidity_score = None

# --- Tracking Error & Information Ratio (vs. benchmark) ---
try:
    # Use bench1 as main benchmark
    merged = pd.DataFrame({
        'portfolio': portfolio_real_value.pct_change(),
        'benchmark': bench1_real_value.pct_change()
    }).dropna()
    excess_returns = merged['portfolio'] - merged['benchmark']
    tracking_error = float(excess_returns.std() * np.sqrt(252))
    information_ratio = float(excess_returns.mean() / tracking_error) if tracking_error != 0 else None
except Exception:
    tracking_error = None
    information_ratio = None

# Save all metrics to JSON
portfolio_diagnostics = {
    'momentum_signal_strength': momentum_signal_strength,
    'forward_pe_implied_upside': forward_pe_implied_upside,
    'weighted_dividend_yield': weighted_dividend_yield,
    'turnover': turnover,
    'liquidity_score': liquidity_score,
    'tracking_error': tracking_error,
    'information_ratio': information_ratio
}
with open(os.path.join(html_data_dir, 'portfolio_diagnostics.json'), 'w') as f:
    json.dump(portfolio_diagnostics, f, indent=4)
