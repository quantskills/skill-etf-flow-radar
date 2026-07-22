# skill-etf-flow-radar 设计文档

**日期**：2026-07-22
**状态**：设计定稿，待用户 review 后进入实现规划
**产物类型**：Claude Code skill（Python CLI 脚本 + SKILL.md 描述）

---

## 1. 定位与目标

**skill 名**：`skill-etf-flow-radar`
**用途**：ETF 净申赎资金流雷达。**每日盘后**扫描主流权益 ETF，输出当日资金流"异动榜"——包括净申赎异常、折溢价背离、连续同向三类经典信号。

**适用场景（写进 SKILL.md）**：
- 每日盘后想快速看"哪些 ETF 今天有异常资金流入/流出"
- 想快速识别"折溢价 + 一级申赎方向背离"的套利/恐慌信号
- 想跟踪某只 ETF 是否处于"连续多日同向"的趋势中

**非目标（本 skill 明确不做）**：
- 单标的深度分析报告
- 把 ETF 净申赎加工为 Alpha 因子做 IC/回测
- 批量日期回补（v2 再加）
- 可视化图表（v2 再加）
- 触限本身作为独立信号（仅作参考列）

---

## 2. 数据依赖

三个 panda_data 接口，字段口径以 `references/need_used_api.md` 表格为准：

| 接口 | 用途 | 关键字段 |
|---|---|---|
| `get_fund_etf_cr_net` | 一级市场净申赎（**核心**） | `symbol, date, net_redemption, shares, shares_change, size, size_change, net_inflow, unit_nav, close` |
| `get_fund_etf_cr_limits` | 当日申赎限额 | `symbol, date, net_purchase_limit, net_redemption_limit, purchase_limit, redemption_limit` |
| `get_fund_daily` | 二级市场行情 + 折溢价 | `symbol, date, close, amount, discount_rate, limit_up, limit_down, shares` |

**术语约定**（本 skill 内部一致，实测后如反向仅需改 sign_flip 常量）：
- **`net_redemption`**：一级市场当日净额。**正 = 净申购，负 = 净赎回**。
- **`discount_rate`**：**正 = 贴水（价格低于净值），负 = 溢价**。

**字段疑点（首次实测须校准）**：
`need_used_api.md` 中 `get_fund_etf_cr_net` 的响应表格给出的是 ETF 字段（`net_redemption`/`shares_change`/`net_inflow`…），但响应示例文本却贴的是股票代码 + 股东减持字段。设计一律以**表格**为准；实现阶段先跑一次 `python -m scripts.data --self-check` 确认实际列名，若不一致必须停下与用户对齐。

---

## 3. 关键决策

### 3.1 ETF 池 · 主流权益 ETF

- 当日 `size ≥ min_size`（默认 **2e9 = 20 亿元**）
- 近 20 交易日均 `amount ≥ min_amount`（默认 **5e7 = 5000 万元**）
- 两个条件取 AND

阈值全部通过 CLI 参数暴露，MVP 阶段可放宽/收紧。

### 3.2 数据回看窗口 · 40 自然日

**为什么是 40 自然日？记录在此避免后续遗忘。**

- S1 净申赎异动的 Z-score 要 **20 个交易日**样本；S7 连续同向要 3 日 + 累计对比 20 日均 → **至少 20 交易日**历史。
- A 股每 5 个自然日约含 3.5 个交易日，20 交易日 ≈ **28 自然日**。取 **40 自然日** 留 ~12 天 buffer，用于覆盖：
  - 长假（春节/国庆最长 9 天连休）
  - 临时休市
  - 部分 ETF 上市未满 20 日时的补齐容差
- **不引入** panda_data 交易日历接口（未在 `need_used_api.md` 声明的接口一律不加）；实现方法是"按自然日往前推 40 天拉数据，df 内部按 date 排序取实际交易日"。

`--fetch_days` 参数暴露，若未来 lookback 变大可等比放大。

### 3.3 三条信号（MVP 只做这三条）

设当日为 `T`，回看窗口 `L`（默认 20 交易日）。

#### S1 · 净申赎异动（Z-score）

```
history = flow_df[symbol=s, date ∈ (T-L, T-1)].net_redemption   # 不含 T 自身，防偷看
mu    = history.mean()
sigma = history.std(ddof=1)

命中：  |z| ≥ z_threshold  (默认 2.0)
其中    z = (flow_df[symbol=s, date=T].net_redemption - mu) / sigma

signal_value = z
方向：       z > 0 → 异常净申购流入；z < 0 → 异常净赎回流出
```

**边界**：`sigma < ε (ε=1)` 时**跳过该 ETF 的 S1 判断**（仍可参与 S4/S7）。原因：近 20 日几乎无申赎，Z-score 分布无意义。

#### S4 · 折溢价背离

```
dr = daily_df[symbol=s, date=T].discount_rate         # 正=贴水, 负=溢价
nr = flow_df [symbol=s, date=T].net_redemption        # 正=净申购, 负=净赎回

命中：  |dr| ≥ discount_threshold  (默认 0.003 = 0.3%)
   AND  dr 与 nr 方向相反 (dr * nr < 0)

两种情形：
  (a) 溢价 (dr<0) + 净申购 (nr>0)  → premium_buy    (一级套利吸筹型)
  (b) 贴水 (dr>0) + 净赎回 (nr<0)  → discount_sell  (恐慌抛压型)

signal_value = |dr|
```

#### S7 · 连续同向

```
K = consec_days  (默认 3)
window = flow_df[symbol=s, date ∈ (T-K+1, T)].net_redemption   # 最近 K 天，含 T

hist    = flow_df[symbol=s, date ∈ (T-L, T-1)].net_redemption.abs()
mu_abs  = hist.mean()      # 用绝对值均值当分母，避免 0 附近除爆

命中：  (i)  window 全部 > 0 或 全部 < 0
   AND  (ii) |window.sum()| ≥ ratio_threshold × mu_abs  (默认 2.0)

signal_value = |window.sum()| / mu_abs        # 倍数，越大越强
方向：       window.sum() > 0 → inflow；< 0 → outflow
```

### 3.4 输出

每条命中一行，schema：

| 列 | 说明 |
|---|---|
| `trade_date` | 扫描日 T，YYYYMMDD |
| `symbol` | ETF 代码 |
| `name` | 留空（本 MVP 不接入基金基础信息接口） |
| `signal_type` | `S1` \| `S4` \| `S7` |
| `signal_value` | S1: z；S4: |dr|；S7: 倍数 |
| `abs_signal_value` | 用于分类排序（|z|/|dr|/倍数） |
| `net_redemption_T` | T 日净申赎额 |
| `size_T` | T 日规模 |
| `amount_T_avg20` | 近 20 日均成交额（池过滤依据） |
| `discount_rate_T` | T 日折溢价率 |
| `limit_hit_flag` | T 日是否触限（`net_purchase_limit`/`net_redemption_limit` 使用率 ≥ 90%），仅参考不作命中条件 |
| `detail_json` | 信号细节 JSON（如 S4 的 pattern、S7 的 direction/days/cum） |

**产物**：
- `output/radar_YYYYMMDD.csv`：完整命中榜。**排序方式**：先按 `signal_type` 分组（S1 → S4 → S7 的固定顺序），组内按 `abs_signal_value` 降序。不做跨 signal_type 的全局排序（三者量纲不同：|z| / |dr| / 倍数，硬排会失真）
- `output/radar_YYYYMMDD.md`：
  - 标题 + 扫描日 + 命中总数
  - Top 10 总榜（各 signal_type 内取头部拼装）
  - S1 / S4 / S7 三个小节，每个小节列出该类下命中的 ETF
  - 一段简短解读（"今日 X 只触发 S1，其中 Y 只为净申购方向..."）

一只 ETF 同日命中多条 → 多行，不去重合并。

---

## 4. 模块结构

```
skill-etf-flow-radar/
├── SKILL.md                    # skill 描述、字段表、使用方式、已知风险
├── skill.json                  # {name, version, tags}
├── references/
│   └── need_used_api.md        # 已有：三个 panda_data 接口规格
├── scripts/
│   ├── radar.py                # CLI 入口 + pipeline 编排（≤100 行）
│   ├── data.py                 # 三个接口封装 + 字段自检（≤120 行）
│   ├── universe.py             # 池过滤（≤60 行）
│   ├── signals.py              # S1 / S4 / S7 三个纯函数（≤200 行）
│   └── report.py               # CSV + MD 生成（≤150 行）
├── tests/
│   ├── test_signals.py         # 三个信号的单测（用构造 df）
│   └── test_universe.py        # 池过滤单测
└── output/                     # 运行产物（建议加 .gitignore）
    ├── radar_YYYYMMDD.csv
    └── radar_YYYYMMDD.md
```

**单文件硬阈值：250 行**。任一文件超过触发拆分（未来 review 依据）。

### 模块职责

- **`radar.py`**：argparse 解析 → 调用 `data.load_*` → `universe.filter` → 依次调 `signals.s1/s4/s7` → concat 命中 df → 交给 `report`
- **`data.py`**：三个 `load_*` 薄封装；一个 `self_check(date)` 函数比对返回列 vs 期望列
- **`universe.py`**：`filter_universe(flow_df, daily_df, date, min_size, min_amount) -> List[symbol]`
- **`signals.py`**：三个纯函数 `s1_net_flow_z / s4_discount_diverge / s7_consec_flow`，签名一致，返回统一 schema 的 DataFrame
- **`report.py`**：`write_csv(hits_df, path)` + `write_markdown(hits_df, path, meta)`

---

## 5. CLI

```bash
python scripts/radar.py [OPTIONS]

# 核心
--date YYYYMMDD              # 扫描日；默认 = 最近一个数据可用的交易日
                             # （用 get_fund_daily(today-7 ~ today) 探测；
                             #  若 get_fund_etf_cr_net 该日无数据 → 报错，不静默用旧数据）

# 三条信号阈值（默认 = 平衡档）
--z_threshold 2.0            # S1: |Z-score| ≥ 该值
--discount_threshold 0.003   # S4: |discount_rate| ≥ 0.3%
--consec_days 3              # S7: 连续同向天数 K
--ratio_threshold 2.0        # S7: 累计 / 20 日均绝对值 ≥ 该值

# ETF 池
--min_size 2e9               # 20 亿
--min_amount 5e7             # 5000 万

# 窗口
--lookback 20                # 交易日
--fetch_days 40              # 自然日

# 输出
--output_dir output          # 默认 ./output/
```

---

## 6. 错误处理

**fail-fast（脚本立刻退出）**：
- 接口异常 → 打印原文 + 建议，退出码 **1**
- `--date` 指定日 `get_fund_etf_cr_net` 无数据 → 退出码 **2**
- universe 为空 → 退出码 **3**
- 字段自检失败（实际列 ≠ 期望列）→ 打印 diff，退出码 **4**

**降级（继续但记 log）**：
- 单只 ETF 历史样本 < lookback → 跳过其 S1/S7 判断，stderr 记 `[skip]`
- `discount_rate` 缺失 → 跳过其 S4，记 `[skip-s4]`
- `get_fund_etf_cr_limits` 当日为空 → `limit_hit_flag` 全填 False，log warning

---

## 7. 测试

**单测（`tests/`，用构造 df，不依赖 panda_data）**：

`test_signals.py`：
- `test_s1_hit_high_z` · `test_s1_low_sigma_skip` · `test_s1_no_lookahead`
- `test_s4_premium_buy` · `test_s4_same_direction_no_hit` · `test_s4_below_threshold_no_hit`
- `test_s7_all_positive_hit` · `test_s7_direction_mixed_no_hit` · `test_s7_ratio_below_no_hit`

`test_universe.py`：
- `test_filter_by_size` · `test_filter_by_amount`（用近 20 日均，不用当日）· `test_filter_intersection`

**不写单测**：`data.py`（依赖真实 panda_data，属集成测试）；`report.py`（IO 层，肉眼可见）。

---

## 8. 验收要求（写进 SKILL.md）

- **无未来函数**：S1/S7 历史窗口显式不含 T 日，有 `test_s1_no_lookahead` 覆盖
- **单元测试全通过**：`pytest tests/` 无失败
- **字段自检通过**：`python -m scripts.data --self-check --date <近期日>` 不报错
- **端到端跑通**：至少一个真实日期能产出 `radar_YYYYMMDD.csv` + `radar_YYYYMMDD.md`；**命中数可为 0**（不为了凑数刻意放宽阈值）
- **文档一致**：SKILL.md 中"信号定义"公式与 `signals.py` 一致
- **单文件不超 250 行**

---

## 9. 已知局限（提前写进 SKILL.md）

- `net_redemption` / `discount_rate` 的正负号方向依赖首次实测校准；如反向，改一处 sign_flip 常量。
- 不含"触限打满"作为独立信号，仅作参考列 `limit_hit_flag`。
- 不接入 ETF 基础信息接口，`name` 列留空（未来若加入需先在 `need_used_api.md` 里声明新接口）。
- 不做批量日期回补（`--start_date/--end_date`）；如需回补，外层 shell 循环即可。
- 不含图表输出；如需可视化，v2 加 matplotlib。
- `get_fund_etf_cr_net` 响应示例与表格字段对不上（示例贴的是股票股东减持数据）；设计一律以表格为准，实测再校准。

---

## 10. 未来演进（v2 候选，非本次范围）

- 补充信号 S2（份额跳变）、S3（放量申购）、S5（一二级方向背离）、S6（触限打满作为独立信号）、S8（规模突破）
- 批量日期回补 + 信号历史频次统计
- 可视化图表（Top 10 条形图、折溢价 vs 净申赎散点、累计申赎曲线）
- 接入 ETF 基础信息（名称、跟踪指数、类型）用于分类和展示
- Alpha 因子研发方向：把 net_redemption / shares_change 加工成横截面因子做 IC/回测
