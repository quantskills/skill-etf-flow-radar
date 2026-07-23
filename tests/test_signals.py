"""Unit tests for scripts/signals.py — S1 net-flow Z-score."""
import json

import pandas as pd
import pytest

from scripts import signals


def _flow_row(symbol: str, date: str, net_redemption: float, size: float = 5e9) -> dict:
    return {"symbol": symbol, "date": date, "net_redemption": net_redemption, "size": size}


def _build_flow_df(symbol: str, values_by_date: list[tuple[str, float]]) -> pd.DataFrame:
    return pd.DataFrame([_flow_row(symbol, d, v) for d, v in values_by_date])


# ---------- S1 ----------

def test_s1_hit_high_z():
    # 20 baseline days of small noise (sigma ≈ 30), T = 1e8 → z massively above threshold
    dates = [f"2026070{i:02d}" for i in range(1, 22)]  # 21 fake trading days
    baseline_values = [10.0, -20.0, 30.0, -10.0, 25.0, -15.0, 5.0, 20.0, -30.0, 15.0,
                       -25.0, 10.0, 35.0, -5.0, 20.0, -10.0, 25.0, -15.0, 5.0, -20.0]
    values = list(zip(dates[:-1], baseline_values)) + [(dates[-1], 1e8)]
    df = _build_flow_df("510050.SH", values)

    hits = signals.s1_net_flow_z(df, ["510050.SH"], date=dates[-1], z_threshold=2.0, lookback=20)

    assert len(hits) == 1
    row = hits.iloc[0]
    assert row["symbol"] == "510050.SH"
    assert row["signal_type"] == "S1"
    assert row["signal_value"] > 5  # very large z
    assert row["abs_signal_value"] == pytest.approx(abs(row["signal_value"]))
    assert row["trade_date"] == dates[-1]


def test_s1_low_sigma_skip():
    dates = [f"2026070{i:02d}" for i in range(1, 22)]
    values = [(d, 0.0) for d in dates]  # T-day also zero → sigma = 0
    df = _build_flow_df("510050.SH", values)

    hits = signals.s1_net_flow_z(df, ["510050.SH"], date=dates[-1], z_threshold=2.0, lookback=20)
    assert hits.empty


def test_s1_zero_sigma_baseline_skip():
    """Baseline with no variance (sigma < epsilon) must be skipped, even if T is extreme."""
    dates = [f"2026070{i:02d}" for i in range(1, 22)]
    values = [(d, 0.0) for d in dates[:-1]] + [(dates[-1], 1e8)]
    df = _build_flow_df("510050.SH", values)

    hits = signals.s1_net_flow_z(df, ["510050.SH"], date=dates[-1], z_threshold=2.0, lookback=20)
    assert hits.empty


def test_s1_no_lookahead():
    """Changing T-day's own value must NOT change mu/sigma → z magnitude scales linearly with T value."""
    dates = [f"2026070{i:02d}" for i in range(1, 22)]
    baseline = [(d, float(i)) for i, d in enumerate(dates[:-1])]  # 0..19

    df_small = pd.DataFrame([_flow_row("X.SH", d, v) for d, v in baseline + [(dates[-1], 100.0)]])
    df_large = pd.DataFrame([_flow_row("X.SH", d, v) for d, v in baseline + [(dates[-1], 1000.0)]])

    hits_small = signals.s1_net_flow_z(df_small, ["X.SH"], dates[-1], z_threshold=0.0, lookback=20)
    hits_large = signals.s1_net_flow_z(df_large, ["X.SH"], dates[-1], z_threshold=0.0, lookback=20)

    # If T were included, sigma would differ between the two dfs and the ratio would not be exact.
    ratio_val = hits_large.iloc[0]["signal_value"] / hits_small.iloc[0]["signal_value"]
    # (1000 - mu) / (100 - mu) — with mu computed on 0..19 (fixed), ratio is a fixed constant.
    mu = sum(range(20)) / 20  # 9.5
    expected_ratio = (1000.0 - mu) / (100.0 - mu)
    assert ratio_val == pytest.approx(expected_ratio, rel=1e-9)


def test_s1_output_columns():
    dates = [f"2026070{i:02d}" for i in range(1, 22)]
    values = [(d, 0.0) for d in dates[:-1]] + [(dates[-1], 1e8)]
    df = _build_flow_df("510050.SH", values)

    hits = signals.s1_net_flow_z(df, ["510050.SH"], date=dates[-1])
    assert list(hits.columns) == signals.SIGNAL_COLUMNS
