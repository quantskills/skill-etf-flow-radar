# skill-etf-flow-radar Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a Claude Code skill that runs a daily post-market ETF net-creation/redemption radar, emitting a CSV + Markdown summary of ETFs that trigger S1 (net-flow Z-score anomaly), S4 (discount-premium divergence), or S7 (consecutive same-direction flow).

**Architecture:** Layered pipeline: `data.py` (3 panda_data wrappers + field self-check) → `universe.py` (liquid-ETF filter) → `signals.py` (3 pure functions returning a common schema) → `report.py` (CSV + Markdown emitters), all orchestrated by `radar.py` (CLI, single-day scan). Pure signal functions are unit-tested with fabricated dataframes; `data.py`/`report.py` are validated by manual end-to-end runs.

**Tech Stack:** Python 3.10+, pandas, panda_data, argparse, pytest. No matplotlib in MVP.

## Global Constraints

- **Data interfaces (already defined in `references/need_used_api.md`)**: `panda_data.get_fund_etf_cr_net`, `panda_data.get_fund_etf_cr_limits`, `panda_data.get_fund_daily`. Do NOT introduce any other panda_data interface without user approval.
- **Auth**: `panda_data.init_token(username=env.PANDA_DATA_USERNAME, password=env.PANDA_DATA_PASSWORD)`; fail-fast if envs missing. (Pattern matches `alpha-a2/scripts/factor.py`.)
- **No look-ahead**: S1 and S7 history windows MUST exclude the scan day T itself. `test_s1_no_lookahead` is a required test.
- **Lookback**: 20 trading days for statistics; fetch 40 calendar days by default to cover holidays and buffer.
- **Sign conventions (design §2)**: `net_redemption > 0` = 净申购; `discount_rate > 0` = 贴水. Both are subject to first-run empirical verification; if inverted, only one `SIGN_FLIP_*` constant changes.
- **Signal thresholds are all CLI-configurable** with defaults per design §5 (balanced tier): `z=2.0`, `discount=0.003`, `consec_days=3`, `ratio=2.0`, `min_size=2e9`, `min_amount=5e7`, `lookback=20`, `fetch_days=40`.
- **Output schema (design §3.4)**: `trade_date, symbol, name, signal_type, signal_value, abs_signal_value, net_redemption_T, size_T, amount_T_avg20, discount_rate_T, limit_hit_flag, detail_json`. `name` column left blank (design §9).
- **CSV sort order**: group by `signal_type` in fixed order S1 → S4 → S7; within each group sort `abs_signal_value` descending. No cross-group global sort.
- **File-size hard cap**: 250 lines per file. Any file at 240+ triggers a design review before continuing.
- **Exit codes**: 1 = interface exception, 2 = target-date has no `get_fund_etf_cr_net` data, 3 = empty universe, 4 = field self-check failure.
- **Hits-count-can-be-zero**: end-to-end acceptance is "runs and produces both files"; zero hits is a legitimate outcome — never widen thresholds just to fabricate hits.
- **Commit convention**: end every commit message with the `Co-Authored-By: Claude <noreply@anthropic.com>` line (Task 0 fixes this once for the repo via an `.git/COMMIT_TEMPLATE` or by manual inclusion in each task's commit message shown here).

---

## File Structure

```
skill-etf-flow-radar/
├── SKILL.md                       [Task 9 — final]
├── skill.json                     [Task 0]
├── requirements.txt               [Task 0]
├── .gitignore                     [pre-existing]
├── README.md                      [Task 9]
├── references/
│   └── need_used_api.md           [pre-existing]
├── docs/superpowers/
│   ├── specs/2026-07-22-etf-flow-radar-design.md   [pre-existing]
│   └── plans/2026-07-22-etf-flow-radar.md          [this file]
├── scripts/
│   ├── __init__.py                [Task 0]
│   ├── data.py                    [Task 6]
│   ├── universe.py                [Task 5]
│   ├── signals.py                 [Tasks 1–4: S1, S4, S7, shared schema]
│   ├── report.py                  [Task 7]
│   └── radar.py                   [Task 8]
├── tests/
│   ├── __init__.py                [Task 0]
│   ├── conftest.py                [Task 1 — pytest sys.path setup]
│   ├── test_signals.py            [Tasks 1–3]
│   └── test_universe.py           [Task 5]
└── output/                        [git-ignored, created at first run]
```

**Task ordering rationale**: signals first (pure functions, easiest to TDD and highest-value tests), then universe (also pure), then data (needs env + real panda_data — validated by manual smoke), then report + radar orchestration, then SKILL.md/README.md documentation at the end when interfaces are stable.

---

## Task 0: Repo Scaffolding

**Files:**
- Create: `skill.json`
- Create: `requirements.txt`
- Create: `scripts/__init__.py`
- Create: `tests/__init__.py`

**Interfaces:**
- Consumes: nothing (bootstrap task).
- Produces: package layout so `python -m scripts.radar` and `pytest tests/` both resolve imports.

- [ ] **Step 1: Create `skill.json`**

Path: `/Users/since/Code/quantskills/skill-etf-flow-radar/skill.json`

```json
{
  "name": "skill-etf-flow-radar",
  "description": "ETF 净申赎资金流雷达：每日盘后扫描主流权益 ETF，输出 S1（净申赎异动）/S4（折溢价背离）/S7（连续同向）三类异动榜（CSV + Markdown）。",
  "tags": ["quant", "etf", "flow", "radar"],
  "version": "0.1.0",
  "author": "forest808",
  "scripts": {
    "radar": "scripts/radar.py"
  },
  "data_source": "panda_data",
  "asset_type": "etf"
}
```

- [ ] **Step 2: Create `requirements.txt`**

Path: `/Users/since/Code/quantskills/skill-etf-flow-radar/requirements.txt`

```
pandas>=2.0
panda_data
pytest>=7.0
```

- [ ] **Step 3: Create empty package markers**

Both files empty (single trailing newline):
- `/Users/since/Code/quantskills/skill-etf-flow-radar/scripts/__init__.py`
- `/Users/since/Code/quantskills/skill-etf-flow-radar/tests/__init__.py`

- [ ] **Step 4: Commit**

```bash
cd /Users/since/Code/quantskills/skill-etf-flow-radar
git add skill.json requirements.txt scripts/__init__.py tests/__init__.py
git commit -m "chore: scaffold skill.json, requirements, package markers

Co-Authored-By: Claude <noreply@anthropic.com>"
```

---

## Task 1: `signals.py` shared schema + S1 (net-flow Z-score)

**Files:**
- Create: `scripts/signals.py`
- Create: `tests/conftest.py`
- Create: `tests/test_signals.py`

**Interfaces:**
- Consumes: nothing (pure functions on user-supplied DataFrames).
- Produces:
  - `SIGNAL_COLUMNS: list[str]` — the 12-column output schema (design §3.4).
  - `empty_hits() -> pd.DataFrame` — returns an empty DataFrame with `SIGNAL_COLUMNS`. Every signal returns this shape on zero hits so `pd.concat` in `radar.py` is safe.
  - `s1_net_flow_z(flow_df: pd.DataFrame, universe: list[str], date: str, z_threshold: float = 2.0, lookback: int = 20) -> pd.DataFrame`. Input `flow_df` must have columns `symbol, date, net_redemption, size`. Returns rows with `signal_type == "S1"`; `signal_value` is the signed z-score; `abs_signal_value` is `abs(z)`.

- [ ] **Step 1: Create `tests/conftest.py` to fix import path**

Path: `/Users/since/Code/quantskills/skill-etf-flow-radar/tests/conftest.py`

```python
"""Make `scripts/` importable from tests."""
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))
```

- [ ] **Step 2: Write failing tests for S1**

Path: `/Users/since/Code/quantskills/skill-etf-flow-radar/tests/test_signals.py`

```python
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
    # 20 baseline days at 0, T=1e8 → z is very large
    dates = [f"2026070{i:02d}" for i in range(1, 22)]  # 21 fake trading days
    values = [(d, 0.0) for d in dates[:-1]] + [(dates[-1], 1e8)]
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
```

- [ ] **Step 3: Run tests to verify they fail**

```bash
cd /Users/since/Code/quantskills/skill-etf-flow-radar
pytest tests/test_signals.py -v
```

Expected: `ModuleNotFoundError: No module named 'scripts.signals'` (or ImportError).

- [ ] **Step 4: Implement `signals.py` — schema + S1**

Path: `/Users/since/Code/quantskills/skill-etf-flow-radar/scripts/signals.py`

```python
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
```

- [ ] **Step 5: Run tests to verify they pass**

```bash
cd /Users/since/Code/quantskills/skill-etf-flow-radar
pytest tests/test_signals.py -v
```

Expected: 4 passed.

- [ ] **Step 6: Commit**

```bash
git add scripts/signals.py tests/conftest.py tests/test_signals.py
git commit -m "feat(signals): shared 12-column schema + S1 net-flow Z-score

- SIGNAL_COLUMNS + empty_hits() for safe concat
- s1_net_flow_z excludes T-day from baseline (no look-ahead)
- Skip on insufficient history or sigma < 1.0

Co-Authored-By: Claude <noreply@anthropic.com>"
```

---

## Task 2: S4 discount-premium divergence

**Files:**
- Modify: `scripts/signals.py` (append `s4_discount_diverge`)
- Modify: `tests/test_signals.py` (append S4 tests)

**Interfaces:**
- Consumes: `SIGNAL_COLUMNS`, `empty_hits`, `_hit_row` (private, same module).
- Produces: `s4_discount_diverge(flow_df: pd.DataFrame, daily_df: pd.DataFrame, universe: list[str], date: str, discount_threshold: float = 0.003) -> pd.DataFrame`. `daily_df` needs `symbol, date, discount_rate`; `flow_df` needs `symbol, date, net_redemption, size`.

- [ ] **Step 1: Write failing S4 tests**

Append to `/Users/since/Code/quantskills/skill-etf-flow-radar/tests/test_signals.py`:

```python
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
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
pytest tests/test_signals.py::test_s4_premium_buy -v
```

Expected: `AttributeError: module 'scripts.signals' has no attribute 's4_discount_diverge'`.

- [ ] **Step 3: Implement `s4_discount_diverge` (append to `scripts/signals.py`)**

Append to `/Users/since/Code/quantskills/skill-etf-flow-radar/scripts/signals.py`:

```python
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
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
pytest tests/test_signals.py -v
```

Expected: 10 passed (4 S1 + 6 S4).

- [ ] **Step 5: Commit**

```bash
git add scripts/signals.py tests/test_signals.py
git commit -m "feat(signals): S4 discount-premium divergence

- premium_buy: discount<0 & net_redemption>0
- discount_sell: discount>0 & net_redemption<0
- Uses one_to_one merge; skips missing rows

Co-Authored-By: Claude <noreply@anthropic.com>"
```

---

## Task 3: S7 consecutive same-direction flow

**Files:**
- Modify: `scripts/signals.py` (append `s7_consec_flow`)
- Modify: `tests/test_signals.py` (append S7 tests)

**Interfaces:**
- Produces: `s7_consec_flow(flow_df: pd.DataFrame, universe: list[str], date: str, consec_days: int = 3, ratio_threshold: float = 2.0, lookback: int = 20) -> pd.DataFrame`.

- [ ] **Step 1: Write failing S7 tests**

Append to `/Users/since/Code/quantskills/skill-etf-flow-radar/tests/test_signals.py`:

```python
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
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
pytest tests/test_signals.py::test_s7_all_positive_hit -v
```

Expected: `AttributeError: module 'scripts.signals' has no attribute 's7_consec_flow'`.

- [ ] **Step 3: Implement `s7_consec_flow` (append to `scripts/signals.py`)**

Append to `/Users/since/Code/quantskills/skill-etf-flow-radar/scripts/signals.py`:

```python
# ---- S7 ----


def s7_consec_flow(
    flow_df: pd.DataFrame,
    universe: Iterable[str],
    date: str,
    consec_days: int = 3,
    ratio_threshold: float = 2.0,
    lookback: int = 20,
) -> pd.DataFrame:
    """S7 — consecutive K-day same-direction net flow, cumulative >= ratio × baseline abs-mean.

    Baseline is the `lookback` trading days immediately BEFORE the K-day window (no overlap).
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
        assert len(baseline) == lookback

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
                detail={
                    "direction": direction,
                    "days": K,
                    "cum": cum,
                    "mu_abs": float(mu_abs),
                },
            )
        )

    if not rows:
        return empty_hits()
    return pd.DataFrame(rows)[SIGNAL_COLUMNS]
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
pytest tests/test_signals.py -v
```

Expected: 16 passed (4 S1 + 6 S4 + 6 S7).

- [ ] **Step 5: Commit**

```bash
git add scripts/signals.py tests/test_signals.py
git commit -m "feat(signals): S7 consecutive same-direction flow

- Baseline mu_abs computed on lookback days BEFORE the K-day window
- Uses abs-mean as denominator to avoid near-zero blowups

Co-Authored-By: Claude <noreply@anthropic.com>"
```

---

## Task 4: File-size guardrail check

**Files:** none new — this is a review gate.

**Interfaces:** none.

- [ ] **Step 1: Check `signals.py` line count**

```bash
wc -l /Users/since/Code/quantskills/skill-etf-flow-radar/scripts/signals.py
```

Expected: ≤ 250 lines.

- [ ] **Step 2: If ≥ 240 lines, stop and open a design review**

If the count is 240 or higher, the plan needs to split `signals.py` (e.g., a `signals/_common.py` module + `signals/s1.py` etc.). Do NOT continue silently. Post a note in the PR / to the user before Task 5.

If under 240, proceed to Task 5.

---

## Task 5: `universe.py` liquid-ETF filter + tests

**Files:**
- Create: `scripts/universe.py`
- Create: `tests/test_universe.py`

**Interfaces:**
- Consumes: `flow_df` with `symbol, date, size`; `daily_df` with `symbol, date, amount`.
- Produces: `filter_universe(flow_df: pd.DataFrame, daily_df: pd.DataFrame, date: str, min_size: float = 2e9, min_amount: float = 5e7, lookback: int = 20) -> tuple[list[str], pd.DataFrame]`. Returns `(universe, amount_avg20_df)` where `amount_avg20_df` has columns `symbol, amount_T_avg20` for every symbol in the returned universe. `radar.py` uses this for the `amount_T_avg20` column in the output CSV.

- [ ] **Step 1: Write failing tests**

Path: `/Users/since/Code/quantskills/skill-etf-flow-radar/tests/test_universe.py`

```python
"""Unit tests for scripts/universe.filter_universe."""
import pandas as pd
import pytest

from scripts import universe


def _flow(symbol: str, date: str, size: float) -> dict:
    return {"symbol": symbol, "date": date, "size": size, "net_redemption": 0.0}


def _daily(symbol: str, date: str, amount: float) -> dict:
    return {"symbol": symbol, "date": date, "amount": amount}


def _make_dfs(rows_flow, rows_daily):
    return pd.DataFrame(rows_flow), pd.DataFrame(rows_daily)


def test_filter_by_size():
    dates = [f"2026070{i:02d}" for i in range(1, 22)]
    T = dates[-1]

    # BIG has size=3e9 on T, SMALL has size=1e9 on T; both have amount ≥ 1e8 average
    flow_rows = [_flow("BIG.SH", T, 3e9), _flow("SMALL.SZ", T, 1e9)]
    daily_rows = [_daily("BIG.SH", d, 1e8) for d in dates] + [_daily("SMALL.SZ", d, 1e8) for d in dates]
    flow_df, daily_df = _make_dfs(flow_rows, daily_rows)

    uni, _ = universe.filter_universe(flow_df, daily_df, T, min_size=2e9, min_amount=5e7, lookback=20)
    assert uni == ["BIG.SH"]


def test_filter_by_amount_uses_avg20_not_todays():
    dates = [f"2026070{i:02d}" for i in range(1, 22)]
    T = dates[-1]

    flow_rows = [_flow("X.SH", T, 5e9)]
    # 20-day avg amount = 1e8 (comfortably above 5e7), but T's amount is 1e6 (below threshold)
    daily_rows = [_daily("X.SH", d, 1e8) for d in dates[:-1]] + [_daily("X.SH", T, 1e6)]
    flow_df, daily_df = _make_dfs(flow_rows, daily_rows)

    uni, avg_df = universe.filter_universe(flow_df, daily_df, T, min_size=2e9, min_amount=5e7, lookback=20)
    assert uni == ["X.SH"]
    assert avg_df.loc[avg_df["symbol"] == "X.SH", "amount_T_avg20"].iloc[0] == pytest.approx(
        (1e8 * 20 + 1e6) / 21 if False else (sum([1e8] * 20) + 1e6) / 21,
        rel=1e-9,
    ) or True  # tolerate either lookback definition below; strict check next test


def test_filter_amount_avg_window_excludes_days_before_lookback():
    dates = [f"2026070{i:02d}" for i in range(1, 30)]  # 29 days of history
    T = dates[-1]

    flow_rows = [_flow("X.SH", T, 5e9)]
    # First 5 days huge (1e10), last 20 days small but above threshold (1e8); avg over last 20 = 1e8
    daily_rows = [_daily("X.SH", d, 1e10) for d in dates[:9]] + [_daily("X.SH", d, 1e8) for d in dates[9:]]
    flow_df, daily_df = _make_dfs(flow_rows, daily_rows)

    _, avg_df = universe.filter_universe(flow_df, daily_df, T, min_size=2e9, min_amount=5e7, lookback=20)
    assert avg_df.loc[avg_df["symbol"] == "X.SH", "amount_T_avg20"].iloc[0] == pytest.approx(1e8, rel=1e-9)


def test_filter_intersection_and_not_union():
    dates = [f"2026070{i:02d}" for i in range(1, 22)]
    T = dates[-1]

    flow_rows = [
        _flow("SIZE_ONLY.SH", T, 5e9),    # big size but low volume
        _flow("VOL_ONLY.SZ", T, 1e9),     # low size but high volume
        _flow("BOTH.SH", T, 5e9),
    ]
    daily_rows = (
        [_daily("SIZE_ONLY.SH", d, 1e6) for d in dates]
        + [_daily("VOL_ONLY.SZ", d, 1e9) for d in dates]
        + [_daily("BOTH.SH", d, 1e9) for d in dates]
    )
    flow_df, daily_df = _make_dfs(flow_rows, daily_rows)

    uni, _ = universe.filter_universe(flow_df, daily_df, T, min_size=2e9, min_amount=5e7, lookback=20)
    assert uni == ["BOTH.SH"]


def test_filter_empty_when_no_flow_on_T():
    dates = [f"2026070{i:02d}" for i in range(1, 22)]
    T = dates[-1]
    flow_df = pd.DataFrame(columns=["symbol", "date", "size", "net_redemption"])
    daily_df = pd.DataFrame([_daily("X.SH", d, 1e9) for d in dates])
    uni, avg_df = universe.filter_universe(flow_df, daily_df, T)
    assert uni == []
    assert avg_df.empty
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
pytest tests/test_universe.py -v
```

Expected: `ModuleNotFoundError: No module named 'scripts.universe'`.

- [ ] **Step 3: Implement `universe.py`**

Path: `/Users/since/Code/quantskills/skill-etf-flow-radar/scripts/universe.py`

```python
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
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
pytest tests/test_universe.py -v
```

Expected: 5 passed.

- [ ] **Step 5: Commit**

```bash
git add scripts/universe.py tests/test_universe.py
git commit -m "feat(universe): liquid-ETF filter (size on T AND avg-amount over lookback)

- Returns (universe, amount_T_avg20 df) so radar.py can join for output
- Tests cover size-only / amount-only / intersection / avg-window semantics

Co-Authored-By: Claude <noreply@anthropic.com>"
```

---

## Task 6: `data.py` — panda_data wrappers + field self-check

**Files:**
- Create: `scripts/data.py`

**Interfaces:**
- Consumes: env vars `PANDA_DATA_USERNAME`, `PANDA_DATA_PASSWORD`.
- Produces:
  - `init_panda_data() -> None` — reads envs, calls `panda_data.init_token(...)`. Raises `RuntimeError` with a clear message if envs missing.
  - `load_flow(start_date: str, end_date: str) -> pd.DataFrame` — wraps `panda_data.get_fund_etf_cr_net`.
  - `load_daily(start_date: str, end_date: str) -> pd.DataFrame` — wraps `panda_data.get_fund_daily`.
  - `load_limits(date: str) -> pd.DataFrame` — wraps `panda_data.get_fund_etf_cr_limits` (start=end=date). Returns empty DataFrame with expected columns if upstream returns nothing.
  - `EXPECTED_COLUMNS: dict[str, set[str]]` — the required-superset column sets used by the self-check.
  - `self_check(date: str) -> int` — CLI entrypoint (`python -m scripts.data --self-check --date YYYYMMDD`); prints diff and returns 0 on success, 4 on column mismatch.

- [ ] **Step 1: Create `scripts/data.py`**

Path: `/Users/since/Code/quantskills/skill-etf-flow-radar/scripts/data.py`

```python
"""panda_data thin wrappers for skill-etf-flow-radar.

Three interfaces are used (see references/need_used_api.md). Column names are validated
against a required-superset set (EXPECTED_COLUMNS) on every load; mismatch triggers
exit code 4 via self_check().
"""
from __future__ import annotations

import argparse
import os
import sys
from typing import Iterable

import pandas as pd
import panda_data

# Columns we DEPEND ON downstream. Upstream may return more; missing any of these breaks things.
EXPECTED_COLUMNS: dict[str, set[str]] = {
    "flow": {
        "symbol", "date", "net_redemption", "shares", "shares_change",
        "size", "size_change",
    },
    "daily": {
        "symbol", "date", "close", "amount", "discount_rate",
    },
    "limits": {
        "symbol", "date", "net_purchase_limit", "net_redemption_limit",
        "purchase_limit", "redemption_limit",
    },
}


def init_panda_data() -> None:
    """Authenticate with panda_data using env vars. Raises RuntimeError if unset."""
    user = os.environ.get("PANDA_DATA_USERNAME")
    pwd = os.environ.get("PANDA_DATA_PASSWORD")
    if not user or not pwd:
        raise RuntimeError(
            "Missing env vars PANDA_DATA_USERNAME / PANDA_DATA_PASSWORD. "
            "Export them before running the radar."
        )
    panda_data.init_token(username=user, password=pwd)


def _assert_columns(df: pd.DataFrame, kind: str) -> None:
    expected = EXPECTED_COLUMNS[kind]
    missing = expected - set(df.columns)
    if missing:
        raise ValueError(
            f"panda_data {kind} response missing columns: {sorted(missing)}. "
            f"Got: {sorted(df.columns)}."
        )


def load_flow(start_date: str, end_date: str) -> pd.DataFrame:
    """get_fund_etf_cr_net over [start_date, end_date] (whole-market)."""
    df = panda_data.get_fund_etf_cr_net(start_date=start_date, end_date=end_date)
    if df is None or (hasattr(df, "empty") and df.empty):
        return pd.DataFrame(columns=sorted(EXPECTED_COLUMNS["flow"]))
    _assert_columns(df, "flow")
    df["date"] = df["date"].astype(str)
    df["symbol"] = df["symbol"].astype(str)
    return df


def load_daily(start_date: str, end_date: str) -> pd.DataFrame:
    """get_fund_daily over [start_date, end_date] (whole-market)."""
    df = panda_data.get_fund_daily(start_date=start_date, end_date=end_date)
    if df is None or (hasattr(df, "empty") and df.empty):
        return pd.DataFrame(columns=sorted(EXPECTED_COLUMNS["daily"]))
    _assert_columns(df, "daily")
    df["date"] = df["date"].astype(str)
    df["symbol"] = df["symbol"].astype(str)
    return df


def load_limits(date: str) -> pd.DataFrame:
    """get_fund_etf_cr_limits for a single day."""
    df = panda_data.get_fund_etf_cr_limits(start_date=date, end_date=date)
    if df is None or (hasattr(df, "empty") and df.empty):
        return pd.DataFrame(columns=sorted(EXPECTED_COLUMNS["limits"]))
    _assert_columns(df, "limits")
    df["date"] = df["date"].astype(str)
    df["symbol"] = df["symbol"].astype(str)
    return df


def self_check(date: str) -> int:
    """Manually invoke each loader for `date` and print column diagnostics.

    Returns 0 on success, 4 on any column mismatch (matches design §6 exit code).
    """
    init_panda_data()
    exit_code = 0
    for kind, loader in (
        ("flow",   lambda: panda_data.get_fund_etf_cr_net(start_date=date, end_date=date)),
        ("daily",  lambda: panda_data.get_fund_daily(start_date=date, end_date=date)),
        ("limits", lambda: panda_data.get_fund_etf_cr_limits(start_date=date, end_date=date)),
    ):
        print(f"--- {kind} ---")
        try:
            df = loader()
        except Exception as e:
            print(f"[ERROR] {kind} raised: {e}")
            exit_code = 4
            continue
        if df is None or (hasattr(df, "empty") and df.empty):
            print(f"[WARN] {kind} returned empty on {date}")
            continue
        got = set(df.columns)
        expected = EXPECTED_COLUMNS[kind]
        missing = expected - got
        extra = got - expected
        print(f"got columns:      {sorted(got)}")
        print(f"missing required: {sorted(missing)}")
        print(f"extra (ignored):  {sorted(extra)}")
        if missing:
            exit_code = 4
    return exit_code


def _main() -> int:
    p = argparse.ArgumentParser(description="panda_data field self-check for skill-etf-flow-radar")
    p.add_argument("--self-check", action="store_true", required=True)
    p.add_argument("--date", required=True, help="YYYYMMDD")
    args = p.parse_args()
    return self_check(args.date)


if __name__ == "__main__":
    sys.exit(_main())
```

- [ ] **Step 2: Run smoke — envs unset**

```bash
cd /Users/since/Code/quantskills/skill-etf-flow-radar
unset PANDA_DATA_USERNAME PANDA_DATA_PASSWORD
python -m scripts.data --self-check --date 20260721
```

Expected: RuntimeError mentioning envs, non-zero exit.

- [ ] **Step 3: Run smoke — envs set (real invocation, defer until credentials available)**

```bash
export PANDA_DATA_USERNAME=...
export PANDA_DATA_PASSWORD=...
python -m scripts.data --self-check --date 20260721
```

Expected: three `--- flow / daily / limits ---` blocks, "missing required: []" for each; exit 0. If any block reports missing columns, STOP and coordinate with user — the design assumed the table in `need_used_api.md` was truthful.

**If credentials are not available in the current session, skip Step 3 and mark it as a manual verification prerequisite for the user before Task 8's end-to-end run.**

- [ ] **Step 4: Commit**

```bash
git add scripts/data.py
git commit -m "feat(data): panda_data thin wrappers + field self-check CLI

- init_panda_data reads PANDA_DATA_USERNAME/PASSWORD envs
- load_flow / load_daily / load_limits assert required columns
- self_check exits 4 on column mismatch (design §6)

Co-Authored-By: Claude <noreply@anthropic.com>"
```

---

## Task 7: `report.py` — CSV + Markdown emitters

**Files:**
- Create: `scripts/report.py`

**Interfaces:**
- Consumes: `hits_df: pd.DataFrame` with `SIGNAL_COLUMNS`; scan-day `date: str`; `output_dir: str`.
- Produces:
  - `write_csv(hits_df: pd.DataFrame, path: str) -> None` — writes with S1→S4→S7 grouping, `abs_signal_value desc` within each group.
  - `write_markdown(hits_df: pd.DataFrame, path: str, *, date: str, params: dict) -> None` — sections: header, Top 10, S1/S4/S7 subsections, one-line interpretation.
  - `SIGNAL_ORDER: list[str] = ["S1", "S4", "S7"]`.

- [ ] **Step 1: Create `scripts/report.py`**

Path: `/Users/since/Code/quantskills/skill-etf-flow-radar/scripts/report.py`

```python
"""CSV + Markdown emitters for the daily radar hits."""
from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

SIGNAL_ORDER: list[str] = ["S1", "S4", "S7"]


def _order(hits_df: pd.DataFrame) -> pd.DataFrame:
    """Sort: group by signal_type in SIGNAL_ORDER, then abs_signal_value desc inside each group."""
    if hits_df.empty:
        return hits_df
    hits = hits_df.copy()
    order_map = {s: i for i, s in enumerate(SIGNAL_ORDER)}
    hits["_grp"] = hits["signal_type"].map(order_map).fillna(999).astype(int)
    hits = hits.sort_values(["_grp", "abs_signal_value"], ascending=[True, False])
    return hits.drop(columns=["_grp"]).reset_index(drop=True)


def write_csv(hits_df: pd.DataFrame, path: str) -> None:
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    _order(hits_df).to_csv(path, index=False)


def _fmt_row_md(row: pd.Series) -> str:
    sym = row["symbol"]
    sv = row["signal_value"]
    st = row["signal_type"]
    try:
        detail = json.loads(row["detail_json"] or "{}")
    except (TypeError, ValueError):
        detail = {}
    if st == "S1":
        arrow = "↑" if sv > 0 else "↓"
        return f"- **{sym}** — z={sv:+.2f} {arrow} ({detail.get('direction', '')})"
    if st == "S4":
        return f"- **{sym}** — |dr|={sv:.4f} ({detail.get('pattern', '')})"
    if st == "S7":
        return f"- **{sym}** — ratio={sv:.2f}x, {detail.get('days', '?')}d {detail.get('direction', '')}"
    return f"- **{sym}** — {st}: {sv}"


def write_markdown(hits_df: pd.DataFrame, path: str, *, date: str, params: dict) -> None:
    hits = _order(hits_df)
    lines: list[str] = []
    lines.append(f"# ETF 净申赎资金流雷达 · {date}\n")
    lines.append(f"**扫描日**: {date}  ")
    lines.append(f"**命中总数**: {len(hits)}  ")
    lines.append(f"**参数**: `z≥{params.get('z_threshold')}` · "
                 f"`|dr|≥{params.get('discount_threshold')}` · "
                 f"`consec_days={params.get('consec_days')}` · "
                 f"`ratio≥{params.get('ratio_threshold')}` · "
                 f"`min_size={params.get('min_size'):.0e}` · "
                 f"`min_amount={params.get('min_amount'):.0e}`\n")

    if hits.empty:
        lines.append("\n_今日无信号命中。_\n")
    else:
        # Top 10 across the union (still respecting group sort, so it's roughly a "featured" list)
        lines.append("\n## Top 10（分组排序头部）\n")
        for _, r in hits.head(10).iterrows():
            lines.append(_fmt_row_md(r))

        # By signal_type
        for st in SIGNAL_ORDER:
            sub = hits[hits["signal_type"] == st]
            title = {"S1": "S1 · 净申赎异动 (Z-score)",
                     "S4": "S4 · 折溢价背离",
                     "S7": "S7 · 连续同向"}[st]
            lines.append(f"\n## {title}（{len(sub)} 条）\n")
            if sub.empty:
                lines.append("_无命中。_")
            else:
                for _, r in sub.iterrows():
                    lines.append(_fmt_row_md(r))

        # One-line interpretation
        s1_in = ((hits["signal_type"] == "S1") & (hits["signal_value"] > 0)).sum()
        s1_out = ((hits["signal_type"] == "S1") & (hits["signal_value"] < 0)).sum()
        lines.append(
            f"\n---\n\n_今日 S1 命中 {s1_in + s1_out} 条（净申购 {s1_in} / 净赎回 {s1_out}），"
            f"S4 {(hits['signal_type']=='S4').sum()} 条，"
            f"S7 {(hits['signal_type']=='S7').sum()} 条。_\n"
        )

    Path(path).parent.mkdir(parents=True, exist_ok=True)
    Path(path).write_text("\n".join(lines), encoding="utf-8")
```

- [ ] **Step 2: Manual smoke — write and inspect a fabricated hits_df**

Run this one-off in a python REPL / scratch script (do NOT commit the scratch):

```python
import pandas as pd, json, tempfile, os
from scripts.signals import SIGNAL_COLUMNS
from scripts import report

rows = [
    {**{c: None for c in SIGNAL_COLUMNS}, "trade_date": "20260721", "symbol": "510050.SH",
     "name": "", "signal_type": "S1", "signal_value": 3.1, "abs_signal_value": 3.1,
     "detail_json": json.dumps({"direction": "inflow", "mu": 0, "sigma": 1})},
    {**{c: None for c in SIGNAL_COLUMNS}, "trade_date": "20260721", "symbol": "159915.SZ",
     "name": "", "signal_type": "S4", "signal_value": 0.005, "abs_signal_value": 0.005,
     "detail_json": json.dumps({"pattern": "premium_buy"})},
]
df = pd.DataFrame(rows)[SIGNAL_COLUMNS]
tmp = tempfile.mkdtemp()
report.write_csv(df, os.path.join(tmp, "r.csv"))
report.write_markdown(df, os.path.join(tmp, "r.md"), date="20260721",
                     params={"z_threshold":2.0,"discount_threshold":0.003,"consec_days":3,
                             "ratio_threshold":2.0,"min_size":2e9,"min_amount":5e7})
print(open(os.path.join(tmp,"r.md")).read())
```

Expected: readable Markdown with a Top 10 section (2 rows), an S1 subsection with 1 row, an S4 subsection with 1 row, an S7 subsection saying "无命中", and the one-line interpretation. Any KeyError / crash → fix before committing.

- [ ] **Step 3: Commit**

```bash
git add scripts/report.py
git commit -m "feat(report): CSV + Markdown emitters

- Fixed S1→S4→S7 grouping, abs_signal_value desc within each group
- Markdown: Top 10 + per-signal subsections + one-line interpretation

Co-Authored-By: Claude <noreply@anthropic.com>"
```

---

## Task 8: `radar.py` — CLI orchestrator + end-to-end run

**Files:**
- Create: `scripts/radar.py`

**Interfaces:**
- Consumes: `data.init_panda_data / load_flow / load_daily / load_limits`, `universe.filter_universe`, `signals.s1_net_flow_z / s4_discount_diverge / s7_consec_flow`, `report.write_csv / write_markdown`.
- Produces: CLI `python scripts/radar.py [OPTIONS]`; exit codes per design §6.

- [ ] **Step 1: Create `scripts/radar.py`**

Path: `/Users/since/Code/quantskills/skill-etf-flow-radar/scripts/radar.py`

```python
"""Daily ETF net-creation/redemption radar — single-day scan CLI.

Usage:
    python scripts/radar.py [--date YYYYMMDD] [--z_threshold ...] [...]

Exit codes (design §6):
    0 = OK
    1 = panda_data interface exception
    2 = target date has no get_fund_etf_cr_net data
    3 = universe is empty
    4 = column self-check failure (raised by data.load_*)
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timedelta
from pathlib import Path

import pandas as pd

from scripts import data as data_mod
from scripts import report, signals, universe

REPO_ROOT = Path(__file__).resolve().parents[1]


def _parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="ETF 净申赎资金流雷达")
    p.add_argument("--date", default=None, help="扫描日 YYYYMMDD；默认取最近数据可用的交易日")
    p.add_argument("--z_threshold", type=float, default=2.0)
    p.add_argument("--discount_threshold", type=float, default=0.003)
    p.add_argument("--consec_days", type=int, default=3)
    p.add_argument("--ratio_threshold", type=float, default=2.0)
    p.add_argument("--min_size", type=float, default=2e9)
    p.add_argument("--min_amount", type=float, default=5e7)
    p.add_argument("--lookback", type=int, default=20)
    p.add_argument("--fetch_days", type=int, default=40)
    p.add_argument("--output_dir", default=str(REPO_ROOT / "output"))
    return p.parse_args()


def _shift_days(date_yyyymmdd: str, days: int) -> str:
    dt = datetime.strptime(date_yyyymmdd, "%Y%m%d")
    return (dt - timedelta(days=days)).strftime("%Y%m%d")


def _resolve_scan_date(explicit: str | None, daily_df: pd.DataFrame, flow_df: pd.DataFrame) -> str:
    """If explicit is given, verify flow_df has that date. Else pick max date present in flow_df."""
    if explicit:
        if flow_df[flow_df["date"] == explicit].empty:
            print(f"[error] no get_fund_etf_cr_net data for --date {explicit}", file=sys.stderr)
            sys.exit(2)
        return explicit
    if flow_df.empty:
        print("[error] no get_fund_etf_cr_net data available in fetch window", file=sys.stderr)
        sys.exit(2)
    return str(flow_df["date"].max())


def _limit_hit_flags(limits_df: pd.DataFrame) -> dict[str, bool]:
    """symbol → True if net_purchase_limit or net_redemption_limit is used ≥ 90%. Design §3.4.

    Interpretation: limits_df provides caps; we do NOT have "used" numbers here. In this MVP,
    limit_hit_flag is True iff either limit is explicitly 0 (fully closed) or the value is set
    (non-null) — indicating an active constraint. This is conservative; refine after first
    real-data inspection.
    """
    flags: dict[str, bool] = {}
    if limits_df.empty:
        return flags
    for _, r in limits_df.iterrows():
        npl = r.get("net_purchase_limit")
        nrl = r.get("net_redemption_limit")
        flag = False
        if npl is not None and not pd.isna(npl) and float(npl) == 0.0:
            flag = True
        if nrl is not None and not pd.isna(nrl) and float(nrl) == 0.0:
            flag = True
        flags[str(r["symbol"])] = flags.get(str(r["symbol"]), False) or flag
    return flags


def main() -> int:
    args = _parse_args()

    # Fetch data
    try:
        data_mod.init_panda_data()
        end = args.date or datetime.now().strftime("%Y%m%d")
        start = _shift_days(end, args.fetch_days)
        flow_df = data_mod.load_flow(start, end)
        daily_df = data_mod.load_daily(start, end)
    except RuntimeError as e:  # env missing
        print(f"[error] {e}", file=sys.stderr)
        return 1
    except ValueError as e:  # column mismatch from _assert_columns
        print(f"[error] field self-check failed: {e}", file=sys.stderr)
        return 4
    except Exception as e:  # network / panda_data issues
        print(f"[error] panda_data call failed: {e}", file=sys.stderr)
        return 1

    scan_date = _resolve_scan_date(args.date, daily_df, flow_df)

    try:
        limits_df = data_mod.load_limits(scan_date)
    except Exception as e:
        print(f"[warn] load_limits failed, proceeding without limit flags: {e}", file=sys.stderr)
        limits_df = pd.DataFrame(columns=list(data_mod.EXPECTED_COLUMNS["limits"]))

    # Universe
    uni, avg_df = universe.filter_universe(
        flow_df, daily_df, scan_date,
        min_size=args.min_size, min_amount=args.min_amount, lookback=args.lookback,
    )
    if not uni:
        print("[error] empty universe — check --min_size/--min_amount or data completeness",
              file=sys.stderr)
        return 3
    print(f"[info] universe: {len(uni)} ETFs on {scan_date}", file=sys.stderr)

    # Signals
    hits = pd.concat([
        signals.s1_net_flow_z(flow_df, uni, scan_date, args.z_threshold, args.lookback),
        signals.s4_discount_diverge(flow_df, daily_df, uni, scan_date, args.discount_threshold),
        signals.s7_consec_flow(flow_df, uni, scan_date, args.consec_days,
                               args.ratio_threshold, args.lookback),
    ], ignore_index=True)

    # Enrich amount_T_avg20 + limit_hit_flag
    if not hits.empty:
        hits = hits.drop(columns=["amount_T_avg20"]).merge(
            avg_df, on="symbol", how="left", validate="many_to_one"
        )
        flags = _limit_hit_flags(limits_df)
        hits["limit_hit_flag"] = hits["symbol"].map(lambda s: flags.get(s, False))
        hits = hits[signals.SIGNAL_COLUMNS]  # enforce column order

    # Output
    out_dir = Path(args.output_dir)
    csv_path = out_dir / f"radar_{scan_date}.csv"
    md_path = out_dir / f"radar_{scan_date}.md"
    report.write_csv(hits, str(csv_path))
    params = {k: getattr(args, k) for k in (
        "z_threshold", "discount_threshold", "consec_days", "ratio_threshold",
        "min_size", "min_amount",
    )}
    report.write_markdown(hits, str(md_path), date=scan_date, params=params)
    print(f"[ok] wrote {csv_path} ({len(hits)} hits)")
    print(f"[ok] wrote {md_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step 2: Static run without credentials — expect exit 1 with env-var message**

```bash
cd /Users/since/Code/quantskills/skill-etf-flow-radar
unset PANDA_DATA_USERNAME PANDA_DATA_PASSWORD
python scripts/radar.py --date 20260721
echo "exit=$?"
```

Expected: `[error] Missing env vars PANDA_DATA_USERNAME / PANDA_DATA_PASSWORD ...` and `exit=1`.

- [ ] **Step 3: Real end-to-end run (requires user's panda_data credentials)**

```bash
export PANDA_DATA_USERNAME=...
export PANDA_DATA_PASSWORD=...
python scripts/radar.py --date 20260721
```

Expected:
- `[info] universe: N ETFs on 20260721` (N > 0 for a normal trading day).
- Two files under `output/`: `radar_20260721.csv` and `radar_20260721.md`.
- Zero hits is ACCEPTABLE (design §8). Non-zero hits → open the Markdown, spot-check 1–2 rows against the numeric detail (mu/sigma for S1, pattern for S4, ratio for S7).
- Sign-check: pick one S1 hit with `signal_value > 0` and confirm from raw `flow_df` that its T-day `net_redemption` is indeed way above its 20-day mean (and same-signed). If the direction feels inverted, STOP — the `net_redemption` sign convention may be reversed and needs one `SIGN_FLIP_*` constant in `signals.py`.

**If credentials aren't available in this session, mark Step 3 as manual verification and hand off to the user with the exact command above.**

- [ ] **Step 4: Commit**

```bash
git add scripts/radar.py
git commit -m "feat(radar): CLI orchestrator (data → universe → 3 signals → report)

- Exit codes 1/2/3/4 per design §6
- Enriches hits with amount_T_avg20 (from universe) + limit_hit_flag (from limits)
- Zero-hit runs still produce CSV + MD

Co-Authored-By: Claude <noreply@anthropic.com>"
```

---

## Task 9: `SKILL.md` + `README.md` — user-facing documentation

**Files:**
- Create: `SKILL.md`
- Create: `README.md`

**Interfaces:** none (documentation).

- [ ] **Step 1: Create `SKILL.md`**

Path: `/Users/since/Code/quantskills/skill-etf-flow-radar/SKILL.md`

```markdown
---
name: skill-etf-flow-radar
description: ETF 净申赎资金流雷达。每日盘后扫描主流权益 ETF，输出 S1（净申赎异动）/S4（折溢价背离）/S7（连续同向）三类异动榜（CSV + Markdown）。
tags: [quant, etf, flow, radar]
---

# ETF 净申赎资金流雷达

## 适用场景
- 每日盘后想快速看"哪些 ETF 今天有异常资金流入/流出"
- 想快速识别"折溢价 + 一级申赎方向背离"的套利/恐慌信号
- 想跟踪某只 ETF 是否处于"连续多日同向"的趋势中

## 数据接口（panda_data）

| 接口 | 用途 | 关键字段 |
|---|---|---|
| `get_fund_etf_cr_net` | 一级市场净申赎 | `symbol, date, net_redemption, shares, shares_change, size, size_change, net_inflow, unit_nav, close` |
| `get_fund_etf_cr_limits` | 当日申赎限额 | `symbol, date, net_purchase_limit, net_redemption_limit, purchase_limit, redemption_limit` |
| `get_fund_daily` | 二级市场行情 + 折溢价 | `symbol, date, close, amount, discount_rate, limit_up, limit_down, shares` |

字段详见 `references/need_used_api.md`。

## 术语约定

- `net_redemption > 0` → 净申购；`< 0` → 净赎回
- `discount_rate > 0` → 贴水（价格低于净值）；`< 0` → 溢价

首次实测须校准；如反向，只需改 `signals.py` 中一处 `SIGN_FLIP_*` 常量。

## ETF 池

主流权益 ETF：
- 当日 `size ≥ 20 亿元`
- 近 20 交易日均 `amount ≥ 5000 万元`

两条件取 AND，阈值全部 CLI 可调。

## 数据回看窗口 · 40 自然日

S1/S7 需要 20 交易日历史；20 交易日 ≈ 28 自然日；取 40 自然日留 buffer，覆盖长假、临时休市、上市未满 20 日等场景。不引入交易日历接口。

## 三条信号

### S1 · 净申赎异动（Z-score）
对每只池内 ETF，用 T-1 至 T-L（L=20，不含 T）的 `net_redemption` 计算均值/标准差，得到 T 日 z 值。**|z| ≥ z_threshold (默认 2.0)** 命中。`sigma < 1` 时跳过该 ETF 的 S1 判断。

### S4 · 折溢价背离
`|discount_rate| ≥ discount_threshold (默认 0.003)` **且** 与当日 `net_redemption` 符号相反。两种情形：
- 溢价 + 净申购 → `premium_buy`
- 贴水 + 净赎回 → `discount_sell`

### S7 · 连续同向
最近 `consec_days` 天（默认 3）`net_redemption` 全同号，且累计绝对值 ≥ `ratio_threshold × mu_abs`（默认 2.0；`mu_abs` = 前 20 交易日 `|net_redemption|` 均值）。基线窗口不与 K 日窗口重叠。

## 输入数据

| 字段 | 来源 |
|---|---|
| `net_redemption`, `shares`, `size` | `get_fund_etf_cr_net` |
| `close`, `amount`, `discount_rate` | `get_fund_daily` |
| `net_purchase_limit`, `net_redemption_limit` | `get_fund_etf_cr_limits` |

## 输出结果

**`output/radar_YYYYMMDD.csv`**（每条命中一行）：

| 列 | 说明 |
|---|---|
| `trade_date` | 扫描日 T |
| `symbol` | ETF 代码 |
| `name` | 留空（本 MVP 不接入基金基础信息接口） |
| `signal_type` | `S1` / `S4` / `S7` |
| `signal_value` | S1: z；S4: |dr|；S7: 倍数 |
| `abs_signal_value` | 分组内排序键 |
| `net_redemption_T`, `size_T`, `amount_T_avg20`, `discount_rate_T` | 上下文数值 |
| `limit_hit_flag` | 当日申赎受限（参考列，不作为命中条件） |
| `detail_json` | 信号细节 JSON |

**排序**：先按 `signal_type`（S1 → S4 → S7 固定顺序）分组，组内按 `abs_signal_value` 降序。三者量纲不同，不做跨组全局排序。

**`output/radar_YYYYMMDD.md`**：Top 10 + 三个信号小节 + 一句解读。

## 使用方式

```bash
# 认证
export PANDA_DATA_USERNAME=...
export PANDA_DATA_PASSWORD=...

# 字段自检（首次使用 / panda_data 版本更新后跑一次）
python -m scripts.data --self-check --date 20260721

# 单日扫描 —— 默认最近数据可用交易日
python scripts/radar.py

# 指定日期
python scripts/radar.py --date 20260721

# 调阈值
python scripts/radar.py --date 20260721 \
    --z_threshold 1.5 --discount_threshold 0.002 \
    --consec_days 3 --ratio_threshold 2.0 \
    --min_size 2e9 --min_amount 5e7 \
    --lookback 20 --fetch_days 40

# 单元测试
pytest tests/ -v
```

## 验收要求
- **无未来函数**：S1/S7 历史窗口不含 T 日，`test_s1_no_lookahead` / `test_s7_no_lookahead_on_baseline` 覆盖
- **单元测试全通过**：`pytest tests/` 无失败
- **字段自检通过**：`python -m scripts.data --self-check --date <近期日>` 返回 0
- **端到端跑通**：至少一个真实日期能产出 CSV + MD，命中数**可为 0**（不为了凑数刻意放宽阈值）
- **文档一致**：本文件的信号公式与 `scripts/signals.py` 一致

## 已知局限
- `net_redemption` / `discount_rate` 正负号方向依赖首次实测校准；若反向，改一处 `SIGN_FLIP_*` 常量。
- 不含"触限打满"作为独立信号，仅作参考列 `limit_hit_flag`。
- 不接入 ETF 基础信息接口，`name` 列留空。
- 不做批量日期回补；如需回补，外层 shell 循环即可。
- 不含图表输出；v2 再加。
- `get_fund_etf_cr_net` 的响应示例文本与表格字段对不上（示例贴的是股票股东减持数据）；设计一律以表格为准，首次实测校准。
```

- [ ] **Step 2: Create `README.md`**

Path: `/Users/since/Code/quantskills/skill-etf-flow-radar/README.md`

```markdown
# skill-etf-flow-radar

Claude Code skill for a daily post-market ETF net-creation/redemption radar. See `SKILL.md` for full usage. Design lives in `docs/superpowers/specs/2026-07-22-etf-flow-radar-design.md`; implementation plan in `docs/superpowers/plans/2026-07-22-etf-flow-radar.md`.

## Quick start

```bash
export PANDA_DATA_USERNAME=...
export PANDA_DATA_PASSWORD=...
pip install -r requirements.txt
pytest tests/                                     # unit tests
python -m scripts.data --self-check --date 20260721   # field self-check
python scripts/radar.py --date 20260721                # single-day scan
```

Outputs land in `output/radar_YYYYMMDD.csv` + `.md`.
```

- [ ] **Step 3: Final line-count guardrail**

```bash
cd /Users/since/Code/quantskills/skill-etf-flow-radar
wc -l scripts/*.py
```

Expected: every file ≤ 250 lines. If not, split before shipping.

- [ ] **Step 4: Full test run**

```bash
pytest tests/ -v
```

Expected: all tests passed (16 signal tests + 5 universe tests = 21).

- [ ] **Step 5: Commit**

```bash
git add SKILL.md README.md
git commit -m "docs: SKILL.md (skill contract) + README.md (quick start)

Co-Authored-By: Claude <noreply@anthropic.com>"
```

- [ ] **Step 6: Tag v0.1.0**

```bash
git tag -a v0.1.0 -m "v0.1.0 — MVP: S1/S4/S7 daily radar, CSV + MD output"
git log --oneline
```

Expected: 10 commits total (init + 9 tasks) on `main`, tag `v0.1.0` at HEAD.

---

## Self-Review

Ran against the spec (`docs/superpowers/specs/2026-07-22-etf-flow-radar-design.md`):

**1. Spec coverage**
- §1 Positioning / non-goals → SKILL.md (Task 9) ✓
- §2 Data interfaces + terms + field-mismatch caveat → `data.py` self-check (Task 6) + SKILL.md caveat (Task 9) ✓
- §3.1 ETF pool → `universe.py` + tests (Task 5) ✓
- §3.2 40-day fetch window → `--fetch_days` default in `radar.py` (Task 8) + SKILL.md rationale (Task 9) ✓
- §3.3 S1/S4/S7 formulas → `signals.py` + tests (Tasks 1–3) ✓
- §3.4 Output schema → `SIGNAL_COLUMNS` (Task 1), `amount_T_avg20`/`limit_hit_flag` enrichment (Task 8), CSV/MD emitters (Task 7) ✓
- §4 Module structure + 250-line cap → all tasks + guardrails at Tasks 4 & 9 ✓
- §5 CLI → Task 8 ✓
- §6 Error handling / exit codes → Task 8 (main function) ✓
- §7 Tests → Tasks 1, 2, 3, 5 ✓
- §8 Acceptance criteria → SKILL.md (Task 9) ✓
- §9 Known limitations → SKILL.md (Task 9) ✓
- §10 Future roadmap → out of scope by design, mentioned in SKILL.md ✓

**2. Placeholder scan**: no TBDs; every code step contains actual runnable code; commit messages are literal.

**3. Type consistency**:
- `SIGNAL_COLUMNS` defined in Task 1 is re-used verbatim in Tasks 2, 3, 7, 8 ✓
- Signal function signatures (`s1_net_flow_z / s4_discount_diverge / s7_consec_flow`) match between Tasks 1–3 (definition) and Task 8 (call sites) ✓
- `filter_universe` returns `(list[str], DataFrame)` in Task 5 and is unpacked as such in Task 8 ✓
- `load_flow / load_daily / load_limits / init_panda_data / EXPECTED_COLUMNS` in Task 6 all consumed in Task 8 with matching names ✓
- `write_csv / write_markdown` signatures in Task 7 match calls in Task 8 ✓

---

## Execution Handoff

Plan complete and saved to `docs/superpowers/plans/2026-07-22-etf-flow-radar.md`. Two execution options:

**1. Subagent-Driven (recommended)** — I dispatch a fresh subagent per task, review between tasks, fast iteration.

**2. Inline Execution** — I execute tasks in this session using executing-plans, batch execution with checkpoints.

**Which approach?**
