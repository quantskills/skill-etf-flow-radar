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


def _write_cross_border_note(lines: list[str], fund_meta: pd.DataFrame | None) -> None:
    """Explain the cross-border/T+0 boundary without turning it into a signal."""
    lines.append("\n## 跨境 ETF 与 T+0/T+1 口径\n")
    lines.append(
        "- 本雷达可在基金详情接口可用时识别 QDII/跨境候选；该标签只用于说明，不参与三条信号判定。"
    )
    lines.append(
        "- 口径对照：国内普通股票 ETF 二级市场通常按 T+1 可卖出；跨境 ETF 的 T+0 仅指二级市场买入后当日卖出的一般交易口径。"
    )
    lines.append(
        "- 申购/赎回的份额确认、可卖出/可赎回时间和资金到账日另行计算，不能从上述 T+0/T+1 买卖口径直接推断。"
    )
    lines.append(
        "- 本报告不根据日线数据推断具体产品的 T+0/T+1，也不把申购/赎回命中解释成可当日交易；具体以基金公告、交易所和券商规则为准。"
    )
    if fund_meta is None or fund_meta.empty:
        lines.append(
            "- 本次未取得基金详情，因此没有完成逐只 QDII/跨境标注；这不影响资金流信号，但不能据此判断 T+0/T+1。"
        )
        return
    qdii = fund_meta[fund_meta["is_qdii_fund"].map(_is_qdii)]
    if qdii.empty:
        lines.append("- 本次扫描池未识别到 QDII/跨境候选，或基金详情未返回该字段。")
    else:
        names = qdii["name"].fillna("").astype(str)
        labels = [f"{r.symbol}（{rname}）" if rname else str(r.symbol)
                  for r, rname in zip(qdii.itertuples(index=False), names)]
        lines.append(
            f"- 本次扫描池识别到 {len(qdii)} 支 QDII/跨境候选：" + "、".join(labels[:10])
            + ("等。" if len(labels) > 10 else "。")
        )


def _is_qdii(value: object) -> bool:
    """Normalize the API's observed 0/1 and string boolean representations."""
    return str(value).strip().lower() in {"1", "true", "yes", "y"}


def write_markdown(
    hits_df: pd.DataFrame,
    path: str,
    *,
    date: str,
    params: dict,
    fund_meta: pd.DataFrame | None = None,
) -> None:
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

    _write_cross_border_note(lines, fund_meta)

    Path(path).parent.mkdir(parents=True, exist_ok=True)
    Path(path).write_text("\n".join(lines), encoding="utf-8")
