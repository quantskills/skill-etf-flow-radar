"""Liquid-ETF universe filter.

Two AND conditions (design §3.1):
  1. On scan-day T: flow_df.size >= min_size (default 2e9 = 20 亿).
  2. Trailing `lookback` trading days' mean daily amount >= min_amount (default 5e7).
"""
from __future__ import annotations

import pandas as pd


def filter_universe(
    flow_df: pd.DataFrame,
    daily_df: pd.DataFrame,
    date: str,
    min_size: float = 2e9,
    min_amount: float = 5e7,
    lookback: int = 20,
) -> tuple[list[str], pd.DataFrame]:
    """Return (sorted universe symbols, amount_T_avg20 DataFrame for those symbols).

    Args:
        flow_df: rows with `symbol, date, size` (from get_fund_etf_cr_net).
        daily_df: rows with `symbol, date, amount` (from get_fund_daily).
        date: scan day T (YYYYMMDD).
        min_size: minimum T-day size.
        min_amount: minimum trailing mean amount.
        lookback: trading days for amount average (T-lookback+1 .. T inclusive).

    Returns:
        (universe, avg_df)
          universe:  sorted list of symbols meeting both conditions.
          avg_df:    DataFrame with columns [symbol, amount_T_avg20] for those symbols.
                     Empty DataFrame with correct columns when universe is empty.
    """
    flow_t = flow_df[flow_df["date"] == date]
    size_ok = set(flow_t[flow_t["size"] >= min_size]["symbol"].unique())

    daily = daily_df[daily_df["date"] <= date].sort_values(["symbol", "date"])
    avg_rows: list[dict] = []
    amount_ok: set[str] = set()
    for symbol, g in daily.groupby("symbol", sort=False):
        window = g.tail(lookback)
        if len(window) < lookback:
            continue
        avg = window["amount"].mean()
        avg_rows.append({"symbol": symbol, "amount_T_avg20": float(avg)})
        if avg >= min_amount:
            amount_ok.add(symbol)

    universe = sorted(size_ok & amount_ok)
    if not universe:
        return [], pd.DataFrame(columns=["symbol", "amount_T_avg20"])
    avg_df = pd.DataFrame(avg_rows)
    avg_df = avg_df[avg_df["symbol"].isin(universe)].reset_index(drop=True)
    return universe, avg_df
