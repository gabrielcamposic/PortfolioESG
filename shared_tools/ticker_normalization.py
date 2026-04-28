#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
shared_tools/ticker_normalization.py

Shared ticker normalization logic used by B2_Consolidate_Ledger and
B4_Portfolio_History to resolve broker-format ticker names (e.g.
"VULCABRAS ON EDS NM") to Yahoo Finance symbols (e.g. "VULC3.SA").

Single source of truth: parameters/tickers.txt (BrokerName column).

Corporate-action modifiers like EX, EDS, ED are stripped during fuzzy
matching so that "AXIA ENERGIAPNB N1" matches "AXIA ENERGIAPNB EX N1".
"""

import csv
import re
from pathlib import Path
from typing import Dict, Optional

ROOT = Path(__file__).resolve().parents[1]
TICKERS_FILE = ROOT / "parameters" / "tickers.txt"

# Words that indicate non-stock events (dividends, rights, subscriptions)
SKIP_PATTERNS = [" DO ", " DIR ", " SUB ", " BON "]

# Corporate-action modifier tokens to strip during fuzzy matching
# EX  = ex-something (ex-direitos, ex-dividendos)
# EDS = ex-direitos de subscrição
# ED  = ex-dividendos
# ERJ = ex-recebimento de juros
# EJ  = ex-juros
_MODIFIER_TOKENS = {"EX", "EDS", "ED", "ERJ", "EJ"}

# Module-level cache
_RESOLVED_CACHE: Dict[str, Optional[str]] = {}
_MAPPINGS_LOADED = False
_EXACT_MAP: Dict[str, str] = {}       # uppercase broker_name → ticker
_FUZZY_MAP: Dict[str, str] = {}       # normalized broker_name (modifiers stripped) → ticker
_COMPANY_NAME_MAP: Dict[str, str] = {}  # uppercase company name → ticker


def _strip_modifiers(name: str) -> str:
    """Remove corporate-action modifier tokens from a broker name.

    "VULCABRAS ON EDS NM" → "VULCABRAS ON NM"
    "AXIA ENERGIAPNB EX N1" → "AXIA ENERGIAPNB N1"
    """
    tokens = name.upper().split()
    return " ".join(t for t in tokens if t not in _MODIFIER_TOKENS)


def _load_mappings() -> None:
    """Load tickers.txt and build exact + fuzzy mappings."""
    global _MAPPINGS_LOADED, _EXACT_MAP, _FUZZY_MAP, _COMPANY_NAME_MAP

    if _MAPPINGS_LOADED:
        return
    _MAPPINGS_LOADED = True

    if not TICKERS_FILE.exists():
        return

    with open(TICKERS_FILE, "r", encoding="utf-8") as fh:
        reader = csv.DictReader(fh)
        for row in reader:
            ticker = (row.get("Ticker") or "").strip()
            broker_name = (row.get("BrokerName") or "").strip()
            company_name = (row.get("Name") or "").strip()

            if not ticker:
                continue

            # Exact BrokerName → Ticker
            if broker_name:
                key = broker_name.upper()
                _EXACT_MAP[key] = ticker
                # Also store a fuzzy version with modifiers stripped
                fuzzy_key = _strip_modifiers(key)
                if fuzzy_key != key:
                    _FUZZY_MAP[fuzzy_key] = ticker
                else:
                    _FUZZY_MAP[fuzzy_key] = ticker

            # Company name mappings
            if company_name:
                _COMPANY_NAME_MAP[company_name.upper()] = ticker
                # Short name after " - "
                if " - " in company_name:
                    short = company_name.split(" - ")[-1].strip().upper()
                    if short and len(short) >= 3:
                        _COMPANY_NAME_MAP[short] = ticker


def resolve_broker_ticker(broker_name: str) -> Optional[str]:
    """Resolve a broker-format ticker name to a Yahoo Finance symbol.

    Returns None for non-stock entries (dividends, rights, etc.).

    Resolution order:
      1. Exact BrokerName match (case-insensitive)
      2. Fuzzy match after stripping corporate-action modifiers (EX/EDS/ED)
      3. Company name / short name match (first word)
      4. Prefix match on BrokerName keys
    """
    if not broker_name:
        return None

    name = broker_name.strip()

    # Skip non-stock entries
    name_upper = name.upper()
    for pat in SKIP_PATTERNS:
        if pat in name_upper:
            return None

    # Check cache
    if name_upper in _RESOLVED_CACHE:
        return _RESOLVED_CACHE[name_upper]

    _load_mappings()

    result = None

    # Strategy 1: Exact BrokerName match
    if name_upper in _EXACT_MAP:
        result = _EXACT_MAP[name_upper]

    # Strategy 2: Fuzzy match (strip modifiers from input, match against fuzzy map)
    if result is None:
        fuzzy_input = _strip_modifiers(name_upper)
        if fuzzy_input in _FUZZY_MAP:
            result = _FUZZY_MAP[fuzzy_input]
        # Also try: the input itself might be the base form, and tickers.txt has the modified form
        if result is None and fuzzy_input in _EXACT_MAP:
            result = _EXACT_MAP[fuzzy_input]

    # Strategy 3: Company name match (first word or first two words)
    if result is None:
        words = name_upper.split()
        if words:
            first = words[0]
            if first in _COMPANY_NAME_MAP:
                result = _COMPANY_NAME_MAP[first]
            elif len(words) >= 2:
                first_two = f"{words[0]} {words[1]}"
                if first_two in _COMPANY_NAME_MAP:
                    result = _COMPANY_NAME_MAP[first_two]

    # Strategy 4: Prefix match on BrokerName keys
    if result is None:
        words = name_upper.split()
        if words:
            first_word = words[0]
            for key, ticker in _EXACT_MAP.items():
                if key.startswith(first_word) and len(key) > len(first_word):
                    result = ticker
                    break

    _RESOLVED_CACHE[name_upper] = result
    return result


def clear_cache() -> None:
    """Clear the module-level caches (useful for testing)."""
    global _RESOLVED_CACHE, _MAPPINGS_LOADED, _EXACT_MAP, _FUZZY_MAP, _COMPANY_NAME_MAP
    _RESOLVED_CACHE.clear()
    _EXACT_MAP.clear()
    _FUZZY_MAP.clear()
    _COMPANY_NAME_MAP.clear()
    _MAPPINGS_LOADED = False

