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
