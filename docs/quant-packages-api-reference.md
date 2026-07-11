# QuantKing 量化包官方 API 参考手册

> 文档定位：第三方库的历史/集成速查。V3 不再将 XTQuant 视为唯一数据源，也不以自动下单为默认产品能力；具体的目标数据与研究设计以 `DATA_ARCHITECTURE.md`、`RESEARCH_WORKFLOW.md` 为准。

> 本文档汇总 xtquant、qlib、backtrader 三个核心包的官方 API 用法，所有签名均经官方文档/源码核实。
> 最后更新: 2026-07-08
> 配套 Skill: `.trae/skills/quant-api-guide/SKILL.md`（精简速查版）

---

## 目录

1. [xtquant — 行情与交易](#一xtquant--行情与交易)
2. [qlib — 因子与模型](#二qlib--因子与模型)
3. [backtrader — 回测框架](#三backtrader--回测框架)

---

# 一、xtquant — 行情与交易

> 官方文档: https://dict.thinktrader.net/nativeApi/xtdata.html （行情）、https://dict.thinktrader.net/nativeApi/xttrader.html （交易）
> 下载页: https://dict.thinktrader.net/nativeApi/download_xtquant.html
> **无 PyPI、无官方 GitHub**，通过 miniQMT 安装目录 wheel 或官网 .rar 分发。最新版 xtquant_250807（2025-12-19），支持 Python 3.6–3.13。

## 1. xtdata 行情模块

### 1.1 连接管理

```python
from xtquant import xtdata

xtdata.connect(port=58610)    # 连接 miniQMT，默认端口 58610。多 QMT 共存时自动选端口
xtdata.disconnect()           # 断开，释放网络和缓存资源
```

- **必须先启动 miniQMT 客户端**，否则端口未监听连接失败。
- **每个工作线程需独立 DataProvider 实例**（本项目 `downloader.py` 已实现）。
- 并行下载循环中加 `time.sleep(0.02)` 防止连接过载。
- token 模式无需 miniQMT，通过 `xtdatacenter` 模块 + TOKEN 直连迅投行情服务器。

### 1.2 历史数据下载（必须先下载后读取）

```python
xtdata.download_history_data(stock_code, period='1d', start_time='', end_time='', incrementally=False)
xtdata.download_history_data2(stock_list, period, start_time='', end_time='', callback=None)  # 批量+回调
```

| 参数 | 类型 | 说明 |
|------|------|------|
| `stock_code` | str | 合约代码 `'000001.SZ'` 或板块名 `'沪深A股'` |
| `period` | str | `'1d'/'1m'/'5m'/'15m'/'30m'/'1h'/'1w'/'1mon'/'1q'/'1hy'/'1y'/'tick'` |
| `start_time` | str | `YYYYMMDD` 或 `YYYYMMDDHHMMSS`，空串=最早 |
| `end_time` | str | 同上，空串=最新 |
| `incrementally` | bool | `True` 仅下载缺失部分（增量更新必用，2023-11-09 起支持） |

- ⚠ `download_history_data2` 在某些 QMT 版本未加入 `__all__`，需手动改 xtdata.py。

### 1.3 行情数据获取

```python
xtdata.get_market_data_ex(
    field_list, stock_list, period='1d',
    start_time='', end_time='', count=-1,
    dividend_type='none', fill_data=True
)
# 返回: pd.DataFrame, index=时间, columns=(字段, 股票代码) 的 MultiIndex
```

| 参数 | 说明 |
|------|------|
| `field_list` | `['open','high','low','close','volume','amount']` |
| `count` | `-1` 全部，`>0` 限返回个数，`0` 不返回 |
| `dividend_type` | `'none'/'front'/'back'/'front_ratio'/'back_ratio'`，仅 K 线有效 |
| `fill_data` | 是否填充缺失数据 |

```python
xtdata.get_market_data(...)     # 旧版，返回 dict 嵌套 {field: {code: DataFrame}}
xtdata.get_full_tick(code_list) # 全推 Tick 快照（含买卖五档），VIP 有 transactionNum
```

### 1.4 订阅接口（实时）

```python
seq = xtdata.subscribe_quote(stock_code, period='1d', start_time='', end_time='', count=0, callback=on_data)
seq = xtdata.subscribe_whole_quote(code_list, callback=on_data)   # 全市场全推，code_list=['SH','SZ']
xtdata.unsubscribe_quote(seq)
xtdata.run()   # 阻塞维持运行，断开时抛异常
```

- 单股订阅建议 ≤50 个，多了用全推。
- callback: `on_data(datas)`，`datas = {stock_code: [data1, data2]}`。
- `subscribe_whole_quote` 订阅后先返回当前最新全推数据。

### 1.5 板块与合约信息

```python
xtdata.get_sector_list()                    # 所有板块名 ['沪深A股','沪深300','创业板',...]
xtdata.get_stock_list_in_sector('沪深A股')  # 全 A 股代码列表
xtdata.get_instrument_detail('000001.SZ')   # {'InstrumentName':..., 'OpenDate':..., 'ExchangeCode':...}
xtdata.download_sector_data()               # 下载板块数据到缓存（按周/日定期）
xtdata.get_divid_factors('000001.SZ')       # 除权除息因子
xtdata.download_financial_data2(codes)      # 下载财务数据
xtdata.get_financial_data(codes)            # 获取财务数据 {code: {table: DataFrame}}
```

### 1.6 dividend_type 复权方式

| 值 | 含义 |
|----|------|
| `none` | 不复权 |
| `front` | 前复权 |
| `back` | 后复权 |
| `front_ratio` | 等比前复权 |
| `back_ratio` | 等比后复权 |

> **本项目约定**: 默认后复权 `back`。前复权在增量更新时新除权事件会改变历史价，导致基准漂移；后复权历史价固定，适合回测连续性。

### 1.7 股票代码格式

`code.market`：`000001.SZ`(深主板)、`600000.SH`(沪主板)、`300001.SZ`(创业板)、`688001.SH`(科创板)、`830001.BJ`(北交所)。

---

## 2. xttrader 交易模块

```python
from xtquant.xttrader import XtQuantTrader, XtQuantTraderCallback
from xtquant.xttype import StockAccount
from xtquant import xtconstant

# 初始化
xt_trader = XtQuantTrader(path, session_id)   # path=userdata_mini 目录, session_id 每进程唯一
acc = StockAccount(account_id, 'STOCK')        # 沪港通 'HUGANGTONG', 深港通 'SHENGANGTONG'

# 生命周期
xt_trader.register_callback(callback)   # 注册回调类（继承 XtQuantTraderCallback）
xt_trader.start()                        # 启动交易线程
xt_trader.connect()                      # 返回 0=成功
xt_trader.subscribe(acc)                 # 订阅主推，返回 0=成功
xt_trader.run_forever()                  # 阻塞接收推送，Ctrl+C 退出
xt_trader.stop()

# 下单
order_id = xt_trader.order_stock(acc, stock_code, order_type, volume, price_type, price, strategy_name, remark)
seq = xt_trader.order_stock_async(...)   # 异步，返回 seq
xt_trader.cancel_order_stock(acc, order_id)      # 返回 0=成功,-1=失败
xt_trader.cancel_order_stock_async(acc, order_id)

# 查询
xt_trader.query_stock_asset(acc)                  # -> XtAsset (cash, fetch_balance, current_balance)
xt_trader.query_stock_orders(acc, cancelable_only=False)  # -> list[XtOrder]
xt_trader.query_stock_order(acc, order_id)        # 单个委托
xt_trader.query_stock_positions(acc)              # -> list[XtPosition]
xt_trader.query_stock_position(acc, stock_code)   # 按代码查持仓
xt_trader.query_stock_trades(acc)                 # -> list[XtTrade]
```

### 关键枚举 (xtconstant)

| 类别 | 常量 |
|------|------|
| 委托类型 | `STOCK_BUY`/`STOCK_SELL`；信用 `CREDIT_FIN_BUY`/`CREDIT_SLO_SELL`；ETF `ETF_PURCHASE`/`ETF_REDEMPTION` |
| 报价类型 | `FIX_PRICE`/`LATEST_PRICE`/`MARKET_SH_CONVERT_5_CANCEL`/`MARKET_SZ_CONVERT_5_CANCEL`/`MARKET_PEER_PRICE_FIRST` |
| 委托状态 | `ORDER_UNREPORTED=48`/`ORDER_REPORTED=50`/`ORDER_REPORTED_CANCEL=51`/`ORDER_CANCELED=54`/`ORDER_PART_SUCC=55`/`ORDER_SUCCEEDED=56`/`ORDER_JUNK=57` |

### 回调类 XtQuantTraderCallback

| 方法 | 说明 |
|------|------|
| `on_disconnected()` | 连接断开 |
| `on_stock_order(order)` | 委托回报 (`XtOrder`) |
| `on_stock_trade(trade)` | 成交变动 (`XtTrade`) |
| `on_order_error(order_error)` | 委托失败 (`XtOrderError`: order_id, error_id, error_msg) |
| `on_cancel_error(cancel_error)` | 撤单失败 |
| `on_order_stock_async_response(response)` | 异步下单回报 (seq, order_id) |
| `on_account_status(status)` | 账号状态推送 |

### 交易陷阱

- `query_stock_positions` 成功可能返回 `[]`（空列表，非 None），需区分查询失败与无持仓。
- 市价单仅在实盘生效，模拟环境不支持。
- 成交回调可能重复推送（网络重连触发全量同步），需自建数据库幂等去重。
- `session_id` 不同策略进程必须不同。

---

# 二、qlib — 因子与模型

> 官方文档: https://qlib.readthedocs.io/en/latest/
> GitHub: https://github.com/microsoft/qlib
> 安装: `pip install pyqlib`（Python 3.8–3.12）

## 1. 初始化

```python
import qlib
from qlib.constant import REG_CN   # 或 from qlib.config import REG_US
qlib.init(provider_uri="data/qlib_data_cn", region=REG_CN)
```

| 参数 | 说明 |
|------|------|
| `provider_uri` | qlib 数据目录路径（.bin 数据位置） |
| `region` | `REG_CN`='cn'(trade_unit=100, limit_threshold=0.099) / `REG_US`='us'(trade_unit=1) |
| `redis_host` | 默认 "127.0.0.1"，锁与缓存依赖 redis，连不上静默降级 |
| `kernels` | 表达式引擎进程数，调试设 1 |
| `exp_manager` | 实验管理器（如 MLflowExpManager） |

- ⚠ **不要在 qlib 仓库目录内 import qlib**，否则编译扩展找不到。
- `region` 必须与 `provider_uri` 数据匹配。

## 2. 数据获取 (qlib.data.D)

```python
from qlib.data import D

D.calendar(start_time='2010-01-01', end_time='2020-12-31', freq='day')
# -> [Timestamp('2010-01-04'), ...]

D.instruments(market='all')          # 股票池配置 {'market':'all','filter_pipe':[]}
D.instruments(market='csi300')

D.list_instruments(instruments=D.instruments('csi300'), start_time=..., end_time=..., as_list=True)
# -> ['SH600036', 'SZ000912', ...]

D.features(instruments, fields, start_time=..., end_time=..., freq='day', disk_cache=1)
# instruments: 股票列表 ['SH600000'] 或 D.instruments() 配置
# fields: 表达式字符串列表 ['$close', 'Ref($close,1)', 'Mean($close,5)']
# 返回: MultiIndex DataFrame (<datetime, instrument>)
# disk_cache: 0=跳过, 1=用缓存, 2=更新缓存
```

表达式也可用代码对象：

```python
from qlib.data.ops import Feature
f1 = Feature("high") / Feature("close")
D.features(["sh600519"], [f1], start_time="20200101")
```

### 过滤器

```python
from qlib.data.filter import NameDFilter, ExpressionDFilter
nameDFilter = NameDFilter(name_rule_re='SH[0-9]{4}55')
expressionDFilter = ExpressionDFilter(rule_expression='$close>Ref($close,1)')
instruments = D.instruments(market='csi300', filter_pipe=[nameDFilter, expressionDFilter])
```

## 3. 表达式算子（qlib/data/ops.py）

### 原始字段
`$close` `$open` `$high` `$low` `$volume` `$vwap` `$factor`

> qlib 价格为**前复权**（首日归一化为1），用 `$close/$factor` 还原真实价。

### 逐元素算子
`Abs` `Sign` `Log` `Mask(feature, instrument)` `Not` `ChangeInstrument(instrument, feature)`

### 二元算子
`Add` `Sub` `Mul` `Div` `Power` `Greater(max)` `Less(min)` `Gt` `Ge` `Lt` `Le` `Eq` `Ne` `And` `Or`

### 滚动算子（N=窗口天数）

| 算子 | 示例 | 说明 |
|------|------|------|
| `Ref(feature, N)` | `Ref($close, 60)` | N 天前的值；**N 为负表示未来**（用于标签） |
| `Mean(feature, N)` | `Mean($close, 5)` | N 日均值 |
| `Sum(feature, N)` | `Sum(Abs($close-Ref($close,1)), 5)` | N 日求和 |
| `Std(feature, N)` | `Std($close, 10)` | N 日标准差 |
| `Max(feature, N)` | `Max($high, 20)` | N 日最大 |
| `Min(feature, N)` | `Min($low, 20)` | N 日最小 |
| `Quantile(feature, N, qscore)` | `Quantile($close, 5, 0.8)` | N 日分位数 |
| `Rank(feature, N)` | `Rank($close, 5)` | 过去 N 日百分位 |
| `IdxMax(feature, N)` | `IdxMax($high, 20)` | 最高价距今天数 |
| `IdxMin(feature, N)` | `IdxMin($low, 20)` | 最低价距今天数 |
| `Slope(feature, N)` | `Slope($close, 5)` | 线性回归斜率 |
| `Rsquare(feature, N)` | `Rsquare($close, 5)` | 线性回归 R² |
| `Resi(feature, N)` | `Resi($close, 5)` | 线性回归残差 |
| `Corr(l, r, N)` | `Corr($close, Log($volume+1), 5)` | N 日皮尔逊相关 |
| `Delta(feature, N)` | - | 差分 |
| `EMA` / `WMA` | - | 指数/加权移动平均 |

> Slope/Rsquare/Resi 依赖 Cython 编译的 `qlib.data._libs.rolling`，未编译会报 ModuleNotFoundError。

### Alpha158 中 RSI 类因子实现（无直接 RSI 算子）
- `SUMP`: `Sum(Greater($close-Ref($close,1),0),N) / (Sum(Abs($close-Ref($close,1)),N)+1e-12)`
- `SUMN`: `Sum(Greater(Ref($close,1)-$close,0),N) / (Sum(Abs($close-Ref($close,1)),N)+1e-12)`
- `SUMD`: `SUMP - SUMN`（类 RSI）

## 4. DataHandler (Alpha158/Alpha360)

```python
from qlib.contrib.data.handler import Alpha158, Alpha360
```

### Alpha158
- ~158 因子：kbar(9个K线形态) + price + rolling(默认 windows=[5,10,20,30,60])
- rolling 支持: ROC, MA, STD, BETA(Slope), RSQR, RESI, MAX, LOW, QTLU, QTLD, RANK, RSV, IMAX, IMIN, CORR, CORD, CNTP, CNTN, CNTD, SUMP, SUMN, SUMD, VMA, VSTD, WVMA, VSUMP, VSUMN, VSUMD
- 默认标签: `Ref($close,-2)/Ref($close,-1)-1`（未来第2日收益）
- 默认 `infer_processors=[]`，需手动配归一化

### Alpha360
- 360 特征：最近 60 日 OHLCV+VWAP，用最新收盘价归一化（CLOSE0=1, VOLUME0=1）
- 标签同 Alpha158

### 自定义 Handler

```python
data_handler_config = {
    "start_time": "2008-01-01", "end_time": "2020-08-01",
    "fit_start_time": "2008-01-01", "fit_end_time": "2014-12-31",  # 必须仅用训练集
    "instruments": "csi300",
}
```

继承 `DataHandlerLP` 重写 `get_feature_config()` / `get_label_config()` 返回 `(fields_list, names_list)`。

## 5. DatasetH 数据分段

```python
from qlib.data.dataset import DatasetH
from qlib.utils import init_instance_by_config

dataset_config = {
    "class": "DatasetH", "module_path": "qlib.data.dataset",
    "kwargs": {
        "handler": {"class": "Alpha158", "module_path": "qlib.contrib.data.handler",
                    "kwargs": data_handler_config},
        "segments": {
            "train": ("2008-01-01", "2014-12-31"),
            "valid": ("2015-01-01", "2016-12-31"),
            "test":  ("2017-01-01", "2020-08-01"),
        },
    },
}
dataset = init_instance_by_config(dataset_config)
dataset.prepare(["train","valid"], col_set=["feature","label"], data_key=DataHandlerLP.DK_L)
```

## 6. 模型训练 (LGBModel)

```python
from qlib.contrib.model.gbdt import LGBModel   # 类名是 LGBModel

model = LGBModel(
    loss="mse",               # 或 "quantile"
    colsample_bytree=0.8879, learning_rate=0.0421, subsample=0.8789,
    lambda_l1=205.6999, lambda_l2=580.9768,
    max_depth=8, num_leaves=210, num_threads=20,
)
model.fit(dataset)
pred_score = model.predict(dataset)   # pd.Series, index=<datetime,instrument>
model.get_feature_importance()
```

### Workflow 完整流程

```python
from qlib.utils import init_instance_by_config, flatten_dict
from qlib.workflow import R
from qlib.workflow.record_temp import SignalRecord, PortAnaRecord

model = init_instance_by_config(task["model"])
dataset = init_instance_by_config(task["dataset"])

with R.start(experiment_name="workflow"):
    R.log_params(**flatten_dict(task))
    model.fit(dataset)
    recorder = R.get_recorder()
    sr = SignalRecord(model, dataset, recorder)
    sr.generate()   # 生成预测信号 + IC 分析
```

## 7. 策略与回测

### TopkDropoutStrategy

```python
from qlib.contrib.strategy import TopkDropoutStrategy
strategy = TopkDropoutStrategy(topk=50, n_drop=5, signal=pred_score)
# signal: pd.Series/DataFrame, index=<datetime,instrument>, 含 score 列
# 持有 Topk 只，每日卖出排名跌出前 K 的 Drop 只、买入排名最高 Drop 只
```

### backtest_daily（简便）

```python
from qlib.contrib.evaluate import backtest_daily, risk_analysis
report, positions = backtest_daily(start_time="2017-01-01", end_time="2020-08-01", strategy=strategy)
# risk_analysis 返回: mean, std, annualized_return, information_ratio, max_drawdown
analysis = risk_analysis(report["return"] - report["bench"])
```

### backtest（详细，含 executor）

```python
from qlib.backtest import backtest, executor
EXECUTOR_CONFIG = {"time_per_step": "day", "generate_portfolio_metrics": True}
backtest_config = {
    "start_time": "2017-01-01", "end_time": "2020-08-01",
    "account": 100000000, "benchmark": "SH000300",
    "exchange_kwargs": {
        "freq": "day", "limit_threshold": 0.095, "deal_price": "close",
        "open_cost": 0.0005, "close_cost": 0.0015, "min_cost": 5,
    },
}
executor_obj = executor.SimulatorExecutor(**EXECUTOR_CONFIG)
portfolio_metric_dict, indicator_dict = backtest(executor=executor_obj, strategy=strategy, **backtest_config)
report_normal, positions_normal = portfolio_metric_dict.get("day")
```

### qrun 命令行工作流

```bash
qrun configuration.yaml
# 调试: python -m pdb qlib/cli/run.py <config.yaml>
```

YAML 中 `signal: <PRED>` 占位符自动替换为模型预测。

## 8. 数据格式与转换

### .bin 格式
- 纯 float32 小端序列，首 4 字节存储日历起始索引 `date_index`。
- 目录: `calendars/day.txt` + `instruments/all.txt`(code\tstart\tend) + `features/<code>/*.day.bin`
- 停牌日 open/close/high/low/volume 设为 NaN。

### dump_bin.py（CSV/Parquet → .bin）

```bash
python scripts/dump_bin.py dump_all \
  --data_path ~/.qlib/my_data \
  --qlib_dir ~/.qlib/qlib_data/ \
  --include_fields open,close,high,low,volume,factor \
  --file_suffix .csv      # 或 .parquet
  --symbol_field_name symbol \
  --date_field_name date
```

子命令: `dump_all`(全量) / `dump_fix`(修复 instruments) / `dump_update`(增量)。

### 数据健康检查

```bash
python scripts/check_data_health.py check_data --qlib_dir ~/.qlib/qlib_data/cn_data
```

---

# 三、backtrader — 回测框架

> 官方文档: https://www.backtrader.com/docu
> GitHub: https://github.com/mementum/backtrader（最后版 1.9.78.123，已停更）
> ⚠ 兼容性: 需 `numpy<1.24`（用了已删除的 np.float/np.int）和 `pandas<1.5`

## 1. Cerebro 引擎

```python
cerebro = bt.Cerebro(**kwargs)   # preload=True, runonce=True, stdstats=True

cerebro.adddata(data)
cerebro.resampledata(data, timeframe=..., compression=...)
cerebro.addstrategy(MyStrategy, param1=value1)
cerebro.optstrategy(MyStrategy, param1=range(10,20))   # 优化
cerebro.addanalyzer(ancls, _name='xx', *args, **kwargs)
cerebro.addobserver(obscls, *args, **kwargs)
cerebro.addsizer(sizercls, *args, **kwargs)

cerebro.broker.setcash(100000)                          # 别名 set_cash，默认 10000
cerebro.broker.getcash()                                # 别名 get_cash
cerebro.broker.getvalue()                               # 别名 get_value
cerebro.broker.setcommission(commission=0.0, ...)       # 简单佣金
cerebro.broker.addcommissioninfo(comminfo, name=None)   # 自定义 CommInfo 实例
cerebro.broker.set_slippage_perc(perc, slip_open=True, ...)  # perc=绝对小数(0.01=1%)
cerebro.broker.set_slippage_fixed(fixed, ...)
cerebro.broker.set_coc(coc)       # Cheat-On-Close
cerebro.broker.set_coo(coo)       # Cheat-On-Open
cerebro.broker.getposition(data)  # 返回该 data 的 Position

results = cerebro.run()   # 返回 list[strategy]；优化返回 list[list]
cerebro.plot()
```

**执行逻辑**: 每 next 周期 → ① 投递 store 通知 → ② 投递已收盘的下一组 bar → ③ 通知 broker 订单/交易/现金 → ④ broker 执行挂单 → ⑤ 调 strategy.next。
> 关键: 步骤②投递的 bar **已发生**，策略在⑤发出的订单**无法**当根成交，只能 x+1（下一根）执行。Market 单用下一根 open 成交。

## 2. Strategy 类

```python
class backtrader.Strategy(*args, **kwargs)
    # 生命周期: __init__ → start → prenext → nextstart → next → stop

    def __init__(self):        # 创建指标、属性；不可在此下单
    def start(self):           # 回测开始前
    def prenext(self):         # 最小周期未满足时（默认 no-op）
    def nextstart(self):       # 最小周期首次满足（默认调 next）
    def next(self):            # 主逻辑：每根满足最小周期的 bar
    def stop(self):            # 回测结束前

    def notify_order(self, order)
    def notify_trade(self, trade)
    def notify_cashvalue(self, cash, value)
    def notify_fund(self, cash, value, fundvalue, shares)
    def notify_store(self, msg, *args, **kwargs)
    def notify_timer(self, timer, when, *args, **kwargs)
```

### 下单方法

```python
buy(data=None, size=None, price=None, plimit=None, exectype=None,
    valid=None, tradeid=0, oco=None, trailamount=None, trailpercent=None,
    parent=None, transmit=True)
sell(...)   # 同 buy
close(data=None, size=None)                    # 平掉现有仓位
cancel(order)

# 目标仓位系列
order_target_size(data=None, target=0)
order_target_value(data=None, target=0.0, price=None)
order_target_percent(data=None, target=0.0)

# 仓位
getposition(data=None, broker=None)    # -> Position(.size, .price, .adjbase)
getsizer() / setsizer(sizer) / getsizing(data=None, isbuy=True)
getdatanames() / getdatabyname(name)
```

### 成员属性

- `self.params` / `self.p`: 策略参数
- `self.datas`: 数据数组；`self.data`/`self.data0`/`self.datas[0]`；`self.dataX`=`self.datas[X]`
- `self.dnames.xxx` / `self.dnames['xxx']`: 按名访问
- `self.broker`: broker 引用
- `self.position`: data0 当前仓位（属性，`.size`/`.price`）
- `len(self)`: = datas[0] 长度

### params 声明

```python
params = (('maperiod', 15), ('printlog', False))
# 访问: self.params.maperiod 或 self.p.maperiod
```

### notify_order 典型用法

```python
def notify_order(self, order):
    if order.status in [order.Submitted, order.Accepted]:
        return
    if order.status == order.Completed:
        if order.isbuy():
            self.buyprice = order.executed.price
            self.buycomm = order.executed.comm
        # order.executed.price / .value / .comm / .size
    elif order.status in [order.Canceled, order.Margin, order.Rejected]:
        pass
    self.order = None
```

## 3. PandasData 数据源

```python
class PandasData(feed.DataBase):
    params = (
        ('datetime', None),     # None=用 DataFrame index
        ('open', -1), ('high', -1), ('low', -1),
        ('close', -1), ('volume', -1), ('openinterest', -1),
    )
```

| 取值 | 含义 |
|------|------|
| `None` | datetime: 用 index；其他: 列不存在 |
| `-1` | 自动检测（按名称匹配 open/high/low/close/volume） |
| `>=0` | DataFrame 数值列索引 |
| 字符串 | DataFrame 列名 |

```python
data = bt.feeds.PandasData(dataname=df)   # df index 须为 DatetimeIndex
data = bt.feeds.PandasData(dataname=df, name='000001')   # 命名便于多数据
```

## 4. 指标（__init__ 创建，next 读 [0]/[-1]）

| 指标 | 签名 | 说明 |
|------|------|------|
| `SMA` | `bt.indicators.SMA(data.close, period=30)` | 简单移动平均，默认 period=30 |
| `EMA` | `bt.indicators.EMA(data.close, period=30)` | 指数移动平均 |
| `MACD` | `bt.indicators.MACD(data.close, period_me1=12, period_me2=26, period_signal=9)` | `.macd`/`.signal`；MACDHisto 额外 `.histo` |
| `RSI` | `bt.indicators.RSI(data.close, period=14)` | 默认 Wilder MA, upperband=70, lowerband=30 |
| `BollingerBands` | `bt.indicators.BollingerBands(data.close, period=20, devfactor=2.0)` | `.mid`/`.top`/`.bot` |
| `CrossOver` | `bt.indicators.CrossOver(a, b)` | 1.0=上穿, -1.0=下穿, 0.0=无 |
| `ATR` | `bt.indicators.ATR(data, period=14)` | 默认 Smoothed MA |
| `Highest` | `bt.indicators.Highest(data.high, period=20)` | 别名 MaxN，默认 period=1 |
| `Lowest` | `bt.indicators.Lowest(data.low, period=10)` | 别名 MinN |

变体: `RSI_SMA`(Cutler), `RSI_EMA`, `RSI_Safe`(safediv=True), `BollingerBandsPct`(`.pctb`)。

## 5. 分析器（strat.analyzers.xxx.get_analysis()）

| 分析器 | 关键参数 | 返回 |
|--------|---------|------|
| `TimeReturn` | `timeframe`, `data` | `{datetime: return}` |
| `Returns` | `timeframe`, `tann`(days=252) | `rtot`/`ravg`/`rnorm`(年化)/`rnorm100` |
| `SharpeRatio` | `riskfreerate=0.01`, `annualize=False` | `{'sharperatio': v}`；`SharpeRatio_A` 默认年化 |
| `DrawDown` | `fund` | `drawdown`/`max.drawdown`/`max.moneydown`/`len` |
| `TradeAnalyzer` | 无 | 嵌套 dict: total/won/lost/pnl/len/streak |
| `Transactions` | `headers=False` | `{datetime: [[size,price,sid,symbol,value]]}` |
| `VWR` | `tau=0.20`, `sdev_max=2.0` | `{'vwr': v}` |

```python
cerebro.addanalyzer(bt.analyzers.SharpeRatio, _name='mysharpe', timeframe=bt.TimeFrame.Days)
strats = cerebro.run()
strat.analyzers.mysharpe.get_analysis()
strat.analyzers.trades.pprint()
```

## 6. 自定义佣金（A股）

```python
class CommInfo_CN(bt.CommInfoBase):
    params = (
        ('commission', 0.0005), ('stampduty', 0.001),
        ('min_comm', 5.0), ('stocklike', True),
        ('commtype', bt.CommInfoBase.COMM_PERC), ('percabs', True),
    )
    def _getcommission(self, size, price, pseudoexec):
        value = abs(size * price)
        comm = max(self.p.min_comm, value * self.p.commission)
        if size < 0:               # 卖出收印花税
            comm += value * self.p.stampduty
        return comm

cerebro.broker.addcommissioninfo(CommInfo_CN())   # 用 addcommissioninfo 非 setcommission
```

关键点:
- 必须重写 `_getcommission(size, price, pseudoexec)`，不是 `getcommission`。
- `size<0` 表示卖出；`pseudoexec=False` 为真实成交。
- `CommInfoBase` 直接子类 `percabs=False`(传5=5%)；`CommissionInfo` 子类 `percabs=True`(传0.05=5%)。本项目用 `percabs=True` 传小数。

## 7. Sizer 仓位管理

```python
class backtrader.Sizer():
    # 自动注入: self.strategy, self.broker
    def _getsizing(self, comminfo, cash, data, isbuy):
        # comminfo: 该 data 的 CommissionInfo
        # cash: 当前可用现金
        # isbuy: True=买, False=卖
        # 返回 int（绝对值生效，0=不下单）

cerebro.addsizer(sizercls, *args, **kwargs)          # 全局默认
cerebro.addsizer_byidx(idx, sizercls, *args, **kwargs)  # 指定策略
```

内置 `SizerFix`: `params=(('stake',1),)`。

## 8. 订单管理

### 状态常量
```
Created, Submitted, Accepted, Partial, Completed, Canceled, Expired, Margin, Rejected
# order.alive(): True 当 ∈ [Created, Submitted, Partial, Accepted]
# 辅助: order.isbuy()/issell(), getstatusname(), getordername(), order.ref
```

### 执行类型
| 类型 | 成交逻辑 |
|------|---------|
| `Order.Market` | 下一根 bar **open** 成交（默认） |
| `Order.Close` | 下一根 bar **close** 成交 |
| `Order.Limit` | 触及 price 即成交；下根 open 已优于限价则用 open |
| `Order.Stop` | 触及 price 后按 Market 执行 |
| `Order.StopLimit` | price 触发后转为 plimit 的 Limit |

### valid 取值
`None`(GTC) / `datetime/date` / `Order.DAY`(`timedelta()`) / matplotlib 数值。

## 9. 多数据与仓位

```python
cerebro.adddata(data0, name='stock_a')
cerebro.adddata(data1, name='stock_b')

# 策略内
self.datas[0] / self.data0 / self.data       # 第一份
self.dnames.stock_a / self.dnames['stock_a'] # 按名
self.getposition(self.data0)                  # 按 data 取仓位
self.buy(data=self.data1, size=100)           # 指定 data 下单
self.close(data=self.dnames.stock_b)          # 平指定仓位
```

自 1.9.0.99 起数据按「peek 下一 datetime」同步，允许不同长度数据共存。

## 10. A 股回测陷阱

1. **T+1**: backtrader 默认无此约束。需在 next 记录买入 bar，卖出前判断 `len(self)-buy_bar>=1`。本项目用 `_buy_date` + `notify_order` 成交后才记录。
2. **整手100股**: 自定义 Sizer `int(.../100)*100`，最低100。
3. **涨跌停**: backtrader 无法模拟封板无成交，需在 next 判断涨停不买、跌停不卖。
4. **信号前视偏差**: 选股信号取 `<=当前日期` 的最近信号日。
5. **资金不足静默拒单**: Margin 状态不报错，需 notify_order 捕获。等权分配留 0.98 安全系数。
6. **订单异步**: `buy()` 返回时未撮合，T+1 记录必须等 Completed 状态。
7. **numpy/pandas 兼容**: 需 `numpy<1.24` + `pandas<1.5`。或手动 patch `np.float→float`。
8. **PandasData**: 要求 DatetimeIndex；列名小写 open/high/low/close/volume 便于自动检测。
9. **前复权数据**: A 股回测应用前复权避免除权跳空被误判为信号。
10. **cheat_on_open**: `Cerebro(cheat_on_open=True)` + `set_coo(True)` 可在 T 日用 T 日 open 下单（实盘不可用）。

---

## 附录：本项目核心导入速查

```python
# xtquant
from xtquant import xtdata, xtconstant
from xtquant.xttrader import XtQuantTrader, XtQuantTraderCallback
from xtquant.xttype import StockAccount

# qlib
import qlib
from qlib.constant import REG_CN
from qlib.data import D
from qlib.data.ops import Ref, Mean, Std, Sum, Max, Min, Corr, Greater, Less, Log, Abs
from qlib.contrib.data.handler import Alpha158, Alpha360
from qlib.data.dataset import DatasetH
from qlib.contrib.model.gbdt import LGBModel
from qlib.contrib.strategy import TopkDropoutStrategy
from qlib.contrib.evaluate import backtest_daily, risk_analysis
from qlib.utils import init_instance_by_config

# backtrader
import backtrader as bt
# bt.Cerebro / bt.Strategy / bt.feeds.PandasData / bt.indicators / bt.analyzers / bt.CommInfoBase / bt.Sizer / bt.Order
```
