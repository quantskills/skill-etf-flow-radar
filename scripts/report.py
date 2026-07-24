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
