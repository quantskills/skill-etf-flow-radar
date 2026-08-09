# skill-etf-flow-radar

Claude Code skill for a daily post-market ETF net-creation/redemption radar. See `SKILL.md` for full usage. Design lives in `docs/superpowers/specs/2026-07-22-etf-flow-radar-design.md`; implementation plan in `docs/superpowers/plans/2026-07-22-etf-flow-radar.md`.

## Quick start

```bash
export PANDA_DATA_USERNAME=...
export PANDA_DATA_PASSWORD=...
pip install -r requirements.txt
pytest tests/                                     # unit tests
python -m scripts.data --self-check --date 20260721   # field self-check
python scripts/radar.py --date 20260721                # single-day scan
```

Outputs land in `output/radar_YYYYMMDD.csv` + `.md`.

## 跨境 ETF 说明

扫描结果可能包含跨境/QDII ETF。基金详情接口可用时，报告会识别并列出 QDII 候选；
接口不可用时会明确提示未完成逐只标注，但不会影响资金流信号。

国内普通股票 ETF 的二级市场买入份额通常按 T+1 可卖出；跨境 ETF 的 T+0 仅指二级市场买入后当日卖出的常见交易口径；申购/赎回的份额确认、
可卖出/可赎回时间和资金到账日不由本 radar 推断，必须以具体基金公告、交易所和券商规则为准。
详见 [SKILL.md](SKILL.md) 的“跨境 ETF 与 T+0/T+1 口径”章节。
