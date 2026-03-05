#!/bin/bash
# estimate_cloud_costs.sh - Orchestrator for cloud cost estimation
# 
# Usage:
#   ./scripts/estimate_cloud_costs.sh [OPTIONS]
#
# Options:
#   --profile       Force re-run of resource profiler (executes full pipeline)
#   --no-run        Skip pipeline execution, use existing logs
#   --executions N  Number of monthly executions (default: 22)
#   --page-views N  Number of monthly page views (default: 100)
set -e
SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
PROJECT_ROOT="$( cd "$SCRIPT_DIR/.." && pwd )"
# Default parameters
FORCE_PROFILE=false
NO_RUN=false
EXECUTIONS=22
PAGE_VIEWS=100
# Parse arguments
while [[ $# -gt 0 ]]; do
    case $1 in
        --profile)
            FORCE_PROFILE=true
            shift
            ;;
        --no-run)
            NO_RUN=true
            shift
            ;;
        --executions)
            EXECUTIONS="$2"
            shift 2
            ;;
        --page-views)
            PAGE_VIEWS="$2"
            shift 2
            ;;
        -h|--help)
            echo "Usage: $0 [OPTIONS]"
            echo ""
            echo "Options:"
            echo "  --profile       Force re-run of resource profiler"
            echo "  --no-run        Skip pipeline execution, use logs"
            echo "  --executions N  Monthly executions (default: 22)"
            echo "  --page-views N  Monthly page views (default: 100)"
            exit 0
            ;;
        *)
            echo "Unknown option: $1"
            exit 1
            ;;
    esac
done
# Paths
METRICS_FILE="$PROJECT_ROOT/data/results/resource_metrics.json"
VENV_PYTHON="$PROJECT_ROOT/.venv/bin/python"
# Use venv Python if available, else system Python
if [ -f "$VENV_PYTHON" ]; then
    PYTHON="$VENV_PYTHON"
else
    PYTHON="python3"
fi
echo "═══════════════════════════════════════════════════════════════════════════"
echo "  CLOUD COST ESTIMATION - PortfolioESG"
echo "═══════════════════════════════════════════════════════════════════════════"
echo ""
echo "  Project: $PROJECT_ROOT"
echo "  Python:  $PYTHON"
echo "  Executions/month: $EXECUTIONS"
echo "  Page views/month: $PAGE_VIEWS"
echo ""
# Check if metrics file exists and is less than 24 hours old
NEED_PROFILE=false
if [ "$FORCE_PROFILE" = true ]; then
    NEED_PROFILE=true
    echo "  ⚡ Force profile requested"
elif [ ! -f "$METRICS_FILE" ]; then
    NEED_PROFILE=true
    echo "  📊 No metrics file found, will profile"
else
    # Check file age (24 hours = 86400 seconds)
    if [ "$(uname)" = "Darwin" ]; then
        FILE_AGE=$(( $(date +%s) - $(stat -f %m "$METRICS_FILE") ))
    else
        FILE_AGE=$(( $(date +%s) - $(stat -c %Y "$METRICS_FILE") ))
    fi
    if [ $FILE_AGE -gt 86400 ]; then
        echo "  ⏰ Metrics file is older than 24h, will re-profile"
        NEED_PROFILE=true
    else
        echo "  ✓ Using existing metrics (age: $(( FILE_AGE / 3600 ))h)"
    fi
fi
echo ""
# Run profiler if needed
if [ "$NEED_PROFILE" = true ]; then
    echo "═══════════════════════════════════════════════════════════════════════════"
    echo "  STEP 1: Resource Profiling"
    echo "═══════════════════════════════════════════════════════════════════════════"
    PROFILE_ARGS=""
    if [ "$NO_RUN" = true ]; then
        PROFILE_ARGS="--no-run"
        echo "  (Skipping pipeline execution, using logs)"
    else
        echo "  (Will execute full pipeline - this takes 10-15 minutes)"
    fi
    echo ""
    "$PYTHON" "$PROJECT_ROOT/scripts/profile_resources.py" $PROFILE_ARGS
    echo ""
fi
# Run cost calculator
echo "═══════════════════════════════════════════════════════════════════════════"
echo "  STEP 2: Cost Calculation"
echo "═══════════════════════════════════════════════════════════════════════════"
echo ""
"$PYTHON" "$PROJECT_ROOT/scripts/cloud_pricing.py" \
    --executions "$EXECUTIONS" \
    --page-views "$PAGE_VIEWS"
echo ""
echo "═══════════════════════════════════════════════════════════════════════════"
echo "  COMPLETE"
echo "═══════════════════════════════════════════════════════════════════════════"
echo ""
echo "  Output files:"
echo "    - $PROJECT_ROOT/data/results/resource_metrics.json"
echo "    - $PROJECT_ROOT/data/results/cloud_cost_comparison.json"
echo ""
