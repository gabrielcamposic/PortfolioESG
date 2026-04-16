#!/usr/bin/env python

# --- Script Version ---
PORTFOLIO_PY_VERSION = "2.1.0"  # Performance improvements.

# ----------------------------------------------------------- #
#                           Libraries                         #
# ----------------------------------------------------------- #
import pandas as pd, collections
import numpy as np
import os, sys, time, json, shutil, logging, itertools, random, csv
from datetime import datetime, timedelta
from collections import Counter
from typing import Dict, Any, List, Tuple
from numbers import Real
import math

# --- Import Shared Utilities ---
from shared_tools.shared_utils import (
    setup_logger,
    load_parameters_from_file
)
from engines.A2_Scoring import detect_market_regime, load_risk_profile

# ----------------------------------------------------------- #
#                           Classes                           #
# ----------------------------------------------------------- #

# -------- (I) Time tracking --------
class ExecutionTimer:
    def __init__(self, rolling_window=10):
        self.start_time = None
        self.rolling_window = rolling_window  # Number of recent simulations to consider
        # Use a deque to automatically keep only the last 'rolling_window' times
        self.recent_times = collections.deque(maxlen=self.rolling_window)

    def start(self):
        """Start a new timing session."""
        if self.start_time is not None:  # Ensure the timer is not already running
            raise RuntimeError("Timer is already running. Call stop() before starting again.")  # Raise error if already running
        self.start_time = time.time()

    def stop(self):
        """Stop timing and record the elapsed time."""
        if self.start_time is None:  # Ensure the timer is running
            raise RuntimeError("Timer is not running. Call start() before stopping.")  # Raise error if not running
        elapsed = time.time() - self.start_time
        self.start_time = None
        self.recent_times.append(elapsed)
        return elapsed

    def estimate_remaining(self, total_runs, completed_runs):
        """Estimate remaining time based on rolling average execution time."""
        if not self.recent_times or completed_runs == 0:
            return None  # Avoid division by zero
        avg_time = sum(self.recent_times) / len(self.recent_times)
        remaining_runs = total_runs - completed_runs
        remaining_time = remaining_runs * avg_time
        return timedelta(seconds=remaining_time)

# ----------------------------------------------------------- #
#                        Helper Functions                     #
# ----------------------------------------------------------- #

def initialize_performance_data(script_version: str) -> Dict[str, Any]:
    """Creates and initializes a dictionary to track script performance metrics."""
    return {
        "run_id": os.environ.get('PIPELINE_RUN_ID', ''),
        "run_start_timestamp": datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
        "portfolio_py_version": script_version,
        "param_load_duration_s": 0.0,
        "data_load_duration_s": 0.0,
        "data_wrangling_duration_s": 0.0,
        "bf_phase_duration_s": 0.0,
        "ga_phase_duration_s": 0.0,
        "refinement_phase_duration_s": 0.0,
        "results_save_duration_s": 0.0,
        "overall_script_duration_s": 0.0,
    }

def log_performance_data(perf_data: Dict, params: Dict, logger: logging.Logger):
    """Logs the script's performance metrics to a CSV file."""
    log_path = params.get("PORTFOLIO_PERFORMANCE_FILE")
    if not log_path:
        logger.warning("'PORTFOLIO_PERFORMANCE_FILE' not in params. Skipping performance logging.")
        return
    try:
        df = pd.DataFrame([perf_data])
        os.makedirs(os.path.dirname(log_path), exist_ok=True)
        df.to_csv(log_path, mode='a', header=not os.path.exists(log_path), index=False)
        logger.info(f"Successfully logged performance data to: {log_path}")
    except Exception as e:
        logger.error(f"Failed to log performance data to '{log_path}': {e}")

def copy_file_to_web_accessible_location(source_param_key: str, params: Dict, logger: logging.Logger):
    """Copies a file to the web-accessible data directory."""
    source_path = params.get(source_param_key)
    dest_folder = params.get("WEB_ACCESSIBLE_DATA_PATH")
    if not isinstance(source_path, str) or not source_path:
        logger.warning(f"Parameter '{source_param_key}' is missing or invalid. Cannot copy file.")
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
        # Check if source and destination are the same file
        if os.path.realpath(source_path) == os.path.realpath(destination_path):
            logger.debug(f"Source and destination are the same file for '{source_param_key}'. Skipping copy.")
            return
        shutil.copy2(source_path, destination_path)
        logger.info(f"Copied '{os.path.basename(source_path)}' to web-accessible location.")
    except Exception as e:
        logger.error(f"Failed to copy file from '{source_path}' to '{dest_folder}': {e}")

def load_scored_stocks(params: Dict, logger: logging.Logger) -> Tuple[List[str], Dict[str, str], str]:
    """Loads the top N scored stocks from the most recent scoring run.

    Returns:
        Tuple of (top_stocks, stock_to_sector_map, scoring_run_id)
    """
    filepath = params.get("SCORED_STOCKS_DB_FILE")
    top_n = params.get("top_n_stocks_from_score", 50)
    if not filepath:
        logger.critical("'SCORED_STOCKS_DB_FILE' not defined in parameters.")
        raise FileNotFoundError("Scored stocks file path is not configured.")

    if not os.path.exists(filepath):
        logger.critical(f"Scored stocks file not found at '{filepath}'.")
        raise FileNotFoundError(f"Scored stocks file not found at '{filepath}'.")

    # Load permanently skipped tickers to filter them out
    skipped_tickers = set()
    findb_path = params.get("FINDB_DIR") or os.path.dirname(params.get("FINDB_FILE", ""))
    if not findb_path:
        findb_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'data', 'findb')

    # Try JSONL first (Phase 3.5 format), fall back to legacy JSON
    skipped_jsonl = os.path.join(findb_path, 'skipped_tickers.jsonl')
    skipped_json = os.path.join(findb_path, 'skipped_tickers.json')
    if os.path.exists(skipped_jsonl):
        try:
            all_skips = {}
            with open(skipped_jsonl, 'r', encoding='utf-8') as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    entry = json.loads(line)
                    all_skips[entry['ticker']] = entry['skip_data']
            skipped_tickers = {ticker for ticker, skip_data in all_skips.items()
                             if skip_data == ["ALL"]}
            logger.info(f"Loaded {len(skipped_tickers)} permanently skipped tickers from JSONL")
        except Exception as e:
            logger.warning(f"Could not read skipped_tickers.jsonl: {e}")
    elif os.path.exists(skipped_json):
        try:
            with open(skipped_json, 'r') as f:
                all_skips = json.load(f)
            skipped_tickers = {ticker for ticker, skip_data in all_skips.items()
                             if skip_data == ["ALL"]}
            logger.info(f"Loaded {len(skipped_tickers)} permanently skipped tickers from legacy JSON")
        except Exception as e:
            logger.warning(f"Could not read skipped_tickers.json: {e}")

    try:
        df: pd.DataFrame = pd.read_csv(filepath)
        required_cols = ['run_id', 'CompositeScore', 'Stock', 'Sector']
        if not all(col in df.columns for col in required_cols):
            raise ValueError(f"Scored stocks file is missing one or more required columns: {required_cols}")

        latest_run_id = df['run_id'].max()
        scoring_run_id = str(latest_run_id)
        # Explicitly construct a DataFrame view to help static analysis infer the correct type
        latest_run_df = pd.DataFrame(df.loc[df['run_id'] == latest_run_id]).copy()

        # Filter out permanently skipped tickers
        if skipped_tickers:
            pre_filter_count = len(latest_run_df)
            latest_run_df = latest_run_df[~latest_run_df['Stock'].isin(skipped_tickers)]
            filtered_count = pre_filter_count - len(latest_run_df)
            if filtered_count > 0:
                logger.info(f"Filtered out {filtered_count} permanently skipped tickers from portfolio candidates")

        # Use non-inplace sort to avoid type-narrowing issues with Series.sort_values
        latest_run_df = latest_run_df.sort_values(by=['CompositeScore'], ascending=False)
        top_stocks_df = latest_run_df.head(top_n)
        top_stocks = top_stocks_df['Stock'].tolist()
        # Use set_index/to_dict to build a mapping; avoids use of .values which can confuse type inference
        stock_to_sector_map = top_stocks_df.set_index('Stock')['Sector'].to_dict()
        # Hybrid approach (Option C): CompositeScore is used for ranking/filtering (Top N),
        # but the MVO optimizer uses PotentialUpside_pct directly as the projected return signal.
        # This aligns the optimization objective with Motor C's expected return calculation.
        upside_col = 'PotentialUpside_pct' if 'PotentialUpside_pct' in top_stocks_df.columns else 'UpsidePotential'
        if upside_col in top_stocks_df.columns:
            stock_to_upside_map = top_stocks_df.set_index('Stock')[upside_col].to_dict()
            logger.info(f"Using '{upside_col}' as optimization signal (Hybrid Option C).")
        else:
            stock_to_upside_map = top_stocks_df.set_index('Stock')['CompositeScore'].to_dict()
            logger.warning(f"Upside column not found, falling back to CompositeScore as optimization signal.")

        logger.info(f"Loaded {len(top_stocks)} top stocks from scoring run '{scoring_run_id}'.")
        if params.get('debug_mode'):
            logger.debug(f"Top stocks: {', '.join(top_stocks)}")
        return top_stocks, stock_to_sector_map, scoring_run_id, stock_to_upside_map
    except Exception as e:
        logger.critical(f"Failed to read or parse scored stocks file '{filepath}': {e}", exc_info=True)
        raise

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

def calculate_blended_returns(
    mean_returns_annualized: pd.Series,
    upside_map: dict,
    vol_percentile: float,
    trend: float,
    params: dict
) -> pd.Series:
    """Calculates synthetic return blending historical (past) and upside (future)."""
    high_vol = vol_percentile > float(params.get('regime_vol_threshold', 0.70))
    bull = trend > float(params.get('regime_bull_threshold', 0.05))
    bear = trend < float(params.get('regime_bear_threshold', -0.05))
    
    if high_vol and bull:
        w_past = float(params.get('blend_highvol_bull_past', 0.70))
    elif high_vol:
        w_past = float(params.get('blend_highvol_bear_past', 0.80))
    elif bull:
        w_past = float(params.get('blend_lowvol_bull_past', 0.30))
    else:
        w_past = float(params.get('blend_lowvol_bear_past', 0.40))
        
    w_future = 1.0 - w_past
    
    blended = pd.Series(index=mean_returns_annualized.index, dtype=float)
    for stock in blended.index:
        hist = mean_returns_annualized[stock]
        fwd = float(upside_map.get(stock, hist))  # Fallback to historical if missing
        blended[stock] = w_past * hist + w_future * fwd
        
    return blended

def generate_portfolio_weights(n, seed=None):
    """Generates random portfolio weights that sum to 1."""
    if seed is not None:
        np.random.seed(seed)
    weights = np.random.rand(n) # Use np.random.rand for [0,1)
    sum_weights = np.sum(weights)
    if sum_weights == 0:  # Highly unlikely, but handles division by zero
        return np.ones(n) / n  # Return equal weights
    return weights / sum_weights

def _calculate_portfolio_metrics_from_precomputed(
    weights: np.ndarray,
    mean_returns_annualized: pd.Series,
    covariance_matrix_annualized: pd.DataFrame,
    rf_rate: float,
    blended_returns: pd.Series = None
) -> Tuple[float, float, float]:
    """
    Calculates core portfolio metrics using pre-computed returns and covariance.
    This is the fast, vectorized core of the simulation engine.
    """
    # Ensure weights is a NumPy array for dot product
    weights_arr = np.array(weights)
    exp_ret = np.dot(weights_arr, mean_returns_annualized)
    vol = np.sqrt(np.dot(weights_arr.T, np.dot(covariance_matrix_annualized, weights_arr)))
    
    if blended_returns is not None:
        proj_score = np.dot(weights_arr, blended_returns)
        sharpe = (proj_score - rf_rate) / vol if vol != 0 else -np.inf
    else:
        sharpe = (exp_ret - rf_rate) / vol if vol != 0 else -np.inf
        
    return exp_ret, vol, sharpe

def simulation_engine_calc(
    stock_combo_prices_df,  # DataFrame with 'Date' and prices for the selected stock combo
    weights,
    current_rf_rate,  # Annual decimal risk-free rate
    logger_instance,
    blended_returns_map=None
):
    """
    Calculates forward-looking (ex-ante) portfolio metrics for optimization.
    This is now a thin wrapper aroung the core vectorized calculation.
    """
    try:
        # Calculate returns of the individual assets in the combo
        # Assumes stock_combo_prices_df has 'Date' as first column
        asset_returns_df = stock_combo_prices_df.iloc[:, 1:].pct_change().fillna(0)

        # Pre-calculate the slow parts
        mean_asset_returns_annualized = asset_returns_df.mean() * 252
        covariance_matrix_annualized = asset_returns_df.cov() * 252
        
        combo_blended_returns = None
        if blended_returns_map is not None:
            stocks = stock_combo_prices_df.columns[1:]
            projected_scores_data = [blended_returns_map.get(s, mean_asset_returns_annualized[s]) for s in stocks]
            combo_blended_returns = pd.Series(projected_scores_data, index=stocks)

        # Use the centralized, vectorized calculation function
        expected_portfolio_return_decimal, expected_volatility_decimal, sharpe_ratio = \
            _calculate_portfolio_metrics_from_precomputed(
                weights, mean_asset_returns_annualized,
                covariance_matrix_annualized, current_rf_rate,
                blended_returns=combo_blended_returns
            )

        return expected_portfolio_return_decimal, expected_volatility_decimal, sharpe_ratio

    except Exception as e:
        # Log more specific error if possible
        stock_names = list(stock_combo_prices_df.columns[1:]) if not stock_combo_prices_df.empty else "N/A"
        logger_instance.info(f"❌ Error in simulation_engine_calc: {e} for stocks {stock_names}")
        return np.nan, np.nan, np.nan

# ----------------------------------------------
# 1. Extract Simulation Parameters
# ----------------------------------------------
def extract_simulation_parameters(sim_params):
    return {
        "SIM_RUNS": sim_params.get("sim_runs", 100),
        "ADAPTIVE_SIM_ENABLED": sim_params.get("adaptive_sim_enabled", True),
        "PROGRESSIVE_MIN_SIMS": sim_params.get("progressive_min_sims", 200),
        "PROGRESSIVE_BASE_LOG_K": sim_params.get("progressive_base_log_k", 500),
        "PROGRESSIVE_MAX_SIMS_CAP": sim_params.get("progressive_max_sims_cap", 3000),
        "PROGRESSIVE_CONVERGENCE_WINDOW": sim_params.get("progressive_convergence_window", 50),
        "PROGRESSIVE_CONVERGENCE_DELTA": sim_params.get("progressive_convergence_delta", 0.005),
        "PROGRESSIVE_CHECK_INTERVAL": sim_params.get("progressive_check_interval", 50),
        "TOP_N_PERCENT_REFINEMENT": sim_params.get("top_n_percent_refinement", 0.10),
        "HEURISTIC_THRESHOLD_K": sim_params.get("heuristic_threshold_k", 9),
        "INITIAL_SCAN_SIMS": sim_params.get("initial_scan_sims", 200),
        "EARLY_DISCARD_FACTOR": sim_params.get("early_discard_factor", 0.75),
        "EARLY_DISCARD_MIN_BEST_SHARPE": sim_params.get("early_discard_min_best_sharpe", 0.1),
        "DEBUG_MODE": sim_params.get("debug_mode", False),
        "GA_POPULATION_SIZE": sim_params.get("ga_population_size", 50),
        "GA_NUM_GENERATIONS": sim_params.get("ga_num_generations", 30),
        "GA_MUTATION_RATE": sim_params.get("ga_mutation_rate", 0.02),
        "GA_CROSSOVER_RATE": sim_params.get("ga_crossover_rate", 0.8),
        "GA_ELITISM_COUNT": sim_params.get("ga_elitism_count", 2),
        "GA_TOURNAMENT_SIZE": sim_params.get("ga_tournament_size", 3),
        "GA_CONVERGENCE_GENERATIONS": sim_params.get("ga_convergence_generations", 10),
        "GA_CONVERGENCE_TOLERANCE": sim_params.get("ga_convergence_tolerance", 0.0001),
        "BF_PROGRESS_LOG_STEP": float(sim_params.get("bf_progress_log_step", 5)),
        "GA_INIT_POP_MAX_ATTEMPTS_MULTIPLIER": sim_params.get("ga_init_pop_max_attempts_multiplier", 5)
    }

# ----------------------------------------------
# 2. Filter Available Stocks
# ----------------------------------------------
def filter_available_stocks(source_df, stock_list):
    return [s for s in stock_list if s in source_df.columns]

# ----------------------------------------------
# 3. Simulate Portfolio Combination
# ----------------------------------------------
def simulate_portfolio_combo(df_subset, num_sims, rf_rate, logger, blended_returns_map=None):
    """
    Optimized simulation for a single stock combination.
    Used by the Genetic Algorithm and Refinement phases.
    """
    # --- PERFORMANCE OPTIMIZATION ---
    # Pre-calculate returns and annualized metrics ONCE for this combination.
    asset_returns_df = df_subset.iloc[:, 1:].pct_change().fillna(0)
    mean_returns_annualized = asset_returns_df.mean() * 252
    covariance_matrix_annualized = asset_returns_df.cov() * 252
    k = len(df_subset.columns) - 1
    
    combo_blended_returns = None
    if blended_returns_map is not None:
        stocks = df_subset.columns[1:]
        projected_scores_data = [blended_returns_map.get(s, mean_returns_annualized[s]) for s in stocks]
        combo_blended_returns = pd.Series(projected_scores_data, index=stocks)
    
    best_sharpe = -float("inf")
    best_weights = None
    
    for _ in range(num_sims):
        weights = generate_portfolio_weights(k)
    
        exp_ret, vol, sharpe = _calculate_portfolio_metrics_from_precomputed(
            weights, mean_returns_annualized, covariance_matrix_annualized, rf_rate,
            blended_returns=combo_blended_returns
        )
    
        # Ensure sharpe is a scalar number before comparing
        if isinstance(sharpe, Real) and pd.notna(sharpe) and sharpe > best_sharpe:
            best_sharpe = sharpe
            best_weights = weights
            
    # After the loop, if we found a valid portfolio, run the full calculation once.
    if best_weights is not None:
        exp_ret, vol, sharpe  = simulation_engine_calc(
            df_subset, best_weights, rf_rate, logger, blended_returns_map=blended_returns_map
        )
        return {
            'sharpe': sharpe, 'weights': best_weights, 'exp_ret': exp_ret,
            'vol': vol
        }

    return None # No valid portfolio found

# ----------------------------------------------
# 6. Convergence Helper
# ----------------------------------------------
def should_continue_sampling(sharpes, min_sims, max_sims, window, delta):
    if len(sharpes) < window:
        return True
    window_data = sharpes[-window:]
    return (max(window_data) - min(window_data)) >= delta

# ----------------------------------------------
# 7. Genetic Algorithm Logic
# ----------------------------------------------

def select_parents(evaluated_population: List[Dict], tournament_size: int) -> Dict:
    """Selects a parent from the population using tournament selection."""
    if not evaluated_population:
        raise ValueError("Cannot select parents from an empty population.")

    # Ensure tournament size is not larger than the population itself
    actual_tournament_size = min(tournament_size, len(evaluated_population))

    # Randomly select contenders for the tournament
    tournament_contenders = random.sample(evaluated_population, actual_tournament_size)

    # The winner is the one with the highest fitness (Sharpe ratio)
    winner = max(tournament_contenders, key=lambda x: x['fitness'])
    return winner

def crossover_portfolios(parent1: List[str], parent2: List[str], available_stocks: List[str], k: int,
                         crossover_rate: float) -> Tuple[List[str], List[str]]:
    """Performs crossover between two parent portfolios."""
    if random.random() > crossover_rate:
        return parent1[:], parent2[:]  # Return copies of parents if no crossover

    # Single-point crossover
    point = random.randint(1, k - 1)
    child1_set = set(parent1[:point] + parent2[point:])
    child2_set = set(parent2[:point] + parent1[point:])

    # Repair: Ensure children have the correct number of unique stocks (k)
    def repair_child(child_set: set) -> List[str]:
        while len(child_set) < k:
            add_stock = random.choice(available_stocks)
            if add_stock not in child_set:
                child_set.add(add_stock)
        return random.sample(list(child_set), k)

    return repair_child(child1_set), repair_child(child2_set)

def mutate_portfolio(portfolio: List[str], available_stocks: List[str], mutation_rate: float) -> List[str]:
    """Performs mutation on a single portfolio."""
    if random.random() > mutation_rate:
        return portfolio

    mutated_portfolio = portfolio[:]
    # Select a random gene (stock) to mutate
    idx_to_mutate = random.randint(0, len(mutated_portfolio) - 1)

    # Find a new stock that is not already in the portfolio
    possible_new_stocks = [s for s in available_stocks if s not in mutated_portfolio]
    if not possible_new_stocks:
        return mutated_portfolio  # Cannot mutate if no other stocks are available

    new_stock = random.choice(possible_new_stocks)
    mutated_portfolio[idx_to_mutate] = new_stock

    return mutated_portfolio

# ----------------------------------------------
# 8. Final Portfolio Search Function
# ----------------------------------------------

def _run_brute_force_iteration(
    k, available_stocks, stock_sector_map, max_stocks_per_sector,
    source_stock_prices_df, sim, timer_instance, current_initial_investment,
    current_rf_rate, logger_instance, best_sharpe_overall
):
    """Helper to run one iteration of the brute-force search for a given k."""
    combos = list(itertools.combinations(available_stocks, k))
    diversified = [c for c in combos if max(Counter(
        stock_sector_map.get(s, 'Unknown') for s in c).values()) <= max_stocks_per_sector]
    total = len(diversified)
    last_logged_progress = -1

    best_result_for_k: Dict[str, Any] = {
        'combo': None, 'weights': None, 'sharpe': -float("inf"),
        'exp_ret': None, 'vol': None
    }
    all_results_for_k: List[Dict[str, Any]] = []

    for i, combo in enumerate(diversified):
        combo_list = list(combo)
        df_subset = source_stock_prices_df[['Date'] + combo_list]
        
        # --- PERFORMANCE OPTIMIZATION ---
        # Pre-calculate returns and annualized metrics ONCE per stock combination.
        # This avoids recalculating these in every simulation run for the same combo.
        asset_returns_df = df_subset.iloc[:, 1:].pct_change().fillna(0)
        mean_returns_annualized = asset_returns_df.mean() * 252
        covariance_matrix_annualized = asset_returns_df.cov() * 252

        best_sharpe_this, best_weights_this = -float("inf"), None
        best_exp_ret_this = best_vol_this = np.nan
        sharpes = []
        sims_run = 0

        if k < 2:
            max_sims = sim["PROGRESSIVE_MIN_SIMS"]
        else:
            log_k_sq = math.log(float(k)) ** 2
            calc_sims = int(sim["PROGRESSIVE_BASE_LOG_K"] * log_k_sq)
            max_sims = max(min(calc_sims, sim["PROGRESSIVE_MAX_SIMS_CAP"]), sim["PROGRESSIVE_MIN_SIMS"])

        for _ in range(max_sims):
            weights = generate_portfolio_weights(k)

            combo_blended_returns = None
            if blended_returns_map is not None:
                stocks = df_subset.columns[1:]
                projected_scores_data = [blended_returns_map.get(s, mean_returns_annualized[s]) for s in stocks]
                combo_blended_returns = pd.Series(projected_scores_data, index=stocks)
                
            # Use the centralized, vectorized calculation function
            exp_ret, vol, sharpe = _calculate_portfolio_metrics_from_precomputed(
                weights, mean_returns_annualized, covariance_matrix_annualized, current_rf_rate, blended_returns=combo_blended_returns
            )

            sims_run += 1

            if isinstance(sharpe, Real) and pd.notna(sharpe) and sharpe > best_sharpe_this:
                best_sharpe_this, best_weights_this = sharpe, weights
                best_exp_ret_this, best_vol_this = exp_ret, vol

            sharpes.append(sharpe if not pd.isna(sharpe) else -float("inf"))
            if sims_run == sim["INITIAL_SCAN_SIMS"]:
                if best_sharpe_overall > sim["EARLY_DISCARD_MIN_BEST_SHARPE"] and best_sharpe_this < best_sharpe_overall * sim["EARLY_DISCARD_FACTOR"]:
                    break
            if sims_run >= sim["PROGRESSIVE_MIN_SIMS"] and sims_run % sim["PROGRESSIVE_CHECK_INTERVAL"] == 0:
                if not should_continue_sampling(sharpes, sim["PROGRESSIVE_MIN_SIMS"], max_sims, sim["PROGRESSIVE_CONVERGENCE_WINDOW"], sim["PROGRESSIVE_CONVERGENCE_DELTA"]):
                    break

        percent = ((i + 1) / total) * 100
        if percent - last_logged_progress >= sim["BF_PROGRESS_LOG_STEP"] or percent == 100.0:
            bf_progress_payload = {
                "current_phase": f"Brute-Force (k={k})",
                "overall_progress": percent
            }
            logger_instance.info(
                f"Brute-force progress for k={k}: {percent:.2f}% ({i + 1}/{total})",
                extra={'web_data': {"progress": bf_progress_payload,
                                    "status_message": f"Evaluating combo {i + 1} of {total} for k={k}"}}
            )
            last_logged_progress = percent

        # After the simulation loop for a combo, calculate full metrics ONCE using the best weights found.
        if best_weights_this is not None:
            (exp_ret_final, vol_final, sharpe_final) = simulation_engine_calc(
                df_subset, best_weights_this, current_rf_rate, logger_instance
            )

            # Check if this combo is the best for the current k (ensure sharpe_final is scalar)
            if isinstance(sharpe_final, Real) and pd.notna(sharpe_final) and sharpe_final > best_result_for_k['sharpe']:
                best_result_for_k.update({
                    'combo': combo_list, 'weights': best_weights_this, 'sharpe': sharpe_final,
                    'exp_ret': exp_ret_final, 'vol': vol_final
                })

            # Add the full results to the list for the refinement phase
            all_results_for_k.append({
                'sharpe': sharpe_final, 'weights': best_weights_this, 'stocks': combo_list,
                'exp_ret': exp_ret_final, 'vol': vol_final,
                'sims_run': sims_run
            })

    return best_result_for_k, all_results_for_k

def _run_refinement_phase(
    all_results, source_stock_prices_df, sim,
    current_rf_rate, logger_instance, current_best_result
):
    """Helper to run the refinement phase on the top brute-force results."""
    logger_instance.info("Starting refinement phase")
    all_results.sort(key=lambda x: x['sharpe'], reverse=True)
    top_n = max(1, int(len(all_results) * sim["TOP_N_PERCENT_REFINEMENT"]))
    top_refine = all_results[:top_n]

    refined_best_result = current_best_result.copy()

    for combo_data in top_refine:
        df_subset = source_stock_prices_df[['Date'] + combo_data['stocks']]
        result = simulate_portfolio_combo(
            df_subset, sim["SIM_RUNS"], current_rf_rate, logger_instance, blended_returns_map=blended_returns_map
        )
        if result and result['sharpe'] > refined_best_result['sharpe']:
            refined_best_result.update({
                'combo': combo_data['stocks'], 'weights': result['weights'], 'sharpe': result['sharpe'],
                'exp_ret': result['exp_ret'], 'vol': result['vol']
            })
    return refined_best_result

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
    sim_params,
    blended_returns_map=None
):
    sim = extract_simulation_parameters(sim_params)
    logger_instance.info("Starting portfolio combination search...")

    available_stocks = [s for s in stocks_to_consider_list if s in source_stock_prices_df.columns]
    if not available_stocks:
        logger_instance.error("No stocks from 'stocks_to_consider_list' found. Skipping search.")
        return None

    max_portfolio_size = min(max_portfolio_size, len(available_stocks))

    best_result = {
        'combo': None, 'weights': None, 'sharpe': -float("inf"),
        'exp_ret': None, 'vol': None
    }
    ga_fitness_history = []
    all_bf_results = []

    for k in range(min_portfolio_size, max_portfolio_size + 1):
        logger_instance.info(f"Evaluating k={k} portfolio size")
        k_result = None
        # Initialize ga_history_for_k for each loop to ensure it's always defined.
        ga_history_for_k = []

        if k <= sim["HEURISTIC_THRESHOLD_K"]:
            k_result, bf_results_for_k = _run_brute_force_iteration(
                k, available_stocks, stock_sector_map, max_stocks_per_sector,
                source_stock_prices_df, sim, timer_instance,
                current_rf_rate, logger_instance, best_result['sharpe'],
                blended_returns_map=blended_returns_map
            )
            if sim["ADAPTIVE_SIM_ENABLED"]:
                all_bf_results.extend(bf_results_for_k)
        else:
            # Refactored call: Assign the returned dictionary directly to k_result.
            k_result = run_genetic_algorithm(
                source_stock_prices_df, available_stocks, k, current_rf_rate,
                logger_instance, timer_instance, sim["SIM_RUNS"], sim_params,
                blended_returns_map=blended_returns_map
            )
            # Extract the fitness history from the result dictionary.
            if k_result:
                ga_history_for_k = k_result.get('ga_fitness_history', [])

        if k_result and k_result['sharpe'] > best_result['sharpe']:
            best_result = k_result
            # If the new best result came from the GA, store its fitness history.
            # The check is now simpler because ga_history_for_k is always defined.
            if ga_history_for_k:
                ga_fitness_history = ga_history_for_k

    if sim["ADAPTIVE_SIM_ENABLED"] and sim["TOP_N_PERCENT_REFINEMENT"] > 0 and all_bf_results:
        best_result = _run_refinement_phase(
            all_bf_results, source_stock_prices_df, sim,
            current_rf_rate, logger_instance, best_result,
            blended_returns_map=blended_returns_map
        )

    # Add the GA history to the final result dictionary
    best_result['ga_fitness_history'] = ga_fitness_history
    return best_result

def run_genetic_algorithm(
        source_stock_prices_df,
        available_stocks_for_search,
        num_stocks_in_combo,
        current_rf_rate,
        logger_instance,
        timer_instance,
        num_simulation_runs,
        sim_params,
        blended_returns_map=None
):
    """
    Performs portfolio optimization using a Genetic Algorithm.
    Uses custom crossover and mutation functions defined by the user.
    """
    # Extract GA parameters
    POPULATION_SIZE = sim_params.get("ga_population_size", 50)
    NUM_GENERATIONS = sim_params.get("ga_num_generations", 30)
    MUTATION_RATE = sim_params.get("ga_mutation_rate", 0.02)
    CROSSOVER_RATE = sim_params.get("ga_crossover_rate", 0.8)
    ELITISM_COUNT = sim_params.get("ga_elitism_count", 2)
    TOURNAMENT_SIZE = sim_params.get("ga_tournament_size", 3)
    CONVERGENCE_GENERATIONS = sim_params.get("ga_convergence_generations", 10)
    CONVERGENCE_TOLERANCE = sim_params.get("ga_convergence_tolerance", 0.0001)
    MAX_ATTEMPTS = POPULATION_SIZE * sim_params.get("ga_init_pop_max_attempts_multiplier", 5)

    if len(available_stocks_for_search) < num_stocks_in_combo:
        logger_instance.warning(
            f"GA Warning: Not enough stocks ({len(available_stocks_for_search)}) for k={num_stocks_in_combo}. Skipping.")
        return {
            'combo': None, 'weights': None, 'sharpe': -float("inf"),
            'exp_ret': None, 'vol': None,
            'ga_fitness_history': []
        }

    # --- Initial Population ---
    population = []
    seen_combos = set()
    for _ in range(MAX_ATTEMPTS):
        if len(population) >= POPULATION_SIZE:
            break
        combo = tuple(sorted(random.sample(available_stocks_for_search, num_stocks_in_combo)))
        if combo not in seen_combos:
            population.append(list(combo))
            seen_combos.add(combo)

    if not population:
        logger_instance.error(f"GA Error: Failed to initialize population for k={num_stocks_in_combo}.")
        return {
            'combo': None, 'weights': None, 'sharpe': -float("inf"),
            'exp_ret': None, 'vol': None,
            'ga_fitness_history': []
        }

    best_sharpe_overall = -float("inf")
    best_combo, best_weights = None, None
    best_exp_ret, best_vol = None, None
    best_sharpe_history = []

    # --- GA Main Loop ---
    for generation in range(NUM_GENERATIONS):
        logger_instance.info(
            f"GA Gen {generation + 1}/{NUM_GENERATIONS} for k={num_stocks_in_combo}",
            extra={'web_data': {
                "progress": {
                    "current_phase": f"Genetic Algorithm (k={num_stocks_in_combo})",
                    "overall_progress": (generation + 1) / NUM_GENERATIONS * 100
                },
                "status_message": f"Running GA Generation {generation + 1}"
            }}
        )

        evaluated_population = []
        for combo in population:
            df_subset = source_stock_prices_df[["Date"] + combo]
            result = simulate_portfolio_combo(df_subset, num_simulation_runs, current_rf_rate, logger_instance, blended_returns_map=blended_returns_map)
            if result:
                evaluated_population.append({
                    'combo': combo,
                    'weights': result['weights'],
                    'fitness': result['sharpe'],
                    'exp_ret': result['exp_ret'],
                    'vol': result['vol']
                })

        if not evaluated_population:
            logger_instance.warning(f"GA Warning: No valid individuals in generation {generation + 1}.")
            continue

        evaluated_population.sort(key=lambda x: x['fitness'], reverse=True)

        # Update best result
        top_result = evaluated_population[0]
        if top_result['fitness'] > best_sharpe_overall:
            best_sharpe_overall = top_result['fitness']
            best_combo = top_result['combo']
            best_weights = top_result['weights']
            best_exp_ret = top_result['exp_ret']
            best_vol = top_result['vol']

        # Elitism: carry over best individuals
        next_population = [ind['combo'] for ind in evaluated_population[:ELITISM_COUNT]]

        # Generate new individuals
        while len(next_population) < POPULATION_SIZE:
            parent1 = select_parents(evaluated_population, TOURNAMENT_SIZE)
            parent2 = select_parents(evaluated_population, TOURNAMENT_SIZE)
            child1, child2 = crossover_portfolios(
                parent1['combo'], parent2['combo'],
                available_stocks=available_stocks_for_search,
                k=num_stocks_in_combo,
                crossover_rate=CROSSOVER_RATE
            )
            next_population.append(mutate_portfolio(child1, available_stocks_for_search, MUTATION_RATE))
            if len(next_population) < POPULATION_SIZE:
                next_population.append(mutate_portfolio(child2, available_stocks_for_search, MUTATION_RATE))

        population = next_population

        # Convergence check
        best_sharpe_history.append(best_sharpe_overall)
        if len(best_sharpe_history) > CONVERGENCE_GENERATIONS:
            best_sharpe_history.pop(0)
            if (max(best_sharpe_history) - min(best_sharpe_history)) < CONVERGENCE_TOLERANCE:
                logger_instance.info(f"\n    GA Converged after {generation + 1} generations.")
                break

    return {
        'combo': best_combo, 'weights': best_weights, 'sharpe': best_sharpe_overall,
        'exp_ret': best_exp_ret, 'vol': best_vol,
        'ga_fitness_history': best_sharpe_history
            }

def main():
    """Main execution function for the Portfolio script."""
    # 1. --- Initial Setup ---
    overall_start_time = time.time()    
    run_id = os.environ.get('PIPELINE_RUN_ID') or datetime.now().strftime('%Y%m%d-%H%M%S')
    script_dir = os.path.dirname(os.path.abspath(__file__))

    expected_params = {
        # From paths.txt
        "FINDB_FILE": str, "WEB_ACCESSIBLE_DATA_PATH": str, "PORTFOLIO_PROGRESS_JSON_FILE": str,
        # From portpar.txt
        "PORTFOLIO_LOG_FILE": str, "PORTFOLIO_PERFORMANCE_FILE": str, "SCORED_STOCKS_DB_FILE": str,
        "PORTFOLIO_RESULTS_DB_FILE": str, "GA_FITNESS_NOISE_DB_FILE": str, "PORTFOLIO_VALUE_DB_FILE": str,
        "debug_mode": bool, "start_date": str, "top_n_stocks_from_score": int,
        "min_stocks": int, "max_stocks": int, "initial_investment": float, "rf": float,
        "max_stocks_per_sector": int, "heuristic_threshold_k": int, "adaptive_sim_enabled": bool,
        "initial_scan_sims": int, "early_discard_factor": float, "early_discard_min_best_sharpe": float,
        "progressive_min_sims": int, "progressive_base_log_k": int, "progressive_max_sims_cap": int,
        "progressive_convergence_window": int, "progressive_convergence_delta": float,
        "progressive_check_interval": int, "top_n_percent_refinement": float, "sim_runs": int,
        "ga_population_size": int, "ga_num_generations": int, "ga_mutation_rate": float,
        "ga_crossover_rate": float, "ga_elitism_count": int, "ga_tournament_size": int,
        "ga_convergence_generations": int, "ga_convergence_tolerance": float,
        "ga_init_pop_max_attempts_multiplier": int, "auto_curate_threshold": float,
    }

    # 2. --- Load Parameters ---
    try:
        paths_file = os.path.join(script_dir, '..', 'parameters', 'paths.txt')
        portpar_file = os.path.join(script_dir, '..', 'parameters', 'portpar.txt')
        params = load_parameters_from_file(
            filepaths=[paths_file, portpar_file],
            expected_parameters=expected_params
        )
    except (FileNotFoundError, Exception) as e:
        temp_logger = setup_logger("PortfolioStartupLogger", "portfolio_startup_error.log", None)
        temp_logger.critical(f"Could not load parameters. Exiting. Error: {e}", exc_info=True)
        sys.exit(1)

    # 3. --- Setup Logger and Performance Tracking ---
    progress_file = params.get("PORTFOLIO_PROGRESS_JSON_FILE")
    initial_progress_data = {
        "portfolio_status": "Running: Initializing...",
        "start_time": datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
        "end_time": "N/A",
        "status_message": "Loading parameters and setting up logger.",
        "progress": {"current_phase": "Initialization"}
    }
    try:
        if progress_file:
            os.makedirs(os.path.dirname(progress_file), exist_ok=True)
            with open(progress_file, 'w') as f:
                json.dump(initial_progress_data, f, indent=4)
    except Exception as e:
        print(f"CRITICAL: Could not initialize progress file {progress_file}. Error: {e}")

    logger = setup_logger(
        "PortfolioRunner",
        log_file=params.get("PORTFOLIO_LOG_FILE"),
        web_log_file=progress_file,
        level=logging.DEBUG if params.get("debug_mode") else logging.INFO
    )
    perf_data = initialize_performance_data(PORTFOLIO_PY_VERSION)
    perf_data["param_load_duration_s"] = time.time() - overall_start_time

    logger.info("Starting A3_Portfolio.py execution pipeline.",
                extra={'web_data': {"status_message": "Parameters loaded."}})

    best_combo, best_weights, best_sharpe, best_exp_ret, best_vol = [None] * 5
    ga_fitness_history = []
    stock_close_df_sim_pool = pd.DataFrame()
    # Ensure stock_sector_map exists even if load_scored_stocks fails or raises
    stock_sector_map: Dict[str, str] = {}

    try:
        # 4. --- Main Execution Block ---
        data_load_start = time.time()
        top_scored_stocks, stock_sector_map, scoring_run_id, stock_to_upside_map = load_scored_stocks(params, logger)
        stock_data_file = params.get("FINDB_FILE")
        if not stock_data_file or not os.path.exists(stock_data_file):
            raise FileNotFoundError(f"Master stock data file not found at '{stock_data_file}'.")
        stock_data_db_df = pd.read_csv(stock_data_file)
        stock_data_db_df['Date'] = pd.to_datetime(stock_data_db_df['Date'], format='mixed', errors='coerce').dt.date
        perf_data["data_load_duration_s"] = time.time() - data_load_start

        # Detect regime and calculate blended returns map
        risk_profile_params = load_risk_profile(params, logger)

        # Precompute master returns for regime detection
        focused_regime_df = stock_data_db_df.copy()
        if 'Stock' in focused_regime_df.columns:
            regime_prices_df = focused_regime_df.pivot(index="Date", columns="Stock", values="Close").replace(0, np.nan).dropna(how='all')
        else:
            regime_prices_df = focused_regime_df
            
        market_regime = detect_market_regime(regime_prices_df, 60, risk_profile_params, logger)
        vol_pct = float(market_regime.get('volatility_percentile', 0.5))
        trend = float(market_regime.get('trend', 0.0))
        
        master_asset_returns = stock_data_db_df.drop(columns=['Date', 'Symbol'], errors='ignore')
        if 'Stock' in stock_data_db_df.columns:
             master_asset_returns = stock_data_db_df.pivot(index="Date", columns="Stock", values="Close").pct_change().fillna(0)
        master_mean_returns_annualized = master_asset_returns.mean() * 252
        
        blended_returns_series = calculate_blended_returns(
            master_mean_returns_annualized, stock_to_upside_map, vol_pct, trend, params
        )
        blended_returns_map = blended_returns_series.to_dict()

        data_wrangling_start = time.time()
        scored_stocks_in_db = [stock for stock in top_scored_stocks if stock in stock_data_db_df['Stock'].unique()]
        if not scored_stocks_in_db:
            raise ValueError("None of the top scored stocks were found in the stock data DB.")
        focused_df = stock_data_db_df[stock_data_db_df['Stock'].isin(scored_stocks_in_db)].copy()
        stock_close_df_sim_pool = focused_df.pivot(index="Date", columns="Stock", values="Close").replace(0, np.nan)
        stock_close_df_sim_pool.dropna(inplace=True)
        stock_close_df_sim_pool.reset_index(inplace=True)
        perf_data["data_wrangling_duration_s"] = time.time() - data_wrangling_start

        sim_timer = ExecutionTimer()

        # Call the refactored function that returns a dictionary
        best_portfolio_result = find_best_stock_combination(
            stock_close_df_sim_pool,
            top_scored_stocks,
            params.get("initial_investment"),
            params.get("min_stocks"),
            params.get("max_stocks"),
            params.get("rf"),
            logger,
            sim_timer,
            stock_sector_map,
            params.get("max_stocks_per_sector"),
            params,
            blended_returns_map=blended_returns_map
        )

        # Correctly unpack the dictionary into the script's main variables
        if best_portfolio_result and best_portfolio_result.get('combo'):
            best_combo = best_portfolio_result['combo']
            best_weights = best_portfolio_result['weights']
            best_sharpe = best_portfolio_result['sharpe']
            best_exp_ret = best_portfolio_result['exp_ret']
            best_vol = best_portfolio_result['vol']
            # Use .get() for safety, providing a default empty list
            ga_fitness_history = best_portfolio_result.get('ga_fitness_history', [])

    except Exception as e:
        logger.critical(f"An unhandled exception occurred: {e}", exc_info=True,
                        extra={'web_data': {"portfolio_status": "Failed", "status_message": str(e)}})

    finally:
        # 5. --- Finalization and Logging ---
        perf_data["overall_script_duration_s"] = time.time() - overall_start_time
        log_performance_data(perf_data, params, logger)

        # Consolidate result saving and add explicit type checks to resolve IDE warnings.
        # This ensures that if a valid combo is found, its associated data is also valid.
        if isinstance(best_combo, list) and best_combo and isinstance(best_weights, (list, np.ndarray)):
            # 1. Save portfolio results
            # Calculate final_value and roi_percent for backward compatibility with existing CSV header
            initial_investment = params.get("initial_investment", 1000)
            final_value = initial_investment * (1 + best_exp_ret)  # Approximate final value after 1 year
            roi_percent = best_exp_ret * 100  # Same as expected return for annual basis

            results_df = pd.DataFrame([{
                "run_id": run_id,
                "scoring_run_id": scoring_run_id,
                "timestamp": datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
                "engine_version": PORTFOLIO_PY_VERSION,
                "min_stocks": params.get("min_stocks"),
                "max_stocks": params.get("max_stocks"),
                "stocks": ', '.join(best_combo),
                "weights": ', '.join(map(str, [round(w, 4) for w in best_weights])),
                "sharpe_forward": round(best_sharpe, 4),
                "final_value": round(final_value, 2),
                "roi_percent": round(roi_percent, 2),
                "expected_return_annual_pct": round(best_exp_ret * 100, 2),
                "expected_volatility_annual_pct": round(best_vol * 100, 2),
            }])
            results_db_path = params.get("PORTFOLIO_RESULTS_DB_FILE")
            if results_db_path:
                try:
                    os.makedirs(os.path.dirname(results_db_path), exist_ok=True)
                    if os.path.exists(results_db_path) and os.path.getsize(results_db_path) > 0:
                        # Read existing header to reconcile schemas
                        existing_df = pd.read_csv(results_db_path, nrows=0)
                        # Merge columns: existing + any new ones from results_df
                        all_cols = list(existing_df.columns) + [c for c in results_df.columns if c not in existing_df.columns]
                        # Reindex new row to match merged schema (missing old cols get NaN)
                        results_df = results_df.reindex(columns=all_cols)
                        # Rewrite file with updated header + all old data + new row
                        old_data = pd.read_csv(results_db_path).reindex(columns=all_cols)
                        merged = pd.concat([old_data, results_df], ignore_index=True)
                        merged.to_csv(results_db_path, index=False)
                    else:
                        results_df.to_csv(results_db_path, index=False)
                    logger.info(f"Successfully appended results to {results_db_path}")
                except Exception as e:
                    logger.error(f"Failed to save portfolio results to {results_db_path}: {e}")

            # 3. Save GA fitness history
            if ga_fitness_history:
                ga_df = pd.DataFrame({
                    'run_id': run_id,
                    'generation': range(1, len(ga_fitness_history) + 1),
                    'best_sharpe': ga_fitness_history
                })
                ga_db_path = params.get("GA_FITNESS_NOISE_DB_FILE")
                if ga_db_path:
                    try:
                        os.makedirs(os.path.dirname(ga_db_path), exist_ok=True)
                        ga_df.to_csv(ga_db_path, mode='a', header=not os.path.exists(ga_db_path), index=False)
                        logger.info(f"Successfully appended GA fitness to {ga_db_path}")
                    except Exception as e:
                        logger.error(f"Failed to save GA fitness to {ga_db_path}: {e}")

            # 4. Create the latest_run_summary.json file for the main portfolio page
            # Calculate additional metrics for Factor & Style Diagnostics

            # 4.1 Sector Exposure - Calculate percentage allocation by sector
            sector_exposure = {}
            # Use a local copy to avoid static analysis confusion about variable initialization
            sector_map_for_output = stock_sector_map if isinstance(stock_sector_map, dict) else {}
            for stock, weight in zip(best_combo, best_weights):
                sector = sector_map_for_output.get(stock, 'Unknown')
                sector_exposure[sector] = sector_exposure.get(sector, 0) + weight
            sector_exposure = {k: round(v, 4) for k, v in sector_exposure.items()}

            # 4.2 Concentration Risk - Calculate HHI and Top 5 holdings
            hhi = sum(w ** 2 for w in best_weights)
            sorted_holdings = sorted(zip(best_combo, best_weights), key=lambda x: x[1], reverse=True)
            top_5_holdings = sorted_holdings[:5]
            top_5_pct = sum(h[1] for h in top_5_holdings)

            # 4.3 Portfolio-weighted Forward P/E & Momentum & Valuation Metrics
            # Load scored stocks to get forwardPE and Momentum
            scored_stocks_file = params.get("SCORED_STOCKS_DB_FILE")
            financials_file = params.get("FINANCIALS_FILE")

            portfolio_weighted_pe = None
            portfolio_momentum = None
            portfolio_dividend_yield = None
            benchmark_weighted_pe = None
            latest_scored = pd.DataFrame()  # Initialize before loading

            if scored_stocks_file and os.path.exists(scored_stocks_file):
                try:
                    scored_df = pd.read_csv(scored_stocks_file)
                    latest_run_id_scored = scored_df['run_id'].max()
                    latest_scored = scored_df[scored_df['run_id'] == latest_run_id_scored]

                    # Calculate portfolio-weighted Forward P/E
                    weighted_pe_sum = 0
                    total_weight_with_pe = 0
                    for stock, weight in zip(best_combo, best_weights):
                        stock_data = latest_scored[latest_scored['Stock'] == stock]
                        if not stock_data.empty:
                            forward_pe = stock_data['forwardPE'].values[0]
                            if pd.notna(forward_pe) and forward_pe > 0:
                                weighted_pe_sum += forward_pe * weight
                                total_weight_with_pe += weight

                    if total_weight_with_pe > 0:
                        portfolio_weighted_pe = round(weighted_pe_sum / total_weight_with_pe, 2)

                    # Calculate portfolio-weighted Momentum
                    weighted_momentum_sum = 0
                    total_weight_with_momentum = 0
                    for stock, weight in zip(best_combo, best_weights):
                        stock_data = latest_scored[latest_scored['Stock'] == stock]
                        if not stock_data.empty:
                            momentum = stock_data['Momentum'].values[0]
                            if pd.notna(momentum):
                                weighted_momentum_sum += momentum * weight
                                total_weight_with_momentum += weight

                    if total_weight_with_momentum > 0:
                        portfolio_momentum = round(weighted_momentum_sum / total_weight_with_momentum, 4)

                    # Calculate benchmark-weighted Forward P/E (using top scored stocks as proxy)
                    benchmark_stocks = latest_scored.head(50)  # Use top 50 as benchmark proxy
                    valid_pes = benchmark_stocks[benchmark_stocks['forwardPE'].notna() & (benchmark_stocks['forwardPE'] > 0)]
                    if not valid_pes.empty:
                        benchmark_weighted_pe = round(valid_pes['forwardPE'].mean(), 2)

                except Exception as e:
                    logger.warning(f"Could not calculate portfolio metrics: {e}")

            # Calculate portfolio-weighted Dividend Yield
            if financials_file and os.path.exists(financials_file):
                try:
                    financials_df = pd.read_csv(financials_file)

                    weighted_div_yield_sum = 0
                    total_weight_with_div = 0
                    for stock, weight in zip(best_combo, best_weights):
                        stock_fin = financials_df[financials_df['Stock'] == stock]
                        if not stock_fin.empty:
                            div_yield = stock_fin['dividendYield'].values[0]
                            if pd.notna(div_yield) and div_yield > 0:
                                weighted_div_yield_sum += div_yield * weight
                                total_weight_with_div += weight

                    if total_weight_with_div > 0:
                        portfolio_dividend_yield = round(weighted_div_yield_sum / total_weight_with_div, 2)
                except Exception as e:
                    logger.warning(f"Could not calculate portfolio dividend yield: {e}")

            # --- Build sector_exposure_list for predictable chart rendering ---
            sector_exposure_list = []
            try:
                if isinstance(sector_exposure, dict) and sector_exposure:
                    sector_exposure_list = sorted([
                        {'sector': k, 'pct': float(v)} for k, v in sector_exposure.items()
                    ], key=lambda x: x['pct'], reverse=True)
            except Exception:
                sector_exposure_list = []

            latest_summary = {
                "last_updated_run_id": run_id,
                "scoring_run_id": scoring_run_id,
                "last_updated_timestamp": datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
                "best_portfolio_details": {
                    "stocks": best_combo,
                    "weights": [round(w, 4) for w in best_weights],
                    "sharpe_forward": round(best_sharpe, 4),
                    "expected_return_annual_pct": round(best_exp_ret * 100, 2),
                    "expected_volatility_annual_pct": round(best_vol * 100, 2),
                    "initial_investment": params.get("initial_investment"),
                    "sector_exposure": sector_exposure,
                    "sector_exposure_list": sector_exposure_list,
                    "concentration_risk": {
                        "hhi": round(hhi, 4),
                        "top_5_holdings_pct": round(top_5_pct, 4),
                        "top_5_holdings": [{"stock": h[0], "weight": round(h[1], 4)} for h in top_5_holdings]
                    },
                    "portfolio_weighted_pe": portfolio_weighted_pe,
                    "momentum_valuation": {
                        "portfolio_momentum": portfolio_momentum,
                        "portfolio_forward_pe": portfolio_weighted_pe,
                        "benchmark_forward_pe": benchmark_weighted_pe,
                        "portfolio_dividend_yield": portfolio_dividend_yield
                    },
                    "holdings_meta": {}
                }
            }

            # Add per-holding metadata (forwardPE, Momentum, currentPrice, targetPrice) if scored stocks are available
            try:
                holdings_meta = {}

                # Load financials DB as fallback for forwardPE data
                financials_db = pd.DataFrame()
                financials_db_file = params.get("FINANCIALS_DB_FILE")
                if financials_db_file and os.path.exists(financials_db_file):
                    try:
                        financials_db = pd.read_csv(financials_db_file)
                        # Get latest entry per stock
                        if 'LastUpdated' in financials_db.columns:
                            financials_db['LastUpdated'] = pd.to_datetime(financials_db['LastUpdated'])
                            financials_db = financials_db.sort_values('LastUpdated').drop_duplicates(subset='Stock', keep='last')
                        logger.info(f"Loaded {len(financials_db)} entries from FinancialsDB for fallback")
                    except Exception as e:
                        logger.warning(f"Could not load FinancialsDB: {e}")

                # Load StockDataDB for price fallback
                stock_data_db = pd.DataFrame()
                stock_data_db_file = params.get("FINDB_FILE")
                if stock_data_db_file and os.path.exists(stock_data_db_file):
                    try:
                        stock_data_db = pd.read_csv(stock_data_db_file)
                        if 'Date' in stock_data_db.columns:
                            stock_data_db['Date'] = pd.to_datetime(stock_data_db['Date'])
                        logger.info(f"Loaded StockDataDB for price fallback")
                    except Exception as e:
                        logger.warning(f"Could not load StockDataDB: {e}")

                for stock in best_combo:
                    stock_row = latest_scored[latest_scored['Stock'] == stock] if not latest_scored.empty else pd.DataFrame()

                    # Get values from scored_stocks if available
                    forward_pe = None
                    forward_eps = None
                    sector_median_pe = None
                    momentum_val = None
                    current_price = None
                    target_price = None

                    if not stock_row.empty:
                        forward_pe = stock_row['forwardPE'].values[0] if 'forwardPE' in stock_row.columns else None
                        forward_eps = stock_row['forwardEPS'].values[0] if 'forwardEPS' in stock_row.columns else None
                        sector_median_pe = stock_row['SectorMedianPE'].values[0] if 'SectorMedianPE' in stock_row.columns else None
                        momentum_val = stock_row['Momentum'].values[0] if 'Momentum' in stock_row.columns else None
                        current_price = stock_row['CurrentPrice'].values[0] if 'CurrentPrice' in stock_row.columns else None
                        target_price = stock_row['TargetPrice'].values[0] if 'TargetPrice' in stock_row.columns else None

                    # Fallback to FinancialsDB for forwardPE and forwardEPS if not found
                    if not financials_db.empty:
                        fin_row = financials_db[financials_db['Stock'] == stock]
                        if not fin_row.empty:
                            if (forward_pe is None or pd.isna(forward_pe) or forward_pe == 0) and 'forwardPE' in fin_row.columns:
                                forward_pe = fin_row['forwardPE'].values[0]
                                logger.debug(f"Using FinancialsDB fallback for {stock} forwardPE: {forward_pe}")
                            if (forward_eps is None or pd.isna(forward_eps)) and 'forwardEPS' in fin_row.columns:
                                forward_eps = fin_row['forwardEPS'].values[0]
                                logger.debug(f"Using FinancialsDB fallback for {stock} forwardEPS: {forward_eps}")

                    # Fallback to StockDataDB for current price if not found
                    if (current_price is None or pd.isna(current_price)) and not stock_data_db.empty:
                        stock_prices = stock_data_db[stock_data_db['Stock'] == stock].sort_values('Date', ascending=False)
                        if not stock_prices.empty and 'Close' in stock_prices.columns:
                            current_price = stock_prices['Close'].values[0]
                            logger.debug(f"Using StockDataDB fallback for {stock} currentPrice: {current_price}")

                    # Calculate target price using forward PE/EPS and sector median PE if still missing
                    if (target_price is None or pd.isna(target_price)) and current_price is not None and pd.notna(current_price):
                        # Try to calculate target price using forward EPS and sector median PE
                        if forward_eps is not None and pd.notna(forward_eps) and forward_eps > 0:
                            if sector_median_pe is not None and pd.notna(sector_median_pe) and sector_median_pe > 0:
                                target_price = forward_eps * sector_median_pe
                                logger.debug(f"Calculated target price for {stock}: {target_price} (EPS * SectorPE)")
                            elif forward_pe is not None and pd.notna(forward_pe) and forward_pe > 0:
                                # If we have forward PE, assume target is fair value at sector median
                                upside_potential = (sector_median_pe / forward_pe - 1) if sector_median_pe and forward_pe else 0
                                target_price = current_price * (1 + upside_potential)
                                logger.debug(f"Calculated target price for {stock}: {target_price} (CurrentPrice * (1 + Upside))")

                    holdings_meta[stock] = {
                        'forwardPE': float(forward_pe) if pd.notna(forward_pe) and forward_pe != 0 else 0.0,
                        'Momentum': float(momentum_val) if pd.notna(momentum_val) else 0.0,
                        'currentPrice': float(current_price) if pd.notna(current_price) else None,
                        'targetPrice': float(target_price) if pd.notna(target_price) else None
                    }

                latest_summary['best_portfolio_details']['holdings_meta'] = holdings_meta
                logger.info(f"Populated holdings_meta for {len(holdings_meta)} stocks")
            except Exception as e:
                # if anything fails, keep holdings_meta empty
                logger.error(f"Failed to populate holdings_meta: {e}")

            latest_summary_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data", "results", "latest_run_summary.json")
            try:
                with open(latest_summary_path, 'w') as f:
                    json.dump(latest_summary, f, indent=4)
                logger.info(f"Successfully created latest run summary at {latest_summary_path}")
            except Exception as e:
                logger.error(f"Failed to create latest run summary: {e}")

        # D_Publish.py handles copying to html/data/

        final_web_payload = {
            "portfolio_status": "Completed",
            "end_time": datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
            "status_message": "Portfolio optimization finished successfully.",
            "progress": {
                "current_phase": "Completed",
                "overall_progress": 100
            }
        }
        logger.info(
            f"Portfolio script finished in {perf_data['overall_script_duration_s']:.2f} seconds.",
            extra={'web_data': final_web_payload}
        )
        logger.info("Execution complete.")

if __name__ == "__main__":
    main()
