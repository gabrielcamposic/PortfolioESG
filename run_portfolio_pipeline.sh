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

# Activate virtual environment (adjust path if necessary)
# Assuming .venv is in your project root: /home/gabrielcampos/PortfolioESG_Prod/.venv
VENV_PATH="$PROJECT_DIR/.venv/bin/activate"
PYTHON_EXEC="$PROJECT_DIR/.venv/bin/python"

if [ -f "$VENV_PATH" ]; then
    log_message "Activating virtual environment: $VENV_PATH"
    source "$VENV_PATH"
    if [ ! -x "$PYTHON_EXEC" ]; then
        log_message "Error: Python executable $PYTHON_EXEC not found or not executable after activating venv. Trying 'python3'."
        PYTHON_EXEC="python3" # Fallback
    fi
else
    log_message "Warning: Virtual environment not found at $VENV_PATH. Assuming Python scripts are globally accessible or 'python3' is in PATH."
    PYTHON_EXEC="python3" # Fallback if no venv
fi

log_message "Using Python interpreter: $($PYTHON_EXEC --version 2>&1)"

# Define paths to your Python scripts (relative to PROJECT_DIR)
DOWNLOAD_SCRIPT="./Download.py" # Note: Case-sensitive on Linux
ENGINE_SCRIPT="./Engine.py"     # Note: Case-sensitive on Linux

# --- Step 1: Run download.py ---
log_message "Starting Download.py..."
"$PYTHON_EXEC" "$DOWNLOAD_SCRIPT" >> "$PIPELINE_LOG_FILE" 2>&1
DOWNLOAD_EXIT_CODE=$?

if [ $DOWNLOAD_EXIT_CODE -eq 0 ]; then
    log_message "Download.py completed successfully."

    # --- Step 2: Run Engine.py ---
    log_message "Starting Engine.py..."
    "$PYTHON_EXEC" "$ENGINE_SCRIPT" >> "$PIPELINE_LOG_FILE" 2>&1
    ENGINE_EXIT_CODE=$?

    if [ $ENGINE_EXIT_CODE -eq 0 ]; then
        log_message "Engine.py completed successfully."
    else
        log_message "Error: Engine.py failed with exit code $ENGINE_EXIT_CODE."
    fi
else
    log_message "Error: Download.py failed with exit code $DOWNLOAD_EXIT_CODE. Engine.py will not run."
fi

# Deactivate virtual environment if it was sourced
if type deactivate > /dev/null 2>&1; then
    log_message "Deactivating virtual environment."
    deactivate
fi

log_message "Portfolio Pipeline Finished"
log_message "======================================"
echo "" >> "$PIPELINE_LOG_FILE"

exit 0