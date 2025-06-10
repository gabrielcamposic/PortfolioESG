import pandas as pd
import os # Required for os.path.expanduser

# --- Configuration from your simpar.txt ---
# Using the absolute path based on your context
stock_data_file_path = "/Users/gabrielcampos/Documents/Prog/PortfolioESG_Data/findb/StockDataDB.csv"
esg_stocks_list_str = "ALUP11.SA, B3SA3.SA, FLRY3.SA, ITUB4.SA, LREN3.SA, ORVR3.SA, SRNA3.SA, SUZB3.SA, VIVT3.SA, WEGE3.SA"
# --- End Configuration ---

esg_stocks = [stock.strip() for stock in esg_stocks_list_str.split(',')]

try:
    # No need for expanduser here as we're using the absolute path
    df = pd.read_csv(stock_data_file_path)
    # Use format='mixed' for robust parsing and .dt.date to keep only the date part
    df['Date'] = pd.to_datetime(df['Date'], format='mixed', errors='coerce').dt.date

    print(f"Checking data in: {stock_data_file_path}")
    print(f"Portfolio stocks: {esg_stocks}\n")

    latest_dates = {}
    all_stocks_present_in_csv = True
    all_stocks_have_data = True

    for stock in esg_stocks:
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
    print(f"ERROR: StockDataDB.csv not found at {stock_data_file_path}")
except Exception as e:
    print(f"An error occurred while checking the CSV: {e}")
