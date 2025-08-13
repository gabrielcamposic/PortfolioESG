#!/bin/bash

# Exit immediately if a command exits with a non-zero status.
set -e
# Treat unset variables as an error when substituting.
set -u
# Pipelines fail if any command in the pipeline fails, not just the last one.
set -o pipefail

# --- Configuration ---
# Get the directory where the script is located
SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" &> /dev/null && pwd )"
PROJECT_ROOT=$(realpath "$SCRIPT_DIR/..")

# This allows Python to find modules like 'shared_tools' from anywhere in the project.
export PYTHONPATH="$PROJECT_ROOT"

# Define paths to the scripts and the main progress file
DOWNLOAD_SCRIPT="$PROJECT_ROOT/engines/Download.py"
SCORING_SCRIPT="$PROJECT_ROOT/engines/Scoring.py"
PORTFOLIO_SCRIPT="$PROJECT_ROOT/engines/Portfolio.py"
VENV_PYTHON="$PROJECT_ROOT/.venv/bin/python"
PIPELINE_JSON_FILE="$PROJECT_ROOT/html/pipeline_progress.json"

# --- Cleanup Trap ---
# This function is registered to run automatically when the script exits,
# for any reason (success, error, or interruption via Ctrl+C).
# It ensures we never leave temporary files behind.
cleanup() {
  rm -f tmp.$$.json
}
trap cleanup EXIT INT TERM

# --- Helper Functions ---
log_message() {
    echo "$(date '+%Y-%m-%d %H:%M:%S') - PIPELINE - INFO - $1"
}

update_pipeline_status() {
    local stage_message="$1"
    local status_message="$2"
    # Use jq to safely update the JSON file. The 'mv' is atomic, which prevents
    # the web page from reading a half-written file.
    jq --arg stage "$stage_message" --arg status "$status_message" \
       '.pipeline_run_status.current_stage = $stage | .pipeline_run_status.status_message = $status' \
       "$PIPELINE_JSON_FILE" > tmp.$$.json && mv tmp.$$.json "$PIPELINE_JSON_FILE"
}

# Reusable function to run each pipeline stage.
# This handles logging, status updates, execution, and error checking.
run_stage() {
    local stage_name="$1"
    local script_path="$2"
    local script_filename=$(basename "$script_path")

    log_message "Starting ${stage_name} stage (${script_filename})..."
    update_pipeline_status "${stage_name}" "${script_filename} is running"

    # Use the virtual environment's Python if it exists, otherwise fall back.
    # This makes the script robust, especially when run from cron.
    if [ -f "$VENV_PYTHON" ]; then
         "$VENV_PYTHON" "$script_path"
    else
         log_message "WARNING: Virtual environment python not found at '$VENV_PYTHON'. Using system 'python3'."
         python3 "$script_path"
    fi

    if [ $? -ne 0 ]; then
        log_message "${stage_name} stage (${script_filename}) failed. Aborting pipeline."
        update_pipeline_status "Failed" "${script_filename} encountered an error."
        exit 1
    fi

    log_message "${stage_name} stage completed successfully."
}


# --- Pipeline Execution ---
log_message "Pipeline execution started."

# 1. Initialize the progress JSON file for a fresh run
jq -n --arg startTime "$(date '+%Y-%m-%d %H:%M:%S')" '{
    "pipeline_run_status": {
        "status_message": "Pipeline execution started.",
        "start_time": $startTime,
        "current_stage": "Initializing...",
        "end_time": "N/A"
    }
}' > "$PIPELINE_JSON_FILE"

# --- Main pipeline stages using the new function ---

# 2. Run the Data Download script
run_stage "Data Download" "$DOWNLOAD_SCRIPT"
# --- IMPROVEMENT: Update status between stages for better UI feedback ---
update_pipeline_status "Awaiting Next Stage" "Data Download completed successfully."

# 3. Run the Stock Scoring script
run_stage "Stock Scoring" "$SCORING_SCRIPT"
update_pipeline_status "Awaiting Next Stage" "Stock Scoring completed successfully."

# 4. Run the Portfolio Optimization script
run_stage "Portfolio Optimization" "$PORTFOLIO_SCRIPT"

# 5. Finalize the pipeline status
log_message "Pipeline execution completed successfully."
jq --arg endTime "$(date '+%Y-%m-%d %H:%M:%S')" \
   '.pipeline_run_status.status_message = "Completed" | .pipeline_run_status.current_stage = "Completed" | .pipeline_run_status.end_time = $endTime' \
   "$PIPELINE_JSON_FILE" > tmp.$$.json && mv tmp.$$.json "$PIPELINE_JSON_FILE"

exit 0