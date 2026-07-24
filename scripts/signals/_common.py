"""Shared schema and row-construction helpers for the signals package."""
from __future__ import annotations

import json

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

# net_redemption is denominated in shares / yuan-ish; <1 means "essentially zero"
_SIGMA_EPSILON = 1.0


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
