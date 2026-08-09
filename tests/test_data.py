"""Unit tests for scripts/data._main — error handling around panda_data auth/service errors.

Rationale: when panda_data returns HTTP 5xx or rejects credentials, users saw a 40-line
traceback and had to squint to find the actual message. `_main()` now catches the two
expected auth-time failures (missing env vars → RuntimeError; upstream refusal →
panda_data.exceptions.ServiceError) and prints one clean line to stderr with exit code 1.
"""
import sys
import types

import pytest

from scripts import data


def _install_fake_panda_data(monkeypatch, init_token_impl):
    """Register a stub `panda_data` module so `import panda_data` inside data.py works.

    We can't rely on the real panda_data being installed in every CI/dev environment
    (see data.py docstring on lazy imports), so the stub covers both cases.
    """
    fake = types.ModuleType("panda_data")
    fake.init_token = init_token_impl
    # data._main catches panda_data.exceptions.ServiceError; provide that attribute path.
    exceptions_mod = types.ModuleType("panda_data.exceptions")

    class ServiceError(Exception):
        pass

    exceptions_mod.ServiceError = ServiceError
    fake.exceptions = exceptions_mod
    monkeypatch.setitem(sys.modules, "panda_data", fake)
    monkeypatch.setitem(sys.modules, "panda_data.exceptions", exceptions_mod)
    return ServiceError


def test_main_returns_1_and_prints_short_error_on_service_error(monkeypatch, capsys):
    ServiceError = _install_fake_panda_data(
        monkeypatch,
        init_token_impl=lambda **kw: (_ for _ in ()).throw(
            sys.modules["panda_data.exceptions"].ServiceError("登录失败: HTTP 503")
        ),
    )
    monkeypatch.setenv("PANDA_DATA_USERNAME", "u")
    monkeypatch.setenv("PANDA_DATA_PASSWORD", "p")
    monkeypatch.setattr(sys, "argv", ["data.py", "--self-check", "--date", "20260724"])

    rc = data._main()

    assert rc == 1
    captured = capsys.readouterr()
    # One-line-ish user-facing error on stderr, no Python traceback framing.
    assert "Traceback" not in captured.err
    assert "登录失败" in captured.err or "HTTP 503" in captured.err or "panda_data" in captured.err.lower()


def test_main_returns_1_on_missing_credentials(monkeypatch, capsys):
    # RuntimeError path was already handled; keep the guarantee under test.
    monkeypatch.delenv("PANDA_DATA_USERNAME", raising=False)
    monkeypatch.delenv("PANDA_DATA_PASSWORD", raising=False)
    monkeypatch.setattr(sys, "argv", ["data.py", "--self-check", "--date", "20260724"])

    rc = data._main()

    assert rc == 1
    captured = capsys.readouterr()
    assert "Traceback" not in captured.err
    assert "PANDA_DATA_USERNAME" in captured.err


# -----------------------------------------------------------------------------
# Cross-month splitting — panda_data returns empty when the range spans months.
# load_flow / load_daily hide this by chunking per calendar month.
# -----------------------------------------------------------------------------


def test_month_chunks_same_month_single_chunk():
    assert data._month_chunks("20260610", "20260630") == [("20260610", "20260630")]
    assert data._month_chunks("20260601", "20260601") == [("20260601", "20260601")]


def test_month_chunks_spans_two_months():
    assert data._month_chunks("20260501", "20260610") == [
        ("20260501", "20260531"),
        ("20260601", "20260610"),
    ]


def test_month_chunks_spans_year_boundary():
    assert data._month_chunks("20261215", "20270115") == [
        ("20261215", "20261231"),
        ("20270101", "20270115"),
    ]


def test_month_chunks_reversed_returns_empty():
    assert data._month_chunks("20260610", "20260601") == []


def _make_daily_row(symbol: str, date: str, amount: float = 1e8) -> dict:
    """One row shaped like panda_data.get_fund_daily."""
    return {
        "symbol": symbol,
        "date": date,
        "close": 1.0,
        "amount": amount,
        "discount_rate": 0.0,
    }


def test_load_daily_single_month_calls_once(monkeypatch):
    """Back-compat: within a single month, panda_data is called exactly once."""
    import pandas as pd

    calls: list[tuple[str, str]] = []

    def fake_get_fund_daily(*, start_date, end_date):
        calls.append((start_date, end_date))
        return pd.DataFrame([_make_daily_row("510300.SH", "20260615")])

    fake = types.ModuleType("panda_data")
    fake.get_fund_daily = fake_get_fund_daily
    monkeypatch.setitem(sys.modules, "panda_data", fake)

    df = data.load_daily("20260610", "20260620")

    assert calls == [("20260610", "20260620")]
    assert list(df["symbol"]) == ["510300.SH"]


def test_load_daily_cross_month_splits_and_concats(monkeypatch):
    """The exact failure mode we hit: `20260501~20260610` returns empty from the real API.

    Our wrapper must split into `20260501~20260531` and `20260601~20260610`, call each,
    and concat. Simulate the real API here: return non-empty per-month, and also verify
    that if the full-span call had been used it would be empty — so we know the wrapper
    is what's giving us data.
    """
    import pandas as pd

    calls: list[tuple[str, str]] = []

    def fake_get_fund_daily(*, start_date, end_date):
        calls.append((start_date, end_date))
        # If a caller ever passes the full cross-month span again, return empty
        # (mirrors real panda_data behavior).
        if start_date == "20260501" and end_date == "20260610":
            return pd.DataFrame()
        if start_date == "20260501" and end_date == "20260531":
            return pd.DataFrame([_make_daily_row("510300.SH", "20260520")])
        if start_date == "20260601" and end_date == "20260610":
            return pd.DataFrame([_make_daily_row("510300.SH", "20260605")])
        return pd.DataFrame()

    fake = types.ModuleType("panda_data")
    fake.get_fund_daily = fake_get_fund_daily
    monkeypatch.setitem(sys.modules, "panda_data", fake)

    df = data.load_daily("20260501", "20260610")

    # Two per-month calls, no full-span call.
    assert calls == [("20260501", "20260531"), ("20260601", "20260610")]
    # Rows from both months present.
    assert sorted(df["date"].tolist()) == ["20260520", "20260605"]


def test_load_flow_cross_month_splits(monkeypatch):
    """Same guarantee for load_flow (get_fund_etf_cr_net)."""
    import pandas as pd

    calls: list[tuple[str, str]] = []

    def fake_get_fund_etf_cr_net(*, start_date, end_date):
        calls.append((start_date, end_date))
        base = {
            "symbol": "510300.SH", "date": start_date,
            "net_redemption": 0.0, "shares": 0.0, "shares_change": 0.0,
            "size": 3e9, "size_change": 0.0,
        }
        return pd.DataFrame([base])

    fake = types.ModuleType("panda_data")
    fake.get_fund_etf_cr_net = fake_get_fund_etf_cr_net
    monkeypatch.setitem(sys.modules, "panda_data", fake)

    df = data.load_flow("20260501", "20260610")

    assert calls == [("20260501", "20260531"), ("20260601", "20260610")]
    assert len(df) == 2


def test_load_daily_dedupes_overlapping_boundary_rows(monkeypatch):
    """Defensive: if a future API change starts returning boundary rows in both
    adjacent chunks (e.g. month-end appears in both months), we dedupe on
    (symbol, date) so the caller doesn't see duplicates."""
    import pandas as pd

    def fake_get_fund_daily(*, start_date, end_date):
        # Both chunks pretend to include a 20260531 row for the same symbol.
        if start_date == "20260501":
            return pd.DataFrame([
                _make_daily_row("510300.SH", "20260520"),
                _make_daily_row("510300.SH", "20260531"),
            ])
        return pd.DataFrame([
            _make_daily_row("510300.SH", "20260531"),
            _make_daily_row("510300.SH", "20260605"),
        ])

    fake = types.ModuleType("panda_data")
    fake.get_fund_daily = fake_get_fund_daily
    monkeypatch.setitem(sys.modules, "panda_data", fake)

    df = data.load_daily("20260501", "20260610")

    # 20260531 appears only once.
    assert sorted(df["date"].tolist()) == ["20260520", "20260531", "20260605"]


def test_load_fund_meta_is_optional_enrichment(monkeypatch):
    import pandas as pd

    calls = []

    def fake_get_fund_detail(*, symbol, fields):
        calls.append((symbol, fields))
        return pd.DataFrame([
            {"symbol": "513050.SH", "name": "中概互联", "is_qdii_fund": 1},
            {"symbol": "510300.SH", "name": "沪深300", "is_qdii_fund": 0},
        ])

    fake = types.ModuleType("panda_data")
    fake.get_fund_detail = fake_get_fund_detail
    monkeypatch.setitem(sys.modules, "panda_data", fake)

    df = data.load_fund_meta(["513050.SH", "510300.SH"])

    assert calls == [
        (["513050.SH", "510300.SH"], ["symbol", "name", "is_qdii_fund"])
    ]
    assert list(df.columns) == ["symbol", "name", "is_qdii_fund"]
    assert df.loc[df["symbol"] == "513050.SH", "is_qdii_fund"].iloc[0] == 1


def test_load_fund_meta_empty_symbols_does_not_call_api(monkeypatch):
    import pandas as pd

    fake = types.ModuleType("panda_data")
    fake.get_fund_detail = lambda **kwargs: (_ for _ in ()).throw(AssertionError("called"))
    monkeypatch.setitem(sys.modules, "panda_data", fake)

    df = data.load_fund_meta([])

    assert df.empty
    assert list(df.columns) == ["symbol", "name", "is_qdii_fund"]
