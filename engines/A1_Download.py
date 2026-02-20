#!/usr/bin/env python

# --- Script Version ---
DOWNLOAD_PY_VERSION = "2.5.1"  # Fixed Pylance warnings, improved type safety

# ----------------------------------------------------------- #
#                           Libraries                         #
# ----------------------------------------------------------- #
import pandas as pd
import numpy as np
from datetime import datetime, timedelta, date
import logging, time, json, os, shutil
from typing import Any, Tuple, Optional, Dict
import yfinance as yfin
from shared_tools.shared_utils import (
    setup_logger,
    load_parameters_from_file,
    get_previous_business_day,
    get_sao_paulo_holidays,
    copy_file_to_web_accessible_location,
)
from shared_tools.shared_utils import write_json_atomic
from shared_tools.path_utils import resolve_paths_in_params

# Suppress yfinance's own logs to clean up the console output.
logging.getLogger('yfinance').setLevel(logging.ERROR)

# ----------------------------------------------------------- #
#                        Helper Functions                     #
# ----------------------------------------------------------- #

# Global cache for consolidated skips to avoid repeated file reads
_consolidated_skips_cache: Optional[Dict[str, list]] = None

# Global cache for existing dates per ticker from StockDataDB (direct mode)
_existing_dates_cache: Optional[Dict[str, set]] = None


def get_consolidated_skip_file(params: dict[str, Any]) -> str:
    """Return the path to the consolidated skipped_tickers.json file."""
    findb_dir = params.get('FINDB_DIR') or os.path.dirname(params.get('FINDB_FILE', ''))
    if not findb_dir:
        # Fallback to data/findb
        script_dir = os.path.dirname(os.path.abspath(__file__))
        findb_dir = os.path.join(script_dir, '..', 'data', 'findb')
    return os.path.join(findb_dir, 'skipped_tickers.json')


def get_ticker_skip_file(ticker: str, params: dict[str, Any]) -> str:
    """Return the path to the legacy skip file for a given ticker.

    Skip files were stored alongside the downloaded data in the findata directory.
    Now we prefer the consolidated file, but this is kept for backward compatibility.
    """
    findata_dir = params.get('findata_directory') or params.get('FINDATA_PATH')
    if not findata_dir:
        raise ValueError("findata_directory or FINDATA_PATH must be configured in parameters")
    return os.path.join(findata_dir, ticker, 'skip.json')


def load_all_skipped_tickers(params: dict[str, Any], logger: logging.Logger) -> dict[str, list]:
    """Load all skipped tickers from the consolidated file.

    Falls back to scanning individual skip.json files if consolidated file doesn't exist.
    Results are cached for performance.
    """
    global _consolidated_skips_cache

    if _consolidated_skips_cache is not None:
        return _consolidated_skips_cache

    consolidated_file = get_consolidated_skip_file(params)

    # Try consolidated file first
    if os.path.exists(consolidated_file):
        try:
            with open(consolidated_file, 'r') as skip_f:
                _consolidated_skips_cache = json.load(skip_f)
                logger.info(f"Loaded consolidated skips for {len(_consolidated_skips_cache)} tickers")
                return _consolidated_skips_cache
        except (json.JSONDecodeError, OSError) as skip_err:
            logger.warning(f"Could not read consolidated skip file: {skip_err}. Falling back to individual files.")

    # Fallback: scan individual skip.json files (legacy support)
    _consolidated_skips_cache = {}
    findata_dir = params.get('findata_directory') or params.get('FINDATA_PATH')

    if findata_dir and os.path.exists(findata_dir):
        for ticker_dir in os.listdir(findata_dir):
            ticker_path = os.path.join(findata_dir, ticker_dir)
            if os.path.isdir(ticker_path):
                skip_file = os.path.join(ticker_path, 'skip.json')
                if os.path.exists(skip_file):
                    try:
                        with open(skip_file, 'r') as ind_f:
                            _consolidated_skips_cache[ticker_dir] = json.load(ind_f)
                    except (json.JSONDecodeError, OSError):
                        pass

    if _consolidated_skips_cache:
        logger.info(f"Loaded skips for {len(_consolidated_skips_cache)} tickers from individual files")

    return _consolidated_skips_cache


def load_ticker_skip_data(ticker: str, params: dict[str, Any], logger: logging.Logger) -> list:
    """Load skip data for a ticker.

    First checks the consolidated file, then falls back to individual skip.json.
    """
    all_skips = load_all_skipped_tickers(params, logger)

    if ticker in all_skips:
        return all_skips[ticker]

    # Fallback to individual file (for backward compatibility during migration)
    try:
        skip_file = get_ticker_skip_file(ticker, params)
        if os.path.exists(skip_file):
            with open(skip_file, 'r') as ind_f:
                return json.load(ind_f)
    except (json.JSONDecodeError, OSError, ValueError):
        pass

    return []


def save_ticker_skip_data(ticker: str, skip_data: list, params: dict[str, Any], logger: logging.Logger) -> None:
    """Save skip data for a ticker to both consolidated and individual files.

    Updates the in-memory cache and saves to the consolidated file.
    Also saves to individual file for backward compatibility during migration.
    """
    global _consolidated_skips_cache

    # Update cache
    if _consolidated_skips_cache is None:
        _consolidated_skips_cache = {}
    _consolidated_skips_cache[ticker] = skip_data

    # Save to consolidated file
    consolidated_file = get_consolidated_skip_file(params)
    try:
        os.makedirs(os.path.dirname(consolidated_file), exist_ok=True)
        with open(consolidated_file, 'w') as out_f:
            json.dump(_consolidated_skips_cache, out_f, indent=2, sort_keys=True)
        logger.info(f"Updated consolidated skip file with {ticker}")
    except OSError as save_err:
        logger.warning(f"Could not save consolidated skip file: {save_err}")



def load_existing_dates_cache(params: dict[str, Any], logger: logging.Logger) -> Dict[str, set]:
    """Load all existing dates from StockDataDB.csv into cache (called once at start)."""
    global _existing_dates_cache

    if _existing_dates_cache is not None:
        return _existing_dates_cache

    _existing_dates_cache = {}
    findb_file = params.get("FINDB_FILE")

    if not findb_file or not os.path.exists(findb_file):
        logger.info("No existing StockDataDB.csv found. Starting fresh.")
        return _existing_dates_cache

    try:
        logger.info(f"Loading existing dates from {findb_file}...")
        df = pd.read_csv(findb_file, usecols=['Stock', 'Date'])
        df['Date'] = pd.to_datetime(df['Date'], errors='coerce').dt.date
        df.dropna(subset=['Date'], inplace=True)

        for ticker, group in df.groupby('Stock'):
            _existing_dates_cache[ticker] = set(group['Date'].tolist())

        total_records = len(df)
        total_tickers = len(_existing_dates_cache)
        logger.info(f"Loaded {total_records} existing records for {total_tickers} tickers from DB.")

    except Exception as e:
        logger.warning(f"Could not load existing dates cache: {e}. Starting fresh.")
        _existing_dates_cache = {}

    return _existing_dates_cache


def get_existing_dates_from_db(ticker: str, params: dict[str, Any], logger: logging.Logger) -> set:
    """Get existing dates for a ticker from cache (must call load_existing_dates_cache first)."""
    global _existing_dates_cache

    if _existing_dates_cache is None:
        load_existing_dates_cache(params, logger)

    return _existing_dates_cache.get(ticker, set())


def get_missing_dates(
        ticker: str,
        start_date: datetime,
        end_date: datetime,
        params: dict[str, Any],
        all_holidays: dict,
        logger: logging.Logger
) -> list[datetime]:
    skip_data = load_ticker_skip_data(ticker, params, logger)
    if skip_data == ["ALL"]:
        logger.info(f"Ticker {ticker} is marked for permanent skip. No missing dates will be calculated.")
        return []

    debug_mode = params.get("debug_mode", False)
    storage_mode = params.get("storage_mode", "legacy")

    if debug_mode:
        logger.debug(f"Getting missing dates for {ticker} from {start_date.date()} to {end_date.date()}.")

    try:
        business_days = pd.bdate_range(start=start_date, end=end_date, freq='C', holidays=list(all_holidays.keys()))
        potential_dates = {dt.date() for dt in business_days}
        if debug_mode:
            logger.debug(f"Generated {len(potential_dates)} potential business days for the period.")
    except Exception as e:
        logger.error(f"Failed to generate business day range for {ticker}: {e}")
        return []

    # Get existing dates based on storage mode
    existing_dates = set()
    if storage_mode == "direct":
        # In direct mode, check the consolidated StockDataDB.csv
        existing_dates = get_existing_dates_from_db(ticker, params, logger)
    else:
        # Legacy mode: check individual CSV files in findata directory
        findata_dir = params.get("findata_directory")
        if findata_dir:
            ticker_folder = os.path.join(findata_dir, ticker)
            if os.path.exists(ticker_folder):
                for filename in os.listdir(ticker_folder):
                    if filename.startswith(f"StockData_{ticker}_") and filename.endswith(".csv"):
                        try:
                            date_str = filename.split('_')[-1].replace('.csv', '')
                            existing_dates.add(datetime.strptime(date_str, "%Y-%m-%d").date())
                        except (ValueError, IndexError):
                            logger.warning(f"Could not parse date from filename: {filename}. Skipping.")

    if debug_mode:
        logger.debug(f"Found {len(existing_dates)} existing dates for {ticker}.")

    # Parse skipped dates (individual dates, not "ALL")
    skipped_dates = set()
    if skip_data and skip_data != ["ALL"]:
        for d_str in skip_data:
            try:
                skipped_dates.add(datetime.strptime(d_str, "%Y-%m-%d").date())
            except ValueError:
                pass

    if debug_mode and skipped_dates:
        logger.debug(f"Found {len(skipped_dates)} dates to explicitly skip for {ticker}.")

    missing_dates_set = potential_dates - existing_dates - skipped_dates

    if not missing_dates_set:
        if debug_mode:
            logger.debug(f"Ticker {ticker} is up-to-date. No missing dates found.")
        return []

    missing_datetimes = sorted([datetime.combine(d, datetime.min.time()) for d in missing_dates_set])

    logger.info(f"Identified {len(missing_datetimes)} missing dates for {ticker}.")
    if debug_mode:
        missing_dates_preview = [d.strftime('%Y-%m-%d') for d in missing_datetimes[:5]]
        logger.debug(f"Missing dates preview: {missing_dates_preview}")

    return missing_datetimes

def initialize_performance_data(script_version: str) -> dict[str, Any]:
    timer_keys = [
        "param_load_duration_s",
        "user_agent_setup_duration_s",
        "initial_db_load_duration_s",
        "findata_processing_duration_s",
        "new_data_download_loop_duration_s",
        "final_db_save_duration_s",
        "overall_script_duration_s"
    ]
    perf_data: dict[str, Any] = {
        "run_start_timestamp": datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
        "download_py_version": script_version,
        "total_tickers_processed": 0,
        "tickers_with_new_data_downloaded": 0,
        **{key: 0.0 for key in timer_keys}
    }
    return perf_data

def load_tickers_data(params: dict[str, Any], logger: logging.Logger) -> pd.DataFrame:
    tickers_file_path = params.get("TICKERS_FILE")
    if not tickers_file_path:
        logger.critical("'TICKERS_FILE' not found in parameters. Cannot load tickers.")
        return pd.DataFrame(columns=['Ticker', 'Name', 'Sector', 'Industry', 'BrokerName'])

    try:
        tickers_df = pd.read_csv(
            tickers_file_path,
            header=0,
            comment='#',
            skip_blank_lines=True,
            sep=','
        )
        for col in tickers_df.select_dtypes(['object']):
            tickers_df[col] = tickers_df[col].str.strip()
        # Ensure required columns exist
        for col in ['Ticker', 'Name', 'Sector', 'Industry']:
            if col not in tickers_df.columns:
                tickers_df[col] = None
        # Add BrokerName column if not present (for backward compatibility)
        if 'BrokerName' not in tickers_df.columns:
            tickers_df['BrokerName'] = None
        tickers_df.dropna(subset=['Ticker'], inplace=True)
        valid_tickers_df = tickers_df[~tickers_df['Sector'].str.contains('Error', na=False, case=False)].copy()
        num_loaded = len(tickers_df)
        num_valid = len(valid_tickers_df)
        num_filtered = num_loaded - num_valid
        logger.info(f"Successfully loaded {num_loaded} total entries from {tickers_file_path}.")
        if num_filtered > 0:
            logger.info(f"Filtered out {num_filtered} tickers marked with 'Error', leaving {num_valid} valid tickers.")
        return valid_tickers_df
    except FileNotFoundError:
        logger.critical(f"Tickers file not found at '{tickers_file_path}'.")
        return pd.DataFrame(columns=['Ticker', 'Name', 'Sector', 'Industry', 'BrokerName'])
    except Exception as e:
        logger.critical(f"An unexpected error occurred while reading tickers file '{tickers_file_path}': {e}")
        return pd.DataFrame(columns=['Ticker', 'Name', 'Sector', 'Industry', 'BrokerName'])

def save_ticker_data_to_csv(ticker: str, data: pd.DataFrame, params: dict, logger: logging.Logger) -> int:
    """Save ticker data - now only used in legacy mode.

    In direct mode (storage_mode='direct'), this function is not called.
    Data is accumulated in memory and saved directly to StockDataDB.csv.

    This function is kept for backward compatibility with legacy mode.
    """
    storage_mode = params.get("storage_mode", "legacy")
    if storage_mode == "direct":
        # In direct mode, we don't save individual CSVs
        return len(data) if not data.empty else 0

    # Legacy mode: save individual CSV files (not recommended)
    findata_dir = params.get("findata_directory")
    if not findata_dir or data.empty:
        return 0
    
    data_to_save = data.copy()
    if 'Date' not in data_to_save.columns:
        logger.error(f"DataFrame for {ticker} is missing the required 'Date' column.")
        return 0
    
    data_to_save['Date'] = pd.to_datetime(data_to_save['Date'], errors='coerce')
    data_to_save.dropna(subset=['Date'], inplace=True)

    ticker_folder = os.path.join(findata_dir, ticker)
    os.makedirs(ticker_folder, exist_ok=True)

    files_saved_count = 0
    for date_obj, group in data_to_save.groupby(data_to_save['Date'].dt.date):
        if not isinstance(date_obj, date):
            continue
        file_name = f"StockData_{ticker}_{date_obj.strftime('%Y-%m-%d')}.csv"
        file_path = os.path.join(ticker_folder, file_name)
        try:
            group.to_csv(file_path, index=False, date_format='%Y-%m-%d')
            files_saved_count += 1
        except OSError as save_err:
            logger.warning(f"Error saving data for {ticker} on {date_obj}: {save_err}")

    if files_saved_count > 0:
        logger.info(f"Successfully saved {files_saved_count} daily data files for {ticker}.")

    return files_saved_count

def fetch_historical_data_for_dates(
        ticker: str,
        missing_dates: list[datetime],
        params: dict,
        logger: logging.Logger
) -> pd.DataFrame:
    if not missing_dates:
        return pd.DataFrame()
    start_date = min(missing_dates)
    end_date = max(missing_dates) + timedelta(days=1)
    debug_mode = params.get("debug_mode", False)
    if debug_mode:
        logger.debug(
            f"Fetching yfinance data for {ticker} from {start_date.strftime('%Y-%m-%d')} to {end_date.strftime('%Y-%m-%d')}")
    try:
        stock = yfin.Ticker(ticker)
        data = stock.history(
            start=start_date.strftime('%Y-%m-%d'),
            end=end_date.strftime('%Y-%m-%d'),
            auto_adjust=False,
            back_adjust=False
        )
        if data.empty:
            logger.warning(f"yfinance returned no data for {ticker} in the requested range.")
            return pd.DataFrame()
        data.reset_index(inplace=True)
        data.rename(columns={
            'Date': 'Date', 'Open': 'Open', 'High': 'High', 'Low': 'Low',
            'Close': 'Close', 'Volume': 'Volume'
        }, inplace=True)
        data['Date'] = pd.to_datetime(data['Date']).dt.tz_localize(None)
        data['Stock'] = ticker
        required_cols = ['Date', 'Open', 'High', 'Low', 'Close', 'Volume', 'Stock']
        # Ensure all required columns exist, fill with NaN if not
        for col in required_cols:
            if col not in data.columns:
                data[col] = np.nan
        return data[required_cols]
    except Exception as e:
        logger.error(f"An error occurred during yfinance download for {ticker}: {e}")
        return pd.DataFrame()

def download_and_process_data(
        tickers_df: pd.DataFrame,
        params: dict[str, Any],
        perf_data: dict,
        logger: logging.Logger
) -> Tuple[dict, Any, str, int, pd.DataFrame]:
    """Download and process data for all tickers.

    Returns:
        Tuple of (perf_data, skip_data, date_range_str, total_rows_downloaded, accumulated_data_df)
        The accumulated_data_df contains all new data downloaded in this run (for direct DB mode).
    """
    logger.info("Starting main data download and processing pipeline.")
    loop_start_time = time.time()

    # Load skipped tickers and filter out permanently skipped ones BEFORE processing
    all_skips = load_all_skipped_tickers(params, logger)
    permanently_skipped = [ticker for ticker, skip_data in all_skips.items() if skip_data == ["ALL"]]

    # Pre-load existing dates cache for direct mode (loads DB only once)
    storage_mode = params.get("storage_mode", "legacy")
    if storage_mode == "direct":
        load_existing_dates_cache(params, logger)

    all_tickers = tickers_df['Ticker'].tolist()
    tickers_to_process = [t for t in all_tickers if t not in permanently_skipped]
    skipped_count = len(all_tickers) - len(tickers_to_process)

    if skipped_count > 0:
        logger.info(f"Skipping {skipped_count} permanently invalid/delisted tickers")
        if skipped_count <= 10:
            logger.info(f"Skipped tickers: {permanently_skipped}")

    total_tickers = len(tickers_to_process)
    all_financials_data = []
    all_new_price_data = []  # Accumulate all new price data for direct DB mode

    end_date = datetime.strptime(get_previous_business_day(params, logger), '%Y-%m-%d')
    history_years = params.get("history_years", 10)
    start_date = end_date - timedelta(days=365 * history_years)
    date_range_str = f"{start_date.strftime('%Y-%m-%d')} to {end_date.strftime('%Y-%m-%d')}"
    all_holidays = {}
    for year in range(start_date.year, end_date.year + 1):
        all_holidays.update(get_sao_paulo_holidays(year, params, logger))
    logger.info(f"Generated holiday calendar from {start_date.year} to {end_date.year}.")
    logger.info(f"--- Starting Data Download for {total_tickers} tickers ---")

    storage_mode = params.get("storage_mode", "legacy")
    if storage_mode == "direct":
        logger.info("Using optimized direct-to-DB storage mode (no individual CSVs)")

    tickers_with_new_data = 0
    total_rows_downloaded = 0
    debug_mode = params.get("debug_mode", False)

    for i, ticker in enumerate(tickers_to_process):
        # Initialize flag for this ticker
        no_metrics_ticker = False

        web_payload = {
            "download_overall_status": "Running: Downloading Data",
            "ticker_download": {
                "current_ticker": ticker,
                "completed_tickers": i,
                "total_tickers": total_tickers,
                "progress": (i / total_tickers) * 100,
                "date_range": date_range_str,
                "rows": total_rows_downloaded
            }
        }
        if i == 0:
            web_payload["download_execution_start"] = perf_data.get("run_start_timestamp")
        logger.info(f"Processing {ticker} ({i + 1}/{total_tickers})", extra={'web_data': web_payload})
        # --- write progress JSON atomically (safe for frontend consumption) ---
        try:
            download_progress_file = params.get("DOWNLOAD_PROGRESS_JSON_FILE")
            if download_progress_file:
                # Normalize and ensure we pass a plain `str` to the writer
                download_progress_file_str = str(os.fspath(download_progress_file))
                write_json_atomic(download_progress_file_str, web_payload)
                # also write into web-accessible data folder if configured
                web_folder = params.get('WEB_ACCESSIBLE_DATA_PATH')
                if web_folder:
                    try:
                        os.makedirs(web_folder, exist_ok=True)
                        web_path = os.path.join(web_folder, os.path.basename(download_progress_file))
                        write_json_atomic(web_path, web_payload)
                    except Exception:
                        pass
        except Exception as e:
            logger.debug(f"Could not write download progress JSON for {ticker}: {e}")

        try:
            stock = yfin.Ticker(ticker)
            info = stock.info
            if not info or 'symbol' not in info:
                logger.warning(f"Ticker {ticker} seems invalid or delisted. Marking to skip.")
                save_ticker_skip_data(ticker, ["ALL"], params, logger)
                continue
            
            forward_pe = info.get('forwardPE')
            forward_eps = info.get('forwardEps')
            dividend_yield = info.get('dividendYield')
            avg_volume = info.get('averageVolume')
            target_mean_price = info.get('targetMeanPrice')
            current_price = info.get('currentPrice') or info.get('regularMarketPrice')

            has_any_metrics = any([forward_pe, forward_eps, dividend_yield, avg_volume, target_mean_price, current_price])

            if has_any_metrics:
                all_financials_data.append({
                    'Stock': ticker,
                    'forwardPE': forward_pe,
                    'forwardEPS': forward_eps,
                    'dividendYield': dividend_yield,
                    'averageVolume': avg_volume,
                    'targetMeanPrice': target_mean_price,
                    'currentPrice': current_price,
                    'LastUpdated': datetime.now()
                })
            else:
                logger.warning(f"Could not retrieve any key financial metrics for {ticker}. Will check if has price data.")
                # Flag this ticker as potentially invalid - will be marked for skip if no price data either
                no_metrics_ticker = True

        except Exception as ex:
            logger.error(f"Could not fetch .info for {ticker}: {ex}. Skipping all data for this ticker.")
            continue


        missing_dates = get_missing_dates(
            ticker=ticker, start_date=start_date, end_date=end_date,
            params=params, all_holidays=all_holidays, logger=logger
        )
        if not missing_dates:
            logger.debug(f"Ticker {ticker} is up-to-date. No price download needed.")
            # Reset the flag for next ticker
            no_metrics_ticker = False
            continue

        new_data_df = fetch_historical_data_for_dates(ticker, missing_dates, params, logger)
        downloaded_dates = set(pd.to_datetime(new_data_df['Date']).dt.date) if not new_data_df.empty else set()
        failed_dates = [d.strftime('%Y-%m-%d') for d in missing_dates if d.date() not in downloaded_dates]

        if failed_dates:
            # Check if ALL dates failed AND ticker had no metrics - mark for permanent skip
            all_failed = len(failed_dates) == len(missing_dates)
            if all_failed and no_metrics_ticker:
                logger.warning(f"Ticker {ticker} has no metrics and no price data. Marking for permanent skip.")
                save_ticker_skip_data(ticker, ["ALL"], params, logger)
                no_metrics_ticker = False
                continue

            logger.warning(f"For {ticker}, {len(failed_dates)} dates failed to download. Adding to skip list.")
            current_skips = load_ticker_skip_data(ticker, params, logger)
            if current_skips == ["ALL"]:
                no_metrics_ticker = False
                continue  # Already permanently skipped
            current_skips.extend(failed_dates)
            current_skips = sorted(list(set(current_skips)))
            save_ticker_skip_data(ticker, current_skips, params, logger)

        # Reset the flag for next ticker
        no_metrics_ticker = False
        if new_data_df.empty:
            continue

        # Accumulate data for direct DB mode
        if storage_mode == "direct":
            all_new_price_data.append(new_data_df)
        else:
            save_ticker_data_to_csv(ticker, new_data_df, params, logger)

        tickers_with_new_data += 1
        total_rows_downloaded += len(new_data_df)
    logger.info("--- Finished Data Download Loop ---")
    final_web_payload = {
        "ticker_download": {
            "current_ticker": "Finished",
            "completed_tickers": total_tickers,
            "total_tickers": total_tickers,
            "progress": 100,
            "rows": total_rows_downloaded,
            "date_range": date_range_str
        }
    }
    # write final progress payload atomically
    try:
        download_progress_file = params.get("DOWNLOAD_PROGRESS_JSON_FILE")
        if download_progress_file:
            download_progress_file_str = str(os.fspath(download_progress_file))
            write_json_atomic(download_progress_file_str, final_web_payload)
            web_folder = params.get('WEB_ACCESSIBLE_DATA_PATH')
            if web_folder:
                try:
                    os.makedirs(web_folder, exist_ok=True)
                    web_path = os.path.join(web_folder, os.path.basename(download_progress_file))
                    write_json_atomic(web_path, final_web_payload)
                except Exception:
                    pass
    except Exception as e:
        logger.debug(f"Could not write final download progress JSON: {e}")

    logger.info(
        f"Pipeline finished. Downloaded {total_rows_downloaded} new price rows for {tickers_with_new_data} tickers.",
        extra={'web_data': final_web_payload}
    )
    # --- Save Financials Data ---
    financials_filepath = params.get("FINANCIALS_DB_FILE")
    if financials_filepath:
        logger.info(f"Consolidating financial data for stocks. Found {len(all_financials_data)} new records.")
        new_financials_df = pd.DataFrame(all_financials_data)
        try:
            existing_df = pd.DataFrame()
            if os.path.exists(financials_filepath):
                try:
                    existing_df = pd.read_csv(financials_filepath, parse_dates=['LastUpdated'])
                except (pd.errors.EmptyDataError, ValueError):
                    logger.warning(f"Financials DB file '{financials_filepath}' is empty or invalid. It will be overwritten.")
                    existing_df = pd.DataFrame()

            final_cols = ['Stock', 'forwardPE', 'forwardEPS', 'dividendYield', 'averageVolume', 'targetMeanPrice', 'currentPrice', 'LastUpdated']

            if new_financials_df.empty and existing_df.empty:
                 logger.info("No existing or new financial data. Creating an empty financials DB.")
                 final_df_to_save = pd.DataFrame(columns=final_cols)
            elif new_financials_df.empty:
                logger.info("No new financial data downloaded. Verifying existing database integrity.")
                final_df_to_save = existing_df
            else:
                combined_df = pd.concat([existing_df, new_financials_df], ignore_index=True)
                combined_df['LastUpdated'] = pd.to_datetime(combined_df['LastUpdated'], errors='coerce')
                combined_df.dropna(subset=['LastUpdated'], inplace=True)
                combined_df['FetchDate'] = combined_df['LastUpdated'].dt.date
                combined_df.sort_values(by='LastUpdated', inplace=True)
                combined_df.drop_duplicates(subset=['Stock', 'FetchDate'], keep='last', inplace=True)
                final_df_to_save = combined_df.drop(columns=['FetchDate'])

            for col in final_cols:
                if col not in final_df_to_save.columns:
                    final_df_to_save[col] = np.nan
            
            final_df_to_save = final_df_to_save[final_cols]

            os.makedirs(os.path.dirname(financials_filepath), exist_ok=True)
            final_df_to_save.to_csv(financials_filepath, index=False)
            logger.info(f"Successfully saved financial data to {financials_filepath}. Total records: {len(final_df_to_save)}.")

        except Exception as e:
            logger.critical(f"Failed to save financial data to '{financials_filepath}': {e}", exc_info=True)
    else:
        logger.warning("'FINANCIALS_DB_FILE' not found in parameters. Cannot save financials.")

    perf_data["new_data_download_loop_duration_s"] = time.time() - loop_start_time
    perf_data["tickers_with_new_data_downloaded"] = tickers_with_new_data
    perf_data["total_tickers_processed"] = total_tickers

    # Combine accumulated data for direct DB mode
    accumulated_df = pd.DataFrame()
    if all_new_price_data:
        accumulated_df = pd.concat(all_new_price_data, ignore_index=True)
        logger.info(f"Accumulated {len(accumulated_df)} rows for direct DB update")

    return perf_data, None, date_range_str, total_rows_downloaded, accumulated_df


def update_master_db_direct(
        params: dict[str, Any],
        logger: logging.Logger,
        new_data_df: pd.DataFrame,
        date_range: str,
        rows_downloaded: int
):
    """Update master database directly from accumulated data (optimized storage mode).

    This function bypasses individual CSV files and directly appends to StockDataDB.csv.
    """
    findb_file = params.get("FINDB_FILE")
    if not findb_file:
        logger.error("'FINDB_FILE' not in params. Cannot update master DB.")
        return

    if new_data_df.empty:
        logger.info("No new data to add to master database.")
        return

    web_payload = {
        "download_overall_status": "Running: Updating DB (Direct)",
        "ticker_download": {
            "current_ticker": "Updating...",
            "date_range": date_range,
            "rows": rows_downloaded
        }
    }
    logger.info("Updating master database directly (optimized mode)...", extra={'web_data': web_payload})
    db_start_time = time.time()

    try:
        # Load existing master DB
        master_df = pd.DataFrame()
        if os.path.exists(findb_file):
            try:
                master_df = pd.read_csv(findb_file)
                logger.info(f"Loaded {len(master_df)} existing records from master database.")
            except Exception as load_err:
                logger.critical(f"Failed to load master DB at '{findb_file}': {load_err}. Aborting update.")
                return
        else:
            logger.info("No existing master database found. Creating new one.")

        # Clean and validate new data
        new_data_df = new_data_df.copy()
        new_data_df['Date'] = pd.to_datetime(new_data_df['Date'], errors='coerce').dt.date
        new_data_df.dropna(subset=['Date'], inplace=True)

        # Combine with existing
        if not master_df.empty:
            master_df['Date'] = pd.to_datetime(master_df['Date'], errors='coerce').dt.date
            master_df.dropna(subset=['Date'], inplace=True)
            combined_df = pd.concat([master_df, new_data_df], ignore_index=True)
        else:
            combined_df = new_data_df

        # Remove duplicates (keep latest)
        combined_df.sort_values(by=['Stock', 'Date'], inplace=True)
        combined_df.drop_duplicates(subset=['Stock', 'Date'], keep='last', inplace=True)

        # Save
        os.makedirs(os.path.dirname(findb_file), exist_ok=True)
        combined_df.to_csv(findb_file, index=False, date_format='%Y-%m-%d')

        duration = time.time() - db_start_time
        logger.info(
            f"Successfully updated master database directly. "
            f"Added {len(new_data_df)} new records. "
            f"Total records now: {len(combined_df)}. Took {duration:.2f}s."
        )
    except Exception as db_err:
        logger.critical(f"Failed to update master database: {db_err}", exc_info=True)


def update_master_db(
        params: dict[str, Any],
        logger: logging.Logger,
        date_range: str,
        rows_downloaded: int,
        accumulated_data: pd.DataFrame = None
):
    """Update master database with new data.

    In direct mode (default): uses accumulated data from memory.
    In legacy mode: scans individual CSV files (not recommended).
    """
    storage_mode = params.get("storage_mode", "legacy")

    # Direct mode: use accumulated data
    if storage_mode == "direct":
        if accumulated_data is not None and not accumulated_data.empty:
            return update_master_db_direct(params, logger, accumulated_data, date_range, rows_downloaded)
        else:
            logger.info("No new data accumulated. Master database unchanged.")
            return

    # Legacy mode: scan individual CSV files (minimal support for backward compatibility)
    findb_file = params.get("FINDB_FILE")
    findata_dir = params.get("findata_directory")
    if not findb_file or not findata_dir:
        logger.error("'FINDB_FILE' or 'findata_directory' not in params. Cannot update master DB.")
        return

    if not os.path.exists(findata_dir):
        logger.warning(f"Findata directory '{findata_dir}' does not exist. Nothing to sync.")
        return

    logger.info("Legacy mode: scanning individual CSV files...")
    legacy_start_time = time.time()

    # Load existing DB
    master_df = pd.DataFrame()
    if os.path.exists(findb_file):
        try:
            master_df = pd.read_csv(findb_file)
        except Exception as load_err:
            logger.critical(f"Failed to load master DB: {load_err}. Aborting.")
            return

    # Scan for new files
    new_data_frames = []
    for ticker_folder in os.listdir(findata_dir):
        ticker_path = os.path.join(findata_dir, ticker_folder)
        if os.path.isdir(ticker_path):
            for filename in os.listdir(ticker_path):
                if filename.endswith(".csv"):
                    try:
                        df = pd.read_csv(os.path.join(ticker_path, filename))
                        new_data_frames.append(df)
                    except Exception:
                        pass

    if not new_data_frames:
        logger.info("No new files found to add.")
        return

    # Combine and dedupe
    new_data_df = pd.concat(new_data_frames, ignore_index=True)
    combined_df = pd.concat([master_df, new_data_df], ignore_index=True)
    combined_df['Date'] = pd.to_datetime(combined_df['Date'], errors='coerce').dt.date
    combined_df.dropna(subset=['Date'], inplace=True)
    combined_df.sort_values(by=['Stock', 'Date'], inplace=True)
    combined_df.drop_duplicates(subset=['Stock', 'Date'], keep='last', inplace=True)

    os.makedirs(os.path.dirname(findb_file), exist_ok=True)
    combined_df.to_csv(findb_file, index=False, date_format='%Y-%m-%d')

    legacy_duration = time.time() - legacy_start_time
    logger.info(f"Legacy sync complete. Added {len(new_data_df)} records in {legacy_duration:.2f}s.")

def log_performance_data(perf_data: dict[str, Any], params: dict[str, Any], logger: logging.Logger) -> None:
    """Log performance data to CSV file."""
    log_path = params.get("DOWNLOAD_PERFORMANCE_FILE")
    if not log_path:
        logger.warning("'DOWNLOAD_PERFORMANCE_FILE' not found in parameters. Skipping performance logging.")
        return
    try:
        df = pd.DataFrame([perf_data])
        log_dir = os.path.dirname(log_path)
        if log_dir:
            os.makedirs(log_dir, exist_ok=True)
        file_exists = os.path.isfile(log_path)
        df.to_csv(log_path, mode='a', header=not file_exists, index=False)
        logger.info(f"Successfully logged performance data to: {log_path}")
    except OSError as perf_err:
        logger.error(f"Failed to log performance data to '{log_path}': {perf_err}")



# ----------------------------------------------------------- #
#                     The application                         #
# ----------------------------------------------------------- #

def main():
    overall_start_time = time.time()
    script_dir = os.path.dirname(os.path.abspath(__file__))
    expected_params = {
        "debug_mode": bool, "history_years": int, "dynamic_user_agents_enabled": bool,
        "storage_mode": str,
        "FALLBACK_USER_AGENTS": str, "USER_AGENT_API_URL": str, "SPECIAL_MARKET_CLOSURES": str,
        "PIPELINE_PROGRESS_JSON_FILE": str,
        "DOWNLOAD_PROGRESS_JSON_FILE": str,
        "WEB_ACCESSIBLE_DATA_PATH": str, "FINDATA_PATH": str,
        "FINDB_FILE": str, "FINANCIALS_DB_FILE": str, "BENCHMARKS_DB_FILE": str, "TICKERS_FILE": str,
        "YFINANCE_SKIP_FILE": str, "DOWNLOAD_LOG_FILE": str, "DOWNLOAD_PERFORMANCE_FILE": str,
    }
    try:
        param_paths_file = os.path.join(script_dir, '..', 'parameters', 'paths.txt')
        param_downpar_file = os.path.join(script_dir, '..', 'parameters', 'downpar.txt')
        params = load_parameters_from_file(
            filepaths=[param_paths_file, param_downpar_file],
            expected_parameters=expected_params
        )
        # Normalize any paths so they point to this machine / repo if possible
        params = resolve_paths_in_params(params, script_dir, None)
        params['findata_directory'] = params.get('FINDATA_PATH')
    except (FileNotFoundError, ValueError, OSError) as param_err:
        temp_logger = setup_logger("StartupLogger", "startup_error.log", None)
        temp_logger.critical(f"Could not load parameters. Exiting. Error: {param_err}", exc_info=True)
        print(f"CRITICAL: Could not load parameters. Exiting. Error: {param_err}")
        import sys
        sys.exit(1)

    download_progress_file = params.get("DOWNLOAD_PROGRESS_JSON_FILE")
    initial_progress_data = {
        "download_overall_status": "Running: Initializing...",
        "download_execution_start": datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
        "download_execution_end": "N/A",
        "ticker_download": {
            "current_ticker": "N/A",
            "completed_tickers": 0,
            "total_tickers": 0,
            "progress": 0,
            "date_range": "N/A",
            "rows": 0
        }
    }
    try:
        if download_progress_file:
            # Use atomic writer to create initial progress JSON for the frontend
            download_progress_file_str = str(os.fspath(download_progress_file))
            write_json_atomic(download_progress_file_str, initial_progress_data)
            # Also write a copy into the web-accessible data folder if configured
            web_folder = params.get('WEB_ACCESSIBLE_DATA_PATH') if 'params' in locals() else None
            if web_folder:
                try:
                    os.makedirs(web_folder, exist_ok=True)
                    web_path = os.path.join(web_folder, os.path.basename(download_progress_file))
                    write_json_atomic(web_path, initial_progress_data)
                except OSError:
                    pass
    except OSError as prog_err:
        print(f"CRITICAL: Could not initialize progress file {download_progress_file}. Error: {prog_err}")

    logger = setup_logger(
        "DownloadRunner",
        log_file=params.get("DOWNLOAD_LOG_FILE"),
        web_log_file=download_progress_file,
        level=logging.DEBUG if params.get("debug_mode") else logging.INFO
    )

    # Re-run normalization now that logger exists so we can log details about resolution
    params = resolve_paths_in_params(params, script_dir, logger)
    perf_data = initialize_performance_data(DOWNLOAD_PY_VERSION)
    perf_data["param_load_duration_s"] = time.time() - overall_start_time

    logger.info("Starting A1_Download.py execution pipeline.")
    storage_mode = params.get("storage_mode", "legacy")
    logger.info(f"Storage mode: {storage_mode} ({'no individual CSVs' if storage_mode == 'direct' else 'individual CSVs + consolidation'})")

    try:
        logger.info("Loading primary tickers...")
        tickers_df = load_tickers_data(params, logger)
        if tickers_df.empty:
            logger.warning("Primary tickers file could not be loaded or is empty.")
            tickers_df = pd.DataFrame(columns=['Ticker', 'Name', 'Sector', 'Industry', 'BrokerName'])

        logger.info("Loading benchmark tickers...")
        benchmarks_df = pd.DataFrame(columns=['Ticker', 'Name', 'Sector', 'Industry', 'BrokerName'])
        benchmarks_file_path = os.path.join(script_dir, '..', 'parameters', 'benchmarks.txt')
        try:
            temp_benchmarks_df = pd.read_csv(
                benchmarks_file_path,
                header=0,
                comment='#',
                skip_blank_lines=True,
                sep=','
            )
            for col in temp_benchmarks_df.select_dtypes(['object']):
                temp_benchmarks_df[col] = temp_benchmarks_df[col].str.strip()
            for col in ['Ticker', 'Name', 'Sector', 'Industry', 'BrokerName']:
                if col not in temp_benchmarks_df.columns:
                    temp_benchmarks_df[col] = None
            benchmarks_df = temp_benchmarks_df[['Ticker', 'Name', 'Sector', 'Industry', 'BrokerName']]
            benchmarks_df.dropna(subset=['Ticker'], inplace=True)
            logger.info(f"Successfully loaded {len(benchmarks_df)} benchmark tickers.")
        except FileNotFoundError:
            logger.warning(f"Benchmark file not found at '{benchmarks_file_path}'. This may be expected.")
        except Exception as e:
            logger.error(f"An error occurred while reading the benchmark tickers file: {e}")

        benchmark_tickers_list = benchmarks_df['Ticker'].tolist()
        combined_tickers_df = pd.concat([tickers_df, benchmarks_df], ignore_index=True)
        combined_tickers_df.drop_duplicates(subset=['Ticker'], keep='last', inplace=True)
        logger.info(f"Total unique tickers to process (including benchmarks): {len(combined_tickers_df)}")

        if combined_tickers_df.empty:
            logger.critical("No valid tickers were loaded. Aborting pipeline.",
                            extra={'web_data': {"download_overall_status": "Failed: No Tickers"}})
            import sys
            sys.exit(1)

        perf_data, _, date_range_str, total_rows_downloaded, accumulated_data = download_and_process_data(
            tickers_df=combined_tickers_df,
            params=params,
            perf_data=perf_data,
            logger=logger
        )

        update_master_db(params, logger, date_range_str, total_rows_downloaded, accumulated_data)

        total_tickers = len(combined_tickers_df)
        final_web_payload = {
            "download_overall_status": "Completed",
            "download_execution_end": datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
            "ticker_download": {
                "current_ticker": "Finished",
                "completed_tickers": total_tickers,
                "total_tickers": total_tickers,
                "progress": 100,
                "date_range": date_range_str,
                "rows": total_rows_downloaded
            }
        }
        logger.info(
            f"Script finished successfully in {time.time() - overall_start_time:.2f} seconds.",
            extra={'web_data': final_web_payload}
        )

    except Exception as main_err:
        logger.critical(f"An unhandled exception occurred in the main pipeline: {main_err}", exc_info=True,
                        extra={'web_data': {"download_overall_status": "Failed: Unhandled Exception"}})
    finally:
        perf_data["overall_script_duration_s"] = time.time() - overall_start_time
        log_performance_data(perf_data, params, logger)
        copy_file_to_web_accessible_location("DOWNLOAD_PERFORMANCE_FILE", params, logger)
        logger.info("Execution complete.")

if __name__ == "__main__":
    import sys
    if len(sys.argv) > 1 and sys.argv[1].lower() == 'test':
        print("--- Running Test Suite for A1_Download.py Functions (using shared_utils) ---")
        test_start_time = time.time()
        EXPECTED_PARAMS = {
            "debug_mode": bool, "history_years": int, "dynamic_user_agents_enabled": bool,
            "FALLBACK_USER_AGENTS": str, "USER_AGENT_API_URL": str, "SPECIAL_MARKET_CLOSURES": str,
            "PIPELINE_JSON_FILE": str, "DOWNLOAD_JSON_FILE": str, "WEB_ACCESSIBLE_DATA_PATH": str, "FINDATA_PATH": str,
            "FINDB_FILE": str, "FINANCIALS_DB_FILE": str, "BENCHMARKS_DB_FILE": str, "TICKERS_FILE": str,
            "YFINANCE_SKIP_FILE": str, "DOWNLOAD_LOG_FILE": str, "DOWNLOAD_PERFORMANCE_FILE": str,
        }
        SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
        try:
            test_paths_file = os.path.join(SCRIPT_DIR, '..', 'parameters', 'paths.txt')
            test_downpar_file = os.path.join(SCRIPT_DIR, '..', 'parameters', 'downpar.txt')
            test_params = load_parameters_from_file(
                filepaths=[test_paths_file, test_downpar_file],
                expected_parameters=EXPECTED_PARAMS
            )
            print(f"Successfully loaded {len(test_params)} parameters for testing.")
        except (FileNotFoundError, ValueError, OSError) as load_err:
            print(f"CRITICAL: Failed to load parameters for test run. Error: {load_err}")
            sys.exit(1)
        test_logger = setup_logger(
            "DownloadTestRunner",
            log_file=os.path.join(SCRIPT_DIR, "download_test.log"),
            web_log_file=os.path.join(SCRIPT_DIR, "progress_test.json"),
            level=logging.DEBUG
        )
        test_logger.info("--- Running Full Pipeline Integration Test ---")
        temp_test_dir = os.path.join(SCRIPT_DIR, "temp_test_data")
        try:
            if os.path.exists(temp_test_dir): shutil.rmtree(temp_test_dir)
            os.makedirs(temp_test_dir, exist_ok=True)
            temp_findata_path = os.path.join(temp_test_dir, "findata")
            temp_findb_path = os.path.join(temp_test_dir, "findb")
            temp_web_path = os.path.join(temp_test_dir, "web")
            os.makedirs(temp_findata_path, exist_ok=True)
            os.makedirs(temp_findb_path, exist_ok=True)
            os.makedirs(temp_web_path, exist_ok=True)
            temp_tickers_file = os.path.join(temp_test_dir, "tickers_test.txt")
            with open(temp_tickers_file, 'w') as ticker_f:
                ticker_f.write("PETR4.SA,Energy,Oil & Gas\n")
                ticker_f.write("INVALID.SA,Test,Invalid\n")
            live_test_params = test_params.copy()
            live_test_params["TICKERS_FILE"] = temp_tickers_file
            live_test_params["findata_directory"] = temp_findata_path
            live_test_params["FINANCIALS_DB_FILE"] = os.path.join(temp_findb_path, "financials_db_test.csv")
            live_test_params["BENCHMARKS_DB_FILE"] = os.path.join(temp_findb_path, "benchmarks_db_test.csv")
            live_test_params["YFINANCE_SKIP_FILE"] = os.path.join(temp_findb_path, "yfinance_skip_test.json")
            live_test_params["DOWNLOAD_PERFORMANCE_FILE"] = os.path.join(temp_findb_path, "perf_test.csv")
            live_test_params["WEB_ACCESSIBLE_DATA_PATH"] = temp_web_path
            live_test_params["history_years"] = 1
            test_tickers_df = load_tickers_data(live_test_params, test_logger)
            initial_perf_data = initialize_performance_data(DOWNLOAD_PY_VERSION)
            final_perf_data, final_skip_data, _, _, _ = download_and_process_data(
                tickers_df=test_tickers_df, params=live_test_params,
                perf_data=initial_perf_data, logger=test_logger
            )
            log_performance_data(final_perf_data, live_test_params, test_logger)
            copy_file_to_web_accessible_location("DOWNLOAD_PERFORMANCE_FILE", live_test_params, test_logger)
            assert final_skip_data.get("INVALID.SA") == ["ALL"], "Invalid ticker was not skipped."
            test_logger.info("[PASS] Invalid ticker was correctly added to skip list.")
            assert os.path.exists(live_test_params["FINANCIALS_DB_FILE"]), "Financials DB was not created."
            test_logger.info("[PASS] Financials DB file was created.")
            assert os.path.exists(os.path.join(temp_findata_path, "PETR4.SA")), "Price data for PETR4.SA was not saved."
            test_logger.info("[PASS] Price data folder for PETR4.SA was created.")
            perf_file_path = live_test_params["DOWNLOAD_PERFORMANCE_FILE"]
            assert os.path.exists(perf_file_path), "Performance log was not created."
            test_logger.info("[PASS] Performance log file was created.")
            copied_perf_file = os.path.join(temp_web_path, os.path.basename(perf_file_path))
            assert os.path.exists(copied_perf_file), "Performance log was not copied to web directory."
            test_logger.info("[PASS] Performance log was copied to web directory.")
            test_logger.info("--- Full Pipeline Integration Test PASSED ---")
        except (AssertionError, FileNotFoundError, ValueError) as test_err:
            test_logger.error(f"--- Test FAILED: {test_err} ---", exc_info=True)
        except OSError as io_err:
            test_logger.error(f"--- An unexpected I/O error occurred during test: {io_err} ---", exc_info=True)
        finally:
            if os.path.exists(temp_test_dir):
                shutil.rmtree(temp_test_dir)
                test_logger.info(f"Cleaned up temporary test directory: {temp_test_dir}")
            print(f"--- Test Suite Finished in {time.time() - test_start_time:.2f} seconds ---")
    else:
        main()
