#!/usr/bin/env python3
"""
engines/B2_Consolidate_Ledger.py

Read data/ledger.csv (all transactions), aggregate by ticker into current positions
and write data/ledger_positions.json. This script is defensive and accepts multiple
column name variants to match the CSVs produced by Process_pdf.py.

Usage:
    python3 engines/B2_Consolidate_Ledger.py

Output:
    html/data/ledger_positions.json  (array of {ticker, net_qty, net_invested})

"""

# --- Script Version ---
CONSOLIDATE_LEDGER_VERSION = "2.0.0"  # Refactored with shared_utils, logging, and parameter loading

import csv
import json
import re
import logging
import time
from pathlib import Path
from datetime import datetime, timezone
from typing import Dict, List, Any, Optional, Tuple

# Ensure project root is on sys.path
ROOT = Path(__file__).resolve().parents[1]
import sys
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from shared_tools.shared_utils import (
    setup_logger,
    load_parameters_from_file,
    initialize_performance_data,
    log_performance_data,
)

# ----------------------------------------------------------- #
#                      Configuration                          #
# ----------------------------------------------------------- #

def load_config(logger: logging.Logger) -> Dict[str, Any]:
    """Load configuration from parameters file with fallbacks."""
    # Default values for paths
    defaults = {
        'LEDGER_FILE': str(ROOT / 'data' / 'ledger.csv'),
        'TICKERS_FILE': str(ROOT / 'parameters' / 'tickers.txt'),
        'FINDB_FILE': str(ROOT / 'data' / 'findb' / 'StockDataDB.csv'),
        'SCORED_STOCKS_FILE': str(ROOT / 'data' / 'results' / 'scored_stocks.csv'),
        'WEB_ACCESSIBLE_DATA_PATH': str(ROOT / 'html' / 'data'),
        'CONSOLIDATE_PERF_FILE': str(ROOT / 'data' / 'Results' / 'consolidate_ledger_performance.csv'),
    }

    # Expected parameters with their types
    expected_types = {
        'LEDGER_FILE': str,
        'TICKERS_FILE': str,
        'FINDB_FILE': str,
        'SCORED_STOCKS_FILE': str,
        'WEB_ACCESSIBLE_DATA_PATH': str,
        'CONSOLIDATE_PERF_FILE': str,
    }

    params = load_parameters_from_file(
        str(ROOT / 'parameters' / 'paths.txt'),
        expected_types,
        logger
    )

    config = {
        'LEDGER_FILE': Path(params.get('LEDGER_FILE', defaults['LEDGER_FILE'])),
        'TICKERS_FILE': Path(params.get('TICKERS_FILE', defaults['TICKERS_FILE'])),
        'FINDB_FILE': Path(params.get('FINDB_FILE', defaults['FINDB_FILE'])),
        'SCORED_STOCKS_FILE': Path(params.get('SCORED_STOCKS_FILE', defaults['SCORED_STOCKS_FILE'])),
        'OUT_JSON': Path(params.get('WEB_ACCESSIBLE_DATA_PATH', defaults['WEB_ACCESSIBLE_DATA_PATH'])) / 'ledger_positions.json',
        'PERFORMANCE_FILE': Path(params.get('CONSOLIDATE_PERF_FILE', defaults['CONSOLIDATE_PERF_FILE'])),
    }

    # Ensure paths are absolute
    for key, path in config.items():
        if not path.is_absolute():
            config[key] = ROOT / path

    return config


# ----------------------------------------------------------- #
#                     Helper Functions                        #
# ----------------------------------------------------------- #

def safe_float(v: Any) -> float:
    """Safely convert a value to float, handling currency formats."""
    if v is None or v == '':
        return 0.0
    try:
        s = str(v)
        # Handle Brazilian currency format (. for thousands, , for decimals)
        if ',' in s and '.' in s:
            # If comma is after last dot, assume BR format
            if s.rfind(',') > s.rfind('.'):
                s = s.replace('.', '').replace(',', '.')
        elif ',' in s:
            s = s.replace(',', '.')
        # Remove non-numeric except . and -
        s = re.sub(r'[^0-9.\-]', '', s)
        return float(s) if s not in ('', '-', '.') else 0.0
    except (ValueError, TypeError):
        return 0.0


def normalize_key(s: Optional[str]) -> str:
    """Normalize string for key matching."""
    if not s:
        return ''
    return re.sub(r'[^A-Za-z0-9]', '', str(s).upper())


def normalize_alpha(s: Optional[str]) -> str:
    """Normalize string keeping only letters."""
    if not s:
        return ''
    return re.sub(r'[^A-Za-z]', '', str(s).upper())


def normalize_ticker(s: Optional[str]) -> str:
    """Normalize ticker symbol."""
    if not s:
        return ''
    return str(s).strip()


def consolidate_from_csv(path: Path, logger: logging.Logger) -> List[Dict[str, Any]]:
    """Read ledger CSV and aggregate into positions."""
    agg: Dict[str, Dict[str, Any]] = {}

    try:
        with path.open(newline='', encoding='utf-8') as fh:
            reader = csv.DictReader(fh)
            for row in reader:
                # Determine ticker
                ticker = (row.get('ticker') or row.get('Ticker') or row.get('symbol') or '').strip()
                if not ticker:
                    continue

                side = (row.get('side') or row.get('Side') or row.get('transaction_type') or '').upper()
                qty = safe_float(row.get('quantity') or row.get('Quantity') or row.get('qty') or '0')
                gross = safe_float(row.get('gross_value') or row.get('total_cost') or row.get('amount') or '0')
                allocated_fees = safe_float(row.get('allocated_fees') or row.get('fees') or '0')
                total_cost = safe_float(row.get('total_cost') or '0')

                if not total_cost:
                    total_cost = gross + allocated_fees

                factor = -1 if side in ('SELL', 'S', 'VENDA', 'V') else 1

                if ticker not in agg:
                    agg[ticker] = {'ticker': normalize_ticker(ticker), 'net_qty': 0.0, 'net_invested': 0.0}
                agg[ticker]['net_qty'] += factor * qty
                agg[ticker]['net_invested'] += factor * total_cost

    except FileNotFoundError:
        logger.error(f"Ledger file not found: {path}")
        return []
    except csv.Error as e:
        logger.error(f"CSV error reading ledger: {e}")
        return []

    # Convert to list sorted by absolute invested
    arr = list(agg.values())
    arr.sort(key=lambda x: abs(x.get('net_invested', 0)), reverse=True)
    return arr


def load_scored_targets(path: Path, logger: logging.Logger) -> Dict[str, Any]:
    """Load scored_stocks.csv and return map of normalized symbol -> target_price."""
    if not path.exists():
        logger.warning(f"Scored stocks file not found: {path}")
        return {'by_symbol': {}, 'by_name': {}, 'entries': []}

    targets = {}
    names_map = {}
    entries = []

    try:
        with path.open(newline='', encoding='utf-8') as fh:
            reader = csv.DictReader(fh)
            for row in reader:
                stock = (row.get('Stock') or row.get('stock') or '').strip()
                name = (row.get('Name') or row.get('name') or '').strip()
                tp = row.get('TargetPrice') or row.get('targetprice') or ''

                if not stock and not name:
                    continue

                k = normalize_key(stock) if stock else ''
                ka = normalize_alpha(stock) if stock else ''
                nk_name = normalize_key(name) if name else ''
                na_name = normalize_alpha(name) if name else ''
                tpv = safe_float(tp)

                if k:
                    targets[k] = {'target': tpv, 'symbol': stock}
                if ka:
                    targets['ALPHA|' + ka] = {'target': tpv, 'symbol': stock}
                if nk_name:
                    names_map[nk_name] = {'target': tpv, 'symbol': stock}
                if na_name:
                    names_map['ALPHA|' + na_name] = {'target': tpv, 'symbol': stock}

                # Build token set for fuzzy matching
                txt = f"{stock} {name}"
                tokens = set([t.upper() for t in re.split(r'[^A-Za-z0-9]+', txt) if len(t) >= 4])
                entries.append({'symbol': stock, 'name': name, 'target': tpv, 'tokens': tokens})

    except csv.Error as e:
        logger.error(f"CSV error reading scored stocks: {e}")

    return {'by_symbol': targets, 'by_name': names_map, 'entries': entries}


def load_tickers_mapping(path: Path, logger: logging.Logger) -> Tuple[Dict[str, str], List[Dict[str, Any]]]:
    """Load tickers.txt and build name -> symbol mapping."""
    name_to_symbol = {}
    entries = []

    if not path.exists():
        logger.warning(f"Tickers file not found: {path}")
        return name_to_symbol, entries

    try:
        with path.open(newline='', encoding='utf-8') as fh:
            reader = csv.DictReader(fh)
            for row in reader:
                symbol = (row.get('Ticker') or '').strip()
                name = (row.get('Name') or '').strip()
                broker_name = (row.get('BrokerName') or '').strip()

                if not symbol:
                    continue

                entries.append({'symbol': symbol, 'name': name, 'broker_name': broker_name})

                # Build mapping keys
                if name:
                    nk = normalize_key(name)
                    na = normalize_alpha(name)
                    if nk:
                        name_to_symbol[nk] = symbol
                    if na:
                        name_to_symbol['ALPHA|' + na] = symbol

                if broker_name:
                    bk = normalize_key(broker_name)
                    ba = normalize_alpha(broker_name)
                    if bk:
                        name_to_symbol[bk] = symbol
                    if ba:
                        name_to_symbol['ALPHA|' + ba] = symbol

    except csv.Error as e:
        logger.error(f"CSV error reading tickers: {e}")

    return name_to_symbol, entries


def find_latest_prices(symbols: List[str], findb_path: Path, logger: logging.Logger) -> Dict[str, float]:
    """Find latest prices for given symbols from StockDataDB."""
    prices = {}

    if not findb_path.exists():
        logger.warning(f"StockDataDB not found: {findb_path}")
        return prices

    try:
        # Build set of normalized symbols
        norm_symbols = {normalize_key(s): s for s in symbols if s}

        with findb_path.open(newline='', encoding='utf-8') as fh:
            reader = csv.DictReader(fh)
            for row in reader:
                stock = (row.get('Stock') or row.get('stock') or '').strip()
                nk = normalize_key(stock)

                if nk in norm_symbols:
                    close = safe_float(row.get('Close') or row.get('close') or '0')
                    date_str = row.get('Date') or ''

                    # Keep latest price
                    orig_symbol = norm_symbols[nk]
                    if orig_symbol not in prices or (date_str and date_str > prices.get(f'{orig_symbol}_date', '')):
                        prices[orig_symbol] = close
                        prices[f'{orig_symbol}_date'] = date_str

    except csv.Error as e:
        logger.error(f"CSV error reading StockDataDB: {e}")

    # Remove date tracking keys
    return {k: v for k, v in prices.items() if not k.endswith('_date')}


def match_symbol_for_position(
    ledger_ticker: str,
    name_to_symbol: Dict[str, str],
    tickers_entries: List[Dict[str, Any]],
    logger: logging.Logger
) -> Optional[str]:
    """Try to find matching symbol for a ledger ticker."""
    nk = normalize_key(ledger_ticker)
    na = normalize_alpha(ledger_ticker)

    # Strategy 1: Direct key match
    if nk and nk in name_to_symbol:
        return name_to_symbol[nk]

    # Strategy 2: Alpha-only match
    if na and ('ALPHA|' + na) in name_to_symbol:
        return name_to_symbol['ALPHA|' + na]

    # Strategy 3: Partial/substring match
    for key, symbol in name_to_symbol.items():
        if key.startswith('ALPHA|'):
            continue
        if nk and len(nk) >= 4 and (nk in key or key in nk):
            return symbol

    # Strategy 4: Token-based fuzzy match
    if tickers_entries:
        ledger_tokens = set([t.upper() for t in re.split(r'[^A-Za-z0-9]+', ledger_ticker) if len(t) >= 3])
        best_match = None
        best_score = 0

        for entry in tickers_entries:
            entry_name = entry.get('name', '') + ' ' + entry.get('broker_name', '')
            entry_tokens = set([t.upper() for t in re.split(r'[^A-Za-z0-9]+', entry_name) if len(t) >= 3])
            score = len(ledger_tokens & entry_tokens)

            if score > best_score:
                best_score = score
                best_match = entry

        if best_score >= 1 and best_match:
            return best_match.get('symbol')

    return None


def match_target_for_position(
    ticker: str,
    symbol: Optional[str],
    scored_maps: Dict[str, Any]
) -> Optional[float]:
    """Find target price for a position."""
    by_symbol = scored_maps.get('by_symbol', {})

    # Try symbol first
    if symbol:
        ks = normalize_key(symbol)
        if ks and ks in by_symbol:
            return by_symbol[ks]['target']
        ka = normalize_alpha(symbol)
        if ka and ('ALPHA|' + ka) in by_symbol:
            return by_symbol['ALPHA|' + ka]['target']

    # Try ticker
    kt = normalize_key(ticker)
    if kt and kt in by_symbol:
        return by_symbol[kt]['target']

    # Try name mapping
    by_name = scored_maps.get('by_name', {})
    if kt and kt in by_name:
        return by_name[kt]['target']

    return None


# ----------------------------------------------------------- #
#                         Main                                #
# ----------------------------------------------------------- #

def main() -> int:
    """Main entry point for consolidating ledger."""
    start_time = time.time()

    # Setup logger
    logger = setup_logger(
        'ConsolidateLedgerRunner',
        log_file=str(ROOT / 'logs' / 'consolidate_ledger.log'),
        web_log_file=None,
        level=logging.INFO
    )

    logger.info(f"Starting B2_Consolidate_Ledger.py v{CONSOLIDATE_LEDGER_VERSION}")

    # Load configuration
    config = load_config(logger)

    # Initialize performance tracking
    perf_data = initialize_performance_data('B2_Consolidate_Ledger', CONSOLIDATE_LEDGER_VERSION)

    try:
        # Check ledger file exists
        if not config['LEDGER_FILE'].exists():
            logger.error(f"Ledger CSV not found: {config['LEDGER_FILE']}")
            perf_data['status'] = 'error'
            perf_data['error'] = 'Ledger file not found'
            return 1

        # Consolidate positions
        positions = consolidate_from_csv(config['LEDGER_FILE'], logger)
        logger.info(f"Consolidated {len(positions)} positions from ledger")
        perf_data['positions_count'] = len(positions)

        # Filter positions with net_qty > 0
        positions = [p for p in positions if p.get('net_qty', 0) > 0]
        logger.info(f"Active positions (net_qty > 0): {len(positions)}")
        perf_data['active_positions'] = len(positions)

        # Load mappings
        name_to_symbol, tickers_entries = load_tickers_mapping(config['TICKERS_FILE'], logger)
        logger.info(f"Loaded {len(tickers_entries)} ticker mappings")

        scored_maps = load_scored_targets(config['SCORED_STOCKS_FILE'], logger)
        logger.info(f"Loaded {len(scored_maps.get('entries', []))} scored stocks")

        # Enrich positions with symbol, target price, current price
        for p in positions:
            ledger_ticker = p.get('ticker', '')

            # Find symbol
            symbol = match_symbol_for_position(ledger_ticker, name_to_symbol, tickers_entries, logger)
            p['symbol'] = symbol

            # Find target price
            target = match_target_for_position(ledger_ticker, symbol, scored_maps)
            p['target_price'] = target

        # Find current prices
        symbols = [p.get('symbol') or p.get('ticker') for p in positions]
        prices_map = find_latest_prices(symbols, config['FINDB_FILE'], logger)

        for p in positions:
            key = p.get('symbol') or p.get('ticker')
            p['current_price'] = prices_map.get(key)

        # Write output
        output = {
            'generated_at': datetime.now(timezone.utc).isoformat(),
            'source': str(config['LEDGER_FILE'].relative_to(ROOT)),
            'positions': positions
        }

        config['OUT_JSON'].parent.mkdir(parents=True, exist_ok=True)
        with config['OUT_JSON'].open('w', encoding='utf-8') as fh:
            json.dump(output, fh, ensure_ascii=False, indent=2)

        logger.info(f"Wrote {config['OUT_JSON']} with {len(positions)} positions")
        perf_data['status'] = 'success'
        return 0

    except Exception as e:
        logger.critical(f"An unhandled exception occurred: {e}", exc_info=True)
        perf_data['status'] = 'error'
        perf_data['error'] = str(e)
        return 1

    finally:
        perf_data['execution_time'] = time.time() - start_time
        # log_performance_data expects a dict with key
        perf_params = {'PERFORMANCE_FILE': str(config['PERFORMANCE_FILE'])}
        log_performance_data(perf_data, perf_params, logger, 'PERFORMANCE_FILE')
        logger.info(f"Consolidate ledger script finished in {perf_data['execution_time']:.2f} seconds")


if __name__ == '__main__':
    raise SystemExit(main())
