#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
B4_Portfolio_History.py

Generates historical portfolio value data based on:
- Transaction history (ledger.csv)
- Daily stock prices (findata)

Output: html/data/portfolio_history.json
"""

import os
import sys
import json
import pandas as pd
from datetime import datetime, timedelta
from pathlib import Path

# ═══════════════════════════════════════════════════════════════════════════════
# CONFIGURAÇÃO
# ═══════════════════════════════════════════════════════════════════════════════

BASE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = BASE_DIR / 'data'
HTML_DATA_DIR = BASE_DIR / 'html' / 'data'
FINDATA_DIR = DATA_DIR / 'findata'
LEDGER_CSV = HTML_DATA_DIR / 'ledger.csv'
OUTPUT_FILE = HTML_DATA_DIR / 'portfolio_history.json'


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


def get_stock_price(symbol, date):
    """Get the closing price for a stock on a given date"""
    # Clean symbol for folder lookup
    if '.SA' not in symbol:
        symbol = f"{symbol}.SA"

    symbol_dir = FINDATA_DIR / symbol

    if not symbol_dir.exists():
        return None

    # Try exact date first
    date_str = date.strftime('%Y-%m-%d')
    csv_file = symbol_dir / f"StockData_{symbol}_{date_str}.csv"

    if csv_file.exists():
        try:
            df = pd.read_csv(csv_file)
            if 'Close' in df.columns and len(df) > 0:
                return float(df['Close'].iloc[0])
        except Exception:
            pass

    # Try to find the nearest previous trading day (up to 10 days back)
    for days_back in range(1, 11):
        prev_date = date - timedelta(days=days_back)
        date_str = prev_date.strftime('%Y-%m-%d')
        csv_file = symbol_dir / f"StockData_{symbol}_{date_str}.csv"

        if csv_file.exists():
            try:
                df = pd.read_csv(csv_file)
                if 'Close' in df.columns and len(df) > 0:
                    return float(df['Close'].iloc[0])
            except Exception:
                pass

    return None


def normalize_symbol(ticker_name):
    """Convert ticker name from ledger to Yahoo Finance symbol"""
    # Mapping of known ticker names to symbols
    mappings = {
        'COPASA ON NM': 'CSMG3.SA',
        'PLANOEPLANO ON NM': 'PLPL3.SA',
        'VULCABRAS ON NM': 'VULC3.SA',
        'VULCABRAS ON ED NM': 'VULC3.SA',
        'VULCABRAS ON EDS NM': 'VULC3.SA',
        'VULCABRAS DO 13,75': None,  # Dividend, skip
        'LAVVI ON NM': 'LAVV3.SA',
        'AXIA ENERGIAPNB EX N1': 'AXIA6.SA',
        'MOURA DUBEUXON ED NM': 'MDNE3.SA',
        'TENDA ON ED NM': 'TEND3.SA',
        'VALE ON NM': 'VALE3.SA',
        'AURA 360 DR3': 'AURA33.SA',
    }

    return mappings.get(ticker_name, None)


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

        # Only add entry if we have holdings and price data
        if has_price_data and total_cost > 0:
            day_transactions = transactions_by_date.get(current_date, None)

            entry = {
                'date': current_date.isoformat(),
                'market_value': round(total_market_value, 2),
                'cost_basis': round(total_cost, 2),
                'profit_loss': round(total_market_value - total_cost, 2),
                'profit_loss_pct': round(((total_market_value / total_cost) - 1) * 100, 2) if total_cost > 0 else 0,
                'positions': position_details
            }

            if day_transactions:
                entry['transactions'] = day_transactions

            history.append(entry)

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
        history = []
    else:
        print(f"[INFO] Loaded {len(transactions_df)} transactions")

        # Build history
        history = build_portfolio_history(transactions_df)
        print(f"[INFO] Generated {len(history)} daily records")

    # Save output
    output = {
        'generated_at': datetime.now().isoformat(),
        'history': history
    }

    OUTPUT_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(OUTPUT_FILE, 'w', encoding='utf-8') as f:
        json.dump(output, f, indent=2, ensure_ascii=False)

    print(f"[INFO] Saved portfolio history to: {OUTPUT_FILE}")


if __name__ == '__main__':
    main()
