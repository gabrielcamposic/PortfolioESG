#!/bin/bash
#
# GCP VM Runner Script
#
# This script is designed to run on a GCP Spot VM with the following features:
# - Graceful handling of preemption (SIGTERM)
# - Automatic checkpoint save on interruption
# - Sync with GCS before and after execution
# - Auto-shutdown after completion (to save costs)
#
# Usage:
#   ./scripts/gcp_vm_runner.sh [--no-shutdown] [--skip-sync]
#
# Environment variables:
#   GCS_DATA_BUCKET     - GCS bucket for data (default: gs://portfolioesg-data)
#   GCS_WEBSITE_BUCKET  - GCS bucket for website (default: gs://portfolioesg-website)
#   SHUTDOWN_AFTER      - Shutdown after completion (default: true)
#

set -o pipefail

# --- Configuration ---
SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" &> /dev/null && pwd )"
PROJECT_ROOT=$(realpath "$SCRIPT_DIR/..")

# Ensure PYTHONPATH includes project root
export PYTHONPATH="$PROJECT_ROOT"

# GCS buckets (can be overridden by environment)
GCS_DATA_BUCKET="${GCS_DATA_BUCKET:-gs://portfolioesg-data}"
GCS_WEBSITE_BUCKET="${GCS_WEBSITE_BUCKET:-gs://portfolioesg-website}"

# Python executable
VENV_PYTHON="$PROJECT_ROOT/.venv/bin/python"
if [ ! -f "$VENV_PYTHON" ]; then
    VENV_PYTHON="python3"
fi

# Logging
LOG_DIR="$PROJECT_ROOT/logs"
LOG_FILE="$LOG_DIR/gcp_vm_runner.log"
mkdir -p "$LOG_DIR"

# Checkpoint file
CHECKPOINT_FILE="$PROJECT_ROOT/data/run_checkpoint.json"

# Flags
SHUTDOWN_AFTER="${SHUTDOWN_AFTER:-true}"
SKIP_SYNC=false

# --- Parse Arguments ---
while [[ $# -gt 0 ]]; do
    case $1 in
        --no-shutdown)
            SHUTDOWN_AFTER=false
            shift
            ;;
        --skip-sync)
            SKIP_SYNC=true
            shift
            ;;
        *)
            echo "Unknown option: $1"
            exit 1
            ;;
    esac
done

# --- Helper Functions ---
log() {
    local msg="[$(date '+%Y-%m-%d %H:%M:%S')] $1"
    echo "$msg"
    echo "$msg" >> "$LOG_FILE"
}

log_error() {
    log "[ERROR] $1"
}

log_warning() {
    log "[WARNING] $1"
}

# --- Signal Handling ---
cleanup() {
    local exit_code=$?
    log "Cleanup triggered with exit code: $exit_code"

    # Save checkpoint if we were interrupted
    if [ -f "$CHECKPOINT_FILE" ]; then
        local status=$(jq -r '.status // "unknown"' "$CHECKPOINT_FILE" 2>/dev/null)
        if [ "$status" = "running" ]; then
            log_warning "Pipeline was running when interrupted. Updating checkpoint."
            jq '.status = "interrupted" | .interrupted_at = now' "$CHECKPOINT_FILE" > tmp.$$.json && mv tmp.$$.json "$CHECKPOINT_FILE"
        fi
    fi

    # Sync logs to GCS even on failure
    if [ "$SKIP_SYNC" = false ]; then
        log "Syncing logs to GCS..."
        gsutil -m cp "$LOG_FILE" "$GCS_DATA_BUCKET/logs/" 2>/dev/null || true

        # Also sync checkpoint
        if [ -f "$CHECKPOINT_FILE" ]; then
            gsutil cp "$CHECKPOINT_FILE" "$GCS_DATA_BUCKET/data/" 2>/dev/null || true
        fi
    fi

    log "Cleanup completed"
}

# Trap signals
trap cleanup EXIT
trap 'log_warning "Received SIGTERM (preemption warning)"; exit 130' SIGTERM
trap 'log_warning "Received SIGINT"; exit 130' SIGINT

# --- Pre-flight Checks ---
preflight_check() {
    log "Running pre-flight checks..."

    # Check if gsutil is available
    if ! command -v gsutil &> /dev/null; then
        log_warning "gsutil not found. GCS sync will be skipped."
        SKIP_SYNC=true
    fi

    # Check if Python is available
    if ! command -v "$VENV_PYTHON" &> /dev/null; then
        log_error "Python not found at $VENV_PYTHON"
        exit 1
    fi

    # Check if required directories exist
    mkdir -p "$PROJECT_ROOT/data/findb"
    mkdir -p "$PROJECT_ROOT/data/results"
    mkdir -p "$PROJECT_ROOT/html/data"

    log "Pre-flight checks passed"
}

# --- GCS Sync Functions ---
sync_from_gcs() {
    if [ "$SKIP_SYNC" = true ]; then
        log "Skipping GCS download (--skip-sync)"
        return 0
    fi

    log "Downloading data from GCS..."

    # Download findb (consolidated data)
    gsutil -m rsync -r "$GCS_DATA_BUCKET/data/findb" "$PROJECT_ROOT/data/findb" 2>&1 | tee -a "$LOG_FILE"

    # Download results
    gsutil -m rsync -r "$GCS_DATA_BUCKET/data/results" "$PROJECT_ROOT/data/results" 2>&1 | tee -a "$LOG_FILE"

    # Download parameters
    gsutil -m rsync -r "$GCS_DATA_BUCKET/parameters" "$PROJECT_ROOT/parameters" 2>&1 | tee -a "$LOG_FILE"

    # Download checkpoint if exists
    gsutil cp "$GCS_DATA_BUCKET/data/run_checkpoint.json" "$CHECKPOINT_FILE" 2>/dev/null || true

    log "GCS download completed"
}

sync_to_gcs() {
    if [ "$SKIP_SYNC" = true ]; then
        log "Skipping GCS upload (--skip-sync)"
        return 0
    fi

    log "Uploading data to GCS..."

    # Upload findb
    gsutil -m rsync -r "$PROJECT_ROOT/data/findb" "$GCS_DATA_BUCKET/data/findb" 2>&1 | tee -a "$LOG_FILE"

    # Upload results
    gsutil -m rsync -r "$PROJECT_ROOT/data/results" "$GCS_DATA_BUCKET/data/results" 2>&1 | tee -a "$LOG_FILE"

    # Upload website data
    gsutil -m rsync -r "$PROJECT_ROOT/html/data" "$GCS_WEBSITE_BUCKET/data" 2>&1 | tee -a "$LOG_FILE"

    # Upload logs
    gsutil -m cp "$LOG_DIR"/*.log "$GCS_DATA_BUCKET/logs/" 2>&1 | tee -a "$LOG_FILE"

    # Clear checkpoint on successful completion
    gsutil rm "$GCS_DATA_BUCKET/data/run_checkpoint.json" 2>/dev/null || true

    log "GCS upload completed"
}

# --- Main Pipeline ---
run_pipeline() {
    log "Starting PortfolioESG pipeline..."

    # Run the Python GCP runner with checkpoint support
    "$VENV_PYTHON" "$PROJECT_ROOT/scripts/gcp_runner.py" --skip-sync
    local exit_code=$?

    if [ $exit_code -eq 0 ]; then
        log "Pipeline completed successfully"
        return 0
    else
        log_error "Pipeline failed with exit code: $exit_code"
        return $exit_code
    fi
}

# --- Main Execution ---
main() {
    log "============================================================"
    log "PortfolioESG GCP VM Runner"
    log "============================================================"
    log "Project root: $PROJECT_ROOT"
    log "GCS data bucket: $GCS_DATA_BUCKET"
    log "GCS website bucket: $GCS_WEBSITE_BUCKET"
    log "Shutdown after: $SHUTDOWN_AFTER"
    log "Skip sync: $SKIP_SYNC"
    log "============================================================"

    # Pre-flight checks
    preflight_check

    # Sync from GCS
    sync_from_gcs

    # Run pipeline
    local pipeline_success=true
    if ! run_pipeline; then
        pipeline_success=false
    fi

    # Sync to GCS
    if [ "$pipeline_success" = true ]; then
        sync_to_gcs
    else
        # Still upload logs and checkpoint on failure
        log "Pipeline failed but syncing logs and checkpoint..."
        if [ "$SKIP_SYNC" = false ]; then
            gsutil -m cp "$LOG_DIR"/*.log "$GCS_DATA_BUCKET/logs/" 2>/dev/null || true
            if [ -f "$CHECKPOINT_FILE" ]; then
                gsutil cp "$CHECKPOINT_FILE" "$GCS_DATA_BUCKET/data/" 2>/dev/null || true
            fi
        fi
    fi

    # Shutdown if configured
    if [ "$SHUTDOWN_AFTER" = true ]; then
        log "Shutting down VM in 30 seconds..."
        sleep 30
        sudo shutdown -h now
    fi

    if [ "$pipeline_success" = true ]; then
        exit 0
    else
        exit 1
    fi
}

# Run main
main

