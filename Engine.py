# ----------------------------------------------------------- #
#                           Libraries                         #
# ----------------------------------------------------------- #
import pandas as pd
import numpy as np
import os
import random
import time
from datetime import datetime, timedelta
from math import comb  # Import combination function
import matplotlib.pyplot as plt
import itertools
import sys  # Import sys module for logging
import json # For logging to html readable

# ----------------------------------------------------------- #
#                           Classes                           #
# ----------------------------------------------------------- #

# -------- (I) Time tracking --------
class ExecutionTimer:
    def __init__(self, rolling_window=10):
        self.start_time = None
        self.total_time = 0
        self.run_count = 0
        self.avg_time = 0  # Rolling average execution time
        self.rolling_window = rolling_window  # Number of recent simulations to consider
        self.recent_times = []  # Store recent simulation times

    def start(self):
        """Start a new timing session."""
        if self.start_time is not None:
            raise RuntimeError("Timer is already running. Call stop() before starting again.")
        self.start_time = time.time()

    def stop(self):
        """Stop timing, update rolling average execution time."""
        if self.start_time is None:
            raise RuntimeError("Timer is not running. Call start() before stopping.")
        elapsed = time.time() - self.start_time
        self.start_time = None  # Reset start time

        # Update rolling average
        self.recent_times.append(elapsed)
        if len(self.recent_times) > self.rolling_window:
            self.recent_times.pop(0)  # Remove the oldest time to maintain the rolling window
        self.avg_time = sum(self.recent_times) / len(self.recent_times)
        self.total_time += elapsed # Accumulate total time of timed operations
        self.run_count += 1        # Increment the count of timed operations

        return elapsed

    def estimate_remaining(self, total_runs, completed_runs):
        """Estimate remaining time based on rolling average execution time."""
        if completed_runs == 0:
            return None  # Avoid division by zero
        remaining_runs = total_runs - completed_runs
        remaining_time = remaining_runs * self.avg_time
        return timedelta(seconds=remaining_time)

    def reset(self):
        """Reset the timer statistics."""
        self.start_time = None
        self.total_time = 0
        self.run_count = 0
        self.avg_time = 0
        self.recent_times = []

# -------- (II) Logging --------

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
        print(message)  # Console output
        self.messages.append(message)
        self.log_count += 1

        # Update web log file if web_data is provided
        if web_data and self.web_log_path:
            self.web_data.update(web_data)
            with open(self.web_log_path, 'w') as web_file:
                json.dump(self.web_data, web_file, indent=4)
                web_file.flush()            # Ensure data is flushed from buffer
                os.fsync(web_file.fileno()) # Force write to disk (good for web access)

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
            self.web_data[key] = value
            with open(self.web_log_path, 'w') as web_file:
                json.dump(self.web_data, web_file, indent=4)
                web_file.flush()
                os.fsync(web_file.fileno())

# ----------------------------------------------------------- #
#                        Basic Functions                      #
# ----------------------------------------------------------- #

def load_simulation_parameters(filepath, logger_instance=None):
    """
    Reads simulation parameters from the given file, converts to appropriate types,
    and expands paths.

    Args:
        filepath (str): The path to the parameters file.
        logger_instance (Logger, optional): An instance of the Logger class.

    Returns:
        dict: A dictionary containing the simulation parameters.

    Raises:
        FileNotFoundError: If the parameters file is not found.
        Exception: For other errors during file reading or parsing.
    """
    parameters = {}
    # Define expected types for known parameters to ensure correct conversion.
    expected_types = {
        "min_stocks": int,
        "max_stocks": int,
        "sim_runs": int,
        "initial_investment": float,
        "rf": float,
        "start_date": str,  # Keep as string; parse to datetime object later if needed
        "stock_data_file": str, # Added: recognize stock_data_file
        "esg_stocks_list": str, 
        "portfolio_folder": str,
        "charts_folder": str,
        "log_file_path": str,
        "web_log_path": str,
    }

    try:
        with open(filepath, 'r') as f:
            for line_number, line in enumerate(f, 1):
                line = line.strip()
                if not line or line.startswith('#'):  # Skip empty lines and comments
                    continue
                
                parts = line.split('=', 1)
                if len(parts) != 2:
                    message = f"Warning: Malformed line {line_number} in '{filepath}': '{line}'. Skipping."
                    if logger_instance:
                        logger_instance.log(message)
                    else:
                        print(message)
                    continue
                
                key, value_str = parts[0].strip(), parts[1].strip()

                # Handle the typo: stock_data_file' -> stock_data_file
                if key == "stock_data_file'":
                    message = (f"Info: Correcting key 'stock_data_file'' to 'stock_data_file' from '{filepath}'. "
                               "Consider fixing this typo in the file itself.")
                    if logger_instance:
                        logger_instance.log(message)
                    else:
                        print(message)
                    key = "stock_data_file"

                processed_value = None

                if key == "esg_stocks_list": # Match the intended parameter name (plural)
                    if value_str: # Ensure not empty string
                        processed_value = [stock.strip() for stock in value_str.split(',') if stock.strip()]
                    else:
                        processed_value = []  # Empty list for empty string
                    parameters[key] = processed_value # Assign the processed list
                    # Continue to next line in file, as this key is handled

                elif key in expected_types: # Check if key is a known, expected type
                    target_type = expected_types[key]
                    try:
                        if target_type == int:
                            processed_value = int(value_str)
                        elif target_type == float:
                            processed_value = float(value_str)
                        elif target_type == str:
                            # Expand user paths for string types
                            if value_str.startswith('~'):
                                processed_value = os.path.expanduser(value_str)
                            else:
                                processed_value = value_str
                        # Add other type conversions if needed (e.g., bool)
                        parameters[key] = processed_value
                    except ValueError:
                        message = (f"Warning: Could not convert value '{value_str}' for key '{key}' to {target_type.__name__} "
                                   f"in '{filepath}'. Using raw string value '{value_str}'.")
                        if logger_instance:
                            logger_instance.log(message)
                        else:
                            print(message)
                        parameters[key] = value_str  # Fallback to string

                else: # Truly unknown key
                    message = f"Warning: Unknown parameter key '{key}' found in '{filepath}'. Treating as string."
                    if logger_instance:
                        logger_instance.log(message)
                    else:
                        print(message)
                    if value_str.startswith('~'):
                        processed_value = os.path.expanduser(value_str)
                    else:
                        processed_value = value_str
                    parameters[key] = processed_value

    except FileNotFoundError:
        message = f"CRITICAL ERROR: Parameters file '{filepath}' not found. Cannot load simulation settings."
        if logger_instance:
            logger_instance.log(message)
        else:
            print(message)
        raise # Re-raise the exception to halt execution if params are critical
    except Exception as e:
        message = f"CRITICAL ERROR: Failed to read or parse parameters file '{filepath}': {e}"
        if logger_instance:
            logger_instance.log(message)
        else:
            print(message)
        raise # Re-raise for critical failure

    # Optional: Validate that all critical expected parameters are present
    # for p_key in expected_types:
    #     if p_key not in parameters:
    #         # Handle missing critical parameter (e.g., raise ValueError, use default, etc.)
    #         message = f"Warning: Expected critical parameter '{p_key}' not found in '{filepath}'."
    #         if logger_instance: logger_instance.log(message)
    #         else: print(message)

    return parameters

def calculate_individual_sharpe_ratios(stock_daily_returns, risk_free_rate):
    """
    Calculate the Sharpe Ratio for each stock individually.

    Args:
        stock_daily_returns (pd.DataFrame): DataFrame with daily returns for each stock.
                                            Assumes the first column might be 'Date' or an index
                                            and actual stock returns start from the second column.
        risk_free_rate (float): Risk-free rate as a decimal (e.g., 0.05 for 5%).

    Returns:
        pd.Series: Sharpe Ratios for each stock.
    """
    mean_returns = stock_daily_returns.mean() * 252 # Annualize mean daily returns
    std_devs = stock_daily_returns.std() * np.sqrt(252) # Annualize standard deviation of daily returns
    sharpe_ratios = (mean_returns - risk_free_rate) / std_devs # Risk-free rate should be annual
    return sharpe_ratios

# ----------------------------------------------------------- #
#                  Portfolio Analysis Functions               #
# ----------------------------------------------------------- #

def price_scaling(raw_prices_df):
    """Scales stock prices relative to their first available price."""
    scaled_prices_df = raw_prices_df.copy()
    for col in raw_prices_df.columns[1:]:  # Assumes Date is the first column
        first_price = raw_prices_df[col].iloc[0]
        if pd.isna(first_price) or first_price == 0:
            # Handle cases where first price is NaN or zero to avoid division errors
            # Option 1: Set scaled prices to NaN or 0
            scaled_prices_df[col] = np.nan # or 0
            # Option 2: Or skip scaling for this stock, keeping original values (or a copy)
            # scaled_prices_df[col] = raw_prices_df[col] # if you want to keep original values
        else:
            scaled_prices_df[col] = raw_prices_df[col] / first_price
    return scaled_prices_df

def generate_portfolio_weights(n, seed=None):
    """Generates random portfolio weights that sum to 1."""
    if seed is not None:
        np.random.seed(seed)
    weights = np.random.rand(n) # Use np.random.rand for [0,1)
    sum_weights = np.sum(weights)
    if sum_weights == 0:  # Highly unlikely, but handles division by zero
        return np.ones(n) / n  # Return equal weights
    return weights / sum_weights

def asset_allocation(df_subset, weights, current_initial_investment, logger_instance):
    """
    Computes portfolio allocation and daily returns for a given subset of stocks and weights.
    df_subset should contain 'Date' as the first column, followed by stock price columns.
    """
    try:
        portfolio_df = df_subset.copy()
        # scaled_df is used to calculate how many shares of each stock can be bought
        # and then to track the value of those shares over time.
        scaled_df = price_scaling(df_subset)

        if 'Date' not in scaled_df.columns:
            logger_instance.log("❌ ValueError in asset_allocation: The 'Date' column is missing from the scaled DataFrame.")
            # Or raise ValueError("The 'Date' column is missing from the scaled DataFrame.")
            return pd.DataFrame() # Return empty if error

        # Calculate the value of each stock holding over time
        for i, stock_col_name in enumerate(scaled_df.columns[1:]):  # Iterate over stock columns (skip 'Date')
            if i < len(weights): # Ensure we don't go out of bounds for weights
                portfolio_df[stock_col_name] = scaled_df[stock_col_name] * weights[i] * current_initial_investment
            else: # Should not happen if len(weights) == num_stocks
                logger_instance.log(f"Warning: Mismatch in number of stocks and weights in asset_allocation for {stock_col_name}")
                portfolio_df[stock_col_name] = 0

        # Summing only numeric columns, excluding 'Date' if it's not already numeric (it's date object)
        numeric_cols = portfolio_df.select_dtypes(include=[np.number]).columns
        portfolio_df['Portfolio Value [$]'] = portfolio_df[numeric_cols].sum(axis=1)
        portfolio_df['Portfolio Daily Return [%]'] = portfolio_df['Portfolio Value [$]'].pct_change() * 100
        portfolio_df.fillna(0, inplace=True) # Fill NaNs, e.g., for the first day's return
        return portfolio_df
    except Exception as e:
        logger_instance.log(f"❌ Error in asset_allocation: {e} for stocks {list(df_subset.columns[1:])}")
        return pd.DataFrame()

def simulation_engine_calc(
    stock_combo_prices_df,  # DataFrame with 'Date' and prices for the selected stock combo
    weights_list,
    current_initial_investment,
    current_rf_rate,  # Annual decimal risk-free rate
    logger_instance
):
    """Runs a simulation for a given portfolio allocation."""
    try:
        # Calculate portfolio value over time and daily returns of the portfolio
        portfolio_df = asset_allocation(stock_combo_prices_df, weights_list, current_initial_investment, logger_instance)

        if portfolio_df.empty or portfolio_df['Portfolio Value [$]'].iloc[0] == 0 : # Check if allocation failed or started with 0 value
            return np.nan, np.nan, np.nan, np.nan, np.nan

        # Calculate returns of the individual assets in the combo
        # Assumes stock_combo_prices_df has 'Date' as first column
        asset_returns_df = stock_combo_prices_df.iloc[:, 1:].pct_change().fillna(0)

        # Expected portfolio return (annualized decimal)
        mean_asset_returns_annualized = asset_returns_df.mean() * 252
        expected_portfolio_return_decimal = np.sum(np.array(weights_list) * mean_asset_returns_annualized)

        # Covariance matrix (annualized)
        covariance_matrix_annualized = asset_returns_df.cov() * 252

        # Expected portfolio volatility (annualized decimal)
        expected_volatility_decimal = np.sqrt(np.dot(np.array(weights_list).T, np.dot(covariance_matrix_annualized, np.array(weights_list))))

        # Sharpe Ratio
        if expected_volatility_decimal == 0:
            sharpe_ratio = np.nan # or 0, or handle as per financial convention
        else:
            sharpe_ratio = (expected_portfolio_return_decimal - current_rf_rate) / expected_volatility_decimal

        final_value = portfolio_df['Portfolio Value [$]'].iloc[-1]
        if current_initial_investment == 0: # Avoid division by zero for ROI
            return_on_investment_percent = np.nan if final_value !=0 else 0
        else:
            return_on_investment_percent = ((final_value - current_initial_investment) / current_initial_investment) * 100

        return expected_portfolio_return_decimal, expected_volatility_decimal, sharpe_ratio, final_value, return_on_investment_percent

    except Exception as e:
        # Log more specific error if possible
        stock_names = list(stock_combo_prices_df.columns[1:]) if not stock_combo_prices_df.empty else "N/A"
        logger_instance.log(f"❌ Error in simulation_engine_calc: {e} for stocks {stock_names}")
        return np.nan, np.nan, np.nan, np.nan, np.nan

def find_best_stock_combination(
    source_stock_prices_df,     # Main StockClose_df (e.g., top 20)
    stocks_to_consider_list,    # E.g., ESG_STOCKS_LIST
    current_initial_investment,
    min_portfolio_size,
    max_portfolio_size,
    num_simulation_runs,        # SIM_RUNS
    current_rf_rate,            # RF_RATE
    logger_instance,
    timer_instance
):
    """Finds the best stock combination from stocks_to_consider_list using brute force."""
    logger_instance.log("    Starting brute-force stock combination search...")

    available_stocks_for_search = [s for s in stocks_to_consider_list if s in source_stock_prices_df.columns]

    if not available_stocks_for_search:
        logger_instance.log("❌ No stocks from 'stocks_to_consider_list' found in 'source_stock_prices_df'. Skipping search.")
        return None, None, -float("inf"), None, None, None, None, 0 # Match expected return tuple

    logger_instance.log(f"    Stocks available for combination search: {', '.join(available_stocks_for_search)}")

    # Adjust max_portfolio_size if it's too large or None
    if max_portfolio_size is None or max_portfolio_size > len(available_stocks_for_search):
        max_portfolio_size = len(available_stocks_for_search)
    if min_portfolio_size <= 0: # Ensure min_portfolio_size is at least 1
        min_portfolio_size = 1
    if min_portfolio_size > max_portfolio_size:
        logger_instance.log(f"❌ Min portfolio size ({min_portfolio_size}) is greater than max ({max_portfolio_size}). Skipping.")
        return None, None, -float("inf"), None, None, None, None, 0

    total_combinations_to_evaluate = sum(comb(len(available_stocks_for_search), k) for k in range(min_portfolio_size, max_portfolio_size + 1))
    total_simulations_expected = total_combinations_to_evaluate * num_simulation_runs

    logger_instance.log(f"    Portfolio target size range: {min_portfolio_size}-{max_portfolio_size}")
    logger_instance.log(f"    Total expected simulations: {total_simulations_expected:,}")

    # Estimate runtime (simplified from Old.py for brevity, can be expanded)
    avg_simulation_time_per_run = 0.05 # Default average time if estimation fails
    # We will use the timer_instance's internal rolling average after the main loop starts.
    # The initial estimation here is just for a very rough upfront estimate.
    if total_simulations_expected > 0 and len(available_stocks_for_search) >= min_portfolio_size :
        temp_timer_for_estimation = ExecutionTimer(rolling_window=10) # Use a temporary timer
        temp_timer_for_estimation.start()
        # Perform a few sample simulations for estimation
        sample_combo = available_stocks_for_search[:min_portfolio_size]
        sample_df_subset = source_stock_prices_df[['Date'] + sample_combo]
        for _ in range(min(10, num_simulation_runs)): # Estimate with up to 10 runs
            weights = generate_portfolio_weights(len(sample_combo))
            simulation_engine_calc(sample_df_subset, weights, current_initial_investment, current_rf_rate, logger_instance)
        elapsed_for_sample = temp_timer_for_estimation.stop() # Stop the temporary timer
        avg_simulation_time_per_run = elapsed_for_sample / min(10, num_simulation_runs) if min(10, num_simulation_runs) > 0 else 0.05
    timer_instance.reset() # Reset the main timer before the actual simulation loop

    estimated_total_runtime = timedelta(seconds=total_simulations_expected * avg_simulation_time_per_run)
    estimated_completion_datetime = datetime.now() + estimated_total_runtime
    logger_instance.log(f"    Estimated avg sim time/run: {avg_simulation_time_per_run:.4f}s. Estimated total runtime: {estimated_total_runtime}. Est. completion: {estimated_completion_datetime.strftime('%Y-%m-%d %H:%M:%S')}")
    logger_instance.update_web_log("estimated_completion_time", estimated_completion_datetime.strftime('%Y-%m-%d %H:%M:%S'))

    overall_best_sharpe = -float("inf")
    best_overall_portfolio_combo = None
    best_overall_weights_alloc = None
    best_overall_final_val = None
    best_overall_roi_val = None
    best_overall_expected_return = None
    best_overall_volatility = None
    total_simulations_done = 0
    logged_thresholds = set() # Initialize once for the entire function call
    # The timer_instance will track the cumulative time of individual simulations.

    for num_stocks_in_combo in range(min_portfolio_size, max_portfolio_size + 1):
        num_combinations_for_size = comb(len(available_stocks_for_search), num_stocks_in_combo)
        simulations_for_this_size = num_combinations_for_size * num_simulation_runs
        current_time_str = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        logger_instance.log(f"\n    Starting {num_stocks_in_combo}-stock portfolios ({num_combinations_for_size} combos, {simulations_for_this_size} total sims) at {current_time_str}...")

        best_sharpe_for_size = -float("inf")
        completed_sims_for_size = 0

        for stock_combo in itertools.combinations(available_stocks_for_search, num_stocks_in_combo):
            stock_combo_list = list(stock_combo)
            df_subset_for_simulation = source_stock_prices_df[['Date'] + stock_combo_list]

            for sim_idx in range(num_simulation_runs):
                timer_instance.start() # Time each individual simulation
                weights = generate_portfolio_weights(len(stock_combo_list))
                exp_ret, vol, sharpe, final_val, roi = simulation_engine_calc(
                    df_subset_for_simulation, weights, current_initial_investment, current_rf_rate, logger_instance
                )
                timer_instance.stop() # Stop timing individual simulation; this updates internal averages
                total_simulations_done += 1 # Increment after timing
                completed_sims_for_size +=1

                if not pd.isna(sharpe) and sharpe > best_sharpe_for_size:
                    best_sharpe_for_size = sharpe
                    if sharpe > overall_best_sharpe:
                        overall_best_sharpe = sharpe
                        best_overall_portfolio_combo = stock_combo_list
                        best_overall_weights_alloc = weights
                        best_overall_final_val = final_val
                        best_overall_roi_val = roi
                        best_overall_expected_return = exp_ret
                        best_overall_volatility = vol
                        logger_instance.log(f"    🌟 New Overall Best! Sharpe: {sharpe:.4f}, Stocks: {', '.join(stock_combo_list)}")

                # Progress Logging at ~25% intervals
                # Calculate current progress percentage
                current_progress_percentage = (total_simulations_done / total_simulations_expected) * 100
                
                # Define logging thresholds (e.g., 25%, 50%, 75%)
                # We'll use a set to keep track of which thresholds have been logged
                # Initialize logged_thresholds if it's the first run of this inner loop for the current num_stocks_in_combo
                if 'logged_thresholds' not in locals() or completed_sims_for_size == 1 : # reset for each stock_combo batch
                    logged_thresholds = set()

                for threshold_pct in [25, 50, 75]: # Log at these percentages
                    if current_progress_percentage >= threshold_pct and threshold_pct not in logged_thresholds:
                        logged_thresholds.add(threshold_pct) # Mark as logged
                        est_rem_time = timer_instance.estimate_remaining(total_simulations_expected, total_simulations_done)
                        logger_instance.log(f"    Progress: {total_simulations_done}/{total_simulations_expected} ({current_progress_percentage:.1f}%). Est. Rem. Time: {est_rem_time}")
                        logger_instance.update_web_log("overall_progress", {
                            "completed_simulations": total_simulations_done,
                            "total_simulations": total_simulations_expected,
                            "percentage": current_progress_percentage,
                            "estimated_completion_time": (datetime.now() + est_rem_time).strftime('%Y-%m-%d %H:%M:%S') if est_rem_time else "N/A"
                        })
                        break # Log only one threshold per iteration if multiple are crossed
        
        logger_instance.log(f"    Completed all {num_stocks_in_combo}-stock portfolio simulations.")

    logger_instance.log(f"\n    Brute-force search completed. Total simulation time: {timedelta(seconds=timer_instance.total_time)}.")
    if best_overall_portfolio_combo:
        logger_instance.log(f"    🏆 Best Overall Portfolio Found:")
        logger_instance.log(f"       Stocks: {', '.join(best_overall_portfolio_combo)}")
        logger_instance.log(f"       Weights: {', '.join(f'{w:.4f}' for w in best_overall_weights_alloc)}")
        logger_instance.log(f"       Sharpe Ratio: {overall_best_sharpe:.4f}")
        logger_instance.log(f"       Expected Annual Return: {best_overall_expected_return*100:.2f}%")
        logger_instance.log(f"       Expected Annual Volatility: {best_overall_volatility*100:.2f}%")
        logger_instance.log(f"       Final Value: ${best_overall_final_val:,.2f} (from ${current_initial_investment:,.2f})")
        logger_instance.log(f"       ROI: {best_overall_roi_val:.2f}%")
        logger_instance.update_web_log("best_portfolio_details", {
            "stocks": best_overall_portfolio_combo, "weights": [round(w,4) for w in best_overall_weights_alloc],
            "sharpe_ratio": round(overall_best_sharpe,4), "final_value": round(best_overall_final_val,2),
            "roi_percent": round(best_overall_roi_val,2), "expected_return_annual_pct": round(best_overall_expected_return*100,2),
            "expected_volatility_annual_pct": round(best_overall_volatility*100,2)
        })
    else:
        logger_instance.log("    ❌ No suitable portfolio combination found.")
        logger_instance.update_web_log("best_portfolio_details", None)

    logger_instance.flush() # Ensure all logs are written
    return (best_overall_portfolio_combo, best_overall_weights_alloc, overall_best_sharpe,
            best_overall_final_val, best_overall_roi_val, best_overall_expected_return,
            best_overall_volatility, avg_simulation_time_per_run)

# ----------------------------------------------------------- #
#                   Configuration Loading                     #
# ----------------------------------------------------------- #

# Step 1: Determine the path to simpar.txt
# It's expected to be in the same directory as this script (Engine.py).
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
PARAMETERS_FILE_PATH = os.path.join(SCRIPT_DIR, "simpar.txt")

# Step 2: Initialize Logger with very basic/default paths.
# These paths will be updated once simpar.txt is loaded.
# Preliminary logs will go to the script's directory.
PRELIM_LOG_FILENAME = "engine_bootstrap.log"
PRELIM_WEB_LOG_FILENAME = "engine_bootstrap_progress.json" # Optional, can be None

PRELIM_LOG_PATH = os.path.join(SCRIPT_DIR, PRELIM_LOG_FILENAME)
PRELIM_WEB_LOG_PATH = os.path.join(SCRIPT_DIR, PRELIM_WEB_LOG_FILENAME)

# Ensure preliminary log directory (script's own directory) exists - usually not an issue.
# os.makedirs(os.path.dirname(PRELIM_LOG_PATH), exist_ok=True) # Not strictly needed if SCRIPT_DIR
# if PRELIM_WEB_LOG_PATH:
#     os.makedirs(os.path.dirname(PRELIM_WEB_LOG_PATH), exist_ok=True)

logger = Logger(
    log_path=PRELIM_LOG_PATH,
    web_log_path=PRELIM_WEB_LOG_PATH
)
logger.log(f"Logger initialized with preliminary path: {PRELIM_LOG_PATH}")
logger.log(f"Attempting to load parameters from: {PARAMETERS_FILE_PATH}")

# Step 3: Load all simulation parameters
try:
    sim_params = load_simulation_parameters(PARAMETERS_FILE_PATH, logger_instance=logger)
    logger.log(f"Successfully loaded parameters from: {PARAMETERS_FILE_PATH}")
except FileNotFoundError:
    logger.log(f"CRITICAL ERROR: Main parameters file not found at '{PARAMETERS_FILE_PATH}'. "
               "Ensure 'simpar.txt' is in the same directory as Engine.py. Exiting.")
    sys.exit(1)
except Exception as e:
    logger.log(f"CRITICAL ERROR: Failed to load parameters from '{PARAMETERS_FILE_PATH}'. Error: {e}. Exiting.")
    sys.exit(1)

# Step 4: Assign all operational variables from the loaded sim_params.
MIN_STOCKS = sim_params.get("min_stocks", 10)
MAX_STOCKS = sim_params.get("max_stocks", 20)
SIM_RUNS = sim_params.get("sim_runs", 100)
INITIAL_INVESTMENT = sim_params.get("initial_investment", 10000.0)
RF_RATE = sim_params.get("rf")
START_DATE_STR = sim_params.get("start_date")
ESG_STOCKS_LIST = sim_params.get("esg_stocks_list", []) # Load the list of ESG stocks

# Paths are now sourced *exclusively* from simpar.txt
# The load_simulation_parameters function already handles os.path.expanduser()
STOCK_DATA_FILE = sim_params.get("stock_data_file")
PORTFOLIO_FOLDER = sim_params.get("portfolio_folder")
CHARTS_FOLDER = sim_params.get("charts_folder")
LOG_FILE_PATH_PARAM = sim_params.get("log_file_path")
WEB_LOG_PATH_PARAM = sim_params.get("web_log_path")

# Step 5: Update logger paths if they were defined in sim_params and are different
if LOG_FILE_PATH_PARAM and LOG_FILE_PATH_PARAM != logger.log_path:
    logger.log(f"Info: Updating log path from parameters file to: {LOG_FILE_PATH_PARAM}")
    os.makedirs(os.path.dirname(LOG_FILE_PATH_PARAM), exist_ok=True)
    logger.log_path = LOG_FILE_PATH_PARAM

if WEB_LOG_PATH_PARAM and WEB_LOG_PATH_PARAM != logger.web_log_path:
    logger.log(f"Info: Updating web log path from parameters file to: {WEB_LOG_PATH_PARAM}")
    os.makedirs(os.path.dirname(WEB_LOG_PATH_PARAM), exist_ok=True)
    logger.web_log_path = WEB_LOG_PATH_PARAM
# Log final configuration values
logger.log("Final configuration loaded:") # Optional: Comment out for less verbose startup
for key, value in sim_params.items(): # Use sim_params which is the direct output of load_simulation_parameters
    # Log the actual loaded value, not the potentially defaulted global variable
    logger.log(f"  - {key}: {value}")

# Convert start_date string to datetime.date object if present
START_DATE = None
if START_DATE_STR:
    try:
        START_DATE = datetime.strptime(START_DATE_STR, '%Y-%m-%d').date()
        logger.log(f"  - Parsed START_DATE (from global var): {START_DATE}")
    except ValueError:
        logger.log(f"Warning: Invalid format for start_date '{START_DATE_STR}' in parameters file. Expected YYYY-MM-DD. Start date will not be used.")

# Validate that critical parameters (especially paths) are now loaded
critical_params_to_check = {
    "STOCK_DATA_FILE": STOCK_DATA_FILE,
    "PORTFOLIO_FOLDER": PORTFOLIO_FOLDER,
    "CHARTS_FOLDER": CHARTS_FOLDER,
    "LOG_FILE_PATH_PARAM": LOG_FILE_PATH_PARAM, # Check the one from params
    "RF_RATE": RF_RATE,
    "ESG_STOCKS_LIST": ESG_STOCKS_LIST # Add if this list must not be empty
}
missing_critical = [name for name, val in critical_params_to_check.items() if val is None]
if missing_critical:
    logger.log(f"CRITICAL ERROR: Missing critical parameters from '{PARAMETERS_FILE_PATH}': {', '.join(missing_critical)}. Exiting.")
    sys.exit(1)

# --- End of Configuration Loading ---

# ----------------------------------------------------------- #
#                     Execution Pipeline                      #
# ----------------------------------------------------------- #

# --- Read & Wrangle Stock Data ---
StockDataDB_df = pd.read_csv(STOCK_DATA_FILE)
StockDataDB_df['Date'] = pd.to_datetime(StockDataDB_df['Date'], format='mixed', errors='coerce').dt.date # Convert to date format, handle mixed formats
StockDataDB_df.fillna({'Close': 0}, inplace=True) # Replace NaN with 0 for closing prices
StockDataDB_df.sort_values(by=['Date', 'Stock'], inplace=True)

# Filter data based on the start_date
if START_DATE:
    StockDataDB_df = StockDataDB_df[StockDataDB_df['Date'] >= START_DATE]
    logger.log(f"    Filtering data from {START_DATE} to {StockDataDB_df['Date'].max()}.")

# Pivot to get closing prices structured by stock
StockClose_df = StockDataDB_df.pivot(index="Date", columns="Stock", values="Close").replace(0, np.nan)
StockClose_df.dropna(inplace=True)  # Keep only complete data
StockClose_df.reset_index(inplace=True)

# Calculate daily returns
StockDailyReturn_df = StockClose_df.copy()
StockDailyReturn_df.iloc[:, 1:] = StockClose_df.iloc[:, 1:].pct_change() * 100 # Calculate daily returns skipping the date column
StockDailyReturn_df.replace(np.nan, 0, inplace=True)

# Calculate Individual Sharpe Ratios
# We use .iloc[:, 1:] to exclude the 'Date' column from calculations.
# The daily returns in StockDailyReturn_df are already percentages, so we divide by 100.
IndividualSharpeRatios_sr = calculate_individual_sharpe_ratios(StockDailyReturn_df.iloc[:, 1:] / 100, RF_RATE)

# --- Debug: Print Individual Sharpe Ratios ---
# logger.log("    --- Individual Stock Sharpe Ratios (Annualized) ---")
# logger.log(f"\n{IndividualSharpeRatios_sr.sort_values(ascending=False).to_string()}") # Commented out for brevity

# --- Filter DataFrames for Top 20 Stocks by Sharpe Ratio ---
top_20_stocks_by_sharpe = IndividualSharpeRatios_sr.nlargest(20).index.tolist()
logger.log(f"    Top 20 stocks by Sharpe Ratio: {', '.join(top_20_stocks_by_sharpe)}")

# Ensure 'Date' column is included, then add the top 20 stocks
StockDailyReturn_df = StockDailyReturn_df[['Date'] + top_20_stocks_by_sharpe]

# logger.log("    --- Head of StockDailyReturn_df (Filtered for Top 20 Stocks by Sharpe) ---") # Commented out for brevity
# logger.log(f"\n{StockDailyReturn_df.head()}") # Commented out for brevity
# logger.log("    --- Tail of StockDailyReturn_df (Filtered for Top 20 Stocks by Sharpe) ---")
# logger.log(f"\n{StockDailyReturn_df.tail()}") # Commented out for brevity

# Filter StockClose_df as well, as it's used by find_best_stock_combination
StockClose_df = StockClose_df[['Date'] + top_20_stocks_by_sharpe]
# --- Initialize Execution Timer ---
sim_timer = ExecutionTimer(rolling_window=max(10, SIM_RUNS // 100)) # Adjust rolling window based on sim_runs

# --- Find Best Stock Combination (e.g., from ESG list within Top 20) ---
logger.log("\n--- Starting Search for Best Stock Combination ---")

# StockClose_df here is already filtered to top 20 stocks by Sharpe.
# ESG_STOCKS_LIST is the list of target tickers from simpar.txt.
# The find_best_stock_combination will find the best combo from ESG_STOCKS_LIST (target list)
# that are also present in the (already filtered) StockClose_df.

(best_portfolio_stocks, best_weights, best_sharpe,
 best_final_value, best_roi, best_exp_return,
 best_volatility, avg_sim_time) = find_best_stock_combination(
    StockClose_df,              # Price data for the universe of stocks to select from (e.g., top 20)
    ESG_STOCKS_LIST,            # List of specific stocks to consider for combinations (e.g., ESG list)
    INITIAL_INVESTMENT,
    MIN_STOCKS,                 # Min stocks in a portfolio combination
    MAX_STOCKS,                 # Max stocks in a portfolio combination
    SIM_RUNS,                   # Number of random weight simulations per combination
    RF_RATE,
    logger,                     # Pass the logger instance
    sim_timer                   # Pass the timer instance
)

logger.log("\n--- Engine Processing Finished ---")
logger.flush() # Final flush