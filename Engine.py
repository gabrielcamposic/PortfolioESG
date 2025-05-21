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

# ----------------------------------------------------------- #
#                   Configuration Loading                     #
# ----------------------------------------------------------- #

# Step 1: Determine the path to Simulation_parameters.txt
# It's expected to be in the same directory as this script (Engine.py).
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
PARAMETERS_FILE_PATH = os.path.join(SCRIPT_DIR, "Simulation_parameters.txt")

# Step 2: Initialize Logger with very basic/default paths.
# These paths will be updated once Simulation_parameters.txt is loaded.
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
               "Ensure 'Simulation_parameters.txt' is in the same directory as Engine.py. Exiting.")
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

# Paths are now sourced *exclusively* from Simulation_parameters.txt
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
logger.log("Final configuration loaded:")
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
