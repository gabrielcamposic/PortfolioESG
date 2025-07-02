#!/home/gabrielcampos/.pyenv/versions/env-fa/bin/python

# --- Script Version ---
SCORING_PY_VERSION = "2.2.0" # Added Momentum factor and 3-way dynamic weighting.
# ----------------------

# ----------------------------------------------------------- #
#                           Libraries                         #
# ----------------------------------------------------------- #
import pandas as pd
import numpy as np
import os
import sys
import json
from datetime import datetime

# ----------------------------------------------------------- #
#                       Global variables                      #
# ----------------------------------------------------------- #

# These will be populated by load_scoring_parameters
DEBUG_MODE = False
STOCK_DATA_FILE = ""
FINANCIALS_DB_FILE = ""
INPUT_STOCKS_FILE = ""
SCORED_STOCKS_OUTPUT_FILE = ""
RISK_FREE_RATE = 0.15
LOG_FILE_PATH = ""
SHARPE_WEIGHT = 0.6
UPSIDE_WEIGHT = 0.4
WEB_LOG_PATH = ""
DYNAMIC_SCORE_WEIGHTING = False
MOMENTUM_ENABLED = False
MOMENTUM_PERIOD_DAYS = 126
MOMENTUM_WEIGHT = 0.0

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
        "debug_mode": bool, "risk_free_rate": float, "dynamic_score_weighting": bool, "momentum_enabled": bool,
        "stock_data_file": str, "input_stocks_file": str,
        "financials_db_file": str, "scored_stocks_output_file": str, "log_file_path": str, "web_log_path": str, 
        "sharpe_weight": float, "upside_weight": float, "momentum_weight": float, "sector_pe_log_path": str, "momentum_period_days": int
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

def load_input_stocks_with_sectors(filepath, logger_instance):
    """
    Loads tickers, sectors, and industries from the input CSV file.
    Handles comments, blank lines, and ensures 'Stock' column for merging.
    Returns a pandas DataFrame.
    """
    try:
        # Use pandas to easily read CSV, skipping comments and blank lines
        stocks_df = pd.read_csv(
            filepath,
            header=None,
            names=['Ticker', 'Sector', 'Industry'],
            comment='#',
            skip_blank_lines=True,
            sep=','
        )
        # Strip whitespace from all string columns
        for col in stocks_df.select_dtypes(['object']):
            stocks_df[col] = stocks_df[col].str.strip()
        
        # Drop rows where Ticker is missing and remove duplicates
        stocks_df.dropna(subset=['Ticker'], inplace=True)
        stocks_df.drop_duplicates(subset=['Ticker'], keep='first', inplace=True)
        
        # Rename 'Ticker' to 'Stock' to match other dataframes
        stocks_df.rename(columns={'Ticker': 'Stock'}, inplace=True)

        logger_instance.log(f"Loaded {len(stocks_df)} unique stocks with sector/industry data from {filepath}")
        return stocks_df
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
    global RISK_FREE_RATE, LOG_FILE_PATH, WEB_LOG_PATH, SHARPE_WEIGHT, UPSIDE_WEIGHT, SECTOR_PE_LOG_PATH, DYNAMIC_SCORE_WEIGHTING, MOMENTUM_ENABLED, MOMENTUM_PERIOD_DAYS, MOMENTUM_WEIGHT
    
    DEBUG_MODE = params.get("debug_mode", False)
    STOCK_DATA_FILE = params.get("stock_data_file")
    FINANCIALS_DB_FILE = params.get("financials_db_file")
    INPUT_STOCKS_FILE = params.get("input_stocks_file")
    SCORED_STOCKS_OUTPUT_FILE = params.get("scored_stocks_output_file")
    RISK_FREE_RATE = params.get("risk_free_rate", 0.0)
    LOG_FILE_PATH = params.get("log_file_path")
    SHARPE_WEIGHT = params.get("sharpe_weight", 0.6)
    UPSIDE_WEIGHT = params.get("upside_weight", 0.4)
    WEB_LOG_PATH = params.get("web_log_path")
    SECTOR_PE_LOG_PATH = params.get("sector_pe_log_path")
    DYNAMIC_SCORE_WEIGHTING = params.get("dynamic_score_weighting", False)
    MOMENTUM_ENABLED = params.get("momentum_enabled", False)
    MOMENTUM_PERIOD_DAYS = params.get("momentum_period_days", 126)
    MOMENTUM_WEIGHT = params.get("momentum_weight", 0.0)

    # Validate that weights sum to 1.0, only if not using dynamic weighting
    total_static_weight = SHARPE_WEIGHT + UPSIDE_WEIGHT + (MOMENTUM_WEIGHT if MOMENTUM_ENABLED else 0)
    if not DYNAMIC_SCORE_WEIGHTING and not np.isclose(total_static_weight, 1.0):
        logger.log(f"CRITICAL: Static score weights do not sum to 1.0 (Total: {total_static_weight}). Exiting.")
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
        stocks_with_sectors_df = load_input_stocks_with_sectors(INPUT_STOCKS_FILE, logger)
        tickers = stocks_with_sectors_df['Stock'].tolist() if not stocks_with_sectors_df.empty else []
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

        # --- New: Calculate Momentum ---
        if MOMENTUM_ENABLED:
            logger.log(f"Calculating {MOMENTUM_PERIOD_DAYS}-day momentum...")
            if len(daily_returns) >= MOMENTUM_PERIOD_DAYS:
                momentum = daily_returns.tail(MOMENTUM_PERIOD_DAYS).sum().rename('Momentum')
                results_df = pd.merge(results_df, momentum, on='Stock', how='left')
            else:
                logger.log(f"Warning: Not enough historical data ({len(daily_returns)} days) to calculate {MOMENTUM_PERIOD_DAYS}-day momentum. Skipping.")
                results_df['Momentum'] = np.nan

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

        # 4b. Merge with sector and industry data (moved earlier to be available for P/E calculation)
        logger.log("Merging sector and industry data...")
        if not stocks_with_sectors_df.empty:
            results_df = pd.merge(results_df, stocks_with_sectors_df, on='Stock', how='left')
            # Fill any potential NaNs in Sector/Industry for stocks that might be in results_df but not Tickers.txt
            results_df[['Sector', 'Industry']] = results_df[['Sector', 'Industry']].fillna('N/A')
        else:
            results_df['Sector'] = 'N/A'
            results_df['Industry'] = 'N/A'

        # 4b. Calculate Risk-Adjusted Upside Score
        logger.log("Calculating Risk-Adjusted Upside Score...")

        # --- New: Calculate Target Price using Sector Median Forward P/E ---
        logger.log("Calculating target price using sector median Forward P/E.")
        # Calculate median P/E for each sector, using only positive P/E values
        sector_median_pe = results_df[results_df['forwardPE'] > 0].groupby('Sector')['forwardPE'].median().rename('SectorMedianPE')
        
        if DEBUG_MODE and not sector_median_pe.empty:
            logger.log(f"DEBUG: Calculated Sector Median P/Es:\n{sector_median_pe.to_string()}")

        # --- New: Log Sector Median P/E to CSV ---
        if SECTOR_PE_LOG_PATH and not sector_median_pe.empty:
            try:
                sector_pe_df = sector_median_pe.reset_index()
                sector_pe_df.columns = ['Sector', 'MedianForwardPE']
                sector_pe_df['run_id'] = run_id
                sector_pe_df['run_timestamp'] = start_time.strftime('%Y-%m-%d %H:%M:%S')
                
                os.makedirs(os.path.dirname(SECTOR_PE_LOG_PATH), exist_ok=True)
                file_exists = os.path.isfile(SECTOR_PE_LOG_PATH)
                sector_pe_df.to_csv(SECTOR_PE_LOG_PATH, mode='a', header=not file_exists, index=False)
                logger.log(f"✅ Sector median P/E data logged to {os.path.basename(SECTOR_PE_LOG_PATH)}")
            except Exception as e:
                logger.log(f"Warning: Could not log sector median P/E data. Error: {e}")

        # Merge the calculated sector median P/E back into the main dataframe
        results_df = pd.merge(results_df, sector_median_pe, on='Sector', how='left')

        # Calculate Target Price using the stock's Forward EPS and its sector's median P/E
        results_df['TargetPrice'] = results_df['forwardEps'] * results_df['SectorMedianPE']

        results_df['PotentialUpside_pct'] = ((results_df['TargetPrice'] - results_df['CurrentPrice']) / results_df['CurrentPrice']).replace([np.inf, -np.inf], np.nan)

        # --- Data Availability Check ---
        missing_upside = results_df['PotentialUpside_pct'].isna().sum()
        if missing_upside > 0:
            logger.log(f"Info: Potential Upside could not be calculated for {missing_upside} of {len(results_df)} stocks due to missing data (e.g., missing EPS or no valid P/E in sector).")
            if DEBUG_MODE:
                missing_tickers = results_df[results_df['PotentialUpside_pct'].isna()]['Stock'].tolist()
                logger.log(f"  - Affected Tickers (sample): {', '.join(missing_tickers[:10])}{'...' if len(missing_tickers) > 10 else ''}")

        # 4c. Normalize metrics and compute final score
        results_df['SharpeRatio_norm'] = normalize_series(results_df['SharpeRatio'])
        results_df['PotentialUpside_pct_norm'] = normalize_series(results_df['PotentialUpside_pct'])
        if MOMENTUM_ENABLED:
            results_df['Momentum_norm'] = normalize_series(results_df['Momentum'])

        # --- Dynamic/Static Weight Calculation ---
        if DYNAMIC_SCORE_WEIGHTING:
            logger.log("Calculating dynamic score weights based on variance...")
            var_sharpe = results_df['SharpeRatio_norm'].var()
            var_upside = results_df['PotentialUpside_pct_norm'].var()
            var_momentum = results_df['Momentum_norm'].var() if MOMENTUM_ENABLED and 'Momentum_norm' in results_df else 0
            total_var = var_sharpe + var_upside + var_momentum

            if total_var > 0:
                sharpe_weight_used = var_sharpe / total_var
                upside_weight_used = var_upside / total_var
                momentum_weight_used = var_momentum / total_var if MOMENTUM_ENABLED else 0.0
            else:
                logger.log("Warning: Total variance of normalized scores is zero. Falling back to equal weights.")
                num_factors = 2 + (1 if MOMENTUM_ENABLED and 'Momentum_norm' in results_df else 0)
                sharpe_weight_used = 1 / num_factors
                upside_weight_used = 1 / num_factors
                momentum_weight_used = 1 / num_factors if MOMENTUM_ENABLED and 'Momentum_norm' in results_df else 0.0
            
            log_msg = f"Dynamic weights calculated: Sharpe={sharpe_weight_used:.3f}, Upside={upside_weight_used:.3f}"
            if MOMENTUM_ENABLED: log_msg += f", Momentum={momentum_weight_used:.3f}"
            logger.log(log_msg)

        else:
            sharpe_weight_used = SHARPE_WEIGHT
            upside_weight_used = UPSIDE_WEIGHT
            momentum_weight_used = MOMENTUM_WEIGHT if MOMENTUM_ENABLED else 0.0
            log_msg = f"Using static score weights: Sharpe={sharpe_weight_used}, Upside={upside_weight_used}"
            if MOMENTUM_ENABLED: log_msg += f", Momentum={momentum_weight_used}"
            logger.log(log_msg)

        results_df['CompositeScore'] = (sharpe_weight_used * results_df['SharpeRatio_norm']) + (upside_weight_used * results_df['PotentialUpside_pct_norm'])
        if MOMENTUM_ENABLED and 'Momentum_norm' in results_df:
            results_df['CompositeScore'] += (momentum_weight_used * results_df['Momentum_norm'])
        logger.log("Composite scoring complete.")

        # --- Add weights and audit columns to DataFrame ---
        results_df['run_id'] = run_id
        results_df['run_timestamp'] = start_time.strftime('%Y-%m-%d %H:%M:%S')
        results_df['scoring_version'] = SCORING_PY_VERSION
        results_df['sharpe_weight_used'] = sharpe_weight_used
        results_df['upside_weight_used'] = upside_weight_used
        if MOMENTUM_ENABLED:
            results_df['momentum_weight_used'] = momentum_weight_used

        # Sort by the new CompositeScore (higher is better)
        results_df.sort_values(by=['CompositeScore'], ascending=False, inplace=True)
        
        # --- Reorder columns for readability before saving ---
        final_column_order = [
            'run_id', 'run_timestamp', 'scoring_version', 'Stock', 'Sector', 'Industry',
            'CompositeScore', 'SharpeRatio', 'PotentialUpside_pct', 'Momentum',
            'SharpeRatio_norm', 'PotentialUpside_pct_norm', 'Momentum_norm',
            'sharpe_weight_used', 'upside_weight_used', 'momentum_weight_used',
            'AnnualizedMeanReturn', 'AnnualizedStdDev', 'CurrentPrice', 'TargetPrice',
            'forwardPE', 'forwardEps', 'SectorMedianPE'
        ]
        existing_columns = [col for col in final_column_order if col in results_df.columns]
        results_df = results_df[existing_columns]

        # 5. Save Results
        logger.log(f"Saving all {len(results_df)} scored stocks...")
        
        # Append the top stocks for this run to the historical scored runs database
        if SCORED_STOCKS_OUTPUT_FILE:
            os.makedirs(os.path.dirname(SCORED_STOCKS_OUTPUT_FILE), exist_ok=True)
            file_exists = os.path.isfile(SCORED_STOCKS_OUTPUT_FILE)

            if file_exists:
                try:
                    # Load the existing data to merge with it
                    existing_df = pd.read_csv(SCORED_STOCKS_OUTPUT_FILE)
                    # Concatenate old and new data. This handles schema changes by creating a superset of columns.
                    combined_df = pd.concat([existing_df, results_df], ignore_index=True)
                    # Overwrite the file with the combined data
                    combined_df.to_csv(SCORED_STOCKS_OUTPUT_FILE, index=False)
                    logger.log(f"Appended new run and updated schema in {os.path.basename(SCORED_STOCKS_OUTPUT_FILE)}")
                except Exception as e:
                    logger.log(f"CRITICAL: Could not read or merge with existing file '{os.path.basename(SCORED_STOCKS_OUTPUT_FILE)}' (Error: {e}). Aborting.")
                    sys.exit(1)
            else:
                # If the file doesn't exist, create it with the current run's data
                results_df.to_csv(SCORED_STOCKS_OUTPUT_FILE, index=False)
                logger.log(f"Created new scored runs file: {os.path.basename(SCORED_STOCKS_OUTPUT_FILE)}")
            logger.log(f"✅ All {len(results_df)} scored stocks for run_id {run_id} saved to {SCORED_STOCKS_OUTPUT_FILE}")

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
