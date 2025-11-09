"""
Path normalization helpers extracted from A1_Download.py to provide a single
place for making parameter paths portable between machines.

Functions:
- _normalize_path_candidate(path_candidate, script_dir): try expanduser/envvars,
  replace other-users /Users/<other>/... with current home, and fallback to
  repo's parameters/ or repo root.
- resolve_paths_in_params(params, script_dir, logger=None): normalize string
  values in a params dict in-place and return the dict.

This module is pure-Python and has no heavy imports, so it can be imported
safely from other engines without pulling in pandas/yfinance during startup.
"""
from __future__ import annotations

import os
import re
from typing import Optional, Dict


def _normalize_path_candidate(path_candidate: str, script_dir: str) -> str:
    """Normalize a single path-like candidate to a local machine path.

    Heuristics used (in order):
    - Expand ~ and environment variables.
    - If the candidate exists as expanded, return its absolute path.
    - If it matches /Users/<other_user>/..., replace the home prefix with the
      current user's home and test for existence.
    - If the basename exists under the repo's parameters/ directory, return that.
    - If it's a relative path that can be joined to the repo root, return that.
    - Otherwise return the expanded absolute path.
    """
    if not isinstance(path_candidate, str) or not path_candidate:
        return path_candidate

    expanded = os.path.expanduser(os.path.expandvars(path_candidate))

    # If it exists already, prefer it.
    if os.path.exists(expanded):
        return os.path.abspath(expanded)

    # Replace /Users/<other_user>/... with current user's home and test.
    m = re.match(r'^/Users/[^/]+(/.*)$', expanded)
    if m:
        home = os.path.expanduser('~')
        candidate = os.path.join(home, m.group(1).lstrip('/'))
        if os.path.exists(candidate):
            return os.path.abspath(candidate)

    # Try locating the file under this repository's parameters/ directory
    repo_parameters = os.path.abspath(os.path.join(script_dir, '..', 'parameters'))
    basename = os.path.basename(expanded)
    if basename:
        repo_candidate = os.path.join(repo_parameters, basename)
        if os.path.exists(repo_candidate):
            return os.path.abspath(repo_candidate)

    # Try joining a relative/absolute-ish path to the repo root
    repo_root_candidate = os.path.abspath(os.path.join(script_dir, '..', expanded.lstrip(os.sep)))
    if os.path.exists(repo_root_candidate):
        return repo_root_candidate

    # Last resort: return expanded absolute form (may not exist)
    return os.path.abspath(expanded)


def _looks_like_path(s: str) -> bool:
    """Heuristic: return True if the string looks like a filesystem path.

    We avoid treating generic config values (like comma/colon lists) as paths.
    Criteria:
    - starts with '~'
    - contains a forward or back slash
    - ends with a common file extension (.txt, .csv, .json, .db, .log)
    """
    if not isinstance(s, str) or not s:
        return False
    if s.startswith('~'):
        return True
    if os.path.sep in s or ('/' in s) or ('\\' in s):
        return True
    lower = s.lower()
    for ext in ('.txt', '.csv', '.json', '.db', '.log'):
        if lower.endswith(ext):
            return True
    return False


def resolve_paths_in_params(params: Dict, script_dir: str, logger: Optional[object] = None) -> Dict:
    """Normalize string-valued entries in params to local-machine paths.

    Non-string params are left untouched. The function mutates the provided
    dict in-place and also returns it for convenience.
    """
    if not isinstance(params, dict):
        return params

    keys_to_try = [k for k in params.keys() if isinstance(params.get(k), str)]
    for key in keys_to_try:
        original = params.get(key)
        # Only attempt normalization for values that look like file-system paths.
        if not _looks_like_path(original):
            continue
        try:
            normalized = _normalize_path_candidate(original, script_dir)
            if normalized != original:
                if logger:
                    try:
                        logger.debug(f"Resolved param '{key}': '{original}' -> '{normalized}'")
                    except Exception:
                        pass
                params[key] = normalized
        except Exception:
            if logger:
                try:
                    logger.debug(f"Could not normalize parameter '{key}' ('{original}')")
                except Exception:
                    pass

    # Backwards compatibility convenience keys
    if 'FINDATA_PATH' in params and not params.get('findata_directory'):
        params['findata_directory'] = params.get('FINDATA_PATH') or params.get('findata_directory')
    if 'findata_directory' in params and not params.get('FINDATA_PATH'):
        params['FINDATA_PATH'] = params.get('findata_directory')

    return params
