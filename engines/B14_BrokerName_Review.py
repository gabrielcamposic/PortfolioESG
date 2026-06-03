#!/usr/bin/env python3
"""
engines/B14_BrokerName_Review.py

Validate broker-format asset names from data/ledger.csv before downstream
portfolio stages use them. Unknown or low-confidence BrokerName mappings are
written to data/brokername_review.csv and the script exits non-zero so the
pipeline does not publish guessed symbols.

Manual approval flow:
  1. Run pipeline; if it stops, open data/brokername_review.csv.
  2. Fill approved_symbol with the Yahoo ticker, e.g. ISAE4.SA.
  3. Set status to approved.
  4. Run pipeline again; approved rows are applied to parameters/tickers.txt.
"""

from __future__ import annotations

import csv
import os
import re
import sys
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Tuple

ROOT = Path(__file__).resolve().parents[1]
LEDGER_CSV = Path(os.environ.get("BROKERNAME_LEDGER_CSV", ROOT / "data" / "ledger.csv"))
TICKERS_FILE = Path(os.environ.get("BROKERNAME_TICKERS_FILE", ROOT / "parameters" / "tickers.txt"))
REVIEW_CSV = Path(os.environ.get("BROKERNAME_REVIEW_CSV", ROOT / "data" / "brokername_review.csv"))

SKIP_PATTERNS = (" DO ", " DIR ", " SUB ", " BON ")
MODIFIER_TOKENS = {"EX", "EDS", "ED", "ERJ", "EJ", "ATZ"}
ASSET_CLASS_TOKENS = {"ON", "PN", "PNA", "PNB", "UNT", "DR2", "DR3"}
MARKET_TOKENS = {"NM", "N1", "N2", "MA"}
TOKEN_STOPWORDS = MODIFIER_TOKENS | ASSET_CLASS_TOKENS | MARKET_TOKENS | {"S", "A"}


@dataclass
class Resolution:
    symbol: Optional[str]
    confidence: str
    method: str
    reason: str


def normalize_space(value: str) -> str:
    return re.sub(r"\s+", " ", (value or "").strip().upper())


def normalize_key(value: str) -> str:
    return re.sub(r"[^A-Z0-9]", "", normalize_space(value))


def strip_modifiers(value: str) -> str:
    tokens = normalize_space(value).split()
    return " ".join(t for t in tokens if t not in MODIFIER_TOKENS)


def tokenize(value: str) -> set[str]:
    return {
        token
        for token in re.split(r"[^A-Z0-9]+", normalize_space(value))
        if len(token) >= 3 and token not in TOKEN_STOPWORDS
    }


def is_skippable_broker_name(broker_name: str) -> bool:
    padded = f" {normalize_space(broker_name)} "
    return any(pattern in padded for pattern in SKIP_PATTERNS)


def read_csv_rows(path: Path) -> Tuple[List[Dict[str, str]], List[str]]:
    if not path.exists():
        return [], []
    with path.open(newline="", encoding="utf-8") as fh:
        reader = csv.DictReader(fh)
        return list(reader), list(reader.fieldnames or [])


def write_csv_rows(path: Path, rows: List[Dict[str, str]], fieldnames: List[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def load_review_approvals(path: Path) -> Dict[str, str]:
    rows, _ = read_csv_rows(path)
    approvals = {}
    for row in rows:
        status = normalize_space(row.get("status", ""))
        broker_name = normalize_space(row.get("broker_name", ""))
        approved_symbol = normalize_space(row.get("approved_symbol", ""))
        if status == "APPROVED" and broker_name and approved_symbol:
            approvals[broker_name] = approved_symbol
    return approvals


def apply_approved_mappings(approvals: Dict[str, str], tickers_file: Path) -> int:
    if not approvals:
        return 0

    rows, fieldnames = read_csv_rows(tickers_file)
    if not rows:
        raise RuntimeError(f"Could not read tickers file: {tickers_file}")
    if "BrokerName" not in fieldnames:
        fieldnames.append("BrokerName")
        for row in rows:
            row.setdefault("BrokerName", "")

    applied = 0
    rows_by_symbol = {normalize_space(row.get("Ticker", "")): row for row in rows}

    for broker_name, symbol in approvals.items():
        row = rows_by_symbol.get(symbol)
        if not row:
            print(f"[ERROR] Approved symbol {symbol} for '{broker_name}' is not in {tickers_file}")
            continue

        current = normalize_space(row.get("BrokerName", ""))
        if current and current != broker_name:
            print(
                f"[ERROR] {symbol} already has BrokerName '{current}', "
                f"cannot replace with '{broker_name}' automatically"
            )
            continue

        if current != broker_name:
            row["BrokerName"] = broker_name
            applied += 1

    if applied:
        write_csv_rows(tickers_file, rows, fieldnames)

    return applied


def build_resolution_maps(rows: Iterable[Dict[str, str]]) -> Tuple[Dict[str, str], Dict[str, Optional[str]]]:
    exact: Dict[str, str] = {}
    fuzzy_values: Dict[str, set[str]] = defaultdict(set)

    for row in rows:
        symbol = normalize_space(row.get("Ticker", ""))
        broker_name = normalize_space(row.get("BrokerName", ""))
        if not symbol or not broker_name:
            continue
        exact[broker_name] = symbol
        fuzzy_values[strip_modifiers(broker_name)].add(symbol)

    fuzzy: Dict[str, Optional[str]] = {}
    for key, symbols in fuzzy_values.items():
        fuzzy[key] = next(iter(symbols)) if len(symbols) == 1 else None

    return exact, fuzzy


def suggest_symbol(broker_name: str, ticker_rows: Iterable[Dict[str, str]]) -> Resolution:
    broker_tokens = tokenize(broker_name)
    best_symbol = None
    best_score = 0
    best_reason = ""

    for row in ticker_rows:
        symbol = normalize_space(row.get("Ticker", ""))
        haystack = " ".join(
            [
                row.get("BrokerName", ""),
                row.get("Name", ""),
                symbol.replace(".SA", ""),
            ]
        )
        score = len(broker_tokens & tokenize(haystack))
        if score > best_score:
            best_symbol = symbol
            best_score = score
            best_reason = f"{best_score} token(s) in common"

    if best_symbol and best_score >= 2:
        return Resolution(best_symbol, "review", "token_suggestion", best_reason)
    if best_symbol and best_score == 1:
        return Resolution(best_symbol, "low", "weak_token_suggestion", best_reason)
    return Resolution(None, "missing", "not_found", "No confident candidate found")


def resolve_strict(
    broker_name: str,
    exact: Dict[str, str],
    fuzzy: Dict[str, Optional[str]],
    ticker_rows: Iterable[Dict[str, str]],
) -> Resolution:
    name = normalize_space(broker_name)
    if not name:
        return Resolution(None, "skip", "empty", "Empty BrokerName")
    if is_skippable_broker_name(name):
        return Resolution(None, "skip", "non_stock_event", "Non-stock event row")

    if name in exact:
        return Resolution(exact[name], "high", "exact_brokername", "BrokerName is registered")

    stripped = strip_modifiers(name)
    if stripped in fuzzy:
        symbol = fuzzy[stripped]
        if symbol:
            return Resolution(symbol, "high", "modifier_stripped", "Matched after stripping event modifier")
        return Resolution(None, "ambiguous", "modifier_stripped", "Modifier-stripped BrokerName is ambiguous")

    return suggest_symbol(name, ticker_rows)


def summarize_active_broker_names(ledger_csv: Path) -> Dict[str, Dict[str, str]]:
    if not ledger_csv.exists():
        raise RuntimeError(f"Ledger file not found: {ledger_csv}")

    summary: Dict[str, Dict[str, object]] = {}
    with ledger_csv.open(newline="", encoding="utf-8") as fh:
        reader = csv.DictReader(fh)
        for row in reader:
            broker_name = normalize_space(row.get("ticker", ""))
            if not broker_name:
                continue
            side = normalize_space(row.get("side", ""))
            qty = float(row.get("quantity") or 0)
            factor = -1 if side in {"SELL", "S", "VENDA", "V"} else 1

            item = summary.setdefault(
                broker_name,
                {
                    "broker_name": broker_name,
                    "net_qty": 0.0,
                    "trade_count": 0,
                    "sides": set(),
                    "first_trade_date": "",
                    "last_trade_date": "",
                },
            )
            item["net_qty"] = float(item["net_qty"]) + factor * qty
            item["trade_count"] = int(item["trade_count"]) + 1
            item["sides"].add(side)
            trade_date = row.get("trade_date", "")
            if trade_date:
                if not item["first_trade_date"] or trade_date < item["first_trade_date"]:
                    item["first_trade_date"] = trade_date
                if not item["last_trade_date"] or trade_date > item["last_trade_date"]:
                    item["last_trade_date"] = trade_date

    active = {}
    for broker_name, item in summary.items():
        if float(item["net_qty"]) <= 0:
            continue
        active[broker_name] = {
            "broker_name": broker_name,
            "net_qty": f"{float(item['net_qty']):g}",
            "trade_count": str(item["trade_count"]),
            "sides": "|".join(sorted(item["sides"])),
            "first_trade_date": str(item["first_trade_date"]),
            "last_trade_date": str(item["last_trade_date"]),
        }
    return active


def build_pending_rows(
    active: Dict[str, Dict[str, str]],
    ticker_rows: List[Dict[str, str]],
    exact: Dict[str, str],
    fuzzy: Dict[str, Optional[str]],
    previous_rows: List[Dict[str, str]],
) -> List[Dict[str, str]]:
    previous_by_name = {normalize_space(row.get("broker_name", "")): row for row in previous_rows}
    pending = []

    for broker_name, item in sorted(active.items()):
        resolution = resolve_strict(broker_name, exact, fuzzy, ticker_rows)
        if resolution.confidence in {"high", "skip"}:
            continue

        previous = previous_by_name.get(broker_name, {})
        row = {
            **item,
            "status": previous.get("status") or "pending",
            "approved_symbol": previous.get("approved_symbol") or "",
            "suggested_symbol": resolution.symbol or "",
            "confidence": resolution.confidence,
            "method": resolution.method,
            "reason": resolution.reason,
        }
        pending.append(row)

    return pending


def main() -> int:
    approvals = load_review_approvals(REVIEW_CSV)
    applied = apply_approved_mappings(approvals, TICKERS_FILE)
    if applied:
        print(f"[INFO] Applied {applied} approved BrokerName mapping(s) to {TICKERS_FILE}")

    ticker_rows, _ = read_csv_rows(TICKERS_FILE)
    if not ticker_rows:
        print(f"[ERROR] Could not read {TICKERS_FILE}")
        return 1

    exact, fuzzy = build_resolution_maps(ticker_rows)
    active = summarize_active_broker_names(LEDGER_CSV)
    previous_rows, _ = read_csv_rows(REVIEW_CSV)
    pending = build_pending_rows(active, ticker_rows, exact, fuzzy, previous_rows)

    fieldnames = [
        "broker_name",
        "net_qty",
        "trade_count",
        "sides",
        "first_trade_date",
        "last_trade_date",
        "status",
        "approved_symbol",
        "suggested_symbol",
        "confidence",
        "method",
        "reason",
    ]
    write_csv_rows(REVIEW_CSV, pending, fieldnames)

    if pending:
        print(f"[ERROR] {len(pending)} BrokerName mapping(s) need review.")
        print(f"[ERROR] Review file: {REVIEW_CSV}")
        print(f"[ERROR] Canonical mapping file: {TICKERS_FILE}")
        print("[ERROR] Add each missing name to the BrokerName column for its Ticker,")
        print("[ERROR] or fill approved_symbol and set status=approved in the review file.")
        for row in pending:
            suggestion = row["suggested_symbol"] or "(no suggestion)"
            print(
                f"  - missing BrokerName='{row['broker_name']}' "
                f"qty={row['net_qty']} suggested_symbol={suggestion} confidence={row['confidence']}"
            )
        return 2

    print(f"[INFO] BrokerName validation passed for {len(active)} active broker name(s).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
