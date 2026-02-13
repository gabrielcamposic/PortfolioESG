#!/usr/bin/env python3
"""
Migration script: Consolidate findata storage for GCP deployment.

This script:
1. Extracts all skip.json files from findata/*/skip.json into a single findb/skipped_tickers.json
2. Validates that StockDataDB.csv contains all data from individual CSVs
3. Optionally removes individual CSV files from findata/ to reduce storage
4. Creates a backup before any destructive operation

Usage:
    python scripts/migrate_findata_to_consolidated.py [--dry-run] [--no-backup] [--remove-csvs]

    --dry-run     Show what would be done without making changes
    --no-backup   Skip creating backup (not recommended)
    --remove-csvs Actually remove CSV files after validation (destructive)
"""

import os
import sys
import json
import shutil
import argparse
from datetime import datetime
from pathlib import Path
from typing import Optional
import pandas as pd

# Add project root to path
SCRIPT_DIR = Path(__file__).parent.absolute()
PROJECT_ROOT = SCRIPT_DIR.parent
sys.path.insert(0, str(PROJECT_ROOT))

# Paths
FINDATA_DIR = PROJECT_ROOT / 'data' / 'findata'
FINDB_DIR = PROJECT_ROOT / 'data' / 'findb'
STOCK_DATA_DB = FINDB_DIR / 'StockDataDB.csv'
SKIPPED_TICKERS_FILE = FINDB_DIR / 'skipped_tickers.json'
BACKUP_DIR = PROJECT_ROOT / 'data' / 'backup'


def log(msg: str, level: str = "INFO"):
    """Simple logging with timestamp."""
    timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    print(f"[{timestamp}] [{level}] {msg}")


def consolidate_skip_files(dry_run: bool = False) -> dict:
    """
    Consolidate all individual skip.json files into a single JSON file.

    Returns:
        dict: Mapping of ticker -> skip_data (list of skipped dates or ["ALL"])
    """
    log("Scanning for skip.json files in findata/...")

    consolidated_skips = {}
    skip_files_found = 0

    if not FINDATA_DIR.exists():
        log(f"findata directory not found at {FINDATA_DIR}", "WARNING")
        return consolidated_skips

    for ticker_dir in FINDATA_DIR.iterdir():
        if not ticker_dir.is_dir():
            continue

        skip_file = ticker_dir / 'skip.json'
        if skip_file.exists():
            skip_files_found += 1
            try:
                with open(skip_file, 'r') as f:
                    skip_data = json.load(f)

                ticker = ticker_dir.name
                consolidated_skips[ticker] = skip_data

                # Report permanently skipped tickers
                if skip_data == ["ALL"]:
                    log(f"  Ticker {ticker}: permanently skipped (invalid/delisted)")
                else:
                    log(f"  Ticker {ticker}: {len(skip_data)} dates skipped")

            except json.JSONDecodeError as e:
                log(f"  Error reading {skip_file}: {e}", "ERROR")
            except Exception as e:
                log(f"  Unexpected error with {skip_file}: {e}", "ERROR")

    log(f"Found {skip_files_found} skip.json files")
    log(f"Consolidated skips for {len(consolidated_skips)} tickers")

    # Count permanently skipped
    permanent_skips = sum(1 for v in consolidated_skips.values() if v == ["ALL"])
    log(f"  - Permanently skipped (delisted): {permanent_skips}")
    log(f"  - With partial date skips: {len(consolidated_skips) - permanent_skips}")

    if not dry_run and consolidated_skips:
        FINDB_DIR.mkdir(parents=True, exist_ok=True)
        with open(SKIPPED_TICKERS_FILE, 'w') as f:
            json.dump(consolidated_skips, f, indent=2, sort_keys=True)
        log(f"Saved consolidated skips to {SKIPPED_TICKERS_FILE}")
    elif dry_run:
        log(f"[DRY RUN] Would save consolidated skips to {SKIPPED_TICKERS_FILE}")

    return consolidated_skips


def validate_stock_data_db() -> tuple[bool, dict]:
    """
    Validate that StockDataDB.csv contains all data from individual CSV files.

    Returns:
        tuple: (is_valid, stats_dict)
    """
    log("Validating StockDataDB.csv against individual CSV files...")

    stats = {
        'db_records': 0,
        'db_tickers': 0,
        'csv_files': 0,
        'csv_records': 0,
        'missing_in_db': [],
        'extra_in_db': []
    }

    if not STOCK_DATA_DB.exists():
        log(f"StockDataDB.csv not found at {STOCK_DATA_DB}", "ERROR")
        return False, stats

    # Load master DB
    try:
        master_df = pd.read_csv(STOCK_DATA_DB)
        master_df['Date'] = pd.to_datetime(master_df['Date'], errors='coerce').dt.date
        stats['db_records'] = len(master_df)
        stats['db_tickers'] = master_df['Stock'].nunique()

        # Create set of (ticker, date) in DB
        db_records = set(zip(master_df['Stock'], master_df['Date']))
        log(f"StockDataDB.csv: {stats['db_records']} records, {stats['db_tickers']} unique tickers")

    except Exception as e:
        log(f"Error reading StockDataDB.csv: {e}", "ERROR")
        return False, stats

    # Scan individual CSV files
    csv_records = set()
    if FINDATA_DIR.exists():
        for ticker_dir in FINDATA_DIR.iterdir():
            if not ticker_dir.is_dir():
                continue

            ticker = ticker_dir.name
            for csv_file in ticker_dir.glob('StockData_*.csv'):
                stats['csv_files'] += 1
                try:
                    # Extract date from filename
                    date_str = csv_file.stem.split('_')[-1]
                    file_date = datetime.strptime(date_str, '%Y-%m-%d').date()
                    csv_records.add((ticker, file_date))
                except ValueError:
                    log(f"  Could not parse date from {csv_file.name}", "WARNING")

    stats['csv_records'] = len(csv_records)
    log(f"Individual CSVs: {stats['csv_files']} files, {stats['csv_records']} unique (ticker, date) pairs")

    # Compare
    missing_in_db = csv_records - db_records
    extra_in_db = db_records - csv_records

    if missing_in_db:
        stats['missing_in_db'] = list(missing_in_db)[:10]  # First 10
        log(f"MISMATCH: {len(missing_in_db)} records in CSVs but not in DB", "WARNING")
        for ticker, date in list(missing_in_db)[:5]:
            log(f"  Example: {ticker} on {date}")

    if extra_in_db:
        stats['extra_in_db'] = list(extra_in_db)[:10]
        log(f"Note: {len(extra_in_db)} records in DB but not in individual CSVs (this is OK)")

    is_valid = len(missing_in_db) == 0
    if is_valid:
        log("✓ Validation passed: StockDataDB.csv contains all data from individual CSVs")
    else:
        log("✗ Validation failed: Some CSV data is missing from StockDataDB.csv", "ERROR")

    return is_valid, stats


def create_backup(dry_run: bool = False) -> Optional[Path]:
    """Create backup of findata and findb before migration."""
    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    backup_path = BACKUP_DIR / f'pre_migration_{timestamp}'

    if dry_run:
        log(f"[DRY RUN] Would create backup at {backup_path}")
        return backup_path

    log(f"Creating backup at {backup_path}...")
    backup_path.mkdir(parents=True, exist_ok=True)

    # Backup findb (small, always backup)
    if FINDB_DIR.exists():
        shutil.copytree(FINDB_DIR, backup_path / 'findb')
        log(f"  Backed up findb/ ({sum(f.stat().st_size for f in FINDB_DIR.rglob('*') if f.is_file()) / 1024 / 1024:.1f} MB)")

    # Backup skip.json files only (not the large CSVs)
    skip_backup_dir = backup_path / 'skip_files'
    skip_backup_dir.mkdir(exist_ok=True)
    if FINDATA_DIR.exists():
        skip_count = 0
        for ticker_dir in FINDATA_DIR.iterdir():
            if ticker_dir.is_dir():
                skip_file = ticker_dir / 'skip.json'
                if skip_file.exists():
                    (skip_backup_dir / ticker_dir.name).mkdir(exist_ok=True)
                    shutil.copy2(skip_file, skip_backup_dir / ticker_dir.name / 'skip.json')
                    skip_count += 1
        log(f"  Backed up {skip_count} skip.json files")

    log(f"✓ Backup created at {backup_path}")
    return backup_path


def remove_individual_csvs(dry_run: bool = False) -> dict:
    """
    Remove individual CSV files from findata/ after validation.
    Keeps skip.json files until they are consolidated.

    Returns:
        dict: Stats about removed files
    """
    stats = {
        'files_removed': 0,
        'bytes_freed': 0,
        'tickers_cleaned': 0
    }

    if not FINDATA_DIR.exists():
        log("findata directory not found, nothing to remove")
        return stats

    log("Removing individual CSV files from findata/...")

    for ticker_dir in FINDATA_DIR.iterdir():
        if not ticker_dir.is_dir():
            continue

        ticker_cleaned = False
        for csv_file in ticker_dir.glob('StockData_*.csv'):
            if dry_run:
                stats['files_removed'] += 1
                stats['bytes_freed'] += csv_file.stat().st_size
            else:
                file_size = csv_file.stat().st_size
                csv_file.unlink()
                stats['files_removed'] += 1
                stats['bytes_freed'] += file_size
            ticker_cleaned = True

        if ticker_cleaned:
            stats['tickers_cleaned'] += 1

    mb_freed = stats['bytes_freed'] / 1024 / 1024
    if dry_run:
        log(f"[DRY RUN] Would remove {stats['files_removed']} CSV files ({mb_freed:.1f} MB)")
    else:
        log(f"Removed {stats['files_removed']} CSV files, freed {mb_freed:.1f} MB")

    return stats


def remove_skip_json_files(dry_run: bool = False) -> int:
    """
    Remove individual skip.json files after consolidation.

    Returns:
        int: Number of files removed
    """
    if not FINDATA_DIR.exists():
        return 0

    count = 0
    for ticker_dir in FINDATA_DIR.iterdir():
        if ticker_dir.is_dir():
            skip_file = ticker_dir / 'skip.json'
            if skip_file.exists():
                if not dry_run:
                    skip_file.unlink()
                count += 1

    if dry_run:
        log(f"[DRY RUN] Would remove {count} skip.json files")
    else:
        log(f"Removed {count} skip.json files")

    return count


def cleanup_empty_ticker_dirs(dry_run: bool = False) -> int:
    """Remove empty ticker directories from findata/."""
    if not FINDATA_DIR.exists():
        return 0

    count = 0
    for ticker_dir in FINDATA_DIR.iterdir():
        if ticker_dir.is_dir():
            # Check if directory is empty or only has skip.json
            contents = list(ticker_dir.iterdir())
            if not contents:
                if not dry_run:
                    ticker_dir.rmdir()
                count += 1

    if count > 0:
        if dry_run:
            log(f"[DRY RUN] Would remove {count} empty ticker directories")
        else:
            log(f"Removed {count} empty ticker directories")

    return count


def calculate_storage_savings() -> dict:
    """Calculate current storage usage and potential savings."""
    stats = {
        'findata_size_mb': 0,
        'findb_size_mb': 0,
        'csv_files_count': 0,
        'skip_files_count': 0
    }

    if FINDATA_DIR.exists():
        for f in FINDATA_DIR.rglob('*'):
            if f.is_file():
                size = f.stat().st_size
                stats['findata_size_mb'] += size
                if f.suffix == '.csv':
                    stats['csv_files_count'] += 1
                elif f.name == 'skip.json':
                    stats['skip_files_count'] += 1

    if FINDB_DIR.exists():
        for f in FINDB_DIR.rglob('*'):
            if f.is_file():
                stats['findb_size_mb'] += f.stat().st_size

    stats['findata_size_mb'] /= 1024 * 1024
    stats['findb_size_mb'] /= 1024 * 1024

    return stats


def main():
    parser = argparse.ArgumentParser(
        description='Migrate findata storage to consolidated format for GCP deployment'
    )
    parser.add_argument('--dry-run', action='store_true',
                        help='Show what would be done without making changes')
    parser.add_argument('--no-backup', action='store_true',
                        help='Skip creating backup (not recommended)')
    parser.add_argument('--remove-csvs', action='store_true',
                        help='Remove individual CSV files after validation')
    parser.add_argument('--force', action='store_true',
                        help='Force removal even if validation fails')

    args = parser.parse_args()

    log("=" * 60)
    log("PortfolioESG Storage Migration Tool")
    log("=" * 60)

    if args.dry_run:
        log("Running in DRY RUN mode - no changes will be made")

    # Show current storage usage
    log("\n--- Current Storage Usage ---")
    storage = calculate_storage_savings()
    log(f"findata/: {storage['findata_size_mb']:.1f} MB ({storage['csv_files_count']} CSVs, {storage['skip_files_count']} skip.json)")
    log(f"findb/:   {storage['findb_size_mb']:.1f} MB")
    log(f"Potential savings: ~{storage['findata_size_mb'] - 1:.1f} MB (keeping ~1MB for skip data)")

    # Step 1: Create backup
    if not args.no_backup:
        log("\n--- Step 1: Creating Backup ---")
        backup_path = create_backup(args.dry_run)
    else:
        log("\n--- Step 1: Skipping Backup (--no-backup) ---")

    # Step 2: Consolidate skip files
    log("\n--- Step 2: Consolidating skip.json Files ---")
    consolidated_skips = consolidate_skip_files(args.dry_run)

    # Step 3: Validate StockDataDB.csv
    log("\n--- Step 3: Validating StockDataDB.csv ---")
    is_valid, validation_stats = validate_stock_data_db()

    # Step 4: Remove CSVs if requested and valid
    if args.remove_csvs:
        log("\n--- Step 4: Removing Individual CSV Files ---")
        if is_valid or args.force:
            if not is_valid:
                log("WARNING: Proceeding with --force despite validation failure", "WARNING")

            csv_stats = remove_individual_csvs(args.dry_run)

            # Also remove the now-redundant skip.json files
            if consolidated_skips:
                remove_skip_json_files(args.dry_run)

            # Cleanup empty directories
            cleanup_empty_ticker_dirs(args.dry_run)
        else:
            log("Skipping CSV removal due to validation failure. Use --force to override.", "ERROR")
    else:
        log("\n--- Step 4: Skipping CSV Removal (use --remove-csvs to enable) ---")

    # Summary
    log("\n" + "=" * 60)
    log("Migration Summary")
    log("=" * 60)
    log(f"Skip files consolidated: {len(consolidated_skips)}")
    log(f"DB validation: {'PASSED' if is_valid else 'FAILED'}")
    if args.remove_csvs and (is_valid or args.force):
        log(f"Storage freed: {storage['findata_size_mb']:.1f} MB")

    if args.dry_run:
        log("\n[DRY RUN] No changes were made. Run without --dry-run to apply changes.")

    log("\nDone!")
    return 0 if is_valid else 1


if __name__ == '__main__':
    sys.exit(main())


