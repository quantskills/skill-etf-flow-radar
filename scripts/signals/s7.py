"""S7 — consecutive K-day same-direction net flow, cumulative vs baseline abs-mean."""
from __future__ import annotations

from typing import Iterable

import pandas as pd

from ._common import SIGNAL_COLUMNS, _SIGMA_EPSILON, _hit_row, empty_hits


def s7_consec_flow(
    flow_df: pd.DataFrame,
    universe: Iterable[str],
    date: str,
    consec_days: int = 3,
    ratio_threshold: float = 2.0,
    lookback: int = 20,
) -> pd.DataFrame:
    """S7 — consecutive K-day same-direction net flow, cumulative >= ratio × baseline abs-mean.

    Baseline = `lookback` trading days immediately BEFORE the K-day window (no overlap).
    """
    universe = list(universe)
    if not universe:
        return empty_hits()

    df = flow_df[flow_df["symbol"].isin(universe)].copy()
    df = df.sort_values(["symbol", "date"])
    K = int(consec_days)
    rows: list[dict] = []

    for symbol, g in df.groupby("symbol", sort=False):
        g = g[g["date"] <= date]
        if g.empty or g.iloc[-1]["date"] != date:
            continue
        if len(g) < K + lookback:
            continue
        window = g.tail(K)
        baseline = g.iloc[-(K + lookback):-K]  # exactly `lookback` rows before the window
        vals = window["net_redemption"].to_numpy()
        if (vals > 0).all():
            direction = "inflow"
        elif (vals < 0).all():
            direction = "outflow"
        else:
            continue
        mu_abs = baseline["net_redemption"].abs().mean()
        if mu_abs is None or pd.isna(mu_abs) or mu_abs < _SIGMA_EPSILON:
            continue
        cum = float(vals.sum())
        ratio = abs(cum) / mu_abs
        if ratio < ratio_threshold:
            continue
        t_row = window.iloc[-1]
        rows.append(
            _hit_row(
                trade_date=date,
                symbol=symbol,
                signal_type="S7",
                signal_value=ratio,
                net_redemption_T=float(t_row["net_redemption"]),
                size_T=float(t_row["size"]) if "size" in t_row and pd.notna(t_row["size"]) else None,
                discount_rate_T=None,
                detail={"direction": direction, "days": K, "cum": cum, "mu_abs": float(mu_abs)},
            )
        )

    if not rows:
        return empty_hits()
    return pd.DataFrame(rows)[SIGNAL_COLUMNS]
