#!/bin/bash
# --- Configuration ---
PIPELINE_SCRIPT_VERSION="1.2.0" # Added error handling, detailed logging, JSON updates
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
       "current_stage": "Initializing pipeline...",
       "end_time": "N/A" # Add end time for pipeline status
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
       "current_ticker": "Waiting for download.py to start...", # download.py will overwrite this
       "overall_status": "Pending", # Add status for download step
       "date_range": "N/A",
       "rows": 0
     },

     # Initial state for Portfolio Optimization Progress (Engine.py)
     # Matches keys expected by progress.html for this section
     "engine_script_start_time": "N/A",
     "estimated_completion_time": "N/A",
     "engine_script_end_time": "N/A",
     "engine_script_total_duration": "N/A",
     "engine_overall_status": "Pending", # Add status for engine step
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

# Function to update progress.json using jq
update_progress_json() {
    local KEY="$1"
    local VALUE="$2"
    # Use a temporary file to avoid issues with jq modifying the file it's reading
    jq --arg key "$KEY" --argjson value "$VALUE" '.[$key] = $value' "$PROGRESS_JSON_FULL_PATH" > "$PROGRESS_JSON_FULL_PATH.tmp" && mv "$PROGRESS_JSON_FULL_PATH.tmp" "$PROGRESS_JSON_FULL_PATH"
}

# Update pipeline status in JSON
update_progress_json "pipeline_run_status" '{ "status_message": "Pipeline is running.", "start_time": "'"$CURRENT_TIMESTAMP"'", "current_stage": "Starting Download.py..." }'


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
"$PYTHON_EXEC" "$DOWNLOAD_SCRIPT" >> "$PIPELINE_LOG_FILE" 2>&1
DOWNLOAD_EXIT_CODE=$?
DOWNLOAD_END_TIME_S=$(date +%s)
DOWNLOAD_DURATION_S=$((DOWNLOAD_END_TIME_S - DOWNLOAD_START_TIME_S))
DOWNLOAD_DURATION_FMT=$(format_duration $DOWNLOAD_DURATION_S)

if [ $DOWNLOAD_EXIT_CODE -eq 0 ]; then
    # Download was successful
    update_progress_json "download_overall_status" '"Completed Successfully"'
    log_message "Download.py completed successfully in $DOWNLOAD_DURATION_FMT."

    # --- Step 2: Run Engine.py ---
    # Update pipeline status to indicate starting Engine.py
    update_progress_json "pipeline_run_status" '{ "status_message": "Pipeline is running.", "start_time": "'"$CURRENT_TIMESTAMP"'", "current_stage": "Starting Engine.py...", "end_time": "N/A" }'
    log_message "Starting Engine.py..."
    ENGINE_START_TIME_S=$(date +%s)
    # Redirect stdout and stderr to the pipeline log file
    "$PYTHON_EXEC" "$ENGINE_SCRIPT" >> "$PIPELINE_LOG_FILE" 2>&1
    ENGINE_EXIT_CODE=$?
    ENGINE_END_TIME_S=$(date +%s)
    ENGINE_DURATION_S=$((ENGINE_END_TIME_S - ENGINE_START_TIME_S))
    ENGINE_DURATION_FMT=$(format_duration $ENGINE_DURATION_S)

    if [ $ENGINE_EXIT_CODE -eq 0 ]; then
        # Engine was successful
        # update_progress_json "engine_overall_status" '"Completed Successfully"' # Engine.py now handles this
        log_message "Engine.py completed successfully in $ENGINE_DURATION_FMT."
        # Pipeline successful completion
        PIPELINE_END_TIME_S=$(date +%s)
        PIPELINE_DURATION_S=$((PIPELINE_END_TIME_S - PIPELINE_START_TIME_S))
        PIPELINE_DURATION_FMT=$(format_duration $PIPELINE_DURATION_S)
        log_message "Portfolio Pipeline Finished successfully in $PIPELINE_DURATION_FMT."
        log_message "======================================"
        echo "" >> "$PIPELINE_LOG_FILE"

        log_message "DEBUG: About to update pipeline_run_status to completed."
        FINAL_STATUS_JSON_VALUE='{ "status_message": "Pipeline completed successfully.", "start_time": "'"$CURRENT_TIMESTAMP"'", "current_stage": "Pipeline Completed", "end_time": "'$(date +"%Y-%m-%d %H:%M:%S")'" }'
        log_message "DEBUG: FINAL_STATUS_JSON_VALUE is: $FINAL_STATUS_JSON_VALUE"

        # Final pipeline status update in JSON
        update_progress_json "pipeline_run_status" "$FINAL_STATUS_JSON_VALUE"
        JQ_EXIT_CODE=$?
        log_message "DEBUG: jq exit code for final pipeline_run_status update: $JQ_EXIT_CODE"
        if [ $JQ_EXIT_CODE -ne 0 ]; then
            log_message "ERROR: jq command failed to update pipeline_run_status to completed."
        else
            log_message "DEBUG: Successfully updated pipeline_run_status to completed (or jq reported success)."
        fi
        log_message "DEBUG: Content of progress.json after final update attempt:"
        cat "$PROGRESS_JSON_FULL_PATH" >> "$PIPELINE_LOG_FILE"

        exit 0 # Exit with success code
    else
        # Engine failed
        update_progress_json "engine_overall_status" '"Failed"'
        log_message "Error: Engine.py failed with exit code $ENGINE_EXIT_CODE after $ENGINE_DURATION_FMT."
        # Pipeline failed during Engine step
        PIPELINE_END_TIME_S=$(date +%s)
        PIPELINE_DURATION_S=$((PIPELINE_END_TIME_S - PIPELINE_START_TIME_S))
        PIPELINE_DURATION_FMT=$(format_duration $PIPELINE_DURATION_S)
        log_message "Portfolio Pipeline Finished with errors in Engine.py after $PIPELINE_DURATION_FMT."
        log_message "======================================"
        echo "" >> "$PIPELINE_LOG_FILE"
        update_progress_json "pipeline_run_status" '{ "status_message": "Pipeline failed during Engine.py.", "start_time": "'"$CURRENT_TIMESTAMP"'", "current_stage": "Engine Failed", "end_time": "'$(date +"%Y-%m-%d %H:%M:%S")'" }'
        exit 1 # Exit with failure code
    fi
else
    # Download failed
    update_progress_json "download_overall_status" '"Failed"'
    log_message "Error: Download.py failed with exit code $DOWNLOAD_EXIT_CODE after $DOWNLOAD_DURATION_FMT. Engine.py will not run."
    # Pipeline failed during Download step
    update_progress_json "pipeline_run_status" '{ "status_message": "Pipeline failed during Download.py.", "start_time": "'"$CURRENT_TIMESTAMP"'", "current_stage": "Download Failed" }'
    # Pipeline failed completion
    PIPELINE_END_TIME_S=$(date +%s)
    PIPELINE_DURATION_S=$((PIPELINE_END_TIME_S - PIPELINE_START_TIME_S))
    PIPELINE_DURATION_FMT=$(format_duration $PIPELINE_DURATION_S)
    log_message "Portfolio Pipeline Finished with errors in Download.py after $PIPELINE_DURATION_FMT."
    log_message "======================================"
    echo "" >> "$PIPELINE_LOG_FILE"
    exit 1 # Exit with failure code
fi

# The lines from 161 to 172 in the original script (calculating final pipeline duration and exiting)
# are now handled within the respective success/failure branches of the if/else logic above.
# This ensures the script exits with the correct status code and logs the final state accurately.