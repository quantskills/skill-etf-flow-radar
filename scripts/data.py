"""panda_data thin wrappers for skill-etf-flow-radar.

Three interfaces are used (see references/need_used_api.md). Column names are validated
against a required-superset set (EXPECTED_COLUMNS) on every load; mismatch triggers
exit code 4 via self_check().

panda_data is a private package imported lazily inside each function so that this module
can be imported (and its EXPECTED_COLUMNS inspected) without panda_data installed —
useful for unit-testing callers that mock the loaders.
"""
from __future__ import annotations

import argparse
import os
import sys

import pandas as pd

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
    import panda_data
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
    import panda_data
    df = panda_data.get_fund_etf_cr_net(start_date=start_date, end_date=end_date)
    if df is None or (hasattr(df, "empty") and df.empty):
        return pd.DataFrame(columns=sorted(EXPECTED_COLUMNS["flow"]))
    _assert_columns(df, "flow")
    df["date"] = df["date"].astype(str)
    df["symbol"] = df["symbol"].astype(str)
    return df


def load_daily(start_date: str, end_date: str) -> pd.DataFrame:
    """get_fund_daily over [start_date, end_date] (whole-market)."""
    import panda_data
    df = panda_data.get_fund_daily(start_date=start_date, end_date=end_date)
    if df is None or (hasattr(df, "empty") and df.empty):
        return pd.DataFrame(columns=sorted(EXPECTED_COLUMNS["daily"]))
    _assert_columns(df, "daily")
    df["date"] = df["date"].astype(str)
    df["symbol"] = df["symbol"].astype(str)
    return df


def load_limits(date: str) -> pd.DataFrame:
    """get_fund_etf_cr_limits for a single day."""
    import panda_data
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
    import panda_data
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
    try:
        return self_check(args.date)
    except RuntimeError as e:
        print(f"[error] {e}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(_main())
