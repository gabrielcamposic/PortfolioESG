#!/bin/bash
# ═══════════════════════════════════════════════════════════════════════════════
# C_OptimizedPortfolio.sh - Portfolio Optimization Pipeline
# ═══════════════════════════════════════════════════════════════════════════════
#
# Combines ideal portfolio (from A_Portfolio) with current holdings (from B_Ledger)
# to generate a cost-aware transition recommendation.
#
# Prerequisites:
#   - A_Portfolio.sh should have been run (generates ideal portfolio)
#   - B_Ledger.sh should have been run (processes trade notes and generates holdings)
#
# Usage:
#   ./engines/C_OptimizedPortfolio.sh
#
# ═══════════════════════════════════════════════════════════════════════════════

set -euo pipefail

# --- Configuration ---
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"

export PYTHONPATH="$PROJECT_ROOT"
export PYTHONUNBUFFERED=1

# Logging
TIMESTAMP=$(date +"%Y%m%d-%H%M%S")
LOG_FILE="$PROJECT_ROOT/logs/optimized_$TIMESTAMP.log"
mkdir -p "$PROJECT_ROOT/logs"

# Activate virtual environment if it exists
VENV_PYTHON="$PROJECT_ROOT/.venv/bin/python"
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

# --- Main ---
log "╔══════════════════════════════════════════════════════════════╗"
log "║     C_OptimizedPortfolio.sh - Portfolio Optimization         ║"
log "╠══════════════════════════════════════════════════════════════╣"
log "║  Timestamp: $TIMESTAMP"
log "║  Log file:  $LOG_FILE"
log "╚══════════════════════════════════════════════════════════════╝"
log ""
log "Combining:"
log "  - Ideal portfolio from A_Portfolio.sh"
log "  - Current holdings from B_Ledger.sh"

# Check if required files exist
if [ ! -f "$PROJECT_ROOT/html/data/latest_run_summary.json" ]; then
    log "ERROR: Ideal portfolio not found."
    log "Please run A_Portfolio.sh first."
    exit 1
fi

if [ ! -f "$PROJECT_ROOT/html/data/ledger_positions.json" ]; then
    log "WARNING: Holdings file not found."
    log "Please run B_Ledger.sh first to process your trade notes."
fi

# Run the optimization script
log ""
log "▶ Running C_OptimizedPortfolio.py..."
PIPELINE_START=$(date +%s)

if "$PY_EXEC" "$SCRIPT_DIR/C_OptimizedPortfolio.py" 2>&1 | tee -a "$LOG_FILE"; then
    PIPELINE_END=$(date +%s)
    PIPELINE_DURATION=$((PIPELINE_END - PIPELINE_START))

    log ""
    log "╔══════════════════════════════════════════════════════════════╗"
    log "║              OPTIMIZATION COMPLETED SUCCESSFULLY             ║"
    log "╠══════════════════════════════════════════════════════════════╣"
    log "║  Duration: ${PIPELINE_DURATION}s"
    log "╚══════════════════════════════════════════════════════════════╝"
    log ""
    log "Output files:"
    log "  - $PROJECT_ROOT/html/data/optimized_recommendation.json"
    log "  - $PROJECT_ROOT/data/results/optimized_portfolio_history.csv"
    EXIT_CODE=0
else
    EXIT_CODE=$?
    log ""
    log "╔══════════════════════════════════════════════════════════════╗"
    log "║              OPTIMIZATION FAILED                             ║"
    log "╠══════════════════════════════════════════════════════════════╣"
    log "║  Exit code: $EXIT_CODE"
    log "╚══════════════════════════════════════════════════════════════╝"
fi

exit $EXIT_CODE

