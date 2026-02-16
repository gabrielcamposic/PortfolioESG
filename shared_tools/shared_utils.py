#!/usr/bin/env python

import json
import os
import sys
import logging
import tempfile
from datetime import datetime, timedelta
from dateutil.easter import easter
from holidays.countries.brazil import Brazil as BrazilHolidays
from typing import List, Dict, Any, Union
from os import PathLike


class FlushingStreamHandler(logging.StreamHandler):
    """
    A StreamHandler that flushes after every emit.
    This prevents buffering pauses in terminal output.
    """
    def emit(self, record):
        super().emit(record)
        self.flush()


class JsonWebLogHandler(logging.Handler):
    """
    A custom logging handler that reads, updates, and writes a JSON file.
    It only acts on log records that have a 'web_data' attribute.
    """
    def __init__(self, filename):
        super().__init__()
        self.filename = filename
        # Ensure the directory for the web log exists before we start.
        dir_name = os.path.dirname(self.filename)
        if dir_name:
            os.makedirs(dir_name, exist_ok=True)

    def emit(self, record):
        """
        This method is called for every log message. We check for our special data.
        """
        if hasattr(record, 'web_data'):
            web_data_to_log = record.web_data

            try:
                # Read current state of the JSON file.
                try:
                    with open(self.filename, 'r', encoding='utf-8') as f:
                        data = json.load(f)
                except (FileNotFoundError, json.JSONDecodeError):
                    print(f"WARNING: JsonWebLogHandler could not read '{self.filename}'. Starting with a new dictionary.")
                    data = {}

                # recursive update
                def recursive_update(d, u):
                    for k, v in u.items():
                        if isinstance(v, dict) and k in d and isinstance(d[k], dict):
                            d[k] = recursive_update(d.get(k, {}), v)
                        else:
                            d[k] = v
                    return d

                data = recursive_update(data, web_data_to_log)

                # Write updated dictionary back to file using standard json.dump (non-atomic for now)
                dir_name = os.path.dirname(self.filename) or '.'
                os.makedirs(dir_name, exist_ok=True)
                with open(self.filename, 'w', encoding='utf-8') as f:
                    json.dump(data, f, indent=4)

            except Exception as e:
                print(f"CRITICAL: JsonWebLogHandler failed to write to '{self.filename}': {e}")

# Keep write_json_atomic available here for centralized use by A1_Download.py
def write_json_atomic(path: Union[str, PathLike[str], bytes], data: Dict[str, Any]) -> None:
    """
    Write a JSON file atomically: write to a temp file in the same directory and replace.
    Keeps UTF-8 and pretty formatting and ensures the directory exists.
    """
    # Expect incoming path as a plain string; normalize with os.fspath for safety
    path_str = os.fspath(path)
    if not path_str:
        raise ValueError("No path provided for write_json_atomic")
    directory = os.path.dirname(path_str) or "."
    os.makedirs(directory, exist_ok=True)
    fd = None
    tmp_path = None
    try:
        fd, tmp_path = tempfile.mkstemp(prefix='.tmp_json_', dir=directory)
        with os.fdopen(fd, 'w', encoding='utf-8') as f:
            fd = None
            json.dump(data, f, indent=4, ensure_ascii=False)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp_path, path_str)
    except Exception:
        # Ensure tmp file is removed on failure
        if tmp_path and os.path.exists(tmp_path):
            try:
                os.remove(tmp_path)
            except Exception:
                pass
        raise

def setup_logger(logger_name, log_file, web_log_file, level=logging.INFO):
    """
    Configures and returns a logger with console, file, and custom web JSON handlers.

    This function is idempotent: if a logger with the same name is already
    configured, it will return the existing logger without adding more handlers.
    """
    logger = logging.getLogger(logger_name)

    # Prevent adding duplicate handlers if this function is called multiple times.
    if logger.hasHandlers():
        return logger

    logger.setLevel(level)

    # Create a standard formatter for console and file logs.
    formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')

    # --- Handler 1: Console Output (FlushingStreamHandler) ---
    # Uses custom handler that flushes after each message to avoid buffering pauses
    stream_handler = FlushingStreamHandler(sys.stdout)
    stream_handler.setFormatter(formatter)
    logger.addHandler(stream_handler)

    # --- Handler 2: Main Log File (FileHandler) ---
    # --- FIX: Add validation to ensure log_file is a valid path ---
    if log_file and isinstance(log_file, str):
        # Ensure the directory for the main log file exists.
        log_dir = os.path.dirname(log_file)
        if log_dir:
            os.makedirs(log_dir, exist_ok=True)
        file_handler = logging.FileHandler(log_file, mode='a')
        file_handler.setFormatter(formatter)
        logger.addHandler(file_handler)
    else:
        print(f"Warning: No valid log_file path provided for logger '{logger_name}'. File logging will be disabled.")
    # --- END FIX ---

    # --- Handler 3: Our Custom Web JSON Handler ---
    # --- FIX: Add validation to ensure web_log_file is a valid path ---
    if web_log_file and isinstance(web_log_file, str):
        json_handler = JsonWebLogHandler(web_log_file)
        logger.addHandler(json_handler)
    else:
        print(f"Warning: No valid web_log_file path provided for logger '{logger_name}'. Web logging will be disabled.")
    # --- END FIX ---

    return logger

def load_parameters_from_file(
    filepaths: Union[str, List[str]],
    expected_parameters: Dict[str, Any],
    logger_instance: logging.Logger = None
) -> Dict[str, Any]:
    """
    Reads parameters from a list of files, converting them to appropriate types.
    Parameters from later files in the list will override those from earlier files.

    Args:
        filepaths (Union[str, List[str]]): A single file path or a list of file paths.
        expected_parameters (dict): Dictionary of parameter names to their expected types.
        logger_instance: Optional logger instance for logging messages.

    Returns:
        dict: A dictionary of the merged and loaded parameters.
    """
    parameters = {}

    # --- FIX: Use a new, clearly-typed variable to avoid IDE confusion ---
    # This avoids reassigning the input argument and makes the logic clearer.
    paths_to_process: List[str]
    if isinstance(filepaths, str):
        paths_to_process = [filepaths]
    else:
        paths_to_process = filepaths
    # --- END FIX ---

    for filepath in paths_to_process:
        try:
            # The 'open' call is now unambiguous for the IDE
            with open(filepath, 'r') as f:
                for line_number, line in enumerate(f, 1):
                    line = line.strip()
                    if not line or line.startswith('#'):
                        continue

                    parts = line.split('=', 1)
                    if len(parts) != 2:
                        message = f"Malformed line {line_number} in '{filepath}': '{line}'. Skipping."
                        if logger_instance:
                            logger_instance.warning(message)
                        else:
                            print(f"Warning: {message}")
                        continue

                    key, value_str = parts[0].strip(), parts[1].strip()

                    # Strip surrounding quotes (single or double) from the value string.
                    if (value_str.startswith('"') and value_str.endswith('"')) or \
                            (value_str.startswith("'") and value_str.endswith("'")):
                        value_str = value_str[1:-1]

                    target_type = expected_parameters.get(key)

                    try:
                        if target_type:
                            if target_type == bool:
                                if value_str.lower() in ('true', 'yes', '1'):
                                    parameters[key] = True
                                elif value_str.lower() in ('false', 'no', '0'):
                                    parameters[key] = False
                                else:
                                    raise ValueError(
                                        f"Boolean value for '{key}' must be one of 'true'/'false', got '{value_str}'")
                            elif target_type == str:
                                parameters[key] = os.path.expanduser(value_str) if value_str.startswith(
                                    '~') else value_str
                            else:  # For int, float, etc.
                                parameters[key] = target_type(value_str)
                        else:  # Unknown parameter
                            message = f"Unknown parameter key '{key}' in '{filepath}'. Treating as string."
                            if logger_instance:
                                logger_instance.debug(message)
                            parameters[key] = os.path.expanduser(value_str) if value_str.startswith('~') else value_str
                    except ValueError:
                        message = (f"Could not convert value '{value_str}' for key '{key}' to {target_type.__name__}. "
                                   f"Falling back to raw string value.")
                        if logger_instance:
                            logger_instance.warning(message)
                        else:
                            print(f"Warning: {message}")
                        parameters[key] = value_str  # Fallback to string

        except FileNotFoundError:
            message = f"Parameters file not found: '{filepath}'"
            if logger_instance:
                logger_instance.critical(message)
            else:
                print(f"CRITICAL ERROR: {message}")
            raise
        except Exception as e:
            message = f"Failed to read or parse parameters file '{filepath}'"
            if logger_instance:
                logger_instance.exception(message)
            else:
                print(f"CRITICAL ERROR: {message}: {e}")
            raise

    return parameters

def get_sao_paulo_holidays(year: int, params: dict, logger: logging.Logger) -> dict:
    """
    Generates a comprehensive dictionary of São Paulo (B3) market holidays for a given year.

    This includes:
    - Standard national and São Paulo state holidays from the `holidays` library.
    - Fixed market-specific holidays (e.g., Christmas Eve).
    - Floating religious holidays calculated from Easter (e.g., Carnival).
    - A hardcoded list of known, one-off special market closure dates from parameters.

    Args:
        year: The integer year for which to generate holidays.
        params: The dictionary of loaded parameters, used to get SPECIAL_MARKET_CLOSURES.
        logger: The configured logger instance.

    Returns:
        A dictionary where keys are `datetime.date` objects and values are the holiday names.
    """
    # 1. Get base holidays from the library
    holiday_dict = BrazilHolidays(years=year, subdiv='SP')

    # 2. Define custom fixed holidays
    fixed_holidays = {
        datetime(year, 1, 25).date(): "Aniversário de São Paulo",
        datetime(year, 7, 9).date(): "Data Magna SP",
        datetime(year, 11, 20).date(): "Consciência Negra",
        datetime(year, 12, 24).date(): "Véspera de Natal",
        datetime(year, 12, 31).date(): "Véspera de Ano Novo",
    }

    # 3. Define custom floating holidays based on Easter
    easter_sunday = easter(year)
    floating_holidays = {
        (easter_sunday - timedelta(days=48)): "Carnaval (Segunda-feira)",
        (easter_sunday - timedelta(days=47)): "Carnaval (Terça-feira)",
        (easter_sunday - timedelta(days=2)): "Sexta-feira Santa",
        (easter_sunday + timedelta(days=60)): "Corpus Christi",
    }

    # 4. Parse special, one-off market closures from parameters
    all_special_closures = {}
    closures_str = params.get("SPECIAL_MARKET_CLOSURES", "")
    if closures_str:
        for pair in closures_str.split(','):
            try:
                date_str, name = pair.split(':', 1)
                date_obj = datetime.strptime(date_str.strip(), "%Y-%m-%d").date()
                all_special_closures[date_obj] = name.strip()
            except ValueError:
                logger.warning(f"Could not parse entry in SPECIAL_MARKET_CLOSURES: '{pair}'. Skipping.")

    special_closures_for_year = {
        date: name for date, name in all_special_closures.items() if date.year == year
    }

    # 5. Merge all dictionaries
    holiday_dict.update(fixed_holidays)
    holiday_dict.update(floating_holidays)
    holiday_dict.update(special_closures_for_year)

    return holiday_dict

def get_previous_business_day(params: dict, logger: logging.Logger) -> str:
    """
    Calculates the most recent, previous business day, using the full holiday calendar.

    This function robustly finds the last valid trading day before today by
    looping backwards and checking against a comprehensive holiday list generated
    for the relevant years.

    Args:
        params: The dictionary of loaded parameters.
        logger: The configured logger instance.

    Returns:
        The date string of the previous business day in 'YYYY-MM-DD' format.
    """
    today = datetime.today()
    # Generate a full holiday list for this year and last year to be safe
    sp_holidays = get_sao_paulo_holidays(today.year, params, logger)
    sp_holidays.update(get_sao_paulo_holidays(today.year - 1, params, logger))

    previous_day = today - timedelta(days=1)
    # Loop backwards until we find a day that is not a weekend or in our holiday list
    while previous_day.weekday() >= 5 or previous_day.date() in sp_holidays:
        previous_day -= timedelta(days=1)

    return previous_day.strftime('%Y-%m-%d')
