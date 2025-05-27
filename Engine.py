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
import math 

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
        timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        log_entry = f"{timestamp} - {message}"
        print(log_entry)  # Console output
        self.messages.append(log_entry)
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
                file.write("\n".join(self.messages) + "\n") # Already adds timestamped messages
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
        "debug_mode": bool, # Added for debug mode
        "web_log_path": str,
        # Adaptive Simulation Parameters
        "adaptive_sim_enabled": bool,
        "initial_scan_sims": int,
        "early_discard_factor": float,
        "early_discard_min_best_sharpe": float,
        "progressive_min_sims": int,
        "progressive_base_log_k": int, # or float if fractional base is desired
        "progressive_max_sims_cap": int,
        "progressive_convergence_window": int,
        "progressive_convergence_delta": float,
        "progressive_check_interval": int,
        "top_n_percent_refinement": float,
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
                        elif target_type == bool:
                            if value_str.lower() == 'true':
                                processed_value = True
                            elif value_str.lower() == 'false':
                                processed_value = False
                            else:
                                raise ValueError(f"Boolean value for '{key}' must be 'true' or 'false', got '{value_str}'")
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

# Helper function for adaptive sampling
def should_continue_sampling(sharpes, min_iter, max_iter_for_combo, convergence_window, delta_threshold, logger_instance=None):
    """
    Decides if more simulations are needed for a combination based on convergence.
    """
    current_sim_count = len(sharpes)
    if current_sim_count < min_iter:
        return True # Not enough initial samples
    if current_sim_count >= max_iter_for_combo:
        return False # Reached max allowed for this combo

    # Ensure enough data for a stable window, but only if we haven't hit max_iter
    if current_sim_count < convergence_window:
        return True

    recent_sharpes = sharpes[-convergence_window:]
    if not recent_sharpes: # Should ideally not happen if current_sim_count >= convergence_window
        return True

    delta = max(recent_sharpes) - min(recent_sharpes)
    
    # Optional: detailed logging for convergence check
    # if logger_instance:
    #     logger_instance.log(f"    Convergence check: sims={current_sim_count}, recent_delta={delta:.4f}, threshold={delta_threshold}", level='DEBUG')

    return delta > delta_threshold

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
    source_stock_prices_df,     # Main StockClose_df (e.g., top N stocks by Sharpe)
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

    # --- Pre-calculate grand_total_expected_simulations_phase1 for better upfront estimation ---
    prelim_grand_total_expected_simulations_phase1 = 0
    for k_size_for_calc in range(min_portfolio_size, max_portfolio_size + 1):
        num_combinations_for_k_size = comb(len(available_stocks_for_search), k_size_for_calc)
        target_sims_for_k = num_simulation_runs # Fallback
        if ADAPTIVE_SIM_ENABLED:
            if k_size_for_calc < 2:
                target_sims_for_k = PROGRESSIVE_MIN_SIMS
            else:
                log_k_sq_calc = (math.log(float(k_size_for_calc)) ** 2) if k_size_for_calc >=1 else 0
                calculated_sims_calc = int(PROGRESSIVE_BASE_LOG_K * log_k_sq_calc)
                capped_sims_calc = min(calculated_sims_calc, PROGRESSIVE_MAX_SIMS_CAP)
                target_sims_for_k = max(capped_sims_calc, PROGRESSIVE_MIN_SIMS)
        prelim_grand_total_expected_simulations_phase1 += num_combinations_for_k_size * target_sims_for_k
    # --- End Pre-calculation ---

    # Calculate expected refinement simulations
    num_refinement_sims_expected = 0
    if ADAPTIVE_SIM_ENABLED and TOP_N_PERCENT_REFINEMENT > 0:
        num_to_refine_expected = int(total_combinations_to_evaluate * TOP_N_PERCENT_REFINEMENT)
        if num_to_refine_expected == 0 and total_combinations_to_evaluate > 0: num_to_refine_expected = 1
        num_refinement_sims_expected = num_to_refine_expected * num_simulation_runs # Refinement uses fixed SIM_RUNS

    total_simulations_expected_for_upfront_estimate = prelim_grand_total_expected_simulations_phase1 + num_refinement_sims_expected
    logger_instance.log(f"    Portfolio target size range: {min_portfolio_size}-{max_portfolio_size}")
    logger_instance.log(f"    Total expected simulations (Phase 1 Adaptive + Refinement): {total_simulations_expected_for_upfront_estimate:,}")

    # Estimate runtime (simplified from Old.py for brevity, can be expanded)
    avg_simulation_time_per_run = 0.05 # Default average time if estimation fails
    # We will use the timer_instance's internal rolling average after the main loop starts.
    # The initial estimation here is just for a very rough upfront estimate.
    if total_simulations_expected_for_upfront_estimate > 0 and len(available_stocks_for_search) >= min_portfolio_size :
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

    estimated_total_runtime = timedelta(seconds=total_simulations_expected_for_upfront_estimate * avg_simulation_time_per_run)
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
    # total_simulations_done = 0 # Replaced by total_actual_simulations_run_phase1
    
    all_combination_results_for_refinement = [] # Stores results for potential refinement
    total_actual_simulations_run_phase1 = 0

    # For more accurate progress estimation with adaptive sims
    # This will be the sum of (target_sims_for_k_progressive or num_simulation_runs) for each k
    # and then multiplied by num_combinations_for_size[k]
    grand_total_expected_simulations_phase1 = 0

    logged_thresholds = set() # Initialize once for the entire function call
    # The timer_instance will track the cumulative time of individual simulations.

    for num_stocks_in_combo in range(min_portfolio_size, max_portfolio_size + 1):
        num_combinations_for_size = comb(len(available_stocks_for_search), num_stocks_in_combo)
        simulations_for_this_size = num_combinations_for_size * num_simulation_runs
        current_time_str = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        logger_instance.log(f"\n    Starting {num_stocks_in_combo}-stock portfolios ({num_combinations_for_size} combos, {simulations_for_this_size} total sims) at {current_time_str}...")

        # Determine target simulations for this k if adaptive
        # This is the max number of sims for the progressive phase for this k
        target_sims_for_k_progressive = num_simulation_runs # Fallback to fixed if not adaptive
        if ADAPTIVE_SIM_ENABLED:
            if num_stocks_in_combo < 2: # Min stocks for log formula
                target_sims_for_k_progressive = PROGRESSIVE_MIN_SIMS
            else:
                log_k_sq = (math.log(float(num_stocks_in_combo)) ** 2) if num_stocks_in_combo >=1 else 0
                calculated_sims = int(PROGRESSIVE_BASE_LOG_K * log_k_sq)
                capped_sims = min(calculated_sims, PROGRESSIVE_MAX_SIMS_CAP)
                target_sims_for_k_progressive = max(capped_sims, PROGRESSIVE_MIN_SIMS)
            if DEBUG_MODE:
                logger_instance.log(f"DEBUG: Adaptive target sims for k={num_stocks_in_combo}: {target_sims_for_k_progressive} (vs fixed SIM_RUNS: {num_simulation_runs})")
        
        # Accumulate to grand total expected simulations for phase 1
        grand_total_expected_simulations_phase1 += num_combinations_for_size * (target_sims_for_k_progressive if ADAPTIVE_SIM_ENABLED else num_simulation_runs)

        best_sharpe_for_size = -float("inf")
        completed_sims_for_size = 0
        # Variables to track best result for the current combination (within adaptive loop)
        best_sharpe_this_combo = -float("inf")
        best_weights_this_combo = None
        best_exp_ret_this_combo = np.nan
        best_vol_this_combo = np.nan
        best_final_val_this_combo = np.nan
        best_roi_this_combo = np.nan

        for stock_combo in itertools.combinations(available_stocks_for_search, num_stocks_in_combo):
            stock_combo_list = list(stock_combo)
            df_subset_for_simulation = source_stock_prices_df[['Date'] + stock_combo_list]
            if DEBUG_MODE:
                logger_instance.log(f"DEBUG: Evaluating combination: {', '.join(stock_combo_list)}")

            # --- Adaptive Simulation Loop for this specific combination ---
            actual_sims_run_for_combo = 0
            all_sharpes_this_combo = [] # Stores sharpe ratios for convergence check for this combo
            
            # Reset bests for this specific combination before its simulation loop
            best_sharpe_this_combo = -float("inf") 
            # ... (reset other best_..._this_combo vars if needed, though they are overwritten)

            # Determine the max number of simulations for this particular combination run
            # If adaptive, it's target_sims_for_k_progressive, else it's the fixed num_simulation_runs
            max_sims_for_this_combo_run = target_sims_for_k_progressive if ADAPTIVE_SIM_ENABLED else num_simulation_runs

            for sim_idx in range(max_sims_for_this_combo_run): # Loop up to the adaptive/fixed target
                timer_instance.start() # Time each individual simulation
                weights = generate_portfolio_weights(len(stock_combo_list))
                exp_ret, vol, sharpe, final_val, roi = simulation_engine_calc(
                    df_subset_for_simulation, weights, current_initial_investment, current_rf_rate, logger_instance
                )
                timer_instance.stop() # Stop timing individual simulation; this updates internal averages
                actual_sims_run_for_combo += 1
                total_actual_simulations_run_phase1 += 1 # Accumulate total actual sims

                if not pd.isna(sharpe) and sharpe > best_sharpe_this_combo:
                    best_sharpe_this_combo = sharpe
                    best_weights_this_combo = weights
                    best_exp_ret_this_combo = exp_ret
                    best_vol_this_combo = vol
                    best_final_val_this_combo = final_val
                    best_roi_this_combo = roi

                if ADAPTIVE_SIM_ENABLED:
                    all_sharpes_this_combo.append(sharpe if not pd.isna(sharpe) else -float('inf'))

                    # 1. Initial Scan & Early Discard for this combination
                    if actual_sims_run_for_combo == INITIAL_SCAN_SIMS:
                        if overall_best_sharpe > EARLY_DISCARD_MIN_BEST_SHARPE and \
                           best_sharpe_this_combo < overall_best_sharpe * EARLY_DISCARD_FACTOR:
                            if DEBUG_MODE:
                                logger_instance.log(f"DEBUG: Combo {stock_combo_list}: Early discard triggered after {actual_sims_run_for_combo} sims. Combo Sharpe {best_sharpe_this_combo:.4f} (Overall best: {overall_best_sharpe:.4f}, Factor: {EARLY_DISCARD_FACTOR})")
                            break # Stop simulating this specific combination
                        elif DEBUG_MODE:
                             logger_instance.log(f"DEBUG: Combo {stock_combo_list}: Initial scan ({INITIAL_SCAN_SIMS} sims) completed. Combo Sharpe {best_sharpe_this_combo:.4f}. No early discard.")

                    # 2. Convergence Check for this combination
                    if actual_sims_run_for_combo >= PROGRESSIVE_MIN_SIMS and \
                       actual_sims_run_for_combo % PROGRESSIVE_CHECK_INTERVAL == 0:
                        if not should_continue_sampling(
                                all_sharpes_this_combo,
                                PROGRESSIVE_MIN_SIMS,
                                max_sims_for_this_combo_run, # Max for this combo
                                PROGRESSIVE_CONVERGENCE_WINDOW,
                                PROGRESSIVE_CONVERGENCE_DELTA,
                                logger_instance): # Pass logger if should_continue_sampling uses it
                            if DEBUG_MODE:
                                logger_instance.log(f"DEBUG: Combo {stock_combo_list}: Converged after {actual_sims_run_for_combo} sims. Best Sharpe for combo: {best_sharpe_this_combo:.4f}. Delta vs Threshold: {max(all_sharpes_this_combo[-PROGRESSIVE_CONVERGENCE_WINDOW:]) - min(all_sharpes_this_combo[-PROGRESSIVE_CONVERGENCE_WINDOW:])} vs {PROGRESSIVE_CONVERGENCE_DELTA}")
                            break # Stop simulating this specific combination
                        elif DEBUG_MODE and actual_sims_run_for_combo % PROGRESSIVE_CHECK_INTERVAL == 0 : # Log if check happened but no convergence
                            logger_instance.log(f"DEBUG: Combo {stock_combo_list}: Convergence check at {actual_sims_run_for_combo} sims. Delta: {max(all_sharpes_this_combo[-PROGRESSIVE_CONVERGENCE_WINDOW:]) - min(all_sharpes_this_combo[-PROGRESSIVE_CONVERGENCE_WINDOW:])}. Continuing.")
            # --- End of Adaptive Simulation Loop for this combination ---
            
            # Use the best result found for this combination (after adaptive/fixed runs)
            sharpe, weights, exp_ret, vol, final_val, roi = (
                best_sharpe_this_combo, best_weights_this_combo, 
                best_exp_ret_this_combo, best_vol_this_combo,
                best_final_val_this_combo, best_roi_this_combo
            )
            if DEBUG_MODE:
                logger_instance.log(f"DEBUG: Combo {stock_combo_list} finished with {actual_sims_run_for_combo} actual simulations. Best Sharpe for this combo: {sharpe:.4f}")


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
                    logger_instance.log(f"    🌟 New Overall Best (Phase 1)! Sharpe: {sharpe:.4f}, Stocks: {', '.join(stock_combo_list)}, Weights: {', '.join(f'{w:.4f}' for w in weights)}, Sims: {actual_sims_run_for_combo}")

            if ADAPTIVE_SIM_ENABLED and not pd.isna(sharpe): # Store result for potential refinement
                all_combination_results_for_refinement.append({
                    'sharpe': sharpe, 'weights': weights, 'stocks': stock_combo_list,
                    'roi': roi, 'exp_ret': exp_ret, 'vol': vol, 
                    'sims_run': actual_sims_run_for_combo # Sims for this combo
                })

            # Progress Logging at ~25% intervals based on actual simulations run
            # total_actual_simulations_run_phase1 is the sum of actual_sims_run_for_combo
            # grand_total_expected_simulations_phase1 is the sum of (num_combinations_for_size * target_sims_for_k_progressive)
            
            current_progress_percentage_actual_sims = (total_actual_simulations_run_phase1 / grand_total_expected_simulations_phase1) * 100 if grand_total_expected_simulations_phase1 > 0 else 0
            
            # Reset logged_thresholds for each new k-size batch if needed, or manage globally
            # For simplicity, let's check thresholds based on total_actual_simulations_run_phase1

            for threshold_pct in [25, 50, 75]: # Log at these percentages of actual simulations
                if current_progress_percentage_actual_sims >= threshold_pct and threshold_pct not in logged_thresholds:
                    logged_thresholds.add(threshold_pct) # Mark as logged
                    
                    remaining_expected_actual_simulations = grand_total_expected_simulations_phase1 - total_actual_simulations_run_phase1
                    
                    if timer_instance.avg_time > 0 and remaining_expected_actual_simulations > 0:
                        est_rem_time_seconds = timer_instance.avg_time * remaining_expected_actual_simulations
                        est_rem_time_delta = timedelta(seconds=est_rem_time_seconds)
                        est_completion_time_str = (datetime.now() + est_rem_time_delta).strftime('%Y-%m-%d %H:%M:%S')
                        logger_instance.log(f"    Progress (Actual Sims Phase 1): {total_actual_simulations_run_phase1:,}/{grand_total_expected_simulations_phase1:,} ({current_progress_percentage_actual_sims:.1f}%). Est. Rem. Time: {est_rem_time_delta}")
                    else:
                        est_rem_time_delta_str = "Calculating..."
                        est_completion_time_str = "Calculating..."
                        logger_instance.log(f"    Progress (Actual Sims Phase 1): {total_actual_simulations_run_phase1:,}/{grand_total_expected_simulations_phase1:,} ({current_progress_percentage_actual_sims:.1f}%). Calculating Est. Rem. Time...")
                    
                    logger_instance.update_web_log("overall_progress", {
                        "completed_actual_simulations": total_actual_simulations_run_phase1,
                        "total_expected_actual_simulations": grand_total_expected_simulations_phase1,
                        "percentage": current_progress_percentage_actual_sims,
                        "estimated_completion_time": est_completion_time_str
                    })
                    break # Log only one threshold per iteration if multiple are crossed

        logger_instance.log(f"    Completed all {num_stocks_in_combo}-stock portfolio simulations.")

    logger_instance.log(f"\n    Initial search phase completed. Total combinations processed: {total_combinations_to_evaluate}. Total actual simulations in phase 1: {total_actual_simulations_run_phase1:,}")
    logger_instance.log(f"    Total time for initial phase: {timedelta(seconds=timer_instance.total_time)}.")

    # --- Refinement Phase ---
    if ADAPTIVE_SIM_ENABLED and TOP_N_PERCENT_REFINEMENT > 0 and all_combination_results_for_refinement:
        logger_instance.log(f"\n    --- Starting Refinement Phase for Top {TOP_N_PERCENT_REFINEMENT*100:.0f}% Combinations ---")
        all_combination_results_for_refinement.sort(key=lambda x: x['sharpe'], reverse=True)
        num_to_refine = int(len(all_combination_results_for_refinement) * TOP_N_PERCENT_REFINEMENT)
        if num_to_refine == 0 and len(all_combination_results_for_refinement) > 0: # Ensure at least one if list is not empty
            num_to_refine = 1
        
        top_combinations_to_refine = all_combination_results_for_refinement[:num_to_refine]
        logger_instance.log(f"    Refining {len(top_combinations_to_refine)} combinations with {num_simulation_runs} simulations each (using fixed SIM_RUNS from simpar.txt)...")

        refinement_timer_start = time.time()
        for i, combo_data in enumerate(top_combinations_to_refine):
            logger_instance.log(f"    Refining combo {i+1}/{len(top_combinations_to_refine)}: {', '.join(combo_data['stocks'])} (Prev Sharpe: {combo_data['sharpe']:.4f} from {combo_data.get('sims_run', 'N/A')} sims)")
            
            # For refinement, run a fixed number of simulations (SIM_RUNS from params)
            # We need to simulate this combo again, num_simulation_runs times
            best_sharpe_refined = -float("inf")
            best_weights_refined = None
            best_exp_ret_refined = np.nan
            best_vol_refined = np.nan
            best_final_val_refined = np.nan
            best_roi_refined = np.nan
            actual_sims_for_refinement_combo = 0

            df_subset_for_refinement = source_stock_prices_df[['Date'] + combo_data['stocks']]
            for _ in range(num_simulation_runs): # Use the original SIM_RUNS for refinement
                weights_ref = generate_portfolio_weights(len(combo_data['stocks']))
                exp_ret_ref, vol_ref, sharpe_ref, final_val_ref, roi_ref = simulation_engine_calc(
                    df_subset_for_refinement, weights_ref, current_initial_investment, current_rf_rate, logger_instance
                )
                actual_sims_for_refinement_combo += 1
                if not pd.isna(sharpe_ref) and sharpe_ref > best_sharpe_refined:
                    best_sharpe_refined = sharpe_ref
                    best_weights_refined = weights_ref
                    best_exp_ret_refined = exp_ret_ref
                    best_vol_refined = vol_ref
                    best_final_val_refined = final_val_ref
                    best_roi_refined = roi_ref

            # Update overall best if this refined combo is better
            if not pd.isna(best_sharpe_refined) and best_sharpe_refined > overall_best_sharpe:
                overall_best_sharpe = best_sharpe_refined
                best_overall_portfolio_combo = combo_data['stocks']
                best_overall_weights_alloc = best_weights_refined
                best_overall_final_val = best_final_val_refined
                best_overall_roi_val = best_roi_refined
                best_overall_expected_return = best_exp_ret_refined
                best_overall_volatility = best_vol_refined
                logger_instance.log(f"    🌟 New Overall Best (Refined)! Sharpe: {best_sharpe_refined:.4f}, Stocks: {', '.join(combo_data['stocks'])}, Weights: {', '.join(f'{w:.4f}' for w in best_weights_refined)}, Sims: {actual_sims_for_refinement_combo}")
        
        refinement_total_time = time.time() - refinement_timer_start
        logger_instance.log(f"    Refinement phase completed. Total time for refinement: {timedelta(seconds=refinement_total_time)}.")

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
DEBUG_MODE = sim_params.get("debug_mode", False) # Load debug_mode, default to False

# Adaptive Simulation Parameters (loaded from sim_params with defaults)
ADAPTIVE_SIM_ENABLED = sim_params.get("adaptive_sim_enabled", True)
INITIAL_SCAN_SIMS = sim_params.get("initial_scan_sims", 200)
EARLY_DISCARD_FACTOR = sim_params.get("early_discard_factor", 0.75)
EARLY_DISCARD_MIN_BEST_SHARPE = sim_params.get("early_discard_min_best_sharpe", 0.1)
PROGRESSIVE_MIN_SIMS = sim_params.get("progressive_min_sims", 200)
PROGRESSIVE_BASE_LOG_K = sim_params.get("progressive_base_log_k", 500)
PROGRESSIVE_MAX_SIMS_CAP = sim_params.get("progressive_max_sims_cap", 3000)
PROGRESSIVE_CONVERGENCE_WINDOW = sim_params.get("progressive_convergence_window", 50)
PROGRESSIVE_CONVERGENCE_DELTA = sim_params.get("progressive_convergence_delta", 0.005)
PROGRESSIVE_CHECK_INTERVAL = sim_params.get("progressive_check_interval", 50)
TOP_N_PERCENT_REFINEMENT = sim_params.get("top_n_percent_refinement", 0.10)


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
logger.log(f"  - DEBUG_MODE: {DEBUG_MODE}") # Explicitly log DEBUG_MODE
for key, value in sim_params.items():
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

overall_script_start_time = datetime.now()
logger.log(f"🚀 Engine.py script started at: {overall_script_start_time.strftime('%Y-%m-%d %H:%M:%S')}")
logger.update_web_log("engine_script_start_time", overall_script_start_time.strftime('%Y-%m-%d %H:%M:%S'))


if DEBUG_MODE:
    logger.log("DEBUG: Engine.py started in DEBUG mode.")

# ----------------------------------------------------------- #
#                     Execution Pipeline                      #
# ----------------------------------------------------------- #

# --- Read & Wrangle Stock Data ---
StockDataDB_df = pd.read_csv(STOCK_DATA_FILE)
StockDataDB_df['Date'] = pd.to_datetime(StockDataDB_df['Date'], format='mixed', errors='coerce').dt.date # Convert to date format, handle mixed formats

logger.log("\n--- Starting Data Loading and Wrangling ---")
section_start_time = datetime.now()
logger.update_web_log("data_wrangling_start", section_start_time.strftime('%Y-%m-%d %H:%M:%S'))

StockDataDB_df.fillna({'Close': 0}, inplace=True) # Replace NaN with 0 for closing prices
StockDataDB_df.sort_values(by=['Date', 'Stock'], inplace=True)

# Filter data based on the start_date
if START_DATE:
    StockDataDB_df = StockDataDB_df[StockDataDB_df['Date'] >= START_DATE]
    logger.log(f"    Data filtered from {START_DATE} to {StockDataDB_df['Date'].max()}.")

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

# --- Filter DataFrames for Top Stocks by Sharpe Ratio based on MAX_STOCKS ---

# Determine the number of top stocks for the initial broader filter based on MAX_STOCKS from simpar.txt
# This num_top_stocks_for_filtering will be used to select from the global stock universe
# before intersecting with the ESG_STOCKS_LIST.
if 3 <= MAX_STOCKS <= 5: # If target portfolio size is small
    num_top_stocks_for_filtering = 25 # Consider a pool of top 25 global stocks
elif 6 <= MAX_STOCKS <= 10: # If target portfolio size is medium
    num_top_stocks_for_filtering = 30 # Consider a pool of top 30 global stocks
elif 11 <= MAX_STOCKS <= 20: # If target portfolio size is large
    num_top_stocks_for_filtering = 40 # Consider a pool of top 40 global stocks
else:
    logger.log(f"    Warning: MAX_STOCKS ({MAX_STOCKS}) is outside the defined tier ranges (3-5, 6-10, 11-20). Defaulting to a pool size of 40 for initial Sharpe Ratio filtering.")
    num_top_stocks_for_filtering = 40
top_n_stocks_by_sharpe = IndividualSharpeRatios_sr.nlargest(num_top_stocks_for_filtering).index.tolist() # Use the dynamically determined number

# Check if the number of stocks found is less than num_top_stocks_for_filtering,
# which can happen if the total number of stocks in IndividualSharpeRatios_sr is small.
actual_stocks_found_count = len(top_n_stocks_by_sharpe)
if actual_stocks_found_count < num_top_stocks_for_filtering:
    logger.log(f"    Note: Requested top {num_top_stocks_for_filtering} stocks, but only {actual_stocks_found_count} unique stocks available in the data after date filtering.")
    num_top_stocks_for_filtering = actual_stocks_found_count # Adjust to actual count

logger.log(f"    Global top {len(top_n_stocks_by_sharpe)} stocks by Sharpe Ratio selected for initial pool: {', '.join(top_n_stocks_by_sharpe)}")

# Ensure 'Date' column is included, then add the top n stocks
StockDailyReturn_df = StockDailyReturn_df[['Date'] + top_n_stocks_by_sharpe]

# Filter StockClose_df as well, as it's used by find_best_stock_combination
StockClose_df = StockClose_df[['Date'] + top_n_stocks_by_sharpe]

section_end_time = datetime.now()
section_duration = section_end_time - section_start_time
logger.log(f"--- Data Loading and Wrangling finished in {section_duration}. End time: {section_end_time.strftime('%Y-%m-%d %H:%M:%S')} ---")
logger.update_web_log("data_wrangling_end", section_end_time.strftime('%Y-%m-%d %H:%M:%S'))
logger.update_web_log("data_wrangling_duration", str(section_duration))

# --- Initialize Execution Timer ---
sim_timer = ExecutionTimer(rolling_window=max(10, SIM_RUNS // 100)) # Adjust rolling window based on sim_runs

# --- Find Best Stock Combination (e.g., from ESG list within Top N) ---
logger.log("\n--- Starting Search for Best Stock Combination ---")
section_start_time = datetime.now()
logger.update_web_log("stock_combination_search_start", section_start_time.strftime('%Y-%m-%d %H:%M:%S'))

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

section_end_time = datetime.now()
section_duration = section_end_time - section_start_time
logger.log(f"--- Search for Best Stock Combination finished in {section_duration}. End time: {section_end_time.strftime('%Y-%m-%d %H:%M:%S')} ---")
logger.update_web_log("stock_combination_search_end", section_end_time.strftime('%Y-%m-%d %H:%M:%S'))
logger.update_web_log("stock_combination_search_duration", str(section_duration))

overall_script_end_time = datetime.now()
total_script_duration = overall_script_end_time - overall_script_start_time
logger.log(f"\n🏁 Engine Processing Finished at {overall_script_end_time.strftime('%Y-%m-%d %H:%M:%S')} 🏁")
logger.log(f"⏳ Total script execution time: {total_script_duration} ⏳")
logger.update_web_log("engine_script_end_time", overall_script_end_time.strftime('%Y-%m-%d %H:%M:%S'))
logger.update_web_log("engine_script_total_duration", str(total_script_duration))
logger.flush() # Final flush