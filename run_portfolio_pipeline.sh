#!/bin/bash
# --- Configuration ---
PIPELINE_SCRIPT_VERSION="1.3.0" # Added Scoring.py stage
PROJECT_DIR="/home/gabrielcampos/PortfolioESG_Prod"
LOG_DIR="$PROJECT_DIR/Logs"
PIPELINE_LOG_FILE="$LOG_DIR/pipeline_execution.log"
PROGRESS_JSON_FULL_PATH="/home/gabrielcampos/PortfolioESG_Prod/html/progress.json"
# Define the absolute path to jq.
JQ_EXEC="/usr/bin/jq"

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
$JQ_EXEC -n \
  --arg startTime "$CURRENT_TIMESTAMP" \
  '{
    "pipeline_run_status": {
      "status_message": "Pipeline execution started.",
      "start_time": $startTime,
      "current_stage": "Initializing pipeline...",
      "end_time": "N/A"
    },
    "scoring_status": "Pending",
    "scoring_start_time": "N/A",
    "scoring_end_time": "N/A",
    "download_execution_start": $startTime,
    "download_execution_end": "N/A",
    "download_overall_status": "Pipeline Initialized - Awaiting Download",
    "ticker_download": {
      "completed_tickers": 0,
      "total_tickers": 0,
      "progress": 0,
      "current_ticker": "Waiting for download.py to start...",
      "overall_status": "Pending",
      "date_range": "N/A",
      "rows": 0
    },
    "engine_script_start_time": "N/A",
    "estimated_completion_time": "N/A",
    "engine_script_end_time": "N/A",
    "engine_script_total_duration": "N/A",
    "engine_overall_status": "Pending",
    "current_engine_phase": "Pipeline Initialized - Awaiting Optimization",
    "overall_progress": {
      "completed_actual_simulations_bf": 0,
      "total_expected_actual_simulations_bf": 0,
      "percentage_bf": 0,
      "estimated_completion_time_bf": "N/A"
    },
    "ga_progress": {
      "status": "Pending",
      "current_k": 0,
      "current_generation": 0,
      "current_individual_ga": 0,
      "percentage_ga": 0,
      "total_individuals_ga": 0,
      "total_generations_ga": 0,
      "best_sharpe_this_k": "N/A"
    },
    "refinement_progress": {
      "status": "Pending",
      "details": "N/A",
      "current_combo_refined": 0,
      "total_combos_to_refine": 0,
      "percentage_refinement": 0
    }
  }' > "$PROGRESS_JSON_FULL_PATH"

echo "Initial progress.json written to $PROGRESS_JSON_FULL_PATH"

# Function to update progress.json using jq
update_progress_json() {
    local KEY="$1"
    local VALUE="$2"
    local TEMP_JSON_FILE="$PROGRESS_JSON_FULL_PATH.tmp"

    log_message "DEBUG: update_progress_json: Attempting to update key '$KEY' with value '$VALUE'"

    # Use a temporary file to avoid issues with jq modifying the file it's reading
    # Capture jq's output (new JSON) and any errors.
    local JQ_CMD_OUTPUT
    JQ_CMD_OUTPUT=$($JQ_EXEC --arg key "$KEY" --argjson value "$VALUE" '.[$key] = $value' "$PROGRESS_JSON_FULL_PATH" 2>&1)
    local JQ_REAL_EXIT_CODE=$?

    if [ $JQ_REAL_EXIT_CODE -eq 0 ]; then
        # jq succeeded, JQ_CMD_OUTPUT contains the new JSON
        echo "$JQ_CMD_OUTPUT" > "$TEMP_JSON_FILE"
        if [ $? -ne 0 ]; then
            log_message "ERROR: Failed to write jq output to temporary file '$TEMP_JSON_FILE' for key '$KEY'."
            rm -f "$TEMP_JSON_FILE" # Clean up partial write if any
            return 1 # Indicate failure
        fi

        mv "$TEMP_JSON_FILE" "$PROGRESS_JSON_FULL_PATH"
        if [ $? -ne 0 ]; then
            log_message "ERROR: Failed to move temporary file '$TEMP_JSON_FILE' to '$PROGRESS_JSON_FULL_PATH' for key '$KEY'."
            return 1 # Indicate failure
        fi
        return 0
    else
        # jq failed
        log_message "ERROR: $JQ_EXEC command failed for key '$KEY'. Exit code: $JQ_REAL_EXIT_CODE."
        log_message "ERROR: Value passed to --argjson for key '$KEY' was: '$VALUE'"
        log_message "ERROR: jq output/error was: $JQ_CMD_OUTPUT"
        return $JQ_REAL_EXIT_CODE
    fi
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
DOWNLOAD_SCRIPT="./Download.py"   # Note: Case-sensitive on Linux
SCORING_SCRIPT="./Scoring.py"     # Note: Case-sensitive on Linux
ENGINE_SCRIPT="./Engine.py"       # Note: Case-sensitive on Linux

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

    # --- Step 2: Run Scoring.py ---
    update_progress_json "pipeline_run_status" '{ "status_message": "Pipeline is running.", "start_time": "'"$CURRENT_TIMESTAMP"'", "current_stage": "Starting Scoring.py..." }'
    log_message "Starting Scoring.py..."
    SCORING_START_TIME_S=$(date +%s)
    "$PYTHON_EXEC" "$SCORING_SCRIPT" >> "$PIPELINE_LOG_FILE" 2>&1
    SCORING_EXIT_CODE=$?
    SCORING_END_TIME_S=$(date +%s)
    SCORING_DURATION_S=$((SCORING_END_TIME_S - SCORING_START_TIME_S))
    SCORING_DURATION_FMT=$(format_duration $SCORING_DURATION_S)

    if [ $SCORING_EXIT_CODE -eq 0 ]; then
        # Scoring was successful
        # Scoring.py itself updates its status to "Completed", so we don't need to do it here.
        log_message "Scoring.py completed successfully in $SCORING_DURATION_FMT."

        # --- Step 3: Run Engine.py ---
        update_progress_json "pipeline_run_status" '{ "status_message": "Pipeline is running.", "start_time": "'"$CURRENT_TIMESTAMP"'", "current_stage": "Starting Engine.py...", "end_time": "N/A" }'
        log_message "Starting Engine.py..."
        ENGINE_START_TIME_S=$(date +%s)
        "$PYTHON_EXEC" "$ENGINE_SCRIPT" >> "$PIPELINE_LOG_FILE" 2>&1
        ENGINE_EXIT_CODE=$?
        ENGINE_END_TIME_S=$(date +%s)
        ENGINE_DURATION_S=$((ENGINE_END_TIME_S - ENGINE_START_TIME_S))
        ENGINE_DURATION_FMT=$(format_duration $ENGINE_DURATION_S)

        if [ $ENGINE_EXIT_CODE -eq 0 ]; then
            # Engine was successful
            log_message "Engine.py completed successfully in $ENGINE_DURATION_FMT."
            PIPELINE_END_TIME_S=$(date +%s)
            PIPELINE_DURATION_S=$((PIPELINE_END_TIME_S - PIPELINE_START_TIME_S))
            PIPELINE_DURATION_FMT=$(format_duration $PIPELINE_DURATION_S)
            log_message "Portfolio Pipeline Finished successfully in $PIPELINE_DURATION_FMT."
            log_message "======================================"
            echo "" >> "$PIPELINE_LOG_FILE"

            FINAL_STATUS_JSON_VALUE='{ "status_message": "Pipeline completed successfully.", "start_time": "'"$CURRENT_TIMESTAMP"'", "current_stage": "Pipeline Completed", "end_time": "'$(date +"%Y-%m-%d %H:%M:%S")'" }'
            update_progress_json "pipeline_run_status" "$FINAL_STATUS_JSON_VALUE"
            exit 0
        else
            # Engine failed
            log_message "Error: Engine.py failed with exit code $ENGINE_EXIT_CODE after $ENGINE_DURATION_FMT."
            PIPELINE_END_TIME_S=$(date +%s)
            PIPELINE_DURATION_S=$((PIPELINE_END_TIME_S - PIPELINE_START_TIME_S))
            PIPELINE_DURATION_FMT=$(format_duration $PIPELINE_DURATION_S)
            log_message "Portfolio Pipeline Finished with errors in Engine.py after $PIPELINE_DURATION_FMT."
            log_message "======================================"
            echo "" >> "$PIPELINE_LOG_FILE"
            update_progress_json "pipeline_run_status" '{ "status_message": "Pipeline failed during Engine.py.", "start_time": "'"$CURRENT_TIMESTAMP"'", "current_stage": "Engine Failed", "end_time": "'$(date +"%Y-%m-%d %H:%M:%S")'" }'
            exit 1
        fi
    else
        # Scoring failed
        # Scoring.py should update its own status to "Failed" in progress.json
        log_message "Error: Scoring.py failed with exit code $SCORING_EXIT_CODE after $SCORING_DURATION_FMT. Engine.py will not run."
        PIPELINE_END_TIME_S=$(date +%s)
        PIPELINE_DURATION_S=$((PIPELINE_END_TIME_S - PIPELINE_START_TIME_S))
        PIPELINE_DURATION_FMT=$(format_duration $PIPELINE_DURATION_S)
        log_message "Portfolio Pipeline Finished with errors in Scoring.py after $PIPELINE_DURATION_FMT."
        log_message "======================================"
        echo "" >> "$PIPELINE_LOG_FILE"
        update_progress_json "pipeline_run_status" '{ "status_message": "Pipeline failed during Scoring.py.", "start_time": "'"$CURRENT_TIMESTAMP"'", "current_stage": "Scoring Failed", "end_time": "'$(date +"%Y-%m-%d %H:%M:%S")'" }'
        exit 1
    fi
else
    # Download failed
    update_progress_json "download_overall_status" '"Failed"'
    log_message "Error: Download.py failed with exit code $DOWNLOAD_EXIT_CODE after $DOWNLOAD_DURATION_FMT. Subsequent steps will not run."
    # Pipeline failed during Download step
    update_progress_json "pipeline_run_status" '{ "status_message": "Pipeline failed during Download.py.", "start_time": "'"$CURRENT_TIMESTAMP"'", "current_stage": "Download Failed" }'
    # Pipeline failed completion
    PIPELINE_END_TIME_S=$(date +%s)
    PIPELINE_DURATION_S=$((PIPELINE_END_TIME_S - PIPELINE_START_TIME_S))
    PIPELINE_DURATION_FMT=$(format_duration $PIPELINE_DURATION_S)
    log_message "Portfolio Pipeline Finished with errors in Download.py after $PIPELINE_DURATION_FMT."
    log_message "======================================"
    echo "" >> "$PIPELINE_LOG_FILE"
    exit 1
fi

# The lines from 161 to 172 in the original script (calculating final pipeline duration and exiting)
# are now handled within the respective success/failure branches of the if/else logic above.
# This ensures the script exits with the correct status code and logs the final state accurately.