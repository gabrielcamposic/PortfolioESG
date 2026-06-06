#!/usr/bin/env python3
"""
C_OptimizedPortfolio.py

Combines the ideal portfolio from A_Portfolio with current holdings from B_Ledger
to generate an optimized transition recommendation that maximizes return while
considering transaction costs.

Usage:
    python3 engines/C_OptimizedPortfolio.py

Outputs:
    - data/results/optimized_portfolio_history.jsonl (histórico de decisões)
    - html/data/optimized_recommendation.json (última recomendação)
"""

# --- Script Version ---
OPTIMIZED_PORTFOLIO_VERSION = "1.1.0"

# ----------------------------------------------------------- #
#                           Libraries                         #
# ----------------------------------------------------------- #
import pandas as pd
import os
import sys
import json
import logging
import math
import shutil
from datetime import datetime, timedelta
from typing import Dict, Any, List, Tuple, Optional

# --- Import Shared Utilities ---
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from shared_tools.shared_utils import (
    setup_logger,
    load_parameters_from_file,
)
from shared_tools.market_regime import compute_market_regime
from shared_tools.target_quality import (
    build_related_target_context,
    calculate_adjusted_return,
    evaluate_target_quality,
)

# ----------------------------------------------------------- #
#                        Configuration                        #
# ----------------------------------------------------------- #

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PARAMS_FILE = os.path.join(ROOT, 'parameters', 'optpar.txt')
PATHS_FILE = os.path.join(ROOT, 'parameters', 'paths.txt')

# Data files
LEDGER_CSV = os.path.join(ROOT, 'data', 'ledger.csv')
LEDGER_POSITIONS_JSON = os.path.join(ROOT, 'data', 'ledger_positions.json')
LATEST_RUN_JSON = os.path.join(ROOT, 'data', 'results', 'latest_run_summary.json')
PORTFOLIO_RESULTS_DB = os.path.join(ROOT, 'data', 'results', 'portfolio_results_db.csv')
WEB_DATA_PATH = os.path.join(ROOT, 'html', 'data')
FINDATA_PATH = os.path.join(ROOT, 'data', 'findata')  # Legacy - kept for backward compatibility
FINDB_PATH = os.path.join(ROOT, 'data', 'findb')
STOCK_DATA_DB = os.path.join(FINDB_PATH, 'StockDataDB.csv')
FINANCIALS_DB = os.path.join(FINDB_PATH, 'FinancialsDB.csv')
TICKERS_FILE = os.path.join(ROOT, 'parameters', 'tickers.txt')

# Global caches for database data (loaded once)
_STOCK_PRICES_CACHE = None
_FINANCIALS_CACHE = None


def _load_stock_prices_db(logger: logging.Logger):
    """Load stock prices from StockDataDB.csv into memory cache"""
    global _STOCK_PRICES_CACHE

    if _STOCK_PRICES_CACHE is not None:
        return _STOCK_PRICES_CACHE

    _STOCK_PRICES_CACHE = {}

    if not os.path.exists(STOCK_DATA_DB):
        logger.warning(f"StockDataDB not found: {STOCK_DATA_DB}")
        return _STOCK_PRICES_CACHE

    try:
        logger.info(f"Loading stock prices from {STOCK_DATA_DB}...")
        df = pd.read_csv(STOCK_DATA_DB)
        df['Date'] = pd.to_datetime(df['Date'])

        # Create a dictionary: {ticker: {date_str: close_price}}
        for _, row in df.iterrows():
            ticker = row.get('Stock', row.get('Ticker', ''))
            if not ticker:
                continue
            date_str = row['Date'].strftime('%Y-%m-%d')
            close_price = row.get('Close')

            if pd.notna(close_price):
                if ticker not in _STOCK_PRICES_CACHE:
                    _STOCK_PRICES_CACHE[ticker] = {}
                _STOCK_PRICES_CACHE[ticker][date_str] = float(close_price)

        logger.info(f"Loaded price data for {len(_STOCK_PRICES_CACHE)} tickers")
    except Exception as e:
        logger.error(f"Failed to load StockDataDB: {e}")

    return _STOCK_PRICES_CACHE


def _load_financials_db(logger: logging.Logger):
    """Load financials data from FinancialsDB.csv into memory cache"""
    global _FINANCIALS_CACHE

    if _FINANCIALS_CACHE is not None:
        return _FINANCIALS_CACHE

    _FINANCIALS_CACHE = {}

    if not os.path.exists(FINANCIALS_DB):
        logger.warning(f"FinancialsDB not found: {FINANCIALS_DB}")
        return _FINANCIALS_CACHE

    try:
        logger.info(f"Loading financials from {FINANCIALS_DB}...")
        df = pd.read_csv(FINANCIALS_DB)

        # Handle different column naming conventions
        ticker_col = 'Stock' if 'Stock' in df.columns else 'Ticker'
        timestamp_col = 'LastUpdated' if 'LastUpdated' in df.columns else ('Timestamp' if 'Timestamp' in df.columns else 'Date')

        if timestamp_col in df.columns:
            df[timestamp_col] = pd.to_datetime(df[timestamp_col], errors='coerce')
            df = df.sort_values(timestamp_col, ascending=False).drop_duplicates(subset=[ticker_col], keep='first')

        for _, row in df.iterrows():
            ticker = row.get(ticker_col, '')
            if not ticker:
                continue

            target_price = row.get('targetMeanPrice') or row.get('TargetMeanPrice') or row.get('TargetPrice')
            target_source = None
            if target_price is not None and pd.notna(target_price):
                try:
                    if float(target_price) > 0:
                        target_source = 'YahooFinance'
                except (TypeError, ValueError):
                    target_source = None

            _FINANCIALS_CACHE[ticker] = {
                'current_price': row.get('currentPrice') or row.get('CurrentPrice'),
                'target_price': target_price,
                'target_price_source': target_source,
                'forward_pe': row.get('forwardPE') or row.get('ForwardPE'),
                'forward_eps': row.get('forwardEPS') or row.get('forwardEps') or row.get('ForwardEps'),
                'average_volume': row.get('averageVolume') or row.get('AverageVolume'),
                'last_updated': str(row.get(timestamp_col, '')) if timestamp_col in row else '',
            }

        logger.info(f"Loaded financials for {len(_FINANCIALS_CACHE)} tickers from FinancialsDB")

        # Also try to load target prices from scored_stocks.csv as FALLBACK
        # IMPORTANT: FinancialsDB (Yahoo Finance) is the source of truth for
        # target_price and current_price. scored_stocks.csv is only used to
        # fill gaps for tickers that don't have data in FinancialsDB.
        # Previously, scored_stocks unconditionally overwrote FinancialsDB
        # targets, causing stale target prices from old scoring runs to
        # inflate the hold_12m metric.
        scored_stocks_path = os.path.join(ROOT, 'data', 'results', 'scored_stocks.csv')
        if os.path.exists(scored_stocks_path):
            try:
                scored_df = pd.read_csv(scored_stocks_path)
                if 'run_timestamp' in scored_df.columns:
                    scored_df['run_timestamp'] = pd.to_datetime(scored_df['run_timestamp'], errors='coerce')
                    scored_df = scored_df.sort_values('run_timestamp', ascending=False).drop_duplicates(subset=['Stock'], keep='first')

                updated_count = 0
                for _, row in scored_df.iterrows():
                    stock = row.get('Stock', '')
                    if not stock:
                        continue

                    current_price = row.get('CurrentPrice')
                    target_price = row.get('TargetPrice')
                    target_source = row.get('TargetPriceSource')

                    if stock not in _FINANCIALS_CACHE:
                        _FINANCIALS_CACHE[stock] = {}

                    # Only use scored_stocks as FALLBACK — do NOT override
                    # existing FinancialsDB data (which is more recent)
                    existing = _FINANCIALS_CACHE[stock]

                    if pd.notna(current_price) and current_price > 0:
                        val = existing.get('current_price')
                        if val is None or pd.isna(val):
                            _FINANCIALS_CACHE[stock]['current_price'] = float(current_price)

                    if pd.notna(target_price) and target_price > 0:
                        val = existing.get('target_price')
                        if val is None or pd.isna(val):
                            _FINANCIALS_CACHE[stock]['target_price'] = float(target_price)
                            _FINANCIALS_CACHE[stock]['target_price_source'] = (
                                str(target_source) if pd.notna(target_source) and str(target_source).strip()
                                else 'scored_stocks'
                            )
                            updated_count += 1

                    if pd.notna(row.get('forwardPE')) and row.get('forwardPE') > 0:
                        val = existing.get('forward_pe')
                        if val is None or pd.isna(val):
                            _FINANCIALS_CACHE[stock]['forward_pe'] = float(row.get('forwardPE'))

                    if pd.notna(row.get('forwardEPS')):
                        val = existing.get('forward_eps')
                        if val is None or pd.isna(val):
                            _FINANCIALS_CACHE[stock]['forward_eps'] = float(row.get('forwardEPS'))

                    if pd.notna(row.get('Sector')):
                        _FINANCIALS_CACHE[stock]['sector'] = str(row.get('Sector'))

                    if pd.notna(row.get('TargetQualityScore')):
                        _FINANCIALS_CACHE[stock]['target_quality_score'] = float(row.get('TargetQualityScore'))
                    if pd.notna(row.get('TargetQualityBucket')):
                        _FINANCIALS_CACHE[stock]['target_quality_bucket'] = str(row.get('TargetQualityBucket'))
                    if pd.notna(row.get('TargetQualityFlags')):
                        _FINANCIALS_CACHE[stock]['target_quality_flags'] = str(row.get('TargetQualityFlags'))
                    if pd.notna(row.get('TargetQualityRelatedTicker')):
                        _FINANCIALS_CACHE[stock]['target_quality_related_ticker'] = str(row.get('TargetQualityRelatedTicker'))

                logger.info(f"Filled {updated_count} tickers with target prices from scored_stocks.csv (fallback only)")
            except Exception as e:
                logger.warning(f"Could not load scored_stocks.csv for target prices: {e}")

    except Exception as e:
        logger.error(f"Failed to load FinancialsDB: {e}")

    return _FINANCIALS_CACHE


# ----------------------------------------------------------- #
#                      Helper Functions                       #
# ----------------------------------------------------------- #

def load_parameters(logger: logging.Logger) -> Dict[str, Any]:
    """Load parameters from optpar.txt and paths.txt"""

    # Define expected parameters and their types
    expected_params = {
        'WEIGHT_EXPECTED_RETURN': float,
        'WEIGHT_SHARPE_RATIO': float,
        'WEIGHT_MOMENTUM': float,
        'MIN_EXCESS_RETURN_THRESHOLD': float,
        'TRANSACTION_COST_MODE': str,
        'TRANSACTION_COST_MIN_TRANSACTIONS': int,
        'TRANSACTION_COST_MIN_MONTHS': int,
        'TRANSACTION_COST_FIXED_PCT': float,
        'EXPECTED_RETURN_WINDOW_DAYS': int,
        'NUM_CANDIDATE_PORTFOLIOS': int,
        'MIN_OVERLAP_THRESHOLD': float,
        'MAX_TRANSACTIONS': int,
        'OPTIMIZED_RESULTS_FILE': str,
        'OPTIMIZED_LATEST_JSON': str,
        'OPTIMIZED_LOG_FILE': str,
        'TARGET_EXTREME_UPSIDE_PCT': float,
        'TARGET_REJECT_UPSIDE_PCT': float,
        'TARGET_LOW_PRICE': float,
        'TARGET_STALE_DAYS': int,
        'TARGET_MAX_FALLBACK_QUALITY': float,
        'TARGET_LOW_LIQUIDITY_AVG_VOLUME': float,
        'TARGET_CLASS_TARGET_TOLERANCE_PCT': float,
        'TARGET_CLASS_PRICE_RATIO': float,
        'TARGET_DISTRESSED_RETURN_PCT': float,
        'RETURN_ADJUSTMENT_CAP_PCT': float,
        'RETURN_ADJUSTMENT_FLOOR_PCT': float,
        'RETURN_ADJUSTMENT_BASE_PCT': float,
        'RETURN_ADJUSTMENT_REJECT_BASE_PCT': float,
        'RETURN_ADJUSTMENT_UNCERTAINTY_PENALTY_PCT': float,
        'REGIME_BENCHMARK_TICKER': str,
        'REGIME_LOOKBACK_3M_DAYS': int,
        'REGIME_LOOKBACK_6M_DAYS': int,
        'REGIME_DRAWDOWN_STRESS_PCT': float,
        'REGIME_NEGATIVE_BREADTH_PCT': float,
        'REGIME_DRAWDOWN_BREADTH_PCT': float,
        'REGIME_ASSET_DRAWDOWN_THRESHOLD_PCT': float,
        'REGIME_VOLATILITY_WATCH_PCT': float,
        'REGIME_DISPERSION_WATCH_PCT': float,
        'SHADOW_BASE_HURDLE_PCT': float,
        'SHADOW_SLIPPAGE_ESTIMATE_PCT': float,
        'SHADOW_TAX_DRAG_ESTIMATE_PCT': float,
        'SHADOW_MODEL_UNCERTAINTY_PENALTY_PCT': float,
        'SHADOW_MIN_PERSISTENCE_DAYS': int,
        'SHADOW_TURNOVER_BUDGET_PCT': float,
        'SHADOW_CONFIDENCE_FLOOR': float,
        'SHADOW_MAX_SUSPICIOUS_RETURN_CONTRIBUTION_PCT': float,
        'SHADOW_PARTIAL_REBALANCE_MIN_GAIN_PCT': float,
        'EXECUTION_ASSET_TOLERANCE_BAND_PCT': float,
        'EXECUTION_SECTOR_TOLERANCE_BAND_PCT': float,
        'EXECUTION_WEEKLY_TURNOVER_BUDGET_PCT': float,
        'EXECUTION_MONTHLY_TURNOVER_BUDGET_PCT': float,
        'EXECUTION_MIN_TRADE_VALUE_BRL': float,
        'EXECUTION_MAX_ACTIONS': int,
        'TURNOVER_PENALTY_LAMBDA': float,
        'STABLE_TURNOVER_TARGET_PCT': float,
        'STABLE_TURNOVER_EXCESS_PENALTY_LAMBDA': float,
        'STABLE_UNCERTAINTY_PENALTY_LAMBDA': float,
        'STABLE_CONCENTRATION_PENALTY_LAMBDA': float,
        'STABLE_SUSPICIOUS_RETURN_PENALTY_LAMBDA': float,
    }

    params = {}

    # Load from optpar.txt
    if os.path.exists(PARAMS_FILE):
        opt_params = load_parameters_from_file(PARAMS_FILE, expected_params, logger)
        params.update(opt_params)
        logger.info(f"Loaded parameters from {PARAMS_FILE}")
    else:
        logger.warning(f"Parameters file not found: {PARAMS_FILE}")

    # Load paths
    if os.path.exists(PATHS_FILE):
        path_params = load_parameters_from_file(PATHS_FILE, {}, logger)
        params.update(path_params)
        logger.info(f"Loaded paths from {PATHS_FILE}")

    # Set defaults
    defaults = {
        'WEIGHT_EXPECTED_RETURN': 0.4,
        'WEIGHT_SHARPE_RATIO': 0.4,
        'WEIGHT_MOMENTUM': 0.2,
        'MIN_EXCESS_RETURN_THRESHOLD': 0.5,
        'TRANSACTION_COST_MODE': 'DYNAMIC',
        'TRANSACTION_COST_MIN_TRANSACTIONS': 20,
        'TRANSACTION_COST_MIN_MONTHS': 6,
        'TRANSACTION_COST_FIXED_PCT': 0.1,
        'EXPECTED_RETURN_WINDOW_DAYS': 252,
        'NUM_CANDIDATE_PORTFOLIOS': 100,
        'TARGET_EXTREME_UPSIDE_PCT': 150.0,
        'TARGET_REJECT_UPSIDE_PCT': 300.0,
        'TARGET_LOW_PRICE': 1.0,
        'TARGET_STALE_DAYS': 45,
        'TARGET_MAX_FALLBACK_QUALITY': 0.35,
        'TARGET_LOW_LIQUIDITY_AVG_VOLUME': 100000.0,
        'TARGET_CLASS_TARGET_TOLERANCE_PCT': 15.0,
        'TARGET_CLASS_PRICE_RATIO': 3.0,
        'TARGET_DISTRESSED_RETURN_PCT': -50.0,
        'RETURN_ADJUSTMENT_CAP_PCT': 150.0,
        'RETURN_ADJUSTMENT_FLOOR_PCT': -80.0,
        'RETURN_ADJUSTMENT_BASE_PCT': 0.0,
        'RETURN_ADJUSTMENT_REJECT_BASE_PCT': 0.0,
        'RETURN_ADJUSTMENT_UNCERTAINTY_PENALTY_PCT': 0.0,
        'REGIME_BENCHMARK_TICKER': '^BVSP',
        'REGIME_LOOKBACK_3M_DAYS': 63,
        'REGIME_LOOKBACK_6M_DAYS': 126,
        'REGIME_DRAWDOWN_STRESS_PCT': 10.0,
        'REGIME_NEGATIVE_BREADTH_PCT': 60.0,
        'REGIME_DRAWDOWN_BREADTH_PCT': 45.0,
        'REGIME_ASSET_DRAWDOWN_THRESHOLD_PCT': 20.0,
        'REGIME_VOLATILITY_WATCH_PCT': 25.0,
        'REGIME_DISPERSION_WATCH_PCT': 35.0,
        'SHADOW_BASE_HURDLE_PCT': 0.5,
        'SHADOW_SLIPPAGE_ESTIMATE_PCT': 0.15,
        'SHADOW_TAX_DRAG_ESTIMATE_PCT': 0.0,
        'SHADOW_MODEL_UNCERTAINTY_PENALTY_PCT': 0.5,
        'SHADOW_MIN_PERSISTENCE_DAYS': 2,
        'SHADOW_TURNOVER_BUDGET_PCT': 35.0,
        'SHADOW_CONFIDENCE_FLOOR': 0.60,
        'SHADOW_MAX_SUSPICIOUS_RETURN_CONTRIBUTION_PCT': 35.0,
        'SHADOW_PARTIAL_REBALANCE_MIN_GAIN_PCT': 1.0,
        'EXECUTION_ASSET_TOLERANCE_BAND_PCT': 2.0,
        'EXECUTION_SECTOR_TOLERANCE_BAND_PCT': 5.0,
        'EXECUTION_WEEKLY_TURNOVER_BUDGET_PCT': 12.0,
        'EXECUTION_MONTHLY_TURNOVER_BUDGET_PCT': 35.0,
        'EXECUTION_MIN_TRADE_VALUE_BRL': 25.0,
        'EXECUTION_MAX_ACTIONS': 6,
        'TURNOVER_PENALTY_LAMBDA': 0.05,
        'STABLE_TURNOVER_TARGET_PCT': 12.0,
        'STABLE_TURNOVER_EXCESS_PENALTY_LAMBDA': 0.10,
        'STABLE_UNCERTAINTY_PENALTY_LAMBDA': 0.03,
        'STABLE_CONCENTRATION_PENALTY_LAMBDA': 0.02,
        'STABLE_SUSPICIOUS_RETURN_PENALTY_LAMBDA': 0.03,
    }

    for key, default in defaults.items():
        if key not in params:
            params[key] = default

    return params


def load_current_holdings(logger: logging.Logger) -> pd.DataFrame:
    """Load current holdings from ledger_positions.json"""
    if not os.path.exists(LEDGER_POSITIONS_JSON):
        logger.warning(f"Ledger positions file not found: {LEDGER_POSITIONS_JSON}")
        return pd.DataFrame()

    try:
        with open(LEDGER_POSITIONS_JSON, 'r', encoding='utf-8') as f:
            data = json.load(f)

        # Handle both formats: dict with 'positions' key or direct array
        if isinstance(data, dict):
            positions = data.get('positions', [])
        elif isinstance(data, list):
            positions = data
        else:
            logger.error(f"Unexpected format in ledger positions: {type(data)}")
            return pd.DataFrame()

        # Filter only positions with net_qty > 0
        holdings = [p for p in positions if isinstance(p, dict) and p.get('net_qty', 0) > 0]

        if not holdings:
            logger.warning("No active holdings found in ledger positions")
            return pd.DataFrame()

        df = pd.DataFrame(holdings)
        logger.info(f"Loaded {len(df)} active holdings from ledger")
        return df

    except Exception as e:
        logger.error(f"Error loading holdings: {e}")
        return pd.DataFrame()


def load_ideal_portfolio(logger: logging.Logger) -> Dict[str, Any]:
    """Load the ideal portfolio from latest_run_summary.json"""
    if not os.path.exists(LATEST_RUN_JSON):
        logger.error(f"Latest run summary not found: {LATEST_RUN_JSON}")
        return {}

    try:
        with open(LATEST_RUN_JSON, 'r', encoding='utf-8') as f:
            data = json.load(f)

        portfolio = data.get('best_portfolio_details', {})
        stocks = portfolio.get('stocks', [])
        weights = portfolio.get('weights', [])

        if not stocks or not weights:
            logger.error("Ideal portfolio has no stocks or weights")
            return {}

        logger.info(f"Loaded ideal portfolio with {len(stocks)} stocks")
        return {
            'stocks': stocks,
            'weights': dict(zip(stocks, weights)),
            'sharpe_ratio': portfolio.get('sharpe_forward', portfolio.get('sharpe_ratio', 0)),
            'expected_return': portfolio.get('expected_return_annual_pct', 0),
            'volatility': portfolio.get('expected_volatility_annual_pct', 0),
            'run_id': data.get('last_updated_run_id', ''),
            'timestamp': data.get('last_updated_timestamp', ''),
        }

    except Exception as e:
        logger.error(f"Error loading ideal portfolio: {e}")
        return {}


def load_ticker_mapping(logger: logging.Logger) -> Dict[str, str]:
    """Load mapping of broker names to symbols from tickers.txt"""
    mapping = {}

    if not os.path.exists(TICKERS_FILE):
        logger.warning(f"Tickers file not found: {TICKERS_FILE}")
        return mapping

    try:
        with open(TICKERS_FILE, 'r', encoding='utf-8') as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith('#'):
                    continue
                parts = line.split(',')
                if len(parts) >= 2:
                    symbol = parts[0].strip()
                    name = parts[1].strip() if len(parts) > 1 else ''
                    broker_name = parts[4].strip() if len(parts) > 4 else ''

                    mapping[symbol] = symbol
                    if name:
                        mapping[name.upper()] = symbol
                    if broker_name:
                        mapping[broker_name.upper()] = symbol

        logger.info(f"Loaded {len(mapping)} ticker mappings")
        return mapping

    except Exception as e:
        logger.error(f"Error loading ticker mapping: {e}")
        return mapping


def normalize_symbol(symbol: str, ticker_mapping: Dict[str, str]) -> str:
    """Normalize a symbol using the ticker mapping"""
    if not symbol:
        return ''

    symbol_clean = symbol.strip().upper()

    # Direct match
    if symbol_clean in ticker_mapping:
        return ticker_mapping[symbol_clean]

    # Try to find partial match
    for key, value in ticker_mapping.items():
        if key.upper() in symbol_clean or symbol_clean in key.upper():
            return value

    # Return with .SA suffix if not present
    if not symbol_clean.endswith('.SA'):
        return symbol_clean + '.SA'

    return symbol_clean


def calculate_dynamic_transaction_cost(logger: logging.Logger, params: Dict) -> float:
    """
    Calculate average transaction cost based on historical ledger data.
    Uses the last 20 transactions OR last 6 months, whichever is larger.
    """
    if not os.path.exists(LEDGER_CSV):
        logger.warning(f"Ledger CSV not found: {LEDGER_CSV}")
        return float(params.get('TRANSACTION_COST_FIXED_PCT', 0.1))

    try:
        df = pd.read_csv(LEDGER_CSV)

        if df.empty:
            logger.warning("Ledger is empty, using fixed transaction cost")
            return float(params.get('TRANSACTION_COST_FIXED_PCT', 0.1))

        # Parse dates
        date_col = 'trade_date' if 'trade_date' in df.columns else 'date'
        if date_col in df.columns:
            df['date_parsed'] = pd.to_datetime(df[date_col], errors='coerce')
        else:
            df['date_parsed'] = pd.Timestamp.now()

        # Get parameters
        min_transactions = int(params.get('TRANSACTION_COST_MIN_TRANSACTIONS', 20))
        min_months = int(params.get('TRANSACTION_COST_MIN_MONTHS', 6))

        # Filter by date (last N months)
        cutoff_date = datetime.now() - timedelta(days=min_months * 30)
        recent_by_date = df[df['date_parsed'] >= cutoff_date]

        # Filter by count (last N transactions)
        recent_by_count = df.tail(min_transactions)

        # Use the larger dataset
        recent = recent_by_date if len(recent_by_date) > len(recent_by_count) else recent_by_count

        if recent.empty:
            logger.warning("No recent transactions found, using fixed cost")
            return float(params.get('TRANSACTION_COST_FIXED_PCT', 0.1))

        # Calculate cost as (fees / gross_value) * 100
        fees_col = 'allocated_fees' if 'allocated_fees' in recent.columns else 'fees'
        value_col = 'gross_value' if 'gross_value' in recent.columns else 'total_cost'

        total_fees = recent[fees_col].sum() if fees_col in recent.columns else 0
        total_value = recent[value_col].sum() if value_col in recent.columns else 1

        if total_value == 0:
            total_value = 1

        avg_cost_pct = (total_fees / total_value) * 100

        logger.info(f"Dynamic transaction cost: {avg_cost_pct:.4f}% "
                   f"(from {len(recent)} transactions, fees={total_fees:.2f}, value={total_value:.2f})")

        return avg_cost_pct

    except Exception as e:
        logger.error(f"Error calculating dynamic transaction cost: {e}")
        return float(params.get('TRANSACTION_COST_FIXED_PCT', 0.1))


def get_current_price(symbol: str, logger: logging.Logger) -> Optional[float]:
    """Get current price for a symbol.

    Priority: StockDataDB (last close) → FinancialsDB (currentPrice).
    Using StockDataDB first ensures consistency with ledger_positions.json,
    which also derives its prices from StockDataDB.
    """
    symbol_clean = symbol.replace('.SA', '') + '.SA' if '.SA' not in symbol else symbol

    # First try StockDataDB (most recent close price) — same source as ledger
    prices_db = _load_stock_prices_db(logger)
    if symbol_clean in prices_db:
        ticker_prices = prices_db[symbol_clean]
        if ticker_prices:
            sorted_dates = sorted(ticker_prices.keys(), reverse=True)
            if sorted_dates:
                return ticker_prices[sorted_dates[0]]

    # Fall back to FinancialsDB currentPrice
    financials = _load_financials_db(logger)
    if symbol_clean in financials:
        current = financials[symbol_clean].get('current_price')
        if current and pd.notna(current):
            return float(current)

    return None


def get_target_price(symbol: str, logger: logging.Logger) -> Optional[float]:
    """Get target price for a symbol from FinancialsDB"""
    symbol_clean = symbol.replace('.SA', '') + '.SA' if '.SA' not in symbol else symbol

    financials = _load_financials_db(logger)
    if symbol_clean in financials:
        target = financials[symbol_clean].get('target_price')
        if target and pd.notna(target):
            return float(target)

    return None


def get_target_metadata(symbol: str, logger: logging.Logger) -> Dict[str, Any]:
    """Get target price metadata used for diagnostics only."""
    symbol_clean = symbol.replace('.SA', '') + '.SA' if '.SA' not in symbol else symbol
    financials = _load_financials_db(logger)
    info = financials.get(symbol_clean, {})

    target = info.get('target_price')
    target_price = None
    if target is not None and pd.notna(target):
        try:
            target_price = float(target)
        except (TypeError, ValueError):
            target_price = None

    source = info.get('target_price_source')
    if target_price is not None and target_price > 0 and not source:
        source = 'Unknown'

    return {
        'target_price': target_price if target_price and target_price > 0 else None,
        'target_source': source or 'None',
        'forward_pe': info.get('forward_pe'),
        'forward_eps': info.get('forward_eps'),
        'sector': info.get('sector'),
        'average_volume': info.get('average_volume'),
        'last_updated': info.get('last_updated'),
        'target_quality_score': info.get('target_quality_score'),
        'target_quality_bucket': info.get('target_quality_bucket'),
        'target_quality_flags': info.get('target_quality_flags'),
        'target_quality_related_ticker': info.get('target_quality_related_ticker'),
    }


def get_historical_return(symbol: str, days: int, logger: logging.Logger) -> Optional[float]:
    """Get historical return for a symbol over the last N days using StockDataDB"""
    symbol_clean = symbol.replace('.SA', '') + '.SA' if '.SA' not in symbol else symbol

    prices_db = _load_stock_prices_db(logger)
    if symbol_clean not in prices_db:
        return None

    ticker_prices = prices_db[symbol_clean]
    if len(ticker_prices) < 2:
        return None

    try:
        # Sort dates
        sorted_dates = sorted(ticker_prices.keys(), reverse=True)

        # Get current price (most recent)
        current_price = ticker_prices[sorted_dates[0]]

        # Find price from approximately N days ago
        target_date = (datetime.strptime(sorted_dates[0], '%Y-%m-%d') - timedelta(days=days)).strftime('%Y-%m-%d')

        # Find the closest date to target
        past_price = None
        for date_str in sorted_dates:
            if date_str <= target_date:
                past_price = ticker_prices[date_str]
                break

        if past_price is None and len(sorted_dates) > 1:
            # Use the oldest available price
            past_price = ticker_prices[sorted_dates[-1]]

        if past_price and past_price > 0:
            return (current_price - past_price) / past_price

        return None

    except Exception as e:
        logger.debug(f"Could not get historical return for {symbol}: {e}")
        return None


def calculate_holdings_metrics(
    holdings: pd.DataFrame,
    ticker_mapping: Dict[str, str],
    params: Dict,
    logger: logging.Logger
) -> Dict[str, Any]:
    """Calculate expected return and other metrics for current holdings"""

    if holdings.empty:
        return {
            'expected_return': 0,
            'total_value': 0,
            'total_invested': 0,
            'stocks': [],
            'weights': {},
            'current_prices': {},
            'target_prices': {},
        }

    total_invested = 0
    total_current_value = 0
    stock_values = {}
    current_prices = {}
    target_prices = {}
    historical_returns = {}

    window_days = int(params.get('EXPECTED_RETURN_WINDOW_DAYS', 252))

    for _, row in holdings.iterrows():
        # Prefer 'symbol' (Yahoo format like PETR3.SA) over 'ticker' (broker name)
        symbol_raw = row.get('symbol') or row.get('ticker', '')
        symbol = normalize_symbol(symbol_raw, ticker_mapping)
        net_qty = float(row.get('net_qty', 0))
        net_invested = float(row.get('net_invested', 0))

        if net_qty <= 0:
            continue

        # Get current price
        current_price = get_current_price(symbol, logger)
        if current_price is None:
            # Use average cost as fallback
            current_price = net_invested / net_qty if net_qty > 0 else 0

        current_prices[symbol] = current_price

        # Get target price
        target_price = get_target_price(symbol, logger)
        if target_price:
            target_prices[symbol] = target_price

        # Get historical return as fallback
        hist_return = get_historical_return(symbol, window_days, logger)
        if hist_return is not None:
            historical_returns[symbol] = hist_return

        current_value = net_qty * current_price
        stock_values[symbol] = current_value
        total_invested += net_invested
        total_current_value += current_value

    # Calculate weights
    weights = {}
    for symbol, value in stock_values.items():
        weights[symbol] = value / total_current_value if total_current_value > 0 else 0

    # Calculate expected return based on target prices (or historical returns as fallback)
    expected_return = 0
    stocks_with_return = 0

    for symbol, weight in weights.items():
        current = current_prices.get(symbol, 0)

        # Prefer target price, fall back to historical return
        if symbol in target_prices:
            target = target_prices[symbol]
            if current > 0 and target > 0:
                stock_return = (target - current) / current
                expected_return += weight * stock_return
                stocks_with_return += 1
        elif symbol in historical_returns:
            # Use historical return as proxy for expected return
            expected_return += weight * historical_returns[symbol]
            stocks_with_return += 1

    expected_return *= 100  # Convert to percentage

    logger.info(f"Holdings expected return calculation: {stocks_with_return}/{len(weights)} stocks with return data")

    return {
        'expected_return': expected_return,
        'total_value': total_current_value,
        'total_invested': total_invested,
        'stocks': list(weights.keys()),
        'weights': weights,
        'current_prices': current_prices,
        'target_prices': target_prices,
        'historical_returns': historical_returns,
    }


def calculate_ideal_expected_return(
    ideal: Dict[str, Any],
    logger: logging.Logger
) -> float:
    """Calculate expected return for ideal portfolio based on target prices"""
    stocks = ideal.get('stocks', [])
    weights = ideal.get('weights', {})

    if not stocks:
        return ideal.get('expected_return', 0)

    expected_return = 0
    valid_stocks = 0

    for stock in stocks:
        weight = weights.get(stock, 0)
        current = get_current_price(stock, logger)
        target = get_target_price(stock, logger)

        if current and target and current > 0:
            stock_return = (target - current) / current
            expected_return += weight * stock_return
            valid_stocks += 1

    if valid_stocks == 0:
        # Fall back to the stored expected return
        return ideal.get('expected_return', 0)

    return expected_return * 100  # Convert to percentage


def _load_avg_purchase_prices(logger: logging.Logger) -> Dict[str, float]:
    """Load weighted-average purchase price per symbol from ledger_positions.json.

    avg_purchase_price = net_invested / net_qty
    """
    avg_prices: Dict[str, float] = {}
    if not os.path.exists(LEDGER_POSITIONS_JSON):
        return avg_prices
    try:
        with open(LEDGER_POSITIONS_JSON, 'r', encoding='utf-8') as f:
            data = json.load(f)
        positions = data.get('positions', []) if isinstance(data, dict) else data
        for pos in positions:
            symbol = pos.get('symbol') or pos.get('resolved_symbol', '')
            qty = float(pos.get('net_qty', 0))
            invested = float(pos.get('net_invested', 0))
            if symbol and qty > 0 and invested > 0:
                avg_prices[symbol] = round(invested / qty, 2)
        logger.info(f"Loaded avg purchase prices for {len(avg_prices)} positions")
    except Exception as e:
        logger.warning(f"Could not load avg purchase prices: {e}")
    return avg_prices


def _load_current_share_quantities(logger: logging.Logger) -> Dict[str, int]:
    """Load current share quantities per symbol from ledger_positions.json."""
    qty_map: Dict[str, int] = {}
    if not os.path.exists(LEDGER_POSITIONS_JSON):
        return qty_map
    try:
        with open(LEDGER_POSITIONS_JSON, 'r', encoding='utf-8') as f:
            data = json.load(f)
        positions = data.get('positions', []) if isinstance(data, dict) else data
        for pos in positions:
            symbol = pos.get('symbol') or pos.get('resolved_symbol', '')
            net_qty = pos.get('net_qty', 0)
            if symbol and net_qty > 0:
                qty_map[symbol] = int(net_qty)
    except Exception as e:
        logger.warning(f"Could not load current share quantities: {e}")
    return qty_map


def calculate_transition_cost(
    holdings: Dict[str, Any],
    target: Dict[str, Any],
    transaction_cost_pct: float,
    logger: logging.Logger
) -> Tuple[float, List[Dict]]:
    """
    Calculate the cost of transitioning from holdings to target portfolio.
    Returns (total_cost_pct, list_of_transactions)

    When the target portfolio has been discretized (has 'share_quantities'),
    transactions are computed as the exact integer delta between current and
    target share counts.  This guarantees that all recommended quantities are
    whole numbers consistent with B3 rules.

    Falls back to the weight-based approach when share_quantities is not yet
    available (e.g. during candidate scoring).

    Each transaction is enriched with:
      - avg_purchase_price: weighted-average purchase price from ledger
      - target_price: 12-month target price from FinancialsDB
      - shares: integer (exact delta between current and target positions)
      - signed_value: positive for SELL (cash in), negative for BUY (cash out)
    """
    holdings_weights = holdings.get('weights', {})
    target_weights = target.get('weights', {})
    holdings_value = holdings.get('total_value', 0)
    current_prices = holdings.get('current_prices', {})

    # Enrich: load avg purchase prices and target prices
    avg_purchase_prices = _load_avg_purchase_prices(logger)

    # ── Share-based path (post-discretization) ─────────────────────
    target_share_quantities = target.get('share_quantities', {})
    use_share_delta = bool(target_share_quantities)

    current_share_quantities: Dict[str, int] = {}
    if use_share_delta:
        current_share_quantities = _load_current_share_quantities(logger)

    transactions = []
    total_traded_value = 0

    # Get all unique stocks
    all_stocks = set(holdings_weights.keys()) | set(target_weights.keys())

    for stock in all_stocks:
        current_weight = holdings_weights.get(stock, 0)
        target_weight = target_weights.get(stock, 0)
        weight_diff = target_weight - current_weight

        if abs(weight_diff) < 0.001:  # Ignore tiny differences
            continue

        action = 'BUY' if weight_diff > 0 else 'SELL'

        # Resolve current price
        price = current_prices.get(stock)
        if price is None:
            price = get_current_price(stock, logger)

        # ── Compute shares ─────────────────────────────────────
        if use_share_delta:
            # Exact integer delta between target and current positions
            target_qty = target_share_quantities.get(stock, 0)
            current_qty = current_share_quantities.get(stock, 0)
            delta = target_qty - current_qty

            if delta == 0:
                continue

            shares = abs(delta)
            # Override action based on actual delta sign
            action = 'BUY' if delta > 0 else 'SELL'
        else:
            # Weight-based fallback (used during candidate scoring)
            shares = None
            if price and price > 0:
                value_change_est = abs(weight_diff) * holdings_value
                raw_shares = value_change_est / price
                if action == 'BUY':
                    shares = max(1, int(math.floor(raw_shares)))
                else:
                    shares = max(1, int(math.floor(raw_shares))) if raw_shares >= 0.5 else 1

        # Compute value from actual integer shares
        actual_value = shares * price if shares and price else abs(weight_diff) * holdings_value
        total_traded_value += actual_value

        estimated_cost = round(actual_value * transaction_cost_pct / 100, 4)

        # Resolve enrichment data
        avg_price = avg_purchase_prices.get(stock)
        tp = get_target_price(stock, logger)

        # signed_value: positive = cash in (SELL), negative = cash out (BUY)
        signed_value = actual_value if action == 'SELL' else -actual_value

        transactions.append({
            'symbol': stock,
            'action': action,
            'weight_change': weight_diff,
            'value_change': actual_value,
            'current_weight': current_weight,
            'target_weight': target_weight,
            'cost': estimated_cost,
            'current_price': round(price, 2) if price else None,
            'shares': shares,
            'avg_purchase_price': avg_price,
            'target_price': round(tp, 2) if tp else None,
            'signed_value': round(signed_value, 2),
        })

    # Total cost as percentage of portfolio
    total_cost_pct = (total_traded_value / holdings_value * transaction_cost_pct) if holdings_value > 0 else 0

    logger.info(f"Transition would trade {total_traded_value:.2f} ({total_traded_value/holdings_value*100:.1f}% of portfolio)")
    logger.info(f"Estimated transition cost: {total_cost_pct:.4f}%")

    return total_cost_pct, transactions


def generate_candidate_portfolios(
    holdings: Dict[str, Any],
    ideal: Dict[str, Any],
    num_candidates: int,
    logger: logging.Logger
) -> List[Dict[str, Any]]:
    """
    Generate candidate portfolios that are intermediate between holdings and ideal.
    Uses different blend ratios to create a range of options.
    """
    candidates = []

    holdings_weights = holdings.get('weights', {})
    ideal_weights = ideal.get('weights', {})

    # Get all stocks
    all_stocks = list(set(holdings_weights.keys()) | set(ideal_weights.keys()))

    # Generate candidates with different blend ratios
    for i in range(num_candidates + 1):
        # Blend ratio: 0 = full holdings, 1 = full ideal
        blend_ratio = i / num_candidates

        blended_weights = {}
        for stock in all_stocks:
            h_weight = holdings_weights.get(stock, 0)
            i_weight = ideal_weights.get(stock, 0)
            blended_weights[stock] = h_weight * (1 - blend_ratio) + i_weight * blend_ratio

        # Normalize weights
        total_weight = sum(blended_weights.values())
        if total_weight > 0:
            blended_weights = {k: v / total_weight for k, v in blended_weights.items()}

        # Remove zero-weight stocks
        blended_weights = {k: v for k, v in blended_weights.items() if v > 0.001}

        candidates.append({
            'blend_ratio': blend_ratio,
            'weights': blended_weights,
            'stocks': list(blended_weights.keys()),
        })

    logger.info(f"Generated {len(candidates)} candidate portfolios")
    return candidates


def score_portfolio(
    portfolio: Dict[str, Any],
    expected_return: float,
    sharpe_ratio: float,
    momentum: float,
    params: Dict
) -> float:
    """
    Calculate a composite score for a portfolio.
    Uses weighted combination of expected return, sharpe ratio, and momentum.
    """
    w_return = float(params.get('WEIGHT_EXPECTED_RETURN', 0.4))
    w_sharpe = float(params.get('WEIGHT_SHARPE_RATIO', 0.4))
    w_momentum = float(params.get('WEIGHT_MOMENTUM', 0.2))

    import math

    # Expected return: Dynamic penalization using log scale for returns > 0
    # Normalize such that 100% (1.0) expected return gives ~1.0 score (math.log1p(1.0) = 0.693)
    if expected_return is not None:
        r = expected_return / 100.0
        if r > 0:
            norm_return = math.log1p(r) / 0.693
        else:
            norm_return = r / 0.20  # -20% -> -1.0
    else:
        norm_return = 0.0

    # Sharpe ratio: Dynamic penalization using log scale
    # Normalize such that Sharpe of 3.0 gives ~1.0 score (math.log1p(3.0) = 1.386)
    if sharpe_ratio is not None:
        if sharpe_ratio > 0:
            norm_sharpe = math.log1p(sharpe_ratio) / 1.386
        else:
            norm_sharpe = sharpe_ratio
    else:
        norm_sharpe = 0.0

    # Momentum: Dynamic penalization using log scale
    # Normalize such that Momentum of 2.0 gives ~1.0 score (math.log1p(2.0) = 1.098)
    if momentum is not None:
        if momentum > 0:
            norm_momentum = math.log1p(momentum) / 1.098
        else:
            norm_momentum = momentum
    else:
        norm_momentum = 0.0

    score = w_return * norm_return + w_sharpe * norm_sharpe + w_momentum * norm_momentum
    return score


def calculate_portfolio_momentum(portfolio: Dict[str, Any], logger: logging.Logger) -> float:
    """Calculate weighted momentum for a portfolio"""
    weights = portfolio.get('weights', {})

    total_momentum = 0
    total_weight = 0

    prices_db = _load_stock_prices_db(logger)

    for stock, weight in weights.items():
        # Get 12-month return as proxy for momentum
        symbol_clean = stock.replace('.SA', '') + '.SA' if '.SA' not in stock else stock

        if symbol_clean not in prices_db:
            continue

        try:
            ticker_prices = prices_db[symbol_clean]
            sorted_dates = sorted(ticker_prices.keys(), reverse=True)

            if len(sorted_dates) < 252:
                continue

            current_price = ticker_prices[sorted_dates[0]]
            # Find price from ~252 trading days ago
            price_12m_ago = ticker_prices[sorted_dates[min(251, len(sorted_dates) - 1)]]

            if price_12m_ago > 0:
                momentum = (current_price - price_12m_ago) / price_12m_ago
                total_momentum += weight * momentum
                total_weight += weight

        except Exception:
            continue

    return total_momentum / total_weight if total_weight > 0 else 0


def _build_transaction_summary(transactions: List[Dict]) -> Dict[str, Any]:
    """Build an aggregate summary of transactions.

    Returns:
        total_buy_value:  absolute value of all BUY transactions
        total_sell_value: absolute value of all SELL transactions
        total_cost:       sum of all estimated operational costs
        projected_balance: sell_value − buy_value − costs
            > 0 → surplus cash to reinvest
            < 0 → additional cash (aporte) needed
    """
    total_buy = 0.0
    total_sell = 0.0
    total_cost = 0.0

    for tx in transactions:
        val = abs(tx.get('value_change', 0))
        cost = tx.get('cost', 0) or 0
        total_cost += cost
        if tx.get('action') == 'BUY':
            total_buy += val
        elif tx.get('action') == 'SELL':
            total_sell += val

    projected_balance = total_sell - total_buy - total_cost

    return {
        'total_buy_value': round(total_buy, 2),
        'total_sell_value': round(total_sell, 2),
        'total_cost': round(total_cost, 2),
        'projected_balance': round(projected_balance, 2),
    }


def _round_or_none(value: Any, digits: int = 2) -> Optional[float]:
    """Round finite numeric values for JSON diagnostics."""
    if value is None:
        return None
    try:
        numeric = float(value)
    except (TypeError, ValueError):
        return None
    if not math.isfinite(numeric):
        return None
    return round(numeric, digits)


def _turnover_pct_from_transition_cost(
    transition_cost_pct: float,
    transaction_cost_pct: float,
) -> float:
    """Recover traded value as % of portfolio from transition cost diagnostics."""
    try:
        if transaction_cost_pct <= 0:
            return 0.0
        return (float(transition_cost_pct or 0) / float(transaction_cost_pct)) * 100
    except (TypeError, ValueError, ZeroDivisionError):
        return 0.0


def _portfolio_weights(portfolio: Dict[str, Any]) -> Dict[str, float]:
    """Return portfolio weights as a normalized ticker -> float dict."""
    weights = portfolio.get('weights', {}) or {}
    if isinstance(weights, dict):
        return {str(k): float(v or 0) for k, v in weights.items()}

    stocks = portfolio.get('stocks', []) or []
    if isinstance(weights, list) and len(stocks) == len(weights):
        return {str(stock): float(weight or 0) for stock, weight in zip(stocks, weights)}

    return {}


def _load_sector_mapping(logger: logging.Logger) -> Dict[str, str]:
    """Load ticker -> sector mapping for market breadth diagnostics."""
    if not os.path.exists(TICKERS_FILE):
        logger.warning(f"Tickers file not found for sector mapping: {TICKERS_FILE}")
        return {}

    try:
        df = pd.read_csv(TICKERS_FILE, comment='#')
        if 'Ticker' not in df.columns or 'Sector' not in df.columns:
            return {}
        df = df.dropna(subset=['Ticker'])
        return {
            str(row['Ticker']).strip(): str(row.get('Sector') or 'Unknown').strip()
            for _, row in df.iterrows()
            if str(row['Ticker']).strip()
        }
    except Exception as e:
        logger.warning(f"Could not load sector mapping from tickers.txt: {e}")
        return {}


def _build_market_regime_diagnostics(
    logger: logging.Logger,
    params: Dict[str, Any],
) -> Dict[str, Any]:
    """Build post-peak market regime diagnostics from StockDataDB."""
    if not os.path.exists(STOCK_DATA_DB):
        logger.warning(f"StockDataDB not found for market regime diagnostics: {STOCK_DATA_DB}")
        return {'state': 'unknown', 'reason': 'stock_data_db_missing'}

    try:
        df = pd.read_csv(STOCK_DATA_DB, usecols=['Date', 'Stock', 'Close'])
        df['Date'] = pd.to_datetime(df['Date'], errors='coerce')
        df = df.dropna(subset=['Date', 'Stock', 'Close'])
        prices = df.pivot(index='Date', columns='Stock', values='Close').sort_index()
        regime = compute_market_regime(prices, params, _load_sector_mapping(logger))
        logger.info(
            "Market regime diagnostics: "
            f"{regime.get('state')} ({', '.join(regime.get('triggers', [])) or 'no triggers'})"
        )
        return regime
    except Exception as e:
        logger.warning(f"Could not build market regime diagnostics: {e}")
        return {'state': 'unknown', 'reason': str(e)}


def _build_target_quality_context(logger: logging.Logger, params: Dict[str, Any]) -> Dict[str, Dict[str, Any]]:
    """Build related-ticker context for target quality checks."""
    financials = _load_financials_db(logger)
    records = []
    for stock, info in financials.items():
        records.append({
            'Stock': stock,
            'CurrentPrice': info.get('current_price'),
            'TargetPrice': info.get('target_price'),
            'TargetPriceSource': info.get('target_price_source'),
        })
    return build_related_target_context(records, params)


def _quality_flags_from_meta(target_meta: Dict[str, Any]) -> List[str]:
    flags = target_meta.get('target_quality_flags')
    if isinstance(flags, list):
        return [str(flag) for flag in flags if str(flag)]
    if isinstance(flags, str) and flags.strip():
        return [flag for flag in flags.split(';') if flag]
    return []


def _build_return_contributors(
    portfolio: Dict[str, Any],
    expected_return_pct: float,
    logger: logging.Logger,
    params: Dict[str, Any],
    related_target_context: Dict[str, Dict[str, Any]],
    allow_historical_fallback: bool = False,
) -> List[Dict[str, Any]]:
    """Explain each asset contribution to target-based expected return."""
    contributors: List[Dict[str, Any]] = []
    weights = _portfolio_weights(portfolio)
    current_prices = portfolio.get('current_prices', {}) or {}
    target_prices = portfolio.get('target_prices', {}) or {}
    historical_returns = portfolio.get('historical_returns', {}) or {}

    for stock, weight in weights.items():
        current = current_prices.get(stock)
        if current is None or not pd.notna(current):
            current = get_current_price(stock, logger)

        target_meta = get_target_metadata(stock, logger)
        target = target_prices.get(stock)
        if target is None or not pd.notna(target):
            target = target_meta.get('target_price')

        raw_upside_pct = None
        contribution_pct = 0.0
        return_source = 'none'
        target_source = target_meta.get('target_source', 'None')

        if current and target and current > 0 and target > 0:
            raw_upside_pct = ((float(target) / float(current)) - 1) * 100
            contribution_pct = weight * raw_upside_pct
            return_source = 'target'
        elif allow_historical_fallback and stock in historical_returns:
            hist_return = historical_returns.get(stock)
            if hist_return is not None and pd.notna(hist_return):
                raw_upside_pct = float(hist_return) * 100
                contribution_pct = weight * raw_upside_pct
                return_source = 'historical'
                target_source = 'HistoricalReturnFallback'

        quality_record = {
            'Stock': stock,
            'CurrentPrice': current,
            'TargetPrice': target,
            'TargetPriceSource': target_source,
            'forwardPE': target_meta.get('forward_pe'),
            'averageVolume': target_meta.get('average_volume'),
            'LastUpdated': target_meta.get('last_updated'),
        }
        if raw_upside_pct is not None:
            quality_record['raw_upside_pct'] = raw_upside_pct

        quality = evaluate_target_quality(quality_record, params, related_target_context)
        if target_meta.get('target_quality_score') is not None:
            quality['target_quality_score'] = float(target_meta.get('target_quality_score'))
        if target_meta.get('target_quality_bucket'):
            quality['target_quality_bucket'] = str(target_meta.get('target_quality_bucket'))
        meta_flags = _quality_flags_from_meta(target_meta)
        if meta_flags:
            quality['target_quality_flags'] = sorted(set(quality['target_quality_flags']) | set(meta_flags))

        base_return_pct = None
        base_return_source = None
        if return_source == 'historical' and raw_upside_pct is not None:
            base_return_pct = raw_upside_pct
            base_return_source = 'historical_fallback'

        adjustment = calculate_adjusted_return(
            {
                'raw_expected_return_pct': raw_upside_pct,
                'target_quality_score': quality.get('target_quality_score'),
                'target_quality_bucket': quality.get('target_quality_bucket'),
                'return_source': return_source,
                'base_return_pct': base_return_pct,
                'base_return_source': base_return_source,
            },
            params,
        )
        adjusted_contribution_pct = weight * adjustment['adjusted_expected_return_pct']
        reduction_contribution_pct = contribution_pct - adjusted_contribution_pct

        contributors.append({
            'stock': stock,
            'weight': round(weight, 6),
            'weight_pct': round(weight * 100, 2),
            'current_price': _round_or_none(current, 4),
            'target_price': _round_or_none(target, 4),
            'raw_upside_pct': _round_or_none(raw_upside_pct, 2),
            'return_contribution_pct': _round_or_none(contribution_pct, 2),
            'raw_expected_return_pct': _round_or_none(adjustment.get('raw_expected_return_pct'), 2),
            'capped_raw_return_pct': _round_or_none(adjustment.get('capped_raw_return_pct'), 2),
            'adjusted_expected_return_pct': _round_or_none(adjustment.get('adjusted_expected_return_pct'), 2),
            'adjusted_return_contribution_pct': _round_or_none(adjusted_contribution_pct, 2),
            'adjusted_return_delta_pct': _round_or_none(adjustment.get('adjusted_return_delta_pct'), 2),
            'adjusted_return_reduction_contribution_pct': _round_or_none(reduction_contribution_pct, 2),
            'shrinkage_factor': _round_or_none(adjustment.get('shrinkage_factor'), 4),
            'base_return_pct': _round_or_none(adjustment.get('base_return_pct'), 2),
            'base_return_source': adjustment.get('base_return_source'),
            'uncertainty_penalty_pct': _round_or_none(adjustment.get('uncertainty_penalty_pct'), 2),
            'target_source': target_source,
            'return_source': return_source,
            'sector': target_meta.get('sector'),
            'forward_pe': _round_or_none(target_meta.get('forward_pe'), 4),
            'forward_eps': _round_or_none(target_meta.get('forward_eps'), 4),
            'target_quality_score': _round_or_none(quality.get('target_quality_score'), 4),
            'target_quality_bucket': quality.get('target_quality_bucket'),
            'target_quality_flags': quality.get('target_quality_flags', []),
            'target_quality_related': quality.get('target_quality_related'),
        })

    contributors.sort(
        key=lambda row: abs(row.get('return_contribution_pct') or 0),
        reverse=True,
    )

    # Keep the exact portfolio expected return visible even when rounded
    # contributors sum to a slightly different value.
    if contributors:
        contributors[0]['portfolio_expected_return_pct'] = round(expected_return_pct, 2)

    return contributors


def _build_return_concentration(
    contributors: List[Dict[str, Any]],
    expected_return_pct: float,
) -> Dict[str, Any]:
    """Measure how much of expected return is concentrated in top contributors."""
    positive = [
        row for row in contributors
        if (row.get('return_contribution_pct') or 0) > 0
    ]
    ordered = positive or contributors
    total = expected_return_pct if abs(expected_return_pct or 0) > 1e-9 else sum(
        abs(row.get('return_contribution_pct') or 0) for row in ordered
    )

    def contribution_pp(n: int) -> float:
        return round(sum((row.get('return_contribution_pct') or 0) for row in ordered[:n]), 2)

    def share(n: int) -> Optional[float]:
        if not total:
            return None
        return round((contribution_pp(n) / total) * 100, 2)

    return {
        'expected_return_pct': round(expected_return_pct or 0, 2),
        'top1_contribution_pct': share(1),
        'top2_contribution_pct': share(2),
        'top5_contribution_pct': share(5),
        'top1_contribution_pp': contribution_pp(1),
        'top2_contribution_pp': contribution_pp(2),
        'top5_contribution_pp': contribution_pp(5),
        'top_symbols': [row.get('stock') for row in ordered[:5]],
    }


def _build_return_source_summary(contributors: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Aggregate expected return contribution by target/return source."""
    by_source: Dict[str, Dict[str, Any]] = {}

    for row in contributors:
        source = row.get('target_source') or row.get('return_source') or 'Unknown'
        if source not in by_source:
            by_source[source] = {
                'source': source,
                'count': 0,
                'weight_pct': 0.0,
                'return_contribution_pct': 0.0,
            }

        by_source[source]['count'] += 1
        by_source[source]['weight_pct'] += row.get('weight_pct') or 0
        by_source[source]['return_contribution_pct'] += row.get('return_contribution_pct') or 0

    summary = []
    for item in by_source.values():
        summary.append({
            'source': item['source'],
            'count': item['count'],
            'weight_pct': round(item['weight_pct'], 2),
            'return_contribution_pct': round(item['return_contribution_pct'], 2),
        })

    summary.sort(key=lambda row: abs(row.get('return_contribution_pct') or 0), reverse=True)
    return summary


def _build_adjusted_return_summary(
    contributors: List[Dict[str, Any]],
    expected_return_pct: float,
) -> Dict[str, Any]:
    """Summarize the shadow expected return after target-quality shrinkage."""
    raw_sum = sum(row.get('return_contribution_pct') or 0 for row in contributors)
    adjusted_sum = sum(row.get('adjusted_return_contribution_pct') or 0 for row in contributors)
    raw_total = expected_return_pct if abs(expected_return_pct or 0) > 1e-9 else raw_sum
    reduction_pct = raw_total - adjusted_sum

    top_reductions = [
        {
            'stock': row.get('stock'),
            'weight_pct': row.get('weight_pct'),
            'raw_return_contribution_pct': row.get('return_contribution_pct'),
            'adjusted_return_contribution_pct': row.get('adjusted_return_contribution_pct'),
            'reduction_pct': row.get('adjusted_return_reduction_contribution_pct'),
            'raw_expected_return_pct': row.get('raw_expected_return_pct'),
            'adjusted_expected_return_pct': row.get('adjusted_expected_return_pct'),
            'shrinkage_factor': row.get('shrinkage_factor'),
            'target_quality_bucket': row.get('target_quality_bucket'),
            'target_quality_flags': row.get('target_quality_flags', []),
        }
        for row in contributors
        if (row.get('adjusted_return_reduction_contribution_pct') or 0) > 0
    ]
    top_reductions.sort(key=lambda row: row.get('reduction_pct') or 0, reverse=True)

    return {
        'raw_expected_return_pct': round(raw_total or 0, 2),
        'raw_contributor_sum_pct': round(raw_sum, 2),
        'adjusted_expected_return_pct': round(adjusted_sum, 2),
        'adjusted_return_reduction_pct': round(reduction_pct, 2),
        'adjusted_return_reduction_pct_of_raw': (
            round((reduction_pct / raw_total) * 100, 2) if raw_total else None
        ),
        'top_reductions': top_reductions[:5],
    }


def _build_shadow_quality_metrics(
    contributors: List[Dict[str, Any]],
    adjusted_summary: Dict[str, Any],
) -> Dict[str, Any]:
    """Summarize portfolio-level target confidence for the shadow gate."""
    total_weight = sum(row.get('weight_pct') or 0 for row in contributors)
    weighted_quality = 0.0
    low_reject_weight = 0.0
    suspicious_contribution = 0.0

    for row in contributors:
        weight_pct = row.get('weight_pct') or 0
        score = row.get('target_quality_score')
        bucket = row.get('target_quality_bucket')
        if score is not None:
            weighted_quality += weight_pct * float(score)
        if bucket in ('low', 'reject'):
            low_reject_weight += weight_pct
            suspicious_contribution += max(row.get('return_contribution_pct') or 0, 0)

    raw_return = adjusted_summary.get('raw_expected_return_pct') or 0
    suspicious_share = (
        (suspicious_contribution / raw_return) * 100
        if raw_return and raw_return > 0
        else None
    )

    return {
        'portfolio_target_quality_score': round(weighted_quality / total_weight, 4) if total_weight else None,
        'low_reject_weight_pct': round(low_reject_weight, 2),
        'suspicious_return_contribution_pct': round(suspicious_contribution, 2),
        'suspicious_return_contribution_share_pct': (
            round(suspicious_share, 2) if suspicious_share is not None else None
        ),
    }


def _load_shadow_gate_history(params: Dict[str, Any], logger: logging.Logger) -> List[Dict[str, Any]]:
    """Read prior shadow gate rows from optimized history, if present."""
    history_path = os.path.expanduser(
        params.get('OPTIMIZED_RESULTS_FILE', os.path.join(ROOT, 'data', 'results', 'optimized_portfolio_history.jsonl'))
    )
    if not os.path.exists(history_path):
        return []

    rows: List[Dict[str, Any]] = []
    try:
        with open(history_path, 'r', encoding='utf-8') as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    row = json.loads(line)
                except json.JSONDecodeError:
                    continue
                rows.append(row)
    except Exception as e:
        logger.debug(f"Could not read shadow gate history: {e}")
        return []

    return rows


def _calculate_signal_persistence_days(
    current_date: str,
    current_signal_passes: bool,
    params: Dict[str, Any],
    logger: logging.Logger,
) -> int:
    """Count distinct recent run dates where the adjusted signal cleared the shadow hurdle."""
    if not current_signal_passes:
        return 0

    passing_dates = {current_date}
    seen_dates = {current_date}
    for row in reversed(_load_shadow_gate_history(params, logger)):
        row_date = str(row.get('date') or '')[:10]
        if not row_date or row_date in seen_dates:
            continue
        seen_dates.add(row_date)

        gain = _round_or_none(row.get('shadow_expected_gain_pct'), 4)
        hurdle = _round_or_none(row.get('shadow_hurdle_pct'), 4)
        if gain is None or hurdle is None or gain < hurdle:
            break
        passing_dates.add(row_date)

    return len(passing_dates)


def _shadow_veto(
    code: str,
    message: str,
    actual: Optional[float] = None,
    threshold: Optional[float] = None,
) -> Dict[str, Any]:
    return {
        'code': code,
        'message': message,
        'actual': _round_or_none(actual, 4),
        'threshold': _round_or_none(threshold, 4),
    }


def _build_shadow_rebalance_gate(
    official_decision: str,
    adjusted_gain_pct: float,
    optimal_transition_cost_pct: float,
    diagnostics: Dict[str, Any],
    params: Dict[str, Any],
    logger: logging.Logger,
    current_date: str,
) -> Dict[str, Any]:
    """Build a stricter shadow decision about whether the trade is ready to execute."""
    market_regime = diagnostics.get('market_regime', {}) or {}
    market_impact = market_regime.get('impact', {}) or {}
    turnover = diagnostics.get('turnover', {}) or {}
    contributors = diagnostics.get('return_contributors', {}).get('optimal', []) or []
    adjusted_summary = diagnostics.get('adjusted_returns', {}).get('optimal', {}) or {}

    base_hurdle = float(params.get('SHADOW_BASE_HURDLE_PCT', params.get('MIN_EXCESS_RETURN_THRESHOLD', 0.5)))
    slippage = float(params.get('SHADOW_SLIPPAGE_ESTIMATE_PCT', 0.15))
    tax_drag = float(params.get('SHADOW_TAX_DRAG_ESTIMATE_PCT', 0.0))
    uncertainty = float(params.get('SHADOW_MODEL_UNCERTAINTY_PENALTY_PCT', 0.5))
    regime_addon = float(market_impact.get('suggested_hurdle_addon_pct') or 0.0)
    dynamic_hurdle = base_hurdle + optimal_transition_cost_pct + slippage + tax_drag + uncertainty + regime_addon

    turnover_budget = float(params.get('SHADOW_TURNOVER_BUDGET_PCT', 35.0))
    turnover_multiplier = float(market_impact.get('suggested_turnover_budget_multiplier') or 1.0)
    effective_turnover_budget = turnover_budget * turnover_multiplier
    turnover_pct = float(turnover.get('total_trade_value_pct') or 0.0)

    confidence_floor = float(params.get('SHADOW_CONFIDENCE_FLOOR', 0.60))
    max_suspicious = float(params.get('SHADOW_MAX_SUSPICIOUS_RETURN_CONTRIBUTION_PCT', 35.0))
    min_persistence = int(params.get('SHADOW_MIN_PERSISTENCE_DAYS', 2))
    partial_min_gain = float(params.get('SHADOW_PARTIAL_REBALANCE_MIN_GAIN_PCT', 1.0))

    quality_metrics = _build_shadow_quality_metrics(contributors, adjusted_summary)
    portfolio_quality = quality_metrics.get('portfolio_target_quality_score')
    suspicious_share = quality_metrics.get('suspicious_return_contribution_share_pct')

    gain_passes = adjusted_gain_pct >= dynamic_hurdle
    signal_persistence_days = _calculate_signal_persistence_days(
        current_date,
        gain_passes,
        params,
        logger,
    )

    vetoes: List[Dict[str, Any]] = []
    if not gain_passes:
        vetoes.append(_shadow_veto(
            'adjusted_gain_below_hurdle',
            'Ganho ajustado abaixo do hurdle dinâmico.',
            adjusted_gain_pct,
            dynamic_hurdle,
        ))
    if signal_persistence_days < min_persistence:
        vetoes.append(_shadow_veto(
            'signal_not_persistent',
            'Sinal ajustado ainda não persistiu pelo mínimo configurado.',
            signal_persistence_days,
            min_persistence,
        ))
    if turnover_pct > effective_turnover_budget:
        vetoes.append(_shadow_veto(
            'turnover_above_budget',
            'Turnover necessário acima do orçamento shadow.',
            turnover_pct,
            effective_turnover_budget,
        ))
    if portfolio_quality is not None and portfolio_quality < confidence_floor:
        vetoes.append(_shadow_veto(
            'target_quality_below_floor',
            'Qualidade média dos targets do portfólio abaixo do piso.',
            portfolio_quality,
            confidence_floor,
        ))
    if suspicious_share is not None and suspicious_share > max_suspicious:
        vetoes.append(_shadow_veto(
            'suspicious_return_contribution_high',
            'Contribuição de targets low/reject acima do limite.',
            suspicious_share,
            max_suspicious,
        ))

    trade_allowed = len(vetoes) == 0
    only_turnover_veto = (
        len(vetoes) == 1
        and vetoes[0].get('code') == 'turnover_above_budget'
        and adjusted_gain_pct >= max(dynamic_hurdle, partial_min_gain)
    )

    if official_decision != 'REBALANCE' and not trade_allowed:
        shadow_decision = 'HOLD'
    elif trade_allowed:
        shadow_decision = 'REBALANCE'
    elif only_turnover_veto:
        shadow_decision = 'PARTIAL_REBALANCE'
    else:
        shadow_decision = 'WATCH'

    reason_by_decision = {
        'REBALANCE': 'Gate shadow liberou a operação.',
        'PARTIAL_REBALANCE': 'Ganho ajustado passa no gate, mas turnover sugere execução parcial.',
        'WATCH': 'Há sinal oficial, mas o gate shadow recomenda observar antes de operar.',
        'HOLD': 'Sem sinal ajustado suficiente para operar.',
    }

    return {
        'shadow_decision': shadow_decision,
        'shadow_decision_reason': reason_by_decision[shadow_decision],
        'shadow_trade_allowed': bool(trade_allowed),
        'shadow_expected_gain_pct': round(adjusted_gain_pct, 4),
        'shadow_hurdle_pct': round(dynamic_hurdle, 4),
        'shadow_hurdle_components': {
            'base_hurdle_pct': round(base_hurdle, 4),
            'transition_cost_pct': round(optimal_transition_cost_pct, 4),
            'slippage_estimate_pct': round(slippage, 4),
            'tax_drag_estimate_pct': round(tax_drag, 4),
            'model_uncertainty_penalty_pct': round(uncertainty, 4),
            'regime_stress_penalty_pct': round(regime_addon, 4),
        },
        'shadow_veto_reasons': vetoes,
        'shadow_signal_persistence_days': signal_persistence_days,
        'shadow_min_persistence_days': min_persistence,
        'shadow_turnover_pct': round(turnover_pct, 4),
        'shadow_turnover_budget_pct': round(effective_turnover_budget, 4),
        'shadow_base_turnover_budget_pct': round(turnover_budget, 4),
        'shadow_turnover_budget_multiplier': round(turnover_multiplier, 4),
        **quality_metrics,
        'shadow_confidence_floor': round(confidence_floor, 4),
        'shadow_max_suspicious_return_contribution_pct': round(max_suspicious, 4),
    }


def _execution_state_label(state: str) -> str:
    labels = {
        'HOLD': 'Manter',
        'WATCH': 'Observar',
        'PARTIAL_REBALANCE': 'Parcial',
        'REBALANCE': 'Rebalancear',
    }
    return labels.get(state, state or '—')


def _execution_today_action(state: str) -> str:
    actions = {
        'HOLD': 'Manter carteira atual.',
        'WATCH': 'Observar sem enviar ordens hoje.',
        'PARTIAL_REBALANCE': 'Executar ajuste parcial dentro do orçamento.',
        'REBALANCE': 'Executar rebalanceamento dentro das bandas.',
    }
    return actions.get(state, 'Sem ação definida.')


def _build_sector_execution_drift(
    holdings: Dict[str, Any],
    optimal: Dict[str, Any],
    sector_band_pct: float,
    logger: logging.Logger,
) -> List[Dict[str, Any]]:
    """Compare current vs target sector exposure for execution diagnostics."""
    financials = _load_financials_db(logger)

    def sector_for(symbol: str) -> str:
        clean = symbol if symbol.endswith('.SA') else f'{symbol}.SA'
        info = financials.get(clean, {})
        return info.get('sector') or 'Unknown'

    current_by_sector: Dict[str, float] = {}
    target_by_sector: Dict[str, float] = {}

    for symbol, weight in (holdings.get('weights', {}) or {}).items():
        sector = sector_for(symbol)
        current_by_sector[sector] = current_by_sector.get(sector, 0.0) + (weight or 0) * 100

    for symbol, weight in (optimal.get('weights', {}) or {}).items():
        sector = sector_for(symbol)
        target_by_sector[sector] = target_by_sector.get(sector, 0.0) + (weight or 0) * 100

    rows = []
    for sector in sorted(set(current_by_sector) | set(target_by_sector)):
        current_pct = current_by_sector.get(sector, 0.0)
        target_pct = target_by_sector.get(sector, 0.0)
        drift_pct = target_pct - current_pct
        rows.append({
            'sector': sector,
            'current_weight_pct': round(current_pct, 2),
            'target_weight_pct': round(target_pct, 2),
            'drift_pct': round(drift_pct, 2),
            'outside_band': abs(drift_pct) >= sector_band_pct,
        })

    rows.sort(key=lambda row: abs(row.get('drift_pct') or 0), reverse=True)
    return rows


def _build_shadow_execution_plan(
    transactions: List[Dict[str, Any]],
    holdings: Dict[str, Any],
    optimal: Dict[str, Any],
    shadow_gate: Dict[str, Any],
    params: Dict[str, Any],
    logger: logging.Logger,
) -> Dict[str, Any]:
    """Translate the shadow state into today's executable action plan."""
    state = shadow_gate.get('shadow_decision') or 'HOLD'
    portfolio_value = holdings.get('total_value', 0) or 0
    asset_band_pct = float(params.get('EXECUTION_ASSET_TOLERANCE_BAND_PCT', 2.0))
    sector_band_pct = float(params.get('EXECUTION_SECTOR_TOLERANCE_BAND_PCT', 5.0))
    weekly_budget_pct = float(params.get('EXECUTION_WEEKLY_TURNOVER_BUDGET_PCT', 12.0))
    monthly_budget_pct = float(params.get('EXECUTION_MONTHLY_TURNOVER_BUDGET_PCT', 35.0))
    min_trade_value = float(params.get('EXECUTION_MIN_TRADE_VALUE_BRL', 25.0))
    max_actions = int(params.get('EXECUTION_MAX_ACTIONS', 6))
    shadow_budget_pct = float(shadow_gate.get('shadow_turnover_budget_pct') or monthly_budget_pct)

    theoretical_trade_value = sum(abs(tx.get('value_change', 0) or 0) for tx in transactions)
    theoretical_trade_pct = (
        theoretical_trade_value / portfolio_value * 100 if portfolio_value > 0 else 0
    )

    executable_states = {'PARTIAL_REBALANCE', 'REBALANCE'}
    can_execute = state in executable_states
    if state == 'REBALANCE':
        today_budget_pct = min(shadow_budget_pct, monthly_budget_pct)
    elif state == 'PARTIAL_REBALANCE':
        today_budget_pct = min(shadow_budget_pct, weekly_budget_pct, monthly_budget_pct)
    else:
        today_budget_pct = 0.0

    today_budget_value = portfolio_value * today_budget_pct / 100 if portfolio_value > 0 else 0
    remaining_budget = today_budget_value
    executed_actions = 0
    executed_value_total = 0.0
    action_rows = []

    sorted_transactions = sorted(
        transactions,
        key=lambda tx: abs(tx.get('weight_change', 0) or 0),
        reverse=True,
    )

    for tx in sorted_transactions:
        current_weight_pct = (tx.get('current_weight') or 0) * 100
        target_weight_pct = (tx.get('target_weight') or 0) * 100
        drift_pct = target_weight_pct - current_weight_pct
        planned_value = abs(tx.get('value_change', 0) or 0)
        planned_value_pct = planned_value / portfolio_value * 100 if portfolio_value > 0 else 0
        outside_asset_band = abs(drift_pct) >= asset_band_pct

        executable_value = 0.0
        executable_shares = 0
        status = 'MONITOR' if state == 'WATCH' else 'HOLD'
        status_reason = _execution_today_action(state)

        if not outside_asset_band:
            status = 'IGNORE_BAND'
            status_reason = 'Dentro da banda de tolerância por ativo.'
        elif planned_value < min_trade_value:
            status = 'IGNORE_SMALL'
            status_reason = 'Valor abaixo do mínimo operacional.'
        elif can_execute:
            if state == 'PARTIAL_REBALANCE' and executed_actions >= max_actions:
                status = 'DEFER_MAX_ACTIONS'
                status_reason = 'Acima do limite de ações executáveis hoje.'
            elif remaining_budget <= 0:
                status = 'DEFER_BUDGET'
                status_reason = 'Fora do orçamento de turnover de hoje.'
            else:
                price = tx.get('current_price') or 0
                planned_shares = int(tx.get('shares') or 0)
                if state == 'REBALANCE':
                    executable_shares = planned_shares
                    executable_value = planned_value
                elif price and planned_shares:
                    executable_shares = min(planned_shares, int(math.floor(remaining_budget / price)))
                    executable_value = executable_shares * price
                else:
                    executable_value = min(planned_value, remaining_budget)

                if executable_value >= min_trade_value and (executable_shares > 0 or not tx.get('shares')):
                    status = 'EXECUTE'
                    status_reason = 'Dentro do gate e do orçamento de execução.'
                    executed_actions += 1
                    executed_value_total += executable_value
                    remaining_budget -= executable_value
                else:
                    executable_value = 0.0
                    executable_shares = 0
                    status = 'DEFER_BUDGET'
                    status_reason = 'Fora do orçamento de turnover de hoje.'

        direction = 1 if tx.get('action') == 'BUY' else -1
        executable_weight_delta_pct = (
            executable_value / portfolio_value * 100 * direction if portfolio_value > 0 else 0
        )
        executable_weight_pct = current_weight_pct + executable_weight_delta_pct

        action_rows.append({
            'symbol': tx.get('symbol'),
            'action': tx.get('action'),
            'status': status,
            'status_reason': status_reason,
            'current_weight_pct': round(current_weight_pct, 2),
            'target_weight_pct': round(target_weight_pct, 2),
            'executable_weight_pct': round(executable_weight_pct, 2),
            'drift_pct': round(drift_pct, 2),
            'outside_asset_band': outside_asset_band,
            'recommended_value_brl': round(planned_value, 2),
            'recommended_value_pct': round(planned_value_pct, 2),
            'executable_value_brl': round(executable_value, 2),
            'executable_value_pct': round(
                executable_value / portfolio_value * 100 if portfolio_value > 0 else 0,
                2,
            ),
            'recommended_shares': tx.get('shares'),
            'executable_shares': executable_shares,
        })

    deferred_value = max(theoretical_trade_value - executed_value_total, 0.0)
    if state == 'REBALANCE':
        intensity_pct = 100.0 if theoretical_trade_value > 0 else 0.0
    elif state == 'PARTIAL_REBALANCE' and theoretical_trade_value > 0:
        intensity_pct = min(100.0, executed_value_total / theoretical_trade_value * 100)
    else:
        intensity_pct = 0.0

    veto_messages = [
        veto.get('message') or veto.get('code')
        for veto in shadow_gate.get('shadow_veto_reasons', [])
    ]
    if state != 'REBALANCE' and not veto_messages:
        veto_messages = [shadow_gate.get('shadow_decision_reason') or _execution_today_action(state)]

    sector_drift = _build_sector_execution_drift(holdings, optimal, sector_band_pct, logger)
    outside_sector_count = sum(1 for row in sector_drift if row.get('outside_band'))

    return {
        'phase': '5_execution_states',
        'decision_state': state,
        'decision_state_label': _execution_state_label(state),
        'today_action': _execution_today_action(state),
        'execution_intensity_pct': round(intensity_pct, 2),
        'can_execute_today': bool(can_execute and executed_value_total > 0),
        'asset_tolerance_band_pct': round(asset_band_pct, 2),
        'sector_tolerance_band_pct': round(sector_band_pct, 2),
        'weekly_turnover_budget_pct': round(weekly_budget_pct, 2),
        'monthly_turnover_budget_pct': round(monthly_budget_pct, 2),
        'shadow_turnover_budget_pct': round(shadow_budget_pct, 2),
        'today_turnover_budget_pct': round(today_budget_pct, 2),
        'today_turnover_budget_brl': round(today_budget_value, 2),
        'min_trade_value_brl': round(min_trade_value, 2),
        'max_actions': max_actions,
        'theoretical_trade_value_brl': round(theoretical_trade_value, 2),
        'theoretical_trade_value_pct': round(theoretical_trade_pct, 2),
        'executable_trade_value_brl': round(executed_value_total, 2),
        'executable_trade_value_pct': round(
            executed_value_total / portfolio_value * 100 if portfolio_value > 0 else 0,
            2,
        ),
        'deferred_trade_value_brl': round(deferred_value, 2),
        'deferred_trade_value_pct': round(
            deferred_value / portfolio_value * 100 if portfolio_value > 0 else 0,
            2,
        ),
        'num_executable_actions': sum(1 for row in action_rows if row.get('status') == 'EXECUTE'),
        'num_deferred_actions': sum(
            1 for row in action_rows
            if row.get('status') in {'MONITOR', 'HOLD', 'DEFER_BUDGET', 'DEFER_MAX_ACTIONS'}
        ),
        'num_ignored_actions': sum(
            1 for row in action_rows
            if row.get('status') in {'IGNORE_BAND', 'IGNORE_SMALL'}
        ),
        'num_asset_band_breaches': sum(1 for row in action_rows if row.get('outside_asset_band')),
        'num_sector_band_breaches': outside_sector_count,
        'why_not_rebalance_today': veto_messages,
        'actions': action_rows,
        'sector_drift': sector_drift,
    }


def _build_target_quality_summary(contributors: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Aggregate target quality by bucket for a portfolio."""
    by_bucket: Dict[str, Dict[str, Any]] = {}

    for row in contributors:
        bucket = row.get('target_quality_bucket') or 'unknown'
        if bucket not in by_bucket:
            by_bucket[bucket] = {
                'bucket': bucket,
                'count': 0,
                'weight_pct': 0.0,
                'return_contribution_pct': 0.0,
                'symbols': [],
            }

        by_bucket[bucket]['count'] += 1
        by_bucket[bucket]['weight_pct'] += row.get('weight_pct') or 0
        by_bucket[bucket]['return_contribution_pct'] += row.get('return_contribution_pct') or 0
        by_bucket[bucket]['symbols'].append(row.get('stock'))

    order = {'high': 0, 'medium': 1, 'low': 2, 'reject': 3, 'unknown': 4}
    summary = []
    for item in by_bucket.values():
        summary.append({
            'bucket': item['bucket'],
            'count': item['count'],
            'weight_pct': round(item['weight_pct'], 2),
            'return_contribution_pct': round(item['return_contribution_pct'], 2),
            'symbols': item['symbols'],
        })

    summary.sort(key=lambda row: order.get(row.get('bucket'), 99))
    return summary


def _build_turnover_diagnostics(
    transactions: List[Dict[str, Any]],
    holdings: Dict[str, Any],
    transaction_summary: Dict[str, Any],
) -> Dict[str, Any]:
    """Summarize the operational size of the proposed transition."""
    portfolio_value = holdings.get('total_value', 0) or 0
    total_trade_value = sum(abs(tx.get('value_change', 0) or 0) for tx in transactions)
    total_trade_pct = (total_trade_value / portfolio_value * 100) if portfolio_value > 0 else 0

    return {
        'num_transactions': len(transactions),
        'total_trade_value': round(total_trade_value, 2),
        'total_trade_value_pct': round(total_trade_pct, 2),
        'total_buy_value': transaction_summary.get('total_buy_value', 0),
        'total_sell_value': transaction_summary.get('total_sell_value', 0),
        'total_cost': transaction_summary.get('total_cost', 0),
        'portfolio_value': round(portfolio_value, 2),
    }


def build_baseline_diagnostics(
    holdings: Dict[str, Any],
    ideal: Dict[str, Any],
    optimal: Dict[str, Any],
    transactions: List[Dict[str, Any]],
    transaction_summary: Dict[str, Any],
    params: Dict[str, Any],
    logger: logging.Logger,
) -> Dict[str, Any]:
    """Build target-quality and adjusted-return diagnostics without changing decisions."""
    portfolios = {
        'holdings': (holdings, holdings.get('expected_return', 0), True),
        'ideal': (ideal, ideal.get('expected_return', 0), False),
        'optimal': (optimal, optimal.get('expected_return', 0), False),
    }

    contributors: Dict[str, List[Dict[str, Any]]] = {}
    concentration: Dict[str, Dict[str, Any]] = {}
    source_summary: Dict[str, List[Dict[str, Any]]] = {}
    quality_summary: Dict[str, List[Dict[str, Any]]] = {}
    adjusted_returns: Dict[str, Dict[str, Any]] = {}
    related_target_context = _build_target_quality_context(logger, params)
    market_regime = _build_market_regime_diagnostics(logger, params)

    for name, (portfolio, expected_return, allow_hist) in portfolios.items():
        rows = _build_return_contributors(
            portfolio,
            expected_return,
            logger,
            params,
            related_target_context,
            allow_historical_fallback=allow_hist,
        )
        contributors[name] = rows
        concentration[name] = _build_return_concentration(rows, expected_return)
        source_summary[name] = _build_return_source_summary(rows)
        quality_summary[name] = _build_target_quality_summary(rows)
        adjusted_returns[name] = _build_adjusted_return_summary(rows, expected_return)

    return {
        'phase': '8_official_decision_promotion',
        'description': 'Explains raw/adjusted return, market stress, legacy decision, promoted operational decision and stable turnover-aware optimization.',
        'return_concentration': concentration,
        'return_contributors': contributors,
        'return_source_summary': source_summary,
        'target_quality_summary': quality_summary,
        'adjusted_returns': adjusted_returns,
        'market_regime': market_regime,
        'turnover': _build_turnover_diagnostics(transactions, holdings, transaction_summary),
    }


def discretize_to_integer_shares(
    portfolio_weights: Dict[str, float],
    total_value: float,
    logger: logging.Logger
) -> Tuple[Dict[str, float], Dict[str, int], float]:
    """Convert continuous portfolio weights into integer share quantities.

    MVO (Motor A) optimises in continuous weight-space.  The real B3
    market only allows integer shares.  This function bridges the gap:

      1. Given continuous weights and total portfolio value, compute how
         many integer shares of each stock can be purchased.
      2. Recalculate actual weights from those integer positions.

    The caller should then recalculate expected return, Sharpe, etc.
    using the *discretized* weights so the recommendation accurately
    reflects the executable portfolio.

    NOTE: Uses floor() rounding to ensure conservative allocation (never
    over-allocates). This matches the strategy in D_Publish.py for the
    pipeline_latest.json generation, ensuring that the recommended
    transactions in optimized_recommendation.json align with the model
    portfolio shown in the "Alocação do Modelo" table.

    Args:
        portfolio_weights: {stock: weight_fraction} summing to ~1.0
        total_value: total portfolio value in BRL
        logger: logger instance

    Returns:
        (actual_weights, share_quantities, total_invested_brl)
    """
    share_quantities: Dict[str, int] = {}
    actual_invested: Dict[str, float] = {}

    for stock, weight in portfolio_weights.items():
        if weight <= 0.001:
            continue

        allocated = weight * total_value
        price = get_current_price(stock, logger)

        if price and price > 0:
            qty = max(1, int(math.floor(allocated / price)))
            share_quantities[stock] = qty
            actual_invested[stock] = qty * price
        else:
            logger.warning(f"  Cannot discretize {stock}: no price available")
            share_quantities[stock] = 0
            actual_invested[stock] = allocated

    total_actual = sum(actual_invested.values())
    actual_weights: Dict[str, float] = {}
    if total_actual > 0:
        actual_weights = {
            stock: inv / total_actual
            for stock, inv in actual_invested.items()
        }

    # Log significant weight deviations
    deviations = []
    for stock in sorted(actual_weights.keys()):
        orig_w = portfolio_weights.get(stock, 0) * 100
        disc_w = actual_weights.get(stock, 0) * 100
        diff = disc_w - orig_w
        if abs(diff) > 0.1:
            deviations.append(
                f"  {stock}: {orig_w:.2f}% → {disc_w:.2f}% "
                f"(Δ{diff:+.2f}%, {share_quantities.get(stock, 0)} shares)"
            )
    if deviations:
        logger.info(f"Discretization weight deviations (>{0.1:.1f}%):")
        for d in deviations:
            logger.info(d)

    return actual_weights, share_quantities, total_actual


def find_optimal_portfolio(
    holdings: Dict[str, Any],
    ideal: Dict[str, Any],
    candidates: List[Dict[str, Any]],
    transaction_cost_pct: float,
    params: Dict,
    logger: logging.Logger
) -> Dict[str, Any]:
    """
    Find the optimal portfolio among candidates that maximizes score
    while accounting for transaction costs.
    """
    best_candidate = None
    best_score = -float('inf')
    best_net_return = -float('inf')

    holdings_expected_return = holdings.get('expected_return', 0)
    ideal_expected_return = ideal.get('expected_return', 0)
    ideal_sharpe = ideal.get('sharpe_ratio', 0)

    for candidate in candidates:
        blend_ratio = candidate['blend_ratio']

        # Calculate expected return (linear interpolation)
        candidate_return = holdings_expected_return * (1 - blend_ratio) + ideal_expected_return * blend_ratio

        # Calculate sharpe ratio (linear interpolation as approximation)
        candidate_sharpe = holdings.get('sharpe_ratio', 0) * (1 - blend_ratio) + ideal_sharpe * blend_ratio

        # Calculate transition cost
        cost, _ = calculate_transition_cost(
            holdings, candidate, transaction_cost_pct, logger
        )

        # Net return after costs
        net_return = candidate_return - cost

        # Calculate momentum
        momentum = calculate_portfolio_momentum(candidate, logger)

        # Calculate score
        score = score_portfolio(candidate, net_return, candidate_sharpe, momentum, params)

        candidate['expected_return'] = candidate_return
        candidate['sharpe_ratio'] = candidate_sharpe
        candidate['net_return'] = net_return
        candidate['transition_cost'] = cost
        candidate['turnover_pct'] = _turnover_pct_from_transition_cost(cost, transaction_cost_pct)
        candidate['momentum'] = momentum
        candidate['score'] = score

        if score > best_score:
            best_score = score
            best_candidate = candidate
            best_net_return = net_return

    return best_candidate


def _stable_penalty_params(params: Dict[str, Any]) -> Dict[str, float]:
    return {
        'turnover_lambda': float(params.get('TURNOVER_PENALTY_LAMBDA', 0.05)),
        'turnover_target_pct': float(params.get('STABLE_TURNOVER_TARGET_PCT', 12.0)),
        'turnover_excess_lambda': float(params.get('STABLE_TURNOVER_EXCESS_PENALTY_LAMBDA', 0.10)),
        'uncertainty_lambda': float(params.get('STABLE_UNCERTAINTY_PENALTY_LAMBDA', 0.03)),
        'concentration_lambda': float(params.get('STABLE_CONCENTRATION_PENALTY_LAMBDA', 0.02)),
        'suspicious_lambda': float(params.get('STABLE_SUSPICIOUS_RETURN_PENALTY_LAMBDA', 0.03)),
        'max_suspicious_pct': float(params.get('SHADOW_MAX_SUSPICIOUS_RETURN_CONTRIBUTION_PCT', 35.0)),
    }


def _build_stable_frontier_row(
    candidate: Dict[str, Any],
    holdings_adjusted_return_pct: float,
    contributors: List[Dict[str, Any]],
    adjusted_summary: Dict[str, Any],
    params: Dict[str, Any],
) -> Dict[str, Any]:
    """Score one candidate using adjusted return and turnover-aware penalties."""
    penalty_params = _stable_penalty_params(params)
    quality_metrics = _build_shadow_quality_metrics(contributors, adjusted_summary)
    concentration = _build_return_concentration(contributors, candidate.get('expected_return', 0))

    adjusted_gross_return = adjusted_summary.get('adjusted_expected_return_pct') or 0.0
    adjusted_net_return = adjusted_gross_return - (candidate.get('transition_cost') or 0.0)
    adjusted_gain = adjusted_net_return - holdings_adjusted_return_pct
    turnover_pct = candidate.get('turnover_pct') or 0.0
    quality_score = quality_metrics.get('portfolio_target_quality_score')
    uncertainty_pct = max(0.0, (1.0 - quality_score) * 100) if quality_score is not None else 0.0
    top2_concentration = concentration.get('top2_contribution_pct') or 0.0
    concentration_excess = max(0.0, top2_concentration - 50.0)
    suspicious_share = quality_metrics.get('suspicious_return_contribution_share_pct') or 0.0
    suspicious_excess = max(0.0, suspicious_share - penalty_params['max_suspicious_pct'])
    turnover_excess = max(0.0, turnover_pct - penalty_params['turnover_target_pct'])

    turnover_penalty = penalty_params['turnover_lambda'] * turnover_pct
    turnover_excess_penalty = penalty_params['turnover_excess_lambda'] * turnover_excess
    uncertainty_penalty = penalty_params['uncertainty_lambda'] * uncertainty_pct
    concentration_penalty = penalty_params['concentration_lambda'] * concentration_excess
    suspicious_penalty = penalty_params['suspicious_lambda'] * suspicious_excess
    stable_score = (
        adjusted_gain
        - turnover_penalty
        - turnover_excess_penalty
        - uncertainty_penalty
        - concentration_penalty
        - suspicious_penalty
    )

    return {
        'blend_ratio': round(candidate.get('blend_ratio', 0), 4),
        'raw_net_return_pct': round(candidate.get('net_return', 0) or 0, 4),
        'adjusted_net_return_pct': round(adjusted_net_return, 4),
        'adjusted_gain_pct': round(adjusted_gain, 4),
        'turnover_pct': round(turnover_pct, 4),
        'target_quality_score': _round_or_none(quality_score, 4),
        'low_reject_weight_pct': quality_metrics.get('low_reject_weight_pct'),
        'suspicious_return_contribution_share_pct': _round_or_none(suspicious_share, 4),
        'top2_return_concentration_pct': _round_or_none(top2_concentration, 4),
        'stable_score': round(stable_score, 4),
        'stable_score_components': {
            'adjusted_gain_pct': round(adjusted_gain, 4),
            'turnover_penalty_pct': round(turnover_penalty, 4),
            'turnover_excess_penalty_pct': round(turnover_excess_penalty, 4),
            'uncertainty_penalty_pct': round(uncertainty_penalty, 4),
            'concentration_penalty_pct': round(concentration_penalty, 4),
            'suspicious_return_penalty_pct': round(suspicious_penalty, 4),
        },
    }


def _sample_stable_frontier(frontier: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Keep the frontier visible without bloating the dashboard."""
    if not frontier:
        return []

    selected_indices = {0, len(frontier) - 1}
    for pct in (0.25, 0.50, 0.75):
        selected_indices.add(round((len(frontier) - 1) * pct))
    best_idx = max(range(len(frontier)), key=lambda idx: frontier[idx].get('stable_score', -float('inf')))
    selected_indices.add(best_idx)

    return [frontier[idx] for idx in sorted(selected_indices)]


def build_stable_optimization_shadow(
    holdings: Dict[str, Any],
    candidates: List[Dict[str, Any]],
    transaction_cost_pct: float,
    params: Dict[str, Any],
    logger: logging.Logger,
) -> Dict[str, Any]:
    """Select a turnover-aware stable portfolio in shadow mode."""
    related_target_context = _build_target_quality_context(logger, params)
    holdings_contributors = _build_return_contributors(
        holdings,
        holdings.get('expected_return', 0),
        logger,
        params,
        related_target_context,
        allow_historical_fallback=True,
    )
    holdings_adjusted = _build_adjusted_return_summary(
        holdings_contributors,
        holdings.get('expected_return', 0),
    )
    holdings_adjusted_return = holdings_adjusted.get('adjusted_expected_return_pct') or 0.0

    frontier: List[Dict[str, Any]] = []
    by_blend: Dict[float, Dict[str, Any]] = {}
    for candidate in candidates:
        contributors = _build_return_contributors(
            candidate,
            candidate.get('expected_return', 0),
            logger,
            params,
            related_target_context,
            allow_historical_fallback=False,
        )
        adjusted_summary = _build_adjusted_return_summary(
            contributors,
            candidate.get('expected_return', 0),
        )
        row = _build_stable_frontier_row(
            candidate,
            holdings_adjusted_return,
            contributors,
            adjusted_summary,
            params,
        )
        frontier.append(row)
        by_blend[round(candidate.get('blend_ratio', 0), 4)] = candidate

    if not frontier:
        return {
            'phase': '6_turnover_penalty_optimization',
            'enabled': False,
            'reason': 'no_candidates',
        }

    frontier.sort(key=lambda row: row.get('blend_ratio', 0))
    selected_row = max(frontier, key=lambda row: row.get('stable_score', -float('inf')))
    selected_candidate = by_blend.get(selected_row.get('blend_ratio'), {})
    official_row = max(frontier, key=lambda row: row.get('blend_ratio', 0))
    if candidates:
        official_blend = round(max(candidates, key=lambda c: c.get('score', -float('inf'))).get('blend_ratio', 0), 4)
        official_row = next(
            (row for row in frontier if row.get('blend_ratio') == official_blend),
            official_row,
        )

    _, stable_transactions = calculate_transition_cost(
        holdings,
        selected_candidate,
        transaction_cost_pct,
        logger,
    )
    stable_transaction_summary = _build_transaction_summary(stable_transactions)

    turnover_saved = (official_row.get('turnover_pct') or 0) - (selected_row.get('turnover_pct') or 0)
    adjusted_return_tradeoff = (
        (official_row.get('adjusted_net_return_pct') or 0)
        - (selected_row.get('adjusted_net_return_pct') or 0)
    )
    adjusted_return_delta = (
        (selected_row.get('adjusted_net_return_pct') or 0)
        - (official_row.get('adjusted_net_return_pct') or 0)
    )

    return {
        'phase': '6_turnover_penalty_optimization',
        'enabled': True,
        'selected_blend_ratio': selected_row.get('blend_ratio'),
        'selected_stable_score': selected_row.get('stable_score'),
        'official_blend_ratio': official_row.get('blend_ratio'),
        'official_stable_score': official_row.get('stable_score'),
        'turnover_saved_pct': round(turnover_saved, 4),
        'adjusted_return_tradeoff_pct': round(adjusted_return_tradeoff, 4),
        'adjusted_return_delta_pct': round(adjusted_return_delta, 4),
        'penalty_parameters': _stable_penalty_params(params),
        'holdings_adjusted_return_pct': round(holdings_adjusted_return, 4),
        'official_candidate': official_row,
        'stable_candidate': selected_row,
        'stable_portfolio': {
            'stocks': selected_candidate.get('stocks', []),
            'weights': selected_candidate.get('weights', {}),
            'expected_return_pct': round(selected_candidate.get('expected_return', 0) or 0, 4),
            'net_return_pct': round(selected_candidate.get('net_return', 0) or 0, 4),
            'adjusted_net_return_pct': selected_row.get('adjusted_net_return_pct'),
            'turnover_pct': selected_row.get('turnover_pct'),
            'stable_score': selected_row.get('stable_score'),
        },
        'stable_transactions': stable_transactions,
        'stable_transaction_summary': stable_transaction_summary,
        'frontier': _sample_stable_frontier(frontier),
    }


def generate_recommendation(
    holdings: Dict[str, Any],
    ideal: Dict[str, Any],
    optimal: Dict[str, Any],
    stable_optimization: Dict[str, Any],
    transaction_cost_pct: float,
    params: Dict,
    logger: logging.Logger
) -> Dict[str, Any]:
    """Generate the final HOLD / REBALANCE recommendation.

    Decision formula
    ----------------
    excess_return = optimal_net_return − holdings_return

        holdings_return   : expected return of the current portfolio,
                            computed as Σ(weight_i × target_price_i/current_price_i − 1).
                            Exposed in dashboard_latest.json as model.returns.hold_12m.

        optimal_net_return: expected return of the chosen candidate portfolio,
                            already net of the one-time transition cost
                            (transition_cost_pct).  Exposed as model.returns.net_12m.

        excess_return     : how much MORE (%) the model delivers vs. keeping the
                            current portfolio.  Positive → model wins → REBALANCE.
                            Exposed as model.returns.excess_net_12m.
                            NOTE: this is excess over the *current holdings*, NOT
                            over any external market index.

    The threshold (MIN_EXCESS_RETURN_THRESHOLD, default 0.5 pp) protects against
    rebalancing for a marginal gain that could be wiped out by market noise.

    # TODO (future improvement): the candidate selection step already uses a
    # composite score (40% expected_return + 40% Sharpe + 20% momentum), so the
    # chosen optimal portfolio may score far higher than holdings even when its
    # raw return is lower.  Consider adding a score-gap clause to the decision:
    #
    #   if score_gap > SCORE_GAP_THRESHOLD and excess_return > SOFT_RETURN_FLOOR:
    #       decision = 'REBALANCE'
    #
    # This would allow switching to a portfolio with a better risk-adjusted
    # profile even when the pure expected-return excess is below the main
    # threshold.  See generate_recommendation for context.
    """

    min_excess_threshold = float(params.get('MIN_EXCESS_RETURN_THRESHOLD', 0.5))

    holdings_return = holdings.get('expected_return', 0)
    optimal_net_return = optimal.get('net_return', 0)
    # excess_return > 0  → model beats current holdings → favour REBALANCE
    # excess_return < 0  → current holdings beat model  → favour HOLD
    excess_return = optimal_net_return - holdings_return

    # Calculate transactions
    _, transactions = calculate_transition_cost(
        holdings, optimal, transaction_cost_pct, logger
    )
    transaction_summary = _build_transaction_summary(transactions)
    diagnostics = build_baseline_diagnostics(
        holdings,
        ideal,
        optimal,
        transactions,
        transaction_summary,
        params,
        logger,
    )
    adjusted_diagnostics = diagnostics.get('adjusted_returns', {})
    holdings_adjusted_return = (
        adjusted_diagnostics.get('holdings', {}).get('adjusted_expected_return_pct', holdings_return)
    )
    ideal_adjusted_return = (
        adjusted_diagnostics.get('ideal', {}).get('adjusted_expected_return_pct', ideal.get('expected_return', 0))
    )
    optimal_adjusted_gross_return = (
        adjusted_diagnostics.get('optimal', {}).get('adjusted_expected_return_pct', optimal.get('expected_return', 0))
    )
    optimal_adjusted_net_return = optimal_adjusted_gross_return - optimal.get('transition_cost', 0)
    adjusted_excess_return = optimal_adjusted_net_return - holdings_adjusted_return
    market_regime = diagnostics.get('market_regime', {}) or {}
    market_regime_impact = market_regime.get('impact', {}) or {}

    # Legacy v1 decision: raw target-price excess return over current holdings.
    if excess_return >= min_excess_threshold:
        legacy_decision = 'REBALANCE'
        legacy_reason = f"Excess return ({excess_return:.2f}%) exceeds threshold ({min_excess_threshold}%)"
    elif optimal.get('blend_ratio', 0) < 0.1:
        legacy_decision = 'HOLD'
        legacy_reason = f"Optimal portfolio is very close to current holdings"
    else:
        legacy_decision = 'HOLD'
        legacy_reason = f"Excess return ({excess_return:.2f}%) below threshold ({min_excess_threshold}%)"

    generated_date = datetime.now().strftime('%Y-%m-%d')
    generated_timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    shadow_gate = _build_shadow_rebalance_gate(
        legacy_decision,
        adjusted_excess_return,
        optimal.get('transition_cost', 0),
        diagnostics,
        params,
        logger,
        generated_date,
    )
    execution_plan = _build_shadow_execution_plan(
        transactions,
        holdings,
        optimal,
        shadow_gate,
        params,
        logger,
    )
    decision_engine_version = 'v2_operational_shadow_conservative'
    legacy_decision_engine_version = 'v1_raw_excess_return'
    decision = (
        execution_plan.get('decision_state')
        or shadow_gate.get('shadow_decision')
        or legacy_decision
    )
    reason = (
        execution_plan.get('today_action')
        or shadow_gate.get('shadow_decision_reason')
        or legacy_reason
    )

    recommendation = {
        'date': generated_date,
        'timestamp': generated_timestamp,
        'decision': decision,
        'reason': reason,
        'decision_engine_version': decision_engine_version,
        'decision_engine_phase': '8_official_decision_promotion',
        'decision_engine_promoted_from': 'shadow.execution_plan.decision_state',
        'decision_transition_window_days': 60,
        'legacy_decision': legacy_decision,
        'legacy_reason': legacy_reason,
        'legacy_decision_engine_version': legacy_decision_engine_version,
        'legacy_excess_return_pct': round(excess_return, 4),
        'excess_return_pct': round(excess_return, 4),
        'min_threshold_pct': min_excess_threshold,
        'optimal_score': round(optimal.get('score', 0), 4),
        'holdings_score': round(score_portfolio(
            holdings, holdings_return, holdings.get('sharpe_ratio', 0),
            calculate_portfolio_momentum(holdings, logger), params
        ), 4),
        'ideal_score': round(score_portfolio(
            ideal, ideal.get('expected_return', 0), ideal.get('sharpe_ratio', 0),
            calculate_portfolio_momentum(ideal, logger), params
        ), 4),
        'ideal_momentum': round(calculate_portfolio_momentum(ideal, logger), 4),
        'comparison': {
            'window_days': int(params.get('EXPECTED_RETURN_WINDOW_DAYS', 252)),
            'holdings': {
                'stocks': holdings.get('stocks', []),
                'weights': holdings.get('weights', {}),
                'expected_return_pct': round(holdings_return, 2),
                'adjusted_expected_return_pct': round(holdings_adjusted_return, 2),
                'total_value': round(holdings.get('total_value', 0), 2),
                'total_invested': round(holdings.get('total_invested', 0), 2),
            },
            'ideal': {
                'stocks': ideal.get('stocks', []),
                'weights': ideal.get('weights', {}),
                'expected_return_pct': round(ideal.get('expected_return', 0), 2),  # Based on target prices
                'adjusted_expected_return_pct': round(ideal_adjusted_return, 2),
                'historical_return_pct': round(ideal.get('expected_return_annual_pct', ideal.get('expected_return', 0)), 2),  # Based on historical data
                'sharpe_ratio': round(ideal.get('sharpe_ratio', 0), 4),
                'run_id': ideal.get('run_id', ''),
            },
            'optimal': {
                'stocks': optimal.get('stocks', []),
                'weights': optimal.get('weights', {}),
                'expected_return_pct': round(optimal.get('expected_return', 0), 2),
                'adjusted_expected_return_pct': round(optimal_adjusted_gross_return, 2),
                'net_return_pct': round(optimal_net_return, 2),
                'adjusted_net_return_pct': round(optimal_adjusted_net_return, 2),
                'blend_ratio': round(optimal.get('blend_ratio', 0), 2),
                'transition_cost_pct': round(optimal.get('transition_cost', 0), 4),
                'share_quantities': optimal.get('share_quantities', {}),
                'total_discretized_value': round(optimal.get('total_discretized', 0), 2),
                'expected_return_continuous_pct': round(
                    optimal.get('expected_return_continuous', optimal.get('expected_return', 0)), 2
                ),
                'discretized': optimal.get('discretized', False),
            },
        },
        'transactions': transactions,
        'transaction_summary': transaction_summary,
        'diagnostics': diagnostics,
        'shadow': {
            'phase': '8_official_decision_promotion',
            'official_decision': decision,
            'legacy_decision': legacy_decision,
            'legacy_reason': legacy_reason,
            'legacy_decision_engine_version': legacy_decision_engine_version,
            'decision_engine_version': decision_engine_version,
            'official_excess_return_pct': round(excess_return, 4),
            'holdings_adjusted_return_pct': round(holdings_adjusted_return, 4),
            'ideal_adjusted_return_pct': round(ideal_adjusted_return, 4),
            'optimal_adjusted_gross_return_pct': round(optimal_adjusted_gross_return, 4),
            'optimal_adjusted_net_return_pct': round(optimal_adjusted_net_return, 4),
            'adjusted_excess_return_pct': round(adjusted_excess_return, 4),
            'market_regime_state': market_regime.get('state'),
            'market_regime_triggers': market_regime.get('triggers', []),
            'market_regime_hurdle_addon_pct': market_regime_impact.get('suggested_hurdle_addon_pct'),
            'market_regime_shrinkage_multiplier': market_regime_impact.get('suggested_shrinkage_multiplier'),
            'market_regime_turnover_budget_multiplier': (
                market_regime_impact.get('suggested_turnover_budget_multiplier')
            ),
            'min_threshold_pct': min_excess_threshold,
            'would_rebalance_on_adjusted_return': bool(adjusted_excess_return >= min_excess_threshold),
            **shadow_gate,
            'execution_plan': execution_plan,
            'stable_optimization': stable_optimization,
        },
        'transaction_cost_pct_used': round(transaction_cost_pct, 4),
        'parameters': {
            'weight_expected_return': float(params.get('WEIGHT_EXPECTED_RETURN', 0.4)),
            'weight_sharpe_ratio': float(params.get('WEIGHT_SHARPE_RATIO', 0.4)),
            'weight_momentum': float(params.get('WEIGHT_MOMENTUM', 0.2)),
            'return_adjustment_cap_pct': float(params.get('RETURN_ADJUSTMENT_CAP_PCT', 150.0)),
            'return_adjustment_base_pct': float(params.get('RETURN_ADJUSTMENT_BASE_PCT', 0.0)),
            'return_adjustment_reject_base_pct': float(params.get('RETURN_ADJUSTMENT_REJECT_BASE_PCT', 0.0)),
            'return_adjustment_uncertainty_penalty_pct': float(
                params.get('RETURN_ADJUSTMENT_UNCERTAINTY_PENALTY_PCT', 0.0)
            ),
            'shadow_base_hurdle_pct': float(params.get('SHADOW_BASE_HURDLE_PCT', 0.5)),
            'shadow_slippage_estimate_pct': float(params.get('SHADOW_SLIPPAGE_ESTIMATE_PCT', 0.15)),
            'shadow_tax_drag_estimate_pct': float(params.get('SHADOW_TAX_DRAG_ESTIMATE_PCT', 0.0)),
            'shadow_model_uncertainty_penalty_pct': float(
                params.get('SHADOW_MODEL_UNCERTAINTY_PENALTY_PCT', 0.5)
            ),
            'shadow_min_persistence_days': int(params.get('SHADOW_MIN_PERSISTENCE_DAYS', 2)),
            'shadow_turnover_budget_pct': float(params.get('SHADOW_TURNOVER_BUDGET_PCT', 35.0)),
            'shadow_confidence_floor': float(params.get('SHADOW_CONFIDENCE_FLOOR', 0.60)),
            'shadow_max_suspicious_return_contribution_pct': float(
                params.get('SHADOW_MAX_SUSPICIOUS_RETURN_CONTRIBUTION_PCT', 35.0)
            ),
            'execution_asset_tolerance_band_pct': float(params.get('EXECUTION_ASSET_TOLERANCE_BAND_PCT', 2.0)),
            'execution_sector_tolerance_band_pct': float(params.get('EXECUTION_SECTOR_TOLERANCE_BAND_PCT', 5.0)),
            'execution_weekly_turnover_budget_pct': float(params.get('EXECUTION_WEEKLY_TURNOVER_BUDGET_PCT', 12.0)),
            'execution_monthly_turnover_budget_pct': float(params.get('EXECUTION_MONTHLY_TURNOVER_BUDGET_PCT', 35.0)),
            'execution_min_trade_value_brl': float(params.get('EXECUTION_MIN_TRADE_VALUE_BRL', 25.0)),
            'execution_max_actions': int(params.get('EXECUTION_MAX_ACTIONS', 6)),
            'turnover_penalty_lambda': float(params.get('TURNOVER_PENALTY_LAMBDA', 0.05)),
            'stable_turnover_target_pct': float(params.get('STABLE_TURNOVER_TARGET_PCT', 12.0)),
            'stable_turnover_excess_penalty_lambda': float(
                params.get('STABLE_TURNOVER_EXCESS_PENALTY_LAMBDA', 0.10)
            ),
            'stable_uncertainty_penalty_lambda': float(params.get('STABLE_UNCERTAINTY_PENALTY_LAMBDA', 0.03)),
            'stable_concentration_penalty_lambda': float(params.get('STABLE_CONCENTRATION_PENALTY_LAMBDA', 0.02)),
            'stable_suspicious_return_penalty_lambda': float(
                params.get('STABLE_SUSPICIOUS_RETURN_PENALTY_LAMBDA', 0.03)
            ),
        }
    }

    logger.info(
        f"Decision: {decision} ({decision_engine_version}) - {reason}; "
        f"legacy={legacy_decision}"
    )

    return recommendation


def save_recommendation(
    recommendation: Dict[str, Any],
    params: Dict,
    logger: logging.Logger
):
    """Save recommendation to JSON and CSV history"""

    # Save latest JSON
    json_path = os.path.expanduser(
        params.get('OPTIMIZED_LATEST_JSON',
                   os.path.join(ROOT, 'data', 'results', 'optimized_recommendation.json'))
    )
    os.makedirs(os.path.dirname(json_path), exist_ok=True)

    try:
        with open(json_path, 'w', encoding='utf-8') as f:
            json.dump(recommendation, f, indent=2, ensure_ascii=False)
        logger.info(f"Saved recommendation JSON to: {json_path}")
    except Exception as e:
        logger.error(f"Error saving recommendation JSON: {e}")

    # Append to JSONL history (one JSON line per run — preserves native arrays)
    jsonl_path = os.path.expanduser(
        params.get('OPTIMIZED_RESULTS_FILE',
                   os.path.join(ROOT, 'data', 'results', 'optimized_portfolio_history.jsonl'))
    )
    os.makedirs(os.path.dirname(jsonl_path), exist_ok=True)

    try:
        history_row = {
            'date': recommendation['date'],
            'timestamp': recommendation['timestamp'],
            'decision': recommendation['decision'],
            'reason': recommendation['reason'],
            'decision_engine_version': recommendation.get('decision_engine_version'),
            'decision_engine_phase': recommendation.get('decision_engine_phase'),
            'legacy_decision': recommendation.get('legacy_decision'),
            'legacy_reason': recommendation.get('legacy_reason'),
            'legacy_decision_engine_version': recommendation.get('legacy_decision_engine_version'),
            'legacy_excess_return_pct': recommendation.get('legacy_excess_return_pct'),
            'excess_return_pct': recommendation['excess_return_pct'],
            'optimal_score': recommendation['optimal_score'],
            'holdings_score': recommendation['holdings_score'],
            'ideal_score': recommendation['ideal_score'],
            'ideal_momentum': recommendation.get('ideal_momentum'),
            'holdings_return_pct': recommendation['comparison']['holdings']['expected_return_pct'],
            'ideal_return_pct': recommendation['comparison']['ideal']['expected_return_pct'],
            'optimal_return_pct': recommendation['comparison']['optimal']['expected_return_pct'],
            'optimal_net_return_pct': recommendation['comparison']['optimal']['net_return_pct'],
            'blend_ratio': recommendation['comparison']['optimal']['blend_ratio'],
            'transition_cost_pct': recommendation['comparison']['optimal']['transition_cost_pct'],
            'transaction_cost_pct_used': recommendation['transaction_cost_pct_used'],
            'num_transactions': len(recommendation['transactions']),
            'diagnostic_holdings_top2_contribution_pct': (
                recommendation.get('diagnostics', {})
                .get('return_concentration', {})
                .get('holdings', {})
                .get('top2_contribution_pct')
            ),
            'diagnostic_optimal_top2_contribution_pct': (
                recommendation.get('diagnostics', {})
                .get('return_concentration', {})
                .get('optimal', {})
                .get('top2_contribution_pct')
            ),
            'diagnostic_total_trade_value_pct': (
                recommendation.get('diagnostics', {})
                .get('turnover', {})
                .get('total_trade_value_pct')
            ),
            'diagnostic_market_regime_state': (
                recommendation.get('diagnostics', {})
                .get('market_regime', {})
                .get('state')
            ),
            'diagnostic_market_regime_triggers': (
                recommendation.get('diagnostics', {})
                .get('market_regime', {})
                .get('triggers', [])
            ),
            'diagnostic_benchmark_drawdown_3m_pct': (
                recommendation.get('diagnostics', {})
                .get('market_regime', {})
                .get('metrics', {})
                .get('benchmark_drawdown_3m_pct')
            ),
            'diagnostic_universe_negative_return_3m_pct': (
                recommendation.get('diagnostics', {})
                .get('market_regime', {})
                .get('metrics', {})
                .get('universe_negative_return_3m_pct')
            ),
            'shadow_decision': recommendation.get('shadow', {}).get('shadow_decision'),
            'shadow_trade_allowed': recommendation.get('shadow', {}).get('shadow_trade_allowed'),
            'shadow_expected_gain_pct': recommendation.get('shadow', {}).get('shadow_expected_gain_pct'),
            'shadow_hurdle_pct': recommendation.get('shadow', {}).get('shadow_hurdle_pct'),
            'shadow_signal_persistence_days': (
                recommendation.get('shadow', {}).get('shadow_signal_persistence_days')
            ),
            'shadow_turnover_pct': recommendation.get('shadow', {}).get('shadow_turnover_pct'),
            'shadow_turnover_budget_pct': recommendation.get('shadow', {}).get('shadow_turnover_budget_pct'),
            'shadow_target_quality_score': (
                recommendation.get('shadow', {}).get('portfolio_target_quality_score')
            ),
            'shadow_suspicious_return_contribution_share_pct': (
                recommendation.get('shadow', {}).get('suspicious_return_contribution_share_pct')
            ),
            'shadow_veto_codes': [
                veto.get('code')
                for veto in recommendation.get('shadow', {}).get('shadow_veto_reasons', [])
            ],
            'execution_state': (
                recommendation.get('shadow', {})
                .get('execution_plan', {})
                .get('decision_state')
            ),
            'execution_intensity_pct': (
                recommendation.get('shadow', {})
                .get('execution_plan', {})
                .get('execution_intensity_pct')
            ),
            'execution_trade_value_pct': (
                recommendation.get('shadow', {})
                .get('execution_plan', {})
                .get('executable_trade_value_pct')
            ),
            'execution_trade_value_brl': (
                recommendation.get('shadow', {})
                .get('execution_plan', {})
                .get('executable_trade_value_brl')
            ),
            'execution_num_actions': (
                recommendation.get('shadow', {})
                .get('execution_plan', {})
                .get('num_executable_actions')
            ),
            'stable_selected_blend_ratio': (
                recommendation.get('shadow', {})
                .get('stable_optimization', {})
                .get('selected_blend_ratio')
            ),
            'stable_official_blend_ratio': (
                recommendation.get('shadow', {})
                .get('stable_optimization', {})
                .get('official_blend_ratio')
            ),
            'stable_turnover_saved_pct': (
                recommendation.get('shadow', {})
                .get('stable_optimization', {})
                .get('turnover_saved_pct')
            ),
            'stable_adjusted_return_tradeoff_pct': (
                recommendation.get('shadow', {})
                .get('stable_optimization', {})
                .get('adjusted_return_tradeoff_pct')
            ),
            'stable_adjusted_return_delta_pct': (
                recommendation.get('shadow', {})
                .get('stable_optimization', {})
                .get('adjusted_return_delta_pct')
            ),
            'stable_selected_score': (
                recommendation.get('shadow', {})
                .get('stable_optimization', {})
                .get('selected_stable_score')
            ),
            'holdings_stocks': recommendation['comparison']['holdings']['stocks'],
            'ideal_stocks': recommendation['comparison']['ideal']['stocks'],
            'optimal_stocks': recommendation['comparison']['optimal']['stocks'],
        }

        with open(jsonl_path, 'a', encoding='utf-8') as f:
            f.write(json.dumps(history_row, ensure_ascii=False) + '\n')
        logger.info(f"Appended to JSONL history: {jsonl_path}")

    except Exception as e:
        logger.error(f"Error saving JSONL history: {e}")

    # Copy portfolio_results_db.csv to html/data for web access
    # NOTE: D_Publish.py now handles this
    pass


def copy_results_to_web(logger: logging.Logger):
    """Copy portfolio results CSV to web-accessible directory (or verify symlink exists)"""
    try:
        dest_path = os.path.join(WEB_DATA_PATH, 'portfolio_results_db.csv')
        os.makedirs(WEB_DATA_PATH, exist_ok=True)

        # Check if destination is already a symlink to the source
        if os.path.islink(dest_path):
            link_target = os.readlink(dest_path)
            if os.path.samefile(link_target, PORTFOLIO_RESULTS_DB):
                logger.info(f"Symlink already exists: {dest_path} -> {PORTFOLIO_RESULTS_DB}")
                return

        # Check if source exists
        if not os.path.exists(PORTFOLIO_RESULTS_DB):
            logger.warning(f"Portfolio results file not found: {PORTFOLIO_RESULTS_DB}")
            return

        # Check if files are the same (via symlink or hard link)
        if os.path.exists(dest_path) and os.path.samefile(PORTFOLIO_RESULTS_DB, dest_path):
            logger.info(f"Portfolio results already accessible at {dest_path}")
            return

        # Remove existing file if it's not a link to our source
        if os.path.exists(dest_path):
            os.remove(dest_path)

        # Copy the file
        shutil.copy2(PORTFOLIO_RESULTS_DB, dest_path)
        logger.info(f"Copied portfolio_results_db.csv to {dest_path}")

    except Exception as e:
        logger.error(f"Error copying portfolio results to web: {e}")


# ----------------------------------------------------------- #
#                           Main                              #
# ----------------------------------------------------------- #

def main():
    """Main execution function"""

    # Setup logger
    log_path = os.path.join(ROOT, 'logs', 'optimized.log')
    web_log_path = os.path.join(ROOT, 'html', 'data', 'optimized_web_log.json')
    os.makedirs(os.path.dirname(log_path), exist_ok=True)
    logger = setup_logger('OptimizedPortfolio', log_path, web_log_path, level=logging.INFO)

    logger.info("=" * 60)
    logger.info(f"C_OptimizedPortfolio.py v{OPTIMIZED_PORTFOLIO_VERSION}")
    logger.info(f"Execution started at {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    logger.info("=" * 60)

    # Load parameters
    params = load_parameters(logger)

    # Load ticker mapping
    ticker_mapping = load_ticker_mapping(logger)

    # Load current holdings
    holdings_df = load_current_holdings(logger)
    if holdings_df.empty:
        logger.error("No holdings found. Cannot generate optimization recommendation.")
        logger.info("Run B_Ledger.sh first to process your trade notes.")
        return 1

    # Calculate holdings metrics
    holdings = calculate_holdings_metrics(holdings_df, ticker_mapping, params, logger)
    logger.info(f"Holdings: {len(holdings['stocks'])} stocks, total value: {holdings['total_value']:.2f}")
    logger.info(f"Holdings expected return: {holdings['expected_return']:.2f}%")

    # ── Diagnostic: warn about holdings without target prices ──
    holdings_with_target = set(holdings.get('target_prices', {}).keys())
    holdings_with_hist = set(holdings.get('historical_returns', {}).keys())
    all_holdings = set(holdings.get('stocks', []))
    missing_target = all_holdings - holdings_with_target
    using_hist_only = missing_target & holdings_with_hist
    no_data = missing_target - holdings_with_hist

    if missing_target:
        logger.warning(
            f"⚠ {len(missing_target)} holdings have NO target price from Yahoo Finance: "
            f"{sorted(missing_target)}"
        )
        if using_hist_only:
            logger.warning(
                f"  → {sorted(using_hist_only)} are using historical return as fallback for hold_12m"
            )
        if no_data:
            logger.warning(
                f"  → {sorted(no_data)} have NO return data at all (contribute 0% to hold_12m)"
            )

    # Log per-asset details for hold_12m transparency
    for symbol in sorted(all_holdings):
        weight = holdings.get('weights', {}).get(symbol, 0) * 100
        current = holdings.get('current_prices', {}).get(symbol, 0)
        target = holdings.get('target_prices', {}).get(symbol, None)
        hist = holdings.get('historical_returns', {}).get(symbol, None)
        if target and current > 0:
            upside = (target - current) / current * 100
            logger.info(f"  {symbol}: w={weight:.1f}%, price={current:.2f}, target={target:.2f}, upside={upside:+.1f}%")
        elif hist is not None:
            logger.info(f"  {symbol}: w={weight:.1f}%, price={current:.2f}, NO TARGET → hist_return={hist*100:+.1f}%")
        else:
            logger.info(f"  {symbol}: w={weight:.1f}%, price={current:.2f}, NO TARGET, NO HIST → 0%")

    # Load ideal portfolio
    ideal = load_ideal_portfolio(logger)
    if not ideal:
        logger.error("No ideal portfolio found. Cannot generate optimization recommendation.")
        logger.info("Run A_Portfolio.sh first to generate the ideal portfolio.")
        return 1

    # Save original historical return before recalculating with target prices
    ideal['expected_return_annual_pct'] = ideal.get('expected_return', 0)

    # Recalculate ideal expected return using target prices (forward-looking)
    ideal_return_recalc = calculate_ideal_expected_return(ideal, logger)
    if ideal_return_recalc != 0:
        ideal['expected_return'] = ideal_return_recalc
    logger.info(f"Ideal portfolio: {len(ideal['stocks'])} stocks, "
               f"target-based return: {ideal['expected_return']:.2f}%, "
               f"historical return: {ideal['expected_return_annual_pct']:.2f}%")

    # Calculate transaction cost
    cost_mode = params.get('TRANSACTION_COST_MODE', 'DYNAMIC')
    if cost_mode.upper() == 'DYNAMIC':
        transaction_cost_pct = calculate_dynamic_transaction_cost(logger, params)
    else:
        transaction_cost_pct = float(params.get('TRANSACTION_COST_FIXED_PCT', 0.1))
    logger.info(f"Transaction cost: {transaction_cost_pct:.4f}% (mode: {cost_mode})")

    # Generate candidate portfolios
    num_candidates = int(params.get('NUM_CANDIDATE_PORTFOLIOS', 100))
    candidates = generate_candidate_portfolios(holdings, ideal, num_candidates, logger)

    # Find optimal portfolio (continuous weights)
    optimal = find_optimal_portfolio(
        holdings, ideal, candidates, transaction_cost_pct, params, logger
    )

    if optimal is None:
        logger.error("Could not find optimal portfolio")
        return 1

    logger.info(f"Optimal portfolio (continuous): blend_ratio={optimal['blend_ratio']:.2f}, "
               f"score={optimal['score']:.4f}, net_return={optimal['net_return']:.2f}%")

    stable_optimization = build_stable_optimization_shadow(
        holdings,
        candidates,
        transaction_cost_pct,
        params,
        logger,
    )
    if stable_optimization.get('enabled'):
        logger.info(
            "Stable shadow portfolio: "
            f"blend_ratio={stable_optimization.get('selected_blend_ratio'):.2f}, "
            f"stable_score={stable_optimization.get('selected_stable_score'):.4f}, "
            f"turnover_saved={stable_optimization.get('turnover_saved_pct'):.2f}%"
        )

    # ── Discretize to integer shares (B3 constraint) ──────────────────
    # MVO optimises in continuous weight-space, but B3 only allows
    # integer shares.  Discretize the optimal portfolio and recalculate
    # ALL metrics so the recommendation reflects the executable portfolio.
    #
    # IMPORTANT: Use the total_current_market from ledger_positions.json
    # for consistency with D_Publish.py (which generates pipeline_latest.json).
    # This ensures recommended transactions match the model portfolio shown
    # in the "Alocação do Modelo" table.
    logger.info("Discretizing optimal portfolio to integer shares (B3)...")

    # Load portfolio market value from ledger_positions.json for consistency
    portfolio_value_for_discretization = holdings['total_value']
    try:
        with open(LEDGER_POSITIONS_JSON, 'r', encoding='utf-8') as f:
            ledger_data = json.load(f)
            ledger_total_market = ledger_data.get('total_current_market', 0)
            if ledger_total_market > 0:
                portfolio_value_for_discretization = ledger_total_market
                logger.info(f"Using ledger total_current_market ({ledger_total_market:.2f}) for discretization "
                           f"(was calculated as {holdings['total_value']:.2f})")
    except Exception as e:
        logger.warning(f"Could not load ledger_positions.json: {e}. Using calculated total_value.")

    disc_weights, share_qtys, disc_total = discretize_to_integer_shares(
        optimal['weights'], portfolio_value_for_discretization, logger
    )

    # Save continuous version for transparency
    optimal['weights_continuous'] = optimal['weights']
    optimal['expected_return_continuous'] = optimal.get('expected_return', 0)

    # Replace weights with discretized version
    optimal['weights'] = disc_weights
    optimal['stocks'] = list(disc_weights.keys())
    optimal['share_quantities'] = share_qtys
    optimal['total_discretized'] = disc_total
    optimal['discretized'] = True

    # Recalculate expected return using discretized weights + target prices
    disc_return = 0.0
    stocks_with_target = 0
    for stock, weight in disc_weights.items():
        current = get_current_price(stock, logger)
        target = get_target_price(stock, logger)
        if current and target and current > 0:
            disc_return += weight * ((target - current) / current)
            stocks_with_target += 1
    disc_return *= 100  # to percentage

    # Recalculate transition cost with discretized weights
    disc_cost, _ = calculate_transition_cost(
        holdings, optimal, transaction_cost_pct, logger
    )

    optimal['expected_return'] = disc_return
    optimal['transition_cost'] = disc_cost
    optimal['net_return'] = disc_return - disc_cost

    logger.info(
        f"Discretized optimal: {len(disc_weights)} positions, "
        f"return: {disc_return:.2f}% (continuous was {optimal['expected_return_continuous']:.2f}%), "
        f"net: {optimal['net_return']:.2f}%, "
        f"invested: {disc_total:.2f} BRL ({stocks_with_target}/{len(disc_weights)} with target price)"
    )

    # Generate recommendation (uses discretized weights)
    recommendation = generate_recommendation(
        holdings, ideal, optimal, stable_optimization, transaction_cost_pct, params, logger
    )

    # Save results
    save_recommendation(recommendation, params, logger)

    # Print summary
    logger.info("=" * 60)
    logger.info("RECOMMENDATION SUMMARY")
    logger.info("=" * 60)
    logger.info(f"Decision: {recommendation['decision']}")
    logger.info(f"Reason: {recommendation['reason']}")
    logger.info(f"Holdings return: {recommendation['comparison']['holdings']['expected_return_pct']:.2f}%")
    logger.info(f"Optimal net return: {recommendation['comparison']['optimal']['net_return_pct']:.2f}%")
    logger.info(f"Excess return: {recommendation['excess_return_pct']:.2f}%")

    if recommendation['transactions']:
        logger.info(f"\nTransactions ({len(recommendation['transactions'])}):")
        for tx in recommendation['transactions']:
            logger.info(f"  {tx['action']} {tx['symbol']}: "
                       f"{tx['current_weight']*100:.1f}% -> {tx['target_weight']*100:.1f}%")

    logger.info("=" * 60)
    logger.info("Execution completed successfully")

    return 0


if __name__ == '__main__':
    sys.exit(main())
