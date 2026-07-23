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


# ---------- S4 ----------

def _daily_row(symbol: str, date: str, discount_rate: float) -> dict:
    return {"symbol": symbol, "date": date, "discount_rate": discount_rate}


def test_s4_premium_buy():
    # 溢价 (dr<0) + 净申购 (nr>0) → premium_buy
    flow = pd.DataFrame([_flow_row("510050.SH", "20260722", 3e7)])
    daily = pd.DataFrame([_daily_row("510050.SH", "20260722", -0.005)])
    hits = signals.s4_discount_diverge(flow, daily, ["510050.SH"], date="20260722", discount_threshold=0.003)
    assert len(hits) == 1
    row = hits.iloc[0]
    assert row["signal_type"] == "S4"
    assert row["signal_value"] == pytest.approx(0.005)
    assert row["abs_signal_value"] == pytest.approx(0.005)
    detail = json.loads(row["detail_json"])
    assert detail["pattern"] == "premium_buy"
    assert row["discount_rate_T"] == pytest.approx(-0.005)


def test_s4_discount_sell():
    # 贴水 (dr>0) + 净赎回 (nr<0) → discount_sell
    flow = pd.DataFrame([_flow_row("510050.SH", "20260722", -2e7)])
    daily = pd.DataFrame([_daily_row("510050.SH", "20260722", 0.004)])
    hits = signals.s4_discount_diverge(flow, daily, ["510050.SH"], "20260722")
    assert len(hits) == 1
    detail = json.loads(hits.iloc[0]["detail_json"])
    assert detail["pattern"] == "discount_sell"


def test_s4_same_direction_no_hit():
    # 溢价 (dr<0) + 净赎回 (nr<0) → 同向，不命中
    flow = pd.DataFrame([_flow_row("510050.SH", "20260722", -3e7)])
    daily = pd.DataFrame([_daily_row("510050.SH", "20260722", -0.005)])
    hits = signals.s4_discount_diverge(flow, daily, ["510050.SH"], "20260722")
    assert hits.empty


def test_s4_below_threshold_no_hit():
    flow = pd.DataFrame([_flow_row("510050.SH", "20260722", 3e7)])
    daily = pd.DataFrame([_daily_row("510050.SH", "20260722", -0.002)])
    hits = signals.s4_discount_diverge(flow, daily, ["510050.SH"], "20260722", discount_threshold=0.003)
    assert hits.empty


def test_s4_missing_discount_row_skip():
    flow = pd.DataFrame([_flow_row("510050.SH", "20260722", 3e7)])
    daily = pd.DataFrame([_daily_row("OTHER.SZ", "20260722", -0.005)])  # no row for 510050 on T
    hits = signals.s4_discount_diverge(flow, daily, ["510050.SH"], "20260722")
    assert hits.empty


def test_s4_output_columns():
    flow = pd.DataFrame([_flow_row("510050.SH", "20260722", 3e7)])
    daily = pd.DataFrame([_daily_row("510050.SH", "20260722", -0.005)])
    hits = signals.s4_discount_diverge(flow, daily, ["510050.SH"], "20260722")
    assert list(hits.columns) == signals.SIGNAL_COLUMNS


# ---------- S7 ----------

def test_s7_all_positive_hit():
    # 20 baseline days |nr| average = 1e7; last 3 days = [3e7]*3 → sum 9e7, ratio 9
    dates = [f"2026070{i:02d}" for i in range(1, 24)]  # 23 days
    baseline = [(d, 1e7) for d in dates[:20]]           # baseline abs-mean = 1e7
    tail = [(d, 3e7) for d in dates[20:]]
    df = _build_flow_df("510050.SH", baseline + tail)

    hits = signals.s7_consec_flow(df, ["510050.SH"], date=dates[-1], consec_days=3, ratio_threshold=2.0, lookback=20)
    assert len(hits) == 1
    row = hits.iloc[0]
    assert row["signal_type"] == "S7"
    assert row["signal_value"] == pytest.approx(9.0)
    detail = json.loads(row["detail_json"])
    assert detail["direction"] == "inflow"
    assert detail["days"] == 3
    assert detail["cum"] == pytest.approx(9e7)


def test_s7_all_negative_hit():
    dates = [f"2026070{i:02d}" for i in range(1, 24)]
    baseline = [(d, 1e7) for d in dates[:20]]
    tail = [(d, -3e7) for d in dates[20:]]
    df = _build_flow_df("510050.SH", baseline + tail)

    hits = signals.s7_consec_flow(df, ["510050.SH"], date=dates[-1])
    assert len(hits) == 1
    detail = json.loads(hits.iloc[0]["detail_json"])
    assert detail["direction"] == "outflow"


def test_s7_direction_mixed_no_hit():
    dates = [f"2026070{i:02d}" for i in range(1, 24)]
    baseline = [(d, 1e7) for d in dates[:20]]
    tail = [(dates[20], 3e7), (dates[21], -3e7), (dates[22], 3e7)]
    df = _build_flow_df("510050.SH", baseline + tail)
    hits = signals.s7_consec_flow(df, ["510050.SH"], dates[-1])
    assert hits.empty


def test_s7_ratio_below_no_hit():
    # window sum = 3e7, baseline abs-mean = 1e7 → ratio 3; threshold 5 → miss
    dates = [f"2026070{i:02d}" for i in range(1, 24)]
    baseline = [(d, 1e7) for d in dates[:20]]
    tail = [(d, 1e7) for d in dates[20:]]  # 3 days at 1e7 → sum 3e7
    df = _build_flow_df("510050.SH", baseline + tail)
    hits = signals.s7_consec_flow(df, ["510050.SH"], dates[-1], consec_days=3, ratio_threshold=5.0)
    assert hits.empty


def test_s7_no_lookahead_on_baseline():
    """Baseline (mu_abs) must exclude the K-day window; changing T should not shrink mu_abs."""
    dates = [f"2026070{i:02d}" for i in range(1, 24)]
    baseline = [(d, 1e7) for d in dates[:20]]
    tail_small = [(d, 3e7) for d in dates[20:]]
    tail_large = [(dates[20], 3e7), (dates[21], 3e7), (dates[22], 1e12)]  # T is huge
    df_small = _build_flow_df("X.SH", baseline + tail_small)
    df_large = _build_flow_df("X.SH", baseline + tail_large)
    hits_small = signals.s7_consec_flow(df_small, ["X.SH"], dates[-1], consec_days=3, ratio_threshold=0.0)
    hits_large = signals.s7_consec_flow(df_large, ["X.SH"], dates[-1], consec_days=3, ratio_threshold=0.0)
    # If mu_abs included the K window, it would differ hugely between small and large;
    # ratio should differ by ~ (3e7 + 3e7 + 1e12) / (3e7 * 3) with mu_abs pinned at 1e7.
    mu_abs = 1e7
    expected_small = (3 * 3e7) / mu_abs
    expected_large = (3e7 + 3e7 + 1e12) / mu_abs
    assert hits_small.iloc[0]["signal_value"] == pytest.approx(expected_small)
    assert hits_large.iloc[0]["signal_value"] == pytest.approx(expected_large)


def test_s7_output_columns():
    dates = [f"2026070{i:02d}" for i in range(1, 24)]
    baseline = [(d, 1e7) for d in dates[:20]]
    tail = [(d, 3e7) for d in dates[20:]]
    df = _build_flow_df("510050.SH", baseline + tail)
    hits = signals.s7_consec_flow(df, ["510050.SH"], dates[-1])
    assert list(hits.columns) == signals.SIGNAL_COLUMNS
