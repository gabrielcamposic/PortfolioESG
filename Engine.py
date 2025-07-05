#!/home/gabrielcampos/.pyenv/versions/env-fa/bin/python

# --- Engine Version ---
ENGINE_VERSION = "1.7.0" # Updated data wrangling to focus exclusively on the provided stock list.
# ----------------------

# ----------------------------------------------------------- #
#                           Libraries                         #
# ----------------------------------------------------------- #
import pandas as pd
import numpy as np
import os
import random
import time
from datetime import datetime, timedelta
from math import comb
import itertools
import sys  # Import sys module for logging
import json # For logging to html readable
import math 
from json_utils import safe_update_json
from collections import Counter # Import Counter for efficient counting
import shutil # Add this import

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
        if web_data and self.web_log_path: # web_data is the new data for *this* specific log call
            try:
                safe_update_json(self.web_log_path, web_data)
            except Exception as e:
                # Log to console as logger might be in a weird state
                print(f"{timestamp} - Error writing to web log file {self.web_log_path} in log(): {e}")

        if self.log_count % self.flush_interval == 0:
            self.flush()

    def update_web_log(self, key, value):
        """Update a specific key in the web log JSON file."""
        if self.web_log_path:
            timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            try:
                safe_update_json(self.web_log_path, {key: value})
            except Exception as e:
                print(f"{timestamp} - Error writing to web log file {self.web_log_path} in update_web_log(): {e}")

    def flush(self):
        """Write logs to file in bulk and clear memory."""
        if self.messages:
            with open(self.log_path, 'a') as file:
                file.write("\n".join(self.messages) + "\n")
            self.messages = []  # Clear memory

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
        "scored_runs_file_path": str, # New: path to scored runs file
        "top_n_stocks_from_score": int, # New: number of top stocks to use
        "portfolio_folder": str, # This is still used for reading benchmark portfolios if that feature is active
        "max_stocks_per_sector": int, # New: diversification constraint
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
        # GA Parameters
        "ga_population_size": int,
        "ga_num_generations": int,
        "ga_mutation_rate": float,
        "ga_crossover_rate": float,
        "ga_elitism_count": int,
        "ga_tournament_size": int,
        # GA Convergence Parameters
        "ga_convergence_generations": int,
        "ga_convergence_tolerance": float,
        "heuristic_threshold_k": int, # Added: Threshold for switching to heuristic
        "results_log_csv_path": str, # Added: Path for results CSV log
        "web_accessible_data_folder": str, # Added: Path for web-accessible data
        "performance_log_csv_path": str, # Added: Path for performance CSV log
        "debug_mode": bool, # Ensure debug_mode is in expected types
        # Stock pool sizing parameters
        "pool_size_tiers": str,
        "pool_size_default_num_stocks": int,
        "ga_fitness_noise_log_path": str, # Added: Path for GA fitness/noise CSV log
        # New parameters for simulation feedback and advanced GA
        "bf_progress_log_thresholds": str, # Will be parsed to list of ints
        "ga_init_pop_max_attempts_multiplier": int,
    }

    # Add the new parameter for portfolio value history
    expected_types["portfolio_value_history_csv_path"] = str
    expected_types["auto_curate_threshold"] = float

    try:
        # Read debug_mode first, if available, to control logging within this function
        local_debug_mode = False
        # We'll do a preliminary pass or look for it specifically

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

                # Special handling for debug_mode to use it immediately
                if key == "debug_mode":
                    try:
                        if value_str.lower() == 'true':
                            local_debug_mode = True
                        elif value_str.lower() == 'false':
                            local_debug_mode = False
                        else:
                            raise ValueError(f"Boolean value for '{key}' must be 'true' or 'false', got '{value_str}'")
                        parameters[key] = local_debug_mode # Store it in parameters dict too
                    except ValueError:
                         message = f"Warning: Could not convert value '{value_str}' for key '{key}' to bool in '{filepath}'. Using default False for local debug."
                         if logger_instance: logger_instance.log(message) # Use logger if available
                         else: print(message) # Fallback print
                # Handle the typo: stock_data_file' -> stock_data_file
                if key == "stock_data_file'":
                    message = (f"Info: Correcting key 'stock_data_file'' to 'stock_data_file' from '{filepath}'. "
                               "Consider fixing this typo in the file itself.")
                    if logger_instance:
                        logger_instance.log(message)
                    else:
                        print(message)
                    key = "stock_data_file"
                
                elif key == "pool_size_tiers":
                    parsed_tiers = []
                    if value_str: # Ensure not empty
                        try:
                            tier_definitions = value_str.split(',')
                            for tier_def in tier_definitions:
                                range_part, num_stocks_part = tier_def.split(':')
                                min_s, max_s = map(int, range_part.split('-'))
                                num_stocks = int(num_stocks_part)
                                parsed_tiers.append(((min_s, max_s), num_stocks))
                            processed_value = parsed_tiers
                        except ValueError as e:
                            message = (f"Warning: Malformed 'pool_size_tiers' string '{value_str}' in '{filepath}'. Error: {e}. "
                                       "Expected format like '3-5:50,6-10:75'. Using empty list.")
                            if logger_instance: logger_instance.log(message)
                            else: print(message)
                            processed_value = [] # Fallback to empty list
                    else:
                        processed_value = [] # Empty list for empty string
                    parameters[key] = processed_value
                    if local_debug_mode and logger_instance: # Use local debug mode
                        logger_instance.log(f"DEBUG: Parsed pool_size_tiers: {processed_value}")
                    # Continue to next line in file, as this key is handled

                elif key == "bf_progress_log_thresholds":
                    if value_str:
                        try:
                            processed_value = [int(t.strip()) for t in value_str.split(',') if t.strip()]
                        except ValueError:
                            message = f"Warning: Malformed 'bf_progress_log_thresholds' string '{value_str}'. Expected comma-separated integers. Using default [25, 50, 75]."
                            if logger_instance: logger_instance.log(message)
                            else: print(message)
                            processed_value = [25, 50, 75] # Fallback
                    else:
                        processed_value = [25, 50, 75] # Default if empty
                    parameters[key] = processed_value
                    # Continue to next line in file



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
                            print(message) # Fallback print
                        parameters[key] = value_str  # Fallback to string

                else: # Truly unknown key
                    message = f"Warning: Unknown parameter key '{key}' found in '{filepath}'. Treating as string."
                    if logger_instance:
                        logger_instance.log(message)
                    else:
                        print(message)
                    if value_str.startswith('~'): # Still expand user paths for unknown strings
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

def load_scored_stocks(filepath, top_n, logger_instance=None):
    """
    Loads the scored runs CSV, identifies the most recent run, and returns the
    top N stocks from that run based on 'CompositeScore'.
    Also returns a dictionary mapping stocks to their sectors.
    """
    expanded_filepath = os.path.expanduser(filepath) # Ensure path is expanded
    if not os.path.exists(expanded_filepath):
        message = f"CRITICAL ERROR: Scored runs file not found at '{expanded_filepath}'. Please run Scoring.py to generate it, or check the path in simpar.txt."
        if logger_instance:
            logger_instance.log(message)
        else:
            print(message)
        raise FileNotFoundError(message)
    
    try:
        df = pd.read_csv(expanded_filepath)
        if 'run_id' not in df.columns or 'CompositeScore' not in df.columns or 'Stock' not in df.columns or 'Sector' not in df.columns:
            raise ValueError("Scored runs file is missing required columns: 'run_id', 'CompositeScore', 'Stock', 'Sector'.")
        
        # Find the most recent run_id
        latest_run_id = df['run_id'].max()
        latest_run_df = df[df['run_id'] == latest_run_id].copy()
        
        # Sort by score and select the top N stocks
        latest_run_df.sort_values(by='CompositeScore', ascending=False, inplace=True)
        top_stocks_df = latest_run_df.head(top_n)
        top_stocks = top_stocks_df['Stock'].tolist()
        stock_to_sector_map = pd.Series(top_stocks_df.Sector.values, index=top_stocks_df.Stock).to_dict()
        
        if logger_instance:
            logger_instance.log(f"Successfully loaded {len(top_stocks)} top stocks from the latest run ('{latest_run_id}') in {os.path.basename(expanded_filepath)}.")
            if DEBUG_MODE:
                logger_instance.log(f"DEBUG: Top {top_n} stocks selected: {', '.join(top_stocks)}")
        
        return top_stocks, stock_to_sector_map

    except Exception as e:
        message = f"CRITICAL ERROR: Failed to read or parse scored runs file '{expanded_filepath}': {e}"
        if logger_instance:
            logger_instance.log(message)
        else:
            print(message)
        raise # Re-raise for critical failure

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
    source_stock_prices_df,
    stocks_to_consider_list,
    current_initial_investment,
    min_portfolio_size,
    max_portfolio_size,
    current_rf_rate,
    logger_instance,
    timer_instance,
    stock_sector_map,
    max_stocks_per_sector,
    sim_params
):
    """Finds the best stock combination from stocks_to_consider_list using brute force or GA."""
    # Extract all config from sim_params
    SIM_RUNS = sim_params.get("sim_runs", 100)
    ADAPTIVE_SIM_ENABLED = sim_params.get("adaptive_sim_enabled", True)
    PROGRESSIVE_MIN_SIMS = sim_params.get("progressive_min_sims", 200)
    PROGRESSIVE_BASE_LOG_K = sim_params.get("progressive_base_log_k", 500)
    PROGRESSIVE_MAX_SIMS_CAP = sim_params.get("progressive_max_sims_cap", 3000)
    PROGRESSIVE_CONVERGENCE_WINDOW = sim_params.get("progressive_convergence_window", 50)
    PROGRESSIVE_CONVERGENCE_DELTA = sim_params.get("progressive_convergence_delta", 0.005)
    PROGRESSIVE_CHECK_INTERVAL = sim_params.get("progressive_check_interval", 50)
    TOP_N_PERCENT_REFINEMENT = sim_params.get("top_n_percent_refinement", 0.10)
    HEURISTIC_THRESHOLD_K = sim_params.get("heuristic_threshold_k", 9)
    INITIAL_SCAN_SIMS = sim_params.get("initial_scan_sims", 200)
    EARLY_DISCARD_FACTOR = sim_params.get("early_discard_factor", 0.75)
    EARLY_DISCARD_MIN_BEST_SHARPE = sim_params.get("early_discard_min_best_sharpe", 0.1)
    DEBUG_MODE = sim_params.get("debug_mode", False)

    logger_instance.log("    Starting brute-force stock combination search...")

    available_stocks_for_search = [s for s in stocks_to_consider_list if s in source_stock_prices_df.columns]

    if not available_stocks_for_search:
        logger_instance.log("❌ No stocks from 'stocks_to_consider_list' found in 'source_stock_prices_df'. Skipping search.")
        return None, None, -float("inf"), None, None, None, None, 0, [], 0.0

    logger_instance.log(f"    Stocks available for combination search: {', '.join(available_stocks_for_search)}")

    # Adjust max_portfolio_size if it's too large or None
    if max_portfolio_size is None or max_portfolio_size > len(available_stocks_for_search):
        max_portfolio_size = len(available_stocks_for_search)
    if min_portfolio_size <= 0: # Ensure min_portfolio_size is at least 1
        min_portfolio_size = 1
    if min_portfolio_size > max_portfolio_size:
        logger_instance.log(f"❌ Min portfolio size ({min_portfolio_size}) is greater than max ({max_portfolio_size}). Skipping.")
        return None, None, -float("inf"), None, None, None, None, 0, available_stocks_for_search, 0.0

    total_combinations_to_evaluate = sum(comb(len(available_stocks_for_search), k) for k in range(min_portfolio_size, max_portfolio_size + 1))

    # --- Pre-calculate grand_total_expected_simulations_phase1 for better upfront estimation ---
    prelim_grand_total_expected_simulations_phase1 = 0
    for k_size_for_calc in range(min_portfolio_size, max_portfolio_size + 1):
        num_combinations_for_k_size = comb(len(available_stocks_for_search), k_size_for_calc)
        target_sims_for_k = SIM_RUNS # Fallback
        if ADAPTIVE_SIM_ENABLED:
            if k_size_for_calc < 2:
                target_sims_for_k = PROGRESSIVE_MIN_SIMS
            else:
                log_k_sq_calc = (math.log(float(k_size_for_calc)) ** 2) if k_size_for_calc >=1 else 0
                calculated_sims_calc = int(PROGRESSIVE_BASE_LOG_K * log_k_sq_calc) # SIM_RUNS is not used here
                capped_sims_calc = min(calculated_sims_calc, PROGRESSIVE_MAX_SIMS_CAP)
                target_sims_for_k = max(capped_sims_calc, PROGRESSIVE_MIN_SIMS)
        prelim_grand_total_expected_simulations_phase1 += num_combinations_for_k_size * target_sims_for_k
    # --- End Pre-calculation ---

    # Calculate expected refinement simulations
    num_refinement_sims_expected = 0
    if ADAPTIVE_SIM_ENABLED and TOP_N_PERCENT_REFINEMENT > 0:
        num_to_refine_expected = int(total_combinations_to_evaluate * TOP_N_PERCENT_REFINEMENT)
        if num_to_refine_expected == 0 and total_combinations_to_evaluate > 0: num_to_refine_expected = 1
        num_refinement_sims_expected = num_to_refine_expected * SIM_RUNS # Refinement uses fixed SIM_RUNS

    total_simulations_expected_for_upfront_estimate = prelim_grand_total_expected_simulations_phase1 + num_refinement_sims_expected
    
    logger_instance.log(f"    Portfolio target size range: {min_portfolio_size}-{max_portfolio_size}")
    logger_instance.log(f"    Brute-force threshold (k <= HEURISTIC_THRESHOLD_K): {HEURISTIC_THRESHOLD_K}") # Log the threshold
    logger_instance.log(f"    Total expected simulations (Phase 1 BF Adaptive + Refinement): {total_simulations_expected_for_upfront_estimate:,}") # Clarify BF

    # Estimate runtime (simplified from Old.py for brevity, can be expanded)
    avg_simulation_time_per_run = 0.05 # Default average time if estimation fails
    # We will use the timer_instance's internal rolling average after the main loop starts.
    # The initial estimation here is just for a very rough upfront estimate.
    if total_simulations_expected_for_upfront_estimate > 0 and len(available_stocks_for_search) >= min_portfolio_size :
        temp_timer_for_estimation = ExecutionTimer(rolling_window=10) # Use a temporary timer
        temp_timer_for_estimation.start()
        # Perform a few sample simulations for estimation
        sample_combo = available_stocks_for_search[:min_portfolio_size]
        sample_df_subset = source_stock_prices_df[['Date'] + sample_combo] # SIM_RUNS is not used here
        for _ in range(min(10, SIM_RUNS)): # Estimate with up to 10 runs
            weights = generate_portfolio_weights(len(sample_combo))
            simulation_engine_calc(sample_df_subset, weights, current_initial_investment, current_rf_rate, logger_instance)
        elapsed_for_sample = temp_timer_for_estimation.stop() # Stop the temporary timer
        avg_simulation_time_per_run = elapsed_for_sample / min(10, SIM_RUNS) if min(10, SIM_RUNS) > 0 else 0.05
    timer_instance.reset() # Reset the main timer before the actual simulation loop

    estimated_total_runtime = timedelta(seconds=total_simulations_expected_for_upfront_estimate * avg_simulation_time_per_run)
    estimated_completion_datetime = datetime.now() + estimated_total_runtime
    logger_instance.log(f"    Estimated avg sim time/run: {avg_simulation_time_per_run:.4f}s. Estimated total runtime (BF+Refinement): {estimated_total_runtime}. Est. completion: {estimated_completion_datetime.strftime('%Y-%m-%d %H:%M:%S')}") # Clarify BF
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
    # handled by brute force. This is used for the in-loop progress bar.
    grand_total_expected_simulations_phase1_bf = prelim_grand_total_expected_simulations_phase1 # Use the pre-calculated value

    refinement_total_time = 0.0 # Initialize refinement_total_time
    logged_thresholds = set() # Initialize once for the entire function call
    # The timer_instance will track the cumulative time of individual simulations.

    for num_stocks_in_combo in range(min_portfolio_size, max_portfolio_size + 1):
        current_time_str = datetime.now().strftime('%Y-%m-%d %H:%M:%S') # Add this line

        # Update phase specifically for Brute-Force or GA
        if num_stocks_in_combo <= HEURISTIC_THRESHOLD_K:
            # Brute-force logic will go here
            num_combinations_for_size = comb(len(available_stocks_for_search), num_stocks_in_combo)
            logger_instance.log(f"\n    Starting {num_stocks_in_combo}-stock portfolios (Brute-Force) ({num_combinations_for_size} combos) at {current_time_str}...")

            # Determine target simulations for this k if adaptive
            target_sims_for_k_progressive = SIM_RUNS # Fallback to fixed if not adaptive
            logger_instance.update_web_log("current_engine_phase", f"Brute-Force (k={num_stocks_in_combo})")
            if ADAPTIVE_SIM_ENABLED:
                if num_stocks_in_combo < 2: # Min stocks for log formula
                    target_sims_for_k_progressive = PROGRESSIVE_MIN_SIMS
                else:
                    log_k_sq = (math.log(float(num_stocks_in_combo)) ** 2) if num_stocks_in_combo >=1 else 0
                    calculated_sims = int(PROGRESSIVE_BASE_LOG_K * log_k_sq)
                    capped_sims = min(calculated_sims, PROGRESSIVE_MAX_SIMS_CAP)
                    target_sims_for_k_progressive = max(capped_sims, PROGRESSIVE_MIN_SIMS)
                if DEBUG_MODE:
                    logger_instance.log(f"DEBUG: Adaptive target sims for k={num_stocks_in_combo}: {target_sims_for_k_progressive} (vs fixed SIM_RUNS: {SIM_RUNS})")
            
            best_sharpe_for_size = -float("inf")
            # Variables to track best result for the current combination (within adaptive loop)
            # These will be used by the brute-force combination loop later
            # best_sharpe_this_combo = -float("inf") 
            # ... (other best_..._this_combo vars)

            # --- New: Sector Diversification Filter ---
            all_possible_combos_for_size = itertools.combinations(available_stocks_for_search, num_stocks_in_combo)
            
            diversified_combos = []
            for combo in all_possible_combos_for_size:
                sector_counts = Counter(stock_sector_map.get(s, 'Unknown') for s in combo)
                if not sector_counts or max(sector_counts.values()) <= max_stocks_per_sector:
                    diversified_combos.append(combo)
            
            if len(diversified_combos) < num_combinations_for_size:
                logger_instance.log(f"    Sector diversification constraint reduced combinations for k={num_stocks_in_combo} from {num_combinations_for_size} to {len(diversified_combos)}.")
            
            # --- End Filter ---

            for stock_combo in diversified_combos: # Iterate over the filtered list
                stock_combo_list = list(stock_combo)
                df_subset_for_simulation = source_stock_prices_df[['Date'] + stock_combo_list]
                if DEBUG_MODE:
                    logger_instance.log(f"DEBUG: Evaluating combination: {', '.join(stock_combo_list)}")

                # --- Adaptive Simulation Loop for this specific combination ---
                actual_sims_run_for_combo = 0
                all_sharpes_this_combo = [] # Stores sharpe ratios for convergence check for this combo
                
                # Reset bests for this specific combination before its simulation loop
                best_sharpe_this_combo = -float("inf") 
                best_weights_this_combo = None
                best_exp_ret_this_combo = np.nan
                best_vol_this_combo = np.nan
                best_final_val_this_combo = np.nan
                best_roi_this_combo = np.nan

                # Determine the max number of simulations for this particular combination run
                max_sims_for_this_combo_run = target_sims_for_k_progressive if ADAPTIVE_SIM_ENABLED else SIM_RUNS
                
                for sim_idx in range(max_sims_for_this_combo_run): # Loop up to the adaptive/fixed target
                    timer_instance.start() # Time each individual simulation
                    weights = generate_portfolio_weights(len(stock_combo_list))
                    exp_ret, vol, sharpe, final_val, roi = simulation_engine_calc(
                        df_subset_for_simulation, weights, current_initial_investment, current_rf_rate, logger_instance
                    )
                    timer_instance.stop() # Stop timing individual simulation; this updates internal averages
                    actual_sims_run_for_combo += 1
                    total_actual_simulations_run_phase1 += 1 # Accumulate total actual sims for BF phase

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
                # --- End of Adaptive Simulation Loop for this combination (will be fully formed later) ---
                
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
                    # Update overall best if this combination is better
                    if sharpe > overall_best_sharpe:
                        overall_best_sharpe = sharpe
                        best_overall_portfolio_combo = stock_combo_list
                        best_overall_weights_alloc = weights
                        best_overall_final_val = final_val
                        best_overall_roi_val = roi
                        best_overall_expected_return = exp_ret
                        best_overall_volatility = vol
                        logger_instance.log(f"    🌟 New Overall Best (Phase 1 BF)! Sharpe: {sharpe:.4f}, Stocks: {', '.join(stock_combo_list)}, Weights: {', '.join(f'{w:.4f}' for w in weights)}, Sims: {actual_sims_run_for_combo}")

                if ADAPTIVE_SIM_ENABLED and not pd.isna(sharpe): # Store result for potential refinement (only from BF phase)
                    all_combination_results_for_refinement.append({
                        'sharpe': sharpe, 'weights': weights, 'stocks': stock_combo_list,
                        'roi': roi, 'exp_ret': exp_ret, 'vol': vol, 
                        'sims_run': actual_sims_run_for_combo # Sims for this combo
                    })

                # Progress Logging at ~25% intervals based on actual simulations run in BF phase
                current_progress_percentage_actual_sims = (total_actual_simulations_run_phase1 / grand_total_expected_simulations_phase1_bf) * 100 if grand_total_expected_simulations_phase1_bf > 0 else 0
                
                for threshold_pct in [25, 50, 75]: # Log at these percentages of actual simulations
                    if current_progress_percentage_actual_sims >= threshold_pct and threshold_pct not in logged_thresholds:
                        logged_thresholds.add(threshold_pct) # Mark as logged
                        
                        remaining_expected_actual_simulations = grand_total_expected_simulations_phase1_bf - total_actual_simulations_run_phase1
                        
                        if timer_instance.avg_time > 0 and remaining_expected_actual_simulations > 0:
                            est_rem_time_seconds = timer_instance.avg_time * remaining_expected_actual_simulations
                            est_rem_time_delta = timedelta(seconds=est_rem_time_seconds)
                            est_completion_time_str = (datetime.now() + est_rem_time_delta).strftime('%Y-%m-%d %H:%M:%S')
                            logger_instance.log(f"    Progress (Actual Sims Phase 1 BF): {total_actual_simulations_run_phase1:,}/{grand_total_expected_simulations_phase1_bf:,} ({current_progress_percentage_actual_sims:.1f}%). Est. Rem. Time: {est_rem_time_delta}")
                        else:
                            # est_rem_time_delta_str = "Calculating..." # Variable not used
                            est_completion_time_str = "Calculating..."
                            logger_instance.log(f"    Progress (Actual Sims Phase 1 BF): {total_actual_simulations_run_phase1:,}/{grand_total_expected_simulations_phase1_bf:,} ({current_progress_percentage_actual_sims:.1f}%). Calculating Est. Rem. Time...")
                        
                        # Update web log with BF progress
                        logger_instance.update_web_log("overall_progress", {
                            "completed_actual_simulations_bf": total_actual_simulations_run_phase1,
                            "total_expected_actual_simulations_bf": grand_total_expected_simulations_phase1_bf,
                            "percentage_bf": current_progress_percentage_actual_sims,
                            "estimated_completion_time_bf": est_completion_time_str
                        })
                        break # Log only one threshold per iteration if multiple are crossed
            # End of loop for a single stock_combo
            
            logger_instance.log(f"    Completed all {num_stocks_in_combo}-stock portfolio simulations (Brute-Force).")

        else: # num_stocks_in_combo > HEURISTIC_THRESHOLD_K
            # --- Heuristic Logic (Genetic Algorithm Placeholder) will go here ---
            logger_instance.log(f"\n    Starting {num_stocks_in_combo}-stock portfolios (Heuristic - GA) at {current_time_str}...")

            # Call the Genetic Algorithm function here
            # This function will return the best portfolio it found for this size k
            # It will also handle its own internal logging and progress tracking
            best_combo_heuristic, best_weights_heuristic, best_sharpe_heuristic, \
            best_final_val_heuristic, best_roi_heuristic, best_exp_ret_heuristic, \
            best_vol_heuristic = run_genetic_algorithm(
                source_stock_prices_df,
                available_stocks_for_search,
                num_stocks_in_combo, # This is k
                current_initial_investment,
                current_rf_rate,
                logger_instance,
                timer_instance,
                SIM_RUNS, # Pass SIM_RUNS for evaluating individuals
                sim_params
                # Add GA-specific parameters here (population size, generations, etc.)
            )

            # Update overall best if the heuristic found a better portfolio for this size k
            if not pd.isna(best_sharpe_heuristic) and best_sharpe_heuristic > overall_best_sharpe:
                 overall_best_sharpe = best_sharpe_heuristic
                 best_overall_portfolio_combo = best_combo_heuristic
                 best_overall_weights_alloc = best_weights_heuristic
                 best_overall_final_val = best_final_val_heuristic
                 best_overall_roi_val = best_roi_heuristic
                 best_overall_expected_return = best_exp_ret_heuristic
                 best_overall_volatility = best_vol_heuristic
                 logger_instance.log(f"    🌟 New Overall Best (Heuristic GA)! Sharpe: {best_sharpe_heuristic:.4f}, Stocks: {', '.join(best_combo_heuristic if best_combo_heuristic else [])}, Weights: {', '.join(f'{w:.4f}' for w in best_weights_heuristic) if best_weights_heuristic is not None else 'N/A'}")

            logger_instance.log(f"    Completed {num_stocks_in_combo}-stock portfolio search (Heuristic - GA).")

    # The rest of the function (Refinement Phase, Final Summary, Return) remains outside the loop for now.
    # ... (existing code for refinement and final summary) ...

    logger_instance.log(f"\n    Initial search phase completed. Total combinations processed: {total_combinations_to_evaluate}. Total actual simulations in phase 1: {total_actual_simulations_run_phase1:,}")
    logger_instance.log(f"    Total time for initial phase: {timedelta(seconds=timer_instance.total_time)}.")

    # --- Refinement Phase ---
    if ADAPTIVE_SIM_ENABLED and TOP_N_PERCENT_REFINEMENT > 0 and all_combination_results_for_refinement:
        logger_instance.log(f"\n    --- Starting Refinement Phase for Top {TOP_N_PERCENT_REFINEMENT*100:.0f}% Combinations ---")
        logger_instance.update_web_log("current_engine_phase", "Refinement Phase")
        all_combination_results_for_refinement.sort(key=lambda x: x['sharpe'], reverse=True)
        num_to_refine = int(len(all_combination_results_for_refinement) * TOP_N_PERCENT_REFINEMENT)
        if num_to_refine == 0 and len(all_combination_results_for_refinement) > 0: # Ensure at least one if list is not empty
            num_to_refine = 1
        
        logger_instance.update_web_log("refinement_progress", {
            "status": "Initializing...",
            "current_combo_refined": 0,
            "total_combos_to_refine": num_to_refine,
            "percentage_refinement": 0
        })
        top_combinations_to_refine = all_combination_results_for_refinement[:num_to_refine] # SIM_RUNS is not used here
        logger_instance.log(f"    Refining {len(top_combinations_to_refine)} combinations with {SIM_RUNS} simulations each (using fixed SIM_RUNS from simpar.txt)...")

        refinement_timer_start = time.time()
        for i, combo_data in enumerate(top_combinations_to_refine):
            logger_instance.log(f"    Refining combo {i+1}/{len(top_combinations_to_refine)}: {', '.join(combo_data['stocks'])} (Prev Sharpe: {combo_data['sharpe']:.4f} from {combo_data.get('sims_run', 'N/A')} sims)")
            
            logger_instance.update_web_log("refinement_progress", {
                "status": "Running",
                "current_combo_refined": i + 1,
                "total_combos_to_refine": len(top_combinations_to_refine),
                "percentage_refinement": ((i + 1) / len(top_combinations_to_refine)) * 100 if len(top_combinations_to_refine) > 0 else 0
            })

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
            for _ in range(SIM_RUNS): # Use the original SIM_RUNS for refinement
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
        logger_instance.update_web_log("refinement_progress", {
            "status": "Completed",
            "current_combo_refined": len(top_combinations_to_refine),
            "total_combos_to_refine": len(top_combinations_to_refine),
            "percentage_refinement": 100
        })

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
            "expected_volatility_annual_pct": round(best_overall_volatility*100,2),
            "initial_investment": round(current_initial_investment, 2) # Add initial investment
        })
    else:
        logger_instance.log("    ❌ No suitable portfolio combination found.")
        logger_instance.update_web_log("best_portfolio_details", None)

    logger_instance.flush() # Ensure all logs are written
    return (best_overall_portfolio_combo, best_overall_weights_alloc, overall_best_sharpe,
            best_overall_final_val, best_overall_roi_val, best_overall_expected_return,
            best_overall_volatility, avg_simulation_time_per_run, available_stocks_for_search, refinement_total_time)

# ----------------------------------------------------------- #
#                  Heuristic Functions (Placeholder)          #
# ----------------------------------------------------------- #

def run_genetic_algorithm(
    source_stock_prices_df,
    available_stocks_for_search,
    num_stocks_in_combo, # This is k for the heuristic
    current_initial_investment,
    current_rf_rate,
    logger_instance,
    timer_instance,
    num_simulation_runs, # SIM_RUNS for evaluating individuals
    sim_params
):
    """
    Comprehensive Genetic Algorithm for portfolio optimization.
    """
    # --- GA Parameters from sim_params ---
    POPULATION_SIZE = sim_params.get("ga_population_size", 50)
    NUM_GENERATIONS = sim_params.get("ga_num_generations", 30)
    MUTATION_RATE = sim_params.get("ga_mutation_rate", 0.01)
    CROSSOVER_RATE = sim_params.get("ga_crossover_rate", 0.7)
    ELITISM_COUNT = sim_params.get("ga_elitism_count", 2)
    TOURNAMENT_SIZE = sim_params.get("ga_tournament_size", 3)
    CONVERGENCE_GENERATIONS = sim_params.get("ga_convergence_generations", 10)
    CONVERGENCE_TOLERANCE = sim_params.get("ga_convergence_tolerance", 0.0001)
    GA_INIT_POP_MAX_ATTEMPTS_MULTIPLIER = sim_params.get("ga_init_pop_max_attempts_multiplier", 5)
    DEBUG_MODE = sim_params.get("debug_mode", False)

    logger_instance.log(f"    GA Parameters: Pop. Size={POPULATION_SIZE}, Generations={NUM_GENERATIONS}, Mutation={MUTATION_RATE}, Crossover={CROSSOVER_RATE}, Elitism={ELITISM_COUNT}, Tournament={TOURNAMENT_SIZE}, Convergence Gens={CONVERGENCE_GENERATIONS}, Tol={CONVERGENCE_TOLERANCE}")

    if len(available_stocks_for_search) < num_stocks_in_combo:
        logger_instance.log(f"    Warning (GA): Not enough available stocks ({len(available_stocks_for_search)}) to form a {num_stocks_in_combo}-stock portfolio. Skipping GA for this k.")
        return (None, None, -float("inf"), None, None, None, None)

    # --- Population Initialization ---
    population = []
    generated_combos = set()
    attempts = 0
    max_attempts = POPULATION_SIZE * GA_INIT_POP_MAX_ATTEMPTS_MULTIPLIER
    while len(population) < POPULATION_SIZE and attempts < max_attempts:
        combo_tuple = tuple(sorted(random.sample(available_stocks_for_search, num_stocks_in_combo)))
        if combo_tuple not in generated_combos:
            population.append(list(combo_tuple))
            generated_combos.add(combo_tuple)
        attempts += 1
    if len(population) < POPULATION_SIZE:
        logger_instance.log(f"    Warning (GA): Could only generate {len(population)} unique individuals for initial population (target: {POPULATION_SIZE}).")
    if not population:
        logger_instance.log(f"    Error (GA): Failed to create any initial GA population for {num_stocks_in_combo} stocks.")
        return (None, None, -float("inf"), None, None, None, None)

    best_sharpe_overall_ga = -float("inf")
    best_combo_overall_ga = None
    best_weights_overall_ga = None
    best_final_val_overall_ga = None
    best_roi_overall_ga = None
    best_exp_ret_overall_ga = None
    best_vol_overall_ga = None
    best_sharpe_history = []

    for generation in range(NUM_GENERATIONS):
        logger_instance.log(f"    GA Generation {generation + 1}/{NUM_GENERATIONS} for k={num_stocks_in_combo}...")
        logger_instance.update_web_log("ga_progress", {
            "status": "Running",
            "current_k": num_stocks_in_combo,
            "current_generation": generation + 1,
            "current_individual_ga": 0,
            "percentage_ga": ((generation + 1) / NUM_GENERATIONS) * 100 if NUM_GENERATIONS > 0 else 0,
            "total_individuals_ga": len(population),
            "total_generations_ga": NUM_GENERATIONS,
            "best_sharpe_this_k": round(best_sharpe_overall_ga, 4) if best_sharpe_overall_ga != -float("inf") else "N/A"
        })
        evaluated_population_details = []
        for individual_idx, combo_list in enumerate(population):
            # Prepare price data for this combo
            try:
                df_subset = source_stock_prices_df[["Date"] + list(combo_list)]
            except Exception as e:
                logger_instance.log(f"    GA: Error extracting price data for {combo_list}: {e}")
                continue
            # Generate random weights and evaluate fitness (Sharpe)
            best_sharpe = -float("inf")
            best_weights = None
            best_final_val = None
            best_roi = None
            best_exp_ret = None
            best_vol = None
            for _ in range(num_simulation_runs):
                weights = generate_portfolio_weights(num_stocks_in_combo)
                sim_result = simulation_engine_calc(
                    df_subset, weights, current_initial_investment, current_rf_rate, logger_instance
                )
                if sim_result is None:
                    continue
                sharpe, exp_ret, vol, final_val, roi = sim_result
                if sharpe is not None and sharpe > best_sharpe:
                    best_sharpe = sharpe
                    best_weights = weights
                    best_final_val = final_val
                    best_roi = roi
                    best_exp_ret = exp_ret
                    best_vol = vol
            evaluated_population_details.append((best_sharpe, combo_list, best_weights, best_exp_ret, best_vol, best_final_val, best_roi))
            if best_sharpe > best_sharpe_overall_ga:
                best_sharpe_overall_ga = best_sharpe
                best_combo_overall_ga = combo_list
                best_weights_overall_ga = best_weights
                best_final_val_overall_ga = best_final_val
                best_roi_overall_ga = best_roi
                best_exp_ret_overall_ga = best_exp_ret
                best_vol_overall_ga = best_vol
        # Sort by Sharpe descending
        evaluated_population_details.sort(key=lambda x: x[0] if x[0] is not None else -float('inf'), reverse=True)
        # Elitism: carry over top N
        next_population = [list(evaluated_population_details[i][1]) for i in range(min(ELITISM_COUNT, len(evaluated_population_details)))]
        # Fill rest of next_population
        while len(next_population) < POPULATION_SIZE:
            # Tournament selection
            parent1 = select_parents(evaluated_population_details, logger_instance, sim_params, TOURNAMENT_SIZE)
            parent2 = select_parents(evaluated_population_details, logger_instance, sim_params, TOURNAMENT_SIZE)
            # Crossover
            child1, child2 = crossover_portfolios(parent1[1], parent2[1], available_stocks_for_search, num_stocks_in_combo, logger_instance, sim_params, CROSSOVER_RATE)
            # Mutation
            child1 = mutate_portfolio(child1, available_stocks_for_search, logger_instance, sim_params, MUTATION_RATE)
            child2 = mutate_portfolio(child2, available_stocks_for_search, logger_instance, sim_params, MUTATION_RATE)
            # Ensure uniqueness
            for child in [child1, child2]:
                child_tuple = tuple(sorted(child))
                if child_tuple not in generated_combos and len(child) == num_stocks_in_combo:
                    next_population.append(child)
                    generated_combos.add(child_tuple)
                if len(next_population) >= POPULATION_SIZE:
                    break
        population = next_population[:POPULATION_SIZE]
        # Convergence check
        current_gen_best_sharpe = evaluated_population_details[0][0] if evaluated_population_details else -float('inf')
        best_sharpe_history.append(current_gen_best_sharpe)
        if len(best_sharpe_history) > CONVERGENCE_GENERATIONS:
            best_sharpe_history.pop(0)
        if generation >= CONVERGENCE_GENERATIONS - 1 and len(best_sharpe_history) == CONVERGENCE_GENERATIONS:
            delta = max(best_sharpe_history) - min(best_sharpe_history)
            if delta < CONVERGENCE_TOLERANCE:
                logger_instance.log(f"    GA: Converged after {generation+1} generations (delta={delta:.6f} < tol={CONVERGENCE_TOLERANCE})")
                break
    # Log GA fitness/noise if path provided
    ga_fitness_noise_filepath = sim_params.get("ga_fitness_noise_log_path")
    if ga_fitness_noise_filepath and best_combo_overall_ga:
        try:
            import csv
            with open(ga_fitness_noise_filepath, "a", newline="") as f:
                writer = csv.writer(f)
                writer.writerow([num_stocks_in_combo, best_sharpe_overall_ga, best_combo_overall_ga, best_weights_overall_ga])
        except Exception as e:
            logger_instance.log(f"    GA: Failed to log fitness/noise: {e}")
    if best_combo_overall_ga:
        return (best_combo_overall_ga, best_weights_overall_ga, best_sharpe_overall_ga, best_final_val_overall_ga, best_roi_overall_ga, best_exp_ret_overall_ga, best_vol_overall_ga)
    else:
        return (None, None, -float("inf"), None, None, None, None)

# --- Updated GA Helper Functions ---
def select_parents(evaluated_population_details, logger_instance, sim_params_dict, tournament_size=None):
    """
    Tournament selection from evaluated population.
    """
    if not evaluated_population_details:
        return random.choice(evaluated_population_details)
    t_size = tournament_size or sim_params_dict.get("ga_tournament_size", 3)
    if len(evaluated_population_details) < t_size:
        t_size = len(evaluated_population_details)
    tournament_contenders = random.sample(evaluated_population_details, t_size)
    tournament_contenders.sort(key=lambda x: x[0] if x[0] is not None else -float('inf'), reverse=True)
    return tournament_contenders[0]

def crossover_portfolios(parent1_stocks, parent2_stocks, available_stocks, k, logger_instance, sim_params_dict, crossover_rate=None):
    """
    Single-point crossover with duplicate removal.
    """
    rate = crossover_rate if crossover_rate is not None else sim_params_dict.get("ga_crossover_rate", 0.7)
    if random.random() >= rate:
        return list(parent1_stocks), list(parent2_stocks)
    point = random.randint(1, k-1)
    child1 = list(parent1_stocks[:point]) + [s for s in parent2_stocks if s not in parent1_stocks[:point]]
    child2 = list(parent2_stocks[:point]) + [s for s in parent1_stocks if s not in parent2_stocks[:point]]
    # Truncate to k
    child1 = child1[:k]
    child2 = child2[:k]
    return child1, child2

def mutate_portfolio(portfolio_stocks, available_stocks, logger_instance, sim_params_dict, mutation_rate=None):
    """
    Mutation by swapping one stock.
    """
    rate = mutation_rate if mutation_rate is not None else sim_params_dict.get("ga_mutation_rate", 0.01)
    if random.random() >= rate or not portfolio_stocks:
        return list(portfolio_stocks)
    out_stock = random.choice(portfolio_stocks)
    in_stock = random.choice([s for s in available_stocks if s not in portfolio_stocks])
    mutated = list(portfolio_stocks)
    mutated[mutated.index(out_stock)] = in_stock
    return mutated