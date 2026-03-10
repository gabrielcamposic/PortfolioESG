#!/usr/bin/env python

# --- Script Version ---
ANALYSIS_PY_VERSION = "2.0.0"  # Refactored to use shared_utils and standard structure.

# ----------------------------------------------------------- #
#                           Libraries                         #
# ----------------------------------------------------------- #
import os
import sys
import time
import json
import logging
import csv
from datetime import datetime
import pandas as pd
import numpy as np

# Ensure project root is on sys.path for imports
script_dir_boot = os.path.dirname(os.path.abspath(__file__))
project_root = os.path.abspath(os.path.join(script_dir_boot, '..'))
if project_root not in sys.path:
    sys.path.insert(0, project_root)

from typing import Optional, Dict, Any

from shared_tools.shared_utils import (
    setup_logger,
    load_parameters_from_file,
    initialize_performance_data,
    log_performance_data,
)
import math

# ----------------------------------------------------------- #
#                        Helper Functions                     #
# ----------------------------------------------------------- #

def load_latest_portfolio(portfolio_db_path: str, logger: logging.Logger) -> tuple:
    """Load the latest portfolio from the results database."""
    portfolios = pd.read_csv(portfolio_db_path)
    latest_row = portfolios.sort_values('run_id').iloc[-1]
    stocks = [s.strip() for s in latest_row['stocks'].split(',')]
    weights_list = [float(w.strip()) for w in latest_row['weights'].split(',')]
    portfolio = dict(zip(stocks, weights_list))
    run_id = latest_row['run_id']
    logger.info(f"Loaded portfolio from run_id: {run_id} with {len(stocks)} stocks")
    return portfolio, run_id, portfolios


def calculate_portfolio_value(stock_prices: pd.DataFrame, portfolio: dict,
                               initial_value: float) -> tuple:
    """Calculate portfolio value time series."""
    weights = pd.Series(portfolio)
    portfolio_prices = stock_prices[list(portfolio.keys())]
    stock_returns = portfolio_prices.pct_change(fill_method=None)
    portfolio_daily_return = (stock_returns * weights).sum(axis=1)
    portfolio_daily_return.iloc[0] = 0.0
    portfolio_real_value = initial_value * (1 + portfolio_daily_return).cumprod()
    return portfolio_real_value, portfolio_daily_return, stock_returns, portfolio_prices


def calculate_benchmark_values(stock_prices: pd.DataFrame, bench1: str, bench2: Optional[str],
                                logger: logging.Logger) -> tuple:
    """Calculate benchmark value time series. Second benchmark is optional."""
    if bench1 not in stock_prices.columns:
        raise ValueError(f"Benchmark ticker {bench1} not found in stock data.")

    bench1_prices = stock_prices[bench1].sort_index().ffill()

    # Second benchmark is optional
    bench2_prices = None
    if bench2 and bench2 in stock_prices.columns:
        bench2_prices = stock_prices[bench2].sort_index().ffill()
        logger.info(f"Loaded benchmarks: {bench1}, {bench2}")
    else:
        if bench2:
            logger.warning(f"Secondary benchmark {bench2} not found, using primary only")
        logger.info(f"Loaded benchmark: {bench1}")

    return bench1_prices, bench2_prices


def calculate_brinson_attribution(portfolio: dict, portfolio_daily_return: pd.Series,
                                   stock_returns: pd.DataFrame, bench1_daily_return: pd.Series,
                                   scored_stocks_file: str, dates: pd.DatetimeIndex,
                                   stock_prices: pd.DataFrame, bench1: str, bench2: str,
                                   logger: logging.Logger) -> Optional[Dict[str, Any]]:
    """Calculate Brinson-Fachler performance attribution."""
    try:
        scored_df = pd.read_csv(scored_stocks_file)
        latest_scored_run = scored_df['run_id'].max()
        scored_latest = scored_df[scored_df['run_id'] == latest_scored_run][['Stock', 'Sector']].set_index('Stock')

        # Map portfolio stocks to sectors
        portfolio_sectors = {}
        for stock in portfolio.keys():
            if stock in scored_latest.index:
                portfolio_sectors[stock] = scored_latest.loc[stock, 'Sector']

        if len(portfolio_sectors) == 0:
            logger.warning("No portfolio stocks found in scored stocks. Skipping attribution.")
            return None

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
                sector_weights_norm = {s: portfolio[s] / port_sector_weights[sector] for s in sector_stocks}
                sector_return = sum((sector_stock_returns[s] * sector_weights_norm[s]).sum()
                                   for s in sector_stocks) / len(recent_dates)
                port_sector_returns[sector] = sector_return

        # Calculate benchmark sector weights and returns
        bench_stocks = [s for s in stock_prices.columns
                       if s in scored_latest.index and s != bench1 and s != bench2]

        if len(bench_stocks) == 0:
            logger.warning("No benchmark stocks found. Skipping attribution.")
            return None

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
                    df_slice = stock_returns[available_stocks].reindex(index=recent_dates)
                    if df_slice.dropna(how='all').empty:
                        bench_sector_returns[sector] = 0.0
                    else:
                        sector_returns_series = df_slice.mean(axis=1)
                        mean_val = sector_returns_series.mean()
                        bench_sector_returns[sector] = float(mean_val) if not pd.isna(mean_val) else 0.0
                except (KeyError, ValueError):
                    bench_sector_returns[sector] = 0.0

        # Calculate total returns
        portfolio_return = portfolio_daily_return.loc[recent_dates].mean() * 252
        benchmark_return = bench1_daily_return.loc[recent_dates].mean() * 252

        # Brinson-Fachler Attribution
        all_sectors = set(list(port_sector_weights.keys()) + list(bench_sector_weights.keys()))

        allocation_effect = 0
        selection_effect = 0
        interaction_effect = 0

        for sector in all_sectors:
            w_p = port_sector_weights.get(sector, 0)
            w_b = bench_sector_weights.get(sector, 0)
            r_p = port_sector_returns.get(sector, 0) * 252
            r_b = bench_sector_returns.get(sector, 0) * 252

            allocation_effect += (w_p - w_b) * (r_b - benchmark_return)
            selection_effect += w_b * (r_p - r_b)
            interaction_effect += (w_p - w_b) * (r_p - r_b)

        total_active_return = float((portfolio_return - benchmark_return) * 100)
        sum_of_effects = float((allocation_effect + selection_effect + interaction_effect) * 100)

        # Calculate residual (should be near zero with proper Brinson decomposition)
        residual = total_active_return - sum_of_effects

        attribution_results = {
            'allocation_effect': float(allocation_effect * 100),
            'selection_effect': float(selection_effect * 100),
            'interaction_effect': float(interaction_effect * 100),
            'total_active_return': total_active_return,
            'sum_of_effects': sum_of_effects,
            'residual': residual if abs(residual) > 0.01 else 0.0  # Only show if > 0.01%
        }

        logger.info(f"Attribution calculated: Active Return = {attribution_results['total_active_return']:.2f}%, "
                    f"Sum of Effects = {sum_of_effects:.2f}%, Residual = {residual:.4f}%")
        return attribution_results

    except FileNotFoundError:
        logger.warning(f"Scored stocks file not found: {scored_stocks_file}")
        return None
    except Exception as e:
        logger.warning(f"Could not calculate performance attribution: {e}")
        return None


def calculate_diagnostics(portfolio: dict, portfolios: pd.DataFrame,
                          stock_df: pd.DataFrame, financials_df: pd.DataFrame,
                          portfolio_real_value: pd.Series, bench1_real_value: pd.Series,
                          logger: logging.Logger) -> dict:
    """Calculate portfolio diagnostics metrics."""
    weights_series = pd.Series(portfolio)
    diagnostics = {}

    # --- Momentum Signal Strength ---
    try:
        price_pivot = stock_df.pivot(index='Date', columns='Stock', values='Close').sort_index()
        returns_3m = price_pivot.pct_change(63, fill_method=None).iloc[-1]
        returns_6m = price_pivot.pct_change(126, fill_method=None).iloc[-1]
        returns_12m = price_pivot.pct_change(252, fill_method=None).iloc[-1]
        momentum_signal = (returns_3m + returns_6m + returns_12m) / 3
        momentum_signal = momentum_signal.reindex(weights_series.index)
        diagnostics['momentum_signal_strength'] = float(np.nansum(momentum_signal * weights_series))
    except (KeyError, ValueError):
        diagnostics['momentum_signal_strength'] = None

    # --- Forward P/E Implied Upside ---
    try:
        valid_stocks = [s for s in weights_series.index if s in financials_df.index]
        if valid_stocks:
            pe_portfolio = np.nansum(financials_df.loc[valid_stocks]['forwardPE'] * weights_series[valid_stocks])
            pe_benchmark = financials_df['forwardPE'].mean()
            diagnostics['forward_pe_implied_upside'] = float((pe_benchmark - pe_portfolio) / pe_portfolio) if pe_portfolio else None
        else:
            diagnostics['forward_pe_implied_upside'] = None
    except (KeyError, ValueError):
        diagnostics['forward_pe_implied_upside'] = None

    # --- Weighted Dividend Yield ---
    try:
        if 'dividendYield' in financials_df.columns:
            valid_stocks = [s for s in weights_series.index if s in financials_df.index]
            if valid_stocks:
                dy_portfolio = np.nansum(financials_df.loc[valid_stocks]['dividendYield'].fillna(0) * weights_series[valid_stocks])
                diagnostics['weighted_dividend_yield'] = float(dy_portfolio)
            else:
                diagnostics['weighted_dividend_yield'] = None
        else:
            diagnostics['weighted_dividend_yield'] = None
    except (KeyError, ValueError):
        diagnostics['weighted_dividend_yield'] = None

    # --- Turnover ---
    try:
        if len(portfolios) > 1:
            prev_row = portfolios.sort_values('run_id').iloc[-2]
            prev_weights = pd.Series(
                [float(w.strip()) for w in prev_row['weights'].split(',')],
                index=[s.strip() for s in prev_row['stocks'].split(',')]
            )
            prev_weights = prev_weights.reindex(weights_series.index).fillna(0)
            diagnostics['turnover'] = float(0.5 * np.sum(np.abs(weights_series - prev_weights)))
        else:
            diagnostics['turnover'] = 0.0
    except (KeyError, ValueError):
        diagnostics['turnover'] = None

    # --- Liquidity Score ---
    try:
        if 'averageVolume' in financials_df.columns:
            valid_stocks = [s for s in weights_series.index if s in financials_df.index]
            if valid_stocks:
                avg_volumes = financials_df.loc[valid_stocks]['averageVolume']
                diagnostics['liquidity_score'] = float((avg_volumes / weights_series[valid_stocks]).mean())
            else:
                diagnostics['liquidity_score'] = None
        else:
            diagnostics['liquidity_score'] = None
    except (KeyError, ValueError, ZeroDivisionError):
        diagnostics['liquidity_score'] = None

    # --- Tracking Error & Information Ratio ---
    try:
        merged = pd.DataFrame({
            'portfolio': portfolio_real_value.pct_change(),
            'benchmark': bench1_real_value.pct_change()
        }).dropna()
        excess_returns = merged['portfolio'] - merged['benchmark']
        tracking_error = float(excess_returns.std() * np.sqrt(252))
        diagnostics['tracking_error'] = tracking_error
        # Information Ratio: annualized excess return / tracking error
        # Both numerator and denominator must be annualized for correct ratio
        annualized_excess_return = float(excess_returns.mean() * 252)
        diagnostics['information_ratio'] = annualized_excess_return / tracking_error if tracking_error != 0 else None
        # Store benchmark return for frontend display
        benchmark_annual_return = float(merged['benchmark'].mean() * 252)
        diagnostics['benchmark_annual_return'] = benchmark_annual_return
    except (KeyError, ValueError, ZeroDivisionError):
        diagnostics['tracking_error'] = None
        diagnostics['information_ratio'] = None
        diagnostics['benchmark_annual_return'] = None

    logger.info(f"Diagnostics calculated: {len([v for v in diagnostics.values() if v is not None])} metrics")
    return diagnostics


# ----------------------------------------------------------- #
#  Real-Portfolio Metrics (migrated from D_MIS.py)            #
# ----------------------------------------------------------- #

def _safe_float(v, default=0.0) -> float:
    if v is None or v == "":
        return default
    try:
        return float(v)
    except (TypeError, ValueError):
        return default


def calculate_sortino(daily_returns: list, annual_return: float,
                      trading_days: int = 252, risk_free: float = 0.1175) -> float:
    """Sortino ratio: excess return / downside volatility."""
    downside = [r for r in daily_returns if r < 0]
    if len(downside) < 2:
        return 0.0
    downside_vol = float(np.std(downside, ddof=1) * np.sqrt(trading_days))
    if downside_vol == 0:
        return 0.0
    return (annual_return - risk_free) / downside_vol


def calculate_max_drawdown(values: list) -> float:
    """Maximum drawdown from a series of portfolio values."""
    if len(values) < 2:
        return 0.0
    peak = values[0]
    max_dd = 0.0
    for v in values[1:]:
        if v > peak:
            peak = v
        dd = (peak - v) / peak if peak > 0 else 0.0
        max_dd = max(max_dd, dd)
    return max_dd


def calculate_beta(portfolio_returns: list, benchmark_returns: list) -> Optional[float]:
    """Beta of portfolio vs benchmark."""
    if len(portfolio_returns) != len(benchmark_returns) or len(portfolio_returns) < 2:
        return None
    p = np.array(portfolio_returns)
    b = np.array(benchmark_returns)
    var_b = np.var(b, ddof=1)
    if var_b == 0:
        return None
    cov = np.cov(p, b, ddof=1)[0, 1]
    return float(cov / var_b)


def calculate_twr(portfolio_values: list, dates: list, flows: dict) -> list:
    """Time-Weighted Return with flow adjustments.
    
    Args:
        portfolio_values: daily portfolio market values
        dates: corresponding date strings
        flows: dict of {date_str: net_cash_flow} (positive = inflow)
    
    Returns:
        list of {date, value} daily TWR returns
    """
    if len(portfolio_values) < 2:
        return []
    returns = []
    for i in range(1, len(portfolio_values)):
        v_prev = _safe_float(portfolio_values[i - 1])
        v_curr = _safe_float(portfolio_values[i])
        f_t = _safe_float(flows.get(dates[i], 0.0))
        if v_prev > 0:
            r_t = (v_curr - f_t) / v_prev - 1
            returns.append({"date": dates[i], "value": r_t})
    return returns


def calculate_performance_windows(twr_returns: list, bench_returns_with_dates: list,
                                   end_date_str: str) -> dict:
    """Calculate performance over standard windows (YTD, 3M, 6M, 12M, 24M)."""
    end_date = pd.Timestamp(end_date_str)
    windows = {}

    def window_start(key):
        if key == "YTD":
            return pd.Timestamp(year=end_date.year, month=1, day=1)
        months = {"3M": 3, "6M": 6, "12M": 12, "24M": 24}.get(key, 0)
        return end_date - pd.DateOffset(months=months)

    def window_return(returns_list, start, end):
        product = 1.0
        for r in returns_list:
            dt = pd.Timestamp(r["date"])
            if start <= dt <= end:
                product *= (1 + _safe_float(r.get("value"), 0.0))
        return product - 1.0

    for key in ["YTD", "3M", "6M", "12M", "24M"]:
        start = window_start(key)
        windows[key] = {
            "portfolio": window_return(twr_returns, start, end_date),
            "benchmark": window_return(bench_returns_with_dates, start, end_date),
        }
    return windows


def calculate_asset_attribution(portfolio_daily_return: pd.Series,
                                 stock_returns: pd.DataFrame,
                                 portfolio: dict,
                                 dates: pd.DatetimeIndex) -> list:
    """Calculate per-asset return attribution (avg_weight, contribution, volatility)."""
    results = []
    weights = pd.Series(portfolio)

    for stock in portfolio.keys():
        if stock not in stock_returns.columns:
            continue
        stock_ret = stock_returns[stock].dropna()
        if stock_ret.empty:
            continue

        weight = weights[stock]
        contribution = float((stock_ret * weight).sum())
        vol = float(stock_ret.std() * np.sqrt(252)) if len(stock_ret) > 1 else 0.0

        # Realized return
        cumulative = (1 + stock_ret).prod() - 1

        results.append({
            "symbol": stock,
            "avg_weight": float(weight),
            "total_contribution": contribution,
            "volatility": vol,
            "realized_return": float(cumulative),
            "observations": len(stock_ret),
        })
    return results


def calculate_extended_diagnostics(
    portfolio: dict,
    portfolio_daily_return: pd.Series,
    portfolio_real_value: pd.Series,
    bench1_daily_return: pd.Series,
    bench1_prices: pd.Series,
    stock_returns: pd.DataFrame,
    dates: pd.DatetimeIndex,
    ledger_csv_path: str,
    portfolio_history_path: str,
    logger: logging.Logger,
) -> dict:
    """Calculate extended diagnostics including metrics from D_MIS.py."""
    extended = {}
    trading_days = 252
    risk_free = 0.1175  # SELIC annual

    try:
        # Basic series
        port_returns = portfolio_daily_return.dropna().tolist()
        bench_returns = bench1_daily_return.reindex(portfolio_daily_return.index).dropna().tolist()
        port_values = portfolio_real_value.dropna().tolist()

        # Annual return & volatility
        if len(port_returns) > 1:
            total_return = (1 + pd.Series(port_returns)).prod() - 1
            n_days = len(port_returns)
            annual_return = (1 + total_return) ** (trading_days / n_days) - 1 if total_return > -1 else -1.0
            annual_vol = float(np.std(port_returns, ddof=1) * np.sqrt(trading_days))
        else:
            total_return = 0.0
            annual_return = 0.0
            annual_vol = 0.0

        extended["annual_return"] = annual_return
        extended["annual_volatility"] = annual_vol

        # Sharpe
        extended["sharpe"] = (annual_return - risk_free) / annual_vol if annual_vol > 0 else 0.0

        # Sortino
        extended["sortino"] = calculate_sortino(port_returns, annual_return, trading_days, risk_free)

        # Max Drawdown
        extended["max_drawdown"] = calculate_max_drawdown(port_values)

        # Calmar
        extended["calmar"] = annual_return / extended["max_drawdown"] if extended["max_drawdown"] > 0 else 0.0

        # Beta
        aligned_port = []
        aligned_bench = []
        for i, (p, b) in enumerate(zip(port_returns, bench_returns)):
            if not (np.isnan(p) or np.isnan(b)):
                aligned_port.append(p)
                aligned_bench.append(b)

        extended["beta"] = calculate_beta(aligned_port, aligned_bench)

        # Correlation
        if len(aligned_port) > 1:
            extended["correlation_vs_benchmark"] = float(np.corrcoef(aligned_port, aligned_bench)[0, 1])
        else:
            extended["correlation_vs_benchmark"] = None

        # TWR (using ledger flows if available)
        flows = {}
        if ledger_csv_path and os.path.exists(ledger_csv_path):
            try:
                ledger_df = pd.read_csv(ledger_csv_path)
                date_col = "trade_date" if "trade_date" in ledger_df.columns else "date"
                side_col = "side" if "side" in ledger_df.columns else "Side"
                total_col = "total_cost" if "total_cost" in ledger_df.columns else "gross_value"
                for _, row in ledger_df.iterrows():
                    d = str(row.get(date_col, "")).strip()
                    side = str(row.get(side_col, "")).upper()
                    total = _safe_float(row.get(total_col))
                    if d:
                        flow = total if side in ("BUY", "C", "COMPRA") else -total
                        flows[d] = flows.get(d, 0.0) + flow
            except Exception as e:
                logger.warning(f"Could not parse ledger flows for TWR: {e}")

        date_strs = [str(d.date()) if hasattr(d, 'date') else str(d) for d in dates]
        twr_returns = calculate_twr(port_values, date_strs, flows)
        if twr_returns:
            twr_total = 1.0
            for r in twr_returns:
                twr_total *= (1 + _safe_float(r.get("value"), 0.0))
            extended["twr_total_return"] = twr_total - 1.0
        else:
            extended["twr_total_return"] = total_return

        # Concentration
        weights_series = pd.Series(portfolio)
        extended["hhi"] = float(sum(w ** 2 for w in weights_series))
        sorted_w = sorted(weights_series.values, reverse=True)
        extended["top3_concentration"] = float(sum(sorted_w[:3])) if len(sorted_w) >= 3 else float(sum(sorted_w))
        extended["top5_concentration"] = float(sum(sorted_w[:5])) if len(sorted_w) >= 5 else float(sum(sorted_w))
        extended["n_assets"] = len(portfolio)

        # Performance windows
        bench_returns_with_dates = []
        for i in range(1, len(bench_returns)):
            if i < len(date_strs):
                bench_returns_with_dates.append({"date": date_strs[i], "value": bench_returns[i] if i < len(bench_returns) else 0.0})

        if date_strs and twr_returns:
            extended["performance_windows"] = calculate_performance_windows(
                twr_returns, bench_returns_with_dates, date_strs[-1]
            )
        else:
            extended["performance_windows"] = {}

        # Per-asset attribution
        extended["asset_attribution"] = calculate_asset_attribution(
            portfolio_daily_return, stock_returns, portfolio, dates
        )

    except Exception as e:
        logger.error(f"Error calculating extended diagnostics: {e}", exc_info=True)

    return extended


# ----------------------------------------------------------- #
#                     Main Function                           #
# ----------------------------------------------------------- #

def main():
    """Main execution function for the Analysis script."""
    overall_start_time = time.time()
    script_dir = os.path.dirname(os.path.abspath(__file__))

    # --- Parameter Setup ---
    expected_params = {
        # From paths.txt
        "FINDB_FILE": str,
        "WEB_ACCESSIBLE_DATA_PATH": str,
        "FINANCIALS_DB_FILE": str,
        # From portpar.txt
        "PORTFOLIO_RESULTS_DB_FILE": str,
        "SCORED_STOCKS_DB_FILE": str,
        "initial_investment": float,
        # From anapar.txt
        "OUTPUT_CSV": str,
        "BENCHMARK_TICKERS": str,
        "ANALYSIS_LOG_FILE": str,
        "ANALYSIS_PERFORMANCE_FILE": str,
    }

    try:
        paths_file = os.path.join(script_dir, '..', 'parameters', 'paths.txt')
        portpar_file = os.path.join(script_dir, '..', 'parameters', 'portpar.txt')
        anapar_file = os.path.join(script_dir, '..', 'parameters', 'anapar.txt')

        params = load_parameters_from_file(
            filepaths=[paths_file, portpar_file, anapar_file],
            expected_parameters=expected_params
        )
    except (FileNotFoundError, Exception) as e:
        print(f"CRITICAL: Could not load parameters: {e}")
        sys.exit(1)

    # --- Setup Logger ---
    logger = setup_logger(
        "AnalysisRunner",
        log_file=params.get("ANALYSIS_LOG_FILE"),
        web_log_file=None,
        level=logging.INFO
    )

    perf_data = initialize_performance_data(ANALYSIS_PY_VERSION, "analysis")
    logger.info(f"Starting A4_Analysis.py v{ANALYSIS_PY_VERSION}")

    try:
        # --- Load Data ---
        data_load_start = time.time()

        portfolio, run_id, portfolios = load_latest_portfolio(
            params.get("PORTFOLIO_RESULTS_DB_FILE"), logger
        )

        stock_df = pd.read_csv(params.get("FINDB_FILE"), parse_dates=['Date'])
        stock_prices = stock_df.pivot(index='Date', columns='Stock', values='Close')

        financials_path = params.get("FINANCIALS_DB_FILE")
        if financials_path and os.path.exists(financials_path):
            financials_df = pd.read_csv(financials_path).set_index('Stock')
        else:
            financials_df = pd.DataFrame()
            logger.warning("FinancialsDB not found, some diagnostics will be unavailable")

        perf_data["data_load_duration_s"] = time.time() - data_load_start

        # --- Calculate Portfolio Values ---
        initial_value = params.get("initial_investment", 1000.0)
        portfolio_real_value, portfolio_daily_return, stock_returns, portfolio_prices = \
            calculate_portfolio_value(stock_prices, portfolio, initial_value)

        # --- Load Benchmarks ---
        benchmark_tickers = [t.strip() for t in params.get("BENCHMARK_TICKERS", "").split(',') if t.strip()]
        if len(benchmark_tickers) < 1:
            raise ValueError("At least one benchmark ticker must be specified in BENCHMARK_TICKERS.")
        bench1 = benchmark_tickers[0]
        bench2 = benchmark_tickers[1] if len(benchmark_tickers) > 1 else None

        bench1_prices, bench2_prices = calculate_benchmark_values(stock_prices, bench1, bench2, logger)

        # --- Align Dates ---
        portfolio_first = portfolio_real_value.first_valid_index()
        bench1_first = bench1_prices.first_valid_index()
        date_candidates = [bench1_first, portfolio_first]
        if bench2_prices is not None:
            bench2_first = bench2_prices.first_valid_index()
            date_candidates.append(bench2_first)
        start_date = max(d for d in date_candidates if d is not None)

        bench1_prices = bench1_prices.loc[start_date:]
        if bench2_prices is not None:
            bench2_prices = bench2_prices.loc[start_date:]
        portfolio_real_value = portfolio_real_value.loc[start_date:]
        portfolio_daily_return = portfolio_daily_return.loc[start_date:]
        portfolio_prices = portfolio_prices.loc[start_date:]
        stock_returns = stock_returns.loc[start_date:]
        dates = portfolio_real_value.index

        bench1_daily_return = bench1_prices.pct_change(fill_method=None)
        if bench2_prices is not None:
            bench2_daily_return = bench2_prices.pct_change(fill_method=None)
        else:
            bench2_daily_return = pd.Series(0.0, index=dates)
        portfolio_daily_return.iloc[0] = 0.0
        bench1_daily_return.iloc[0] = 0.0
        if bench2_prices is not None:
            bench2_daily_return.iloc[0] = 0.0

        # --- Accumulated Returns ---
        portfolio_accum_return = 1000 * (1 + portfolio_daily_return).cumprod()
        bench1_accum_return = 1000 * (1 + bench1_daily_return).cumprod()
        if bench2_prices is not None:
            bench2_accum_return = 1000 * (1 + bench2_daily_return).cumprod()
        else:
            bench2_accum_return = pd.Series(1000.0, index=dates)

        # --- Portfolio Composition ---
        portfolio_compositions = []
        for date in dates:
            comp = {}
            for stock in portfolio.keys():
                val = portfolio_prices.at[date, stock] if (date in portfolio_prices.index and stock in portfolio_prices.columns) else None
                comp[stock] = {
                    "weight": portfolio[stock],
                    "value": float(val) if pd.notna(val) else None
                }
            portfolio_compositions.append(json.dumps(comp))

        # --- Brinson Attribution ---
        attribution_results = calculate_brinson_attribution(
            portfolio, portfolio_daily_return, stock_returns, bench1_daily_return,
            params.get("SCORED_STOCKS_DB_FILE"), dates, stock_prices, bench1, bench2, logger
        )

        # --- Build Output DataFrame ---
        output = pd.DataFrame({
            'run_id': run_id,
            'date': dates,
            'portfolio_real_value': portfolio_real_value.values,
            'benchmark1_name': bench1,
            'benchmark1_real_value': bench1_prices.values,
            'benchmark2_name': bench2 if bench2 else '',
            'benchmark2_real_value': bench2_prices.values if bench2_prices is not None else None,
            'portfolio_daily_return': portfolio_daily_return.values,
            'benchmark1_daily_return': bench1_daily_return.values,
            'benchmark2_daily_return': bench2_daily_return.values,
            'portfolio_accum_return': portfolio_accum_return.values,
            'benchmark1_accum_return': bench1_accum_return.values,
            'benchmark2_accum_return': bench2_accum_return.values,
            'portfolio_composition': portfolio_compositions
        })

        # --- Calculate Diagnostics ---
        diagnostics = calculate_diagnostics(
            portfolio, portfolios, stock_df, financials_df,
            portfolio_real_value, bench1_prices, logger
        )

        # --- Calculate Extended Diagnostics (TWR, Sortino, Beta, MaxDD, etc.) ---
        project_root = os.path.abspath(os.path.join(script_dir, '..'))
        ledger_csv_path = os.path.join(project_root, 'data', 'ledger.csv')
        portfolio_history_path = os.path.join(project_root, 'data', 'portfolio_history.json')

        extended = calculate_extended_diagnostics(
            portfolio, portfolio_daily_return, portfolio_real_value,
            bench1_daily_return, bench1_prices, stock_returns, dates,
            ledger_csv_path, portfolio_history_path, logger,
        )

        # Merge extended into diagnostics
        diagnostics.update({k: v for k, v in extended.items()
                           if k not in ("performance_windows", "asset_attribution")})

        # --- Save Results ---
        results_save_start = time.time()
        results_dir = os.path.join(project_root, 'data', 'results')
        os.makedirs(results_dir, exist_ok=True)
        run_timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')

        # Save main timeseries CSV to data/results/
        output_csv = params.get("OUTPUT_CSV")
        if output_csv:
            os.makedirs(os.path.dirname(output_csv), exist_ok=True)
            output.to_csv(output_csv, index=False)
            logger.info(f"Saved timeseries to {output_csv}")

        # Append diagnostics to history CSV with run_id
        # (snapshot JSON is derived by D_Publish from this history CSV)
        diag_history_path = os.path.join(results_dir, 'portfolio_diagnostics_history.csv')
        diag_row = {
            'run_id': run_id,
            'run_timestamp': run_timestamp,
            'momentum_signal_strength': diagnostics.get('momentum_signal_strength'),
            'forward_pe_implied_upside': diagnostics.get('forward_pe_implied_upside'),
            'weighted_dividend_yield': diagnostics.get('weighted_dividend_yield'),
            'turnover': diagnostics.get('turnover'),
            'liquidity_score': diagnostics.get('liquidity_score'),
            'tracking_error': diagnostics.get('tracking_error'),
            'information_ratio': diagnostics.get('information_ratio'),
            'benchmark_annual_return': diagnostics.get('benchmark_annual_return'),
            'twr_total_return': diagnostics.get('twr_total_return'),
            'annual_return': diagnostics.get('annual_return'),
            'annual_volatility': diagnostics.get('annual_volatility'),
            'sharpe': diagnostics.get('sharpe'),
            'sortino': diagnostics.get('sortino'),
            'max_drawdown': diagnostics.get('max_drawdown'),
            'calmar': diagnostics.get('calmar'),
            'beta': diagnostics.get('beta'),
            'correlation_vs_benchmark': diagnostics.get('correlation_vs_benchmark'),
            'hhi': diagnostics.get('hhi'),
            'top3_concentration': diagnostics.get('top3_concentration'),
            'top5_concentration': diagnostics.get('top5_concentration'),
            'n_assets': diagnostics.get('n_assets'),
        }
        diag_df = pd.DataFrame([diag_row])
        diag_df.to_csv(diag_history_path, mode='a',
                       header=not os.path.exists(diag_history_path) or os.path.getsize(diag_history_path) == 0,
                       index=False)
        logger.info(f"Appended diagnostics to {diag_history_path}")

        # Save attribution to history CSV
        # (snapshot JSON is derived by D_Publish from this history CSV)
        if attribution_results:

            # Append Brinson attribution to history CSV
            attr_history_path = os.path.join(results_dir, 'performance_attribution_history.csv')
            attr_row = {
                'run_id': run_id,
                'run_timestamp': run_timestamp,
                'allocation_effect': attribution_results.get('allocation_effect'),
                'selection_effect': attribution_results.get('selection_effect'),
                'interaction_effect': attribution_results.get('interaction_effect'),
                'total_active_return': attribution_results.get('total_active_return'),
                'residual': attribution_results.get('residual'),
            }
            attr_df = pd.DataFrame([attr_row])
            attr_df.to_csv(attr_history_path, mode='a',
                          header=not os.path.exists(attr_history_path) or os.path.getsize(attr_history_path) == 0,
                          index=False)
            logger.info(f"Appended attribution to {attr_history_path}")

        # Append per-asset attribution to history CSV
        asset_attr = extended.get("asset_attribution", [])
        if asset_attr:
            asset_attr_path = os.path.join(results_dir, 'asset_attribution_history.csv')
            for a in asset_attr:
                a['run_id'] = run_id
                a['run_timestamp'] = run_timestamp
            asset_df = pd.DataFrame(asset_attr)
            cols_order = ['run_id', 'run_timestamp', 'symbol', 'avg_weight',
                         'total_contribution', 'volatility', 'beta', 'realized_return', 'observations']
            # Add missing columns with None
            for c in cols_order:
                if c not in asset_df.columns:
                    asset_df[c] = None
            asset_df = asset_df[cols_order]
            asset_df.to_csv(asset_attr_path, mode='a',
                           header=not os.path.exists(asset_attr_path) or os.path.getsize(asset_attr_path) == 0,
                           index=False)
            logger.info(f"Appended {len(asset_attr)} asset attributions to {asset_attr_path}")

        # Append performance windows to history CSV
        perf_windows = extended.get("performance_windows", {})
        if perf_windows:
            perf_win_path = os.path.join(results_dir, 'performance_windows_history.csv')
            win_row = {
                'run_id': run_id,
                'run_timestamp': run_timestamp,
                'benchmark_ticker': bench1,
            }
            for key in ["ytd", "3m", "6m", "12m", "24m"]:
                window_data = perf_windows.get(key.upper(), {})
                win_row[f'perf_{key}_portfolio'] = window_data.get('portfolio')
                win_row[f'perf_{key}_benchmark'] = window_data.get('benchmark')
            win_df = pd.DataFrame([win_row])
            win_df.to_csv(perf_win_path, mode='a',
                         header=not os.path.exists(perf_win_path) or os.path.getsize(perf_win_path) == 0,
                         index=False)
            logger.info(f"Appended performance windows to {perf_win_path}")


        perf_data["results_save_duration_s"] = time.time() - results_save_start

    except Exception as e:
        logger.critical(f"An unhandled exception occurred: {e}", exc_info=True)
        raise

    finally:
        perf_data["overall_script_duration_s"] = time.time() - overall_start_time
        log_performance_data(perf_data, params, logger, "ANALYSIS_PERFORMANCE_FILE")
        logger.info(f"Analysis completed in {perf_data['overall_script_duration_s']:.2f} seconds")


if __name__ == "__main__":
    main()
