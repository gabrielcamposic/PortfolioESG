#!/usr/bin/env python3
"""
Generate JSON files consumed by html/ledger.js:
 - data/ledger_positions.json   : array { positions: [...] }
 - data/pipeline_latest.json    : latest pipeline composition + computed projected quantities and totals
 - data/scored_targets.json     : mapping of normalized ticker -> target price and symbol map

This script mirrors logic from html/js/ledger.js but runs server-side so the frontend can fetch ready-made JSON.
"""

import csv
import json
import math
import os
from datetime import datetime, timezone
from typing import List, Dict, Any, Optional, Tuple

# Explicit paths used in this repository
LEDGER_CSV = os.path.join('data', 'ledger.csv')
PIPELINE_CSV = os.path.join('data', 'results', 'portfolio_results_db.csv')
FINDB_STOCKDB = os.path.join('data', 'findb', 'StockDataDB.csv')
SCORED_STOCKS = os.path.join('data', 'results', 'scored_stocks.csv')
LATEST_RUN_SUMMARY = os.path.join('html', 'data', 'latest_run_summary.json')

OUTPUT_LEDGER_JSON = os.path.join('html','data','ledger_positions.json')
OUTPUT_LEDGER_CSV = os.path.join('html','data','ledger.csv')
OUTPUT_PIPELINE_JSON = os.path.join('html','data','pipeline_latest.json')
OUTPUT_SCORED_JSON = os.path.join('html','data','scored_targets.json')

CSV_ENCODING = 'utf-8'

# Utilities

def safe_parse_float(v):
    if v is None:
        return 0.0
    if isinstance(v, (int, float)):
        return float(v)
    try:
        s = str(v).strip()
        if s == '':
            return 0.0
        # remove currency symbols and thousands separators
        cleaned = ''.join(ch for ch in s if ch.isdigit() or ch in '.-eE')
        return float(cleaned) if cleaned not in ('', '.', '-', '+') else 0.0
    except Exception:
        return 0.0


def normalize_ticker(s: Optional[str]) -> str:
    if not s:
        return ''
    s2 = str(s).upper()
    for ch in [' ', '.', '-', '/']:
        s2 = s2.replace(ch, '')
    s2 = ''.join([c for c in s2 if c.isalnum()])
    return s2


def normalize_broker_ticker(ticker: str) -> str:
    """
    Normalize broker ticker names to consolidate variations of the same stock.
    Brazilian brokers often use different suffixes like 'ON NM', 'ON ED NM', 'ON EDS NM', etc.
    This function extracts the base company name for grouping purposes.

    Examples:
        'VULCABRAS ON NM' -> 'VULCABRAS'
        'VULCABRAS ON ED NM' -> 'VULCABRAS'
        'VULCABRAS ON EDS NM' -> 'VULCABRAS'
        'VALE ON NM' -> 'VALE'
        'COPASA ON NM' -> 'COPASA'
        'MOURA DUBEUXON ED NM' -> 'MOURA DUBEUX' (handles glued ON)
        'AXIA ENERGIAPNB EX N1' -> 'AXIA ENERGIA' (handles glued PNB)

    Special cases (dividends, rights, etc.) are kept separate:
        'VULCABRAS DO 13,75' -> 'VULCABRAS DO 13,75' (dividend/right, keep as is)
    """
    if not ticker:
        return ''

    t = str(ticker).strip().upper()

    # Skip normalization for special instruments (dividends, rights, subscriptions)
    # These typically have patterns like "DO", "DIR", "SUB", followed by numbers or specific codes
    special_patterns = [' DO ', ' DIR ', ' SUB ', ' BON ']
    for pat in special_patterns:
        if pat in t:
            return ticker  # Return original for special instruments

    # Common suffixes used by Brazilian brokers that indicate share class/listing
    # Order matters - longer/more specific patterns first
    suffixes_to_remove = [
        'ON EDS NM', 'ON ED NM', 'ON E NM', 'ON NM', 'ON N2', 'ON N1', 'ON MB',
        'PN EDS NM', 'PN ED NM', 'PN E NM', 'PN NM', 'PN N2', 'PN N1', 'PN MB',
        'PNA EDS NM', 'PNA ED NM', 'PNA NM', 'PNB EDS NM', 'PNB ED NM', 'PNB NM',
        'PNB EX N1', 'PNB EX N2', 'PNB EX NM',  # Ex-rights patterns
        'UNT EDS NM', 'UNT ED NM', 'UNT NM', 'UNT N2',
        'CI EDS', 'CI ED', 'CI',
        'DR3', 'DR2', 'DR1',
        'EDS NM', 'ED NM', 'NM', 'N2', 'N1', 'MB',
        'EX N1', 'EX N2', 'EX NM',  # Ex-rights patterns
        'ON', 'PN', 'PNA', 'PNB', 'UNT',
    ]

    result = t
    for suffix in suffixes_to_remove:
        # Check if ends with suffix (with or without leading space)
        if result.endswith(' ' + suffix):
            result = result[:-(len(suffix)+1)].strip()
            break
        elif result.endswith(suffix):
            result = result[:-len(suffix)].strip()
            break

    # Handle cases where ON/PN/PNA/PNB is glued to the company name (no space)
    # e.g., "MOURA DUBEUXON" -> "MOURA DUBEUX", "AXIA ENERGIAPNB" -> "AXIA ENERGIA"
    import re
    # Pattern: word boundary followed by ON/PN/PNA/PNB at end
    glued_patterns = [
        (r'(\w)ON$', r'\1'),      # DUBEUXON -> DUBEUX
        (r'(\w)PNB$', r'\1'),     # ENERGIAPNB -> ENERGIA
        (r'(\w)PNA$', r'\1'),     # Similar pattern
        (r'(\w)PN$', r'\1'),      # Similar pattern
    ]
    for pattern, replacement in glued_patterns:
        if re.search(pattern, result):
            result = re.sub(pattern, replacement, result)
            break

    return result.strip() if result else ticker


# FIFO lot-based aggregation for ledger.csv

def aggregate_ledger_from_csv(path: str) -> Tuple[List[Dict[str,Any]], float, float]:
    """
    Read data/ledger.csv and perform FIFO lot accounting per ticker.
    Returns (positions_list, total_current_market_value, total_invested_cash)
    positions_list: [{ ticker, symbol, net_qty, net_invested, lots: [{qty, unit_cost}] }]
    total_current_market_value: float (sum qty * latest_price if available will be updated later)
    total_invested_cash: sum of money spent on open lots (sum of lot qty * unit_cost)
    """
    if not os.path.exists(path):
        return [], 0.0, 0.0

    # Structure: per-normalized-ticker lots list (fifo)
    lots_by_ticker: Dict[str, List[Dict[str, Any]]] = {}
    # Track the most recent original ticker name for each normalized key
    original_ticker_names: Dict[str, str] = {}
    # We'll also keep realized P/L per ticker (optional)
    realized_by_ticker: Dict[str, float] = {}

    # We'll parse the CSV streaming
    with open(path, encoding=CSV_ENCODING, errors='replace') as fh:
        reader = csv.DictReader(fh)
        for row in reader:
            # Identify fields
            raw_ticker = (row.get('ticker') or row.get('Ticker') or row.get('symbol') or row.get('Symbol') or '').strip()
            if not raw_ticker:
                continue

            # Normalize ticker for consolidation (e.g., "VULCABRAS ON NM" and "VULCABRAS ON ED NM" -> "VULCABRAS")
            ticker_key = normalize_broker_ticker(raw_ticker)

            side = (row.get('side') or row.get('Side') or '').strip().upper()
            qty = safe_parse_float(row.get('quantity') or row.get('qty') or row.get('quantity') or row.get('Quantity') or 0)
            # Use total_cost if available to include fees; else use effective_price * qty
            total_cost = None
            if row.get('total_cost') not in (None, ''):
                total_cost = safe_parse_float(row.get('total_cost'))
            elif row.get('totalCost') not in (None, ''):
                total_cost = safe_parse_float(row.get('totalCost'))
            elif row.get('net_cash_flow') not in (None, ''):
                # net_cash_flow is negative for buys; invert sign
                total_cost = abs(safe_parse_float(row.get('net_cash_flow')))
            else:
                # fallback
                unit = safe_parse_float(row.get('effective_price') or row.get('unit_price') or row.get('unitPrice') or 0)
                total_cost = unit * qty
            unit_cost = (total_cost / qty) if qty and total_cost is not None else 0.0

            if ticker_key not in lots_by_ticker:
                lots_by_ticker[ticker_key] = []
                realized_by_ticker[ticker_key] = 0.0

            # Always update to most recent original name (for display purposes)
            original_ticker_names[ticker_key] = raw_ticker

            if side == 'BUY' or side == 'B' or (side == '' and safe_parse_float(qty) > 0):
                # append buy lot
                lots_by_ticker[ticker_key].append({'qty': int(qty), 'unit_cost': unit_cost})
            else:
                # SELL or other negative side -> reduce FIFO lots
                sell_qty = int(qty)
                while sell_qty > 0 and lots_by_ticker[ticker_key]:
                    lot = lots_by_ticker[ticker_key][0]
                    take = min(lot['qty'], sell_qty)
                    # realized cash: proceeds not used here; for realized P/L we'd compute here
                    lot['qty'] -= take
                    sell_qty -= take
                    if lot['qty'] == 0:
                        lots_by_ticker[ticker_key].pop(0)
                # if we sell more than we have, we allow negative net position (short) by recording negative lot
                if sell_qty > 0:
                    # represent short position as negative lot with unit_cost equal to unit_cost (from row)
                    lots_by_ticker[ticker_key].append({'qty': -int(sell_qty), 'unit_cost': unit_cost})
                    sell_qty = 0

    # build positions list and totals
    positions = []
    total_invested_cash = 0.0
    for ticker_key, lots in lots_by_ticker.items():
        # Clean up lots: remove zero-quantity lots and consolidate
        cleaned_lots = [l for l in lots if l['qty'] != 0]

        net_qty = sum([l['qty'] for l in cleaned_lots])

        # For positions with net_qty > 0: invested = sum of positive lots
        # For positions with net_qty <= 0: invested = 0 (position is closed or short)
        if net_qty > 0:
            net_invested = sum([l['qty'] * l['unit_cost'] for l in cleaned_lots if l['qty'] > 0])
        else:
            net_invested = 0.0
            cleaned_lots = []  # Clear lots for closed positions

        # Use normalized key as ticker, but keep original name for display
        original_name = original_ticker_names.get(ticker_key, ticker_key)
        positions.append({
            'ticker': ticker_key,  # Normalized for matching with targets/prices
            'symbol': original_name,  # Original for display
            'net_qty': int(net_qty),
            'net_invested': float(net_invested),
            'lots': cleaned_lots
        })
        total_invested_cash += max(0.0, net_invested)

    # total_current_market will be computed later once we have prices; return 0.0 for now
    return positions, 0.0, total_invested_cash


# Read pipeline results and select latest run (by timestamp or run_id)

def load_latest_pipeline(path: str) -> Dict[str, Any]:
    # Prefer JSON summary from frontend if available (produced by Portfolio/Analysis)
    if os.path.exists(LATEST_RUN_SUMMARY):
        try:
            with open(LATEST_RUN_SUMMARY, 'r', encoding='utf-8') as fh:
                js = json.load(fh)
            bp = js.get('best_portfolio_details', {})
            stocks = bp.get('stocks') or bp.get('ticker_list') or []
            weights = bp.get('weights') or bp.get('weights_pct') or []
            # If weights look like fractions (sum<=1.1), normalize to percentages
            if weights:
                ssum = sum(weights)
                if ssum > 0 and ssum <= 1.1:
                    weights = [w * 100.0 for w in weights]
            return {'stocks': stocks, 'weights': weights, 'used_path': LATEST_RUN_SUMMARY}
        except Exception:
            # fall back to CSV approach below
            pass
    if not os.path.exists(path):
        return {'stocks': [], 'weights': [], 'used_path': None}
    rows = []
    with open(path, encoding=CSV_ENCODING, errors='replace') as fh:
        reader = csv.DictReader(fh)
        for r in reader:
            rows.append(r)
    if not rows:
        return {'stocks': [], 'weights': [], 'used_path': path}
    # choose row with latest timestamp if possible
    best = None
    best_dt = None
    for r in rows:
        ts = r.get('timestamp') or r.get('Timestamp') or r.get('time') or r.get('run_timestamp')
        if ts:
            try:
                dt = datetime.fromisoformat(ts)
            except Exception:
                try:
                    dt = datetime.strptime(ts, '%Y-%m-%d %H:%M:%S')
                except Exception:
                    dt = None
        else:
            dt = None
        if dt and (best_dt is None or dt > best_dt):
            best_dt = dt
            best = r
    if best is None:
        # fallback last row
        best = rows[-1]
    stocks_field = best.get('stocks') or best.get('Stocks') or best.get('ticker_list') or best.get('tickers')
    weights_field = best.get('weights') or best.get('Weights') or best.get('weight_list') or best.get('weights_pct')
    stocks = []
    weights = []
    if stocks_field:
        stocks = [s.strip() for s in str(stocks_field).replace('"','').split(',') if s.strip()]
    if weights_field:
        weights = [safe_parse_float(s) for s in str(weights_field).replace('"','').split(',') if s.strip()]
    # normalize weights as percentages if they sum to ~1
    if weights:
        ssum = sum(weights)
        if ssum > 0 and ssum <= 1.1:
            weights = [w * 100.0 for w in weights]
    return {'stocks': stocks, 'weights': weights, 'used_path': path}


# Stream StockDataDB.csv and keep last seen close price per symbol (memory efficient)

def load_latest_prices(path: str) -> Dict[str, float]:
    result: Dict[str, float] = {}
    if not os.path.exists(path):
        return result
    # open and stream
    with open(path, encoding=CSV_ENCODING, errors='replace') as fh:
        reader = csv.reader(fh)
        try:
            first = next(reader)
        except StopIteration:
            return result
        # Determine whether this is a header row or a data row by checking first cell pattern
        def looks_like_date(s: str) -> bool:
            s = (s or '').strip()
            return len(s) >= 10 and s[0:4].isdigit() and s[4] == '-' and s[5:7].isdigit() and s[7] == '-' and s[8:10].isdigit()

        if first and looks_like_date(first[0]):
            # No header: data format is likely: date,open,high,low,close,volume,symbol,...
            # find probable indices: close is around index 4, symbol around index 6 (heuristic)
            # but we can be flexible: try to find the token that looks like a symbol (contains letters and dot)
            # record the first row then continue processing it below
            data_rows = [first]
            for parts in reader:
                data_rows.append(parts)
            # process all data rows: for each row try to detect symbol and close fields
            for parts in data_rows:
                # find symbol index: token that contains a dot and letters (e.g., 'AALR3.SA')
                stock = None
                close_val = None
                for i, token in enumerate(parts):
                    t = (token or '').strip()
                    if t.endswith('.SA') or ('.' in t and any(c.isalpha() for c in t)):
                        stock = t
                        # assume close is at index 4 if available
                        if len(parts) > 4:
                            close_str = parts[4].strip().strip('"')
                        else:
                            close_str = parts[-2] if len(parts) >= 2 else ''
                        try:
                            val = float(''.join(ch for ch in close_str if (ch.isdigit() or ch in '.-eE')))
                            close_val = val
                        except Exception:
                            close_val = None
                        break
                if stock and close_val is not None:
                    result[stock] = close_val
            return result
        else:
            # first row is header; process header and remaining rows normally
            header = first
            stock_ix = None
            close_ix = None
            for i, h in enumerate(header):
                if h is None:
                    continue
                key = h.strip().lower()
                if key in ('stock', 'symbol', 'ticker') and stock_ix is None:
                    stock_ix = i
                if key in ('close', 'last', 'closeprice') and close_ix is None:
                    close_ix = i
            # heuristics for missing indices
            if stock_ix is None:
                stock_ix = 0
            if close_ix is None:
                close_ix = len(header) - 1
            for parts in reader:
                if len(parts) <= max(stock_ix, close_ix):
                    continue
                stock = parts[stock_ix].strip().strip('"')
                close_str = parts[close_ix].strip().strip('"')
                if not stock:
                    continue
                try:
                    val = float(''.join(ch for ch in close_str if (ch.isdigit() or ch in '.-eE')))
                    result[stock] = val
                except Exception:
                    continue
    return result


# Load scored stocks to produce target map and symbol map

def load_scored_maps(path: str) -> Dict[str, Any]:
    targets = {}
    symbols = {}
    name_to_symbol = {}
    if not os.path.exists(path):
        return {'targets': targets, 'symbols': symbols, 'name_to_symbol': name_to_symbol}
    with open(path, encoding=CSV_ENCODING, errors='replace') as fh:
        reader = csv.DictReader(fh)
        for r in reader:
            # scored_stocks.csv often contains both trading symbol and company name
            trading = (r.get('Stock') or r.get('stock') or r.get('StockSymbol') or r.get('Symbol') or r.get('Ticker') or '').strip()
            name = (r.get('Name') or r.get('name') or r.get('Company') or '').strip()
            tp = safe_parse_float(r.get('TargetPrice') or r.get('target') or r.get('Target') or '')
            if trading:
                key = normalize_ticker(trading)
                if tp:
                    targets[key] = tp
                symbols[key] = trading
            if name and trading:
                name_to_symbol[normalize_ticker(name)] = trading
    return {'targets': targets, 'symbols': symbols, 'name_to_symbol': name_to_symbol}


def load_broker_name_mapping(tickers_path: str) -> Dict[str, str]:
    """
    Load mapping from BrokerName (as seen in broker notes) to trading symbol (like VALE3.SA).
    Returns dict: { normalized_broker_name: trading_symbol }

    Example: { 'AURA360DR3': 'AURA33.SA', 'AXIAENERGIAPNBEXN1': 'AXPE11.SA' }
    """
    mapping = {}
    if not os.path.exists(tickers_path):
        return mapping

    with open(tickers_path, encoding=CSV_ENCODING, errors='replace') as fh:
        reader = csv.DictReader(fh)
        for row in reader:
            ticker = (row.get('Ticker') or '').strip()
            broker_name = (row.get('BrokerName') or '').strip()
            company_name = (row.get('Name') or '').strip()

            if ticker:
                # Map by broker name if available
                if broker_name:
                    key = normalize_ticker(broker_name)
                    mapping[key] = ticker
                    # Also map the normalized broker ticker
                    normalized_broker = normalize_broker_ticker(broker_name)
                    mapping[normalize_ticker(normalized_broker)] = ticker

                # Also map by company name
                if company_name:
                    key = normalize_ticker(company_name)
                    mapping[key] = ticker

                # Also map by ticker base (without .SA)
                ticker_base = ticker.replace('.SA', '').strip()
                mapping[normalize_ticker(ticker_base)] = ticker

    return mapping


# Build pipeline rows from stocks/weights, using ledger current market value as available cash

def build_pipeline_rows(stocks: List[str], weights: List[float], ledger_market_value: float, price_map: Dict[str,float], target_map: Dict[str,float]):
    rows = []
    totals = {'totalPct': 0.0, 'totalCurrentSum': 0.0, 'totalProjectedQty': 0, 'totalProjectedInvested': 0.0, 'totalProjectedBRL': 0.0}
    for i, s in enumerate(stocks):
        w = safe_parse_float(weights[i] if i < len(weights) else 0)
        totals['totalPct'] += w
        allocated = (ledger_market_value * (w/100.0)) if ledger_market_value and ledger_market_value>0 else None
        current = None
        # try direct symbol lookup, then normalized
        if s in price_map:
            current = price_map[s]
        else:
            # attempt normalized lookup
            norm = normalize_ticker(s)
            # price_map keys might be with suffix like .SA; check keys normalized
            for k in price_map.keys():
                if normalize_ticker(k) == norm:
                    current = price_map[k]
                    break
        tp = target_map.get(normalize_ticker(s))
        if allocated is not None and current is not None and current != 0:
            projected_qty = int(math.floor(allocated / current))
            projected_invested = projected_qty * current
        else:
            projected_qty = None
            projected_invested = None
        projected_brl = (projected_qty * tp) if (projected_qty is not None and tp is not None) else None
        if allocated is not None:
            totals['totalCurrentSum'] += allocated
        if projected_qty:
            totals['totalProjectedQty'] += projected_qty
        if projected_invested:
            totals['totalProjectedInvested'] += projected_invested
        if projected_brl:
            totals['totalProjectedBRL'] += projected_brl
        rows.append({
            'ticker': s,
            'weight': w,
            'current': current,
            'projectedQty': projected_qty,
            'projectedInvested': projected_invested,
            'target': tp,
            'projectedBRL': projected_brl
        })
    rows.sort(key=lambda r: (r.get('projectedInvested') or 0), reverse=True)
    return {'rows': rows, 'totals': totals}


# Main

TICKERS_FILE = os.path.join('parameters', 'tickers.txt')

def main():
    print('Generating assets JSON (revised)...')
    # 1) aggregate ledger.csv
    positions, _, total_invested_cash = aggregate_ledger_from_csv(LEDGER_CSV)

    # 2) load latest prices from StockDataDB.csv (streaming)
    price_map = load_latest_prices(FINDB_STOCKDB)

    # 2b) load scored maps (also contains name->symbol mapping) to help translate ledger names to trading symbols
    scored = load_scored_maps(SCORED_STOCKS)
    target_map = scored.get('targets', {})
    symbol_map = scored.get('symbols', {})
    name_to_symbol = scored.get('name_to_symbol', {})

    # 2c) load broker name mapping from tickers.txt
    broker_mapping = load_broker_name_mapping(TICKERS_FILE)

    # 3) compute current market value using price_map
    total_current_market = 0.0
    for p in positions:
        qty = p.get('net_qty', 0)
        if qty and qty != 0:
            # prefer explicit symbol, else try to map ledger ticker (which may be company name) to trading symbol
            symbol = p.get('symbol') or p.get('ticker')
            ticker_key = p.get('ticker', '')

            # Try multiple ways to find the trading symbol
            trading_symbol = None

            # 1. Try broker_mapping with normalized ticker key
            if not trading_symbol:
                mapped = broker_mapping.get(normalize_ticker(ticker_key))
                if mapped:
                    trading_symbol = mapped

            # 2. Try broker_mapping with original symbol
            if not trading_symbol:
                mapped = broker_mapping.get(normalize_ticker(symbol))
                if mapped:
                    trading_symbol = mapped

            # 3. Try name_to_symbol mapping
            if not trading_symbol:
                mapped = name_to_symbol.get(normalize_ticker(ticker_key))
                if mapped:
                    trading_symbol = mapped

            # 4. If symbol already looks like a market symbol, use it
            if not trading_symbol and ('.' in (symbol or '') or (symbol or '').endswith('SA')):
                trading_symbol = symbol

            # Update symbol if we found a trading symbol
            if trading_symbol:
                p['symbol'] = trading_symbol
                symbol = trading_symbol

            # Now try to get price
            price = None
            if symbol in price_map:
                price = price_map[symbol]
            else:
                for k in price_map.keys():
                    if normalize_ticker(k) == normalize_ticker(symbol):
                        price = price_map[k]
                        # update symbol to the exact price_map key
                        p['symbol'] = k
                        break
            if price is not None:
                total_current_market += qty * price
                p['current_price'] = price
            else:
                p['current_price'] = None
        else:
            p['current_price'] = None

    # If there are still positions with null current_price, try to match by searching price_map names by partial match of normalized ticker
    for p in positions:
        if (p.get('current_price') is None) and p.get('net_qty',0) != 0:
            norm = normalize_ticker(p.get('ticker'))
            matched = None
            for k in price_map.keys():
                if norm in normalize_ticker(k) or normalize_ticker(k) in norm:
                    matched = k
                    break
            if matched:
                price = price_map.get(matched)
                if price is not None:
                    p['symbol'] = matched
                    p['current_price'] = price
                    total_current_market += p.get('net_qty',0) * price

    # 4) write ledger_positions.json wrapper
    ledger_out = {'positions': positions, 'total_invested_cash': total_invested_cash, 'total_current_market': total_current_market, 'generated_at': datetime.now(timezone.utc).isoformat()}

    # If the ledger CSV does not exist, avoid overwriting an existing consolidated ledger JSON
    # This preserves the last known positions for the frontend when there are no new transactions.
    if not os.path.exists(LEDGER_CSV):
        html_existing = os.path.join('html', 'data', os.path.basename(OUTPUT_LEDGER_JSON))
        if os.path.exists(html_existing):
            print(f"Ledger CSV not found ({LEDGER_CSV}); keeping existing {html_existing} and skipping write of {OUTPUT_LEDGER_JSON}.")
        else:
            # No source CSV and no existing HTML copy: write an empty ledger_positions.json so frontend shows 'No ledger data'
            try:
                os.makedirs(os.path.dirname(OUTPUT_LEDGER_JSON) or '.', exist_ok=True)
                with open(OUTPUT_LEDGER_JSON, 'w', encoding='utf-8') as fh:
                    json.dump(ledger_out, fh, ensure_ascii=False, indent=2)
                print('Wrote', OUTPUT_LEDGER_JSON)
            except Exception as e:
                print('Failed to write ledger json:', e)
    else:
        try:
            # ensure output directory exists
            os.makedirs(os.path.dirname(OUTPUT_LEDGER_JSON) or '.', exist_ok=True)
            with open(OUTPUT_LEDGER_JSON, 'w', encoding='utf-8') as fh:
                json.dump(ledger_out, fh, ensure_ascii=False, indent=2)
            print('Wrote', OUTPUT_LEDGER_JSON)
        except Exception as e:
            print('Failed to write ledger json:', e)

    # 5) load latest pipeline run
    pipeline = load_latest_pipeline(PIPELINE_CSV)
    stocks = pipeline.get('stocks', [])
    weights = pipeline.get('weights', [])
    used_path = pipeline.get('used_path')
    # normalize weights if missing
    if stocks and (not weights or len(weights) != len(stocks)):
        weights = [100.0 / len(stocks) for _ in stocks]

    built = build_pipeline_rows(stocks, weights, total_current_market or total_invested_cash, price_map, target_map)
    pipeline_out = {
         'stocks': stocks,
         'weights': weights,
         'rows': built['rows'],
         'totals': built['totals'],
         'used_path': used_path,
        'generated_at': datetime.now(timezone.utc).isoformat()
    }
    try:
        # ensure output directory exists
        os.makedirs(os.path.dirname(OUTPUT_PIPELINE_JSON) or '.', exist_ok=True)
        with open(OUTPUT_PIPELINE_JSON, 'w', encoding='utf-8') as fh:
            json.dump(pipeline_out, fh, ensure_ascii=False, indent=2)
        print('Wrote', OUTPUT_PIPELINE_JSON)
        # No secondary copy needed; OUTPUT_PIPELINE_JSON already points to html/data
    except Exception as e:
        print('Failed to write pipeline json:', e)

    # 6) write scored targets map
    scored_out = {'targets': target_map, 'symbols': symbol_map, 'generated_at': datetime.now(timezone.utc).isoformat()}
    try:
        # ensure output directory exists
        os.makedirs(os.path.dirname(OUTPUT_SCORED_JSON) or '.', exist_ok=True)
        with open(OUTPUT_SCORED_JSON, 'w', encoding='utf-8') as fh:
            json.dump(scored_out, fh, ensure_ascii=False, indent=2)
        print('Wrote', OUTPUT_SCORED_JSON)
        # No secondary copy needed; OUTPUT_SCORED_JSON already points to html/data
    except Exception as e:
        print('Failed to write scored json:', e)

    print('Summary: positions:', len(positions), 'total_invested_cash:', total_invested_cash, 'total_current_market:', total_current_market, 'pipeline_stocks:', len(stocks))

    # 7) Copy ledger.csv to html/data for frontend access
    try:
        if os.path.exists(LEDGER_CSV):
            os.makedirs(os.path.dirname(OUTPUT_LEDGER_CSV) or '.', exist_ok=True)
            # Read and write to ensure proper encoding
            with open(LEDGER_CSV, 'r', encoding=CSV_ENCODING, errors='replace') as src:
                content = src.read()
            with open(OUTPUT_LEDGER_CSV, 'w', encoding=CSV_ENCODING) as dst:
                dst.write(content)
            print('Wrote', OUTPUT_LEDGER_CSV)
    except Exception as e:
        print('Failed to write ledger.csv to html/data:', e)


if __name__ == '__main__':
    main()
