#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
engines/B4_Portfolio_History.py

Generates historical portfolio value data based on:
- Transaction history (ledger.csv)
- Daily stock prices (StockDataDB.csv)

Output: data/portfolio_history.csv
"""

# --- Script Version ---
PORTFOLIO_HISTORY_VERSION = "3.1.0"  # Shared ticker normalization + skip weekends

import sys
import logging
import pandas as pd
from datetime import datetime, timedelta
from pathlib import Path

# ═══════════════════════════════════════════════════════════════════════════════
# CONFIGURAÇÃO
# ═══════════════════════════════════════════════════════════════════════════════

BASE_DIR = Path(__file__).resolve().parent.parent

# Ensure project root is on sys.path
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

DATA_DIR = BASE_DIR / 'data'
HTML_DATA_DIR = BASE_DIR / 'html' / 'data'
FINDB_DIR = DATA_DIR / 'findb'
STOCK_DATA_DB = FINDB_DIR / 'StockDataDB.csv'
LEDGER_CSV = DATA_DIR / 'ledger.csv'
OUTPUT_FILE = DATA_DIR / 'portfolio_history.csv'

# Simple logging
logging.basicConfig(level=logging.INFO, format='%(message)s')
logger = logging.getLogger('PortfolioHistory')

# Global cache for stock prices loaded from StockDataDB
_STOCK_PRICES_CACHE = None


def load_transactions():
    """Load transactions from ledger.csv"""
    if not LEDGER_CSV.exists():
        print(f"[WARN] Ledger file not found: {LEDGER_CSV}")
        return pd.DataFrame()

    df = pd.read_csv(LEDGER_CSV)

    # Ensure trade_date is datetime
    df['trade_date'] = pd.to_datetime(df['trade_date'])

    # Sort by date
    df = df.sort_values('trade_date')

    return df


def _load_stock_prices_db():
    """Load all stock prices from StockDataDB.csv into memory cache"""
    global _STOCK_PRICES_CACHE

    if _STOCK_PRICES_CACHE is not None:
        return _STOCK_PRICES_CACHE

    _STOCK_PRICES_CACHE = {}

    if not STOCK_DATA_DB.exists():
        print(f"[WARN] StockDataDB not found: {STOCK_DATA_DB}")
        return _STOCK_PRICES_CACHE

    try:
        print(f"[INFO] Loading stock prices from {STOCK_DATA_DB}...")
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

        print(f"[INFO] Loaded prices for {len(_STOCK_PRICES_CACHE)} tickers")
    except Exception as e:
        print(f"[ERROR] Failed to load StockDataDB: {e}")

    return _STOCK_PRICES_CACHE


def get_stock_price(symbol, date):
    """Get the closing price for a stock on a given date from StockDataDB"""
    # Clean symbol for lookup
    if '.SA' not in symbol and not symbol.startswith('^'):
        symbol = f"{symbol}.SA"

    prices_db = _load_stock_prices_db()

    if symbol not in prices_db:
        return None

    ticker_prices = prices_db[symbol]
    date_str = date.strftime('%Y-%m-%d')

    # Try exact date first
    if date_str in ticker_prices:
        return ticker_prices[date_str]

    # Try to find the nearest previous trading day (up to 10 days back)
    for days_back in range(1, 11):
        prev_date = date - timedelta(days=days_back)
        prev_date_str = prev_date.strftime('%Y-%m-%d')
        if prev_date_str in ticker_prices:
            return ticker_prices[prev_date_str]

    return None


from shared_tools.ticker_normalization import resolve_broker_ticker


def normalize_symbol(ticker_name):
    """
    Convert ticker name from ledger (broker format) to Yahoo Finance symbol.

    Delegates to shared_tools.ticker_normalization.resolve_broker_ticker()
    which handles exact matches, corporate-action modifier stripping (EX/EDS/ED),
    company name matching, and prefix matching.
    """
    result = resolve_broker_ticker(ticker_name)
    if result is None and ticker_name and ticker_name.strip():
        # Only warn for entries that aren't skip-pattern matches
        skip_patterns = [' DO ', ' DIR ', ' SUB ', ' BON ']
        upper = ticker_name.upper()
        if not any(p in upper for p in skip_patterns):
            print(f"[WARN] Unknown ticker '{ticker_name}' - please add BrokerName mapping to tickers.txt")
    return result


def build_portfolio_history(transactions_df):
    """Build daily portfolio history from transactions"""
    if transactions_df.empty:
        return []

    # Get date range
    first_date = transactions_df['trade_date'].min()
    last_date = datetime.now()

    # Build holdings map: date -> {symbol: qty}
    holdings_by_date = {}
    cost_basis_by_date = {}
    transactions_by_date = {}

    current_holdings = {}  # symbol -> qty
    current_cost_basis = {}  # symbol -> total_cost

    # Process transactions
    for _, tx in transactions_df.iterrows():
        date = tx['trade_date'].date()
        ticker = tx['ticker']
        symbol = normalize_symbol(ticker)

        if symbol is None:
            continue

        side = tx['side'].upper()
        qty = float(tx['quantity'])
        total_cost = float(tx['total_cost'])

        if symbol not in current_holdings:
            current_holdings[symbol] = 0
            current_cost_basis[symbol] = 0

        if side == 'BUY':
            current_holdings[symbol] += qty
            current_cost_basis[symbol] += total_cost
        else:  # SELL
            # Calculate proportional cost reduction
            if current_holdings[symbol] > 0:
                avg_cost = current_cost_basis[symbol] / current_holdings[symbol]
                current_cost_basis[symbol] -= avg_cost * qty
            current_holdings[symbol] -= qty

        # Record transaction
        if date not in transactions_by_date:
            transactions_by_date[date] = []
        transactions_by_date[date].append({
            'symbol': symbol,
            'side': side,
            'qty': qty,
            'price': float(tx['unit_price']),
            'total': total_cost
        })

    # Generate daily history
    history = []
    current_date = first_date.date()
    end_date = last_date.date()

    running_holdings = {}
    running_cost_basis = {}

    while current_date <= end_date:
        # T3: Skip weekends (Saturday=5, Sunday=6)
        if current_date.weekday() >= 5:
            current_date += timedelta(days=1)
            continue

        # Update holdings from transactions on this date
        if current_date in transactions_by_date:
            for tx in transactions_by_date[current_date]:
                symbol = tx['symbol']
                if symbol not in running_holdings:
                    running_holdings[symbol] = 0
                    running_cost_basis[symbol] = 0

                if tx['side'] == 'BUY':
                    running_holdings[symbol] += tx['qty']
                    running_cost_basis[symbol] += tx['total']
                else:
                    if running_holdings[symbol] > 0:
                        avg_cost = running_cost_basis[symbol] / running_holdings[symbol]
                        running_cost_basis[symbol] -= avg_cost * tx['qty']
                    running_holdings[symbol] -= tx['qty']

        # Calculate market value
        total_market_value = 0
        total_cost = 0
        position_details = []
        has_price_data = False

        for symbol, qty in running_holdings.items():
            if qty <= 0:
                continue

            price = get_stock_price(symbol, datetime.combine(current_date, datetime.min.time()))

            if price is not None:
                has_price_data = True
                market_value = qty * price
                cost = running_cost_basis.get(symbol, 0)

                total_market_value += market_value
                total_cost += cost

                position_details.append({
                    'symbol': symbol,
                    'qty': qty,
                    'price': round(price, 2),
                    'value': round(market_value, 2)
                })

        # Only add entries if we have holdings and price data
        if has_price_data and total_cost > 0:
            for pos in position_details:
                history.append({
                    'date': current_date.isoformat(),
                    'symbol': pos['symbol'],
                    'qty': pos['qty'],
                    'price': pos['price'],
                    'value': pos['value'],
                    'market_value': round(total_market_value, 2),
                    'cost_basis': round(total_cost, 2),
                    'pnl': round(total_market_value - total_cost, 2),
                    'pnl_pct': round(((total_market_value / total_cost) - 1) * 100, 2) if total_cost > 0 else 0,
                })

        current_date += timedelta(days=1)

    return history


def main():
    print(f"[INFO] Starting portfolio history generation...")
    print(f"[INFO] Base dir: {BASE_DIR}")
    print(f"[INFO] Ledger file: {LEDGER_CSV}")

    # Load transactions
    transactions_df = load_transactions()

    if transactions_df.empty:
        print("[WARN] No transactions found. Creating empty history.")
        rows = []
    else:
        print(f"[INFO] Loaded {len(transactions_df)} transactions")

        # Build history
        rows = build_portfolio_history(transactions_df)
        n_dates = len(set(r['date'] for r in rows))
        print(f"[INFO] Generated {len(rows)} position rows across {n_dates} dates")

    # Save output as CSV
    OUTPUT_FILE.parent.mkdir(parents=True, exist_ok=True)
    df = pd.DataFrame(rows) if rows else pd.DataFrame(
        columns=['date', 'symbol', 'qty', 'price', 'value', 'market_value', 'cost_basis', 'pnl', 'pnl_pct']
    )
    df.to_csv(OUTPUT_FILE, index=False)

    print(f"[INFO] Saved portfolio history to: {OUTPUT_FILE}")


if __name__ == '__main__':
    main()
