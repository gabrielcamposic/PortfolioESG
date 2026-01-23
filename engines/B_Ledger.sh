#!/bin/bash
# Small manual pipeline to process broker note PDFs and refresh ledger/frontend JSON
# Run this only when you have new broker notes to ingest.

set -euo pipefail

SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" &> /dev/null && pwd )"
PROJECT_ROOT=$(realpath "$SCRIPT_DIR/..")
export PYTHONPATH="$PROJECT_ROOT"

VENV_PYTHON="$PROJECT_ROOT/.venv/bin/python"
PROCESS_NOTES_SCRIPT="$PROJECT_ROOT/engines/B1_Process_Notes.py"
CONSOLIDATE_LEDGER_SCRIPT="$PROJECT_ROOT/engines/B2_Consolidate_Ledger.py"
GENERATE_ASSETS_SCRIPT="$PROJECT_ROOT/engines/B3_Generate_json.py"
PORTFOLIO_HISTORY_SCRIPT="$PROJECT_ROOT/engines/B4_Portfolio_History.py"

# choose python
if [ -f "$VENV_PYTHON" ]; then
    PY_EXEC="$VENV_PYTHON"
else
    PY_EXEC="python3"
fi

echo "Starting trade processing pipeline: ProcessNotes -> ConsolidateLedger -> GenerateAssets"

# 1) Process broker notes (idempotent)
if ! (cd "$PROJECT_ROOT" && "$PY_EXEC" "$PROCESS_NOTES_SCRIPT"); then
    echo "ProcessNotes failed. Aborting." >&2
    exit 1
fi

# 2) Consolidate ledger into positions JSON
if ! (cd "$PROJECT_ROOT" && "$PY_EXEC" "$CONSOLIDATE_LEDGER_SCRIPT"); then
    echo "Consolidate ledger failed. Aborting." >&2
    exit 1
fi

# 3) Regenerate frontend JSON assets (copies to html/data)
if ! (cd "$PROJECT_ROOT" && "$PY_EXEC" "$GENERATE_ASSETS_SCRIPT"); then
    echo "Generate assets JSON failed. Aborting." >&2
    exit 1
fi

# 4) Generate portfolio history for charts
if ! (cd "$PROJECT_ROOT" && "$PY_EXEC" "$PORTFOLIO_HISTORY_SCRIPT"); then
    echo "Generate portfolio history failed. Aborting." >&2
    exit 1
fi

echo "Trade pipeline completed successfully."

