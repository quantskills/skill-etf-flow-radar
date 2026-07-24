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
import sys
from datetime import datetime, timedelta
from pathlib import Path

import pandas as pd

# Allow both `python scripts/radar.py` and `python -m scripts.radar` invocations.
# When the file is run directly, Python prepends `scripts/` (not the repo root) to
# sys.path, so `from scripts import ...` below would fail. Insert the repo root
# ourselves before the package imports.
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

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
