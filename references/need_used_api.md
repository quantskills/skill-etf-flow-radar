**0. get_fund_detail - 可选的基金基本信息增强**

本接口不参与资金流信号计算，仅用于补充基金名称和识别 QDII/跨境候选。当前
`panda_data` 客户端将其标记为“已废弃或未上线”，因此调用失败时必须降级，不能
阻断 radar。

最小使用字段：`symbol, name, is_qdii_fund`。`clearing_speed` 虽可能返回，但当前
接口文档没有给出其数值编码与 T+0/T+1 的可靠映射，**不得据此直接推断交易规则**。

交易口径仍需区分：跨境 ETF 二级市场买卖通常可按 T+0 理解，但申购/赎回确认、可用
时间和资金到账是另一套流程。本 skill 只标注候选，不替代具体产品公告。

**1. get_fund_etf_cr_limits - 获取ETF申赎限制数据**

**1.1. 方法名：get_fund_etf_cr_limits**

**1.2. 入参**

| 字段 | 类型 | 描述 | 是否必填 |
|:---|:---|:---|:---|
| start_date | string | 开始日期(交易日期)，格式 YYYYMMDD | 必填 |
| end_date | string | 结束日期(交易日期)，格式 YYYYMMDD | 必填 |
| symbol | Optional[Union[string, List[string]]] | 基金代码 | 非必填 |
| exchange | Optional[Union[string, List[string]]] | 交易市场 | 非必填 |
| fields | Optional[Union[string, List[string]]] | 返回字段 | 非必填 |

**1.3. 响应参数**

| 字段 | 类型 | 描述 |
|:---|:---|:---|
| symbol | string | 交易代码 |
| date | string | 交易日期 |
| exchange | string | 交易市场 |
| nav | float | 基金份额净值 |
| min_cr_unit | integer | 最小申赎单位 |
| purchase_limit | integer | 申购上限 |
| redemption_limit | integer | 赎回上限 |
| net_purchase_limit | integer | 净申购上限 |
| net_redemption_limit | integer | 净赎回上限 |
| account_net_purchase | integer | 单账户净申购上限 |
| account_net_redemption | integer | 单账户净赎回上限 |
| account_purchase_limit | integer | 单账户申购上限 |
| account_redemption_limit | integer | 单账户赎回上限 |

**1.4. 使用示例**

**1.4.1. 获取一段时间内的数据**

```python
import panda_data
result = panda_data.get_fund_etf_cr_limits(
    start_date='20250501',
    end_date="20250508"
)
print(result)
```

**响应示例**

```text
symbol  date  exchange  min_cr_unit  nav  purchase_limit  redemption_limit  account_net_purchase  account_net_redemption  account_purchase_limit  account_redemption_limit  net_purchase_limit  net_redemption_limit
0  159001.SZ  20250506  SZ  1  100.0  None  None  5000000.0  None  None  None  15000000.0  2000000.0
1  159003.SZ  20250506  SZ  1  100.0  None  None  3000000.0  None  None  None  3000000.0  50000.0
2  159005.SZ  20250506  SZ  1  100.0  2000000.0  2000000.0  200000.0  2000000.0  2000000.0  2000000.0  2000000.0  50000.0
3  159150.SZ  20250506  SZ  1000000  1.1158  None  30000000.0  None  None  None  None  None  None
4  159201.SZ  20250506  SZ  1000000  0.9561  None  500000000.0  None  None  None  None  None  None
5  159202.SZ  20250506  SZ  1000000  1.0042  500000000.0  50000000.0  None  None  None  None  None  None
6  159206.SZ  20250506  SZ  1000000  0.8777  None  15000000.0  None  None  None  None  None  None
7  159207.SZ  20250506  SZ  500000  0.9958  None  110000000.0  None  None  None  None  None  None
8  159209.SZ  20250506  SZ  1000000  0.9646  None  100000000.0  None  None  None  None  None  None
9  159211.SZ  20250506  SZ  2000000  1.0159  None  6000000.0  None  None  None  None  None  None
10  159212.SZ  20250506  SZ  2000000  1.0178  None  44000000.0  None  None  None  None  None  None
11  159213.SZ  20250506  SZ  1500000  1.0355  None  30000000.0  None  None  None  None  None  None
12  159215.SZ  20250506  SZ  3000000  0.9704  None  300000000.0  None  300000000.0  None  300000000.0  None  300000000.0
13  159216.SZ  20250506  SZ  1500000  1.0439  None  15000000.0  None  None  None  None  None  None
14  159217.SZ  20250506  SZ  1000000  1.0159  None  126000000.0  None  None  None  None  None  None
15  159222.SZ  20250506  SZ  1000000  1.0125  None  100000000.0  None  None  None  None  None  None
16  159225.SZ  20250506  SZ  1000000  1.0124  None  20000000.0  None  None  None  None  None  None
17  159231.SZ  20250506  SZ  500000  0.9956  None  30000000.0  None  None  None  None  None  None
18  159232.SZ  20250506  SZ  2000000  0.9899  None  900000000.0  None  None  None  None  None  None
19  159235.SZ  20250506  SZ  1000000  0.9905  None  300000000.0  None  None  None  None  None  None
```


**2. get_fund_etf_cr_net - 获取ETF净申赎数据**

**2.1. 方法名：get_fund_etf_cr_net**

**2.2. 入参**

| 字段 | 类型 | 描述 | 是否必填 |
|:---|:---|:---|:---|
| start_date | string | 开始日期(交易日期)，格式 YYYYMMDD | 必填 |
| end_date | string | 结束日期(交易日期)，格式 YYYYMMDD | 必填 |
| symbol | Optional[Union[string, List[string]]] | 基金代码 | 非必填 |
| exchange | Optional[Union[string, List[string]]] | 交易市场 | 非必填 |
| fields | Optional[Union[string, List[string]]] | 返回字段 | 非必填 |

**2.3. 响应参数**

| 字段 | 类型 | 描述 |
|:---|:---|:---|
| symbol | string | 交易代码 |
| exchange | string | 交易市场 |
| date | string | 交易日期 |
| shares | float | 份额 |
| shares_change | float | 份额变动 |
| size | float | 规模 |
| size_change | float | 规模变动 |
| net_redemption | float | 净申赎 |
| unit_nav | float | 单位净值 |
| reference_net | float | 参考净值 |
| close | float | 收盘价 |
| vwap | float | 成交均价 |
| market_cap | float | 市值 |
| net_inflow | float | 资金净流入 |
| net_inflow_avg | float | 资金净流入(成交均价) |
| split_rate | float | 拆分折算比例 |
| currency_symbol | string | 货币种类 |
| notes | string | 备注 |

**2.4. 使用示例**

**2.4.1. 获取一段时间内的数据**

```python
import panda_data
result = panda_data.get_fund_etf_cr_net(
    start_date='20250501',
    end_date="20250508"
)
print(result)
```

**响应示例**

```text
symbol  info_date  end_date  name  currency  amount  ex_amount  sub_amount  occur_amount  ex_occur_amount  sub_occur_amount  total_amount  ex_balance  sub_balance  total_amount_ratio  high_debt_ratio_amount  related_amount  excess_amount
0  000002.SZ  20250401  20241231  万科A  CNY  9640958.26  243337.59  9397620.67  5015893.11  173180.42  4842712.69  7424999.26  184286.57  7240712.69  36.62  4989736.45  None  None
1  000002.SZ  20250823  20250630  万科A  CNY  10430848.57  321350.98  10109497.59  2375233.77  85052.39  2290181.38  8632172.11  258510.43  8373661.68  42.59  5409448.13  None  None
2  000006.SZ  20250426  20241231  深振业A  CNY  246700.0  0.0  246700.0  26415.46  0.0  26415.46  102958.33  0.0  102958.33  19.05  102958.33  0.0  0.0
3  000006.SZ  20250829  20250630  深振业A  CNY  None  0.0  0.0  None  0.0  0.0  None  0.0  0.0  None  None  None  None
4  000008.SZ  20250419  20241231  神州高铁  CNY  410665.0  0.0  410665.0  101000.0  0.0  101000.0  130450.16  0.0  130450.16  43.04  25000.0  0.0  78420.13
5  000008.SZ  20250827  20250630  神州高铁  CNY  280000.0  0.0  280000.0  32300.0  0.0  32300.0  130700.0  0.0  130700.0  44.57  8000.0  0.0  133356.0
6  000009.SZ  20250416  20241231  中国宝安  CNY  79000.0  None  79000.0  0.0  None  0.0  16065.99  None  16065.99  None  0.0  0.0  0.0
7  000009.SZ  20250829  20250630  中国宝安  CNY  None  None  0.0  None  None  0.0  None  None  0.0  None  None  None  None
8  000010.SZ  20250429  20241231  美丽生态  CNY  105000.0  105000.0  0.0  None  0.0  0.0  46070.0  46070.0  0.0  152.65  None  None  None
9  000010.SZ  20250829  20250630  美丽生态  CNY  100000.0  None  100000.0  0.0  None  0.0  8140.0  None  8140.0  26.62  None  None  None
10  000011.SZ  20250329  20241231  深物业A  CNY  567000.0  None  567000.0  47346.86  None  47346.86  369146.63  None  369146.63  109.81  369146.63  None  None
11  000011.SZ  20250829  20250630  深物业A  CNY  None  None  0.0  None  None  0.0  None  None  0.0  None  None  None  None
12  000012.SZ  20250428  20241231  南玻A  CNY  1809583.0  0.0  1809583.0  284521.0  0.0  284521.0  820718.0  0.0  820718.0  60.63  68460.0  0.0  0.0
13  000012.SZ  20250819  20250630  南玻A  CNY  1790428.0  0.0  1790428.0  141558.0  0.0  141558.0  813954.0  0.0  813954.0  61.59  65173.0  0.0  0.0
14  000016.SZ  20250415  20241231  深康佳A  CNY  2176225.0  1237370.0  938855.0  684825.0  594755.0  90070.0  1244164.0  851125.0  393039.0  525.04  1244164.0  800000.0  1125681.0
15  000016.SZ  20250829  20250630  深康佳A  CNY  2001305.0  1076870.0  924435.0  29229.0  2249.0  26980.0  1202815.0  844256.0  358559.0  646.01  1202815.0  800000.0  1084332.0
16  000021.SZ  20250425  20241231  深科技  CNY  1679627.0  28800.0  1650827.0  477419.59  19200.0  458219.59  420207.04  24000.0  396207.04  35.38  219867.0  0.0  0.0
17  000021.SZ  20250828  20250630  深科技  CNY  1604627.0  28800.0  1575827.0  242601.58  17760.0  224841.58  449932.7  27360.0  422572.7  36.5  294481.8  0.0  0.0
18  000022.SZ  20250403  20241231  深赤湾A  CNY  2992037.43  364244.65  2627792.78  8316.0  0.0  8316.0  1448370.16  34240.58  1414129.58  23.55  1310704.38  34240.58  None
19  000022.SZ  20250830  20250630  深赤湾A  CNY  2602785.64  52387.32  2550398.32  None  0.0  0.0  1439243.13  34133.5  1405109.63  23.01  1305228.15  34133.5  0.0
```

**1. get_fund_daily - 获取场内基金日行情数据**

**1.1. 方法名：get_fund_daily**

**1.2. 入参**

| 字段 | 类型 | 描述 | 是否必填 |
|:---|:---|:---|:---|
| start_date | string | 开始日期(交易日期)，格式YYYYMMDD，eg:"20250101" | 必填 |
| end_date | string | 结束日期(交易日期)，格式YYYYMMDD，eg:"20251231" | 必填 |
| symbol | Optional[Union[string, List[string]]] | 基金代码，如 "159915.SZ" 或 \["159915.SZ", "510050.SH"\]，可传单个或列表，为空返回所有 | 非必填 |
| exchange | Optional[Union[string, List[string]]] | 交易市场，可传单个或多个交易所代码，如 "SZ" 或 \["SZ", "SH"\] | 非必填 |
| fields | Optional[Union[string, List[string]]] | 返回字段子集，自动补齐 symbol,date,exchange | 非必填 |

**1.3. 响应参数**

| 字段 | 类型 | 描述 |
|:---|:---|:---|
| symbol | string | 基金代码 |
| date | string | 交易日期 |
| exchange | string | 交易市场 |
| pre_close | float | 昨收盘价 |
| open | float | 开盘价 |
| high | float | 最高价 |
| low | float | 最低价 |
| close | float | 收盘价 |
| change | float | 涨跌额 |
| change_rate | float | 涨跌幅 |
| volume | float | 成交量 |
| amount | float | 成交金额 |
| discount | float | 贴水 |
| discount_rate | float | 贴水率 |
| cum_adj_factor | float | 累计复权因子 |
| price_limit | float | 涨跌幅限制 |
| limit_up | float | 涨停价 |
| limit_down | float | 跌停价 |
| actual_pre_close | float | 实际昨收盘价 |
| shares | float | 基金总份额 |
| exchange_shares | float | 场内份额 |
| floating_shares | float | 流通份额 |
| restricted_shares | float | 限售份额 |
| notes | string | 备注 |

**1.4. 使用示例**

**1.4.1. 按基金代码查询一段区间的日行情**

```python
import panda_data
result = panda_data.get_fund_daily(
    symbol="510050.SH",
    start_date="20250601",
    end_date="20250630",
)
print(result)
```

**响应示例**

```text
symbol  date  exchange  pre_close  open  high  low  close  change  change_rate  volume  amount  discount  discount_rate  cum_adj_factor
0  510050.SH  20250630  SH  2.795  2.795  2.809  2.787  2.807  0.012  0.0043  789373449  2.210765e+09  -0.0006  -0.000214  1.410444
1  510050.SH  20250627  SH  2.826  2.829  2.839  2.792  2.795  -0.031  -0.0110  735136118  2.068150e+09  0.0010  0.000358  1.410444
2  510050.SH  20250626  SH  2.832  2.830  2.834  2.822  2.826  -0.006  -0.0021  591542718  1.672621e+09  0.0005  0.000177  1.410444
3  510050.SH  20250625  SH  2.792  2.794  2.834  2.788  2.832  0.040  0.0143  974126991  2.736403e+09  -0.0018  -0.000636  1.410444
4  510050.SH  20250624  SH  2.762  2.762  2.810  2.761  2.792  0.030  0.0109  958847700  2.675962e+09  0.0009  0.000322  1.410444
5  510050.SH  20250623  SH  2.749  2.743  2.771  2.733  2.762  0.013  0.0047  755015613  2.076109e+09  -0.0010  -0.000362  1.410444
6  510050.SH  20250620  SH  2.733  2.735  2.755  2.734  2.749  0.016  0.0059  788226011  2.165197e+09  0.0003  0.000109  1.410444
7  510050.SH  20250619  SH  2.750  2.746  2.748  2.727  2.733  -0.017  -0.0062  806218699  2.206083e+09  0.0015  0.000549  1.410444
8  510050.SH  20250618  SH  2.753  2.752  2.760  2.739  2.750  -0.003  -0.0011  427677032  1.175527e+09  -0.0005  -0.000182  1.410444
9  510050.SH  20250617  SH  2.753  2.752  2.756  2.740  2.753  0.000  0.0000  571268034  1.570752e+09  -0.0001  -0.000036  1.410444
10  510050.SH  20250616  SH  2.746  2.737  2.757  2.735  2.753  0.007  0.0026  578828372  1.590303e+09  0.0011  0.000399  1.410444
11  510050.SH  20250613  SH  2.760  2.755  2.760  2.736  2.746  -0.014  -0.0051  651201333  1.788407e+09  -0.0003  -0.000109  1.410444
12  510050.SH  20250612  SH  2.762  2.758  2.766  2.741  2.760  -0.002  -0.0007  392650273  1.081966e+09  0.0002  0.000072  1.410444
13  510050.SH  20250611  SH  2.742  2.742  2.776  2.741  2.762  0.020  0.0073  585072791  1.616634e+09  -0.0005  -0.000181  1.410444
14  510050.SH  20250610  SH  2.756  2.758  2.767  2.735  2.742  -0.014  -0.0051  917943537  2.523181e+09  0.0020  0.000729  1.410444
15  510050.SH  20250609  SH  2.756  2.758  2.767  2.747  2.756  0.000  0.0000  709788198  1.957559e+09  -0.0010  -0.000363  1.410444
16  510050.SH  20250606  SH  2.754  2.758  2.768  2.751  2.756  0.002  0.0007  506736659  1.397082e+09  0.0005  0.000181  1.410444
17  510050.SH  20250605  SH  2.755  2.760  2.761  2.745  2.754  -0.001  -0.0004  416479500  1.146638e+09  0.0024  0.000871  1.410444
18  510050.SH  20250604  SH  2.748  2.751  2.764  2.748  2.755  0.007  0.0026  318023306  8.767604e+08  -0.0005  -0.000182  1.410444
19  510050.SH  20250603  SH  2.749  2.740  2.761  2.734  2.748  -0.001  -0.0004  501260254  1.377558e+09  0.0029  0.001054  1.410444
```

**1.4.2. 查询基金日行情，只取收盘价与涨跌停价**

```python
import panda_data
result = panda_data.get_fund_daily(
    symbol=["159915.SZ", "510050.SH"],
    start_date="20250610",
    end_date="20250613",
    fields=["close", "limit_up", "limit_down"],
)
print(result)
```

**响应示例**

```text
symbol  date  close
0  159915.SZ  20250613  2.020
1  159915.SZ  20250612  2.040
2  159915.SZ  20250611  2.038
3  159915.SZ  20250610  2.012
4  510050.SH  20250613  2.746
5  510050.SH  20250612  2.760
6  510050.SH  20250611  2.762
7  510050.SH  20250610  2.742
```
