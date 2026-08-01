---
name: skill-etf-flow-radar
description: 每日盘后 ETF 资金流雷达 —— 用户问「今天/最近 ETF 有什么异动」「ETF 资金流看下」「哪些 ETF 在被大量申购/赎回」「ETF 净申赎异动」类问题时触发。扫描主流权益 ETF，输出三类信号（净申赎异动 / 折溢价背离 / 连续同向），以「样式② 结构化播报」呈现给用户。
tags: [quant, etf, flow, radar]
---

# ETF 净申赎资金流雷达

## 何时触发本 skill

用户提问命中下列语义时，自动调用：

- 「今天 ETF 有什么异动」「最近 ETF 资金流看下」
- 「哪些 ETF 被大量申购/赎回」「ETF 净申赎异动」
- 「跑一下 ETF 资金流雷达」「扫一下 ETF 资金流」
- 「有没有 ETF 出现折溢价套利机会」（折溢价背离语义）

**不触发**：单只 ETF 的个股问答、非 ETF 的股票资金流、宏观资金面判断。

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

首次实测须校准；如反向，修改 `scripts/signals/{s1,s4,s7}.py` 中对应的方向判断（S1 的 direction / S4 的 pattern / S7 的 direction）。

## ETF 池

主流权益 ETF：
- 当日 `size ≥ 20 亿元`
- 近 20 交易日均 `amount ≥ 5000 万元`

两条件取 AND，阈值全部 CLI 可调。

## 数据回看窗口 · 40 自然日

S1/S7 需要 20 交易日历史；20 交易日 ≈ 28 自然日；取 40 自然日留 buffer，覆盖长假、临时休市、上市未满 20 日等场景。不引入交易日历接口。

## 三条信号

> 📌 **命名说明**：本 skill 内部用 `S1` / `S4` / `S7` 作为信号代号（对应 `scripts/signals/s1.py` 等文件、CSV 里 `signal_type` 列的取值、以及"设计文档中信号编号"的历史沿革）。这些编号**只出现在代码和 CSV 输出中**，**绝对不要在给用户的呈现文本里出现**。呈现时必须使用下方三条中文名称：
> - S1 → 「净申赎异动」
> - S4 → 「折溢价背离」
> - S7 → 「连续同向」

### 信号一 · 净申赎异动（内部代号 S1，Z-score）
对每只池内 ETF，用 T-1 至 T-L（L=20，不含 T）的 `net_redemption` 计算均值/标准差，得到 T 日 z 值。**|z| ≥ z_threshold (默认 2.0)** 命中。`sigma < 1` 时跳过该 ETF 的判断。

### 信号二 · 折溢价背离（内部代号 S4）
`|discount_rate| ≥ discount_threshold (默认 0.003)` **且** 与当日 `net_redemption` 符号相反。两种情形：
- 溢价 + 净申购 → `premium_buy`
- 贴水 + 净赎回 → `discount_sell`

### 信号三 · 连续同向（内部代号 S7）
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

## Agent 触发流程（本 skill 的正式用法）

用户提问命中「何时触发」后，按以下四步执行，**不要跳步、不要问用户参数**：

### Step 1 · 决定扫描日期

- 用户明说了日期（"20260730"、"上周五"）→ 换算为 `YYYYMMDD` 用作 `--date`
- 用户没说 → 省略 `--date`，让 radar 自动取 `flow_df` 里最新可用日
- 用户说"最近"、"这几天"→ 仍然按单日跑（本 skill 不做多日回补）

### Step 2 · 调用（推荐一行）

```bash
cd /Users/since/Code/quantskills/skill-etf-flow-radar && \
set -a && source ~/.zshrc >/dev/null 2>&1 && set +a && \
/opt/miniconda3/envs/pandaai/bin/python scripts/radar.py [--date YYYYMMDD]
```

- 环境是 conda `pandaai`（Python 3.10，`panda_data` 已装）
- 凭证 `PANDA_DATA_USERNAME` / `PANDA_DATA_PASSWORD` 在 `~/.zshrc`（非交互 shell 须显式 source）
- **不用再传 `--fetch_days`**：v0.2 起 `load_flow` / `load_daily` 已内部按月分段，跨月不再返回空
- exit code：0 OK / 1 panda_data 异常 / 2 该日无 flow 数据 / 3 池空 / 4 字段自检失败

### Step 3 · 读取输出

产物固定在两个位置：

- `output/radar_YYYYMMDD.csv` —— 全量命中，字段见「输出结果」
- `output/radar_YYYYMMDD.md` —— Top 10 + 三个信号分组

**直接读 `.md`** 拿排行，需要数值细节（如 z、净申购绝对额）再看 `.csv`。

### Step 4 · 用「样式② 结构化播报」呈现

**不要**把 CSV 路径丢给用户，也**不要**贴 markdown 原文。**不要**在呈现里出现 `S1`/`S4`/`S7` 这样的内部代号，一律使用中文信号名。按下列固定五段呈现：

```
今日 ETF 资金流扫描（YYYYMMDD，池 N 支）

▎主线判断：<一句话，见下表>

▎净申购最强 · 关注做多方向
- <symbol>：z+X.XX，单日净申购 X.X 亿（为 20 日均值 X.X 倍）
- <symbol>：z+X.XX，X.X 亿
- <symbol>：z+X.XX（规模较小/较大，异动明显）

▎净赎回最强 · 关注做空/避险方向
- <symbol>：z-X.XX
- <symbol>：z-X.XX
- <symbol>：z-X.XX

▎折溢价背离：X 条 <如 0 且日期≥20260611，须加数据说明句>
▎连续同向 3 日：X 条 <若有，取 top3 附 ratio 与方向>
```

**主线判断话术表**（判断依据是「净申赎异动」信号的正负分布）：

| 场景 | 话术 |
|---|---|
| 净申赎异动一边倒净申购（申购数≥赎回数×2） | 「资金整体做多，风险偏好抬升」 |
| 净申赎异动一边倒净赎回（赎回数≥申购数×2） | 「资金整体撤离，避险情绪主导」 |
| 净申赎异动双向命中相近 | 「资金流分歧，无一边倒共识」 |
| 净申赎异动命中 ≤ 2 条 | 「今日资金流平淡，无显著异动」 |
| 池空（exit 3） | 「今日无满足流动性门槛的 ETF 数据，可能是节假日/停市」 |

**数据侧特殊情况**（Agent 必须显式说明，避免误报市场现象）：

- **`discount_rate` 从 2026-06-11 起 panda_data 返回全空** → 用 20260611 及之后的日期跑时，「折溢价背离」恒为 0。呈现时须写："折溢价背离：0 条（panda_data 自 2026-06-11 起 `discount_rate` 全空，非市场信号缺失）"
- **exit 1（panda_data 5xx）** → 不要重试超过一次，直接告诉用户"panda_data 服务暂不可用，稍后再试"
- **exit 2（该日无 flow 数据）** → 提示用户"该日期无 ETF 一级申赎数据，可能是非交易日"

**收尾一句**（可选）：如果用户看起来还会追问，加"如需看具体 ETF 细节、调阈值、或换日期，告诉我"。

## 阈值调整（用户主动要求时才调）

用户明确说"放宽/收紧阈值"或"我要看 z=1.5 的"时，透传对应 CLI 参数即可：

```bash
python scripts/radar.py --date YYYYMMDD \
    --z_threshold 1.5 --discount_threshold 0.002 \
    --consec_days 3 --ratio_threshold 2.0 \
    --min_size 2e9 --min_amount 5e7 --lookback 20
```

否则一律用默认阈值，不要主动"帮用户放宽"。

## 开发者入口（不用于 Agent 触发路径）

```bash
# 字段自检（升级 panda_data 后手动跑一次）
python -m scripts.data --self-check --date 20260730

# 单元测试
pytest tests/ -v
```

## 验收要求
- **无未来函数**：S1/S7 历史窗口不含 T 日，`test_s1_no_lookahead` / `test_s7_no_lookahead_on_baseline` 覆盖
- **单元测试全通过**：`pytest tests/` 无失败
- **字段自检通过**：`python -m scripts.data --self-check --date <近期日>` 返回 0
- **端到端跑通**：至少一个真实日期能产出 CSV + MD，命中数**可为 0**（不为了凑数刻意放宽阈值）
- **文档一致**：本文件的信号公式与 `scripts/signals/` 包中 `s1.py` / `s4.py` / `s7.py` 一致
- **跨月不返回空**：`load_flow` / `load_daily` 内部按月分段，`test_load_daily_cross_month_splits_and_concats` 等 4 项测试覆盖

## 已知局限
- `net_redemption` / `discount_rate` 正负号方向依赖首次实测校准；若反向，修改 `scripts/signals/{s1,s4,s7}.py` 中对应方向判断（v0.1.0 未抽出 `SIGN_FLIP` 常量，需要动手编辑三处比较；v0.2 计划补上）。
- **`discount_rate` 自 2026-06-11 起 panda_data 返回全空**，「折溢价背离」信号对之后日期恒 0 命中；这不是本 skill 的 bug，是上游数据缺失，Agent 呈现时须显式说明。
- 不含"触限打满"作为独立信号，仅作参考列 `limit_hit_flag`。
- 不接入 ETF 基础信息接口，`name` 列留空。
- 不做批量日期回补；如需回补，外层 shell 循环即可。
- 不含图表输出；v2 再加。
- `get_fund_etf_cr_net` 的响应示例文本与表格字段对不上（示例贴的是股票股东减持数据）；设计一律以表格为准，首次实测校准。

