"""ETF flow-radar signals: S1 (net-flow Z-score), S4 (discount divergence), S7 (consecutive flow).

Each signal is a pure function on user-supplied DataFrames. Zero hits => empty DataFrame with
the shared 12-column schema. All three return the same schema so `pd.concat` is safe.

Sign conventions (see design doc §2):
  - net_redemption > 0 → 净申购 (net creation / inflow to primary market)
  - discount_rate  > 0 → 贴水 (secondary price below NAV)
Both are subject to empirical calibration on first end-to-end run.
"""
from __future__ import annotations

import json
from typing import Iterable

import pandas as pd

# ---- Shared output schema (design §3.4) ----
SIGNAL_COLUMNS: list[str] = [
    "trade_date",
    "symbol",
    "name",
    "signal_type",
    "signal_value",
    "abs_signal_value",
    "net_redemption_T",
    "size_T",
    "amount_T_avg20",
    "discount_rate_T",
    "limit_hit_flag",
    "detail_json",
]


def empty_hits() -> pd.DataFrame:
    """Return an empty DataFrame carrying SIGNAL_COLUMNS (for safe concat on zero hits)."""
    return pd.DataFrame(columns=SIGNAL_COLUMNS)


def _hit_row(
    *,
    trade_date: str,
    symbol: str,
    signal_type: str,
    signal_value: float,
    net_redemption_T: float | None,
    size_T: float | None,
    discount_rate_T: float | None,
    detail: dict,
) -> dict:
    """Build one hit row conforming to SIGNAL_COLUMNS. name/amount_T_avg20/limit_hit_flag are
    filled later in radar.py after joining daily/limits data."""
    return {
        "trade_date": trade_date,
        "symbol": symbol,
        "name": "",
        "signal_type": signal_type,
        "signal_value": float(signal_value),
        "abs_signal_value": float(abs(signal_value)),
        "net_redemption_T": net_redemption_T,
        "size_T": size_T,
        "amount_T_avg20": None,
        "discount_rate_T": discount_rate_T,
        "limit_hit_flag": False,
        "detail_json": json.dumps(detail, ensure_ascii=False),
    }


# ---- S1 ----

_SIGMA_EPSILON = 1.0  # net_redemption is denominated in shares / yuan-ish; <1 means "essentially zero"


def s1_net_flow_z(
    flow_df: pd.DataFrame,
    universe: Iterable[str],
    date: str,
    z_threshold: float = 2.0,
    lookback: int = 20,
) -> pd.DataFrame:
    """S1 — Z-score of today's net_redemption vs the prior `lookback` trading days (T excluded).

    Args:
        flow_df: rows with `symbol, date, net_redemption` (extra columns ignored).
        universe: symbols to evaluate.
        date: scan day T, string YYYYMMDD.
        z_threshold: hit iff abs(z) >= z_threshold.
        lookback: number of prior trading days used as baseline (must not include T).

    Returns:
        DataFrame with SIGNAL_COLUMNS. May be empty.
    """
    universe = list(universe)
    if not universe:
        return empty_hits()

    df = flow_df[flow_df["symbol"].isin(universe)].copy()
    df = df.sort_values(["symbol", "date"])
    rows: list[dict] = []

    for symbol, g in df.groupby("symbol", sort=False):
        g = g[g["date"] <= date]
        if g.empty or g.iloc[-1]["date"] != date:
            continue  # no data on T
        history = g[g["date"] < date].tail(lookback)
        if len(history) < lookback:
            continue  # insufficient history → skip S1 (design §6)
        mu = history["net_redemption"].mean()
        sigma = history["net_redemption"].std(ddof=1)
        if sigma is None or pd.isna(sigma) or sigma < _SIGMA_EPSILON:
            continue
        t_row = g.iloc[-1]
        z = (t_row["net_redemption"] - mu) / sigma
        if abs(z) < z_threshold:
            continue
        rows.append(
            _hit_row(
                trade_date=date,
                symbol=symbol,
                signal_type="S1",
                signal_value=z,
                net_redemption_T=float(t_row["net_redemption"]),
                size_T=float(t_row["size"]) if "size" in t_row and pd.notna(t_row["size"]) else None,
                discount_rate_T=None,
                detail={
                    "mu": float(mu),
                    "sigma": float(sigma),
                    "direction": "inflow" if z > 0 else "outflow",
                },
            )
        )

    if not rows:
        return empty_hits()
    return pd.DataFrame(rows)[SIGNAL_COLUMNS]


# ---- S4 ----


def s4_discount_diverge(
    flow_df: pd.DataFrame,
    daily_df: pd.DataFrame,
    universe: Iterable[str],
    date: str,
    discount_threshold: float = 0.003,
) -> pd.DataFrame:
    """S4 — |discount_rate| >= threshold AND direction opposite to net_redemption.

    Patterns:
      premium_buy:    discount_rate < 0 (溢价) AND net_redemption > 0 (净申购)
      discount_sell:  discount_rate > 0 (贴水) AND net_redemption < 0 (净赎回)
    """
    universe = list(universe)
    if not universe:
        return empty_hits()

    flow_t = flow_df[(flow_df["date"] == date) & (flow_df["symbol"].isin(universe))]
    daily_t = daily_df[(daily_df["date"] == date) & (daily_df["symbol"].isin(universe))]
    if flow_t.empty or daily_t.empty:
        return empty_hits()

    merged = flow_t.merge(
        daily_t[["symbol", "discount_rate"]], on="symbol", how="inner", validate="one_to_one"
    )
    rows: list[dict] = []
    for _, r in merged.iterrows():
        nr = r["net_redemption"]
        dr = r["discount_rate"]
        if pd.isna(nr) or pd.isna(dr):
            continue
        if abs(dr) < discount_threshold:
            continue
        if dr * nr >= 0:  # same direction (or one is zero) → not diverging
            continue
        pattern = "premium_buy" if dr < 0 else "discount_sell"
        rows.append(
            _hit_row(
                trade_date=date,
                symbol=r["symbol"],
                signal_type="S4",
                signal_value=abs(dr),  # already ≥ 0; abs_signal_value equals signal_value
                net_redemption_T=float(nr),
                size_T=float(r["size"]) if "size" in r and pd.notna(r["size"]) else None,
                discount_rate_T=float(dr),
                detail={
                    "pattern": pattern,
                    "discount_rate": float(dr),
                    "net_redemption": float(nr),
                },
            )
        )

    if not rows:
        return empty_hits()
    return pd.DataFrame(rows)[SIGNAL_COLUMNS]
