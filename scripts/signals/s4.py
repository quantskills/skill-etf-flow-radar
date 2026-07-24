"""S4 — discount-premium divergence from net_redemption direction."""
from __future__ import annotations

from typing import Iterable

import pandas as pd

from ._common import SIGNAL_COLUMNS, _hit_row, empty_hits


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
                signal_value=abs(dr),
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
