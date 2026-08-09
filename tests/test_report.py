import pandas as pd

from scripts import report


def test_markdown_explains_cross_border_t0_boundary(tmp_path):
    path = tmp_path / "radar.md"
    meta = pd.DataFrame([
        {"symbol": "513050.SH", "name": "中概互联", "is_qdii_fund": 1},
        {"symbol": "510300.SH", "name": "沪深300", "is_qdii_fund": 0},
    ])

    report.write_markdown(
        pd.DataFrame(columns=[
            "trade_date", "symbol", "name", "signal_type", "signal_value",
            "abs_signal_value", "net_redemption_T", "size_T", "amount_T_avg20",
            "discount_rate_T", "limit_hit_flag", "detail_json",
        ]),
        str(path),
        date="20260808",
        params={
            "z_threshold": 2.0, "discount_threshold": 0.003,
            "consec_days": 3, "ratio_threshold": 2.0,
            "min_size": 2e9, "min_amount": 5e7,
        },
        fund_meta=meta,
    )

    text = path.read_text(encoding="utf-8")
    assert "跨境 ETF 与 T+0/T+1 口径" in text
    assert "国内普通股票 ETF 二级市场通常按 T+1 可卖出" in text
    assert "二级市场买入后当日卖出" in text
    assert "申购/赎回" in text
    assert "513050.SH" in text


def test_markdown_marks_missing_fund_meta(tmp_path):
    path = tmp_path / "radar.md"
    report.write_markdown(
        pd.DataFrame(columns=[
            "trade_date", "symbol", "name", "signal_type", "signal_value",
            "abs_signal_value", "net_redemption_T", "size_T", "amount_T_avg20",
            "discount_rate_T", "limit_hit_flag", "detail_json",
        ]),
        str(path),
        date="20260808",
        params={
            "z_threshold": 2.0, "discount_threshold": 0.003,
            "consec_days": 3, "ratio_threshold": 2.0,
            "min_size": 2e9, "min_amount": 5e7,
        },
    )

    assert "没有完成逐只 QDII/跨境标注" in path.read_text(encoding="utf-8")
