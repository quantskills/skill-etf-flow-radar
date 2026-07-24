---
name: skill-etf-flow-radar
description: ETF 净申赎资金流雷达。每日盘后扫描主流权益 ETF，输出 S1（净申赎异动）/S4（折溢价背离）/S7（连续同向）三类异动榜（CSV + Markdown）。
tags: [quant, etf, flow, radar]
---

# ETF 净申赎资金流雷达

## 适用场景
- 每日盘后想快速看"哪些 ETF 今天有异常资金流入/流出"
- 想快速识别"折溢价 + 一级申赎方向背离"的套利/恐慌信号
- 想跟踪某只 ETF 是否处于"连续多日同向"的趋势中

## 数据接口（panda_data）

| 接口 | 用途 | 关键字段 |
|---|---|---|
| `get_fund_etf_cr_net` | 一级市场净申赎 | `symbol, date, net_redemption, shares, shares_change, size, size_change, net_inflow, unit_nav, close` |
| `get_fund_etf_cr_limits` | 当日申赎限额 | `symbol, date, net_purchase_limit, net_redemption_limit, purchase_limit, redemption_limit` |
| `get_fund_daily` | 二级市场行情 + 折溢价 | `symbol, date, close, amount, discount_rate, limit_up, limit_down, shares` |

字段详见 `references/need_used_api.md`。

## 术语约定

- `net_redemption > 0` → 净申购；`< 0` → 净赎回
- `discount_rate > 0` → 贴水（价格低于净值）；`< 0` → 溢价

首次实测须校准；如反向，只需改 `signals.py` 中一处 `SIGN_FLIP_*` 常量。

## ETF 池

主流权益 ETF：
- 当日 `size ≥ 20 亿元`
- 近 20 交易日均 `amount ≥ 5000 万元`

两条件取 AND，阈值全部 CLI 可调。

## 数据回看窗口 · 40 自然日

S1/S7 需要 20 交易日历史；20 交易日 ≈ 28 自然日；取 40 自然日留 buffer，覆盖长假、临时休市、上市未满 20 日等场景。不引入交易日历接口。

## 三条信号

### S1 · 净申赎异动（Z-score）
对每只池内 ETF，用 T-1 至 T-L（L=20，不含 T）的 `net_redemption` 计算均值/标准差，得到 T 日 z 值。**|z| ≥ z_threshold (默认 2.0)** 命中。`sigma < 1` 时跳过该 ETF 的 S1 判断。

### S4 · 折溢价背离
`|discount_rate| ≥ discount_threshold (默认 0.003)` **且** 与当日 `net_redemption` 符号相反。两种情形：
- 溢价 + 净申购 → `premium_buy`
- 贴水 + 净赎回 → `discount_sell`

### S7 · 连续同向
最近 `consec_days` 天（默认 3）`net_redemption` 全同号，且累计绝对值 ≥ `ratio_threshold × mu_abs`（默认 2.0；`mu_abs` = 前 20 交易日 `|net_redemption|` 均值）。基线窗口不与 K 日窗口重叠。

## 输入数据

| 字段 | 来源 |
|---|---|
| `net_redemption`, `shares`, `size` | `get_fund_etf_cr_net` |
| `close`, `amount`, `discount_rate` | `get_fund_daily` |
| `net_purchase_limit`, `net_redemption_limit` | `get_fund_etf_cr_limits` |

## 输出结果

**`output/radar_YYYYMMDD.csv`**（每条命中一行）：

| 列 | 说明 |
|---|---|
| `trade_date` | 扫描日 T |
| `symbol` | ETF 代码 |
| `name` | 留空（本 MVP 不接入基金基础信息接口） |
| `signal_type` | `S1` / `S4` / `S7` |
| `signal_value` | S1: z；S4: |dr|；S7: 倍数 |
| `abs_signal_value` | 分组内排序键 |
| `net_redemption_T`, `size_T`, `amount_T_avg20`, `discount_rate_T` | 上下文数值 |
| `limit_hit_flag` | 当日申赎受限（参考列，不作为命中条件） |
| `detail_json` | 信号细节 JSON |

**排序**：先按 `signal_type`（S1 → S4 → S7 固定顺序）分组，组内按 `abs_signal_value` 降序。三者量纲不同，不做跨组全局排序。

**`output/radar_YYYYMMDD.md`**：Top 10 + 三个信号小节 + 一句解读。

## 使用方式

```bash
# 认证
export PANDA_DATA_USERNAME=...
export PANDA_DATA_PASSWORD=...

# 字段自检（首次使用 / panda_data 版本更新后跑一次）
python -m scripts.data --self-check --date 20260721

# 单日扫描 —— 默认最近数据可用交易日
python scripts/radar.py

# 指定日期
python scripts/radar.py --date 20260721

# 调阈值
python scripts/radar.py --date 20260721 \
    --z_threshold 1.5 --discount_threshold 0.002 \
    --consec_days 3 --ratio_threshold 2.0 \
    --min_size 2e9 --min_amount 5e7 \
    --lookback 20 --fetch_days 40

# 单元测试
pytest tests/ -v
```

## 验收要求
- **无未来函数**：S1/S7 历史窗口不含 T 日，`test_s1_no_lookahead` / `test_s7_no_lookahead_on_baseline` 覆盖
- **单元测试全通过**：`pytest tests/` 无失败
- **字段自检通过**：`python -m scripts.data --self-check --date <近期日>` 返回 0
- **端到端跑通**：至少一个真实日期能产出 CSV + MD，命中数**可为 0**（不为了凑数刻意放宽阈值）
- **文档一致**：本文件的信号公式与 `scripts/signals.py` 一致

## 已知局限
- `net_redemption` / `discount_rate` 正负号方向依赖首次实测校准；若反向，改一处 `SIGN_FLIP_*` 常量。
- 不含"触限打满"作为独立信号，仅作参考列 `limit_hit_flag`。
- 不接入 ETF 基础信息接口，`name` 列留空。
- 不做批量日期回补；如需回补，外层 shell 循环即可。
- 不含图表输出；v2 再加。
- `get_fund_etf_cr_net` 的响应示例文本与表格字段对不上（示例贴的是股票股东减持数据）；设计一律以表格为准，首次实测校准。
