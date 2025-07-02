import pandas as pd
import os # Required for os.path.expanduser

# --- Configuration ---
# This script now reads the same files as Engine.py to provide a relevant status check.
SCORED_RUNS_FILE_PATH = os.path.expanduser("~/Documents/Prog/PortfolioESG_Data/Results/scored_runs.csv")
STOCK_DATA_DB_PATH = os.path.expanduser("~/Documents/Prog/PortfolioESG_Data/findb/StockDataDB.csv")
TOP_N_STOCKS_TO_CHECK = 20 # Set this to match 'top_n_stocks_from_score' in simpar.txt

def load_top_scored_stocks(filepath, top_n):
    """Loads the top N stocks from the most recent run in the scored_runs.csv file."""
    if not os.path.exists(filepath):
        print(f"ERROR: Scored runs file not found at {filepath}.")
        return []
    try:
        df = pd.read_csv(filepath)
        latest_run_id = df['run_id'].max()
        latest_run_df = df[df['run_id'] == latest_run_id]
        top_stocks = latest_run_df.sort_values(by='CompositeScore', ascending=False).head(top_n)['Stock'].tolist()
        return top_stocks
    except Exception as e:
        print(f"An error occurred while reading the scored runs file: {e}")
        return []

# --- Main Execution ---
portfolio_stocks = load_top_scored_stocks(SCORED_RUNS_FILE_PATH, TOP_N_STOCKS_TO_CHECK)
if not portfolio_stocks:
    print("Could not load any stocks to check. Exiting.")
    exit(1)

try:
    df = pd.read_csv(STOCK_DATA_DB_PATH)
    # Use format='mixed' for robust parsing and .dt.date to keep only the date part
    df['Date'] = pd.to_datetime(df['Date'], format='mixed', errors='coerce').dt.date

    print(f"Checking data in: {STOCK_DATA_DB_PATH}")
    print(f"Checking status for the top {TOP_N_STOCKS_TO_CHECK} stocks from the latest scoring run.")
    print(f"Stocks to be used by Engine: {portfolio_stocks}\n")

    latest_dates = {}
    all_stocks_present_in_csv = True
    all_stocks_have_data = True

    for stock in portfolio_stocks:
        if stock in df['Stock'].unique():
            stock_df = df[df['Stock'] == stock]
            if not stock_df.empty:
                latest_date = stock_df['Date'].max()
                latest_dates[stock] = latest_date
                print(f"Latest data for {stock}: {latest_date.strftime('%Y-%m-%d')}")
            else:
                print(f"WARNING: Stock {stock} is in StockDataDB.csv but has no date entries after filtering (if any).")
                latest_dates[stock] = None
                all_stocks_have_data = False
        else:
            print(f"WARNING: Stock {stock} not found in StockDataDB.csv!")
            latest_dates[stock] = None
            all_stocks_present_in_csv = False

    if not all_stocks_present_in_csv:
        print("\nCRITICAL: One or more portfolio stocks are entirely missing from StockDataDB.csv.")
        print("Engine.py will likely fail or produce incomplete results.")
    elif not all_stocks_have_data:
        print("\nWARNING: One or more portfolio stocks have no data entries in StockDataDB.csv (or were filtered out).")
        print("This will cause Engine.py to truncate data significantly.")
    elif latest_dates:
        # Filter out None values before finding min, in case some stocks had no data
        valid_latest_dates = [d for d in latest_dates.values() if d is not None]
        if not valid_latest_dates:
            print("\nCRITICAL: None of the portfolio stocks have valid date entries in StockDataDB.csv.")
        else:
            limiting_date = min(valid_latest_dates)
            print(f"\nAfter considering all stocks in your portfolio, the data for chart generation")
            print(f"will effectively be available up to: {limiting_date.strftime('%Y-%m-%d')}")
            print("This is because Engine.py removes dates where *any* stock in the portfolio has missing data.")

            reference_date_ts = pd.to_datetime("2025-04-14")
            if limiting_date > reference_date_ts.date(): # Compare date object with date object
                print(f"\nSUCCESS: StockDataDB.csv now contains data beyond {reference_date_ts.date().strftime('%Y-%m-%d')} for all portfolio stocks.")
                print("Running Engine.py again should update the chart with this more recent data.")
            else:
                print(f"\nINFO: StockDataDB.csv still does not have complete data for all portfolio stocks")
                print(f"significantly beyond {reference_date_ts.date().strftime('%Y-%m-%d')} (limited by date: {limiting_date.strftime('%Y-%m-%d')}).")
                print("If Download.py reported success but data is still missing for specific stocks,")
                print("you might want to check the download log file specified in 'downpar.txt' for any warnings or errors related to those stocks.")
except FileNotFoundError:
    print(f"ERROR: StockDataDB.csv not found at {STOCK_DATA_DB_PATH}")
except Exception as e:
    print(f"An error occurred while checking the CSV: {e}")
