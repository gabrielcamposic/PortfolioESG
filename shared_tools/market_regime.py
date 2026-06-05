"""Market regime diagnostics for post-peak stress detection."""

from __future__ import annotations

import math
from typing import Any, Dict, Optional

import numpy as np
import pandas as pd


DEFAULT_MARKET_REGIME_PARAMS = {
    "REGIME_BENCHMARK_TICKER": "^BVSP",
    "REGIME_LOOKBACK_3M_DAYS": 63,
    "REGIME_LOOKBACK_6M_DAYS": 126,
    "REGIME_DRAWDOWN_STRESS_PCT": 10.0,
    "REGIME_NEGATIVE_BREADTH_PCT": 60.0,
    "REGIME_DRAWDOWN_BREADTH_PCT": 45.0,
    "REGIME_ASSET_DRAWDOWN_THRESHOLD_PCT": 20.0,
    "REGIME_VOLATILITY_WATCH_PCT": 25.0,
    "REGIME_DISPERSION_WATCH_PCT": 35.0,
}


def _float_or_none(value: Any) -> Optional[float]:
    if value is None or value == "":
        return None
    try:
        numeric = float(value)
    except (TypeError, ValueError):
        return None
    return numeric if math.isfinite(numeric) else None


def _param_float(params: Dict[str, Any], key: str) -> float:
    value = _float_or_none(params.get(key))
    return float(value if value is not None else DEFAULT_MARKET_REGIME_PARAMS[key])


def _param_int(params: Dict[str, Any], key: str) -> int:
    value = _float_or_none(params.get(key))
    return int(value if value is not None else DEFAULT_MARKET_REGIME_PARAMS[key])


def _round_or_none(value: Any, digits: int = 2) -> Optional[float]:
    numeric = _float_or_none(value)
    return round(numeric, digits) if numeric is not None else None


def _window_series(series: pd.Series, window_days: int) -> pd.Series:
    clean = pd.to_numeric(series, errors="coerce").dropna()
    return clean.tail(window_days + 1)


def _return_pct(series: pd.Series, window_days: int) -> Optional[float]:
    window = _window_series(series, window_days)
    min_obs = max(20, int(window_days * 0.45))
    if len(window) < min_obs or window.iloc[0] <= 0:
        return None
    return (window.iloc[-1] / window.iloc[0] - 1.0) * 100.0


def _drawdown_from_peak_pct(series: pd.Series, window_days: int) -> Optional[float]:
    window = pd.to_numeric(series, errors="coerce").dropna().tail(window_days)
    min_obs = max(20, int(window_days * 0.45))
    if len(window) < min_obs:
        return None
    peak = window.max()
    if peak <= 0:
        return None
    return (window.iloc[-1] / peak - 1.0) * 100.0


def _annualized_volatility_pct(series: pd.Series, window_days: int) -> Optional[float]:
    window = _window_series(series, window_days)
    returns = window.pct_change().dropna()
    if len(returns) < 20:
        return None
    return float(returns.std(ddof=1) * np.sqrt(252) * 100.0)


def _column_returns_pct(prices: pd.DataFrame, window_days: int) -> pd.Series:
    returns: Dict[str, float] = {}
    min_obs = max(20, int(window_days * 0.45))
    for col in prices.columns:
        window = _window_series(prices[col], window_days)
        if len(window) >= min_obs and window.iloc[0] > 0:
            returns[str(col)] = float((window.iloc[-1] / window.iloc[0] - 1.0) * 100.0)
    return pd.Series(returns, dtype=float)


def _column_drawdowns_pct(prices: pd.DataFrame, window_days: int) -> pd.Series:
    drawdowns: Dict[str, float] = {}
    min_obs = max(20, int(window_days * 0.45))
    for col in prices.columns:
        window = pd.to_numeric(prices[col], errors="coerce").dropna().tail(window_days)
        if len(window) >= min_obs and window.max() > 0:
            drawdowns[str(col)] = float((window.iloc[-1] / window.max() - 1.0) * 100.0)
    return pd.Series(drawdowns, dtype=float)


def _benchmark_series(prices: pd.DataFrame, params: Dict[str, Any]) -> tuple[str, pd.Series, bool]:
    configured = str(params.get("REGIME_BENCHMARK_TICKER") or DEFAULT_MARKET_REGIME_PARAMS["REGIME_BENCHMARK_TICKER"])
    if configured in prices.columns:
        return configured, prices[configured], True

    candidates = [
        col for col in prices.columns
        if "BVSP" in str(col).upper() or "IBOV" in str(col).upper()
    ]
    if candidates:
        return str(candidates[0]), prices[candidates[0]], True

    universe = prices[[col for col in prices.columns if str(col).endswith(".SA")]]
    return "UNIVERSE_MEAN", universe.mean(axis=1), False


def _sector_medians(returns: pd.Series, sector_map: Optional[Dict[str, str]]) -> pd.Series:
    if not sector_map:
        return pd.Series(dtype=float)
    by_sector: Dict[str, list[float]] = {}
    for stock, value in returns.items():
        sector = sector_map.get(str(stock))
        if sector:
            by_sector.setdefault(sector, []).append(float(value))
    return pd.Series(
        {sector: float(np.median(values)) for sector, values in by_sector.items() if values},
        dtype=float,
    )


def compute_market_regime(
    prices: pd.DataFrame,
    params: Optional[Dict[str, Any]] = None,
    sector_map: Optional[Dict[str, str]] = None,
) -> Dict[str, Any]:
    """Compute market stress diagnostics from benchmark and universe prices."""
    params = params or {}
    if prices.empty:
        return {"state": "unknown", "reason": "empty_price_data"}

    clean = prices.copy()
    clean.index = pd.to_datetime(clean.index, errors="coerce")
    clean = clean[~clean.index.isna()].sort_index()
    clean = clean.apply(pd.to_numeric, errors="coerce").dropna(how="all", axis=1)
    if clean.empty:
        return {"state": "unknown", "reason": "no_numeric_price_data"}

    window_3m = _param_int(params, "REGIME_LOOKBACK_3M_DAYS")
    window_6m = _param_int(params, "REGIME_LOOKBACK_6M_DAYS")
    stress_drawdown = _param_float(params, "REGIME_DRAWDOWN_STRESS_PCT")
    stress_negative_breadth = _param_float(params, "REGIME_NEGATIVE_BREADTH_PCT")
    stress_drawdown_breadth = _param_float(params, "REGIME_DRAWDOWN_BREADTH_PCT")
    asset_drawdown_threshold = _param_float(params, "REGIME_ASSET_DRAWDOWN_THRESHOLD_PCT")
    volatility_watch = _param_float(params, "REGIME_VOLATILITY_WATCH_PCT")
    dispersion_watch = _param_float(params, "REGIME_DISPERSION_WATCH_PCT")

    benchmark_ticker, benchmark, benchmark_found = _benchmark_series(clean, params)
    benchmark = pd.to_numeric(benchmark, errors="coerce").dropna()
    universe_cols = [col for col in clean.columns if str(col).endswith(".SA")]
    universe = clean[universe_cols].dropna(how="all", axis=1)

    benchmark_return_3m = _return_pct(benchmark, window_3m)
    benchmark_return_6m = _return_pct(benchmark, window_6m)
    benchmark_drawdown_3m = _drawdown_from_peak_pct(benchmark, window_3m)
    benchmark_drawdown_6m = _drawdown_from_peak_pct(benchmark, window_6m)
    benchmark_vol = _annualized_volatility_pct(benchmark, window_3m)

    benchmark_returns = benchmark.pct_change().dropna()
    rolling_vol = benchmark_returns.rolling(window_3m).std() * np.sqrt(252) * 100.0
    rolling_vol = rolling_vol.dropna()
    vol_percentile = None
    if benchmark_vol is not None and len(rolling_vol) > 0:
        vol_percentile = float((rolling_vol < benchmark_vol).mean() * 100.0)

    returns_3m = _column_returns_pct(universe, window_3m)
    returns_6m = _column_returns_pct(universe, window_6m)
    drawdowns_6m = _column_drawdowns_pct(universe, window_6m)
    negative_3m = float((returns_3m < 0).mean() * 100.0) if len(returns_3m) else None
    negative_6m = float((returns_6m < 0).mean() * 100.0) if len(returns_6m) else None
    dd20_breadth = (
        float((drawdowns_6m <= -asset_drawdown_threshold).mean() * 100.0)
        if len(drawdowns_6m)
        else None
    )

    dispersion_3m = None
    if len(returns_3m) >= 10:
        dispersion_3m = float(returns_3m.quantile(0.90) - returns_3m.quantile(0.10))

    sector_returns = _sector_medians(returns_3m, sector_map)
    sector_median_return = float(sector_returns.median()) if len(sector_returns) else None
    worst_sector = str(sector_returns.idxmin()) if len(sector_returns) else None
    worst_sector_return = float(sector_returns.min()) if len(sector_returns) else None

    triggers = []
    if benchmark_drawdown_3m is not None and benchmark_drawdown_3m <= -stress_drawdown:
        triggers.append("benchmark_drawdown_3m")
    if benchmark_drawdown_6m is not None and benchmark_drawdown_6m <= -stress_drawdown:
        triggers.append("benchmark_drawdown_6m")
    if negative_3m is not None and negative_3m >= stress_negative_breadth:
        triggers.append("negative_breadth_3m")
    if dd20_breadth is not None and dd20_breadth >= stress_drawdown_breadth:
        triggers.append("broad_asset_drawdown")
    if benchmark_vol is not None and benchmark_vol >= volatility_watch:
        triggers.append("elevated_benchmark_volatility")
    if dispersion_3m is not None and dispersion_3m >= dispersion_watch:
        triggers.append("high_cross_sectional_dispersion")

    stress_triggers = {
        "benchmark_drawdown_3m",
        "benchmark_drawdown_6m",
        "negative_breadth_3m",
        "broad_asset_drawdown",
    }
    if any(trigger in stress_triggers for trigger in triggers):
        state = "stress"
    elif triggers:
        state = "volatile_watch"
    else:
        state = "normal"

    impact_by_state = {
        "normal": {
            "suggested_shrinkage_multiplier": 1.0,
            "suggested_hurdle_addon_pct": 0.0,
            "suggested_turnover_budget_multiplier": 1.0,
        },
        "volatile_watch": {
            "suggested_shrinkage_multiplier": 1.10,
            "suggested_hurdle_addon_pct": 0.50,
            "suggested_turnover_budget_multiplier": 0.85,
        },
        "stress": {
            "suggested_shrinkage_multiplier": 1.25,
            "suggested_hurdle_addon_pct": 1.00,
            "suggested_turnover_budget_multiplier": 0.70,
        },
    }

    peak_3m = benchmark.tail(window_3m).max() if len(benchmark.tail(window_3m)) else None
    peak_6m = benchmark.tail(window_6m).max() if len(benchmark.tail(window_6m)) else None
    as_of = clean.index.max()

    return {
        "state": state,
        "as_of": as_of.strftime("%Y-%m-%d") if pd.notna(as_of) else None,
        "benchmark_ticker": benchmark_ticker,
        "benchmark_found": benchmark_found,
        "triggers": triggers,
        "metrics": {
            "benchmark_current": _round_or_none(benchmark.iloc[-1] if len(benchmark) else None, 2),
            "benchmark_peak_3m": _round_or_none(peak_3m, 2),
            "benchmark_peak_6m": _round_or_none(peak_6m, 2),
            "benchmark_return_3m_pct": _round_or_none(benchmark_return_3m, 2),
            "benchmark_return_6m_pct": _round_or_none(benchmark_return_6m, 2),
            "benchmark_drawdown_3m_pct": _round_or_none(benchmark_drawdown_3m, 2),
            "benchmark_drawdown_6m_pct": _round_or_none(benchmark_drawdown_6m, 2),
            "benchmark_volatility_annual_pct": _round_or_none(benchmark_vol, 2),
            "benchmark_volatility_percentile": _round_or_none(vol_percentile, 2),
            "universe_negative_return_3m_pct": _round_or_none(negative_3m, 2),
            "universe_negative_return_6m_pct": _round_or_none(negative_6m, 2),
            "universe_drawdown_gt_20_pct": _round_or_none(dd20_breadth, 2),
            "cross_sectional_dispersion_3m_pct": _round_or_none(dispersion_3m, 2),
            "sector_median_return_3m_pct": _round_or_none(sector_median_return, 2),
            "worst_sector_3m": worst_sector,
            "worst_sector_return_3m_pct": _round_or_none(worst_sector_return, 2),
            "universe_count": int(len(universe.columns)),
        },
        "thresholds": {
            "drawdown_stress_pct": stress_drawdown,
            "negative_breadth_pct": stress_negative_breadth,
            "drawdown_breadth_pct": stress_drawdown_breadth,
            "asset_drawdown_threshold_pct": asset_drawdown_threshold,
            "volatility_watch_pct": volatility_watch,
            "dispersion_watch_pct": dispersion_watch,
        },
        "impact": impact_by_state[state],
    }
