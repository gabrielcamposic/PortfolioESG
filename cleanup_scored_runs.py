#!/usr/bin/env python
import csv
import os

# --- Configuration ---
# This should point to the file you want to clean.
SCORED_RUNS_FILE = os.path.expanduser('~/Documents/Prog/PortfolioESG_Data/findb/scored_runs.csv')
# --- End Configuration ---

def cleanup_csv_by_schema(filepath):
    """
    Cleans a CSV file by keeping only the rows that match the schema of the last row.
    This is useful for fixing files corrupted by appending data with different columns.
    """
    if not os.path.exists(filepath):
        print(f"File not found: {filepath}")
        return

    print(f"Starting cleanup of: {filepath}")

    # Read all lines first to handle potential parsing errors
    with open(filepath, 'r', newline='', encoding='utf-8') as f:
        lines = f.readlines()

    if len(lines) < 2:
        print("File has less than two lines (header + data). No cleanup needed.")
        return

    # Determine the correct number of columns from the last line
    last_line_reader = csv.reader([lines[-1]])
    try:
        correct_num_columns = len(next(last_line_reader))
        print(f"Determined correct schema should have {correct_num_columns} columns (based on the last row).")
    except StopIteration:
        print("Could not parse the last line. Aborting cleanup.")
        return

    # Filter ALL lines based on the correct column count.
    # This will keep the correct header and the correct data rows, and discard old ones.
    cleaned_lines = []
    rows_removed = 0

    for i, line in enumerate(lines, 1): # Iterate through ALL lines from the start
        row_reader = csv.reader([line])
        try:
            num_columns = len(next(row_reader))
            if num_columns == correct_num_columns:
                cleaned_lines.append(line)
            else:
                print(f"  - Removing malformed line {i}: Expected {correct_num_columns} columns, found {num_columns}.")
                rows_removed += 1
        except StopIteration: # Handle empty lines
            print(f"  - Removing empty line {i}.")
            rows_removed += 1

    if rows_removed == 0:
        print("No rows with incorrect schema found. File is already clean.")
        return

    with open(filepath, 'w', newline='', encoding='utf-8') as f:
        f.writelines(cleaned_lines)
    print(f"\nCleanup complete. Removed {rows_removed} malformed rows. File has been updated.")

if __name__ == "__main__":
    cleanup_csv_by_schema(SCORED_RUNS_FILE)