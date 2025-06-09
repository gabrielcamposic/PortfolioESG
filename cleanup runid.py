import pandas as pd
import os

# --- Configuration ---
RUN_ID_TO_REMOVE = "20250609_114424"
RESULTS_LOG_PATH = os.path.expanduser("~/Documents/Prog/PortfolioESG_Data/Results/engine_results_log.csv")
HISTORY_LOG_PATH = os.path.expanduser("~/Documents/Prog/PortfolioESG_Data/Results/portfolio_value_history.csv")

# --- Paths for web-accessible copies ---
WEB_RESULTS_LOG_PATH = os.path.expanduser("~/Documents/Prog/PortfolioESG_public/html/data/engine_results_log.csv")
WEB_HISTORY_LOG_PATH = os.path.expanduser("~/Documents/Prog/PortfolioESG_public/html/data/portfolio_value_history.csv")

# --- Function to remove run from a CSV file ---
def remove_run_from_csv(filepath, run_id_column_name, run_id_to_remove):
    if not os.path.exists(filepath):
        print(f"File not found: {filepath}. Skipping.")
        return

    try:
        df = pd.read_csv(filepath)
        original_row_count = len(df)

        # Ensure the run_id_column_name exists
        if run_id_column_name not in df.columns:
            print(f"Column '{run_id_column_name}' not found in {filepath}. Skipping.")
            return

        # Filter out the specified run_id
        # Convert run_id_to_remove to the same type as the column for safe comparison
        if df[run_id_column_name].dtype == 'object': # String type
             df_filtered = df[df[run_id_column_name].astype(str) != str(run_id_to_remove)]
        else: # Numeric type (less likely for run_id but good to be safe)
             df_filtered = df[df[run_id_column_name] != type(df[run_id_column_name].iloc[0])(run_id_to_remove)]


        removed_rows = original_row_count - len(df_filtered)

        if removed_rows > 0:
            df_filtered.to_csv(filepath, index=False)
            print(f"Removed {removed_rows} row(s) for run_id '{run_id_to_remove}' from {filepath}")
        else:
            print(f"No rows found for run_id '{run_id_to_remove}' in {filepath}")

    except Exception as e:
        print(f"Error processing file {filepath}: {e}")

# --- Main execution ---
if __name__ == "__main__":
    print(f"Attempting to remove run_id: {RUN_ID_TO_REMOVE}")
    print("-" * 30)

    print("Cleaning source log files...")
    # Remove from source engine_results_log.csv
    # The column name for run ID in this file is 'run_id'
    remove_run_from_csv(RESULTS_LOG_PATH, "run_id", RUN_ID_TO_REMOVE)

    # Remove from source portfolio_value_history.csv
    # The column name for run ID in this file is 'RunID'
    remove_run_from_csv(HISTORY_LOG_PATH, "RunID", RUN_ID_TO_REMOVE)

    print("\nCleaning web-accessible log files...")
    # Remove from web-accessible engine_results_log.csv
    remove_run_from_csv(WEB_RESULTS_LOG_PATH, "run_id", RUN_ID_TO_REMOVE)

    # Remove from web-accessible portfolio_value_history.csv
    remove_run_from_csv(WEB_HISTORY_LOG_PATH, "RunID", RUN_ID_TO_REMOVE)

    print("-" * 30)
    print("\nCleanup attempt finished.")
    print("Check the output above to see if the run ID was found and removed from the files.")
    print("Refresh esgportfolio.html to see the changes.")
