#!/bin/bash
# ═══════════════════════════════════════════════════════════════════════════════
# B_Ledger.sh - Trade Processing Pipeline
# ═══════════════════════════════════════════════════════════════════════════════
#
# Pipeline to process broker note PDFs and refresh ledger/frontend JSON.
# Run this only when you have new broker notes to ingest.
#
# Stages:
#   B1: Process broker notes (PDF parsing)
#   B2: Consolidate ledger positions
#   B3: Generate frontend JSON assets
#   B4: Generate portfolio history for charts
#
# Usage:
#   ./B_Ledger.sh
#
# ═══════════════════════════════════════════════════════════════════════════════

set -euo pipefail

# --- Configuration ---
SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" &> /dev/null && pwd )"
PROJECT_ROOT=$(realpath "$SCRIPT_DIR/..")
export PYTHONPATH="$PROJECT_ROOT"

# Force Python to run in unbuffered mode to avoid output pauses in terminal
export PYTHONUNBUFFERED=1

# Scripts
VENV_PYTHON="$PROJECT_ROOT/.venv/bin/python"
PROCESS_NOTES_SCRIPT="$PROJECT_ROOT/engines/B1_Process_Notes.py"
CONSOLIDATE_LEDGER_SCRIPT="$PROJECT_ROOT/engines/B2_Consolidate_Ledger.py"
GENERATE_ASSETS_SCRIPT="$PROJECT_ROOT/engines/B3_Generate_json.py"
PORTFOLIO_HISTORY_SCRIPT="$PROJECT_ROOT/engines/B4_Portfolio_History.py"

# Logging
TIMESTAMP=$(date +"%Y%m%d-%H%M%S")
LOG_FILE="$PROJECT_ROOT/logs/ledger_$TIMESTAMP.log"
mkdir -p "$PROJECT_ROOT/logs"

# Choose Python interpreter
if [ -f "$VENV_PYTHON" ]; then
    PY_EXEC="$VENV_PYTHON"
else
    PY_EXEC="python3"
fi

# --- Helper Functions ---
log() {
    local msg="[$(date '+%Y-%m-%d %H:%M:%S')] $1"
    echo "$msg"
    echo "$msg" >> "$LOG_FILE"
}

run_stage() {
    local name="$1"
    local script="$2"
    log "▶ Starting: $name"
    local start_time=$(date +%s)

    if (cd "$PROJECT_ROOT" && "$PY_EXEC" "$script" 2>&1 | tee -a "$LOG_FILE"); then
        local end_time=$(date +%s)
        local duration=$((end_time - start_time))
        log "✓ $name completed in ${duration}s"
        return 0
    else
        log "✗ $name failed"
        return 1
    fi
}

# --- Main ---
log "╔══════════════════════════════════════════════════════════════╗"
log "║           B_Ledger.sh - Trade Processing Pipeline           ║"
log "╠══════════════════════════════════════════════════════════════╣"
log "║  Timestamp: $TIMESTAMP"
log "║  Log file:  $LOG_FILE"
log "╚══════════════════════════════════════════════════════════════╝"

PIPELINE_START=$(date +%s)

# 1) Process broker notes (idempotent)
if ! run_stage "B1_Process_Notes" "$PROCESS_NOTES_SCRIPT"; then
    log "ProcessNotes failed. Aborting." >&2
    exit 1
fi

# 2) Consolidate ledger into positions JSON
if ! run_stage "B2_Consolidate_Ledger" "$CONSOLIDATE_LEDGER_SCRIPT"; then
    log "Consolidate ledger failed. Aborting." >&2
    exit 1
fi

# 3) Regenerate frontend JSON assets (copies to html/data)
if ! run_stage "B3_Generate_json" "$GENERATE_ASSETS_SCRIPT"; then
    log "Generate assets JSON failed. Aborting." >&2
    exit 1
fi

# 4) Generate portfolio history for charts
if ! run_stage "B4_Portfolio_History" "$PORTFOLIO_HISTORY_SCRIPT"; then
    log "Generate portfolio history failed. Aborting." >&2
    exit 1
fi

PIPELINE_END=$(date +%s)
PIPELINE_DURATION=$((PIPELINE_END - PIPELINE_START))

log "╔══════════════════════════════════════════════════════════════╗"
log "║              PIPELINE COMPLETED SUCCESSFULLY                 ║"
log "╠══════════════════════════════════════════════════════════════╣"
log "║  Total Duration: ${PIPELINE_DURATION}s"
log "╚══════════════════════════════════════════════════════════════╝"
log ""
log "Results available at:"
log "  - Positions:  $PROJECT_ROOT/html/data/ledger_positions.json"
log "  - History:    $PROJECT_ROOT/html/data/portfolio_history.json"
log "  - Pipeline:   $PROJECT_ROOT/html/data/pipeline_latest.json"
