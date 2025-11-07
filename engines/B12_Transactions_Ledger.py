from decimal import Decimal, ROUND_HALF_UP
import csv
from collections import defaultdict
from pathlib import Path

from engines.B11_Transactions_Parser import parse_decimal, date_to_iso


def load_transactions(path: Path):
    txs = []
    with path.open(newline='', encoding='utf-8') as f:
        r = csv.DictReader(f)
        for row in r:
            gross = parse_decimal(row.get('gross_value') or row.get('value') or '')
            tx = {
                'transaction_id': row.get('transaction_id'),
                'broker_document': row.get('broker_document'),
                'portfolio': row.get('portfolio') or 'MAIN',
                'trade_date': date_to_iso(row.get('trade_date') or ''),
                'settlement_date': date_to_iso(row.get('settlement_date') or ''),
                'ticker': row.get('ticker') or row.get('description') or '',
                'side': (row.get('side') or '').upper(),
                'quantity': parse_decimal(row.get('quantity') or '0'),
                'unit_price': parse_decimal(row.get('unit_price') or '0'),
                'gross_value': gross,
                'currency': row.get('currency') or 'BRL',
                'notes': row.get('notes') or ''
            }
            txs.append(tx)
    return txs


def load_fees(path: Path):
    fees_by_doc = defaultdict(list)
    with path.open(newline='', encoding='utf-8') as f:
        r = csv.DictReader(f)
        for row in r:
            tid = row.get('transaction_id')
            amt = parse_decimal(row.get('amount'))
            fees_by_doc[tid].append({
                'fee_type': row.get('fee_type'),
                'amount': amt,
                'category': row.get('category') or 'Other',
                'kind': row.get('kind') or 'fee',
                'currency': row.get('currency') or 'BRL',
                'description': row.get('description') or ''
            })
    return fees_by_doc


def allocate_fees_proportional(txs, fees_by_doc):
    # Map broker_document -> list of txs
    by_doc = defaultdict(list)
    for tx in txs:
        doc = tx.get('broker_document')
        by_doc[doc].append(tx)

    # initialize allocated fees per tx
    alloc = {tx['transaction_id']: Decimal('0') for tx in txs}

    for doc, fees in fees_by_doc.items():
        doc_txs = by_doc.get(doc, [])
        if not doc_txs:
            # no matching trades: skip or attach to synthetic row
            continue
        total_gross = sum((t['gross_value'] for t in doc_txs), Decimal('0'))
        if total_gross == 0:
            # if zero, split equally
            per_count = sum((f['amount'] for f in fees), Decimal('0')) / Decimal(len(doc_txs))
            for t in doc_txs:
                alloc[t['transaction_id']] += per_count
            continue
        # for each fee, allocate proportionally across doc_txs
        for fee in fees:
            amount = fee['amount']
            # for numerical stability, allocate and round to cents
            remaining = amount
            allocated_sum = Decimal('0')
            for i, t in enumerate(doc_txs):
                if i == len(doc_txs) - 1:
                    share = remaining
                else:
                    share = (amount * t['gross_value'] / total_gross).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)
                    remaining -= share
                alloc[t['transaction_id']] += share
                allocated_sum += share
    return alloc


def build_ledger(txs, alloc):
    ledger = []
    for tx in txs:
        txid = tx['transaction_id']
        fees = alloc.get(txid, Decimal('0'))
        taxes = Decimal('0')
        gross = tx['gross_value']
        if tx['side'] == 'BUY' or tx['side'] == 'C' or tx['side'] == 'COMPRA':
            total_cost = gross + fees + taxes
            net_cash_flow = -total_cost  # cash out
        else:
            total_cost = gross - fees - taxes
            net_cash_flow = total_cost  # cash in
        effective_price = (total_cost / tx['quantity']).quantize(Decimal('0.0001')) if tx['quantity'] != 0 else None
        ledger.append({
            'transaction_id': txid,
            'portfolio': tx['portfolio'],
            'trade_date': tx['trade_date'],
            'settlement_date': tx['settlement_date'],
            'broker_document': tx['broker_document'],
            'ticker': tx['ticker'],
            'side': tx['side'],
            'quantity': str(tx['quantity']),
            'unit_price': str(tx['unit_price']),
            'gross_value': str(gross),
            'allocated_fees': str(fees),
            'total_cost': str(total_cost),
            'net_cash_flow': str(net_cash_flow),
            'effective_price': str(effective_price) if effective_price is not None else ''
        })
    return ledger


def write_ledger(path: Path, ledger):
    fieldnames = ['transaction_id','portfolio','trade_date','settlement_date','broker_document','ticker','side','quantity','unit_price','gross_value','allocated_fees','total_cost','net_cash_flow','effective_price']
    with path.open('w', newline='', encoding='utf-8') as f:
        w = csv.DictWriter(f, fieldnames=fieldnames)
        w.writeheader()
        for r in ledger:
            w.writerow(r)


def compute_summary(ledger):
    total_gross = Decimal('0')
    total_impl = Decimal('0')
    for r in ledger:
        if (r['side'] or '').upper() in ('BUY','C','COMPRA'):
            total_gross += Decimal(r['gross_value'])
            total_impl += Decimal(r['allocated_fees'])
    pct = (total_impl / total_gross * Decimal('100')).quantize(Decimal('0.01')) if total_gross != 0 else Decimal('0')
    return {'total_invested': total_gross, 'total_implementation_cost': total_impl, 'implementation_pct': pct}
