#!/usr/bin/env python

# --- Script Version ---
SCORING_PY_VERSION = "3.0.0"  # Refactored to use shared_utils and new parameter/logging standards.

# ----------------------------------------------------------- #
#                           Libraries                         #
# ----------------------------------------------------------- #
import os
import sys
import csv
# Ensure project root is on sys.path so imports like `shared_tools` work when
# running engine scripts directly (python engines/A2_Scoring.py). When Python
# executes a script, sys.path[0] is the script's containing folder (engines/),
# which prevents sibling packages from being importable without this fix.
script_dir_boot = os.path.dirname(os.path.abspath(__file__))
project_root = os.path.abspath(os.path.join(script_dir_boot, '..'))
if project_root not in sys.path:
    sys.path.insert(0, project_root)

import pandas as pd
import numpy as np
import time, logging, json
from datetime import datetime
from typing import Any, Dict

# --- Use shared utilities for consistency ---
from shared_tools.shared_utils import (
    setup_logger,
    load_parameters_from_file,
    copy_file_to_web_accessible_location,
)
from shared_tools.path_utils import resolve_paths_in_params

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
    except (IOError, OSError) as log_err:
        logger.error(f"Failed to log performance data to '{log_path}': {log_err}")


def load_input_stocks_with_sectors(params: Dict[str, Any], logger: logging.Logger) -> pd.DataFrame:
    """Loads tickers, names, sectors, and industries, preparing them for scoring."""
    tickers_file_path = params.get("TICKERS_FILE")
    if not tickers_file_path:
        logger.critical("'TICKERS_FILE' not found in parameters. Cannot load stocks.")
        return pd.DataFrame()

    try:
        stocks_df = pd.read_csv(
            tickers_file_path, header=0,
            comment='#', skip_blank_lines=True, sep=','
        )
        # Ensure required columns exist
        for col in ['Ticker', 'Name', 'Sector', 'Industry']:
            if col not in stocks_df.columns:
                stocks_df[col] = None
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

        # Filter out tickers that are marked as invalid/delisted from consolidated skip file
        findb_path = params.get("FINDB_DIR") or os.path.dirname(params.get("FINDB_FILE", ""))
        if not findb_path:
            # Fallback to data/findb
            findb_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'data', 'findb')

        skipped_tickers_file = os.path.join(findb_path, 'skipped_tickers.json')
        invalid_tickers = []

        if os.path.exists(skipped_tickers_file):
            try:
                with open(skipped_tickers_file, 'r') as f:
                    all_skips = json.load(f)
                # Find all tickers with ["ALL"] skip status (permanently invalid)
                invalid_tickers = [ticker for ticker, skip_data in all_skips.items()
                                 if skip_data == ["ALL"]]
            except Exception as e:
                logger.warning(f"Could not read skipped_tickers.json: {e}")

        # Fallback: also check individual skip.json files (legacy support)
        findata_path = params.get("FINDATA_PATH") or params.get("findata_directory")
        if findata_path and os.path.exists(findata_path):
            for ticker in stocks_df['Ticker'].tolist():
                if ticker in invalid_tickers:
                    continue  # Already marked as invalid
                skip_file = os.path.join(findata_path, ticker, 'skip.json')
                if os.path.exists(skip_file):
                    try:
                        with open(skip_file, 'r') as f:
                            skip_data = json.load(f)
                        if skip_data == ["ALL"]:
                            invalid_tickers.append(ticker)
                    except Exception:
                        pass

        if invalid_tickers:
            logger.info(f"Filtering out {len(invalid_tickers)} invalid/delisted tickers from scoring")
            stocks_df = stocks_df[~stocks_df['Ticker'].isin(invalid_tickers)].copy()

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
        return pd.DataFrame(columns=['Stock', 'forwardPE', 'forwardEPS'])

    try:
        logger.info(f"Loading financial data from {filepath}...")
        financials_df = pd.read_csv(filepath)
        financials_df['LastUpdated'] = pd.to_datetime(financials_df['LastUpdated'])
        latest_financials = financials_df.sort_values('LastUpdated').drop_duplicates(subset='Stock', keep='last')
        logger.info(f"Found latest financial data for {len(latest_financials)} stocks.")
        return latest_financials[['Stock', 'forwardPE', 'forwardEPS']]
    except FileNotFoundError:
        logger.warning(f"Financials data file not found at '{filepath}'. Scoring will proceed without P/E data.")
        return pd.DataFrame(columns=['Stock', 'forwardPE', 'forwardEPS'])


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
    # Replace inf/-inf with NaN first, then handle
    clean_column = column.replace([np.inf, -np.inf], np.nan)

    if clean_column.isna().all() or clean_column.max() == clean_column.min():
        return pd.Series(0.5, index=column.index)

    normalized = (clean_column - clean_column.min()) / (clean_column.max() - clean_column.min())
    return normalized.fillna(0)


# ----------------------------------------------------------- #
#                Risk Profile & Market Regime                 #
# ----------------------------------------------------------- #

def load_risk_profile(params: Dict[str, Any], logger: logging.Logger) -> Dict[str, Any]:
    """Loads risk profile configuration from risk_profile.txt."""
    script_dir = os.path.dirname(os.path.abspath(__file__))
    risk_profile_path = os.path.join(script_dir, '..', 'parameters', 'risk_profile.txt')

    # Default values if file not found
    defaults = {
        'risk_profile': 'moderado',
        'profile_strength': 0.4,
        'auto_regime_detection': True,
        'regime_lookback_days': 60,
    }

    try:
        profile_params = load_parameters_from_file(risk_profile_path, {k: type(v) for k, v in defaults.items()})
        logger.info(f"Loaded risk profile: {profile_params.get('risk_profile', 'moderado')}, strength: {profile_params.get('profile_strength', 0.4)}")
        return profile_params
    except Exception as e:
        logger.warning(f"Could not load risk_profile.txt: {e}. Using defaults.")
        return defaults


def detect_market_regime(price_df: pd.DataFrame, lookback_days: int, risk_profile_params: Dict[str, Any], logger: logging.Logger) -> Dict[str, Any]:
    """
    Detects current market regime based on benchmark performance and volatility.

    Returns:
        Dict with 'regime' (str), 'volatility_percentile' (float), 'trend' (float)
    """
    # Get multipliers from config (with defaults)
    regime_mults = {
        'strong_bull': float(risk_profile_params.get('regime_strong_bull_mult', 1.5)),
        'bull': float(risk_profile_params.get('regime_bull_mult', 1.2)),
        'neutral': float(risk_profile_params.get('regime_neutral_mult', 1.0)),
        'bear': float(risk_profile_params.get('regime_bear_mult', 0.8)),
        'strong_bear': float(risk_profile_params.get('regime_strong_bear_mult', 0.6)),
    }

    # Get thresholds from config (with defaults)
    thresholds = {
        'strong_bull': float(risk_profile_params.get('regime_strong_bull_threshold', 0.20)),
        'bull': float(risk_profile_params.get('regime_bull_threshold', 0.05)),
        'bear': float(risk_profile_params.get('regime_bear_threshold', -0.05)),
        'strong_bear': float(risk_profile_params.get('regime_strong_bear_threshold', -0.20)),
        'bear_vol': float(risk_profile_params.get('regime_bear_vol_threshold', 0.85)),
    }

    try:
        # Use IBOV (^BVSP) or first available benchmark
        benchmark_cols = [col for col in price_df.columns if 'BVSP' in col or 'IBOV' in col]
        if not benchmark_cols:
            # Fallback: use mean of all stocks
            benchmark_series = price_df.mean(axis=1)
        else:
            benchmark_series = price_df[benchmark_cols[0]]

        # Get recent data
        recent = benchmark_series.tail(lookback_days).dropna()
        if len(recent) < 20:
            logger.warning("Insufficient data for regime detection. Assuming neutral.")
            return {'regime': 'neutral', 'volatility_percentile': 0.5, 'trend': 0.0, 'strength_mult': regime_mults['neutral']}

        # Calculate metrics
        returns = recent.pct_change().dropna()
        volatility = returns.std() * np.sqrt(252)  # Annualized
        trend = (recent.iloc[-1] / recent.iloc[0] - 1) * (252 / len(recent))  # Annualized return

        # Historical volatility percentile (compare to full history)
        full_returns = price_df.mean(axis=1).pct_change().dropna()
        rolling_vol = full_returns.rolling(lookback_days).std() * np.sqrt(252)
        vol_percentile = (rolling_vol < volatility).mean() if len(rolling_vol) > 0 else 0.5

        # Determine regime using parametrized thresholds
        if trend > thresholds['strong_bull'] and vol_percentile < 0.7:
            regime = 'strong_bull'
        elif trend > thresholds['bull']:
            regime = 'bull'
        elif trend < thresholds['strong_bear'] or vol_percentile > thresholds['bear_vol']:
            regime = 'strong_bear'
        elif trend < thresholds['bear']:
            regime = 'bear'
        else:
            regime = 'neutral'

        strength_mult = regime_mults.get(regime, 1.0)

        logger.info(f"Market regime detected: {regime} (trend: {trend:.2%}, vol_percentile: {vol_percentile:.2f}, strength_mult: {strength_mult})")

        return {
            'regime': regime,
            'volatility_percentile': vol_percentile,
            'trend': trend,
            'strength_mult': strength_mult
        }

    except (KeyError, ValueError, ZeroDivisionError) as regime_err:
        logger.warning(f"Error detecting market regime: {regime_err}. Assuming neutral.")
        return {'regime': 'neutral', 'volatility_percentile': 0.5, 'trend': 0.0, 'strength_mult': regime_mults['neutral']}


def adjust_weights_with_risk_profile(
    base_weights: Dict[str, float],
    risk_profile_params: Dict[str, Any],
    market_regime: Dict[str, Any],
    logger: logging.Logger
) -> Dict[str, float]:
    """
    Adjusts dynamic weights based on risk profile and market regime.

    The adjustment uses interpolation between the pure dynamic weights
    and the profile's central tendencies, modified by the current market regime.

    Formula:
        adjusted_weight = (1 - effective_strength) * base_weight + effective_strength * (tendency * multiplier)

    Args:
        base_weights: Dict with 'sharpe', 'upside', 'momentum' weights from variance calculation
        risk_profile_params: Configuration from risk_profile.txt
        market_regime: Output from detect_market_regime()
        logger: Logger instance

    Returns:
        Dict with adjusted weights (normalized to sum to 1.0)
    """
    profile = str(risk_profile_params.get('risk_profile', 'moderado')).lower()
    base_strength = float(risk_profile_params.get('profile_strength', 0.4))
    auto_regime = risk_profile_params.get('auto_regime_detection', True)
    if isinstance(auto_regime, str):
        auto_regime = auto_regime.lower() == 'true'

    # Get profile tendencies and multipliers (convert to float)
    tendencies = {
        'sharpe': float(risk_profile_params.get(f'{profile}_sharpe_tendency', 0.40)),
        'upside': float(risk_profile_params.get(f'{profile}_upside_tendency', 0.35)),
        'momentum': float(risk_profile_params.get(f'{profile}_momentum_tendency', 0.25)),
    }

    multipliers = {
        'sharpe': float(risk_profile_params.get(f'{profile}_sharpe_mult', 1.0)),
        'upside': float(risk_profile_params.get(f'{profile}_upside_mult', 1.0)),
        'momentum': float(risk_profile_params.get(f'{profile}_momentum_mult', 1.0)),
    }

    # Adjust strength based on market regime if auto-detection is enabled
    if auto_regime:
        regime_mult = float(market_regime.get('strength_mult', 1.0))
        effective_strength = min(1.0, base_strength * regime_mult)
        logger.info(f"Risk profile strength adjusted for {market_regime['regime']} regime: {base_strength:.2f} -> {effective_strength:.2f}")
    else:
        effective_strength = base_strength

    # Calculate adjusted weights
    adjusted = {}
    for metric in ['sharpe', 'upside', 'momentum']:
        base = float(base_weights.get(metric, 0.0))
        tendency = float(tendencies.get(metric, base))
        mult = float(multipliers.get(metric, 1.0))

        # Interpolate between dynamic and profile preference
        target = tendency * mult
        adjusted[metric] = (1.0 - effective_strength) * base + effective_strength * target

    # Normalize to sum to 1.0
    total = sum(adjusted.values())
    if total > 0:
        adjusted = {k: v / total for k, v in adjusted.items()}

    logger.info(f"Weights adjusted with {profile} profile: sharpe={adjusted['sharpe']:.3f}, upside={adjusted['upside']:.3f}, momentum={adjusted['momentum']:.3f}")

    return adjusted


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
        # Normalize paths so they work on this machine/repo
        params = resolve_paths_in_params(params, script_dir, None)
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

    logger.info("Starting A2_Scoring.py execution pipeline.")

    script_failed = False  # Track if script encountered an error

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
        logger.info(f"Looking for price data for {len(valid_tickers)} stocks")

        filtered_stock_data = all_stock_data_df[all_stock_data_df['Stock'].isin(valid_tickers)].copy()
        logger.info(f"Found {len(filtered_stock_data)} price records matching the stocks")

        if filtered_stock_data.empty:
            # Log which stocks are in the DB vs what we're looking for
            stocks_in_db = set(all_stock_data_df['Stock'].unique())
            missing_stocks = set(valid_tickers) - stocks_in_db
            logger.error(f"No matching stocks found. Stocks in DB: {len(stocks_in_db)}, Looking for: {len(valid_tickers)}")
            if missing_stocks:
                logger.error(f"Sample of missing stocks: {list(missing_stocks)[:10]}")
            logger.critical("No price data available for any of the loaded stocks.",
                           extra={'web_data': {"scoring_status": "Failed: No Matching Stocks"}})
            sys.exit(1)

        daily_close_prices = filtered_stock_data.pivot(index='Date', columns='Stock', values='Close')

        # Check if we have price data before proceeding
        if daily_close_prices.empty:
            logger.critical("No price data available for the loaded stocks. Check if download was successful.",
                           extra={'web_data': {"scoring_status": "Failed: No Price Data"}})
            sys.exit(1)

        daily_returns = daily_close_prices.pct_change(fill_method=None).dropna(how='all')
        current_prices_df = daily_close_prices.iloc[-1].reset_index(name='CurrentPrice')
        sharpe_df = calculate_individual_sharpe_ratios(daily_returns, params)
        sharpe_df.rename(columns={'index': 'Stock'}, inplace=True)
        if params.get("momentum_enabled", False):
            momentum_period = params.get("momentum_period_days", 126)
            if len(daily_close_prices) > momentum_period:
                momentum_returns = daily_close_prices.pct_change(periods=momentum_period, fill_method=None).iloc[-1]
                momentum_df = momentum_returns.reset_index(name='MomentumScore')
                momentum_df.fillna(0, inplace=True)
            else:
                logger.warning(f"Not enough data for momentum calculation. Need {momentum_period} days, have {len(daily_close_prices)}.")
                momentum_df = pd.DataFrame(columns=['Stock', 'MomentumScore'])
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
        analysis_df = analysis_df.merge(current_prices_df, on='Stock', how='left')

        # Calculate UpsidePotential: prefer Yahoo Finance targetMeanPrice, fallback to SectorMedianPE method
        # Method 1: Direct from Yahoo Finance targetMeanPrice
        if 'targetMeanPrice' in analysis_df.columns:
            has_target = analysis_df['targetMeanPrice'].notna() & (analysis_df['targetMeanPrice'] > 0)
            has_current = analysis_df['CurrentPrice'].notna() & (analysis_df['CurrentPrice'] > 0)
            valid_target_mask = has_target & has_current

            # Calculate upside from Yahoo target price
            analysis_df.loc[valid_target_mask, 'UpsidePotential'] = (
                (analysis_df.loc[valid_target_mask, 'targetMeanPrice'] /
                 analysis_df.loc[valid_target_mask, 'CurrentPrice']) - 1
            )
            analysis_df.loc[valid_target_mask, 'TargetPrice'] = analysis_df.loc[valid_target_mask, 'targetMeanPrice']
            analysis_df.loc[valid_target_mask, 'TargetPriceSource'] = 'YahooFinance'

            yahoo_count = valid_target_mask.sum()
            logger.info(f"Using Yahoo Finance targetMeanPrice for {yahoo_count} stocks")
        else:
            valid_target_mask = pd.Series(False, index=analysis_df.index)
            yahoo_count = 0

        # Method 2: Fallback - calculate from SectorMedianPE for stocks without Yahoo target
        fallback_mask = ~valid_target_mask & analysis_df['CurrentPrice'].notna() & (analysis_df['CurrentPrice'] > 0)
        safe_forward_pe = analysis_df['forwardPE'].replace(0, np.nan)
        fallback_upside = ((analysis_df['SectorMedianPE'] / safe_forward_pe) - 1)

        analysis_df.loc[fallback_mask, 'UpsidePotential'] = fallback_upside.loc[fallback_mask].fillna(0)
        analysis_df.loc[fallback_mask, 'TargetPrice'] = (
            analysis_df.loc[fallback_mask, 'CurrentPrice'] *
            (1 + analysis_df.loc[fallback_mask, 'UpsidePotential'])
        )
        analysis_df.loc[fallback_mask, 'TargetPriceSource'] = 'SectorPE_Fallback'

        fallback_count = fallback_mask.sum()
        if fallback_count > 0:
            logger.info(f"Using SectorMedianPE fallback for {fallback_count} stocks")

        # Fill any remaining NaN values
        analysis_df['UpsidePotential'] = analysis_df['UpsidePotential'].fillna(0)
        analysis_df['TargetPriceSource'] = analysis_df['TargetPriceSource'].fillna('None')

        # Cap extreme values to avoid inf affecting normalization
        analysis_df['UpsidePotential'] = analysis_df['UpsidePotential'].clip(lower=-0.99, upper=10.0)

        scored_df = analysis_df.merge(sharpe_df, on='Stock', how='left')
        if not momentum_df.empty:
            scored_df = scored_df.merge(momentum_df, on='Stock', how='left')
        scored_df['SharpeNorm'] = normalize_series(scored_df['SharpeRatio'])
        scored_df['UpsideNorm'] = normalize_series(scored_df['UpsidePotential'])
        if 'MomentumScore' in scored_df.columns:
            scored_df['MomentumNorm'] = normalize_series(scored_df['MomentumScore'])
        else:
            scored_df['MomentumNorm'] = 0.0

        # Load risk profile configuration
        risk_profile_params = load_risk_profile(params, logger)

        # Detect market regime for adaptive adjustment
        market_regime = {'regime': 'neutral', 'strength_mult': 1.0}
        if risk_profile_params.get('auto_regime_detection', True):
            lookback = risk_profile_params.get('regime_lookback_days', 60)
            if isinstance(lookback, str):
                lookback = int(lookback)
            market_regime = detect_market_regime(daily_close_prices, lookback, risk_profile_params, logger)

        if params.get("dynamic_score_weighting"):
            logger.info("Using DYNAMIC weighting for composite score.")
            variances = {
                'sharpe': scored_df['SharpeNorm'].var(),
                'upside': scored_df['UpsideNorm'].var(),
                'momentum': scored_df['MomentumNorm'].var() if params.get("momentum_enabled") else 0
            }
            total_variance = sum(variances.values())
            base_weights = {k: v / total_variance for k, v in variances.items()} if total_variance > 0 else {'sharpe': 0.5,
                                                                                                        'upside': 0.5,
                                                                                                        'momentum': 0.0}
            logger.info(f"Base dynamic weights (variance-based): {base_weights}")

            # Adjust weights with risk profile
            weights = adjust_weights_with_risk_profile(base_weights, risk_profile_params, market_regime, logger)
            logger.info(f"Final weights (profile-adjusted): {weights}")
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
        scored_df['risk_profile_used'] = risk_profile_params.get('risk_profile', 'moderado')
        scored_df['market_regime'] = market_regime.get('regime', 'neutral')
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

        # Rename columns for downstream compatibility
        rename_map = {
            'UpsidePotential': 'PotentialUpside_pct', 'MomentumScore': 'Momentum',
            'SharpeNorm': 'SharpeRatio_norm', 'UpsideNorm': 'PotentialUpside_pct_norm',
            'MomentumNorm': 'Momentum_norm'
        }
        columns_to_rename = {k: v for k, v in rename_map.items() if k in scored_df.columns}
        scored_df.rename(columns=columns_to_rename, inplace=True)

        # Filter out stocks with zero or negative upside potential (after renaming)
        if 'PotentialUpside_pct' in scored_df.columns:
            initial_count = len(scored_df)
            filtered_df = scored_df[scored_df['PotentialUpside_pct'] > 0].copy()
            filtered_count = len(filtered_df)
            logger.info(f"Filtered out {initial_count - filtered_count} stocks with zero or negative upside potential.")
            logger.info(f"Passing {filtered_count} high-scoring, undervalued stocks to the portfolio stage.")
        else:
            filtered_df = scored_df.copy()
            logger.warning("Column 'PotentialUpside_pct' not found after renaming. No upside filter applied.")

        # Filter out stocks with missing CurrentPrice or TargetPrice - they can't be properly evaluated
        if 'CurrentPrice' in filtered_df.columns and 'TargetPrice' in filtered_df.columns:
            pre_filter_count = len(filtered_df)
            filtered_df = filtered_df[
                filtered_df['CurrentPrice'].notna() &
                (filtered_df['CurrentPrice'] > 0) &
                filtered_df['TargetPrice'].notna() &
                (filtered_df['TargetPrice'] > 0)
            ].copy()
            price_filtered_count = pre_filter_count - len(filtered_df)
            if price_filtered_count > 0:
                logger.info(f"Filtered out {price_filtered_count} stocks with missing or invalid CurrentPrice/TargetPrice.")

        # Filter out stocks with forwardPE = 0 (invalid data from Yahoo Finance)
        if 'forwardPE' in filtered_df.columns:
            pre_filter_count = len(filtered_df)
            filtered_df = filtered_df[
                filtered_df['forwardPE'].notna() &
                (filtered_df['forwardPE'] > 0)
            ].copy()
            pe_filtered_count = pre_filter_count - len(filtered_df)
            if pe_filtered_count > 0:
                logger.info(f"Filtered out {pe_filtered_count} stocks with missing or zero forwardPE.")

        # Validate required columns for downstream use
        required_columns = [
            'run_id', 'run_timestamp', 'scoring_version', 'Stock', 'Name', 'Sector', 'Industry',
            'CompositeScore', 'SharpeRatio', 'PotentialUpside_pct', 'Momentum',
            'SharpeRatio_norm', 'PotentialUpside_pct_norm', 'Momentum_norm',
            'sharpe_weight_used', 'upside_weight_used', 'momentum_weight_used',
            'AnnualizedMeanReturn', 'AnnualizedStdDev', 'CurrentPrice', 'TargetPrice',
            'TargetPriceSource', 'forwardPE', 'forwardEPS', 'SectorMedianPE'
        ]
        missing_columns = [col for col in required_columns if col not in filtered_df.columns]
        if missing_columns:
            logger.warning(f"The following required columns are missing in the output: {missing_columns}")
        final_df_to_save = filtered_df[[col for col in required_columns if col in filtered_df.columns]].copy()

        # Only sort and drop duplicates if necessary
        if 'CompositeScore' in final_df_to_save.columns:
            final_df_to_save = final_df_to_save.sort_values(by='CompositeScore', ascending=False)
        if 'Stock' in final_df_to_save.columns:
            final_df_to_save = final_df_to_save.drop_duplicates(subset=['Stock'], keep='first')


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
            final_df_to_save.to_csv(scored_stocks_file, mode='a', header=not file_exists, index=False, quoting=csv.QUOTE_MINIMAL)
            logger.info(f"Appended {len(final_df_to_save)} new records to {scored_stocks_file}")

        if sector_pe_file:
            os.makedirs(os.path.dirname(sector_pe_file), exist_ok=True)
            file_exists = os.path.isfile(sector_pe_file)
            sector_pe.to_csv(sector_pe_file, mode='a', header=not file_exists, index=False)
            logger.info(f"Appended {len(sector_pe)} new records to {sector_pe_file}")

        perf_data["results_save_duration_s"] = time.time() - save_start_time
        script_failed = False

    except Exception as e:
        logger.critical(f"An unhandled exception occurred in the main scoring pipeline: {e}", exc_info=True,
                        extra={'web_data': {"scoring_status": "Failed: Unhandled Exception"}})
        script_failed = True
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
            "scoring_status": "Failed" if script_failed else "Completed",
            "scoring_start_time": perf_data.get("run_start_timestamp"),  # <-- ADD THIS LINE
            "scoring_end_time": datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
            "stocks_scored_count": perf_data.get("stocks_successfully_scored", 0)
        }
        logger.info(
            f"Scoring script finished in {perf_data['overall_script_duration_s']:.2f} seconds.",
            extra={'web_data': final_web_payload}
        )
        logger.info("Execution complete.")

        # Exit with error code if script failed
        if script_failed:
            sys.exit(1)

if __name__ == "__main__":
    main()