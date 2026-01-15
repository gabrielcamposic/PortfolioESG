#!/usr/bin/env python3
"""
scripts/B2_Consolidate_Ledger.py

Read data/ledger.csv (all transactions), aggregate by ticker into current positions
and write data/ledger_positions.json. This script is defensive and accepts multiple
column name variants to match the CSVs produced by Process_pdf.py.

Usage:
    python3 scripts/B2_Consolidate_Ledger.py

Output:
    data/ledger_positions.json  (array of {ticker, net_qty, net_invested})

"""
import csv
import json
import os
from datetime import datetime, timezone

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LEDGER_CSV = os.path.join(ROOT, 'data', 'ledger.csv')
OUT_JSON = os.path.join(ROOT, 'html', 'data', 'ledger_positions.json')
TICKERS_TXT = os.path.join(ROOT, 'parameters', 'tickers.txt')

CSV_CANDIDATES = [LEDGER_CSV]
SCORED_STOCKS_CANDIDATES = [
    os.path.join(ROOT, 'data', 'results', 'scored_stocks.csv'),
    os.path.join(ROOT, 'html', 'data', 'scored_stocks.csv'),
    os.path.join(ROOT, 'data', 'scored_stocks.csv'),
]
FINDB_CANDIDATES = [
    os.path.join(ROOT, 'data', 'findb', 'StockDataDB.csv'),
    os.path.join(ROOT, 'data', 'findb', 'stockdatadb.csv'),
    os.path.join(ROOT, 'data', 'StockDataDB.csv'),
]


def safe_float(v):
    if v is None or v == '':
        return 0.0
    try:
        # remove currency symbols and thousands separators
        s = str(v).replace('.', '').replace(',', '.') if isinstance(v, str) and v.count(',') and v.count('.') == 0 else str(v)
        # allow values like 'R$ 123,45' by removing non-numeric except . and -
        import re
        s = re.sub(r'[^0-9.-]', '', s)
        return float(s) if s not in ('', '-', None) else 0.0
    except Exception:
        try:
            return float(v)
        except Exception:
            return 0.0


def find_file(candidates):
    for p in candidates:
        if os.path.exists(p):
            return p
    return None


def normalize_ticker(s):
    if not s:
        return ''
    return str(s).strip()


def consolidate_from_csv(path):
    agg = {}
    with open(path, newline='', encoding='utf-8') as fh:
        reader = csv.DictReader(fh)
        for row in reader:
            # determine ticker
            ticker = (row.get('ticker') or row.get('Ticker') or row.get('TICKER') or row.get('symbol') or row.get('Symbol') or '').strip()
            if not ticker:
                continue
            side = (row.get('side') or row.get('Side') or row.get('transaction_type') or row.get('type') or '').upper()
            qty = safe_float(row.get('quantity') or row.get('Quantity') or row.get('qty') or row.get('Qty') or row.get('net_qty'))
            gross = safe_float(row.get('gross_value') or row.get('Gross_value') or row.get('grossValue') or row.get('gross') or row.get('amount') or row.get('Amount') or row.get('net_invested') or row.get('net_value') or row.get('total_cost'))
            allocated_fees = safe_float(row.get('allocated_fees') or row.get('allocatedFees') or row.get('allocated_fee') or row.get('fees'))
            total_cost = safe_float(row.get('total_cost') or row.get('total') or (gross + allocated_fees))
            if not total_cost:
                total_cost = gross + allocated_fees
            factor = -1 if side in ('SELL', 'S', 'SELLS', 'OUT') else 1

            if ticker not in agg:
                agg[ticker] = {'ticker': normalize_ticker(ticker), 'net_qty': 0.0, 'net_invested': 0.0}
            agg[ticker]['net_qty'] += factor * qty
            agg[ticker]['net_invested'] += factor * total_cost

    # convert to list sorted by absolute invested
    arr = list(agg.values())
    arr.sort(key=lambda x: abs(x.get('net_invested', 0)), reverse=True)
    return arr


def normalize_key(s):
    if not s:
        return ''
    import re
    k = re.sub(r'[^A-Za-z0-9]', '', str(s).upper())
    return k

# letters-only normalization to match tickers where numeric class suffix differs
def normalize_alpha(s):
    if not s:
        return ''
    import re
    return re.sub(r'[^A-Za-z]', '', str(s).upper())


def build_scored_entries(path):
    entries = []
    try:
        with open(path, newline='', encoding='utf-8') as fh:
            reader = csv.DictReader(fh)
            for row in reader:
                stock = (row.get('Stock') or row.get('stock') or row.get('StockSymbol') or '').strip()
                name = (row.get('Name') or row.get('name') or '').strip()
                tp = safe_float(row.get('TargetPrice') or row.get('targetprice') or row.get('target') or '')
                # tokenization: keep alphanumeric tokens length >=4
                import re
                tokens = set([t.upper() for t in re.split(r'[^A-Za-z0-9]+', (stock + ' ' + name)) if len(t) >= 4])
                entries.append({'symbol': stock, 'name': name, 'target': tp, 'tokens': tokens})
    except Exception:
        pass
    return entries


def load_scored_targets(candidates):
    """Load scored_stocks.csv and return map of normalized symbol -> target_price"""
    path = find_file(candidates)
    if not path:
        print('No scored_stocks.csv found in candidates; continuing without target prices')
        return { 'by_symbol': {}, 'by_name': {}, 'entries': [] }
    targets = {}
    names_map = {}
    entries = []
    try:
        with open(path, newline='', encoding='utf-8') as fh:
            reader = csv.DictReader(fh)
            for row in reader:
                # scoring CSV uses 'Stock' for ticker and 'TargetPrice' column
                stock = (row.get('Stock') or row.get('stock') or row.get('StockSymbol') or '').strip()
                name = (row.get('Name') or row.get('name') or '').strip()
                tp = row.get('TargetPrice') or row.get('targetprice') or row.get('target') or ''
                if not stock and not name:
                    continue
                k = normalize_key(stock) if stock else ''
                ka = normalize_alpha(stock) if stock else ''
                nk_name = normalize_key(name) if name else ''
                na_name = normalize_alpha(name) if name else ''
                tpv = safe_float(tp)
                # store mappings by stock symbol and by name (both alnum and alpha forms)
                if k:
                    targets[k] = { 'target': tpv, 'symbol': stock }
                if ka:
                    targets['ALPHA|' + ka] = { 'target': tpv, 'symbol': stock }
                if nk_name:
                    names_map[nk_name] = { 'target': tpv, 'symbol': stock }
                if na_name:
                    names_map['ALPHA|' + na_name] = { 'target': tpv, 'symbol': stock }
                entries.append({'symbol': stock, 'name': name, 'target': tpv})
    except Exception as e:
        print('Failed to parse scored_stocks.csv:', e)
    # build token sets for entries
    import re
    for e in entries:
        txt = (e.get('symbol') or '') + ' ' + (e.get('name') or '')
        e['tokens'] = set([t.upper() for t in re.split(r'[^A-Za-z0-9]+', txt) if len(t) >= 4])
    return { 'by_symbol': targets, 'by_name': names_map, 'entries': entries }


def find_best_entry_by_token_overlap(ledger_ticker, entries):
    if not ledger_ticker or not entries:
        return None
    import re
    lt = ledger_ticker.upper()
    lt_tokens = set([t for t in re.split(r'[^A-Za-z0-9]+', lt) if len(t) >= 4])
    best = None
    best_score = 0
    for e in entries:
        score = len(lt_tokens & e.get('tokens', set()))
        if score > best_score:
            best_score = score
            best = e
    # require at least one token match
    if best_score > 0:
        return best
    return None


def match_target_for_ticker(ticker, scored_maps):
    """Try to find best matching target price and symbol for a ticker using scored maps.

    Returns (target_price_or_None, matched_symbol_or_None)
    """
    if not scored_maps:
        return (None, None)
    by_sym = scored_maps.get('by_symbol', {})
    by_name = scored_maps.get('by_name', {})
    entries = scored_maps.get('entries', [])
    nk = normalize_key(ticker)
    na = normalize_alpha(ticker)
    # 1. exact symbol match
    if nk and nk in by_sym:
        obj = by_sym[nk]
        return (obj['target'], obj['symbol'])
    # 2. exact alpha symbol form
    if na and ('ALPHA|' + na) in by_sym:
        obj = by_sym['ALPHA|' + na]
        return (obj['target'], obj['symbol'])
    # 3. exact name match
    if nk and nk in by_name:
        obj = by_name[nk]
        return (obj['target'], obj['symbol'])
    if na and ('ALPHA|' + na) in by_name:
        obj = by_name['ALPHA|' + na]
        return (obj['target'], obj['symbol'])
    # 4. token-overlap heuristic
    best = find_best_entry_by_token_overlap(ticker, entries)
    if best:
        return (best.get('target'), best.get('symbol'))
    # 5. substring match on symbols
    for k in by_sym.keys():
        if k.startswith('ALPHA|'):
            continue
        if nk and (nk in k or k in nk):
            obj = by_sym[k]
            return (obj['target'], obj['symbol'])
    return (None, None)


def load_tickers_map(path):
    """Load parameters/tickers.txt (CSV with header Ticker,Name,Sector,Industry,BrokerName) and return two maps:
       - name_to_symbol: normalized name -> symbol (uses both Name and BrokerName columns)
       - symbol_to_name: normalized symbol -> name

    BrokerName is the name as it appears in broker notes, which may differ from the official Name.
    Also creates partial mappings for common name variations found in broker notes.
    """
    name_to_symbol = {}
    symbol_to_name = {}
    entries_list = []  # Store all entries for fuzzy matching later
    if not os.path.exists(path):
        return name_to_symbol, symbol_to_name, entries_list
    try:
        with open(path, newline='', encoding='utf-8') as fh:
            import csv
            import re
            reader = csv.DictReader(fh)
            for row in reader:
                sym = (row.get('Ticker') or row.get('ticker') or '').strip()
                name = (row.get('Name') or row.get('name') or '').strip()
                broker_name = (row.get('BrokerName') or row.get('brokername') or '').strip()

                if not sym and not name:
                    continue

                ks = normalize_key(sym) if sym else ''

                # Store entry for fuzzy matching (include broker_name)
                entries_list.append({'symbol': sym, 'name': name, 'broker_name': broker_name})

                # Map symbol to name
                if ks:
                    symbol_to_name[ks] = name

                # Map the ticker symbol without .SA suffix
                if sym and sym.endswith('.SA'):
                    base_sym = sym[:-3]
                    base_key = normalize_key(base_sym)
                    if base_key:
                        name_to_symbol[base_key] = sym

                # Priority 1: Map BrokerName (exact match from broker notes)
                if broker_name:
                    bn_key = normalize_key(broker_name)
                    bn_alpha = normalize_alpha(broker_name)
                    if bn_key:
                        name_to_symbol[bn_key] = sym
                    if bn_alpha:
                        name_to_symbol['ALPHA|' + bn_alpha] = sym
                    # Also map partial broker names
                    words = broker_name.upper().split()
                    for i in range(len(words)):
                        partial = ' '.join(words[:i+1])
                        partial_key = normalize_key(partial)
                        if partial_key and len(partial_key) >= 4 and partial_key not in name_to_symbol:
                            name_to_symbol[partial_key] = sym

                # Priority 2: Map official Name
                if name:
                    nk = normalize_key(name)
                    na = normalize_alpha(name)
                    if nk and nk not in name_to_symbol:
                        name_to_symbol[nk] = sym
                    if na and ('ALPHA|' + na) not in name_to_symbol:
                        name_to_symbol['ALPHA|' + na] = sym

                    # Create partial mappings from official name
                    words = name.upper().split()
                    if words:
                        first_word = words[0]
                        first_key = normalize_key(first_word)
                        if first_key and len(first_key) >= 4 and first_key not in name_to_symbol:
                            name_to_symbol[first_key] = sym

                        for i in range(1, min(len(words), 4)):
                            partial = ' '.join(words[:i+1])
                            partial_key = normalize_key(partial)
                            if partial_key and partial_key not in name_to_symbol:
                                name_to_symbol[partial_key] = sym

    except Exception:
        pass
    return name_to_symbol, symbol_to_name, entries_list


def find_latest_prices_for_symbols(symbols, candidates):
    """Scan StockDataDB.csv (candidates) bottom-up to find the most recent Close for requested symbols.
       Returns a map {requested_symbol: close_price}
    """
    path = find_file(candidates)
    if not path:
        return {}
    # build match map: normalized keys -> requested symbol
    match_map = {}
    for s in symbols:
        if not s:
            continue
        k = normalize_key(s)
        ka = normalize_alpha(s)
        match_map[k] = s
        match_map['ALPHA|' + ka] = s
        # also include uppercase raw form
        match_map[str(s).upper()] = s
    found = {}
    try:
        with open(path, 'r', encoding='utf-8') as fh:
            reader = csv.reader(fh)
            header = next(reader, None)
            if not header:
                return found
            header_clean = [h.strip() for h in header]
            # find stock and close indices
            stock_idx = None
            close_idx = None
            for i,h in enumerate(header_clean):
                if h.lower() == 'stock':
                    stock_idx = i
                if h.lower() == 'close':
                    close_idx = i
            if stock_idx is None or close_idx is None:
                return found
            # read all rows into memory (we'll scan reversed)
            rows = list(reader)
            for row in reversed(rows):
                if len(found) == len(match_map):
                    break
                if len(row) <= max(stock_idx, close_idx):
                    continue
                stock = row[stock_idx].strip() if row[stock_idx] is not None else ''
                close_raw = row[close_idx] if row[close_idx] is not None else ''
                if not stock:
                    continue
                kstock = normalize_key(stock)
                kastock = normalize_alpha(stock)
                # try keys in order of preference
                if kstock in match_map and match_map[kstock] not in found:
                    found[match_map[kstock]] = safe_float(close_raw)
                    continue
                if 'ALPHA|' + kastock in match_map and match_map['ALPHA|' + kastock] not in found:
                    found[match_map['ALPHA|' + kastock]] = safe_float(close_raw)
                    continue
                # direct uppercase match
                if stock.upper() in match_map and match_map[stock.upper()] not in found:
                    found[match_map[stock.upper]] = safe_float(close_raw)
                    continue
    except Exception:
        pass
    return found


def main():
    src = find_file(CSV_CANDIDATES)
    if not src:
        print('No ledger.csv found. Looked in:', CSV_CANDIDATES)
        return 1

    positions = consolidate_from_csv(src)

    # Load tickers.txt to map ledger "ticker" (often a full name) to actual symbol
    name_to_symbol, symbol_to_name, tickers_entries = load_tickers_map(TICKERS_TXT)

    # Attempt to enrich positions with target prices from scored_stocks.csv
    scored_maps = load_scored_targets(SCORED_STOCKS_CANDIDATES)

    for p in positions:
        ledger_label = p.get('ticker') or ''
        # Try to find symbol from parameters/tickers.txt using name normalization
        sym = None
        nk = normalize_key(ledger_label)
        na = normalize_alpha(ledger_label)

        # Strategy 1: Direct key match
        if nk and nk in name_to_symbol:
            sym = name_to_symbol[nk]
        # Strategy 2: Alpha-only match
        elif na and ('ALPHA|' + na) in name_to_symbol:
            sym = name_to_symbol['ALPHA|' + na]
        # Strategy 3: Partial/substring match - check if ledger_label is contained in any key
        if not sym:
            for key, symbol in name_to_symbol.items():
                if key.startswith('ALPHA|'):
                    continue
                # Check if the ledger label (normalized) is a substring of the key or vice versa
                if nk and len(nk) >= 4 and (nk in key or key in nk):
                    sym = symbol
                    break
        # Strategy 4: Token-based fuzzy match against tickers_entries
        if not sym and tickers_entries:
            import re
            ledger_tokens = set([t.upper() for t in re.split(r'[^A-Za-z0-9]+', ledger_label) if len(t) >= 3])
            best_match = None
            best_score = 0
            for entry in tickers_entries:
                entry_name = entry.get('name', '')
                entry_tokens = set([t.upper() for t in re.split(r'[^A-Za-z0-9]+', entry_name) if len(t) >= 3])
                # Score = number of matching tokens
                score = len(ledger_tokens & entry_tokens)
                if score > best_score:
                    best_score = score
                    best_match = entry
            if best_score >= 1 and best_match:
                sym = best_match.get('symbol')

        # If we found symbol via tickers.txt, prefer it for scored lookup
        tp = None
        if sym:
            # try direct symbol lookup in scored_maps
            by_sym = scored_maps.get('by_symbol', {})
            ks = normalize_key(sym)
            if ks and ks in by_sym:
                tp = by_sym[ks]['target']
            else:
                # fallback to the more general matcher using symbol or ledger label
                tp, mapped_sym = match_target_for_ticker(sym, scored_maps)
                if not tp:
                    tp, mapped_sym = match_target_for_ticker(ledger_label, scored_maps)
        else:
            # no mapping from tickers.txt, attempt best-effort scored lookup
            tp, mapped_sym = match_target_for_ticker(ledger_label, scored_maps)
            if mapped_sym and not sym:
                sym = mapped_sym

        p['target_price'] = tp if tp is not None else None
        p['symbol'] = sym if sym is not None else None

    # Populate current prices by scanning StockDataDB.csv once
    symbols_list = [p.get('symbol') or p.get('ticker') for p in positions]
    prices_map = find_latest_prices_for_symbols(symbols_list, FINDB_CANDIDATES)
    for p in positions:
        key = p.get('symbol') or p.get('ticker')
        p['current_price'] = prices_map.get(key) if key in prices_map else None

    out = {
        'generated_at': datetime.now(timezone.utc).isoformat(),
        'source': os.path.relpath(src),
        'positions': positions
    }
    # write JSON directly into web-accessible html/data directory (don't write to repo-level data/)
    os.makedirs(os.path.dirname(OUT_JSON) or '.', exist_ok=True)
    with open(OUT_JSON, 'w', encoding='utf-8') as fh:
        json.dump(out, fh, ensure_ascii=False, indent=2)

    print(f'Wrote {OUT_JSON} with {len(positions)} positions (generated_at={out["generated_at"]})')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
