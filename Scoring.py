#!/home/gabrielcampos/.pyenv/versions/env-fa/bin/python
# ----------------------------------------------------------- #
#                           Libraries                         #
# ----------------------------------------------------------- #
import pandas as pd
import numpy as np
import os
import sys
import json
from datetime import datetime

# --- Script Version ---
SCORING_PY_VERSION = "1.0.0"
# ----------------------

# ----------------------------------------------------------- #
#                       Global variables                      #
# ----------------------------------------------------------- #

# These will be populated by load_scoring_parameters
DEBUG_MODE = False
STOCK_DATA_FILE = ""
FINANCIALS_DB_FILE = ""
INPUT_STOCKS_FILE = ""
SCORED_STOCKS_OUTPUT_FILE = ""
SCORED_RESULTS_CSV_PATH = ""
TOP_N_STOCKS = 20
RISK_FREE_RATE = 0.0
LOG_FILE_PATH = ""
SHARPE_WEIGHT = 0.6
UPSIDE_WEIGHT = 0.4
WEB_LOG_PATH = ""

# ----------------------------------------------------------- #
#                           Classes                           #
# ----------------------------------------------------------- #

class Logger:
    def __init__(self, log_path, flush_interval=10, web_log_path=None):
        self.log_path = log_path
        self.web_log_path = web_log_path
        self.messages = []
        self.flush_interval = flush_interval
        self.log_count = 0

    def log(self, message, web_data=None):
        timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        log_entry = f"{timestamp} - {message}"
        print(log_entry)
        self.messages.append(log_entry)
        self.log_count += 1

        if web_data and self.web_log_path:
            loaded_json_data = {}
            if os.path.exists(self.web_log_path):
                try:
                    with open(self.web_log_path, 'r') as f_read:
                        loaded_json_data = json.load(f_read)
                except (json.JSONDecodeError, Exception) as e:
                    print(f"{timestamp} - Warning: Could not read web log at {self.web_log_path}. Error: {e}")
            
            loaded_json_data.update(web_data)
            
            try:
                with open(self.web_log_path, 'w') as web_file:
                    json.dump(loaded_json_data, web_file, indent=4)
            except Exception as e:
                print(f"{timestamp} - Error writing to web log file {self.web_log_path}: {e}")

        if self.log_count % self.flush_interval == 0:
            self.flush()

    def flush(self):
        if self.messages:
            with open(self.log_path, 'a') as file:
                file.write("\n".join(self.messages) + "\n")
            self.messages = []

    def update_web_log(self, key, value):
        if self.web_log_path:
            loaded_json_data = {}
            if os.path.exists(self.web_log_path):
                try:
                    with open(self.web_log_path, 'r') as f_read:
                        loaded_json_data = json.load(f_read)
                except (json.JSONDecodeError, Exception) as e:
                    print(f"Warning: Could not read web log for update at {self.web_log_path}. Error: {e}")
            
            loaded_json_data[key] = value
            
            try:
                with open(self.web_log_path, 'w') as web_file:
                    json.dump(loaded_json_data, web_file, indent=4)
            except Exception as e:
                print(f"Error updating web log file {self.web_log_path}: {e}")

# ----------------------------------------------------------- #
#                        Basic Functions                      #
# ----------------------------------------------------------- #

def load_scoring_parameters(filepath, logger_instance=None):
    parameters = {}
    expected_types = {
        "debug_mode": bool, "top_n_stocks": int, "risk_free_rate": float,
        "stock_data_file": str, "input_stocks_file": str,
        "financials_db_file": str, "scored_stocks_output_file": str, "log_file_path": str, "web_log_path": str, "sharpe_weight": float, "upside_weight": float,
        "scored_results_csv_path": str
    }
    try:
        with open(filepath, 'r') as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith('#'): continue
                key, value_str = line.split('=', 1)
                key, value_str = key.strip(), value_str.strip()
                if key in expected_types:
                    target_type = expected_types[key]
                    try:
                        if target_type == bool: value = value_str.lower() == 'true'
                        elif target_type == int: value = int(value_str)
                        elif target_type == float: value = float(value_str)
                        else: value = os.path.expanduser(value_str) if value_str.startswith('~') else value_str
                        parameters[key] = value
                    except ValueError:
                        if logger_instance: logger_instance.log(f"Warning: Could not convert '{value_str}' for key '{key}'. Storing as string.")
                        parameters[key] = value_str
    except FileNotFoundError:
        if logger_instance: logger_instance.log(f"CRITICAL: Parameters file '{filepath}' not found.")
        raise
    return parameters

def load_input_stocks(filepath, logger_instance):
    try:
        with open(filepath, 'r') as f:
            # Read all lines, split by comma on each line, and flatten the list
            tickers = []
            for line in f:
                tickers.extend([ticker.strip() for ticker in line.split(',') if ticker.strip()])
        # Remove duplicates and sort for consistency
        tickers = sorted(list(set(tickers)))
        logger_instance.log(f"Loaded {len(tickers)} unique tickers from {filepath}")
        return tickers
    except FileNotFoundError:
        logger_instance.log(f"CRITICAL: Input stocks file not found at '{filepath}'.")
        raise

def calculate_individual_sharpe_ratios(stock_daily_returns, risk_free_rate):
    """Calculates Sharpe Ratio and its components for each stock."""
    annualized_mean_returns = stock_daily_returns.mean() * 252
    annualized_std_devs = stock_daily_returns.std() * np.sqrt(252)
    # Replace 0 std_devs with NaN to avoid division by zero, then fill resulting NaNs
    sharpe_ratios = (annualized_mean_returns - risk_free_rate) / annualized_std_devs.replace(0, np.nan)
    sharpe_ratios = sharpe_ratios.fillna(0)

    # Create a DataFrame with all metrics
    results_df = pd.DataFrame({
        'AnnualizedMeanReturn': annualized_mean_returns,
        'AnnualizedStdDev': annualized_std_devs,
        'SharpeRatio': sharpe_ratios
    })
    return results_df.reset_index() # The stock ticker is in the index, reset_index makes it a column

def load_financials_data(filepath, logger_instance):
    """
    Loads historical financial data from the CSV file, then returns only the
    most recent entry for each stock.
    """
    try:
        logger_instance.log(f"Loading financial data from {filepath}...")
        financials_df = pd.read_csv(filepath)
        # Ensure LastUpdated is a datetime object to sort correctly
        financials_df['LastUpdated'] = pd.to_datetime(financials_df['LastUpdated'])
        # Sort by stock and date, then take the last (most recent) entry for each stock
        latest_financials = financials_df.sort_values('LastUpdated').drop_duplicates(subset='Stock', keep='last')
        logger_instance.log(f"Successfully loaded and found latest financial data for {len(latest_financials)} stocks.")
        return latest_financials[['Stock', 'forwardPE', 'forwardEps']]
    except FileNotFoundError:
        logger_instance.log(f"Warning: Financials data file not found at '{filepath}'. Scoring will proceed without P/E data.")
        return pd.DataFrame(columns=['Stock', 'forwardPE', 'forwardEps']) # Return empty df with correct columns

def normalize_series(column):
    """Normalizes a pandas Series to a 0-1 scale using Min-Max scaling."""
    # Check if column has variance to avoid division by zero
    if pd.isna(column).all() or column.max() == column.min():
        # Return a neutral value (0.5) if all are NaN or all values are the same
        return pd.Series(0.5, index=column.index)
    
    normalized = (column - column.min()) / (column.max() - column.min())
    return normalized.fillna(0) # Fill any remaining NaNs with 0 after normalization

# ----------------------------------------------------------- #
#                     Execution Pipeline                      #
# ----------------------------------------------------------- #

def main():
    """Main execution function for the scoring script."""
    # --- Configuration Loading ---
    script_dir = os.path.dirname(os.path.abspath(__file__))
    parameters_file_path = os.path.join(script_dir, "scorepar.txt")
    
    # Initialize preliminary logger
    prelim_log_path = os.path.join(script_dir, "scoring_bootstrap.log")
    logger = Logger(log_path=prelim_log_path)
    logger.log(f"Scoring script v{SCORING_PY_VERSION} started.")
    logger.log(f"Attempting to load parameters from: {parameters_file_path}")

    try:
        params = load_scoring_parameters(parameters_file_path, logger)
        logger.log("Successfully loaded parameters.")
    except FileNotFoundError:
        logger.log(f"CRITICAL: Parameters file not found at '{parameters_file_path}'. Exiting.")
        sys.exit(1)

    # Assign global variables from loaded parameters
    global DEBUG_MODE, STOCK_DATA_FILE, FINANCIALS_DB_FILE, INPUT_STOCKS_FILE, SCORED_STOCKS_OUTPUT_FILE
    global SCORED_RESULTS_CSV_PATH, TOP_N_STOCKS, RISK_FREE_RATE, LOG_FILE_PATH, WEB_LOG_PATH, SHARPE_WEIGHT, UPSIDE_WEIGHT
    
    DEBUG_MODE = params.get("debug_mode", False)
    STOCK_DATA_FILE = params.get("stock_data_file")
    FINANCIALS_DB_FILE = params.get("financials_db_file")
    INPUT_STOCKS_FILE = params.get("input_stocks_file")
    SCORED_STOCKS_OUTPUT_FILE = params.get("scored_stocks_output_file")
    SCORED_RESULTS_CSV_PATH = params.get("scored_results_csv_path")
    TOP_N_STOCKS = params.get("top_n_stocks", 20)
    RISK_FREE_RATE = params.get("risk_free_rate", 0.0)
    LOG_FILE_PATH = params.get("log_file_path")
    SHARPE_WEIGHT = params.get("sharpe_weight", 0.6)
    UPSIDE_WEIGHT = params.get("upside_weight", 0.4)
    WEB_LOG_PATH = params.get("web_log_path")

    # Validate that weights sum to 1.0
    if not np.isclose(SHARPE_WEIGHT + UPSIDE_WEIGHT, 1.0):
        logger.log(f"CRITICAL: Score weights do not sum to 1.0 (sharpe_weight={SHARPE_WEIGHT}, upside_weight={UPSIDE_WEIGHT}). Exiting.")
        sys.exit(1)

    # Update logger with paths from parameters
    if LOG_FILE_PATH:
        logger.log_path = LOG_FILE_PATH
        os.makedirs(os.path.dirname(LOG_FILE_PATH), exist_ok=True)
    if WEB_LOG_PATH:
        logger.web_log_path = WEB_LOG_PATH
        os.makedirs(os.path.dirname(WEB_LOG_PATH), exist_ok=True)
    logger.log("Logger paths updated from parameters.")
    
    start_time = datetime.now()
    run_id = start_time.strftime('%Y%m%d_%H%M%S')
    logger.log(f"🚀 Scoring execution started at: {start_time.strftime('%Y-%m-%d %H:%M:%S')}", 
               web_data={"scoring_status": "Running", "scoring_start_time": start_time.strftime('%Y-%m-%d %H:%M:%S')})

    try:
        # 1. Load Input Stocks
        tickers = load_input_stocks(INPUT_STOCKS_FILE, logger)
        if not tickers:
            logger.log("No tickers loaded. Exiting.", web_data={"scoring_status": "Failed - No Tickers"})
            sys.exit(1)

        # 2. Load Historical Data and Calculate Sharpe
        logger.log(f"Loading historical data from {STOCK_DATA_FILE}...")
        all_data_df = pd.read_csv(STOCK_DATA_FILE)
        all_data_df['Date'] = pd.to_datetime(all_data_df['Date'], format='mixed', errors='coerce').dt.date
        filtered_df = all_data_df[all_data_df['Stock'].isin(tickers)]
        close_prices_df = filtered_df.pivot(index='Date', columns='Stock', values='Close')

        # Calculate daily returns for each stock individually.
        # pct_change handles NaNs by propagating them, which is fine for individual calculations.
        # The .mean() and .std() functions used later will ignore these NaNs by default.
        daily_returns = close_prices_df.pct_change(fill_method=None)

        # Check if we have enough data to proceed after calculating returns.
        # The first row of pct_change is always NaN, so we need at least 2 valid rows in the original data.
        if daily_returns.empty or len(daily_returns.dropna(how='all')) < 2:
            logger.log("CRITICAL: Not enough historical data to calculate returns for any stock. Please check StockDataDB.csv.", web_data={"scoring_status": "Failed - Insufficient Data"})
            sys.exit(1)
        logger.log(f"Successfully pivoted data and calculated daily returns for {len(tickers)} tickers.")
        
        logger.log("Calculating Sharpe Ratios...")
        results_df = calculate_individual_sharpe_ratios(daily_returns, RISK_FREE_RATE)

        # Add a check to ensure some stocks were processed
        if results_df.empty:
            logger.log("CRITICAL: No valid tickers were found in the historical data, or no returns could be calculated. The results will be empty. Please check your Tickers.txt and StockDataDB.csv.", 
                       web_data={"scoring_status": "Failed - No Tickers Processed"})
            sys.exit(1)

        # 3. Load Financials (including Forward P/E) from file
        financials_df = load_financials_data(FINANCIALS_DB_FILE, logger)

        # 4. Merge and Score
        logger.log("Merging financial data and calculating scores...")
        if not financials_df.empty:
            results_df = pd.merge(results_df, financials_df, on='Stock', how='left')
        else:
            # Ensure columns exist even if financial fetch fails
            results_df['forwardPE'] = np.nan
            results_df['forwardEps'] = np.nan

        # 4a. Get latest closing price for each stock for upside calculation
        logger.log("Fetching latest prices for upside calculation...")
        latest_prices = close_prices_df.iloc[-1].rename('CurrentPrice')
        results_df = pd.merge(results_df, latest_prices.reset_index(), on='Stock', how='left')

        # 4b. Calculate Risk-Adjusted Upside Score
        logger.log("Calculating Risk-Adjusted Upside Score...")
        # Use median for benchmark P/E as it's more robust to outliers
        reasonable_pe = results_df['forwardPE'][(results_df['forwardPE'] > 0) & (results_df['forwardPE'] < 100)]
        benchmark_pe = reasonable_pe.median() if not reasonable_pe.empty else 20.0 # Fallback benchmark
        logger.log(f"Using a benchmark P/E of {benchmark_pe:.2f} for target price calculation.")

        results_df['TargetPrice'] = results_df['forwardEps'] * benchmark_pe
        results_df['PotentialUpside_pct'] = ((results_df['TargetPrice'] - results_df['CurrentPrice']) / results_df['CurrentPrice']).replace([np.inf, -np.inf], np.nan)

        # 4c. Normalize metrics and compute final score
        results_df['SharpeRatio_norm'] = normalize_series(results_df['SharpeRatio'])
        results_df['PotentialUpside_pct_norm'] = normalize_series(results_df['PotentialUpside_pct'])

        # Calculate final composite score using weights from parameters
        results_df['CompositeScore'] = (SHARPE_WEIGHT * results_df['SharpeRatio_norm']) + \
                                       (UPSIDE_WEIGHT * results_df['PotentialUpside_pct_norm'])
        logger.log("Composite scoring complete.")

        # Add run_id and timestamp for auditability
        results_df['run_id'] = run_id
        results_df['run_timestamp'] = start_time.strftime('%Y-%m-%d %H:%M:%S')

        # Sort by the new CompositeScore (higher is better)
        results_df.sort_values(by=['CompositeScore'], ascending=False, inplace=True)
        
        # 5. Save Results
        logger.log(f"Selecting top {TOP_N_STOCKS} stocks and saving results...")
        top_stocks_df = results_df.head(TOP_N_STOCKS)

        # Save the full results for this run to the main results CSV
        if SCORED_RESULTS_CSV_PATH:
            os.makedirs(os.path.dirname(SCORED_RESULTS_CSV_PATH), exist_ok=True)
            results_df.to_csv(SCORED_RESULTS_CSV_PATH, index=False)
            logger.log(f"Full scored results saved to {SCORED_RESULTS_CSV_PATH}")

        # Append the top stocks for this run to the historical scored runs database
        if SCORED_STOCKS_OUTPUT_FILE:
            os.makedirs(os.path.dirname(SCORED_STOCKS_OUTPUT_FILE), exist_ok=True)
            file_exists = os.path.isfile(SCORED_STOCKS_OUTPUT_FILE)

            # Schema validation: if file exists, check if headers match.
            if file_exists:
                try:
                    # Read only the header to avoid loading the whole file into memory.
                    existing_header = pd.read_csv(SCORED_STOCKS_OUTPUT_FILE, nrows=0).columns.tolist()
                    current_header = top_stocks_df.columns.tolist()

                    # If schemas don't match, abort to prevent corruption.
                    if set(existing_header) != set(current_header):
                        logger.log(f"CRITICAL: Schema of existing '{os.path.basename(SCORED_STOCKS_OUTPUT_FILE)}' does not match current output.")
                        logger.log("This is likely due to a code change. Please backup/rename the old file or use the cleanup utility.")
                        logger.log("Aborting to prevent data corruption.")
                        sys.exit(1)
                except Exception as e:
                    logger.log(f"CRITICAL: Could not validate schema of existing file (Error: {e}). Aborting.")
                    sys.exit(1)
            
            top_stocks_df.to_csv(SCORED_STOCKS_OUTPUT_FILE, mode='a', header=not file_exists, index=False)
            logger.log(f"✅ Top {TOP_N_STOCKS} stocks for run_id {run_id} appended to {SCORED_STOCKS_OUTPUT_FILE}")

        end_time = datetime.now()
        duration = end_time - start_time
        logger.log(f"✅ Scoring execution finished successfully in {duration}.", 
                   web_data={"scoring_status": "Completed", "scoring_end_time": end_time.strftime('%Y-%m-%d %H:%M:%S')})

    except Exception as e:
        end_time = datetime.now()
        logger.log(f"CRITICAL ERROR: An unhandled exception occurred: {e}", 
                   web_data={"scoring_status": "Failed", "scoring_end_time": end_time.strftime('%Y-%m-%d %H:%M:%S')})
        import traceback
        logger.log(f"Traceback:\n{traceback.format_exc()}")
        logger.flush()
        sys.exit(1)

    logger.flush()

if __name__ == "__main__":
    main()
