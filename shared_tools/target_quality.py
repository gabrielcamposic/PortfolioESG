"""Target quality heuristics shared by scoring and recommendation diagnostics."""

from __future__ import annotations

import math
import re
from datetime import datetime
from typing import Any, Dict, Iterable, List, Optional


DEFAULT_TARGET_QUALITY_PARAMS = {
    "TARGET_EXTREME_UPSIDE_PCT": 150.0,
    "TARGET_REJECT_UPSIDE_PCT": 300.0,
    "TARGET_LOW_PRICE": 1.0,
    "TARGET_STALE_DAYS": 45,
    "TARGET_MAX_FALLBACK_QUALITY": 0.35,
    "TARGET_LOW_LIQUIDITY_AVG_VOLUME": 100000.0,
    "TARGET_CLASS_TARGET_TOLERANCE_PCT": 15.0,
    "TARGET_CLASS_PRICE_RATIO": 3.0,
    "TARGET_DISTRESSED_RETURN_PCT": -50.0,
}

DEFAULT_RETURN_ADJUSTMENT_PARAMS = {
    "RETURN_ADJUSTMENT_CAP_PCT": 150.0,
    "RETURN_ADJUSTMENT_FLOOR_PCT": -80.0,
    "RETURN_ADJUSTMENT_BASE_PCT": 0.0,
    "RETURN_ADJUSTMENT_REJECT_BASE_PCT": 0.0,
    "RETURN_ADJUSTMENT_UNCERTAINTY_PENALTY_PCT": 0.0,
}


DEFAULT_PARAMS = {
    **DEFAULT_TARGET_QUALITY_PARAMS,
    **DEFAULT_RETURN_ADJUSTMENT_PARAMS,
}


def _float_or_none(value: Any) -> Optional[float]:
    if value is None or value == "":
        return None
    try:
        numeric = float(value)
    except (TypeError, ValueError):
        return None
    if not math.isfinite(numeric):
        return None
    return numeric


def _param_float(params: Dict[str, Any], key: str) -> float:
    value = _float_or_none(params.get(key))
    return float(value if value is not None else DEFAULT_PARAMS[key])


def _param_int(params: Dict[str, Any], key: str) -> int:
    value = _float_or_none(params.get(key))
    return int(value if value is not None else DEFAULT_PARAMS[key])


def ticker_root(ticker: str) -> str:
    """Return the root shared by B3 share classes/units, e.g. KLBN4 -> KLBN."""
    clean = str(ticker or "").upper().replace(".SA", "")
    return re.sub(r"\d+$", "", clean)


def parse_date(value: Any) -> Optional[datetime]:
    if value is None or value == "":
        return None
    if isinstance(value, datetime):
        return value
    text = str(value)
    for fmt in ("%Y-%m-%d %H:%M:%S.%f", "%Y-%m-%d %H:%M:%S", "%Y-%m-%d"):
        try:
            return datetime.strptime(text[: len(fmt)], fmt)
        except ValueError:
            continue
    try:
        return datetime.fromisoformat(text.replace("Z", "+00:00")).replace(tzinfo=None)
    except ValueError:
        return None


def build_related_target_context(
    records: Iterable[Dict[str, Any]],
    params: Optional[Dict[str, Any]] = None,
) -> Dict[str, Dict[str, Any]]:
    """Detect likely target/class mismatches among tickers with the same root."""
    params = params or {}
    tolerance = _param_float(params, "TARGET_CLASS_TARGET_TOLERANCE_PCT") / 100.0
    min_price_ratio = _param_float(params, "TARGET_CLASS_PRICE_RATIO")

    grouped: Dict[str, List[Dict[str, Any]]] = {}
    for raw in records:
        stock = str(raw.get("Stock") or raw.get("stock") or raw.get("ticker") or "")
        if not stock:
            continue
        current = _float_or_none(raw.get("CurrentPrice", raw.get("current_price")))
        target = _float_or_none(raw.get("TargetPrice", raw.get("target_price")))
        if current is None or target is None or current <= 0 or target <= 0:
            continue
        grouped.setdefault(ticker_root(stock), []).append(
            {"stock": stock, "current": current, "target": target}
        )

    context: Dict[str, Dict[str, Any]] = {}
    for rows in grouped.values():
        if len(rows) < 2:
            continue
        for row in rows:
            for other in rows:
                if row["stock"] == other["stock"]:
                    continue
                target_delta = abs(row["target"] - other["target"]) / max(row["target"], other["target"])
                price_ratio = max(row["current"], other["current"]) / min(row["current"], other["current"])
                if target_delta <= tolerance and price_ratio >= min_price_ratio:
                    context[row["stock"]] = {
                        "matched_ticker": other["stock"],
                        "target_delta_pct": round(target_delta * 100, 2),
                        "price_ratio": round(price_ratio, 2),
                    }
                    break
    return context


def quality_bucket(score: float, force_reject: bool = False) -> str:
    if force_reject or score <= 0.15:
        return "reject"
    if score <= 0.40:
        return "low"
    if score <= 0.70:
        return "medium"
    return "high"


def evaluate_target_quality(
    record: Dict[str, Any],
    params: Optional[Dict[str, Any]] = None,
    related_context: Optional[Dict[str, Dict[str, Any]]] = None,
    as_of: Optional[datetime] = None,
) -> Dict[str, Any]:
    """Return quality score, bucket and flags for a target price signal."""
    params = params or {}
    related_context = related_context or {}
    as_of = as_of or datetime.now()

    stock = str(record.get("Stock") or record.get("stock") or record.get("ticker") or "")
    current = _float_or_none(record.get("CurrentPrice", record.get("current_price")))
    target = _float_or_none(record.get("TargetPrice", record.get("target_price")))
    source = str(record.get("TargetPriceSource", record.get("target_source", "")) or "None")
    forward_pe = _float_or_none(record.get("forwardPE", record.get("forward_pe")))
    avg_volume = _float_or_none(record.get("averageVolume", record.get("average_volume")))
    historical_return_pct = _float_or_none(record.get("HistoricalReturnPct", record.get("historical_return_pct")))
    last_updated = parse_date(record.get("LastUpdated", record.get("last_updated")))

    flags: List[str] = []
    score = 1.0
    force_reject = False

    if target is None or target <= 0:
        flags.append("missing_target")
        score = 0.0
        force_reject = True

    raw_upside_pct = None
    if current is None or current <= 0:
        flags.append("missing_current_price")
        score -= 0.35
    elif target is not None and target > 0:
        raw_upside_pct = ((target / current) - 1) * 100

    if source == "SectorPE_Fallback":
        flags.append("sector_pe_fallback")
        score = min(score, _param_float(params, "TARGET_MAX_FALLBACK_QUALITY"))

    if raw_upside_pct is not None:
        if raw_upside_pct >= _param_float(params, "TARGET_EXTREME_UPSIDE_PCT"):
            flags.append("extreme_upside")
            score -= 0.25
        if raw_upside_pct >= _param_float(params, "TARGET_REJECT_UPSIDE_PCT"):
            score -= 0.35
            if source == "SectorPE_Fallback":
                force_reject = True

    if forward_pe is not None and forward_pe <= 0:
        flags.append("negative_or_zero_forward_pe")
        score -= 0.35

    if current is not None and current < _param_float(params, "TARGET_LOW_PRICE"):
        flags.append("very_low_price")
        score -= 0.20

    if avg_volume is not None and avg_volume < _param_float(params, "TARGET_LOW_LIQUIDITY_AVG_VOLUME"):
        flags.append("low_liquidity")
        score -= 0.15

    stale_days = _param_int(params, "TARGET_STALE_DAYS")
    if last_updated is not None and (as_of - last_updated).days > stale_days:
        flags.append("stale_target")
        score -= 0.20

    if stock in related_context:
        flags.append("target_class_mismatch_suspected")
        flags.append("unit_or_share_class_mismatch_suspected")
        flags.append("corporate_action_check_required")
        score = min(score, 0.20)
        if raw_upside_pct is not None and raw_upside_pct >= _param_float(params, "TARGET_EXTREME_UPSIDE_PCT"):
            force_reject = True

    if historical_return_pct is not None and historical_return_pct <= _param_float(params, "TARGET_DISTRESSED_RETURN_PCT"):
        flags.append("distressed_price_action")
        score -= 0.20

    if current is not None and current < _param_float(params, "TARGET_LOW_PRICE") and raw_upside_pct is not None:
        if raw_upside_pct >= _param_float(params, "TARGET_REJECT_UPSIDE_PCT"):
            flags.append("distressed_price_action")

    score = max(0.0, min(1.0, score))
    bucket = quality_bucket(score, force_reject=force_reject)

    return {
        "target_quality_score": round(score, 4),
        "target_quality_bucket": bucket,
        "target_quality_flags": sorted(set(flags)),
        "target_quality_related": related_context.get(stock),
        "raw_upside_pct": round(raw_upside_pct, 4) if raw_upside_pct is not None else None,
    }


def calculate_adjusted_return(
    record: Dict[str, Any],
    params: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Shrink a raw forward return according to target quality confidence.

    The returned value is diagnostic/shadow data only: callers keep their
    official decision logic on the existing raw expected return until a later
    rollout phase explicitly switches the model.
    """
    params = params or {}

    raw_return_pct = _float_or_none(
        record.get(
            "raw_expected_return_pct",
            record.get("raw_upside_pct", record.get("RawExpectedReturnPct")),
        )
    )
    if raw_return_pct is None:
        raw_return_pct = 0.0

    bucket = str(
        record.get(
            "target_quality_bucket",
            record.get("TargetQualityBucket", ""),
        )
        or ""
    ).lower()
    score = _float_or_none(
        record.get(
            "target_quality_score",
            record.get("TargetQualityScore"),
        )
    )
    if score is None:
        score = 0.0 if bucket == "reject" else 1.0
    shrinkage_factor = max(0.0, min(1.0, score))
    if bucket == "reject":
        shrinkage_factor = 0.0

    cap_pct = _param_float(params, "RETURN_ADJUSTMENT_CAP_PCT")
    floor_pct = _param_float(params, "RETURN_ADJUSTMENT_FLOOR_PCT")
    capped_raw_return_pct = max(floor_pct, min(cap_pct, raw_return_pct))

    base_return_pct = _float_or_none(
        record.get("base_return_pct", record.get("BaseReturnPct"))
    )
    base_return_source = str(
        record.get("base_return_source", record.get("BaseReturnSource", "configured_base"))
        or "configured_base"
    )
    return_source = str(record.get("return_source") or "").lower()

    if base_return_pct is None:
        if bucket == "reject" and return_source != "historical":
            base_return_pct = _param_float(params, "RETURN_ADJUSTMENT_REJECT_BASE_PCT")
            base_return_source = "reject_base"
        else:
            base_return_pct = _param_float(params, "RETURN_ADJUSTMENT_BASE_PCT")
            base_return_source = "configured_base"

    max_penalty_pct = _param_float(params, "RETURN_ADJUSTMENT_UNCERTAINTY_PENALTY_PCT")
    uncertainty_penalty_pct = max_penalty_pct * (1.0 - shrinkage_factor)

    adjusted_return_pct = (
        shrinkage_factor * capped_raw_return_pct
        + (1.0 - shrinkage_factor) * base_return_pct
        - uncertainty_penalty_pct
    )

    return {
        "raw_expected_return_pct": round(raw_return_pct, 4),
        "capped_raw_return_pct": round(capped_raw_return_pct, 4),
        "base_return_pct": round(base_return_pct, 4),
        "base_return_source": base_return_source,
        "target_quality_score": round(shrinkage_factor, 4),
        "shrinkage_factor": round(shrinkage_factor, 4),
        "uncertainty_penalty_pct": round(uncertainty_penalty_pct, 4),
        "adjusted_expected_return_pct": round(adjusted_return_pct, 4),
        "adjusted_return_delta_pct": round(raw_return_pct - adjusted_return_pct, 4),
    }
