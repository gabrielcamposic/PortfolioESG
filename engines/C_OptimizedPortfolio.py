#!/usr/bin/env python3
"""
C_OptimizedPortfolio.py

Combines the ideal portfolio from A_Portfolio with current holdings from B_Ledger
to generate an optimized transition recommendation that maximizes return while
considering transaction costs.

Usage:
    python3 engines/C_OptimizedPortfolio.py

Outputs:
    - data/results/optimized_portfolio_history.csv (histórico de decisões)
    - html/data/optimized_recommendation.json (última recomendação)
"""

# --- Script Version ---
OPTIMIZED_PORTFOLIO_VERSION = "1.0.0"

# ----------------------------------------------------------- #
#                           Libraries                         #
# ----------------------------------------------------------- #
import pandas as pd
import os
import sys
import json
import logging
import shutil
from datetime import datetime, timedelta
from typing import Dict, Any, List, Tuple, Optional

# --- Import Shared Utilities ---
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from shared_tools.shared_utils import (
    setup_logger,
    load_parameters_from_file,
)

# ----------------------------------------------------------- #
#                        Configuration                        #
# ----------------------------------------------------------- #

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PARAMS_FILE = os.path.join(ROOT, 'parameters', 'optpar.txt')
PATHS_FILE = os.path.join(ROOT, 'parameters', 'paths.txt')

# Data files
LEDGER_CSV = os.path.join(ROOT, 'data', 'ledger.csv')
LEDGER_POSITIONS_JSON = os.path.join(ROOT, 'html', 'data', 'ledger_positions.json')
LATEST_RUN_JSON = os.path.join(ROOT, 'html', 'data', 'latest_run_summary.json')
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

            _FINANCIALS_CACHE[ticker] = {
                'current_price': row.get('currentPrice') or row.get('CurrentPrice'),
                'target_price': row.get('targetMeanPrice') or row.get('TargetMeanPrice') or row.get('TargetPrice'),
                'forward_pe': row.get('forwardPE') or row.get('ForwardPE'),
                'forward_eps': row.get('forwardEPS') or row.get('forwardEps') or row.get('ForwardEps'),
            }

        logger.info(f"Loaded financials for {len(_FINANCIALS_CACHE)} tickers from FinancialsDB")

        # Also try to load target prices from scored_stocks.csv (more complete data)
        scored_stocks_path = os.path.join(FINDB_PATH, '..', 'Results', 'scored_stocks.csv')
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

                    if stock not in _FINANCIALS_CACHE:
                        _FINANCIALS_CACHE[stock] = {}

                    # Update with scored_stocks data if available and valid
                    if pd.notna(current_price) and current_price > 0:
                        _FINANCIALS_CACHE[stock]['current_price'] = float(current_price)
                    if pd.notna(target_price) and target_price > 0:
                        _FINANCIALS_CACHE[stock]['target_price'] = float(target_price)
                        updated_count += 1
                    if pd.notna(row.get('forwardPE')) and row.get('forwardPE') > 0:
                        _FINANCIALS_CACHE[stock]['forward_pe'] = float(row.get('forwardPE'))
                    if pd.notna(row.get('forwardEPS')):
                        _FINANCIALS_CACHE[stock]['forward_eps'] = float(row.get('forwardEPS'))

                logger.info(f"Updated {updated_count} tickers with target prices from scored_stocks.csv")
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
            'sharpe_ratio': portfolio.get('sharpe_ratio', 0),
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
    """Get current price for a symbol from StockDataDB (latest available price)"""
    symbol_clean = symbol.replace('.SA', '') + '.SA' if '.SA' not in symbol else symbol

    # First try FinancialsDB for currentPrice
    financials = _load_financials_db(logger)
    if symbol_clean in financials:
        current = financials[symbol_clean].get('current_price')
        if current and pd.notna(current):
            return float(current)

    # Fall back to StockDataDB (most recent close price)
    prices_db = _load_stock_prices_db(logger)
    if symbol_clean not in prices_db:
        return None

    ticker_prices = prices_db[symbol_clean]
    if not ticker_prices:
        return None

    # Get the most recent date's price
    sorted_dates = sorted(ticker_prices.keys(), reverse=True)
    if sorted_dates:
        return ticker_prices[sorted_dates[0]]

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
        ticker = row.get('ticker', row.get('symbol', ''))
        symbol = normalize_symbol(ticker, ticker_mapping)
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


def calculate_transition_cost(
    holdings: Dict[str, Any],
    target: Dict[str, Any],
    transaction_cost_pct: float,
    logger: logging.Logger
) -> Tuple[float, List[Dict]]:
    """
    Calculate the cost of transitioning from holdings to target portfolio.
    Returns (total_cost_pct, list_of_transactions)
    """
    holdings_weights = holdings.get('weights', {})
    target_weights = target.get('weights', {})
    holdings_value = holdings.get('total_value', 0)

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

        value_change = abs(weight_diff) * holdings_value
        total_traded_value += value_change

        action = 'BUY' if weight_diff > 0 else 'SELL'
        transactions.append({
            'symbol': stock,
            'action': action,
            'weight_change': weight_diff,
            'value_change': value_change,
            'current_weight': current_weight,
            'target_weight': target_weight,
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

    # Normalize values (simple min-max normalization with assumed ranges)
    # Expected return: assume -20% to +100%
    norm_return = (expected_return + 20) / 120 if expected_return is not None else 0
    norm_return = max(0, min(1, norm_return))

    # Sharpe ratio: assume -1 to +3
    norm_sharpe = (sharpe_ratio + 1) / 4 if sharpe_ratio is not None else 0
    norm_sharpe = max(0, min(1, norm_sharpe))

    # Momentum: assume -1 to +2
    norm_momentum = (momentum + 1) / 3 if momentum is not None else 0
    norm_momentum = max(0, min(1, norm_momentum))

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
        candidate['momentum'] = momentum
        candidate['score'] = score

        if score > best_score:
            best_score = score
            best_candidate = candidate
            best_net_return = net_return

    return best_candidate


def generate_recommendation(
    holdings: Dict[str, Any],
    ideal: Dict[str, Any],
    optimal: Dict[str, Any],
    transaction_cost_pct: float,
    params: Dict,
    logger: logging.Logger
) -> Dict[str, Any]:
    """Generate the final recommendation"""

    min_excess_threshold = float(params.get('MIN_EXCESS_RETURN_THRESHOLD', 0.5))

    holdings_return = holdings.get('expected_return', 0)
    optimal_net_return = optimal.get('net_return', 0)
    excess_return = optimal_net_return - holdings_return

    # Calculate transactions
    _, transactions = calculate_transition_cost(
        holdings, optimal, transaction_cost_pct, logger
    )

    # Determine decision
    if excess_return >= min_excess_threshold:
        decision = 'REBALANCE'
        reason = f"Excess return ({excess_return:.2f}%) exceeds threshold ({min_excess_threshold}%)"
    elif optimal.get('blend_ratio', 0) < 0.1:
        decision = 'HOLD'
        reason = f"Optimal portfolio is very close to current holdings"
    else:
        decision = 'HOLD'
        reason = f"Excess return ({excess_return:.2f}%) below threshold ({min_excess_threshold}%)"

    recommendation = {
        'date': datetime.now().strftime('%Y-%m-%d'),
        'timestamp': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
        'decision': decision,
        'reason': reason,
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
        'comparison': {
            'window_days': int(params.get('EXPECTED_RETURN_WINDOW_DAYS', 252)),
            'holdings': {
                'stocks': holdings.get('stocks', []),
                'weights': holdings.get('weights', {}),
                'expected_return_pct': round(holdings_return, 2),
                'total_value': round(holdings.get('total_value', 0), 2),
                'total_invested': round(holdings.get('total_invested', 0), 2),
            },
            'ideal': {
                'stocks': ideal.get('stocks', []),
                'weights': ideal.get('weights', {}),
                'expected_return_pct': round(ideal.get('expected_return', 0), 2),  # Based on target prices
                'historical_return_pct': round(ideal.get('expected_return_annual_pct', ideal.get('expected_return', 0)), 2),  # Based on historical data
                'sharpe_ratio': round(ideal.get('sharpe_ratio', 0), 4),
                'run_id': ideal.get('run_id', ''),
            },
            'optimal': {
                'stocks': optimal.get('stocks', []),
                'weights': optimal.get('weights', {}),
                'expected_return_pct': round(optimal.get('expected_return', 0), 2),  # Based on target prices
                'net_return_pct': round(optimal_net_return, 2),
                'blend_ratio': round(optimal.get('blend_ratio', 0), 2),
                'transition_cost_pct': round(optimal.get('transition_cost', 0), 4),
            },
        },
        'transactions': transactions,
        'transaction_cost_pct_used': round(transaction_cost_pct, 4),
        'parameters': {
            'weight_expected_return': float(params.get('WEIGHT_EXPECTED_RETURN', 0.4)),
            'weight_sharpe_ratio': float(params.get('WEIGHT_SHARPE_RATIO', 0.4)),
            'weight_momentum': float(params.get('WEIGHT_MOMENTUM', 0.2)),
        }
    }

    logger.info(f"Decision: {decision} - {reason}")

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
                   os.path.join(ROOT, 'html', 'data', 'optimized_recommendation.json'))
    )
    os.makedirs(os.path.dirname(json_path), exist_ok=True)

    try:
        with open(json_path, 'w', encoding='utf-8') as f:
            json.dump(recommendation, f, indent=2, ensure_ascii=False)
        logger.info(f"Saved recommendation JSON to: {json_path}")
    except Exception as e:
        logger.error(f"Error saving recommendation JSON: {e}")

    # Append to CSV history
    csv_path = os.path.expanduser(
        params.get('OPTIMIZED_RESULTS_FILE',
                   os.path.join(ROOT, 'data', 'results', 'optimized_portfolio_history.csv'))
    )
    os.makedirs(os.path.dirname(csv_path), exist_ok=True)

    try:
        history_row = {
            'date': recommendation['date'],
            'timestamp': recommendation['timestamp'],
            'decision': recommendation['decision'],
            'reason': recommendation['reason'],
            'excess_return_pct': recommendation['excess_return_pct'],
            'optimal_score': recommendation['optimal_score'],
            'holdings_score': recommendation['holdings_score'],
            'ideal_score': recommendation['ideal_score'],
            'holdings_return_pct': recommendation['comparison']['holdings']['expected_return_pct'],
            'ideal_return_pct': recommendation['comparison']['ideal']['expected_return_pct'],
            'optimal_return_pct': recommendation['comparison']['optimal']['expected_return_pct'],
            'optimal_net_return_pct': recommendation['comparison']['optimal']['net_return_pct'],
            'blend_ratio': recommendation['comparison']['optimal']['blend_ratio'],
            'transition_cost_pct': recommendation['comparison']['optimal']['transition_cost_pct'],
            'transaction_cost_pct_used': recommendation['transaction_cost_pct_used'],
            'num_transactions': len(recommendation['transactions']),
            'holdings_stocks': ','.join(recommendation['comparison']['holdings']['stocks']),
            'ideal_stocks': ','.join(recommendation['comparison']['ideal']['stocks']),
            'optimal_stocks': ','.join(recommendation['comparison']['optimal']['stocks']),
        }

        df = pd.DataFrame([history_row])
        df.to_csv(csv_path, mode='a', header=not os.path.exists(csv_path), index=False)
        logger.info(f"Appended to CSV history: {csv_path}")

    except Exception as e:
        logger.error(f"Error saving CSV history: {e}")

    # Copy portfolio_results_db.csv to html/data for web access
    copy_results_to_web(logger)


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

    # Find optimal portfolio
    optimal = find_optimal_portfolio(
        holdings, ideal, candidates, transaction_cost_pct, params, logger
    )

    if optimal is None:
        logger.error("Could not find optimal portfolio")
        return 1

    logger.info(f"Optimal portfolio: blend_ratio={optimal['blend_ratio']:.2f}, "
               f"score={optimal['score']:.4f}, net_return={optimal['net_return']:.2f}%")

    # Generate recommendation
    recommendation = generate_recommendation(
        holdings, ideal, optimal, transaction_cost_pct, params, logger
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

