#!/usr/bin/env python3
"""
engines/B1_Process_Notes.py

Consolidated orchestrator to process broker-note PDFs in `Notas_Negociação/`:
- find PDFs
- extract text (pdfplumber / OCR fallback via transactions_parser)
- parse trades and fees
- append to transactions CSVs (idempotent by broker_document)
- rebuild ledger (uses transactions_ledger utilities)
- maintain a small `data/processed_notes.json` manifest to avoid reprocessing files

This is intended to be run by the main pipeline (A_Portfolio_Pipeline.sh) after price download
and before scoring/portfolio stages.
"""

from pathlib import Path
import sys
import csv
from datetime import datetime
import json

# Ensure project root is on sys.path when running from engines/
ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from engines.B11_Transactions_Parser import (
    NOTAS_DIR, TX_FILE, FEES_FILE, LEDGER_FILE,
    extract_text_from_pdf, parse_broker_note_text, format_decimal
)
from engines.B12_Transactions_Ledger import (
    load_transactions, load_fees, allocate_fees_proportional, build_ledger, write_ledger, compute_summary
)

# Resolve relative project paths to absolute paths against ROOT
# (transactions_parser defines them relative to CWD)

def _resolve_path(p):
    try:
        return p if p.is_absolute() else (ROOT / p)
    except Exception:
        return p

NOTAS_DIR = _resolve_path(NOTAS_DIR)
TX_FILE = _resolve_path(TX_FILE)
FEES_FILE = _resolve_path(FEES_FILE)
LEDGER_FILE = _resolve_path(LEDGER_FILE)
PROCESSED_MANIFEST = ROOT / 'data' / 'processed_notes.json'


def find_pdfs_to_process():
    if not NOTAS_DIR.exists():
        return []
    pdfs = sorted(NOTAS_DIR.glob('*.pdf'), key=lambda p: p.stat().st_mtime)
    return pdfs


def broker_doc_exists(broker_doc):
    if not TX_FILE.exists():
        return False
    with TX_FILE.open(newline='', encoding='utf-8') as f:
        r = csv.DictReader(f)
        for row in r:
            if (row.get('broker_document') or '') == (broker_doc or ''):
                return True
    return False


def load_processed_manifest():
    if not PROCESSED_MANIFEST.exists():
        return {}
    try:
        return json.loads(PROCESSED_MANIFEST.read_text(encoding='utf-8'))
    except Exception:
        return {}


def save_processed_manifest(m):
    PROCESSED_MANIFEST.parent.mkdir(parents=True, exist_ok=True)
    PROCESSED_MANIFEST.write_text(json.dumps(m, ensure_ascii=False, indent=2), encoding='utf-8')


def append_parsed_csvs(parsed):
    trades = parsed.get('trades', [])
    fees = parsed.get('fees', [])
    broker_doc = parsed.get('broker_document') or f"manual-{datetime.now().strftime('%Y%m%d%H%M%S')}"

    tx_fieldnames = ['transaction_id', 'portfolio', 'trade_date', 'settlement_date', 'broker_document', 'broker', 'ticker', 'isin', 'side', 'quantity', 'unit_price', 'gross_value', 'currency', 'fx_rate', 'order_type', 'broker_order_id', 'notes', 'import_ts']
    fees_fieldnames = ['transaction_id', 'category', 'kind', 'fee_type', 'amount', 'currency', 'description']

    now = datetime.now().isoformat()

    # Prepare to append transactions
    write_tx_header = not TX_FILE.exists()
    TX_FILE.parent.mkdir(parents=True, exist_ok=True)
    with TX_FILE.open('a', newline='', encoding='utf-8') as f:
        w = csv.DictWriter(f, fieldnames=tx_fieldnames)
        if write_tx_header:
            w.writeheader()
        for i, t in enumerate(trades, start=1):
            tid = f"{broker_doc}-{i}"
            qty_val = t.get('quantity')
            try:
                qty_str = str(int(qty_val))
            except Exception:
                qty_str = str(qty_val)
            unit_str = format_decimal(t.get('unit_price'), 4) if t.get('unit_price') is not None else ''
            gross_str = format_decimal(t.get('gross_value'), 2) if t.get('gross_value') is not None else ''
            row = {
                'transaction_id': tid,
                'portfolio': 'MAIN',
                'trade_date': parsed.get('trade_date') or '',
                'settlement_date': parsed.get('settlement_date') or '',
                'broker_document': broker_doc,
                'broker': parsed.get('broker') or '',
                'ticker': t.get('ticker'),
                'isin': '',
                'side': t.get('side'),
                'quantity': qty_str,
                'unit_price': unit_str,
                'gross_value': gross_str,
                'currency': 'BRL',
                'fx_rate': '1.0',
                'order_type': '',
                'broker_order_id': broker_doc,
                'notes': t.get('description'),
                'import_ts': now
            }
            w.writerow(row)

    # Append fees
    write_fees_header = not FEES_FILE.exists()
    FEES_FILE.parent.mkdir(parents=True, exist_ok=True)
    with FEES_FILE.open('a', newline='', encoding='utf-8') as f:
        w = csv.DictWriter(f, fieldnames=fees_fieldnames)
        if write_fees_header:
            w.writeheader()
        for fee in fees:
            amt_str = format_decimal(fee.get('amount'), 2)
            w.writerow({'transaction_id': broker_doc, 'category': fee.get('category', 'Other'), 'kind': fee.get('kind', 'fee'), 'fee_type': fee.get('fee_type'), 'amount': amt_str, 'currency': 'BRL', 'description': fee.get('description')})

    return broker_doc


def rebuild_ledger():
    txs = load_transactions(TX_FILE)
    fees_by_doc = load_fees(FEES_FILE)
    alloc = allocate_fees_proportional(txs, fees_by_doc)
    ledger = build_ledger(txs, alloc)
    write_ledger(LEDGER_FILE, ledger)
    summary = compute_summary(ledger)
    return summary


def main():
    pdfs = find_pdfs_to_process()
    if not pdfs:
        print('No PDFs found in', NOTAS_DIR)
        return

    manifest = load_processed_manifest()
    processed = manifest.get('processed', [])
    processed_files = set(processed)

    any_new = False
    new_docs = []

    for pdf in pdfs:
        key = str(pdf.name)
        if key in processed_files:
            # already processed this file
            continue
        print('Processing PDF:', pdf)
        text = extract_text_from_pdf(pdf)
        if not text or not text.strip():
            print('Failed to extract text from PDF:', pdf)
            # mark as processed to avoid infinite retries? keep as not-processed so user can fix
            continue
        parsed = parse_broker_note_text(text)
        broker_doc = parsed.get('broker_document')
        if broker_doc and broker_doc_exists(broker_doc):
            print('Broker document already exists in transactions CSVs:', broker_doc)
            processed_files.add(key)
            continue
        if not parsed.get('trades'):
            print('No trades parsed from document:', pdf)
            # still mark as processed to avoid repeated attempts on documents that contain only statements
            processed_files.add(key)
            continue
        broker_doc = append_parsed_csvs(parsed)
        print('Appended parsed data for broker_document=', broker_doc)
        new_docs.append(broker_doc)
        processed_files.add(key)
        any_new = True

    # save manifest
    manifest['processed'] = sorted(list(processed_files))
    manifest['last_run'] = datetime.now().isoformat()
    if new_docs:
        manifest['last_added'] = new_docs
    save_processed_manifest(manifest)

    if any_new:
        print('Rebuilding ledger...')
        summary = rebuild_ledger()
        print('Ledger rebuilt at', LEDGER_FILE)
        print('Summary:')
        print(' Total invested (BUY):', summary['total_invested'])
        print(' Total implementation cost (fees):', summary['total_implementation_cost'])
        print(' Implementation cost (% of invested):', summary['implementation_pct'], '%')
    else:
        print('No new documents processed. Ledger unchanged.')


if __name__ == '__main__':
    main()

