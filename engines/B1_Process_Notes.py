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

This is intended to be run by the main pipeline (A_Portfolio.sh) after price download
and before scoring/portfolio stages.
"""

# --- Script Version ---
PROCESS_NOTES_VERSION = "2.0.0"  # Refactored with shared_utils, logging, and parameter loading

from pathlib import Path
import sys
import csv
import re
import logging
import time
from datetime import datetime
import json
from typing import Dict, List, Tuple, Optional, Any

# Ensure project root is on sys.path when running from engines/
ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from shared_tools.shared_utils import (
    setup_logger,
    load_parameters_from_file,
    initialize_performance_data,
    log_performance_data,
)

from engines.B11_Transactions_Parser import (
    extract_text_from_pdf, parse_broker_note_text, format_decimal
)
from engines.B12_Transactions_Ledger import (
    load_transactions, load_fees, allocate_fees_proportional, build_ledger, write_ledger, compute_summary
)

# ----------------------------------------------------------- #
#                      Configuration                          #
# ----------------------------------------------------------- #

def load_config(logger: logging.Logger) -> Dict[str, Any]:
    """Load configuration from parameters file with fallbacks."""
    # Default values for paths
    defaults = {
        'NOTAS_DIR': str(ROOT / 'Notas_Negociação'),
        'TX_FILE': str(ROOT / 'data' / 'transactions_parsed.csv'),
        'FEES_FILE': str(ROOT / 'data' / 'fees_parsed.csv'),
        'LEDGER_FILE': str(ROOT / 'data' / 'ledger.csv'),
        'PROCESSED_MANIFEST': str(ROOT / 'html' / 'data' / 'processed_notes.json'),
        'TICKERS_FILE': str(ROOT / 'parameters' / 'tickers.txt'),
        'PROCESS_NOTES_PERF_FILE': str(ROOT / 'data' / 'Results' / 'process_notes_performance.csv'),
    }

    # Expected parameters with their types (for load_parameters_from_file)
    expected_types = {
        'NOTAS_DIR': str,
        'TX_FILE': str,
        'FEES_FILE': str,
        'LEDGER_FILE': str,
        'PROCESSED_MANIFEST': str,
        'TICKERS_FILE': str,
        'PROCESS_NOTES_PERF_FILE': str,
    }

    params = load_parameters_from_file(
        str(ROOT / 'parameters' / 'paths.txt'),
        expected_types,
        logger
    )

    # Build config with resolved paths, using defaults if not found
    config = {
        'NOTAS_DIR': Path(params.get('NOTAS_DIR', defaults['NOTAS_DIR'])),
        'TX_FILE': Path(params.get('TX_FILE', defaults['TX_FILE'])),
        'FEES_FILE': Path(params.get('FEES_FILE', defaults['FEES_FILE'])),
        'LEDGER_FILE': Path(params.get('LEDGER_FILE', defaults['LEDGER_FILE'])),
        'PROCESSED_MANIFEST': Path(params.get('PROCESSED_MANIFEST', defaults['PROCESSED_MANIFEST'])),
        'TICKERS_FILE': Path(params.get('TICKERS_FILE', defaults['TICKERS_FILE'])),
        'PERFORMANCE_FILE': Path(params.get('PROCESS_NOTES_PERF_FILE', defaults['PROCESS_NOTES_PERF_FILE'])),
    }

    # Ensure paths are absolute
    for key, path in config.items():
        if not path.is_absolute():
            config[key] = ROOT / path

    return config


# ----------------------------------------------------------- #
#                     Helper Functions                        #
# ----------------------------------------------------------- #

def normalize_for_match(s: Optional[str]) -> str:
    """Normalize a string for fuzzy matching: uppercase, remove spaces and punctuation."""
    if not s:
        return ''
    return re.sub(r'[^A-Z0-9]', '', str(s).upper())


def update_broker_names_in_tickers(broker_names_found: Dict[str, str], tickers_file: Path, logger: logging.Logger) -> None:
    """
    Update tickers.txt with BrokerName values for matched symbols.
    broker_names_found: dict of {symbol: broker_name} to update

    Only updates if the current BrokerName is empty for that symbol.
    """
    if not broker_names_found or not tickers_file.exists():
        return

    try:
        # Read all rows
        rows = []
        fieldnames = None
        with tickers_file.open('r', newline='', encoding='utf-8') as f:
            reader = csv.DictReader(f)
            fieldnames = reader.fieldnames
            for row in reader:
                rows.append(row)

        if not fieldnames or 'BrokerName' not in fieldnames:
            logger.warning("Cannot update BrokerName: column not found in tickers.txt")
            return

        # Update rows where BrokerName is empty and we have a match
        updated = False
        for row in rows:
            ticker = (row.get('Ticker') or '').strip()
            current_broker_name = (row.get('BrokerName') or '').strip()

            if ticker in broker_names_found and not current_broker_name:
                row['BrokerName'] = broker_names_found[ticker]
                updated = True
                logger.info(f"Updated BrokerName for {ticker}: {broker_names_found[ticker]}")

        # Write back if updated
        if updated:
            with tickers_file.open('w', newline='', encoding='utf-8') as f:
                writer = csv.DictWriter(f, fieldnames=fieldnames)
                writer.writeheader()
                writer.writerows(rows)

    except FileNotFoundError:
        logger.error(f"Tickers file not found: {tickers_file}")
    except csv.Error as e:
        logger.error(f"CSV error reading tickers file: {e}")
    except IOError as e:
        logger.error(f"IO error updating tickers file: {e}")


def find_symbol_for_broker_name(broker_name: str, tickers_file: Path, logger: logging.Logger) -> Tuple[Optional[str], bool]:
    """
    Try to find the symbol (Ticker) for a given broker name by matching against tickers.txt.
    Returns (symbol, matched) tuple or (None, False) if not found.
    """
    if not broker_name or not tickers_file.exists():
        return None, False

    broker_norm = normalize_for_match(broker_name)
    # Extract first word for partial matching
    first_word = broker_name.split()[0].upper() if broker_name.split() else ''
    first_word_norm = normalize_for_match(first_word)

    try:
        with tickers_file.open('r', newline='', encoding='utf-8') as f:
            reader = csv.DictReader(f)
            for row in reader:
                ticker = (row.get('Ticker') or '').strip()
                name = (row.get('Name') or '').strip()
                existing_broker = row.get('BrokerName')

                # Handle None values
                if existing_broker is None:
                    existing_broker = ''
                else:
                    existing_broker = existing_broker.strip()

                # Check if BrokerName already matches
                if existing_broker:
                    if normalize_for_match(existing_broker) == broker_norm:
                        return ticker, True

                # Check if official Name matches (partial)
                name_norm = normalize_for_match(name)
                if first_word_norm and len(first_word_norm) >= 4:
                    if first_word_norm in name_norm or name_norm.startswith(first_word_norm):
                        return ticker, True

    except FileNotFoundError:
        logger.warning(f"Tickers file not found: {tickers_file}")
    except csv.Error as e:
        logger.warning(f"CSV error reading tickers file: {e}")

    return None, False


def find_pdfs_to_process(notas_dir: Path) -> List[Path]:
    """Find all PDFs in the notes directory, sorted by modification time."""
    if not notas_dir.exists():
        return []
    pdfs = sorted(notas_dir.glob('*.pdf'), key=lambda p: p.stat().st_mtime)
    return pdfs


def broker_doc_exists(broker_doc: str, tx_file: Path) -> bool:
    """Check if a broker document already exists in the transactions file."""
    if not tx_file.exists():
        return False
    try:
        with tx_file.open(newline='', encoding='utf-8') as f:
            reader = csv.DictReader(f)
            for row in reader:
                if (row.get('broker_document') or '') == (broker_doc or ''):
                    return True
    except (FileNotFoundError, csv.Error):
        return False
    return False


def load_processed_manifest(manifest_path: Path) -> Dict[str, Any]:
    """Load the processed notes manifest."""
    if not manifest_path.exists():
        return {}
    try:
        return json.loads(manifest_path.read_text(encoding='utf-8'))
    except (json.JSONDecodeError, IOError):
        return {}


def save_processed_manifest(manifest: Dict[str, Any], manifest_path: Path) -> None:
    """Save the processed notes manifest."""
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding='utf-8')


def validate_parsed_data(parsed: Dict[str, Any], logger: logging.Logger) -> bool:
    """Validate that parsed data has required fields."""
    if not parsed:
        logger.warning("Parsed data is empty")
        return False

    # Check for trades
    trades = parsed.get('trades', [])
    if not trades:
        logger.warning("No trades found in parsed data")
        return False

    # Check for trade_date (required for ledger)
    trade_date = parsed.get('trade_date')
    if not trade_date:
        logger.warning("Missing trade_date in parsed data")
        # Not a fatal error, but worth logging

    # Check for broker_document (required for idempotency)
    broker_doc = parsed.get('broker_document')
    if not broker_doc:
        logger.warning("Missing broker_document in parsed data - will generate one")

    return True


def append_parsed_csvs(parsed: Dict[str, Any], config: Dict[str, Any], logger: logging.Logger) -> str:
    """Append parsed trades and fees to CSV files."""
    trades = parsed.get('trades', [])
    fees = parsed.get('fees', [])
    broker_doc = parsed.get('broker_document') or f"manual-{datetime.now().strftime('%Y%m%d%H%M%S')}"

    tx_fieldnames = [
        'transaction_id', 'portfolio', 'trade_date', 'settlement_date', 'broker_document',
        'broker', 'ticker', 'isin', 'side', 'quantity', 'unit_price', 'gross_value',
        'currency', 'fx_rate', 'order_type', 'broker_order_id', 'notes', 'import_ts'
    ]
    fees_fieldnames = ['transaction_id', 'category', 'kind', 'fee_type', 'amount', 'currency', 'description']

    now = datetime.now().isoformat()
    tx_file = config['TX_FILE']
    fees_file = config['FEES_FILE']

    try:
        # Prepare to append transactions
        write_tx_header = not tx_file.exists()
        tx_file.parent.mkdir(parents=True, exist_ok=True)

        with tx_file.open('a', newline='', encoding='utf-8') as f:
            writer = csv.DictWriter(f, fieldnames=tx_fieldnames, quoting=csv.QUOTE_MINIMAL)
            if write_tx_header:
                writer.writeheader()

            for i, t in enumerate(trades, start=1):
                tid = f"{broker_doc}-{i}"
                qty_val = t.get('quantity')
                try:
                    qty_str = str(int(qty_val))
                except (ValueError, TypeError):
                    qty_str = str(qty_val) if qty_val else '0'

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
                writer.writerow(row)

        logger.debug(f"Appended {len(trades)} transactions to {tx_file}")

    except IOError as e:
        logger.error(f"Failed to write transactions: {e}")
        raise

    try:
        # Append fees
        write_fees_header = not fees_file.exists()
        fees_file.parent.mkdir(parents=True, exist_ok=True)

        with fees_file.open('a', newline='', encoding='utf-8') as f:
            writer = csv.DictWriter(f, fieldnames=fees_fieldnames, quoting=csv.QUOTE_MINIMAL)
            if write_fees_header:
                writer.writeheader()

            for fee in fees:
                amt_str = format_decimal(fee.get('amount'), 2)
                writer.writerow({
                    'transaction_id': broker_doc,
                    'category': fee.get('category', 'Other'),
                    'kind': fee.get('kind', 'fee'),
                    'fee_type': fee.get('fee_type'),
                    'amount': amt_str,
                    'currency': 'BRL',
                    'description': fee.get('description')
                })

        logger.debug(f"Appended {len(fees)} fees to {fees_file}")

    except IOError as e:
        logger.error(f"Failed to write fees: {e}")
        raise

    return broker_doc


def rebuild_ledger(config: Dict[str, Any], logger: logging.Logger) -> Dict[str, Any]:
    """Rebuild the ledger from transactions and fees."""
    tx_file = config['TX_FILE']
    fees_file = config['FEES_FILE']
    ledger_file = config['LEDGER_FILE']

    txs = load_transactions(tx_file)
    fees_by_doc = load_fees(fees_file)
    alloc = allocate_fees_proportional(txs, fees_by_doc)
    ledger = build_ledger(txs, alloc)
    write_ledger(ledger_file, ledger)
    summary = compute_summary(ledger)

    logger.info(f"Ledger rebuilt at {ledger_file}")
    return summary


def _log_rebuild_summary(summary: Dict[str, Any], logger: logging.Logger) -> None:
    """Log the rebuild summary in a consistent format."""
    logger.info("Ledger Summary:")
    logger.info(f"  Total invested (BUY): {summary.get('total_invested', 0)}")
    logger.info(f"  Total implementation cost (fees): {summary.get('total_implementation_cost', 0)}")
    logger.info(f"  Implementation cost (% of invested): {summary.get('implementation_pct', 0)}%")


# ----------------------------------------------------------- #
#                         Main                                #
# ----------------------------------------------------------- #

def main():
    """Main entry point for processing broker notes."""
    start_time = time.time()

    # Setup logger
    logger = setup_logger(
        'ProcessNotesRunner',
        log_file=str(ROOT / 'logs' / 'process_notes.log'),
        web_log_file=None,  # No web logging for this script
        level=logging.INFO
    )

    logger.info(f"Starting B1_Process_Notes.py v{PROCESS_NOTES_VERSION}")

    # Load configuration
    config = load_config(logger)

    # Initialize performance tracking
    perf_data = initialize_performance_data('B1_Process_Notes', PROCESS_NOTES_VERSION)

    try:
        # Find PDFs to process
        pdfs = find_pdfs_to_process(config['NOTAS_DIR'])
        if not pdfs:
            logger.info(f"No PDFs found in {config['NOTAS_DIR']}")
            perf_data['pdfs_found'] = 0
            perf_data['pdfs_processed'] = 0

            # Still rebuild ledger for consistency
            logger.info("Rebuilding ledger to ensure consistency...")
            summary = rebuild_ledger(config, logger)
            _log_rebuild_summary(summary, logger)

            perf_data['status'] = 'success'
            perf_data['execution_time'] = time.time() - start_time
            log_performance_data(perf_data, config['PERFORMANCE_FILE'], logger)
            return

        logger.info(f"Found {len(pdfs)} PDFs in {config['NOTAS_DIR']}")
        perf_data['pdfs_found'] = len(pdfs)

        # Load manifest
        manifest = load_processed_manifest(config['PROCESSED_MANIFEST'])
        processed = manifest.get('processed', [])
        processed_files = set(processed)

        any_new = False
        new_docs = []
        broker_names_to_update = {}
        pdfs_processed = 0
        pdfs_skipped = 0

        for pdf in pdfs:
            key = str(pdf.name)
            if key in processed_files:
                pdfs_skipped += 1
                continue

            logger.info(f"Processing PDF: {pdf}")

            # Extract text
            text = extract_text_from_pdf(pdf)
            if not text or not text.strip():
                logger.warning(f"Failed to extract text from PDF: {pdf}")
                continue

            # Parse broker note
            parsed = parse_broker_note_text(text)

            # Validate parsed data
            if not validate_parsed_data(parsed, logger):
                processed_files.add(key)
                continue

            # Check if broker document already exists
            broker_doc = parsed.get('broker_document')
            if broker_doc and broker_doc_exists(broker_doc, config['TX_FILE']):
                logger.info(f"Broker document already exists: {broker_doc}")
                processed_files.add(key)
                continue

            # Collect broker names for updating tickers.txt
            for trade in parsed.get('trades', []):
                ticker_name = trade.get('ticker', '').strip()
                if ticker_name:
                    symbol, matched = find_symbol_for_broker_name(ticker_name, config['TICKERS_FILE'], logger)
                    if symbol and matched and symbol not in broker_names_to_update:
                        broker_names_to_update[symbol] = ticker_name

            # Append to CSVs
            broker_doc = append_parsed_csvs(parsed, config, logger)
            logger.info(f"Appended parsed data for broker_document={broker_doc}")

            new_docs.append(broker_doc)
            processed_files.add(key)
            any_new = True
            pdfs_processed += 1

        logger.info(f"Processed {pdfs_processed} new PDFs, skipped {pdfs_skipped} already processed")
        perf_data['pdfs_processed'] = pdfs_processed
        perf_data['pdfs_skipped'] = pdfs_skipped

        # Update tickers.txt with new broker names
        if broker_names_to_update:
            logger.info(f"Updating {len(broker_names_to_update)} BrokerNames in tickers.txt...")
            update_broker_names_in_tickers(broker_names_to_update, config['TICKERS_FILE'], logger)

        # Save manifest
        manifest['processed'] = sorted(list(processed_files))
        manifest['last_run'] = datetime.now().isoformat()
        if new_docs:
            manifest['last_added'] = new_docs
        save_processed_manifest(manifest, config['PROCESSED_MANIFEST'])

        # Rebuild ledger
        logger.info("Rebuilding ledger...")
        summary = rebuild_ledger(config, logger)
        _log_rebuild_summary(summary, logger)

        perf_data['total_invested'] = str(summary.get('total_invested', 0))
        perf_data['implementation_cost_pct'] = str(summary.get('implementation_pct', 0))
        perf_data['status'] = 'success'

    except Exception as e:
        logger.critical(f"An unhandled exception occurred: {e}", exc_info=True)
        perf_data['status'] = 'error'
        perf_data['error'] = str(e)
        raise

    finally:
        perf_data['execution_time'] = time.time() - start_time
        # log_performance_data expects a dict with key, so pass config as dict
        perf_params = {'PERFORMANCE_FILE': str(config['PERFORMANCE_FILE'])}
        log_performance_data(perf_data, perf_params, logger, 'PERFORMANCE_FILE')
        logger.info(f"Process notes script finished in {perf_data['execution_time']:.2f} seconds")


if __name__ == '__main__':
    main()
