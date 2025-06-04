#!/bin/bash
# --- Configuration ---
PIPELINE_SCRIPT_VERSION="1.1.0" # Added explicit script versioning
PROJECT_DIR="/home/gabrielcampos/PortfolioESG_Prod"
LOG_DIR="$PROJECT_DIR/Logs"
PIPELINE_LOG_FILE="$LOG_DIR/pipeline_execution.log"
PROGRESS_JSON_FULL_PATH="/home/gabrielcampos/PortfolioESG_Prod/html/progress.json"

# --- Ensure Project and Log Directories Exist ---
cd "$PROJECT_DIR" || {
    echo "Error: Could not navigate to project directory $PROJECT_DIR. Exiting."
    exit 1
}
mkdir -p "$LOG_DIR"

# --- Logging Function ---
log_message() {
    echo "$(date '+%Y-%m-%d %H:%M:%S') - $1" | tee -a "$PIPELINE_LOG_FILE"
}

# --- Duration Formatting Function ---
format_duration() {
    local T_SECONDS=$1
    local DAYS=$((T_SECONDS/60/60/24))
    local HOURS=$((T_SECONDS/60/60%24))
    local MINUTES=$((T_SECONDS/60%60))
    local SECONDS=$((T_SECONDS%60))
    local DURATION_STR=""
    if [ "$DAYS" -gt 0 ]; then
        DURATION_STR="${DAYS}d "
    fi
    printf "%s%02d:%02d:%02d" "$DURATION_STR" "$HOURS" "$MINUTES" "$SECONDS"
}

# --- Main Execution ---

# Current timestamp
CURRENT_TIMESTAMP=$(date +"%Y-%m-%d %H:%M:%S")

# Create/overwrite progress.json with initial status for all sections
jq -n \
  --arg startTime "$CURRENT_TIMESTAMP" \
  '{
     # New section for overall pipeline status
     "pipeline_run_status": {
       "status_message": "Pipeline execution started.",
       "start_time": $startTime,
       "current_stage": "Initializing pipeline..."
     },

     # Initial state for Stock Database Update (download.py)
     # Matches keys expected by progress.html for this section
     "download_execution_start": $startTime, # Indicates pipeline start, download.py will overwrite
     "download_execution_end": "N/A",
     "download_overall_status": "Pipeline Initialized - Awaiting Download",
     "ticker_download": {
       "completed_tickers": 0,
       "total_tickers": 0,
       "progress": 0,
       "current_ticker": "Waiting for download.py to start...",
       "date_range": "N/A",
       "rows": 0
     },

     # Initial state for Portfolio Optimization Progress (Engine.py)
     # Matches keys expected by progress.html for this section
     "engine_script_start_time": "N/A",
     "estimated_completion_time": "N/A",
     "engine_script_end_time": "N/A",
     "engine_script_total_duration": "N/A",
     "current_engine_phase": "Pipeline Initialized - Awaiting Optimization",
     "overall_progress": { # For Brute-Force
        "completed_actual_simulations_bf": 0,
        "total_expected_actual_simulations_bf": 0,
        "percentage_bf": 0,
        "estimated_completion_time_bf": "N/A"
     },
     "ga_progress": { # For GA
        "status": "Pending",
        "current_k": 0,
        "current_generation": 0,
        "current_individual_ga": 0,
        "percentage_ga": 0,
        "total_individuals_ga": 0,
        "total_generations_ga": 0,
        "best_sharpe_this_k": "N/A"
     },
     "refinement_progress": { # For Refinement
        "status": "Pending",
        "details": "N/A",
        "current_combo_refined": 0, "total_combos_to_refine": 0, "percentage_refinement": 0
     }
     # "best_portfolio_details" (for Best Overall Portfolio section) is intentionally omitted
   }' > "$PROGRESS_JSON_FULL_PATH"

echo "Initial progress.json written to $PROGRESS_JSON_FULL_PATH"

# Define the Python interpreter from the pyenv environment
# This matches the shebang in your Python scripts.
PYTHON_EXEC="/home/gabrielcampos/.pyenv/versions/env-fa/bin/python"

if [ ! -x "$PYTHON_EXEC" ]; then
    log_message "Error: Python executable $PYTHON_EXEC not found or not executable. Please check the path."
    # Fallback to system python3 if pyenv one is not found (less ideal, but for safety)
    PYTHON_EXEC="python3"
fi

PIPELINE_START_TIME_S=$(date +%s)
log_message "--------------------------------------"
log_message "Portfolio Pipeline Started"
log_message "--------------------------------------"
log_message "Pipeline Script Version: $PIPELINE_SCRIPT_VERSION"

log_message "Using Python interpreter: $($PYTHON_EXEC --version 2>&1)"

# Define paths to your Python scripts (relative to PROJECT_DIR)
DOWNLOAD_SCRIPT="./Download.py" # Note: Case-sensitive on Linux
ENGINE_SCRIPT="./Engine.py"     # Note: Case-sensitive on Linux

# --- Step 1: Run download.py ---
log_message "Starting Download.py..."
DOWNLOAD_START_TIME_S=$(date +%s)
# The output of Download.py (stdout and stderr) will be appended to $PIPELINE_LOG_FILE
# which, in your cron setup, is pipeline_cron.log.
# This ensures Python tracebacks are captured here.
"$PYTHON_EXEC" "$DOWNLOAD_SCRIPT"
DOWNLOAD_EXIT_CODE=$?
DOWNLOAD_END_TIME_S=$(date +%s)
DOWNLOAD_DURATION_S=$((DOWNLOAD_END_TIME_S - DOWNLOAD_START_TIME_S))
DOWNLOAD_DURATION_FMT=$(format_duration $DOWNLOAD_DURATION_S)

if [ $DOWNLOAD_EXIT_CODE -eq 0 ]; then
    log_message "Download.py completed successfully in $DOWNLOAD_DURATION_FMT."

    # --- Step 2: Run Engine.py ---
    log_message "Starting Engine.py..."
    ENGINE_START_TIME_S=$(date +%s)
    "$PYTHON_EXEC" "$ENGINE_SCRIPT"
    ENGINE_EXIT_CODE=$?
    ENGINE_END_TIME_S=$(date +%s)
    ENGINE_DURATION_S=$((ENGINE_END_TIME_S - ENGINE_START_TIME_S))
    ENGINE_DURATION_FMT=$(format_duration $ENGINE_DURATION_S)

    if [ $ENGINE_EXIT_CODE -eq 0 ]; then
        log_message "Engine.py completed successfully in $ENGINE_DURATION_FMT."
    else
        log_message "Error: Engine.py failed with exit code $ENGINE_EXIT_CODE after $ENGINE_DURATION_FMT."
    fi
else
    log_message "Error: Download.py failed with exit code $DOWNLOAD_EXIT_CODE after $DOWNLOAD_DURATION_FMT. Engine.py will not run."
fi

PIPELINE_END_TIME_S=$(date +%s)
PIPELINE_DURATION_S=$((PIPELINE_END_TIME_S - PIPELINE_START_TIME_S))
PIPELINE_DURATION_FMT=$(format_duration $PIPELINE_DURATION_S)

log_message "Portfolio Pipeline Finished in $PIPELINE_DURATION_FMT."
log_message "======================================"
echo "" >> "$PIPELINE_LOG_FILE"

exit 0