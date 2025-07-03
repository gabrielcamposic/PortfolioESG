# test_run_portfolio_pipeline.sh

#!/bin/bash

# Test runner for run_portfolio_pipeline.sh

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PIPELINE_SCRIPT="$SCRIPT_DIR/run_portfolio_pipeline.sh"
PROGRESS_JSON="$SCRIPT_DIR/html/progress.json"
LOG_DIR="$SCRIPT_DIR/Logs"
LOG_FILE="$LOG_DIR/pipeline_execution.log"

# Helper: create mock Python scripts
create_mock_scripts() {
    # $1: Download exit code, $2: Scoring exit code, $3: Engine exit code
    echo -e "#!/usr/bin/env python3\nimport sys; print('Download.py mock'); sys.exit($1)" > "$SCRIPT_DIR/Download.py"
    echo -e "#!/usr/bin/env python3\nimport sys; print('Scoring.py mock'); sys.exit($2)" > "$SCRIPT_DIR/Scoring.py"
    echo -e "#!/usr/bin/env python3\nimport sys; print('Engine.py mock'); sys.exit($3)" > "$SCRIPT_DIR/Engine.py"
    chmod +x "$SCRIPT_DIR/Download.py" "$SCRIPT_DIR/Scoring.py" "$SCRIPT_DIR/Engine.py"
}

# Helper: clean environment
clean_env() {
    rm -rf "$LOG_DIR"
    mkdir -p "$LOG_DIR"
    mkdir -p "$SCRIPT_DIR/html"
    rm -f "$PROGRESS_JSON"
}

# Helper: check progress.json for a key/value
check_progress_json() {
    local key="$1"
    local expected="$2"
    grep -q "\"$key\"" "$PROGRESS_JSON" && grep -q "$expected" "$PROGRESS_JSON"
}

# Test 1: All steps succeed
test_happy_path() {
    clean_env
    create_mock_scripts 0 0 0
    bash "$PIPELINE_SCRIPT"
    local exit_code=$?
    if [ $exit_code -ne 0 ]; then
        echo "FAIL: Happy path - pipeline did not exit 0"
        return 1
    fi
    grep -q "Portfolio Pipeline Finished successfully" "$LOG_FILE" || { echo "FAIL: Happy path - log missing success"; return 1; }
    check_progress_json "pipeline_run_status" "Pipeline completed successfully" || { echo "FAIL: Happy path - progress.json missing success"; return 1; }
    echo "PASS: Happy path"
}

# Test 2: Download fails
test_download_fail() {
    clean_env
    create_mock_scripts 1 0 0
    bash "$PIPELINE_SCRIPT"
    local exit_code=$?
    if [ $exit_code -eq 0 ]; then
        echo "FAIL: Download fail - pipeline exited 0"
        return 1
    fi
    grep -q "Download.py failed" "$LOG_FILE" || { echo "FAIL: Download fail - log missing failure"; return 1; }
    check_progress_json "pipeline_run_status" "Pipeline failed during Download.py" || { echo "FAIL: Download fail - progress.json missing failure"; return 1; }
    echo "PASS: Download fail"
}

# Test 3: Scoring fails
test_scoring_fail() {
    clean_env
    create_mock_scripts 0 1 0
    bash "$PIPELINE_SCRIPT"
    local exit_code=$?
    if [ $exit_code -eq 0 ]; then
        echo "FAIL: Scoring fail - pipeline exited 0"
        return 1
    fi
    grep -q "Scoring.py failed" "$LOG_FILE" || { echo "FAIL: Scoring fail - log missing failure"; return 1; }
    check_progress_json "pipeline_run_status" "Pipeline failed during Scoring.py" || { echo "FAIL: Scoring fail - progress.json missing failure"; return 1; }
    echo "PASS: Scoring fail"
}

# Test 4: Engine fails
test_engine_fail() {
    clean_env
    create_mock_scripts 0 0 1
    bash "$PIPELINE_SCRIPT"
    local exit_code=$?
    if [ $exit_code -eq 0 ]; then
        echo "FAIL: Engine fail - pipeline exited 0"
        return 1
    fi
    grep -q "Engine.py failed" "$LOG_FILE" || { echo "FAIL: Engine fail - log missing failure"; return 1; }
    check_progress_json "pipeline_run_status" "Pipeline failed during Engine.py" || { echo "FAIL: Engine fail - progress.json missing failure"; return 1; }
    echo "PASS: Engine fail"
}

# Run all tests
test_happy_path
test_download_fail
test_scoring_fail
test_engine_fail

# Cleanup
rm -f "$SCRIPT_DIR/Download.py" "$SCRIPT_DIR/Scoring.py" "$SCRIPT_DIR/Engine.py"