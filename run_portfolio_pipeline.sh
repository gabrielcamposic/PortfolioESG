#!/bin/bash
# --- Configuration ---
PROJECT_DIR="/home/gabrielcampos/PortfolioESG_Prod"
LOG_DIR="$PROJECT_DIR/Logs"
PIPELINE_LOG_FILE="$LOG_DIR/pipeline_execution.log"

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

# --- Main Execution ---
log_message "--------------------------------------"
log_message "Portfolio Pipeline Started"
log_message "--------------------------------------"

# Define the Python interpreter from the pyenv environment
# This matches the shebang in your Python scripts.
PYTHON_EXEC="/home/gabrielcampos/.pyenv/versions/env-fa/bin/python"

if [ ! -x "$PYTHON_EXEC" ]; then
    log_message "Error: Python executable $PYTHON_EXEC not found or not executable. Please check the path."
    # Fallback to system python3 if pyenv one is not found (less ideal, but for safety)
    PYTHON_EXEC="python3"
fi

log_message "Using Python interpreter: $($PYTHON_EXEC --version 2>&1)"

# Define paths to your Python scripts (relative to PROJECT_DIR)
DOWNLOAD_SCRIPT="./Download.py" # Note: Case-sensitive on Linux
ENGINE_SCRIPT="./Engine.py"     # Note: Case-sensitive on Linux

# --- Step 1: Run download.py ---
log_message "Starting Download.py..."
# The output of Download.py (stdout and stderr) will be appended to $PIPELINE_LOG_FILE
# which, in your cron setup, is pipeline_cron.log.
# This ensures Python tracebacks are captured here.
"$PYTHON_EXEC" "$DOWNLOAD_SCRIPT"
DOWNLOAD_EXIT_CODE=$?

if [ $DOWNLOAD_EXIT_CODE -eq 0 ]; then
    log_message "Download.py completed successfully."

    # --- Step 2: Run Engine.py ---
    log_message "Starting Engine.py..."
    "$PYTHON_EXEC" "$ENGINE_SCRIPT"
    ENGINE_EXIT_CODE=$?

    if [ $ENGINE_EXIT_CODE -eq 0 ]; then
        log_message "Engine.py completed successfully."
    else
        log_message "Error: Engine.py failed with exit code $ENGINE_EXIT_CODE."
    fi
else
    log_message "Error: Download.py failed with exit code $DOWNLOAD_EXIT_CODE. Engine.py will not run."
fi

log_message "Portfolio Pipeline Finished"
log_message "======================================"
echo "" >> "$PIPELINE_LOG_FILE"

exit 0