#!/usr/bin/env python

import json
import os
import time
from contextlib import contextmanager

@contextmanager
def file_lock(lock_path):
    """
    A context manager for a file-based lock using a directory.
    mkdir is an atomic operation, making it a reliable lock mechanism.
    """
    # --- Acquire Lock ---
    # Loop until the lock directory is successfully created.
    while True:
        try:
            os.mkdir(lock_path)
            break  # Lock acquired, exit the loop.
        except FileExistsError:
            # Lock is held by another process, wait and retry.
            time.sleep(0.2)
        except Exception as e:
            print(f"Error acquiring lock {lock_path}: {e}")
            raise  # Re-raise other exceptions.

    # --- Yield to Context and then Release Lock ---
    # The try...finally block ensures the lock is released even if an error occurs
    # within the 'with' block where this context manager is used.
    try:
        yield
    finally:
        try:
            os.rmdir(lock_path)
        except OSError:
            # This can happen if the directory is not empty or doesn't exist.
            # It's generally safe to ignore in the finally block.
            pass

def safe_update_json(file_path, update_data):
    """
    Atomically reads, updates, and writes a JSON file using a file lock.
    """
    lock_path = file_path + ".lock"
    with file_lock(lock_path):
        try:
            # Read existing data
            if os.path.exists(file_path) and os.path.getsize(file_path) > 0:
                with open(file_path, 'r') as f:
                    data = json.load(f)
            else:
                data = {}
        except (json.JSONDecodeError, FileNotFoundError):
            # If file is corrupt or doesn't exist, start fresh
            data = {}
        
        # Update with new data
        data.update(update_data)
        
        # Write back to the file
        with open(file_path, 'w') as f:
            json.dump(data, f, indent=4)