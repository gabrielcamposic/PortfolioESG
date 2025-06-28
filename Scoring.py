#!/home/gabrielcampos/.pyenv/versions/env-fa/bin/python
# ----------------------------------------------------------- #
#                           Libraries                         #
# ----------------------------------------------------------- #
import yfinance as yf
import pandas as pd
import numpy as np
import os
import sys
import json
from datetime import datetime
import time

# --- Script Version ---
SCORING_PY_VERSION = "1.0.0"
# ----------------------

# ----------------------------------------------------------- #
#                       Global variables                      #
# ----------------------------------------------------------- #

# These will be populated by load_scoring_parameters
DEBUG_MODE = False
STOCK_DATA_FILE = ""
INPUT_STOCKS_FILE = ""
SCORED_STOCKS_OUTPUT_FILE = ""
SCORED_RESULTS_CSV_PATH = ""
TOP_N_STOCKS = 20
RISK_FREE_RATE = 0.0
LOG_FILE_PATH = ""
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
        "scored_stocks_output_file": str, "log_file_path": str, "web_log_path": str,
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
            tickers = [line.strip() for line in f.read().split(',') if line.strip()]
        logger_instance.log(f"Loaded {len(tickers)} tickers from {filepath}")
        return tickers
    except FileNotFoundError:
        logger_instance.log(f"CRITICAL: Input stocks file not found at '{filepath}'.")
        raise

def get_stock_financials(tickers, logger_instance):
    logger_instance.log(f"Fetching financial data for {len(tickers)} tickers...")
    financials = {}
    for i, ticker in enumerate(tickers):
        try:
            stock = yf.Ticker(ticker)
            info = stock.info
            forward_pe = info.get('forwardPE')
            forward_eps = info.get('forwardEps')

            if isinstance(forward_pe, (int, float)) and isinstance(forward_eps, (int, float)) and forward_eps > 0:
                financials[ticker] = {'forwardPE': forward_pe, 'forwardEps': forward_eps}
                if DEBUG_MODE: logger_instance.log(f"  - Fetched for {ticker}: PE={forward_pe}, EPS={forward_eps}")
            else:
                logger_instance.log(f"  - Skipping {ticker} due to missing/invalid forward PE/EPS. PE: {forward_pe}, EPS: {forward_eps}")
            
            logger_instance.update_web_log("scoring_progress", {"current_ticker": ticker, "progress": ((i + 1) / len(tickers)) * 100})
            time.sleep(0.2)  # Be polite to the API
        except Exception as e:
            logger_instance.log(f"  - Error fetching financial data for {ticker}: {e}")
    return financials

def calculate_individual_sharpe_ratios(stock_daily_returns, risk_free_rate):
    mean_returns = stock_daily_returns.mean() * 252
    std_devs = stock_daily_returns.std() * np.sqrt(252)
    # Replace 0 std_devs with NaN to avoid division by zero, then fill resulting NaNs
    sharpe_ratios = (mean_returns - risk_free_rate) / std_devs.replace(0, np.nan)
    return sharpe_ratios.fillna(0)

# ----------------------------------------------------------- #
#