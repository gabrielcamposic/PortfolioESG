#!/bin/zsh
#
# C_OptimizedPortfolio.sh
#
# Wrapper script to run the optimized portfolio recommendation.
# Combines ideal portfolio (from A_Portfolio) with current holdings (from B_Ledger)
# to generate a cost-aware transition recommendation.
#
# Usage:
#   ./engines/C_OptimizedPortfolio.sh
#
# Prerequisites:
#   - A_Portfolio.sh should have been run (generates ideal portfolio)
#   - B_Ledger.sh should have been run (processes trade notes and generates holdings)
#

# Get the directory where this script is located
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"

# Activate virtual environment if it exists
if [ -d "$PROJECT_ROOT/.venv" ]; then
    source "$PROJECT_ROOT/.venv/bin/activate"
fi

echo "=============================================="
echo "  Optimized Portfolio Recommendation"
echo "=============================================="
echo ""
echo "This script combines:"
echo "  - Ideal portfolio from A_Portfolio.sh"
echo "  - Current holdings from B_Ledger.sh"
echo ""
echo "To generate a cost-aware transition recommendation."
echo ""
echo "----------------------------------------------"

# Check if required files exist
if [ ! -f "$PROJECT_ROOT/html/data/latest_run_summary.json" ]; then
    echo "ERROR: Ideal portfolio not found."
    echo "Please run A_Portfolio.sh first."
    exit 1
fi

if [ ! -f "$PROJECT_ROOT/html/data/ledger_positions.json" ]; then
    echo "WARNING: Holdings file not found."
    echo "Please run B_Ledger.sh first to process your trade notes."
    echo ""
fi

# Run the optimization script
echo "Running C_OptimizedPortfolio.py..."
echo ""

python3 "$SCRIPT_DIR/C_OptimizedPortfolio.py"
EXIT_CODE=$?

if [ $EXIT_CODE -eq 0 ]; then
    echo ""
    echo "----------------------------------------------"
    echo "✓ Optimization complete!"
    echo ""
    echo "Output files:"
    echo "  - html/data/optimized_recommendation.json (latest)"
    echo "  - data/results/optimized_portfolio_history.csv (history)"
    echo "  - logs/optimized.log (detailed log)"
    echo ""
else
    echo ""
    echo "----------------------------------------------"
    echo "✗ Optimization failed with exit code $EXIT_CODE"
    echo "Check logs/optimized.log for details."
fi

exit $EXIT_CODE

