#!/usr/bin/env python

# --- Script Version ---
SCORING_PY_VERSION = "3.0.0"  # Refactored to use shared_utils and new parameter/logging standards.

# ----------------------------------------------------------- #
#                           Libraries                         #
# ----------------------------------------------------------- #
import pandas as pd
import numpy as np
import os, sys, time, logging, shutil
from datetime import datetime
from typing import Any, Dict

# --- Use shared utilities for consistency ---
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
        # Metadata
        "run_start_timestamp": datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
        "scoring_py_version": script_version,
        # Counters
        "stocks_loaded_from_input": 0,
        "stocks_successfully_scored": 0,
        # Timers
        "param_load_duration_s": 0.0,
        "data_load_duration_s": 0.0,
        "scoring_and_analysis_duration_s": 0.0,
        "results_save_duration_s": 0.0,
        "overall_script_duration_s": 0.0,
    }


def log_performance_data(perf_data: Dict[str, Any], params: Dict[str, Any], logger: logging.Logger):
    """Logs the script's performance metrics to a CSV file."""
    log_path = params.get("SCORING_PERFORMANCE_FILE")
    if not log_path:
        logger.warning("'SCORING_PERFORMANCE_FILE' not in params. Skipping performance logging.")
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


def copy_file_to_web_accessible_location(source_param_key: str, params: Dict[str, Any], logger: logging.Logger):
    """Copies a file to the web-accessible data directory."""
    source_path = params.get(source_param_key)
    dest_folder = params.get("WEB_ACCESSIBLE_DATA_PATH")

    if not isinstance(source_path, str) or not source_path:
        logger.warning(f"Param '{source_param_key}' is missing or invalid. Cannot copy file.")
        return
    if not isinstance(dest_folder, str) or not dest_folder:
        logger.warning("'WEB_ACCESSIBLE_DATA_PATH' is missing or invalid. Cannot copy file.")
        return
    if not os.path.exists(source_path):
        logger.warning(f"Source file for '{source_param_key}' not found at '{source_path}'.")
        return

    try:
        os.makedirs(dest_folder, exist_ok=True)
        destination_path = os.path.join(dest_folder, os.path.basename(source_path))
        shutil.copy2(source_path, destination_path)
        logger.info(f"Copied '{os.path.basename(source_path)}' to web-accessible location.")
    except Exception as e:
        logger.error(f"Failed to copy file from '{source_path}' to '{dest_folder}': {e}")


def load_input_stocks_with_sectors(params: Dict[str, Any], logger: logging.Logger) -> pd.DataFrame:
    """Loads tickers, names, sectors, and industries, preparing them for scoring."""
    tickers_file_path = params.get("TICKERS_FILE")
    if not tickers_file_path:
        logger.critical("'TICKERS_FILE' not found in parameters. Cannot load stocks.")
        return pd.DataFrame()

    try:
        stocks_df = pd.read_csv(
            tickers_file_path, header=None, names=['Ticker', 'Name', 'Sector', 'Industry'],
            comment='#', skip_blank_lines=True, sep=','
        )
        for col in stocks_df.select_dtypes(['object']):
            stocks_df[col] = stocks_df[col].str.strip()

        # --- SUGGESTED MODIFICATION START ---
        # Check for and handle missing company names to improve data quality.
        # If a name is missing, use the stock's ticker as a fallback.
        missing_names_mask = stocks_df['Name'].isnull() | (stocks_df['Name'] == '')
        if missing_names_mask.any():
            num_missing = missing_names_mask.sum()
            logger.warning(f"Found {num_missing} stocks with missing names. Using Ticker as a fallback for them.")
            stocks_df.loc[missing_names_mask, 'Name'] = stocks_df.loc[missing_names_mask, 'Ticker']
        # --- SUGGESTED MODIFICATION END ---

        # Filter out tickers marked with 'Error'
        stocks_df = stocks_df[~stocks_df['Sector'].str.contains('Error', na=False, case=False)].copy()

        # Sanitize for safety and consistency
        stocks_df['Sector'] = stocks_df['Sector'].str.replace('&', 'and', regex=False)
        stocks_df['Industry'] = stocks_df['Industry'].str.replace('&', 'and', regex=False)

        stocks_df.dropna(subset=['Ticker'], inplace=True)
        stocks_df.drop_duplicates(subset=['Ticker'], keep='first', inplace=True)
        stocks_df.rename(columns={'Ticker': 'Stock'}, inplace=True)

        logger.info(f"Loaded {len(stocks_df)} unique stocks with sector/industry data.")
        return stocks_df
    except FileNotFoundError:
        logger.critical(f"Input stocks file not found at '{tickers_file_path}'.")
        return pd.DataFrame()
    except Exception as e:
        logger.critical(f"Error reading tickers file '{tickers_file_path}': {e}")
        return pd.DataFrame()


def load_financials_data(params: Dict[str, Any], logger: logging.Logger) -> pd.DataFrame:
    """Loads the most recent financial data entry for each stock."""
    filepath = params.get("FINANCIALS_DB_FILE")
    if not filepath:
        logger.warning("'FINANCIALS_DB_FILE' not in params. Scoring will proceed without P/E data.")
        return pd.DataFrame(columns=['Stock', 'forwardPE', 'forwardEps'])

    try:
        logger.info(f"Loading financial data from {filepath}...")
        financials_df = pd.read_csv(filepath)
        financials_df['LastUpdated'] = pd.to_datetime(financials_df['LastUpdated'])
        latest_financials = financials_df.sort_values('LastUpdated').drop_duplicates(subset='Stock', keep='last')
        logger.info(f"Found latest financial data for {len(latest_financials)} stocks.")
        return latest_financials[['Stock', 'forwardPE', 'forwardEps']]
    except FileNotFoundError:
        logger.warning(f"Financials data file not found at '{filepath}'. Scoring will proceed without P/E data.")
        return pd.DataFrame(columns=['Stock', 'forwardPE', 'forwardEps'])


def calculate_individual_sharpe_ratios(stock_daily_returns: pd.DataFrame, params: Dict[str, Any]) -> pd.DataFrame:
    """Calculates Sharpe Ratio and its components for each stock."""
    risk_free_rate = params.get("risk_free_rate", 0.0)
    annualized_mean_returns = stock_daily_returns.mean() * 252
    annualized_std_devs = stock_daily_returns.std() * np.sqrt(252)
    sharpe_ratios = (annualized_mean_returns - risk_free_rate) / annualized_std_devs.replace(0, np.nan)
    sharpe_ratios = sharpe_ratios.fillna(0)

    return pd.DataFrame({
        'AnnualizedMeanReturn': annualized_mean_returns,
        'AnnualizedStdDev': annualized_std_devs,
        'SharpeRatio': sharpe_ratios
    }).reset_index()


def normalize_series(column: pd.Series) -> pd.Series:
    """Normalizes a pandas Series to a 0-1 scale using Min-Max scaling."""
    if pd.isna(column).all() or column.max() == column.min():
        return pd.Series(0.5, index=column.index)
    normalized = (column - column.min()) / (column.max() - column.min())
    return normalized.fillna(0)

# ----------------------------------------------------------- #
#                     Execution Pipeline                      #
# ----------------------------------------------------------- #

def main():
    """Main execution function for the scoring script."""
    # 1. --- Initial Setup ---
    overall_start_time = time.time()
    run_id = datetime.now().strftime('%Y%m%d-%H%M%S')
    script_dir = os.path.dirname(os.path.abspath(__file__))

    expected_params = {
        # From paths.txt
        "FINDB_FILE": str, "FINANCIALS_DB_FILE": str, "TICKERS_FILE": str,
        "WEB_ACCESSIBLE_DATA_PATH": str, "SCORING_PROGRESS_JSON_FILE": str,
        # From scorpar.txt
        "SCORED_STOCKS_DB_FILE": str, "SECTOR_PE_DB_FILE": str,
        "CORRELATION_MATRIX_FILE": str,
        "SCORING_LOG_FILE": str, "SCORING_PERFORMANCE_FILE": str,
        "debug_mode": bool, "risk_free_rate": float, "dynamic_score_weighting": bool,
        "momentum_enabled": bool, "momentum_period_days": int, "sharpe_weight": float,
        "upside_weight": float, "momentum_weight": float,
    }

    # 2. --- Load Parameters ---
    try:
        paths_file = os.path.join(script_dir, '..', 'parameters', 'paths.txt')
        scorpar_file = os.path.join(script_dir, '..', 'parameters', 'scorpar.txt')
        params = load_parameters_from_file(
            filepaths=[paths_file, scorpar_file],
            expected_parameters=expected_params
        )
    except (FileNotFoundError, Exception) as e:
        temp_logger = setup_logger("ScoringStartupLogger", "scoring_startup_error.log", None)
        temp_logger.critical(f"Could not load parameters. Exiting. Error: {e}", exc_info=True)
        print(f"CRITICAL: Could not load parameters. Exiting. Error: {e}")
        sys.exit(1)

    # 3. --- Setup Logger and Performance Tracking ---
    scoring_progress_file = params.get("SCORING_PROGRESS_JSON_FILE")
    logger = setup_logger(
        "ScoringRunner",
        log_file=params.get("SCORING_LOG_FILE"),
        web_log_file=scoring_progress_file,
        level=logging.DEBUG if params.get("debug_mode") else logging.INFO
    )
    perf_data = initialize_performance_data(SCORING_PY_VERSION)
    perf_data["param_load_duration_s"] = time.time() - overall_start_time

    logger.info("Starting Scoring.py execution pipeline.")

    try:
        # 4. --- Data Loading ---
        data_load_start_time = time.time()
        findb_file = params.get("FINDB_FILE")
        if not findb_file or not os.path.exists(findb_file):
            logger.critical(f"Master data file not found at '{findb_file}'. Cannot proceed.",
                            extra={'web_data': {"scoring_status": "Failed: Missing Master DB"}})
            sys.exit(1)
        all_stock_data_df = pd.read_csv(findb_file, parse_dates=['Date'])
        logger.info(f"Loaded {len(all_stock_data_df)} records from master data file.")

        stocks_with_sectors_df = load_input_stocks_with_sectors(params, logger)
        if stocks_with_sectors_df.empty:
            logger.critical("No valid stocks with sector data loaded. Aborting.",
                            extra={'web_data': {"scoring_status": "Failed: No Tickers"}})
            sys.exit(1)
        perf_data["stocks_loaded_from_input"] = len(stocks_with_sectors_df)

        financials_df = load_financials_data(params, logger)
        perf_data["data_load_duration_s"] = time.time() - data_load_start_time

        # 5. --- Scoring and Analysis ---
        analysis_start_time = time.time()
        logger.info("Starting scoring and analysis...")

        valid_tickers = stocks_with_sectors_df['Stock'].unique()
        filtered_stock_data = all_stock_data_df[all_stock_data_df['Stock'].isin(valid_tickers)].copy()
        daily_close_prices = filtered_stock_data.pivot(index='Date', columns='Stock', values='Close')
        daily_returns = daily_close_prices.pct_change(fill_method=None).dropna(how='all')
        current_prices_df = daily_close_prices.iloc[-1].reset_index(name='CurrentPrice')
        sharpe_df = calculate_individual_sharpe_ratios(daily_returns, params)
        sharpe_df.rename(columns={'index': 'Stock'}, inplace=True)
        if params.get("momentum_enabled", False):
            momentum_period = params.get("momentum_period_days", 126)
            momentum_returns = daily_close_prices.pct_change(periods=momentum_period, fill_method=None).iloc[-1]
            momentum_df = momentum_returns.reset_index(name='MomentumScore')
            momentum_df.fillna(0, inplace=True)
        else:
            momentum_df = pd.DataFrame(columns=['Stock', 'MomentumScore'])
        base_df = stocks_with_sectors_df.merge(financials_df, on='Stock', how='left')

        # Calculate and prepare historical sector P/E data
        sector_pe = base_df[base_df['forwardPE'] > 0].groupby('Sector')['forwardPE'].median().reset_index()
        sector_pe.rename(columns={'forwardPE': 'SectorMedianPE'}, inplace=True)
        sector_pe['run_id'] = run_id
        sector_pe['run_timestamp'] = perf_data['run_start_timestamp']
        sector_pe['scoring_version'] = SCORING_PY_VERSION

        # Reorder columns to the desired format
        final_sector_pe_columns = ['run_id', 'run_timestamp', 'scoring_version', 'Sector', 'SectorMedianPE']
        sector_pe = sector_pe[final_sector_pe_columns]

        analysis_df = base_df.merge(sector_pe[['Sector', 'SectorMedianPE']], on='Sector', how='left')
        analysis_df['UpsidePotential'] = ((analysis_df['SectorMedianPE'] / analysis_df['forwardPE']) - 1).fillna(0)
        analysis_df = analysis_df.merge(current_prices_df, on='Stock', how='left')
        analysis_df['TargetPrice'] = analysis_df['CurrentPrice'] * (1 + analysis_df['UpsidePotential'])

        scored_df = analysis_df.merge(sharpe_df, on='Stock', how='left')
        if not momentum_df.empty:
            scored_df = scored_df.merge(momentum_df, on='Stock', how='left')
        scored_df['SharpeNorm'] = normalize_series(scored_df['SharpeRatio'])
        scored_df['UpsideNorm'] = normalize_series(scored_df['UpsidePotential'])
        if 'MomentumScore' in scored_df.columns:
            scored_df['MomentumNorm'] = normalize_series(scored_df['MomentumScore'])
        else:
            scored_df['MomentumNorm'] = 0.0
        if params.get("dynamic_score_weighting"):
            logger.info("Using DYNAMIC weighting for composite score.")
            variances = {
                'sharpe': scored_df['SharpeNorm'].var(),
                'upside': scored_df['UpsideNorm'].var(),
                'momentum': scored_df['MomentumNorm'].var() if params.get("momentum_enabled") else 0
            }
            total_variance = sum(variances.values())
            weights = {k: v / total_variance for k, v in variances.items()} if total_variance > 0 else {'sharpe': 0.5,
                                                                                                        'upside': 0.5,
                                                                                                        'momentum': 0.0}
            logger.info(f"Dynamic weights calculated: {weights}")
        else:
            logger.info("Using STATIC weighting for composite score.")
            weights = {
                'sharpe': params.get("sharpe_weight", 0.5),
                'upside': params.get("upside_weight", 0.5),
                'momentum': params.get("momentum_weight", 0.0) if params.get("momentum_enabled") else 0.0
            }
        scored_df['CompositeScore'] = (
                scored_df['SharpeNorm'] * weights.get('sharpe', 0) +
                scored_df['UpsideNorm'] * weights.get('upside', 0) +
                scored_df['MomentumNorm'] * weights.get('momentum', 0)
        )
        scored_df['run_id'] = run_id
        scored_df['run_timestamp'] = perf_data['run_start_timestamp']
        scored_df['scoring_version'] = SCORING_PY_VERSION
        scored_df['sharpe_weight_used'] = weights.get('sharpe', 0)
        scored_df['upside_weight_used'] = weights.get('upside', 0)
        scored_df['momentum_weight_used'] = weights.get('momentum', 0)
        scored_df.sort_values(by='CompositeScore', ascending=False, inplace=True)
        perf_data["stocks_successfully_scored"] = len(scored_df)
        perf_data["scoring_and_analysis_duration_s"] = time.time() - analysis_start_time
        logger.info(f"Successfully scored {len(scored_df)} stocks.")

        # 6. --- Save Results ---
        save_start_time = time.time()
        logger.info("Saving scored stocks, sector P/E, and correlation data...",
                    extra={'web_data': {"scoring_status": "Running: Saving Results"}})

        scored_stocks_file = params.get("SCORED_STOCKS_DB_FILE")
        sector_pe_file = params.get("SECTOR_PE_DB_FILE")
        correlation_matrix_file = params.get("CORRELATION_MATRIX_FILE")

        # In /Users/gabrielcampos/PortfolioESG/engines/Scoring.py
        # ... inside the main() function, replacing the block that starts with rename_map ...

        # --- PROPOSED REPLACEMENT ---

        rename_map = {
            'UpsidePotential': 'PotentialUpside_pct', 'MomentumScore': 'Momentum',
            'SharpeNorm': 'SharpeRatio_norm', 'UpsideNorm': 'PotentialUpside_pct_norm',
            'MomentumNorm': 'Momentum_norm'
        }
        scored_df.rename(columns=rename_map, inplace=True)

        # --- MODIFICATION START ---
        # Add the hard filter to remove any stocks with 0% or negative upside potential.
        # This ensures that only undervalued stocks are passed to the portfolio engine.
        initial_count = len(scored_df)
        # We filter on the newly renamed 'PotentialUpside_pct' column.
        filtered_df = scored_df[scored_df['PotentialUpside_pct'] > 0].copy()
        filtered_count = len(filtered_df)

        logger.info(f"Filtered out {initial_count - filtered_count} stocks with zero or negative upside potential.")
        logger.info(f"Passing {filtered_count} high-scoring, undervalued stocks to the portfolio stage.")
        # --- MODIFICATION END ---

        final_column_order = [
            'run_id', 'run_timestamp', 'scoring_version', 'Stock', 'Name', 'Sector', 'Industry',
            'CompositeScore', 'SharpeRatio', 'PotentialUpside_pct', 'Momentum',
            'SharpeRatio_norm', 'PotentialUpside_pct_norm', 'Momentum_norm',
            'sharpe_weight_used', 'upside_weight_used', 'momentum_weight_used',
            'AnnualizedMeanReturn', 'AnnualizedStdDev', 'CurrentPrice', 'TargetPrice',
            'forwardPE', 'forwardEps', 'SectorMedianPE'
        ]
        # Use the newly filtered_df to create the final DataFrame
        final_df_to_save = filtered_df[[col for col in final_column_order if col in filtered_df.columns]]

        # --- END OF REPLACEMENT ---
        # The rest of the file (saving logic) remains the same.

        if correlation_matrix_file:
            try:
                top_20_tickers = final_df_to_save.head(20)['Stock'].tolist()
                if len(top_20_tickers) > 1:
                    top_20_returns = daily_returns[top_20_tickers]
                    correlation_df = top_20_returns.corr()
                    os.makedirs(os.path.dirname(correlation_matrix_file), exist_ok=True)
                    correlation_df.to_csv(correlation_matrix_file, index=True)
                    logger.info(f"Saved Top 20 stock correlation matrix to {correlation_matrix_file}")
                else:
                    logger.warning("Not enough stocks in the top 20 to calculate a correlation matrix.")
            except Exception as e:
                logger.error(f"Failed to create or save correlation matrix: {e}")

        if scored_stocks_file:
            os.makedirs(os.path.dirname(scored_stocks_file), exist_ok=True)
            file_exists = os.path.isfile(scored_stocks_file)
            final_df_to_save.to_csv(scored_stocks_file, mode='a', header=not file_exists, index=False)
            logger.info(f"Appended {len(final_df_to_save)} new records to {scored_stocks_file}")

        if sector_pe_file:
            os.makedirs(os.path.dirname(sector_pe_file), exist_ok=True)
            file_exists = os.path.isfile(sector_pe_file)
            sector_pe.to_csv(sector_pe_file, mode='a', header=not file_exists, index=False)
            logger.info(f"Appended {len(sector_pe)} new records to {sector_pe_file}")

        perf_data["results_save_duration_s"] = time.time() - save_start_time

    except Exception as e:
        logger.critical(f"An unhandled exception occurred in the main scoring pipeline: {e}", exc_info=True,
                        extra={'web_data': {"scoring_status": "Failed: Unhandled Exception"}})
    finally:
        # 7. --- Finalization and Logging ---
        perf_data["overall_script_duration_s"] = time.time() - overall_start_time
        log_performance_data(perf_data, params, logger)

        # Copy key results to the web-accessible directory
        copy_file_to_web_accessible_location("SCORED_STOCKS_DB_FILE", params, logger)
        copy_file_to_web_accessible_location("SECTOR_PE_DB_FILE", params, logger)
        copy_file_to_web_accessible_location("CORRELATION_MATRIX_FILE", params, logger)
        copy_file_to_web_accessible_location("SCORING_PERFORMANCE_FILE", params, logger)

        final_web_payload = {
            "scoring_status": "Completed",
            "scoring_start_time": perf_data.get("run_start_timestamp"),  # <-- ADD THIS LINE
            "scoring_end_time": datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
            "stocks_scored_count": perf_data.get("stocks_successfully_scored", 0)
        }
        logger.info(
            f"Scoring script finished in {perf_data['overall_script_duration_s']:.2f} seconds.",
            extra={'web_data': final_web_payload}
        )
        logger.info("Execution complete.")

if __name__ == "__main__":
    main()