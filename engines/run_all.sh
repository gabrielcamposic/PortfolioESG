#!/bin/bash
#
# PortfolioESG - Master Orchestrator
#
# This script orchestrates all pipeline stages in the correct order:
#   1. A_Portfolio.sh - Download data, score stocks, generate recommended portfolio
#   2. B_Ledger.sh    - Process trading notes, update holdings
#   3. C_OptimizedPortfolio.sh - Compare holdings vs recommended, decide rebalancing
#
# Usage:
#   ./engines/run_all.sh [OPTIONS]
#
# Options:
#   --skip-download   Skip A1_Download (use cached data)
#   --skip-ledger     Skip B_Ledger (no new trading notes)
#   --only-A          Run only A_Portfolio pipeline
#   --only-B          Run only B_Ledger pipeline
#   --only-C          Run only C_OptimizedPortfolio
#   --dry-run         Show what would be executed without running
#   --verbose         Show detailed output
#
# Environment:
#   SKIP_DOWNLOAD=1   Same as --skip-download
#   SKIP_LEDGER=1     Same as --skip-ledger
#

set -o pipefail

# --- Configuration ---
SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" &> /dev/null && pwd )"
PROJECT_ROOT=$(realpath "$SCRIPT_DIR/..")
LOG_DIR="$PROJECT_ROOT/logs"
TIMESTAMP=$(date '+%Y%m%d-%H%M%S')
MASTER_LOG="$LOG_DIR/run_all_$TIMESTAMP.log"

# Ensure log directory exists
mkdir -p "$LOG_DIR"

# --- Default Options ---
RUN_A=true
RUN_B=true
RUN_C=true
SKIP_DOWNLOAD=${SKIP_DOWNLOAD:-false}
DRY_RUN=false
VERBOSE=false

# --- Parse Arguments ---
while [[ $# -gt 0 ]]; do
    case $1 in
        --skip-download)
            SKIP_DOWNLOAD=true
            shift
            ;;
        --skip-ledger)
            RUN_B=false
            shift
            ;;
        --only-A)
            RUN_A=true
            RUN_B=false
            RUN_C=false
            shift
            ;;
        --only-B)
            RUN_A=false
            RUN_B=true
            RUN_C=false
            shift
            ;;
        --only-C)
            RUN_A=false
            RUN_B=false
            RUN_C=true
            shift
            ;;
        --dry-run)
            DRY_RUN=true
            shift
            ;;
        --verbose|-v)
            VERBOSE=true
            shift
            ;;
        --help|-h)
            head -30 "$0" | tail -25
            exit 0
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
    echo "$msg" >> "$MASTER_LOG"
}

log_error() {
    log "[ERROR] $1"
}

log_success() {
    log "[SUCCESS] $1"
}

run_stage() {
    local stage_name="$1"
    local script_path="$2"
    local extra_args="${3:-}"

    log "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    log "Starting: $stage_name"
    log "Script:   $script_path"
    log "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"

    if [ "$DRY_RUN" = true ]; then
        log "[DRY RUN] Would execute: $script_path $extra_args"
        return 0
    fi

    local start_time=$(date +%s)

    # Execute the script
    if [ "$VERBOSE" = true ]; then
        "$script_path" $extra_args 2>&1 | tee -a "$MASTER_LOG"
        local exit_code=${PIPESTATUS[0]}
    else
        "$script_path" $extra_args >> "$MASTER_LOG" 2>&1
        local exit_code=$?
    fi

    local end_time=$(date +%s)
    local duration=$((end_time - start_time))
    local minutes=$((duration / 60))
    local seconds=$((duration % 60))

    if [ $exit_code -eq 0 ]; then
        log_success "$stage_name completed in ${minutes}m ${seconds}s"
        return 0
    else
        log_error "$stage_name failed with exit code $exit_code after ${minutes}m ${seconds}s"
        return $exit_code
    fi
}

# --- Pre-flight Checks ---
preflight_check() {
    log "Running pre-flight checks..."

    local errors=0

    # Check Python venv
    if [ ! -f "$PROJECT_ROOT/.venv/bin/python" ]; then
        log_error "Python virtual environment not found at $PROJECT_ROOT/.venv"
        ((errors++))
    fi

    # Check required scripts
    for script in A_Portfolio.sh B_Ledger.sh C_OptimizedPortfolio.sh; do
        if [ ! -x "$SCRIPT_DIR/$script" ]; then
            log_error "Script not found or not executable: $SCRIPT_DIR/$script"
            ((errors++))
        fi
    done

    # Check required directories
    for dir in data/findb parameters html/data; do
        if [ ! -d "$PROJECT_ROOT/$dir" ]; then
            log "[WARN] Directory missing, will be created: $PROJECT_ROOT/$dir"
            mkdir -p "$PROJECT_ROOT/$dir"
        fi
    done

    if [ $errors -gt 0 ]; then
        log_error "Pre-flight check failed with $errors error(s)"
        return 1
    fi

    log "Pre-flight checks passed"
    return 0
}

# --- Main Execution ---
main() {
    local overall_start=$(date +%s)

    log "╔══════════════════════════════════════════════════════════════╗"
    log "║           PortfolioESG - Master Pipeline Runner              ║"
    log "╠══════════════════════════════════════════════════════════════╣"
    log "║  Timestamp: $TIMESTAMP                              ║"
    log "║  Log file:  $MASTER_LOG"
    log "╚══════════════════════════════════════════════════════════════╝"
    log ""
    log "Configuration:"
    log "  Run A (Portfolio):     $RUN_A"
    log "  Run B (Ledger):        $RUN_B"
    log "  Run C (Optimization):  $RUN_C"
    log "  Skip Download:         $SKIP_DOWNLOAD"
    log "  Dry Run:               $DRY_RUN"
    log ""

    # Pre-flight
    if ! preflight_check; then
        return 1
    fi

    local failed_stages=()

    # --- Stage A: Portfolio Pipeline ---
    if [ "$RUN_A" = true ]; then
        log ""
        log "▶ STAGE A: Portfolio Pipeline (Download → Score → Optimize → Analyze)"

        if [ "$SKIP_DOWNLOAD" = true ]; then
            # Run individual scripts, skipping download
            log "Skipping A1_Download (--skip-download)"

            # Run A2, A3, A4 directly
            for script in A2_Scoring.py A3_Portfolio.py A4_Analysis.py; do
                script_name="${script%.py}"
                if ! run_stage "$script_name" "$PROJECT_ROOT/.venv/bin/python" "$SCRIPT_DIR/$script"; then
                    failed_stages+=("$script_name")
                    log_error "Aborting due to failure in $script_name"
                    break
                fi
            done
        else
            # Run full A_Portfolio.sh
            if ! run_stage "A_Portfolio" "$SCRIPT_DIR/A_Portfolio.sh"; then
                failed_stages+=("A_Portfolio")
            fi
        fi
    fi

    # --- Stage B: Ledger Pipeline ---
    if [ "$RUN_B" = true ]; then
        log ""
        log "▶ STAGE B: Ledger Pipeline (Process Notes → Consolidate → Generate JSON)"

        if ! run_stage "B_Ledger" "$SCRIPT_DIR/B_Ledger.sh"; then
            failed_stages+=("B_Ledger")
            # B failure is not critical, continue to C
            log "[WARN] Ledger processing failed but continuing..."
        fi
    fi

    # --- Stage C: Optimized Portfolio ---
    if [ "$RUN_C" = true ]; then
        log ""
        log "▶ STAGE C: Optimized Portfolio (Compare Holdings vs Recommended)"

        if ! run_stage "C_OptimizedPortfolio" "$SCRIPT_DIR/C_OptimizedPortfolio.sh"; then
            failed_stages+=("C_OptimizedPortfolio")
        fi
    fi

    # --- Summary ---
    local overall_end=$(date +%s)
    local total_duration=$((overall_end - overall_start))
    local total_minutes=$((total_duration / 60))
    local total_seconds=$((total_duration % 60))

    log ""
    log "╔══════════════════════════════════════════════════════════════╗"
    log "║                    EXECUTION SUMMARY                         ║"
    log "╠══════════════════════════════════════════════════════════════╣"
    log "║  Total Duration: ${total_minutes}m ${total_seconds}s"

    if [ ${#failed_stages[@]} -eq 0 ]; then
        log "║  Status: ✓ ALL STAGES COMPLETED SUCCESSFULLY"
        log "╚══════════════════════════════════════════════════════════════╝"
        log ""
        log "Results available at:"
        log "  - Portfolio:    $PROJECT_ROOT/html/data/pipeline_latest.json"
        log "  - History:      $PROJECT_ROOT/html/data/portfolio_history.json"
        log "  - Ledger:       $PROJECT_ROOT/html/data/ledger_positions.json"
        log "  - Recommendation: $PROJECT_ROOT/html/data/optimized_recommendation.json"
        log ""
        log "View dashboard: http://localhost:8000/latest_run_summary.html"
        return 0
    else
        log "║  Status: ✗ SOME STAGES FAILED"
        log "║  Failed: ${failed_stages[*]}"
        log "╚══════════════════════════════════════════════════════════════╝"
        log ""
        log "Check log for details: $MASTER_LOG"
        return 1
    fi
}

# Change to project root
cd "$PROJECT_ROOT"

# Run main
main
exit $?

