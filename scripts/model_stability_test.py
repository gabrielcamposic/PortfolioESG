import subprocess
import os
import pandas as pd
import numpy as np
import json
from datetime import datetime
import time
import sys

# Configuration
NUM_RUNS = 10
ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ENGINES_DIR = os.path.join(ROOT_DIR, "engines")
DATA_DIR = os.path.join(ROOT_DIR, "data")
RESULTS_DIR = os.path.join(DATA_DIR, "results")
STABILITY_REPORT_FILE = os.path.join(RESULTS_DIR, "stability_report.md")
PORTFOLIO_DB = os.path.join(RESULTS_DIR, "portfolio_results_db.csv")
SCORED_STOCKS_DB = os.path.join(RESULTS_DIR, "scored_stocks.csv")
STOCK_DATA_DB = os.path.join(DATA_DIR, "findb", "StockDataDB.csv")

def ensure_absolute_path(path):
    if path.startswith('~'):
        return os.path.expanduser(path)
    return path

# Resolve paths
PORTFOLIO_DB = ensure_absolute_path(PORTFOLIO_DB)
SCORED_STOCKS_DB = ensure_absolute_path(SCORED_STOCKS_DB)
STOCK_DATA_DB = ensure_absolute_path(STOCK_DATA_DB)

def run_portfolio_engine(run_id):
    print(f"--- Running iteration {run_id} ---")
    env = os.environ.copy()
    env['PIPELINE_RUN_ID'] = run_id
    # Ensure project root is in PYTHONPATH so shared_tools can be found
    env['PYTHONPATH'] = ROOT_DIR + (":" + env.get('PYTHONPATH', '') if env.get('PYTHONPATH') else "")
    
    # Run A3_Portfolio.py
    cmd = ["python3", os.path.join(ENGINES_DIR, "A3_Portfolio.py")]
    result = subprocess.run(cmd, env=env, capture_output=True, text=True)
    
    if result.returncode != 0:
        print(f"Error running portfolio engine: {result.stderr}")
        return False
    return True

def calculate_historical_return_12m(stocks, weights, price_df):
    """Calculate the 12-month historical return (last 252 days) for the portfolio."""
    if price_df is None or price_df.empty:
        return 0, {}
    
    portfolio_hist_return = 0
    stock_returns = {}
    
    for stock, weight in zip(stocks, weights):
        stock_prices = price_df[price_df['Stock'] == stock].sort_values('Date')
        if len(stock_prices) < 252:
            # Not enough data for 12m, use all available or fallback to 0
            if len(stock_prices) > 1:
                ret = (stock_prices['Close'].iloc[-1] / stock_prices['Close'].iloc[0]) - 1
            else:
                ret = 0
        else:
            ret = (stock_prices['Close'].iloc[-1] / stock_prices['Close'].iloc[-252]) - 1
        
        stock_returns[stock] = ret
        portfolio_hist_return += ret * weight
        
    return portfolio_hist_return, stock_returns

def get_aggregate_score_components(stocks, weights, scored_df):
    """Calculate weighted normalized scores (Sharpe, Upside, Momentum)."""
    if scored_df is None or scored_df.empty:
        return 0, 0, 0, 0
    
    # Get latest run from scored_df
    latest_run_id = scored_df['run_id'].max()
    latest_scored = scored_df[scored_df['run_id'] == latest_run_id]
    
    w_sharpe = 0
    w_upside = 0
    w_momentum = 0
    w_composite = 0
    
    for stock, weight in zip(stocks, weights):
        stock_data = latest_scored[latest_scored['Stock'] == stock]
        if not stock_data.empty:
            w_sharpe += (stock_data['SharpeRatio_norm'].values[0] if 'SharpeRatio_norm' in stock_data.columns else 0) * weight
            w_upside += (stock_data['PotentialUpside_pct_norm'].values[0] if 'PotentialUpside_pct_norm' in stock_data.columns else 0) * weight
            w_momentum += (stock_data['Momentum_norm'].values[0] if 'Momentum_norm' in stock_data.columns else 0) * weight
            w_composite += (stock_data['CompositeScore'].values[0] if 'CompositeScore' in stock_data.columns else 0) * weight
            
    return w_composite, w_sharpe, w_upside, w_momentum

def main():
    test_run_base_id = f"STAB_{datetime.now().strftime('%Y%m%d_%H%M')}"
    run_ids = []
    
    # Check if necessary files exist
    if not os.path.exists(STOCK_DATA_DB):
        print(f"CRITICAL: Stock Data DB not found at {STOCK_DATA_DB}")
        sys.exit(1)
        
    print(f"Starting stability test with {NUM_RUNS} iterations.")
    
    for i in range(1, NUM_RUNS + 1):
        run_id = f"{test_run_base_id}_{i}"
        start_time = time.time()
        if run_portfolio_engine(run_id):
            elapsed = time.time() - start_time
            print(f"Iteration {i} completed in {elapsed:.1f}s")
            run_ids.append(run_id)
        else:
            print(f"Iteration {i} failed.")
            
    if not run_ids:
        print("No successful runs. Exiting.")
        sys.exit(1)
        
    # Analysis
    print("Analyzing results...")
    df_results = pd.read_csv(PORTFOLIO_DB)
    df_stability = df_results[df_results['run_id'].isin(run_ids)].copy()
    
    # Load support data
    scored_df = pd.read_csv(SCORED_STOCKS_DB) if os.path.exists(SCORED_STOCKS_DB) else None
    price_df = pd.read_csv(STOCK_DATA_DB)
    price_df['Date'] = pd.to_datetime(price_df['Date'])
    
    all_runs_data = []
    composition_tracker = {} # {stock: [weights across runs]}
    
    for _, row in df_stability.iterrows():
        run_id = row['run_id']
        stocks = [s.strip() for s in row['stocks'].split(',')]
        weights = [float(w.strip()) for w in row['weights'].split(',')]
        
        # Performance metrics
        sharpe = row['sharpe_forward']
        exp_ret_12m = row['expected_return_annual_pct'] / 100.0
        
        # Calculate historical return (12m)
        hist_ret_12m, _ = calculate_historical_return_12m(stocks, weights, price_df)
        
        # Aggregate scores
        comp_score, comp_sharpe, comp_upside, comp_momentum = get_aggregate_score_components(stocks, weights, scored_df)
        
        all_runs_data.append({
            'run_id': run_id,
            'sharpe': sharpe,
            'exp_ret_12m': exp_ret_12m * 100,
            'hist_ret_12m': hist_ret_12m * 100,
            'comp_score': comp_score,
            'comp_sharpe': comp_sharpe,
            'comp_upside': comp_upside,
            'comp_momentum': comp_momentum,
            'volatility': row['expected_volatility_annual_pct']
        })
        
        # Track composition
        run_idx = len(all_runs_data) - 1
        # Update existing keys with 0 for this run
        for s in composition_tracker:
            composition_tracker[s].append(0)
            
        # Update with actual weights
        for s, w in zip(stocks, weights):
            if s not in composition_tracker:
                composition_tracker[s] = [0] * run_idx + [w]
            else:
                composition_tracker[s][-1] = w

    df_stats = pd.DataFrame(all_runs_data)
    
    # Generate Report
    with open(STABILITY_REPORT_FILE, 'w', encoding='utf-8') as f:
        f.write("# Relatório de Estabilidade do Modelo\n\n")
        f.write(f"Data do Teste: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
        f.write(f"Número de Execuções: {NUM_RUNS}\n\n")
        
        f.write("## 1. Estatísticas de Performance\n\n")
        f.write("| Métrica | Média | Desvio Padrão | CV (%) | Min | Max |\n")
        f.write("| :--- | :---: | :---: | :---: | :---: | :---: |\n")
        
        metrics = {
            'Sharpe Ratio': 'sharpe',
            'Retorno Esperado (12m %)': 'exp_ret_12m',
            'Retorno Histórico (12m %)': 'hist_ret_12m',
            'Volatilidade (%)': 'volatility',
            'Score Agregado': 'comp_score',
            'Componente Sharpe': 'comp_sharpe',
            'Componente Upside': 'comp_upside',
            'Componente Momentum': 'comp_momentum'
        }
        
        for name, col in metrics.items():
            mean = df_stats[col].mean()
            std = df_stats[col].std()
            cv = (std / abs(mean) * 100) if mean != 0 else 0
            min_val = df_stats[col].min()
            max_val = df_stats[col].max()
            f.write(f"| {name} | {mean:.4f} | {std:.4f} | {cv:.2f}% | {min_val:.4f} | {max_val:.4f} |\n")
            
        f.write("\n> [!TIP]\n")
        f.write("> Um Coeficiente de Variação (CV) abaixo de 5% indica alta estabilidade. Acima de 10% sugere que o modelo pode precisar de mais iterações para convergir.\n\n")
        
        f.write("## 2. Estabilidade da Composição\n\n")
        f.write("| Ativo | Frequência (%) | Peso Médio | Desvio Peso | CV Peso (%) |\n")
        f.write("| :--- | :---: | :---: | :---: | :---: |\n")
        
        composition_stats = []
        for stock, weights_list in composition_tracker.items():
            weights_arr = np.array(weights_list)
            # Ensure all lists have the same length as run_ids
            if len(weights_arr) < len(run_ids):
                weights_arr = np.pad(weights_arr, (0, len(run_ids) - len(weights_arr)), 'constant')
                
            freq = (weights_arr > 0).mean() * 100
            mean_w = weights_arr[weights_arr > 0].mean() if freq > 0 else 0
            std_w = weights_arr[weights_arr > 0].std() if freq > 0 else 0
            cv_w = (std_w / mean_w * 100) if mean_w > 0 else 0
            composition_stats.append({
                'stock': stock,
                'freq': freq,
                'mean_w': mean_w,
                'std_w': std_w,
                'cv_w': cv_w
            })
            
        # Sort by frequency desc
        composition_stats.sort(key=lambda x: x['freq'], reverse=True)
        for s in composition_stats:
            f.write(f"| {s['stock']} | {s['freq']:.1f}% | {s['mean_w']:.4f} | {s['std_w']:.4f} | {s['cv_w']:.2f}% |\n")
            
        f.write("\n## 3. Conclusão e Recomendações\n\n")
        
        # Calculate overall stability based on Sharpe and Expected Return
        main_metrics_cv = [
            (df_stats['sharpe'].std() / abs(df_stats['sharpe'].mean()) * 100) if df_stats['sharpe'].mean() != 0 else 0,
            (df_stats['exp_ret_12m'].std() / abs(df_stats['exp_ret_12m'].mean()) * 100) if df_stats['exp_ret_12m'].mean() != 0 else 0
        ]
        max_cv = max(main_metrics_cv)
        
        if max_cv < 5:
            f.write("O modelo apresenta **alta estabilidade**. Os resultados são consistentes e convergem para um ótimo global claro.\n")
        elif max_cv < 10:
            f.write("O modelo apresenta **estabilidade moderada**. Existe alguma variação, mas a Seleção de Ativos principal permanece constante.\n")
        else:
            f.write("O modelo apresenta **baixa estabilidade**. A alta variabilidade sugere que o espaço de busca é complexo e o algoritmo pode estar parando em ótimos locais.\n")
            f.write("\n**Ações Recomendadas:**\n")
            f.write("- Aumentar o número de gerações do Algoritmo Genético (`ga_num_generations`).\n")
            f.write("- Aumentar o tamanho da população (`ga_population_size`).\n")
            f.write("- Aumentar o número de simulações adaptativas.\n")

    print(f"Stability report generated at: {STABILITY_REPORT_FILE}")

if __name__ == "__main__":
    main()
