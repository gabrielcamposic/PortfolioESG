#!/usr/bin/env python

# --- Script Version ---
BACKTESTING_PY_VERSION = "1.5.0" # Added performance logging.

# ----------------------------------------------------------- #
#                           Libraries                         #
# ----------------------------------------------------------- #
import pandas as pd
import numpy as np
import os, sys, time, json, shutil, logging
from datetime import datetime
from typing import Dict, Any, Tuple

from shared_tools.shared_utils import (
    setup_logger,
    load_parameters_from_file,
)


# ----------------------------------------------------------- #
#                        Helper Functions                     #
# ----------------------------------------------------------- #

def initialize_performance_data(script_version: str) -> Dict[str, Any]:
    """Creates and initializes a dictionary to track script performance metrics."""
    return {
        "run_start_timestamp": datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
        "backtesting_py_version": script_version,
        "stocks_in_portfolio": 0,
        "benchmark_used": "N/A",
        "param_load_duration_s": 0.0,
        "data_load_duration_s": 0.0,
        "simulation_duration_s": 0.0,
        "metrics_calculation_duration_s": 0.0,
        "results_save_duration_s": 0.0,
        "overall_script_duration_s": 0.0,
    }

def log_performance_data(perf_data: Dict[str, Any], params: Dict[str, Any], logger: logging.Logger):
    """Logs the script's performance metrics to a CSV file."""
    log_path = params.get("BACKTESTING_PERFORMANCE_FILE")
    if not log_path:
        logger.warning("'BACKTESTING_PERFORMANCE_FILE' not in params. Skipping performance logging.")
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

def copy_file_to_web_accessible_location(source_path: str, params: Dict, logger: logging.Logger):
    """Copies a file to the web-accessible data directory."""
    dest_folder = params.get("WEB_ACCESSIBLE_DATA_PATH")
    if not isinstance(dest_folder, str) or not dest_folder:
        logger.warning("'WEB_ACCESSIBLE_DATA_PATH' is missing or invalid. Cannot copy file.")
        return
    if not os.path.exists(source_path):
        logger.warning(f"Source file not found at '{source_path}'.")
        return
    try:
        os.makedirs(dest_folder, exist_ok=True)
        destination_path = os.path.join(dest_folder, os.path.basename(source_path))
        shutil.copy2(source_path, destination_path)
        logger.info(f"Copied '{os.path.basename(source_path)}' to web-accessible location.")
    except Exception as e:
        logger.error(f"Failed to copy file from '{source_path}' to '{dest_folder}': {e}")

def calculate_backtest_metrics(equity_curve: pd.Series) -> Dict[str, float]:
    """
    Calculates key backtesting performance metrics from a daily equity curve.
    """
    if equity_curve.empty or len(equity_curve) < 2:
        return {
            "cagr_pct": 0.0, "volatility_pct": 0.0,
            "sharpe_ratio": 0.0, "max_drawdown_pct": 0.0,
            "total_return_pct": 0.0
        }

    total_return = (equity_curve.iloc[-1] / equity_curve.iloc[0]) - 1
    years = (equity_curve.index[-1] - equity_curve.index[0]).days / 365.25
    cagr = ((1 + total_return) ** (1 / years)) - 1 if years > 0 else 0.0
    daily_returns = equity_curve.pct_change().dropna()
    volatility = daily_returns.std() * np.sqrt(252)
    sharpe_ratio = (daily_returns.mean() * 252) / volatility if volatility != 0 else 0.0
    rolling_max = equity_curve.cummax()
    daily_drawdown = (equity_curve / rolling_max) - 1.0
    max_drawdown = daily_drawdown.min()

    return {
        "total_return_pct": total_return * 100,
        "cagr_pct": cagr * 100,
        "volatility_pct": volatility * 100,
        "sharpe_ratio": sharpe_ratio,
        "max_drawdown_pct": max_drawdown * 100,
    }


def run_simulation(
        prices_df: pd.DataFrame,
        weights: np.ndarray,
        initial_investment: float
) -> pd.Series:
    """
    Runs a historical simulation for a given portfolio.
    """
    normalized_prices = prices_df / prices_df.iloc[0]
    weighted_prices = normalized_prices * weights
    portfolio_relative_value = weighted_prices.sum(axis=1)
    equity_curve = portfolio_relative_value * initial_investment
    return equity_curve


# ----------------------------------------------------------- #
#                     Execution Pipeline                      #
# ----------------------------------------------------------- #

def main():
    """Main execution function for the Backtesting script."""
    overall_start_time = time.time()
    script_dir = os.path.dirname(os.path.abspath(__file__))

    expected_params = {
        # From paths.txt
        "FINDB_FILE": str, "WEB_ACCESSIBLE_DATA_PATH": str,
        "BACKTESTING_PROGRESS_JSON_FILE": str,
        "BACKTESTING_EQUITY_CURVE_FILE": str,
        # From backpar.txt
        "BACKTESTING_LOG_FILE": str, "BACKTESTING_RESULTS_FILE": str,
        "BACKTESTING_PERFORMANCE_FILE": str, "debug_mode": bool,
    }

    # 1. --- Load Parameters & Setup Logger ---
    try:
        paths_file = os.path.join(script_dir, '..', 'parameters', 'paths.txt')
        backpar_file = os.path.join(script_dir, '..', 'parameters', 'backpar.txt')
        params = load_parameters_from_file(
            filepaths=[paths_file, backpar_file],
            expected_parameters=expected_params
        )
    except (FileNotFoundError, Exception) as e:
        temp_logger = setup_logger("BacktestingStartupLogger", "backtesting_startup_error.log", None)
        temp_logger.critical(f"Could not load parameters. Exiting. Error: {e}", exc_info=True)
        sys.exit(1)

    perf_data = initialize_performance_data(BACKTESTING_PY_VERSION)
    perf_data["param_load_duration_s"] = time.time() - overall_start_time

    progress_file = params.get("BACKTESTING_PROGRESS_JSON_FILE")
    logger = setup_logger(
        "BacktestingRunner",
        log_file=params.get("BACKTESTING_LOG_FILE"),
        web_log_file=progress_file,
        level=logging.DEBUG if params.get("debug_mode") else logging.INFO
    )

    initial_payload = {
        "backtesting_status": "Running: Initializing...",
        "start_time": datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
        "end_time": "N/A",
        "status_message": "Starting backtesting engine.",
        "progress": 0
    }
    logger.info("--- Starting Backtesting.py execution ---", extra={'web_data': initial_payload})

    try:
        # 2. --- Load Inputs ---
        data_load_start_time = time.time()
        logger.info("Loading input data...", extra={'web_data': {"status_message": "Loading benchmark and portfolio data.", "progress": 10}})
        
        benchmarks_file_path = os.path.join(script_dir, '..', 'parameters', 'benchmarks.txt')
        try:
            benchmark_df = pd.read_csv(benchmarks_file_path)
            if benchmark_df.empty or 'Ticker' not in benchmark_df.columns:
                raise ValueError("Benchmark file is empty or missing 'Ticker' column.")
            benchmark_ticker = benchmark_df['Ticker'].iloc[0]
            logger.info(f"Loaded benchmark ticker: {benchmark_ticker}")
            perf_data["benchmark_used"] = benchmark_ticker
        except FileNotFoundError:
            logger.critical(f"Benchmark file not found at '{benchmarks_file_path}'. Exiting.", extra={'web_data': {"backtesting_status": "Failed", "status_message": f"Benchmark file not found at '{benchmarks_file_path}'"}})
            sys.exit(1)
        except Exception as e:
            logger.critical(f"Error reading benchmark file: {e}. Exiting.", extra={'web_data': {"backtesting_status": "Failed", "status_message": f"Error reading benchmark file: {e}"}})
            sys.exit(1)

        latest_summary_path = os.path.join(params.get("WEB_ACCESSIBLE_DATA_PATH"), "latest_run_summary.json")
        if not os.path.exists(latest_summary_path):
            logger.critical(f"Latest run summary not found at '{latest_summary_path}'. Cannot run backtest.", extra={'web_data': {"backtesting_status": "Failed", "status_message": "latest_run_summary.json not found."}})
            sys.exit(1)
        with open(latest_summary_path, 'r') as f:
            portfolio_summary = json.load(f)

        portfolio_details = portfolio_summary.get('best_portfolio_details', {})
        stocks = portfolio_details.get('stocks')
        weights = np.array(portfolio_details.get('weights'))
        initial_investment = portfolio_details.get('initial_investment', 10000)

        if not stocks or weights.size == 0:
            logger.critical("No valid stocks or weights found in summary file. Aborting.", extra={'web_data': {"backtesting_status": "Failed", "status_message": "No stocks/weights in summary."}})
            sys.exit(1)

        logger.info(f"Loaded portfolio of {len(stocks)} stocks for backtesting.")
        perf_data["stocks_in_portfolio"] = len(stocks)

        findb_file = params.get("FINDB_FILE")
        if not os.path.exists(findb_file):
            logger.critical(f"Master price database not found at '{findb_file}'. Aborting.", extra={'web_data': {"backtesting_status": "Failed", "status_message": "Master price DB not found."}})
            sys.exit(1)
        all_prices_df = pd.read_csv(findb_file, parse_dates=['Date'])
        logger.info("Loaded historical price data.", extra={'web_data': {"status_message": "Aligning price data.", "progress": 25}})

        all_relevant_tickers = stocks + [benchmark_ticker]
        prices_df = all_prices_df[all_prices_df['Stock'].isin(all_relevant_tickers)]
        prices_pivot = prices_df.pivot(index='Date', columns='Stock', values='Close').dropna()

        portfolio_prices_final = prices_pivot[stocks]
        benchmark_prices = prices_pivot[[benchmark_ticker]]

        common_index = portfolio_prices_final.index.intersection(benchmark_prices.index)
        portfolio_prices_final = portfolio_prices_final.loc[common_index]
        benchmark_prices = benchmark_prices.loc[common_index]
        perf_data["data_load_duration_s"] = time.time() - data_load_start_time
        logger.info(f"Backtest period: {common_index.min().date()} to {common_index.max().date()}")

        # 3. --- Run Simulations ---
        simulation_start_time = time.time()
        logger.info("Running simulations...", extra={'web_data': {"status_message": "Running portfolio simulation.", "progress": 50}})
        portfolio_equity_curve = run_simulation(portfolio_prices_final, weights, initial_investment)
        logger.info("Running simulation for the benchmark...", extra={'web_data': {"status_message": "Running benchmark simulation.", "progress": 70}})
        benchmark_equity_curve = run_simulation(benchmark_prices, np.array([1.0]), initial_investment)
        perf_data["simulation_duration_s"] = time.time() - simulation_start_time

        # 4. --- Calculate Metrics ---
        metrics_start_time = time.time()
        logger.info("Calculating performance metrics...", extra={'web_data': {"status_message": "Calculating performance metrics.", "progress": 85}})
        portfolio_metrics = calculate_backtest_metrics(portfolio_equity_curve)
        benchmark_metrics = calculate_backtest_metrics(benchmark_equity_curve)
        perf_data["metrics_calculation_duration_s"] = time.time() - metrics_start_time

        # 5. --- Save Results ---
        save_start_time = time.time()
        logger.info("Saving results...", extra={'web_data': {"status_message": "Saving results to CSV.", "progress": 95}})
        results_data = {
            'run_id': portfolio_summary.get('last_updated_run_id'),
            'timestamp': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
            'engine_version': BACKTESTING_PY_VERSION,
            'benchmark': benchmark_ticker,
            'portfolio_total_return_pct': portfolio_metrics['total_return_pct'],
            'benchmark_total_return_pct': benchmark_metrics['total_return_pct'],
            'portfolio_cagr_pct': portfolio_metrics['cagr_pct'],
            'benchmark_cagr_pct': benchmark_metrics['cagr_pct'],
            'portfolio_volatility_pct': portfolio_metrics['volatility_pct'],
            'benchmark_volatility_pct': benchmark_metrics['volatility_pct'],
            'portfolio_sharpe_ratio': portfolio_metrics['sharpe_ratio'],
            'benchmark_sharpe_ratio': benchmark_metrics['sharpe_ratio'],
            'portfolio_max_drawdown_pct': portfolio_metrics['max_drawdown_pct'],
            'benchmark_max_drawdown_pct': benchmark_metrics['max_drawdown_pct'],
        }
        results_df = pd.DataFrame([results_data])
        results_path = params.get("BACKTESTING_RESULTS_FILE")
        os.makedirs(os.path.dirname(results_path), exist_ok=True)
        results_df.to_csv(results_path, mode='a', header=not os.path.exists(results_path), index=False)
        logger.info(f"Saved backtesting metrics to {results_path}")

        equity_df = pd.DataFrame({
            'Date': portfolio_equity_curve.index,
            'Portfolio': portfolio_equity_curve.values,
            'Benchmark': benchmark_equity_curve.values
        })
        equity_df['run_id'] = portfolio_summary.get('last_updated_run_id')
        equity_curve_path = params.get("BACKTESTING_EQUITY_CURVE_FILE")
        os.makedirs(os.path.dirname(equity_curve_path), exist_ok=True)
        equity_df.to_csv(equity_curve_path, index=False)
        logger.info(f"Saved equity curve data to {equity_curve_path}")

        copy_file_to_web_accessible_location(results_path, params, logger)
        copy_file_to_web_accessible_location(equity_curve_path, params, logger)
        perf_data["results_save_duration_s"] = time.time() - save_start_time

        final_payload = {
            "backtesting_status": "Completed",
            "end_time": datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
            "status_message": "Backtesting finished successfully.",
            "progress": 100
        }
        logger.info("Backtesting completed successfully.", extra={'web_data': final_payload})

    except Exception as e:
        error_payload = {
            "backtesting_status": "Failed",
            "end_time": datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
            "status_message": f"An error occurred: {e}"
        }
        logger.critical(f"An unhandled exception occurred in the backtesting pipeline: {e}", exc_info=True, extra={'web_data': error_payload})
    finally:
        perf_data["overall_script_duration_s"] = time.time() - overall_start_time
        log_performance_data(perf_data, params, logger)
        performance_file_path = params.get("BACKTESTING_PERFORMANCE_FILE")
        if performance_file_path:
            copy_file_to_web_accessible_location(performance_file_path, params, logger)
        duration = time.time() - overall_start_time
        logger.info(f"--- Backtesting.py execution finished in {duration:.2f} seconds. ---")


if __name__ == "__main__":
    main()