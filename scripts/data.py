"""panda_data thin wrappers for skill-etf-flow-radar.

Three core interfaces are used (see references/need_used_api.md). Column names are validated
against a required-superset set (EXPECTED_COLUMNS) on every load; mismatch triggers
exit code 4 via self_check().

Fund metadata is an optional enrichment: get_fund_detail is used on the selected universe
to identify QDII/cross-border candidates and fill names. Its failure never blocks the radar,
because the endpoint is marked deprecated/unlaunched by panda_data and is not required for
the three signals.

panda_data is a private package imported lazily inside each function so that this module
can be imported (and its EXPECTED_COLUMNS inspected) without panda_data installed —
useful for unit-testing callers that mock the loaders.

Cross-month behavior
--------------------
panda_data's `get_fund_daily` / `get_fund_etf_cr_net` return an empty DataFrame when
[start_date, end_date] spans multiple natural months (observed on 20260501~20260610 for
daily; same shape for flow). Root cause is server-side, not fixed in the client.

To hide this from callers (the radar's 40-natural-day fetch window routinely straddles
a month boundary), `load_flow` / `load_daily` split the request into month-sized chunks
internally and concat the results. Single-month requests still make a single call
(back-compat with existing tests that mock the loader once).
"""
from __future__ import annotations

import argparse
import os
import sys
from datetime import datetime, timedelta
from typing import Callable

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


def _month_chunks(start_date: str, end_date: str) -> list[tuple[str, str]]:
    """Split [start_date, end_date] into month-sized closed intervals (YYYYMMDD strings).

    Same month → one chunk (single-call fast path, preserves back-compat with tests
    that mock the loader exactly once). Multi-month → one chunk per month, each
    clipped to [start_date, end_date].

    Examples:
        _month_chunks("20260610", "20260630") → [("20260610", "20260630")]
        _month_chunks("20260501", "20260610")
            → [("20260501","20260531"), ("20260601","20260610")]
    """
    s = datetime.strptime(start_date, "%Y%m%d")
    e = datetime.strptime(end_date, "%Y%m%d")
    if s > e:
        return []
    chunks: list[tuple[str, str]] = []
    cur = s
    while cur <= e:
        # Last day of `cur`'s month
        if cur.month == 12:
            next_month_first = datetime(cur.year + 1, 1, 1)
        else:
            next_month_first = datetime(cur.year, cur.month + 1, 1)
        month_end = next_month_first - timedelta(days=1)
        chunk_end = min(month_end, e)
        chunks.append((cur.strftime("%Y%m%d"), chunk_end.strftime("%Y%m%d")))
        cur = chunk_end + timedelta(days=1)
    return chunks


def _load_chunked(
    fetch_one: Callable[[str, str], "pd.DataFrame | None"],
    start_date: str,
    end_date: str,
    kind: str,
) -> pd.DataFrame:
    """Call `fetch_one(s, e)` per month-chunk of [start_date, end_date], concat, dedupe.

    Kept in one place so `load_flow` / `load_daily` share the cross-month workaround.
    An empty return from any chunk is treated as "no data in that month" (not an error);
    the final frame is the concat of whatever came back. Empty overall → empty frame
    with the expected columns.
    """
    frames: list[pd.DataFrame] = []
    for s, e in _month_chunks(start_date, end_date):
        df = fetch_one(s, e)
        if df is None or (hasattr(df, "empty") and df.empty):
            continue
        _assert_columns(df, kind)
        frames.append(df)
    if not frames:
        return pd.DataFrame(columns=sorted(EXPECTED_COLUMNS[kind]))
    out = pd.concat(frames, ignore_index=True)
    # Chunks are non-overlapping by construction; still dedupe on (symbol, date) as a
    # cheap safety net in case a future panda_data change starts returning boundary
    # rows in both adjacent chunks.
    out = out.drop_duplicates(subset=["symbol", "date"], keep="first").reset_index(drop=True)
    out["date"] = out["date"].astype(str)
    out["symbol"] = out["symbol"].astype(str)
    return out


def load_flow(start_date: str, end_date: str) -> pd.DataFrame:
    """get_fund_etf_cr_net over [start_date, end_date] (whole-market).

    Cross-month windows are split by month internally (see module docstring).
    """
    import panda_data
    return _load_chunked(
        lambda s, e: panda_data.get_fund_etf_cr_net(start_date=s, end_date=e),
        start_date, end_date, "flow",
    )


def load_daily(start_date: str, end_date: str) -> pd.DataFrame:
    """get_fund_daily over [start_date, end_date] (whole-market).

    Cross-month windows are split by month internally (see module docstring).
    """
    import panda_data
    return _load_chunked(
        lambda s, e: panda_data.get_fund_daily(start_date=s, end_date=e),
        start_date, end_date, "daily",
    )


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


def load_fund_meta(symbols: list[str]) -> pd.DataFrame:
    """Load optional fund metadata for the selected universe.

    The endpoint is deliberately kept out of EXPECTED_COLUMNS/self_check: it is an
    enrichment only, and panda_data currently marks get_fund_detail as deprecated or
    not universally available. Callers should catch failures and continue without it.

    Returns a stable, small schema even if the service omits optional fields.
    """
    columns = ["symbol", "name", "is_qdii_fund"]
    if not symbols:
        return pd.DataFrame(columns=columns)

    import panda_data

    df = panda_data.get_fund_detail(
        symbol=list(symbols),
        fields=columns,
    )
    if df is None or (hasattr(df, "empty") and df.empty):
        return pd.DataFrame(columns=columns)
    if "symbol" not in df.columns:
        raise ValueError("panda_data fund detail response missing column: symbol")
    out = df.copy()
    for col in columns:
        if col not in out.columns:
            out[col] = None
    out = out[columns].drop_duplicates(subset=["symbol"], keep="first")
    out["symbol"] = out["symbol"].astype(str)
    return out.reset_index(drop=True)


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

    # Lazily resolve panda_data.exceptions.ServiceError. If panda_data isn't installed,
    # init_panda_data() will fail earlier with RuntimeError (missing env vars) or ImportError;
    # either way we won't need to catch ServiceError, so a placeholder tuple is safe.
    try:
        from panda_data.exceptions import ServiceError as _ServiceError
        service_error_cls: tuple = (_ServiceError,)
    except ImportError:
        service_error_cls = ()

    try:
        return self_check(args.date)
    except RuntimeError as e:
        # Missing PANDA_DATA_USERNAME / PANDA_DATA_PASSWORD, etc.
        print(f"[error] {e}", file=sys.stderr)
        return 1
    except service_error_cls as e:  # type: ignore[misc]  # empty tuple = catch nothing
        # Auth / network failures from panda_data (HTTP 4xx/5xx, login rejected, …).
        # Print one line; full traceback would drown the actionable message.
        print(f"[error] panda_data service error: {e}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(_main())
