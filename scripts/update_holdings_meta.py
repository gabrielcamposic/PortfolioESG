#!/usr/bin/env python3
import csv, json, os

# Use absolute paths based on script location
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.abspath(os.path.join(SCRIPT_DIR, '..'))

CSV = os.path.join(PROJECT_ROOT, 'data', 'results', 'scored_stocks.csv')
JSON = os.path.join(PROJECT_ROOT, 'html', 'data', 'latest_run_summary.json')

if not os.path.exists(CSV):
    print('Scored stocks CSV not found:', CSV)
    raise SystemExit(1)
if not os.path.exists(JSON):
    print('Latest run summary JSON not found:', JSON)
    raise SystemExit(1)

# Read CSV into a dict keeping the latest occurrence per Stock (assuming file appends newer runs)
stocks_map = {}
with open(CSV, newline='', encoding='utf-8') as f:
    reader = csv.DictReader(f)
    for row in reader:
        stock = row.get('Stock')
        if not stock:
            continue
        stocks_map[stock] = row

with open(JSON, 'r', encoding='utf-8') as f:
    js = json.load(f)

p = js.get('best_portfolio_details', {})
holdings = p.get('stocks', [])

if not holdings:
    print('No holdings found in JSON; nothing to do')
else:
    hm = {}
    for s in holdings:
        r = stocks_map.get(s)
        if r:
            fpe = r.get('forwardPE')
            mom = r.get('Momentum')
            current_price = r.get('CurrentPrice')
            target_price = r.get('TargetPrice')
            try:
                fpe_v = float(fpe) if fpe not in (None, '', 'nan') else None
            except Exception:
                fpe_v = None
            try:
                mom_v = float(mom) if mom not in (None, '', 'nan') else None
            except Exception:
                mom_v = None
            try:
                current_price_v = float(current_price) if current_price not in (None, '', 'nan') else None
            except Exception:
                current_price_v = None
            try:
                target_price_v = float(target_price) if target_price not in (None, '', 'nan') else None
            except Exception:
                target_price_v = None
            hm[s] = {
                'forwardPE': fpe_v,
                'Momentum': mom_v,
                'currentPrice': current_price_v,
                'targetPrice': target_price_v
            }
        else:
            hm[s] = {'forwardPE': None, 'Momentum': None, 'currentPrice': None, 'targetPrice': None}
    js.setdefault('best_portfolio_details', {})['holdings_meta'] = hm

    # Backup original JSON
    bak = JSON + '.bak'
    try:
        with open(bak, 'w', encoding='utf-8') as f:
            json.dump(js, f, indent=2, ensure_ascii=False)
    except Exception:
        pass

    with open(JSON, 'w', encoding='utf-8') as f:
        json.dump(js, f, indent=4, ensure_ascii=False)
    print('Updated', JSON)

