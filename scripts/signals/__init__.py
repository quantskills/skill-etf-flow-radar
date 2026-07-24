"""ETF flow-radar signals: S1 (net-flow Z-score), S4 (discount divergence), S7 (consecutive flow).

Each signal is a pure function on user-supplied DataFrames. Zero hits => empty DataFrame with
the shared 12-column schema. All three return the same schema so ``pd.concat`` is safe.

Sign conventions (see design doc §2):
  - net_redemption > 0 → 净申购 (net creation / inflow to primary market)
  - discount_rate  > 0 → 贴水 (secondary price below NAV)
Both are subject to empirical calibration on first end-to-end run.
"""
from __future__ import annotations

from ._common import SIGNAL_COLUMNS, empty_hits
from .s1 import s1_net_flow_z
from .s4 import s4_discount_diverge
from .s7 import s7_consec_flow

__all__ = [
    "SIGNAL_COLUMNS",
    "empty_hits",
    "s1_net_flow_z",
    "s4_discount_diverge",
    "s7_consec_flow",
]
