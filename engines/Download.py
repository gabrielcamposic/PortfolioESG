#!/usr/bin/env python

# --- Script Version ---
DOWNLOAD_PY_VERSION = "2.1.0"  # Added benchmark tickers to download process

# ----------------------------------------------------------- #
#                           Libraries                         #
# ----------------------------------------------------------- #
import pandas as pd
from datetime import datetime, timedelta, date
import logging, time, json, os, shutil
from typing import Any
import yfinance as yfin
from shared_tools.shared_utils import (
    setup_logger,
    load_parameters_from_file,
    get_previous_business_day,
    get_sao_paulo_holidays
)

# Suppress yfinance's own logs to clean up the console output.
logging.getLogger('yfinance').setLevel(logging.ERROR)

# ----------------------------------------------------------- #
#                        Helper Functions                     #
# ----------------------------------------------------------- #

def get_missing_dates(
        ticker: str,
        start_date: datetime,
        end_date: datetime,
        params: dict[str, Any],
        yfinance_skip_data: dict,
        all_holidays: dict,
        logger: logging.Logger
) -> list[datetime]:
    """
    Identifies missing daily data files for a stock ticker within a date range.

    This function determines which business days (excluding weekends and pre-computed
    holidays) do not have a corresponding data file in the findata directory. It also
    respects a list of dates to explicitly skip for a given ticker.

    Args:
        ticker: The stock ticker symbol (e.g., "AALR3.SA").
        start_date: The beginning of the date range to check.
        end_date: The end of the date range to check.
        params: Dictionary of loaded parameters, must contain 'findata_directory'.
        yfinance_skip_data: A dictionary mapping tickers to a list of date strings
                            ("YYYY-MM-DD") that should be ignored.
        all_holidays: A pre-computed dictionary of all market holidays.
        logger: The configured logger instance.

    Returns:
        A sorted list of datetime objects representing the missing dates.
    """
    if yfinance_skip_data.get(ticker) == ["ALL"]:
        logger.info(f"Ticker {ticker} is marked for permanent skip. No missing dates will be calculated.")
        return []

    debug_mode = params.get("debug_mode", False)
    findata_dir = params.get("findata_directory")

    if not findata_dir:
        logger.error("'findata_directory' not found in parameters. Cannot check for missing dates.")
        return []

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

    ticker_folder = os.path.join(findata_dir, ticker)
    existing_dates = set()
    if os.path.exists(ticker_folder):
        for filename in os.listdir(ticker_folder):
            if filename.startswith(f"StockData_{ticker}_") and filename.endswith(".csv"):
                try:
                    date_str = filename.split('_')[-1].replace('.csv', '')
                    existing_dates.add(datetime.strptime(date_str, "%Y-%m-%d").date())
                except (ValueError, IndexError):
                    logger.warning(f"Could not parse date from filename: {filename}. Skipping.")
    elif debug_mode:
        logger.debug(f"No data folder found for {ticker} at {ticker_folder}.")

    if debug_mode:
        logger.debug(f"Found {len(existing_dates)} existing data files for {ticker}.")

    skipped_dates_str = yfinance_skip_data.get(ticker, [])
    skipped_dates = {datetime.strptime(d_str, "%Y-%m-%d").date() for d_str in skipped_dates_str}
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
    """
    Creates and initializes a dictionary to track script performance metrics.
    """
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
    """
    Loads tickers, names, sectors, and industries from the configured tickers file.
    """
    tickers_file_path = params.get("TICKERS_FILE")
    if not tickers_file_path:
        logger.critical("'TICKERS_FILE' not found in parameters. Cannot load tickers.")
        return pd.DataFrame(columns=['Ticker', 'Name', 'Sector', 'Industry'])

    try:
        tickers_df = pd.read_csv(
            tickers_file_path,
            header=0,
            names=['Ticker', 'Name', 'Sector', 'Industry'],
            comment='#',
            skip_blank_lines=True,
            sep=','
        )
        for col in tickers_df.select_dtypes(['object']):
            tickers_df[col] = tickers_df[col].str.strip()
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
        return pd.DataFrame(columns=['Ticker', 'Name', 'Sector', 'Industry'])
    except Exception as e:
        logger.critical(f"An unexpected error occurred while reading tickers file '{tickers_file_path}': {e}")
        return pd.DataFrame(columns=['Ticker', 'Name', 'Sector', 'Industry'])

def save_ticker_data_to_csv(ticker: str, data: pd.DataFrame, params: dict, logger: logging.Logger) -> int:
    """
    Saves fetched historical data for a ticker into individual daily CSV files.
    """
    findata_dir = params.get("findata_directory")
    debug_mode = params.get("debug_mode", False)
    if not findata_dir:
        logger.error("'findata_directory' not found in parameters. Cannot save ticker data.")
        return 0
    if data.empty:
        if debug_mode:
            logger.debug(f"No data provided for ticker: {ticker}. Nothing to save.")
        return 0
    data_to_save = data.copy()
    if 'Date' not in data_to_save.columns:
        logger.error(f"DataFrame for {ticker} is missing the required 'Date' column. Cannot save.")
        return 0
    data_to_save['Date'] = pd.to_datetime(data_to_save['Date'], errors='coerce')
    data_to_save.dropna(subset=['Date'], inplace=True)
    ticker_folder = os.path.join(findata_dir, ticker)
    try:
        os.makedirs(ticker_folder, exist_ok=True)
    except OSError as e:
        logger.error(f"Failed to create directory '{ticker_folder}': {e}")
        return 0
    files_saved_count = 0
    for date_obj, group in data_to_save.groupby(data_to_save['Date'].dt.date):
        if not isinstance(date_obj, date):
            logger.warning(f"Skipping group with unexpected key type: {type(date_obj)}")
            continue
        file_name = f"StockData_{ticker}_{date_obj.strftime('%Y-%m-%d')}.csv"
        file_path = os.path.join(ticker_folder, file_name)
        try:
            group.to_csv(file_path, index=False)
            files_saved_count += 1
            if debug_mode:
                logger.debug(f"Saved data for {ticker} on {date_obj} to {file_path}")
        except Exception as e:
            logger.warning(f"Error saving data for {ticker} on {date_obj}: {e}")
    if files_saved_count > 0:
        logger.info(f"Successfully saved {files_saved_count} daily data files for {ticker}.")
    elif debug_mode:
        logger.debug(f"No new daily files were written for {ticker}.")
    return files_saved_count

def fetch_historical_data_for_dates(
        ticker: str,
        missing_dates: list[datetime],
        params: dict,
        logger: logging.Logger
) -> pd.DataFrame:
    """
    Fetches historical data from yfinance for a specific list of missing dates.
    """
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
        data = data[[col for col in required_cols if col in data.columns]]
        return data
    except Exception as e:
        logger.error(f"An error occurred during yfinance download for {ticker}: {e}")
        return pd.DataFrame()

def download_and_process_data(
        tickers_df: pd.DataFrame,
        params: dict[str, Any],
        perf_data: dict,
        logger: logging.Logger
) -> (dict, dict, str, int):
    """
    The main data processing pipeline.
    """
    logger.info("Starting main data download and processing pipeline.")
    loop_start_time = time.time()
    tickers_to_process = tickers_df['Ticker'].tolist()
    total_tickers = len(tickers_to_process)
    all_financials_data = []
    yfinance_skip_file = params.get("YFINANCE_SKIP_FILE")
    skip_data = {}
    if yfinance_skip_file and os.path.exists(yfinance_skip_file):
        try:
            with open(yfinance_skip_file, 'r') as f:
                skip_data = json.load(f)
            logger.info(f"Loaded yfinance skip data for {len(skip_data)} tickers.")
        except json.JSONDecodeError:
            logger.error(f"Could not decode JSON from {yfinance_skip_file}. Starting with empty skip data.")
    end_date = datetime.strptime(get_previous_business_day(params, logger), '%Y-%m-%d')
    history_years = params.get("history_years", 10)
    start_date = end_date - timedelta(days=365 * history_years)
    date_range_str = f"{start_date.strftime('%Y-%m-%d')} to {end_date.strftime('%Y-%m-%d')}"
    all_holidays = {}
    for year in range(start_date.year, end_date.year + 1):
        all_holidays.update(get_sao_paulo_holidays(year, params, logger))
    logger.info(f"Generated holiday calendar from {start_date.year} to {end_date.year}.")
    logger.info(f"--- Starting Data Download for {total_tickers} tickers ---")
    tickers_with_new_data = 0
    total_rows_downloaded = 0
    for i, ticker in enumerate(tickers_to_process):
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
        try:
            stock = yfin.Ticker(ticker)
            info = stock.info
            if not info or 'symbol' not in info:
                logger.warning(f"Ticker {ticker} seems invalid or delisted. Marking to skip.")
                skip_data[ticker] = ["ALL"]
                continue
            forward_pe = info.get('forwardPE')
            forward_eps = info.get('forwardEps')
            if isinstance(forward_pe, (int, float)) and forward_pe > 0 and isinstance(forward_eps, (int, float)):
                all_financials_data.append({
                    'Stock': ticker, 'forwardPE': forward_pe, 'forwardEps': forward_eps,
                    'LastUpdated': datetime.now().strftime('%Y-%m-%d %H:%M:%S')
                })
        except Exception as e:
            logger.error(f"Could not fetch .info for {ticker}: {e}. Skipping all data for this ticker.")
            continue
        missing_dates = get_missing_dates(
            ticker=ticker, start_date=start_date, end_date=end_date,
            params=params, yfinance_skip_data=skip_data,
            all_holidays=all_holidays, logger=logger
        )
        if not missing_dates:
            logger.debug(f"Ticker {ticker} is up-to-date. No price download needed.")
            continue
        new_data_df = fetch_historical_data_for_dates(ticker, missing_dates, params, logger)
        downloaded_dates = set(pd.to_datetime(new_data_df['Date']).dt.date) if not new_data_df.empty else set()
        failed_dates = [d.strftime('%Y-%m-%d') for d in missing_dates if d.date() not in downloaded_dates]
        if failed_dates:
            logger.warning(f"For {ticker}, {len(failed_dates)} dates failed to download. Adding to skip list.")
            current_skips = skip_data.get(ticker, [])
            current_skips.extend(failed_dates)
            skip_data[ticker] = sorted(list(set(current_skips)))
        if new_data_df.empty:
            continue
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
    logger.info(
        f"Pipeline finished. Downloaded {total_rows_downloaded} new price rows for {tickers_with_new_data} tickers.",
        extra={'web_data': final_web_payload}
    )
    financials_filepath = params.get("FINANCIALS_DB_FILE")
    if all_financials_data and financials_filepath:
        logger.info(f"Saving financial data for {len(all_financials_data)} tickers.")
        new_financials_df = pd.DataFrame(all_financials_data)
        new_financials_df['FetchDate'] = pd.to_datetime(new_financials_df['LastUpdated']).dt.date
        try:
            if os.path.exists(financials_filepath):
                existing_df = pd.read_csv(financials_filepath)
                existing_df['FetchDate'] = pd.to_datetime(existing_df['LastUpdated']).dt.date
                combined_df = pd.concat([existing_df, new_financials_df], ignore_index=True)
            else:
                combined_df = new_financials_df
            combined_df.sort_values(by='LastUpdated', inplace=True)
            combined_df.drop_duplicates(subset=['Stock', 'FetchDate'], keep='last', inplace=True)
            final_df_to_save = combined_df.drop(columns=['FetchDate'])
            os.makedirs(os.path.dirname(financials_filepath), exist_ok=True)
            final_df_to_save.to_csv(financials_filepath, index=False)
            logger.info(
                f"Successfully saved financial data to {financials_filepath}. Total records: {len(final_df_to_save)}.")
        except Exception as e:
            logger.critical(f"Failed to save financial data to '{financials_filepath}': {e}")
    elif not financials_filepath:
        logger.warning("'FINANCIALS_DB_FILE' not found in parameters. Cannot save financials.")
    else:
        logger.info("No new financial data was fetched to be saved.")
    if yfinance_skip_file:
        try:
            with open(yfinance_skip_file, 'w') as f:
                json.dump(skip_data, f, indent=4)
            logger.info(f"Successfully saved updated yfinance skip data to {yfinance_skip_file}")
        except Exception as e:
            logger.error(f"Failed to save yfinance skip data: {e}")
    perf_data["new_data_download_loop_duration_s"] = time.time() - loop_start_time
    perf_data["tickers_with_new_data_downloaded"] = tickers_with_new_data
    perf_data["total_tickers_processed"] = total_tickers
    return perf_data, skip_data, date_range_str, total_rows_downloaded

def update_master_db(
        params: dict[str, Any],
        logger: logging.Logger,
        date_range: str,
        rows_downloaded: int
):
    """
    Efficiently updates the master database by scanning for new daily files.
    """
    findb_file = params.get("FINDB_FILE")
    findata_dir = params.get("findata_directory")
    if not findb_file or not findata_dir:
        logger.error("'FINDB_FILE' or 'findata_directory' not in params. Cannot update master DB.")
        return
    web_payload = {
        "download_overall_status": "Running: Synchronizing DB",
        "ticker_download": {
            "current_ticker": "Synchronizing...",
            "date_range": date_range,
            "rows": rows_downloaded
        }
    }
    logger.info("Starting master database synchronization scan...", extra={'web_data': web_payload})
    start_time = time.time()
    existing_records = set()
    master_df = pd.DataFrame()
    if os.path.exists(findb_file):
        try:
            master_df = pd.read_csv(findb_file, parse_dates=['Date'])
            master_df['Date'] = pd.to_datetime(master_df['Date']).dt.date
            existing_records = set(zip(master_df['Stock'], master_df['Date']))
            logger.info(f"Loaded {len(master_df)} records from existing master database.")
        except Exception as e:
            logger.critical(f"Failed to load or parse master DB at '{findb_file}': {e}. Aborting update.")
            return
    else:
        logger.info("No existing master database found. Will create a new one.")
    files_to_add = []
    logger.info(f"Scanning '{findata_dir}' for new daily data files...")
    if not os.path.exists(findata_dir):
        logger.warning(f"Findata directory '{findata_dir}' does not exist. Nothing to sync.")
    else:
        for ticker_folder in os.listdir(findata_dir):
            ticker_path = os.path.join(findata_dir, ticker_folder)
            if os.path.isdir(ticker_path):
                for filename in os.listdir(ticker_path):
                    if filename.startswith(f"StockData_{ticker_folder}_") and filename.endswith(".csv"):
                        try:
                            date_str = filename.split('_')[-1].replace('.csv', '')
                            file_date = datetime.strptime(date_str, "%Y-%m-%d").date()
                            if (ticker_folder, file_date) not in existing_records:
                                files_to_add.append(os.path.join(ticker_path, filename))
                        except (ValueError, IndexError):
                            logger.warning(f"Could not parse date from filename: {filename}. Skipping.")
    if not files_to_add:
        logger.info("Master database is already in sync with all daily files. No update needed.")
        return
    logger.info(f"Found {len(files_to_add)} new daily files to add to the master database.")
    new_data_frames = []
    for file_path in files_to_add:
        try:
            df = pd.read_csv(file_path, dtype={'Stock Splits': float, 'Dividends': float})
            new_data_frames.append(df)
        except Exception as e:
            logger.error(f"Failed to read new data file '{file_path}': {e}")
    if not new_data_frames:
        logger.warning("No data could be read from the identified new files. Aborting update.")
        return
    try:
        new_data_df = pd.concat(new_data_frames, ignore_index=True)
        combined_df = pd.concat([master_df, new_data_df], ignore_index=True)
        combined_df.sort_values(by=['Stock', 'Date'], inplace=True)
        combined_df.drop_duplicates(subset=['Stock', 'Date'], keep='last', inplace=True)
        combined_df.to_csv(findb_file, index=False)
        duration = time.time() - start_time
        logger.info(
            f"Successfully synchronized master database. Added {len(new_data_df)} new records. "
            f"Total records now: {len(combined_df)}. Took {duration:.2f}s."
        )
    except Exception as e:
        logger.critical(f"An error occurred while saving the updated master database to '{findb_file}': {e}")

def log_performance_data(perf_data: dict[str, Any], params: dict[str, Any], logger: logging.Logger):
    """
    Logs the script's performance metrics to a CSV file.
    """
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
    except Exception as e:
        logger.error(f"Failed to log performance data to '{log_path}': {e}")

def copy_file_to_web_accessible_location(source_param_key: str, params: dict[str, Any], logger: logging.Logger):
    """
    Copies a file to the web-accessible data directory.
    """
    source_path = params.get(source_param_key)
    dest_folder = params.get("WEB_ACCESSIBLE_DATA_PATH")
    if not isinstance(source_path, str) or not source_path:
        logger.warning(f"Parameter key '{source_param_key}' is missing or not a valid string. Cannot copy file.")
        return
    if not isinstance(dest_folder, str) or not dest_folder:
        logger.warning("'WEB_ACCESSIBLE_DATA_PATH' is missing or not a valid string. Cannot copy file.")
        return
    if not os.path.exists(source_path):
        logger.warning(f"Source file for key '{source_param_key}' not found at '{source_path}'. Cannot copy.")
        return
    try:
        os.makedirs(dest_folder, exist_ok=True)
        destination_path = os.path.join(dest_folder, os.path.basename(source_path))
        shutil.copy2(source_path, destination_path)
        logger.info(f"Successfully copied '{os.path.basename(source_path)}' to web-accessible location: {destination_path}")
    except Exception as e:
        logger.error(f"Failed to copy file from '{source_path}' to '{dest_folder}': {e}")

# ----------------------------------------------------------- #
#                     The application                         #
# ----------------------------------------------------------- #

def main():
    """
    The main execution pipeline for the Download.py script.
    """
    overall_start_time = time.time()
    script_dir = os.path.dirname(os.path.abspath(__file__))
    expected_params = {
        "debug_mode": bool, "history_years": int, "dynamic_user_agents_enabled": bool,
        "FALLBACK_USER_AGENTS": str, "USER_AGENT_API_URL": str, "SPECIAL_MARKET_CLOSURES": str,
        "PIPELINE_PROGRESS_JSON_FILE": str,
        "DOWNLOAD_PROGRESS_JSON_FILE": str,
        "WEB_ACCESSIBLE_DATA_PATH": str, "FINDATA_PATH": str,
        "FINDB_FILE": str, "FINANCIALS_DB_FILE": str, "TICKERS_FILE": str,
        "YFINANCE_SKIP_FILE": str, "DOWNLOAD_LOG_FILE": str, "DOWNLOAD_PERFORMANCE_FILE": str,
    }
    try:
        paths_file = os.path.join(script_dir, '..', 'parameters', 'paths.txt')
        downpar_file = os.path.join(script_dir, '..', 'parameters', 'downpar.txt')
        params = load_parameters_from_file(
            filepaths=[paths_file, downpar_file],
            expected_parameters=expected_params
        )
        params['findata_directory'] = params.get('FINDATA_PATH')
    except (FileNotFoundError, Exception) as e:
        temp_logger = setup_logger("StartupLogger", "startup_error.log", None)
        temp_logger.critical(f"Could not load parameters. Exiting. Error: {e}", exc_info=True)
        print(f"CRITICAL: Could not load parameters. Exiting. Error: {e}")
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
            os.makedirs(os.path.dirname(download_progress_file), exist_ok=True)
            with open(download_progress_file, 'w') as f:
                json.dump(initial_progress_data, f, indent=4)
    except Exception as e:
        print(f"CRITICAL: Could not initialize progress file {download_progress_file}. Error: {e}")

    logger = setup_logger(
        "DownloadRunner",
        log_file=params.get("DOWNLOAD_LOG_FILE"),
        web_log_file=download_progress_file,
        level=logging.DEBUG if params.get("debug_mode") else logging.INFO
    )
    perf_data = initialize_performance_data(DOWNLOAD_PY_VERSION)
    perf_data["param_load_duration_s"] = time.time() - overall_start_time

    logger.info("Starting Download.py execution pipeline.")

    try:
        # --- MODIFICATION START ---
        logger.info("Loading primary tickers...")
        tickers_df = load_tickers_data(params, logger)
        if tickers_df.empty:
            logger.warning("Primary tickers file could not be loaded or is empty.")
            tickers_df = pd.DataFrame(columns=['Ticker', 'Name', 'Sector', 'Industry'])

        logger.info("Loading benchmark tickers...")
        benchmarks_df = pd.DataFrame(columns=['Ticker', 'Name', 'Sector', 'Industry'])
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
            for col in ['Ticker', 'Name', 'Sector', 'Industry']:
                if col not in temp_benchmarks_df.columns:
                    temp_benchmarks_df[col] = None
            benchmarks_df = temp_benchmarks_df[['Ticker', 'Name', 'Sector', 'Industry']]
            benchmarks_df.dropna(subset=['Ticker'], inplace=True)
            logger.info(f"Successfully loaded {len(benchmarks_df)} benchmark tickers.")
        except FileNotFoundError:
            logger.warning(f"Benchmark file not found at '{benchmarks_file_path}'. This may be expected.")
        except Exception as e:
            logger.error(f"An error occurred while reading the benchmark tickers file: {e}")

        combined_tickers_df = pd.concat([tickers_df, benchmarks_df], ignore_index=True)
        combined_tickers_df.drop_duplicates(subset=['Ticker'], keep='last', inplace=True)
        logger.info(f"Total unique tickers to process (including benchmarks): {len(combined_tickers_df)}")
        # --- MODIFICATION END ---

        if combined_tickers_df.empty:
            logger.critical("No valid tickers were loaded. Aborting pipeline.",
                            extra={'web_data': {"download_overall_status": "Failed: No Tickers"}})
            import sys
            sys.exit(1)

        perf_data, _, date_range_str, total_rows_downloaded = download_and_process_data(
            tickers_df=combined_tickers_df,
            params=params,
            perf_data=perf_data,
            logger=logger
        )

        update_master_db(params, logger, date_range_str, total_rows_downloaded)

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

    except Exception as e:
        logger.critical(f"An unhandled exception occurred in the main pipeline: {e}", exc_info=True,
                        extra={'web_data': {"download_overall_status": "Failed: Unhandled Exception"}})
    finally:
        perf_data["overall_script_duration_s"] = time.time() - overall_start_time
        log_performance_data(perf_data, params, logger)
        copy_file_to_web_accessible_location("DOWNLOAD_PERFORMANCE_FILE", params, logger)
        logger.info("Execution complete.")

if __name__ == "__main__":
    import sys
    if len(sys.argv) > 1 and sys.argv[1].lower() == 'test':
        print("--- Running Test Suite for Download.py Functions (using shared_utils) ---")
        start_time = time.time()
        EXPECTED_PARAMS = {
            "debug_mode": bool, "history_years": int, "dynamic_user_agents_enabled": bool,
            "FALLBACK_USER_AGENTS": str, "USER_AGENT_API_URL": str, "SPECIAL_MARKET_CLOSURES": str,
            "PIPELINE_JSON_FILE": str, "DOWNLOAD_JSON_FILE": str, "WEB_ACCESSIBLE_DATA_PATH": str, "FINDATA_PATH": str,
            "FINDB_FILE": str, "FINANCIALS_DB_FILE": str, "TICKERS_FILE": str,
            "YFINANCE_SKIP_FILE": str, "DOWNLOAD_LOG_FILE": str, "DOWNLOAD_PERFORMANCE_FILE": str,
        }
        SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
        try:
            paths_file = os.path.join(SCRIPT_DIR, '..', 'parameters', 'paths.txt')
            downpar_file = os.path.join(SCRIPT_DIR, '..', 'parameters', 'downpar.txt')
            test_params = load_parameters_from_file(
                filepaths=[paths_file, downpar_file],
                expected_parameters=EXPECTED_PARAMS
            )
            print(f"Successfully loaded {len(test_params)} parameters for testing.")
        except Exception as e:
            print(f"CRITICAL: Failed to load parameters for test run. Error: {e}")
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
            with open(temp_tickers_file, 'w') as f:
                f.write("PETR4.SA,Energy,Oil & Gas\n")
                f.write("INVALID.SA,Test,Invalid\n")
            live_test_params = test_params.copy()
            live_test_params["TICKERS_FILE"] = temp_tickers_file
            live_test_params["findata_directory"] = temp_findata_path
            live_test_params["FINANCIALS_DB_FILE"] = os.path.join(temp_findb_path, "financials_db_test.csv")
            live_test_params["YFINANCE_SKIP_FILE"] = os.path.join(temp_findb_path, "yfinance_skip_test.json")
            live_test_params["DOWNLOAD_PERFORMANCE_FILE"] = os.path.join(temp_findb_path, "perf_test.csv")
            live_test_params["WEB_ACCESSIBLE_DATA_PATH"] = temp_web_path
            live_test_params["history_years"] = 1
            test_tickers_df = load_tickers_data(live_test_params, test_logger)
            initial_perf_data = initialize_performance_data(DOWNLOAD_PY_VERSION)
            final_perf_data, final_skip_data, _, _ = download_and_process_data(
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
        except (AssertionError, FileNotFoundError, ValueError) as e:
            test_logger.error(f"--- Test FAILED: {e} ---", exc_info=True)
        except Exception as e:
            test_logger.error(f"--- An unexpected error occurred during test: {e} ---", exc_info=True)
        finally:
            if os.path.exists(temp_test_dir):
                shutil.rmtree(temp_test_dir)
                test_logger.info(f"Cleaned up temporary test directory: {temp_test_dir}")
            print(f"--- Test Suite Finished in {time.time() - start_time:.2f} seconds ---")
    else:
        main()
