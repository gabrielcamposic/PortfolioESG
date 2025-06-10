#!/home/gabrielcampos/.pyenv/versions/env-fa/bin/python
# ----------------------------------------------------------- #
#                           Libraries                         #
# ----------------------------------------------------------- #

import yfinance as yfin
import pandas as pd
import os
import requests
from datetime import datetime, timedelta
import holidays
import random
import time # Keep time for interval timing
import json
import shutil # For copying files
from fake_useragent import UserAgent
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry 

# --- Script Version ---
DOWNLOAD_PY_VERSION = "1.3.0" # Added comprehensive error handling, improved web logging
# ----------------------

# ----------------------------------------------------------- #
#                       Global variables                      #
# ----------------------------------------------------------- #

# These will be populated by load_download_parameters
DEBUG_MODE = False
HISTORY_YEARS = 10
FINDATA_DIR = ""
FINDB_DIR = ""
TICKERS_FILE = ""
DB_FILEPATH = "" # Will be constructed
DOWNLOAD_LOG_FILE = ""
PROGRESS_JSON_FILE = ""
DOWNLOAD_PERFORMANCE_LOG_PATH = "" # For performance logging
YFINANCE_SKIP_FILEPATH = "" # For yfinance unavailable data (skip list)
WEB_ACCESSIBLE_DATA_FOLDER = "" # For copying logs

# Fallback list of user agents (moved here, after parameter placeholders)
FALLBACK_USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 11_6) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:120.0) Gecko/20100101 Firefox/120.0",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 12.3; rv:118.0) Gecko/20100101 Firefox/118.0",
    "Mozilla/5.0 (X11; Linux x86_64; rv:115.0) Gecko/20100101 Firefox/115.0",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 13_1) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.1 Safari/605.1.15",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/118.0.0.0 Safari/537.36 Edg/118.0.2088.76",
    "Mozilla/5.0 (Linux; Android 11; Pixel 5) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.6099.144 Mobile Safari/537.36",
    "Mozilla/5.0 (iPhone; CPU iPhone OS 17_2 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.2 Mobile/15E148 Safari/604.1"
]
USER_AGENTS = FALLBACK_USER_AGENTS # Initialize with fallback
ua = None # For fake_useragent instance

# ----------------------------------------------------------- #
#                           Classes                           #
# ----------------------------------------------------------- #

class Logger:
    def __init__(self, log_path, flush_interval=10, web_log_path=None):
        self.log_path = log_path
        self.web_log_path = web_log_path  # Path to the web-accessible log file
        self.messages = []
        self.flush_interval = flush_interval
        self.log_count = 0
        self.web_data = {}  # Data to be written to the web log file

    def log(self, message, web_data=None):
        """Logs messages and optionally updates the web log file."""
        timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        log_entry = f"{timestamp} - {message}"
        print(log_entry)  # Console output
        self.messages.append(log_entry)
        self.log_count += 1

        # Update web log file if web_data is provided
        if web_data and self.web_log_path: # web_data is the new data for *this* specific log call
            loaded_json_data = {}
            if os.path.exists(self.web_log_path):
                try:
                    with open(self.web_log_path, 'r') as f_read:
                        loaded_json_data = json.load(f_read)
                except json.JSONDecodeError:
                    # Log to console as logger might be in a weird state or path is new
                    print(f"{timestamp} - Warning: Malformed JSON in {self.web_log_path}. Will be overwritten by current update.")
                except Exception as e:
                    print(f"{timestamp} - Error reading {self.web_log_path} in log(): {e}")
            
            loaded_json_data.update(web_data) # Merge the new data from this specific log call
            
            try:
                with open(self.web_log_path, 'w') as web_file:
                    json.dump(loaded_json_data, web_file, indent=4)
                    web_file.flush()
                    os.fsync(web_file.fileno())
                self.web_data = loaded_json_data # Update internal state to match what was just written
            except Exception as e:
                # Log to console as logger might be in a weird state
                print(f"{timestamp} - Error writing to web log file {self.web_log_path} in log(): {e}")


        if self.log_count % self.flush_interval == 0:
            self.flush()

    def flush(self):
        """Write logs to file in bulk and clear memory."""
        if self.messages:
            with open(self.log_path, 'a') as file:
                file.write("\n".join(self.messages) + "\n")
            self.messages = []  # Clear memory

    def update_web_log(self, key, value):
        """Update a specific key in the web log JSON file."""
        if self.web_log_path:
            timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S') # For potential console logs
            loaded_json_data = {}
            if os.path.exists(self.web_log_path):
                try:
                    with open(self.web_log_path, 'r') as f_read:
                        loaded_json_data = json.load(f_read)
                except json.JSONDecodeError:
                    print(f"{timestamp} - Warning: Malformed JSON in {self.web_log_path} for update_web_log. Will create new/overwrite with current key.")
                except Exception as e:
                    print(f"{timestamp} - Error reading {self.web_log_path} in update_web_log(): {e}")
            
            loaded_json_data[key] = value # Update the specific key in the loaded data
            
            try:
                with open(self.web_log_path, 'w') as web_file:
                    json.dump(loaded_json_data, web_file, indent=4)
                    web_file.flush()
                    os.fsync(web_file.fileno())
                self.web_data = loaded_json_data # Update internal state to match what was just written
            except Exception as e:
                print(f"Error updating web log file {self.web_log_path}: {e}") # Log to console if logger itself fails

# ----------------------------------------------------------- #
#                        Basic Functions                      #
# ----------------------------------------------------------- #

def load_download_parameters(filepath, logger_instance=None):
    """
    Reads download parameters from the given file, converts to appropriate types,
    and expands paths.
    """
    parameters = {}
    expected_types = {
        "debug_mode": bool,
        "history_years": int,
        "findata_directory": str,
        "findb_directory": str,
        "tickers_list_file": str,
        "download_log_file": str,
        "progress_json_file": str,
        # Optional user-agent params
        "dynamic_user_agents_enabled": bool,
        "download_performance_log_path": str,
        "web_accessible_data_folder": str,
        "yfinance_skip_filepath": str # Path for the yfinance skip file
    }

    try:
        with open(filepath, 'r') as f:
            for line_number, line in enumerate(f, 1):
                line = line.strip()
                if not line or line.startswith('#'):
                    continue
                
                parts = line.split('=', 1)
                if len(parts) != 2:
                    message = f"Warning: Malformed line {line_number} in '{filepath}': '{line}'. Skipping."
                    if logger_instance: logger_instance.log(message)
                    else: print(message)
                    continue
                
                key, value_str = parts[0].strip(), parts[1].strip()
                processed_value = None

                if key in expected_types:
                    target_type = expected_types[key]
                    try:
                        if target_type == int:
                            processed_value = int(value_str)
                        elif target_type == float: # Though no floats expected here yet
                            processed_value = float(value_str)
                        elif target_type == bool:
                            if value_str.lower() == 'true':
                                processed_value = True
                            elif value_str.lower() == 'false':
                                processed_value = False
                            else:
                                raise ValueError(f"Boolean value for '{key}' must be 'true' or 'false', got '{value_str}'")
                        elif target_type == str:
                            if value_str.startswith('~'):
                                processed_value = os.path.expanduser(value_str)
                            else:
                                processed_value = value_str
                        parameters[key] = processed_value
                    except ValueError:
                        message = (f"Warning: Could not convert value '{value_str}' for key '{key}' to {target_type.__name__} "
                                   f"in '{filepath}'. Using raw string value '{value_str}'.")
                        if logger_instance: logger_instance.log(message)
                        else: print(message)
                        parameters[key] = value_str # Fallback to string
                        processed_value = value_str # Ensure processed_value reflects the fallback for logging
                    # This log is now correctly indented and follows the try-except block for known keys
                    if DEBUG_MODE and logger_instance:
                        logger_instance.log(f"DEBUG: Loaded parameter: {key} = {processed_value}")
                else:
                    # Handle unknown keys by treating them as strings after path expansion
                    message = f"Info: Unknown parameter key '{key}' found in '{filepath}'. Treating as string."
                    if logger_instance: logger_instance.log(message)
                    else: print(message)

                    if value_str.startswith('~'):
                        processed_value = os.path.expanduser(value_str)
                    else:
                        processed_value = value_str
                    parameters[key] = processed_value
                    if DEBUG_MODE and logger_instance:
                        logger_instance.log(f"DEBUG: Loaded unknown parameter: {key} = {processed_value}")

    except FileNotFoundError:
        message = f"CRITICAL ERROR: Parameters file '{filepath}' not found. Cannot load download settings."
        if logger_instance: logger_instance.log(message)
        else: print(message)
        raise
    except Exception as e:
        message = f"CRITICAL ERROR: Failed to read or parse parameters file '{filepath}': {e}"
        if logger_instance: logger_instance.log(message)
        else: print(message)
        raise

    # Validate that critical parameters are present
    critical_keys = ["findata_directory", "findb_directory", "tickers_list_file", "download_log_file"]
    for crit_key in critical_keys:
        if crit_key not in parameters or not parameters[crit_key]: # Check if key exists and has a non-empty value
            message = f"CRITICAL ERROR: Missing or empty critical parameter '{crit_key}' in '{filepath}'."
            if logger_instance: logger_instance.log(message)
            else: print(message)
            raise ValueError(message)
    return parameters

# Function to fetch dynamic user agents
def fetch_dynamic_user_agents():
    if DEBUG_MODE:
        logger.log("DEBUG: Attempting to fetch dynamic user agents.")
    try:
        # Example API for fetching user agents (replace with a reliable source if needed)
        response = requests.get("https://useragentapi.com/api/v4/json/f7afb3be4db1a4fd3f67cea1c225fadc/user_agents")
        response.raise_for_status()  # Raise an error for bad responses (4xx or 5xx)
        data = response.json()

        # Extract user agents from the JSON response
        user_agents = [agent['user_agent'] for agent in data.get('data', [])]

        if DEBUG_MODE:
            logger.log(f"DEBUG: Fetched {len(user_agents)} dynamic user agents.")
        return user_agents
    except Exception as e:
        if DEBUG_MODE:
            logger.log(f"DEBUG: Failed to fetch dynamic user agents: {e}")
        logger.log(f"⚠️ Failed to fetch dynamic user agents: {e}")
        return None

# Function to rotate User-Agent and Proxy
def rotate_user_agent(session, user_agents):
    if user_agents:
        random_user_agent = random.choice(user_agents)
        session.headers.update({"User-Agent": random_user_agent})
        if DEBUG_MODE:
            logger.log(f"DEBUG: Rotated User-Agent: {random_user_agent}")
    else:
        if DEBUG_MODE:
            logger.log("DEBUG: No user agents available for rotation.")

def get_previous_business_day():
    today = datetime.today()
    sp_holidays = holidays.Brazil(years=today.year, subdiv='SP')

    if today.weekday() == 0:  # Monday
        previous_business_day = today - timedelta(days=3)
    else:
        previous_business_day = today - timedelta(days=1)

    while previous_business_day.weekday() >= 5 or previous_business_day in sp_holidays:
        previous_business_day -= timedelta(days=1)

    return previous_business_day.strftime('%Y-%m-%d')

def get_sao_paulo_holidays(year):
    from dateutil.easter import easter
    holiday_dict = {}

    # National + SP holidays
    sp_holidays = holidays.Brazil(years=year, subdiv='SP')
    for date, name in sp_holidays.items():
        holiday_dict[date] = name

    # Fixed market-specific dates
    fixed_holidays = {
        datetime(year, 1, 25): "Aniversário de São Paulo",
        datetime(year, 7, 9): "Data Magna SP",
        datetime(year, 11, 20): "Consciência Negra",
        datetime(year, 12, 24): "Véspera de Natal",
        datetime(year, 12, 31): "Véspera de Ano Novo",
    }

    # Floating based on Easter
    easter_sunday = easter(year)
    floating_holidays = {
        easter_sunday - timedelta(days=48): "Carnaval (Segunda-feira)",
        easter_sunday - timedelta(days=47): "Carnaval (Terça-feira)",
        easter_sunday - timedelta(days=2): "Sexta-feira Santa",
        easter_sunday + timedelta(days=60): "Corpus Christi",
    }

    # Market closures
    special_market_closures = {
        datetime(2016, 12, 30): "Encerramento B3",
        datetime(2022, 12, 30): "Encerramento B3",
        datetime(2023, 12, 29): "Encerramento B3",
    }

    all_custom = {**fixed_holidays, **floating_holidays, **special_market_closures}
    holiday_dict.update(all_custom)

    return holiday_dict


def get_missing_dates(ticker, current_findata_dir, start_date, end_date, yfinance_skip_data, logger_instance=None):
    """
    Return only business days (excluding weekends and holidays) that are missing for a given ticker,
    and are not in the provided yfinance_skip_data.
    """
    if DEBUG_MODE:
        # Use logger_instance if provided, otherwise fallback to global logger
        log_target = logger_instance if logger_instance else logger
        log_target.log(f"DEBUG: get_missing_dates for {ticker}, start: {start_date.strftime('%Y-%m-%d')}, end: {end_date.strftime('%Y-%m-%d')}")
    
    ticker_folder = os.path.join(current_findata_dir, ticker)
    if not os.path.exists(ticker_folder):
        logger.log(f"📂 No folder found for {ticker}. All dates are missing.")
        ticker_holidays = holidays.Brazil(years=range(start_date.year, end_date.year + 1), subdiv='SP')
        # The following line was causing issues if get_sao_paulo_holidays returns a dict instead of HolidayBase
        ticker_holidays.update(get_sao_paulo_holidays(start_date.year)) # Pass logger_instance if get_sao_paulo_holidays uses it
        business_days = pd.bdate_range(start=start_date, end=end_date, freq='C', holidays=ticker_holidays)
        skipped_dates_for_ticker_str = yfinance_skip_data.get(ticker, [])
        skipped_dates_for_ticker_dt_obj = {datetime.strptime(d_str, "%Y-%m-%d").date() for d_str in skipped_dates_for_ticker_str}
        return [dt.to_pydatetime() for dt in business_days if dt.date() not in skipped_dates_for_ticker_dt_obj]

    # Step 1: Get existing dates from CSV filenames
    existing_dates = []
    for file in os.listdir(ticker_folder):
        if file.startswith(f"StockData_{ticker}_") and file.endswith(".csv"):
            try:
                file_date = file.split("_")[-1].replace(".csv", "")
                existing_dates.append(datetime.strptime(file_date, "%Y-%m-%d").date())
            except ValueError:
                logger.log(f"⚠️ Skipping file with invalid date format: {file}")
                continue
    if DEBUG_MODE:
        logger.log(f"DEBUG: Found {len(existing_dates)} existing date files for {ticker}.")

    # Step 2: Build full business date range (excluding holidays/weekends)
    all_years = list(range(start_date.year, end_date.year + 1))
    br_holidays = {}

    for year in all_years:
        custom = get_sao_paulo_holidays(year) # Pass logger_instance if get_sao_paulo_holidays uses it
        br_holidays.update(custom)

    business_days = pd.bdate_range(start=start_date, end=end_date, freq='C', holidays=br_holidays)
    if DEBUG_MODE:
        logger.log(f"DEBUG: Generated {len(business_days)} business days in range for {ticker}.")

    # Step 2.5: Exclude skipped dates
    skipped_dates_for_ticker_str = yfinance_skip_data.get(ticker, [])
    skipped_dates_for_ticker_dt_obj = {datetime.strptime(d_str, "%Y-%m-%d").date() for d_str in skipped_dates_for_ticker_str}

    # Filter business_days (which is a DatetimeIndex)
    # Keep only those business_days that are NOT in skipped_dates_for_ticker_dt_obj
    potential_business_days_to_check_files_for = [dt for dt in business_days if dt.date() not in skipped_dates_for_ticker_dt_obj]

    if DEBUG_MODE and len(skipped_dates_for_ticker_dt_obj) > 0:
        logger.log(f"DEBUG: For {ticker}, {len(business_days) - len(potential_business_days_to_check_files_for)} dates were already skipped and excluded from file check.")

    # Step 3: Find missing dates (as datetime objects) by checking against existing files
    missing_dates = [dt.to_pydatetime() for dt in potential_business_days_to_check_files_for if dt.date() not in existing_dates]
    if DEBUG_MODE:
        logger.log(f"DEBUG: Identified {len(missing_dates)} missing dates for {ticker}.")

    return missing_dates

def initialize_performance_data():
    return {
        "run_start_timestamp": datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
        "download_py_version": DOWNLOAD_PY_VERSION,
        "param_load_duration_s": 0.0, "user_agent_setup_duration_s": 0.0,
        "initial_db_load_duration_s": 0.0, "findata_processing_duration_s": 0.0,
        "total_tickers_processed": 0, "tickers_with_new_data_downloaded": 0,
        "new_data_download_loop_duration_s": 0.0, "final_db_save_duration_s": 0.0,
        "overall_script_duration_s": 0.0
    }

def read_tickers_from_file(file_path):
    with open(file_path, 'r') as f:
        tickers = [line.strip() for line in f.readlines() if line.strip()]
    return tickers

def save_ticker_data_to_csv(ticker, data, current_findata_dir):
    """
    Save the fetched data for a ticker to individual CSVs in the findata folder (one file per date).
    """
    if DEBUG_MODE:
        logger.log(f"DEBUG: save_ticker_data_to_csv for ticker: {ticker}")
    # Ensure the current_findata_dir folder for the ticker exists
    ticker_folder = os.path.join(current_findata_dir, ticker)
    if not os.path.exists(ticker_folder):
        os.makedirs(ticker_folder)

    # Validate the data
    if data.empty:
        logger.log(f"⚠️ No data to save for ticker: {ticker}. DataFrame is empty.")
        if DEBUG_MODE:
            logger.log(f"DEBUG: No data to save for {ticker} as DataFrame is empty.")
        return

    # Make sure 'Date' is a datetime object
    data['Date'] = pd.to_datetime(data['Date'], errors='coerce')
    data = data.dropna(subset=['Date'])

    # Save one CSV per unique date
    for date, group in data.groupby(data['Date'].dt.date):
        file_name = f"StockData_{ticker}_{date}.csv"
        file_path = os.path.join(ticker_folder, file_name)

        try:
            group.to_csv(file_path, index=False)
            if DEBUG_MODE:
                logger.log(f"DEBUG: Saved data for {ticker} on {date} to {file_path}")
            logger.log(f"✅ Data for {ticker} on {date} saved to {file_path}")
        except Exception as e:
            logger.log(f"⚠️ Error saving data for {ticker} on {date}: {e}")
            if DEBUG_MODE:
                logger.log(f"DEBUG: Error saving data for {ticker} on {date}: {e}")

def debug_check_dates_against_holidays(dates_to_check):
    from datetime import datetime
    import holidays

    # This function seems to be for manual debugging, so its internal prints are fine.
    checked_dates = [datetime.strptime(d, "%Y-%m-%d").date() for d in dates_to_check]
    all_years = set(d.year for d in checked_dates)

    # Correct merge into a flat dict, not HolidayBase
    br_holidays = {}
    for year in all_years:
        national = holidays.Brazil(years=year, subdiv='SP')
        custom = get_sao_paulo_holidays(year)

        for day, name in national.items():
            br_holidays[day] = name
        for day, name in custom.items():
            br_holidays[day] = name

    print("📆 Checking which missing dates are in the holiday calendar...\n")
    for d in checked_dates:
        holiday = br_holidays.get(d)
        if holiday:
            print(f"✅ {d} is a holiday: {holiday}")
        else:
            print(f"❌ {d} is NOT marked as a holiday")

def download_and_append(tickers_list, current_findata_dir, current_findb_dir, current_db_filepath, perf_data_ref, yfinance_skip_data):
    """
    Download missing data for each ticker, compare with existing data in findata and StockDataDB.csv,
    and update StockDataDB.csv with only the missing rows.
    """
    if DEBUG_MODE:
        logger.log("DEBUG: Starting download_and_append function.")
    global USER_AGENTS, ua
    common_cols = ['Date', 'Stock', 'Open', 'Low', 'High', 'Close', 'Volume']

    end_date = datetime.strptime(get_previous_business_day(), '%Y-%m-%d')
    # start_date for get_missing_dates will be defined later, per ticker if needed, or globally.
    # For now, the global start_date for yfinance downloads is defined here.
    global_start_date_for_yfinance = datetime.today() - timedelta(days=365 * HISTORY_YEARS)

    # Helper to get current ticker_download status for modification
    def get_current_ticker_status():
        # Fallback to a basic structure if "ticker_download" isn't in web_data yet (should be rare after initial log)
        return logger.web_data.get("ticker_download", {"current_ticker": "Initializing...", "completed_tickers": 0, "total_tickers": 0, "progress": 0, "date_range": "N/A", "rows": 0}).copy()

    # Step 1: Load existing StockDataDB.csv
    initial_db_load_start_time = time.time()
    # This DataFrame will be the base for accumulating all data.
    if os.path.exists(current_db_filepath):
        combined_data = pd.read_csv(current_db_filepath)
        if DEBUG_MODE:
            logger.log(f"DEBUG: Raw combined_data (from existing_db) loaded with {len(combined_data)} rows. Columns: {combined_data.columns.tolist()}")
        combined_data['Date'] = pd.to_datetime(combined_data['Date'], format='mixed', errors='coerce').dt.date # Ensure Date is in correct format
        
        status_update = get_current_ticker_status()
        status_update["current_ticker"] = f"Loaded StockDataDB.csv ({len(combined_data)} rows)"
        logger.update_web_log("ticker_download", status_update)

        if DEBUG_MODE:
            logger.log(f"DEBUG: Loaded existing StockDataDB.csv into combined_data. Shape: {combined_data.shape} from {current_db_filepath}.")
        logger.log(f"✅ Loaded existing StockDataDB.csv. Rows: {len(combined_data)}, Path: {current_db_filepath}")
    else:
        combined_data = pd.DataFrame(columns=common_cols)
        status_update = get_current_ticker_status()
        status_update["current_ticker"] = "StockDataDB.csv not found. Initializing."
        logger.update_web_log("ticker_download", status_update)
        if DEBUG_MODE:
            logger.log(f"DEBUG: StockDataDB.csv not found at {current_db_filepath}. Initializing empty combined_data. Shape: {combined_data.shape}")
        logger.log(f"⚠️ {current_db_filepath} does not exist. Starting with an empty database.")

    perf_data_ref["initial_db_load_duration_s"] = time.time() - initial_db_load_start_time

    # Step 2 & 3 (Merged): Process findata folder ticker by ticker and merge into combined_data
    logger.log(f"🔄 Processing existing data from findata directory: {current_findata_dir}")
    
    status_update = get_current_ticker_status()
    status_update["current_ticker"] = "Processing local findata directory..."
    logger.update_web_log("ticker_download", status_update)
    findata_processing_start_time = time.time()


    for ticker_item in tickers_list: # Iterate using the passed tickers_list
        ticker_folder = os.path.join(current_findata_dir, ticker_item)
        if not os.path.exists(ticker_folder):
            if DEBUG_MODE:
                logger.log(f"DEBUG: No findata folder found for ticker {ticker_item} at {ticker_folder}. Skipping this ticker for findata load.")
            logger.log(f"📂 No findata data folder for {ticker_item}. Skipping.")
            continue
        
        status_update = get_current_ticker_status()
        status_update["current_ticker"] = f"Processing local files for {ticker_item}..."
        logger.update_web_log("ticker_download", status_update)
        
        if DEBUG_MODE:
            logger.log(f"DEBUG: Processing findata for ticker: {ticker_item} from {ticker_folder}")
        
        files_in_ticker_folder = [f for f in os.listdir(ticker_folder) if f.endswith(".csv")]
        if DEBUG_MODE:
            logger.log(f"DEBUG: Found {len(files_in_ticker_folder)} CSV files in {ticker_folder}.")

        if not files_in_ticker_folder:
            logger.log(f"📂 No CSV files found for {ticker_item} in {ticker_folder}. Skipping.")
            continue

        # Initialize lists and counters for the current ticker's findata files
        ticker_findata_rows = []
        files_processed_for_ticker = 0
        rows_loaded_for_ticker = 0

        for file_count, file_name in enumerate(files_in_ticker_folder):
            file_path = os.path.join(ticker_folder, file_name)
            try:
                if DEBUG_MODE and file_count % 50 == 0 : # Log every 50 files per ticker to avoid flooding
                    logger.log(f"DEBUG: Loading file {file_count + 1}/{len(files_in_ticker_folder)} for ticker {ticker_item}: {file_path}")
                file_data = pd.read_csv(file_path)
                files_processed_for_ticker += 1
                if 'Date' in file_data.columns:
                    file_data['Date'] = pd.to_datetime(file_data['Date'], format='mixed', errors='coerce').dt.date
                else:
                    logger.log(f"⚠️ 'Date' column missing in file {file_path}. Skipping this file.")
                    continue
                file_data['Stock'] = ticker_item
                ticker_findata_rows.append(file_data)
                rows_loaded_for_ticker += len(file_data)
            except Exception as e:
                logger.log(f"⚠️ Failed to load file {file_path}: {e}")
        
        # After processing all files for the current ticker_item
        if ticker_findata_rows:
            if DEBUG_MODE:
                logger.log(f"DEBUG: For ticker {ticker_item}, processed {files_processed_for_ticker} files from findata, loaded {rows_loaded_for_ticker} rows. Concatenating into ticker_df...")
            ticker_df = pd.concat(ticker_findata_rows, ignore_index=True)
            if DEBUG_MODE:
                logger.log(f"DEBUG: Concatenated {len(ticker_df)} findata rows for {ticker_item}. Shape: {ticker_df.shape}. Columns: {ticker_df.columns.tolist()}")

            # Ensure columns match common_cols before concatenating with combined_data
            # For ticker_df:
            missing_cols_in_ticker_df = [col for col in common_cols if col not in ticker_df.columns]
            for col in missing_cols_in_ticker_df:
                ticker_df[col] = pd.NA # Or appropriate default like 0 for numeric, or None
            if not ticker_df.empty: # Only reorder if not empty
                ticker_df = ticker_df[common_cols] # Reorder/select common columns

            # For combined_data (especially if it was empty or from an old DB with different columns):
            if combined_data.empty and not ticker_df.empty: # If combined_data was empty, it now takes columns of the first ticker_df
                 combined_data = pd.DataFrame(columns=common_cols) # Initialize with common_cols
            
            missing_cols_in_combined_data = [col for col in common_cols if col not in combined_data.columns]
            for col in missing_cols_in_combined_data:
                 combined_data[col] = pd.NA
            if not combined_data.empty: # Only reorder if not empty
                combined_data = combined_data[common_cols]

            # Now concatenate ticker_df to combined_data
            combined_data = pd.concat([combined_data, ticker_df], ignore_index=True)
            if DEBUG_MODE:
                logger.log(f"DEBUG: Combined {ticker_item}'s findata into combined_data. Shape before dedup: {combined_data.shape}.")
            
            combined_data = combined_data.drop_duplicates(subset=['Date', 'Stock'], keep='last')
            if DEBUG_MODE:
                logger.log(f"DEBUG: Deduplicated combined_data after {ticker_item}'s findata. Shape after dedup: {combined_data.shape}.")
            logger.log(f"✅ Processed and merged findata for {ticker_item}. Current total unique rows in combined_data: {len(combined_data)}")
        else:
            if DEBUG_MODE:
                logger.log(f"DEBUG: No valid findata rows loaded for {ticker_item} from its folder. Skipping merge for this ticker.")
            logger.log(f"ℹ️ No new findata rows to merge for {ticker_item}.")

    perf_data_ref["findata_processing_duration_s"] = time.time() - findata_processing_start_time
    logger.log(f"✅ Finished processing all findata. Current total unique rows in combined_data: {len(combined_data)}. Shape: {combined_data.shape}.")
    
    # Step 4: Download missing data for each ticker
    # all_downloaded_data list is removed; data will be merged immediately.
    logger.log("🔄 Starting download of new/missing data...")
    
    new_data_download_loop_start_time = time.time()
    local_tickers_with_new_data_count = 0
    status_update = get_current_ticker_status()
    cumulative_rows_downloaded_this_run = 0 # Initialize cumulative row counter
    status_update["current_ticker"] = "Preparing to download new/missing data..."
    logger.update_web_log("ticker_download", status_update)
    perf_data_ref["total_tickers_processed"] = len(tickers_list)

    for i, ticker_to_process in enumerate(tickers_list): # Minor rename for clarity
        total_tickers_to_process = len(tickers_list)

        # Update progress for the web log BEFORE processing the current ticker
        current_ticker_progress_data = {
            "completed_tickers": i, # Tickers completed *before* this one
            "total_tickers": total_tickers_to_process,
            "progress": (i / total_tickers_to_process) * 100 if total_tickers_to_process > 0 else 0,
            "current_ticker": ticker_to_process, # This is the one *being* processed
            "date_range": "N/A", # Will be updated after potential download
            "rows": 0 # Will be updated after potential download
        }
        # Merge with existing status rather than overwriting other parts of ticker_download
        merged_status_for_web = get_current_ticker_status()
        merged_status_for_web.update(current_ticker_progress_data)
        logger.update_web_log("ticker_download", merged_status_for_web)

        # This message is useful for progress tracking, could be INFO or conditional DEBUG
        if DEBUG_MODE:
            logger.log(f"DEBUG: Processing ticker {i+1}/{len(tickers_list)}: {ticker_to_process}")
        else:
            # Log less frequently if not in debug to avoid flooding, e.g., every 10% or N tickers
            if i % max(1, total_tickers_to_process // 10) == 0 or i == total_tickers_to_process - 1:
                logger.log(f"Processing ticker {i+1}/{len(tickers_list)}: {ticker_to_process}")

        # 🔁 Refresh user agents every 10 tickers
        if i > 0 and i % 10 == 0 and ua:
            try:
                USER_AGENTS = [ua.random for _ in range(50)]
                if DEBUG_MODE:
                    logger.log(f"DEBUG: Refreshed user agent list after {i} tickers processed.")
            except Exception as e:
                if DEBUG_MODE:
                    logger.log(f"DEBUG: Failed to refresh user agents: {e}")

        # Step 1: Determine missing business days
        if DEBUG_MODE: logger.log(f"DEBUG: Calling get_missing_dates for {ticker_to_process}.")
        # Use global_start_date_for_yfinance for determining the overall range for missing dates
        missing_dates = get_missing_dates(ticker_to_process, current_findata_dir, global_start_date_for_yfinance, end_date, yfinance_skip_data, logger)
        if DEBUG_MODE: logger.log(f"DEBUG: get_missing_dates returned {len(missing_dates)} potential missing dates for {ticker_to_process}.")
        confirmed_missing_dates = []
        for d in missing_dates:
            # This check is redundant if get_missing_dates is correct, but good for robustness
            file_path = os.path.join(current_findata_dir, ticker_to_process, f"StockData_{ticker_to_process}_{d.date()}.csv")
            if not os.path.exists(file_path):
                confirmed_missing_dates.append(d)

        if not confirmed_missing_dates:
            logger.log(f"✅ All data for {ticker_to_process} is already downloaded or no missing dates found. Skipping download.")
            # Update web log to reflect completion of this ticker (even if skipped)
            current_ticker_progress_data["completed_tickers"] = i + 1
            current_ticker_progress_data["progress"] = ((i + 1) / total_tickers_to_process) * 100 if total_tickers_to_process > 0 else 0
            current_ticker_progress_data["current_ticker"] = f"{ticker_to_process} (No new dates)"
            # date_range and rows remain N/A or 0
            merged_status_for_web_skip = get_current_ticker_status()
            merged_status_for_web_skip.update(current_ticker_progress_data)
            logger.update_web_log("ticker_download", merged_status_for_web_skip)
            continue

        # If we proceed, it means there are dates to attempt downloading for.
        # current_ticker_progress_data["current_ticker"] is already set to ticker_to_process.

        if DEBUG_MODE:
            logger.log(f"DEBUG: Confirmed {len(confirmed_missing_dates)} missing dates for {ticker_to_process} to download.")

        # Step 2: Fetch missing data
        if DEBUG_MODE:
            logger.log(f"DEBUG: Rotating user agent for {ticker_to_process}.")
        rotate_user_agent(session, USER_AGENTS) # Only rotate user agent now
        end_date_for_download = max(confirmed_missing_dates) + timedelta(days=1)
        download_start_date_str = min(confirmed_missing_dates).strftime('%Y-%m-%d')
        download_end_date_str = end_date_for_download.strftime('%Y-%m-%d')
        if DEBUG_MODE:
            logger.log(f"DEBUG: Calling yfin.download for {ticker_to_process}, start: {download_start_date_str}, end: {download_end_date_str}")
        data = yfin.download(
            ticker_to_process,
            start=download_start_date_str,
            end=download_end_date_str
        )
        if data.empty:
            logger.log(f"⚠️ No data fetched by yfinance for {ticker_to_process} for the period {download_start_date_str} to {download_end_date_str}. Skipping save.")
            if DEBUG_MODE:
                logger.log(f"DEBUG: yfin.download returned empty DataFrame for {ticker_to_process}.")
            # Update web log to reflect completion of this ticker attempt
            current_ticker_progress_data["completed_tickers"] = i + 1
            current_ticker_progress_data["progress"] = ((i + 1) / total_tickers_to_process) * 100 if total_tickers_to_process > 0 else 0
            current_ticker_progress_data["current_ticker"] = f"{ticker_to_process} (No data fetched)"
            current_ticker_progress_data["date_range"] = f"{download_start_date_str} to {download_end_date_str}" # Show attempted range
            current_ticker_progress_data["rows"] = 0
            merged_status_for_web_no_fetch = get_current_ticker_status()
            merged_status_for_web_no_fetch.update(current_ticker_progress_data)
            logger.update_web_log("ticker_download", merged_status_for_web_no_fetch)
            continue

        data.reset_index(inplace=True)

        # Step 3: Flatten MultiIndex if needed
        if isinstance(data.columns, pd.MultiIndex):
            data.columns = [col[0] if col[0] != '' else col[1] for col in data.columns]
            if DEBUG_MODE:
                logger.log(f"DEBUG: Flattened MultiIndex columns for {ticker_to_process}.")

        # Step 4: Ensure 'Date' column
        if 'Date' not in data.columns:
            if 'index' in data.columns:
                data.rename(columns={'index': 'Date'}, inplace=True)
            else:
                datetime_cols = [col for col in data.columns if pd.api.types.is_datetime64_any_dtype(data[col])]
                if datetime_cols:
                    data.rename(columns={datetime_cols[0]: 'Date'}, inplace=True)

        if 'Date' not in data.columns:
            logger.log(f"⚠️ Ticker {ticker_to_process}: No 'Date' column found after reset. Skipping.")
            if DEBUG_MODE:
                logger.log(f"DEBUG: No 'Date' column for {ticker_to_process} after attempting to find/rename. Skipping.")
            continue

        # Step 5: Filter and Save
        data['Date'] = pd.to_datetime(data['Date']).dt.date
        data['Stock'] = ticker_to_process

        # --- Yfinance Skip Data Update Logic ---
        # Identify dates that were in confirmed_missing_dates but are NOT in the downloaded 'data'
        downloaded_dates_in_data_set = set(data['Date'].tolist()) # set of datetime.date objects
        
        dates_to_add_to_skip_data_for_ticker = []
        for confirmed_dt_obj in confirmed_missing_dates: # confirmed_missing_dates contains datetime.datetime
            confirmed_date_as_date_obj = confirmed_dt_obj.date() # convert to datetime.date for comparison
            if confirmed_date_as_date_obj not in downloaded_dates_in_data_set:
                dates_to_add_to_skip_data_for_ticker.append(confirmed_date_as_date_obj.strftime('%Y-%m-%d'))
        
        if dates_to_add_to_skip_data_for_ticker:
            if DEBUG_MODE:
                logger.log(f"DEBUG: Adding {len(dates_to_add_to_skip_data_for_ticker)} dates to yfinance skip data for {ticker_to_process}: {', '.join(dates_to_add_to_skip_data_for_ticker)}")
            current_skip_data_for_ticker = yfinance_skip_data.get(ticker_to_process, [])
            current_skip_data_for_ticker.extend(dates_to_add_to_skip_data_for_ticker)
            yfinance_skip_data[ticker_to_process] = sorted(list(set(current_skip_data_for_ticker))) # Keep unique and sorted
        # --- End Yfinance Skip Data Update Logic ---

        data = data[data['Date'].isin([d.date() for d in confirmed_missing_dates])]

        if data.empty:
            logger.log(f"⚠️ No new data to save for {ticker_to_process} after filtering for the {len(confirmed_missing_dates)} specifically missing dates.")
            if DEBUG_MODE:
                logger.log(f"DEBUG: DataFrame empty for {ticker_to_process} after filtering for confirmed_missing_dates. Skipping save.")
            # Update web log to reflect completion of this ticker attempt
            current_ticker_progress_data["completed_tickers"] = i + 1
            current_ticker_progress_data["progress"] = ((i + 1) / total_tickers_to_process) * 100 if total_tickers_to_process > 0 else 0
            current_ticker_progress_data["current_ticker"] = f"{ticker_to_process} (No relevant data)"
            current_ticker_progress_data["date_range"] = f"{min(confirmed_missing_dates).strftime('%Y-%m-%d')} to {max(confirmed_missing_dates).strftime('%Y-%m-%d')}"
            current_ticker_progress_data["rows"] = 0
            merged_status_for_web_no_relevant = get_current_ticker_status()
            merged_status_for_web_no_relevant.update(current_ticker_progress_data)
            logger.update_web_log("ticker_download", merged_status_for_web_no_relevant)
            continue

        downloaded_min_date_str = min(data['Date']).strftime('%Y-%m-%d')
        downloaded_max_date_str = max(data['Date']).strftime('%Y-%m-%d')
        logger.log(
            f"📈 Downloaded {len(data)} relevant rows for {ticker_to_process} from {downloaded_min_date_str} to {downloaded_max_date_str}"
        )
        if DEBUG_MODE:
            logger.log(f"DEBUG: Downloaded {len(data)} rows for {ticker_to_process}. Calling save_ticker_data_to_csv.")

        cumulative_rows_downloaded_this_run += len(data) # Add to cumulative count
        save_ticker_data_to_csv(ticker_to_process, data, current_findata_dir)
        
        # Directly merge the newly downloaded 'data' (for the current ticker) into 'combined_data'
        new_data_merged_for_ticker = False
        if not data.empty:
            # Ensure columns match common_cols before concatenating
            # For the newly downloaded 'data':
            missing_cols_in_new_data = [col for col in common_cols if col not in data.columns]
            for col in missing_cols_in_new_data:
                data[col] = pd.NA # Or appropriate default
            if not data.empty:
                data = data[common_cols]

            # For combined_data (especially if it was empty):
            if combined_data.empty and not data.empty: # If combined_data was empty and new data is not
                combined_data = pd.DataFrame(columns=common_cols) # Initialize with common_cols
            
            missing_cols_in_combined_data = [col for col in common_cols if col not in combined_data.columns]
            for col in missing_cols_in_combined_data:
                 combined_data[col] = pd.NA
            if not combined_data.empty:
                combined_data = combined_data[common_cols]

            combined_data = pd.concat([combined_data, data], ignore_index=True)
            if DEBUG_MODE: 
                logger.log(f"DEBUG: Combined newly downloaded data for {ticker_to_process}. Shape before dedup: {combined_data.shape}")
            combined_data = combined_data.drop_duplicates(subset=['Date', 'Stock'], keep='last')
            if DEBUG_MODE: 
                logger.log(f"DEBUG: Deduplicated combined_data after new download for {ticker_to_process}. Shape after dedup: {combined_data.shape}")
            logger.log(f"✅ Merged {len(data)} newly downloaded rows for {ticker_to_process}. Total unique rows in combined_data: {len(combined_data)}")
            new_data_merged_for_ticker = True # Mark that data was actually merged
            
            # Update web log with details after successful download and merge for this ticker
            current_ticker_progress_data["date_range"] = f"{downloaded_min_date_str} to {downloaded_max_date_str}"
            current_ticker_progress_data["rows"] = len(data)
            current_ticker_progress_data["completed_tickers"] = i + 1 # Mark this ticker as completed
            current_ticker_progress_data["progress"] = ((i + 1) / total_tickers_to_process) * 100 if total_tickers_to_process > 0 else 0
            merged_status_for_web_success = get_current_ticker_status()
            merged_status_for_web_success.update(current_ticker_progress_data)
            logger.update_web_log("ticker_download", merged_status_for_web_success)
        
        if new_data_merged_for_ticker: # Increment if data was downloaded AND merged
            local_tickers_with_new_data_count +=1
    perf_data_ref["tickers_with_new_data_downloaded"] = local_tickers_with_new_data_count

    # Step 6: Save the updated StockDataDB.csv
    # Final update for ticker_download to show 100% completion if all tickers were processed
    if total_tickers_to_process > 0:
        # Determine the overall date range the script considered for downloads
        overall_start_date_str = global_start_date_for_yfinance.strftime('%Y-%m-%d')
        overall_end_date_str = end_date.strftime('%Y-%m-%d') # end_date is already a datetime object

        final_ticker_progress = {
            "completed_tickers": total_tickers_to_process,
            "total_tickers": total_tickers_to_process,
            "progress": 100,
            "current_ticker": "All tickers processed",
            "date_range": f"{overall_start_date_str} to {overall_end_date_str}", # Show overall processed range
            "rows": cumulative_rows_downloaded_this_run # Use the cumulative count
        }
        logger.update_web_log("ticker_download", final_ticker_progress)
    
    status_update = get_current_ticker_status() # Get the latest before this final update
    status_update["current_ticker"] = "Saving final StockDataDB.csv..."
    logger.update_web_log("ticker_download", status_update)
    perf_data_ref["new_data_download_loop_duration_s"] = time.time() - new_data_download_loop_start_time

    if DEBUG_MODE:
        logger.log(f"DEBUG: Saving final combined_data with {len(combined_data)} rows to {current_db_filepath}.")
    
    final_db_save_start_time = time.time()
    combined_data.to_csv(current_db_filepath, index=False)
    perf_data_ref["final_db_save_duration_s"] = time.time() - final_db_save_start_time

    # Save the yfinance_skip_data at the end of processing all tickers
    if YFINANCE_SKIP_FILEPATH:
        try:
            # Ensure lists in yfinance_skip_data are sorted and unique
            for ticker_skip_key in yfinance_skip_data:
                if isinstance(yfinance_skip_data[ticker_skip_key], list):
                    yfinance_skip_data[ticker_skip_key] = sorted(list(set(yfinance_skip_data[ticker_skip_key])))
            with open(YFINANCE_SKIP_FILEPATH, 'w') as f_skip_save:
                json.dump(yfinance_skip_data, f_skip_save, indent=4)
            logger.log(f"✅ Saved updated yfinance skip data to {YFINANCE_SKIP_FILEPATH}")
        except Exception as e_skip_save:
            logger.log(f"⚠️ Error saving yfinance skip data to {YFINANCE_SKIP_FILEPATH}: {e_skip_save}")

    status_update["current_ticker"] = f"StockDataDB.csv saved ({len(combined_data)} rows)" # Update after save
    logger.update_web_log("ticker_download", status_update)
    logger.log(f"✅ Updated {current_db_filepath} with {len(combined_data)} total unique rows.")
    if DEBUG_MODE:
        logger.log("DEBUG: Finished download_and_append function.")

def log_download_performance(perf_data, log_path, logger_instance):
    if not log_path:
        logger_instance.log("Warning: download_performance_log_path not defined. Skipping performance log.")
        return
    try:
        df = pd.DataFrame([perf_data]) # Create DataFrame from the single dict
        os.makedirs(os.path.dirname(log_path), exist_ok=True)
        file_exists = os.path.isfile(log_path)
        df.to_csv(log_path, mode='a', header=not file_exists, index=False)
        logger_instance.log(f"✅ Download performance data logged to: {log_path}")
    except Exception as e:
        logger_instance.log(f"❌ Error logging download performance to {log_path}: {e}")

def copy_log_to_web_accessible_location(source_csv_path, web_dest_folder, logger_instance, log_type="Performance"):
    if not source_csv_path or not os.path.exists(source_csv_path):
        logger_instance.log(f"Warning: Source {log_type} Log CSV not found at '{source_csv_path}'. Cannot copy.")
        return
    if not web_dest_folder:
        logger_instance.log(f"Warning: web_accessible_data_folder not set. Cannot copy {log_type} Log.")
        return
    try:
        os.makedirs(web_dest_folder, exist_ok=True)
        destination_csv_path = os.path.join(web_dest_folder, os.path.basename(source_csv_path))
        shutil.copy2(source_csv_path, destination_csv_path)
        logger_instance.log(f"✅ Copied {log_type} Log to web-accessible location: {destination_csv_path}")
    except Exception as e:
        logger_instance.log(f"❌ Error copying {log_type} Log to web directory: {e}")
# ----------------------------------------------------------- #
#                     Execution Pipeline                      #
# ----------------------------------------------------------- #

# --- Configuration Loading ---
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
PARAMETERS_FILE_PATH = os.path.join(SCRIPT_DIR, "downpar.txt")
overall_script_start_time_dt = datetime.now() # For overall script duration

overall_script_start_time_dt = datetime.now() # For overall script duration
performance_metrics = initialize_performance_data() # Initialize performance data dict

# Initialize preliminary logger
prelim_log_path = os.path.join(SCRIPT_DIR, "download_bootstrap.log")
logger = Logger(log_path=prelim_log_path, web_log_path=None) # No web log for bootstrap
logger.log(f"Logger initialized with preliminary path: {prelim_log_path}")
logger.log(f"Attempting to load parameters from: {PARAMETERS_FILE_PATH}")

param_load_start_time = time.time()
try:
    params = load_download_parameters(PARAMETERS_FILE_PATH, logger_instance=logger)
    performance_metrics["param_load_duration_s"] = time.time() - param_load_start_time
    logger.log(f"Successfully loaded parameters from: {PARAMETERS_FILE_PATH}")
except FileNotFoundError:
    logger.log(f"CRITICAL ERROR: Parameters file not found at '{PARAMETERS_FILE_PATH}'. Exiting.")
    exit(1) # Use exit(1) for error
except ValueError as ve: # Catch specific ValueError from load_download_parameters for missing critical params
    logger.log(f"CRITICAL ERROR: {ve}. Exiting.")
    exit(1)
except Exception as e:
    logger.log(f"CRITICAL ERROR: Failed to load parameters from '{PARAMETERS_FILE_PATH}'. Error: {e}. Exiting.")
    logger.flush() # Ensure error is written before exiting
    exit(1)

# Assign global variables from loaded parameters
DEBUG_MODE = params.get("debug_mode", False)
HISTORY_YEARS = params.get("history_years", 10)
FINDATA_DIR = params.get("findata_directory") # Critical, checked in load_download_parameters
FINDB_DIR = params.get("findb_directory")     # Critical
TICKERS_FILE = params.get("tickers_list_file") # Critical
DOWNLOAD_LOG_FILE = params.get("download_log_file") # Critical
PROGRESS_JSON_FILE = params.get("progress_json_file", os.path.join(SCRIPT_DIR, "progress.json")) # Default if not specified
DOWNLOAD_PERFORMANCE_LOG_PATH = params.get("download_performance_log_path") # Load performance log path
YFINANCE_SKIP_FILEPATH = params.get("yfinance_skip_filepath") # Load yfinance skip path
WEB_ACCESSIBLE_DATA_FOLDER = params.get("web_accessible_data_folder") # Load web data folder

DB_FILENAME = "StockDataDB.csv" # Standard name for the database file
DB_FILEPATH = os.path.join(FINDB_DIR, DB_FILENAME)

# Update logger with paths from parameters
logger.log_path = DOWNLOAD_LOG_FILE
logger.web_log_path = PROGRESS_JSON_FILE # Can be None if not in params
os.makedirs(os.path.dirname(DOWNLOAD_LOG_FILE), exist_ok=True)
if PROGRESS_JSON_FILE: # Only create dir if path is set
    os.makedirs(os.path.dirname(PROGRESS_JSON_FILE), exist_ok=True)
logger.log(f"Logger paths updated. Log file: {DOWNLOAD_LOG_FILE}, Web log: {PROGRESS_JSON_FILE if PROGRESS_JSON_FILE else 'None'}")
if DEBUG_MODE:
    logger.log(f"DEBUG: Final Parameters Loaded:")
    logger.log(f"DEBUG:   DEBUG_MODE = {DEBUG_MODE}")
    logger.log(f"DEBUG:   YFINANCE_SKIP_FILEPATH = {YFINANCE_SKIP_FILEPATH if YFINANCE_SKIP_FILEPATH else 'Not Set'}")
    logger.log(f"DEBUG:   HISTORY_YEARS = {HISTORY_YEARS}")
    logger.log(f"DEBUG:   DB_FILEPATH = {DB_FILEPATH}")

# --- Main Execution Block with Error Handling ---
try:
    # --- End Configuration Loading ---

    logger.log(f"🚀 Starting execution pipeline at: {overall_script_start_time_dt.strftime('%Y-%m-%d %H:%M:%S')}") # This is the primary log call for start
    performance_metrics["run_start_timestamp"] = overall_script_start_time_dt.strftime('%Y-%m-%d %H:%M:%S') # Re-confirm start time

    # Initial web log update for download status
    initial_ticker_download_status = {
        "completed_tickers": 0,
        "total_tickers": 0,
        "progress": 0,
        "current_ticker": "Initializing...",
        "overall_status": "Running", # Indicate download.py is now running
        "date_range": "N/A",
        "rows": 0
    } # This was the end of ticker_download
    initial_web_log_data = {
        "download_execution_start": overall_script_start_time_dt.strftime('%Y-%m-%d %H:%M:%S'),
        "ticker_download": initial_ticker_download_status,
        "download_execution_end": "N/A" # Explicitly set to N/A
    }
    logger.log("Download script initialized web progress.", web_data=initial_web_log_data)

    if DEBUG_MODE:
        logger.update_web_log("download_overall_status", "Initializing (Debug Mode)...")
        logger.log("DEBUG: Attempting to initialize UserAgent.")
    user_agent_setup_start_time = time.time()
    # Fetch dynamic user agents or use the fallback list
    try:
        from fake_useragent import UserAgent
        ua = UserAgent()
        USER_AGENTS = [ua.random for _ in range(50)]  # Generate 50 real agents
        logger.log(f"✅ Generated {len(USER_AGENTS)} dynamic user agents using fake-useragent.")
    except Exception as e:
        USER_AGENTS = FALLBACK_USER_AGENTS
        if DEBUG_MODE:
            logger.update_web_log("download_overall_status", "Initializing (UserAgent Fallback)...")
            logger.log(f"DEBUG: Failed to init UserAgent or generate dynamic agents: {e}. Using fallback.")
        logger.log(f"⚠️ Failed to generate dynamic user agents. Using fallback list. Reason: {e}")
    performance_metrics["user_agent_setup_duration_s"] = time.time() - user_agent_setup_start_time

    # Create a session
    session = requests.Session()

    # Configure retries for the session
    retry_strategy = Retry(
        total=3,  # Number of retries
        backoff_factor=1,  # Wait time between retries (exponential backoff)
        status_forcelist=[500, 502, 503, 504],  # Retry on these HTTP status codes
    )
    adapter = HTTPAdapter(max_retries=retry_strategy)
    session.mount("http://", adapter)
    session.mount("https://", adapter)
    if DEBUG_MODE:
        logger.log(f"DEBUG: Session created with retry strategy.")

    # --- Session Creation and Configuration ---
    # Moved here to be defined before download_and_append is called
    session = requests.Session()

    # Configure retries for the session
    retry_strategy = Retry(
        total=3,  # Number of retries
        backoff_factor=1,  # Wait time between retries (exponential backoff)
        status_forcelist=[500, 502, 503, 504],  # Retry on these HTTP status codes
    )
    adapter = HTTPAdapter(max_retries=retry_strategy)
    session.mount("http://", adapter)
    session.mount("https://", adapter)
    logger.log("✅ HTTP session created and configured with retry strategy.")

    logger.update_web_log("download_overall_status", "Reading Tickers List...")
    if DEBUG_MODE:
        logger.log(f"DEBUG: Reading tickers from: {TICKERS_FILE}")
    tickers_to_download = read_tickers_from_file(TICKERS_FILE)
    if not tickers_to_download:
        logger.update_web_log("download_overall_status", "Failed (No Tickers)")
        logger.log("⚠️ No tickers found in the Tickers.txt file. Exiting.")
        # Update web log to indicate failure or no tickers
        failed_ticker_status = {
            "completed_tickers": 0,
            "total_tickers": 0,
            "progress": 0,
            "current_ticker": "No tickers found in file",
            "date_range": "N/A",
            "rows": 0
        }
        logger.update_web_log("ticker_download", failed_ticker_status)
        logger.update_web_log("download_execution_end", datetime.now().strftime('%Y-%m-%d %H:%M:%S'))
        logger.flush()
        exit(1)

    # Update total_tickers in web log now that we have the list
    # Ensure "ticker_download" key exists from initial_web_log_data merge
    current_ticker_status = logger.web_data.get("ticker_download", initial_ticker_download_status).copy()
    current_ticker_status["total_tickers"] = len(tickers_to_download)
    current_ticker_status["overall_status"] = "Running" # Confirm running status
    current_ticker_status["current_ticker"] = "Preparing to process findata..."
    logger.update_web_log("download_overall_status", "Processing Local Data...")
    logger.update_web_log("ticker_download", current_ticker_status)

    if DEBUG_MODE:
        logger.log(f"DEBUG: Found {len(tickers_to_download)} tickers to process. Calling download_and_append.")

    # Load yfinance skip data before calling download_and_append
    current_yfinance_skip_data = {}
    if YFINANCE_SKIP_FILEPATH and os.path.exists(YFINANCE_SKIP_FILEPATH):
        try:
            with open(YFINANCE_SKIP_FILEPATH, 'r') as f_skip_load:
                current_yfinance_skip_data = json.load(f_skip_load)
            logger.log(f"✅ Loaded yfinance skip data from {YFINANCE_SKIP_FILEPATH} with {len(current_yfinance_skip_data)} tickers.")
        except Exception as e_skip_load:
            logger.log(f"⚠️ Error loading yfinance skip data from {YFINANCE_SKIP_FILEPATH}: {e_skip_load}. Starting with empty skip data.")

    logger.update_web_log("download_overall_status", "Downloading Data...")
    download_and_append(tickers_to_download, FINDATA_DIR, FINDB_DIR, DB_FILEPATH, performance_metrics, current_yfinance_skip_data)

    overall_script_end_time_dt = datetime.now()
    total_script_duration = overall_script_end_time_dt - overall_script_start_time_dt
    performance_metrics["overall_script_duration_s"] = total_script_duration.total_seconds()

    logger.log(f"✅ Execution completed at: {overall_script_end_time_dt.strftime('%Y-%m-%d %H:%M:%S')} in {total_script_duration}")
    logger.update_web_log("download_overall_status", "Completed")

    # Final update for ticker_download status upon successful completion
    final_ticker_download_status = logger.web_data.get("ticker_download", {}).copy() # Get current state
    final_ticker_download_status["overall_status"] = "Completed"
    final_ticker_download_status["current_ticker"] = "Download completed"
    final_ticker_download_status["completed_tickers"] = len(tickers_to_download)
    final_ticker_download_status["total_tickers"] = len(tickers_to_download)
    final_ticker_download_status["progress"] = 100
    logger.update_web_log("ticker_download", final_ticker_download_status)

    logger.update_web_log("download_execution_end", overall_script_end_time_dt.strftime('%Y-%m-%d %H:%M:%S')) # Mark end time

    # Log performance data to CSV and copy
    log_download_performance(performance_metrics, DOWNLOAD_PERFORMANCE_LOG_PATH, logger)
    copy_log_to_web_accessible_location(DOWNLOAD_PERFORMANCE_LOG_PATH, WEB_ACCESSIBLE_DATA_FOLDER, logger, "Download Performance")

except Exception as e:
    # Catch any unhandled exceptions in the main execution block
    logger.log(f"CRITICAL ERROR: Unhandled exception during Download.py execution: {e}", web_data={"download_overall_status": "Failed"})
    import traceback
    logger.log(f"Traceback:\n{traceback.format_exc()}")
    # The script will now exit with a non-zero status due to the unhandled exception
logger.flush() # Final flush