#!/usr/bin/env python3
"""
GCP Runner with Checkpoint Support

This script wraps the portfolio pipeline with:
1. Checkpoint saving/loading for resumption after Spot VM preemption
2. Graceful handling of SIGTERM (preemption warning)
3. Automatic retry with exponential backoff
4. GCS synchronization before and after execution

Usage:
    python scripts/gcp_runner.py [--stage STAGE] [--skip-sync]

    --stage     Start from specific stage (download, scoring, portfolio, analysis)
    --skip-sync Skip GCS synchronization (for testing)
"""

import os
import sys
import json
import signal
import time
import subprocess
from datetime import datetime
from pathlib import Path
from typing import Optional
import argparse

# Add project root to path
SCRIPT_DIR = Path(__file__).parent.absolute()
PROJECT_ROOT = SCRIPT_DIR.parent
sys.path.insert(0, str(PROJECT_ROOT))

# Configuration
CHECKPOINT_FILE = PROJECT_ROOT / 'data' / 'run_checkpoint.json'
ENGINES_DIR = PROJECT_ROOT / 'engines'
LOGS_DIR = PROJECT_ROOT / 'logs'

# Pipeline stages in order
PIPELINE_STAGES = [
    {
        'name': 'download',
        'script': 'A1_Download.py',
        'description': 'Download stock data from Yahoo Finance',
        'retry_on_interrupt': True,  # Can safely resume
    },
    {
        'name': 'scoring',
        'script': 'A2_Scoring.py',
        'description': 'Score stocks based on metrics',
        'retry_on_interrupt': True,
    },
    {
        'name': 'portfolio',
        'script': 'A3_Portfolio.py',
        'description': 'Generate optimized portfolio',
        'retry_on_interrupt': False,  # Should restart from beginning
    },
    {
        'name': 'analysis',
        'script': 'A4_Analysis.py',
        'description': 'Generate analysis and visualizations',
        'retry_on_interrupt': True,
    },
]

# GCS Configuration (from environment or defaults)
GCS_DATA_BUCKET = os.environ.get('GCS_DATA_BUCKET', 'gs://portfolioesg-data')
GCS_WEBSITE_BUCKET = os.environ.get('GCS_WEBSITE_BUCKET', 'gs://portfolioesg-website')

# Global flag for graceful shutdown
_shutdown_requested = False
_current_stage = None


def log(msg: str, level: str = "INFO"):
    """Simple logging with timestamp."""
    timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    print(f"[{timestamp}] [{level}] {msg}")

    # Also log to file
    log_file = LOGS_DIR / 'gcp_runner.log'
    LOGS_DIR.mkdir(parents=True, exist_ok=True)
    with open(log_file, 'a') as f:
        f.write(f"[{timestamp}] [{level}] {msg}\n")


def signal_handler(signum, frame):
    """Handle SIGTERM (preemption warning) gracefully."""
    global _shutdown_requested
    _shutdown_requested = True
    log(f"Received signal {signum}. Initiating graceful shutdown...", "WARNING")

    # Save checkpoint immediately
    if _current_stage is not None:
        save_checkpoint(_current_stage, 'interrupted')
        log(f"Checkpoint saved for stage '{_current_stage}'")


def load_checkpoint() -> Optional[dict]:
    """Load checkpoint from file if exists."""
    if CHECKPOINT_FILE.exists():
        try:
            with open(CHECKPOINT_FILE, 'r') as f:
                checkpoint = json.load(f)
            log(f"Loaded checkpoint: {checkpoint}")
            return checkpoint
        except (json.JSONDecodeError, Exception) as e:
            log(f"Error loading checkpoint: {e}", "WARNING")
    return None


def save_checkpoint(stage: str, status: str, error_msg: str = None):
    """Save checkpoint to file."""
    checkpoint = {
        'stage': stage,
        'status': status,  # 'running', 'completed', 'interrupted', 'failed'
        'timestamp': datetime.now().isoformat(),
        'error': error_msg,
        'attempt_count': 1
    }

    # Increment attempt count if resuming
    existing = load_checkpoint()
    if existing and existing.get('stage') == stage:
        checkpoint['attempt_count'] = existing.get('attempt_count', 0) + 1

    CHECKPOINT_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(CHECKPOINT_FILE, 'w') as f:
        json.dump(checkpoint, f, indent=2)

    log(f"Checkpoint saved: stage={stage}, status={status}")


def clear_checkpoint():
    """Remove checkpoint file after successful completion."""
    if CHECKPOINT_FILE.exists():
        CHECKPOINT_FILE.unlink()
        log("Checkpoint cleared")


def get_stage_index(stage_name: str) -> int:
    """Get the index of a stage by name."""
    for i, stage in enumerate(PIPELINE_STAGES):
        if stage['name'] == stage_name:
            return i
    return 0


def sync_from_gcs(skip: bool = False):
    """Sync data from GCS before execution."""
    if skip:
        log("Skipping GCS sync (--skip-sync)")
        return

    log("Syncing data from GCS...")
    try:
        # Sync data directory
        subprocess.run([
            'gsutil', '-m', 'rsync', '-r',
            f'{GCS_DATA_BUCKET}/data/findb',
            str(PROJECT_ROOT / 'data' / 'findb')
        ], check=True, capture_output=True)

        subprocess.run([
            'gsutil', '-m', 'rsync', '-r',
            f'{GCS_DATA_BUCKET}/data/results',
            str(PROJECT_ROOT / 'data' / 'results')
        ], check=True, capture_output=True)

        subprocess.run([
            'gsutil', '-m', 'rsync', '-r',
            f'{GCS_DATA_BUCKET}/parameters',
            str(PROJECT_ROOT / 'parameters')
        ], check=True, capture_output=True)

        log("GCS sync completed successfully")
    except subprocess.CalledProcessError as e:
        log(f"GCS sync failed: {e.stderr.decode() if e.stderr else e}", "WARNING")
    except FileNotFoundError:
        log("gsutil not found. Skipping GCS sync.", "WARNING")


def sync_to_gcs(skip: bool = False):
    """Sync data back to GCS after execution."""
    if skip:
        log("Skipping GCS upload (--skip-sync)")
        return

    log("Syncing data to GCS...")
    try:
        # Sync results
        subprocess.run([
            'gsutil', '-m', 'rsync', '-r',
            str(PROJECT_ROOT / 'data' / 'results'),
            f'{GCS_DATA_BUCKET}/data/results'
        ], check=True, capture_output=True)

        subprocess.run([
            'gsutil', '-m', 'rsync', '-r',
            str(PROJECT_ROOT / 'data' / 'findb'),
            f'{GCS_DATA_BUCKET}/data/findb'
        ], check=True, capture_output=True)

        # Sync website data
        subprocess.run([
            'gsutil', '-m', 'rsync', '-r',
            str(PROJECT_ROOT / 'html' / 'data'),
            f'{GCS_WEBSITE_BUCKET}/data'
        ], check=True, capture_output=True)

        log("GCS upload completed successfully")
    except subprocess.CalledProcessError as e:
        log(f"GCS upload failed: {e.stderr.decode() if e.stderr else e}", "WARNING")
    except FileNotFoundError:
        log("gsutil not found. Skipping GCS upload.", "WARNING")


def run_stage(stage: dict) -> bool:
    """Run a single pipeline stage.

    Returns:
        bool: True if successful, False if failed or interrupted
    """
    global _current_stage, _shutdown_requested

    stage_name = stage['name']
    script_path = ENGINES_DIR / stage['script']

    _current_stage = stage_name
    log(f"Starting stage: {stage_name} - {stage['description']}")
    save_checkpoint(stage_name, 'running')

    if _shutdown_requested:
        log(f"Shutdown requested before starting {stage_name}", "WARNING")
        save_checkpoint(stage_name, 'interrupted')
        return False

    try:
        # Find Python executable
        venv_python = PROJECT_ROOT / '.venv' / 'bin' / 'python'
        python_exe = str(venv_python) if venv_python.exists() else 'python3'

        # Run the script
        env = os.environ.copy()
        env['PYTHONPATH'] = str(PROJECT_ROOT)

        result = subprocess.run(
            [python_exe, str(script_path)],
            cwd=str(PROJECT_ROOT),
            env=env,
            capture_output=False  # Show output in real-time
        )

        if _shutdown_requested:
            log(f"Shutdown requested during {stage_name}", "WARNING")
            save_checkpoint(stage_name, 'interrupted')
            return False

        if result.returncode != 0:
            log(f"Stage {stage_name} failed with return code {result.returncode}", "ERROR")
            save_checkpoint(stage_name, 'failed', f"Return code: {result.returncode}")
            return False

        log(f"Stage {stage_name} completed successfully")
        save_checkpoint(stage_name, 'completed')
        return True

    except Exception as e:
        log(f"Stage {stage_name} raised exception: {e}", "ERROR")
        save_checkpoint(stage_name, 'failed', str(e))
        return False


def run_pipeline(start_stage: str = None, skip_sync: bool = False) -> bool:
    """Run the complete pipeline from a given stage.

    Returns:
        bool: True if all stages completed successfully
    """
    # Check for existing checkpoint
    checkpoint = load_checkpoint()

    if start_stage:
        start_idx = get_stage_index(start_stage)
        log(f"Starting from stage: {start_stage} (index {start_idx})")
    elif checkpoint and checkpoint.get('status') in ('interrupted', 'running'):
        # Resume from interrupted stage
        stage_name = checkpoint['stage']
        stage_config = next((s for s in PIPELINE_STAGES if s['name'] == stage_name), None)

        if stage_config and stage_config.get('retry_on_interrupt', True):
            start_idx = get_stage_index(stage_name)
            log(f"Resuming from interrupted stage: {stage_name}")

            # Wait before retry (in case of rapid restart)
            wait_time = min(30 * checkpoint.get('attempt_count', 1), 180)  # Max 3 minutes
            log(f"Waiting {wait_time}s before retry (attempt {checkpoint.get('attempt_count', 1)})")
            time.sleep(wait_time)
        else:
            log(f"Stage {stage_name} cannot be resumed. Restarting from beginning.")
            start_idx = 0
    else:
        start_idx = 0
        log("Starting fresh pipeline run")

    # Sync from GCS
    sync_from_gcs(skip_sync)

    # Run stages
    success = True
    for i, stage in enumerate(PIPELINE_STAGES[start_idx:], start=start_idx):
        if _shutdown_requested:
            log("Shutdown requested. Stopping pipeline.", "WARNING")
            success = False
            break

        if not run_stage(stage):
            success = False
            break

    # Sync to GCS
    if success or any(
        s.get('status') == 'completed'
        for s in [load_checkpoint()] if s
    ):
        sync_to_gcs(skip_sync)

    if success:
        clear_checkpoint()
        log("Pipeline completed successfully!")
    else:
        log("Pipeline did not complete successfully", "WARNING")

    return success


def main():
    parser = argparse.ArgumentParser(
        description='Run PortfolioESG pipeline with checkpoint support'
    )
    parser.add_argument('--stage', type=str, choices=[s['name'] for s in PIPELINE_STAGES],
                        help='Start from specific stage')
    parser.add_argument('--skip-sync', action='store_true',
                        help='Skip GCS synchronization')
    parser.add_argument('--status', action='store_true',
                        help='Show current checkpoint status and exit')

    args = parser.parse_args()

    # Show status only
    if args.status:
        checkpoint = load_checkpoint()
        if checkpoint:
            print(json.dumps(checkpoint, indent=2))
        else:
            print("No checkpoint found")
        return 0

    # Set up signal handlers
    signal.signal(signal.SIGTERM, signal_handler)
    signal.signal(signal.SIGINT, signal_handler)

    log("=" * 60)
    log("PortfolioESG GCP Runner with Checkpoint Support")
    log("=" * 60)

    # Run pipeline
    success = run_pipeline(args.stage, args.skip_sync)

    return 0 if success else 1


if __name__ == '__main__':
    sys.exit(main())


