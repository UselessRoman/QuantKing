# 架构与开发指南

本文件是 QuantKing 的技术参考文档，涵盖模块设计、数据流、项目约定、已知陷阱和扩展方法，供开发者深入理解和维护项目。

---

## 数据层 `data/`

### DataProvider — XTquant 行情封装

`data/xt_provider.py` (330 行) 封装 XTquant SDK 的行情接口，隔离底层依赖。

xtquant 采用可选导入模式：模块顶部 `try/except ImportError` 设置 `_XT_AVAILABLE` 标志，缺失时所有方法返回空值不报错。这一设计使得无 miniQMT 环境下代码仍可导入和测试。

核心方法：

| 方法 | 功能 | 注意事项 |
|------|------|----------|
| `connect(port)` | 连接 miniQMT | 带 `@retry_on_failure`（3 次/指数退避） |
| `get_kline(codes, period, ..., dividend_type)` | 获取 K 线 | 默认**后复权**（`dividend_type='back'`） |
| `download_history(codes, period, start, end)` | 全量下载 | 写入 XTquant 本地缓存 |
| `download_history_incremental(codes, period)` | 增量下载 | 仅补充缺失日期 |
| `get_full_tick(codes)` | 全推 Tick | 实时行情 |
| `get_stock_list_in_sector(sector)` | 板块成分股 | 如 `'沪深A股'` |
| `download_financial_data(codes)` | 下载财务数据 | |

`get_kline()` 返回值的处理逻辑较复杂：xtquant 的 `get_market_data_ex()` 返回 `dict[str, DataFrame]` 或 `DataFrame`（MultiIndex），代码中做了多重 fallback 合并，适配不同版本返回格式。

### Database — SQLite + Parquet 混合存储

`data/database.py` 是项目的数据存储核心。SQLite 存储元数据和索引，Parquet 存储时序数据（K 线、财务、除权因子）。

SQLite 表结构（7 张表）：

| 表名 | 用途 |
|------|------|
| `stocks` | 股票基础信息（代码、名称、上市日期等） |
| `sectors` | 板块分类 |
| `trade_records` | 交易记录 |
| `kline_index` | K 线文件索引（代码→文件路径→日期范围） |
| `financial_index` | 财务数据索引 |
| `audit_log` | 审计日志 |
| `backtest_history` | 回测历史（JSON 序列化 params/result/codes） |

写入侧：`_incremental_write_parquet()` 通用方法完成去重→合并→排序→写入，带 `_date_cache` 内存缓存避免全量读 Parquet。K 线写入新增 `insert_daily_kline_df()` 接受 DataFrame 直传，消除了旧代码 DF→`list[dict]`→DF 的序列化往返；`insert_daily_kline()` 保留兼容但内部委托给 DF 版本。

读取侧：`get_daily_kline_df()` 使用 pyarrow 谓词下推（`filters` 参数做日期过滤，IO 层面完成不再全文件读入后内存过滤）和列裁剪（`columns` 参数，回测只需 OHLCV 5 列），单文件读取量减少 30-70%。读侧 LRU 缓存（`OrderedDict`，上限 200 条）命中时返回视图不 copy，由下游 `load_bt_data` 统一 copy，消除旧代码双拷贝。SQLite 以 WAL 模式运行提升并发读性能。

### qlib_converter — Parquet 到 qlib 二进制转换

`data/qlib_converter.py` 将本地 Parquet K 线转换为 qlib 二进制格式。

转换采用流式两遍扫描（旧代码将全部股票 DF 存入 dict 常驻内存，5000 股 × 10 年日线约数 GB 峰值）：
1. 第一遍扫描所有 Parquet 文件，只收集全局交易日历并集（不保留 DF）
2. 第二遍逐文件重新读→对齐→写 bin，缺失日期填 NaN

`.bin` 文件格式为**纯 float32 小端序列**，长度等于全局日历天数。旧版曾错误写入 `int32(日期) + float32(值)` 混合格式导致 qlib 读取错位，已在批次 A 修复。

产出目录结构：
```
data/qlib_data_cn/
├── calendars/day.txt          # 交易日历（每行一个日期）
├── instruments/all.txt        # 股票列表（code\tstart\tend）
└── features/<code>/
    ├── open.1d.bin            # 纯 float32 小端
    ├── high.1d.bin
    ├── ...
    └── amount.1d.bin
```

### backtrader_feeder — 数据源适配

`data/backtrader_feeder.py` (113 行) 将 DataFrame 包装为 backtrader 的 `PandasData` 数据源。

`XTQuantDataFeed` 继承 `bt.feeds.PandasData`，定义字段映射：`datetime='date'`、`open/high/low/close/volume` 对应同名列、`openinterest=-1`（A 股无持仓量概念）。`load_bt_data()` 对 DataFrame 做预处理（date 列转 datetime 索引）并校验必需列。`load_multi_stock_data()` 批量加载多股票，返回 `{code: PandasData}` 字典。

### DataValidator — 数据健康检查

`data/data_validator.py` (196 行) 对 K 线数据做多维度质量验证：必需列检查、空值检查、价格跳变检测（`price_jump_threshold=0.11`，覆盖 A 股 10% 涨跌停及创业板/科创板 20%）、high >= low 校验。

---

## 策略层 `strategy/`

### 因子体系

`strategy/alpha_factors.py` (365 行) 定义 22 个 Alpha 因子，覆盖 7 个类别：

| 类别 | 因子 |
|------|------|
| 动量 | ret_1d, ret_5d, ret_10d, ret_20d, ret_60d |
| 波动率 | std_5d, std_20d, hl_amplitude_20d |
| 量价 | vol_ratio_5_20, vol_ratio_5_60, volume_trend_10d |
| 均线偏离 | ma5_dev, ma10_dev, ma20_dev, ma60_dev |
| 技术指标 | rsi_14, macd_dif, macd_signal, macd_hist, bb_position |
| 反转 | reversal_3d |
| 流动性 | turnover_5d |

因子计算采用双模式：

- **qlib 模式**：使用 `QLIB_FACTOR_EXPRESSIONS` 中的 qlib 表达式通过 `D.features()` 计算，与 pandas 模式的 22 个因子完全对齐。旧代码直接用 Alpha158（约 158 个因子），导致模式切换时特征集错位，已修复。同时修正了 `Ref` 方向错误（qlib 中 `Ref(x, n>0)` = 过去值，收益率应用正数 Ref）
- **pandas 模式**：从 `Database` 批量加载 K 线，用 `ThreadPoolExecutor` 并行读取 Parquet，分块计算因子（每批 500 股：concat→计算→dropna→收集），避免全量 concat 内存峰值。用 `groupby('code').transform` 向量化计算，避免 `groupby.apply` 逐组调用 Python 函数。MACD 三线（dif/signal/hist）从分别计算改为一次计算复用

qlib 不可用时自动回退 pandas 模式。两处 `assert` 强制因子名、表达式和 `FACTOR_META` 三者数量与集合一致，防止"22 vs 15 不一致"的历史问题复发。

训练标签 `forward_ret_5d`（未来 5 日收益）在 pandas 模式中一并计算，注释强调必须从特征 X 中排除。

### 模型训练

`strategy/qlib_model.py` 的 `QlibTrainer` 支持双模式训练：

- **qlib 模式**：确保 qlib 初始化后委托给 sklearn 模式训练，保证特征处理与预测路径完全一致。旧代码新建 Alpha158 `DatasetH` 完全忽略 `handler._factors`，日期硬编码且 `predict()` 调用不存在的 `_get_dataset()`，已修复
- **sklearn 模式**：`lgb.LGBMRegressor`（300 树, max_depth=6, subsample/colsample=0.8），按日期切分训练/验证集（70%/15%）

关键修复（见 CHANGELOG v2.2.0 P0 + 批次 A）：
1. 标签使用 `forward_ret_5d` 而非 `ret_5d`，避免标签泄漏
2. 按日期切分而非行数 `iloc`，避免时间泄漏
3. 训练时保存 `_feature_cols`（特征列顺序）和 `_fillna_medians`（中位数），预测时复用，避免 train/predict 特征列顺序不一致导致 LightGBM 按列位置匹配错乱

### 信号生成

`strategy/signal_generator.py` 的 `SignalGenerator` 将预测分数转换为选股列表：

- `generate()`：Top-K 选股，支持 `min_score` 阈值过滤和 `blacklist` 黑名单。兼容 MultiIndex（按日期分组）和单日两种输入。计算结果写入 `_cache`，使 `get_latest_signals()` 正常工作
- `generate_with_risk_control()`：基于现有持仓生成 BUY/SELL/HOLD 指令，`max_turnover` 限制买卖变动数量，按 score 排序后再选 Top-K
- `filter_by_sector()`：按板块过滤

### 策略注册中心

`strategy/registry.py` (106 行) 的 `REGISTRY` 是策略注册的唯一真相源，按命名空间组织：

```python
REGISTRY = {"bt": {}, "live": {}}
```

- `"bt"` 命名空间：backtrader 回测策略类（`bt.Strategy` 子类）
- `"live"` 命名空间：实盘策略类（`BaseStrategy` 子类）

`@register_strategy("bt")` 装饰器用 `cls.name` 作键注册策略类。`bt_strategy.py` 末尾的 `STRATEGY_REGISTRY` 实际是 `REGISTRY["bt"]` 的引用，保留向后兼容。`register_builtin_bt_strategies()` 在导入时自动注册 6 个内置策略。

---

## 回测层 `backtest/`

### 内置策略

`backtest/bt_strategy.py` (377 行) 实现 6 个 backtrader 策略：

| 策略 | 类名 | 逻辑 | 参数 |
|------|------|------|------|
| 均线交叉 | `MACrossStrategy` | SMA 快慢线 CrossOver 金叉买/死叉卖 | fast=5, slow=20 |
| MACD | `MACDStrategy` | DIF 上/下穿 Signal | fast=12, slow=26, signal=9 |
| RSI | `RSIStrategy` | RSI < oversold 买, > overbought 卖 | period=14, oversold=30, overbought=70 |
| 布林带 | `BollingerBandsStrategy` | 收盘价 < 下轨买, > 上轨卖 | period=20, devfactor=2.0 |
| 海龟突破 | `TurtleStrategy` | 突破 N 日高点买, 跌破 N 日低点卖 | entry=20, exit=10, atr=20 |
| qlib 信号 | `QlibSignalStrategy` | 调仓日读 Top-K 信号等权调仓 | signals, codes, top_k=20, rebalance_freq=20 |

前 5 个技术策略结构一致：`__init__` 建指标 + `next`（单仓金叉买/死叉卖）+ `notify_order`（清理 `self.order` 防重入）。

`QlibSignalStrategy` 是最复杂的策略，包含三处关键设计（详见 CHANGELOG 批次 A）：
- 信号通过 `params.signals` 在 `addstrategy` 时注入（backtrader 在 `cerebro.run()` 内部实例化策略）
- `_get_target_codes()` 只取 `<= 当前日期` 的最近信号日（修正前视偏差）
- `notify_order()` 只有 `Completed` 才记 `_buy_date`（修正 T+1 误判）

等权资金分配使用安全系数：`per_stock_value = total_value * 0.98 / top_k`，0.98 覆盖佣金 + 滑点 + 整百股取整上溢。

### A 股交易规则

`backtest/bt_broker.py` (94 行) 实现 A 股费率：

| 费项 | 费率 | 说明 |
|------|------|------|
| 佣金 | 万 2.5 | 最低 5 元 |
| 印花税 | 千 1 | 仅卖出收取 |
| 过户费 | 万 0.1 | 沪深统一收取（近似，深市实际无过户费但金额极小） |

`AShareSizer` 按比例计算买入量：`int(available/price/100)*100`，最低 100 股。卖出返回全部持仓。

`BacktestRunner` 在 `__init__` 时设置万分之一比例滑点（`set_slippage_perc(perc=0.0001)`）。

### 回测执行与分析

`backtest/runner.py` 的 `BacktestRunner` 封装 Cerebro 创建/配置/执行，提供三种入口：

| 方法 | 用途 |
|------|------|
| `run()` | 通用回测，先 `set_strategy()` 再 `run()` |
| `run_qlib_signal(codes, signals)` | QlibSignalStrategy 专用（信号经 params 注入） |
| `run_quick(codes, strategy_name)` | 最简一键回测 |

`load_data_from_db()` 用 `ThreadPoolExecutor`（最多 8 线程）并行读取 Parquet DataFrame（Parquet 读取线程安全），再串行构建 PandasData feed，N=20 股预计加速 3-5 倍。支持传入外部 Database 实例避免重复连接。`set_strategy()` 防止策略重复注册。

`backtest/bt_analyzer.py` 的 `BacktestAnalyzer` 从已运行的 Strategy 实例提取绩效指标。`analyze(strat)` 接收已运行的 `strat` 而非重新 run（批次 A 修复），从 `TimeReturn` analyzer 取日收益率累乘还原净值曲线。计算指标包括：总收益、年化收益、最大回撤、夏普（日 rf=0.02/252，年化 `*sqrt(252)`）、胜率、盈亏比、总交易数。结果带 `unreliable` 标记供前端提示数据可信度。

最大回撤和回撤曲线使用 `np.maximum.accumulate` 向量化计算（旧代码 Python for 循环逐元素遍历），提速 100 倍以上。回撤曲线用实际交易日日期作 key 而非整数序号。纯算法方法（`_calc_max_drawdown` / `_calc_sharpe` / `_calc_trade_stats`）与 IO 分离，可独立单测。

---

## 交易层 `trading/`

### TraderManager — 实盘交易管理

`trading/xt_trader.py` (484 行) 的 `TraderManager` 封装 XtQuantTrader，管理多账号连接。内部维护 `_traders`/`_callbacks`/`_connected`/`_accounts` 四个字典。

`connect_all()` 遍历账号配置逐个创建 `XtQuantTrader` 并连接，内置 `_Callback` 回调类处理断连/委托/成交/状态推送。`buy()/sell()` 使用限价单（`price_type=LATEST_PRICE_FIFTH`），`cancel_order()` 撤单（返回 0 为成功）。

所有方法均有 try/except 异常保护，xtquant 不可用时优雅降级（`_XT_TRADER_AVAILABLE` 标志）。

### StrategyExecutor — 策略执行器

`trading/executor.py` (397 行) 的 `StrategyExecutor` 串联"行情→策略→风控→下单→记录"完整流水线。

`run_once()` 使用模块级 `_EXEC_LOCK` 互斥锁防止 Web 查询与实盘下单并发。执行流程：检查连接/熔断 → 查询资产持仓 → 更新资产峰值 → 检查日亏损/回撤熔断 → 逐股票下载 K 线 → 运行策略生成信号 → 风控检查 → 下单 → 交易记录入库。

`_refresh_account_state()` 在每笔下单后重新查询真实账户状态，替代旧版本地推算（避免多笔循环中持仓只加不减导致超买）。T+1 限制通过 `_buy_dates` 字典跟踪。

`run_loop()` 启动 daemon 线程定时循环，内置交易时段判断（`is_trading_time()`）。

---

## 风控层 `risk/`

`risk/risk_manager.py` (324 行) 的 `RiskManager` 在交易执行前做多维度风险评估。所有状态变更方法用 `threading.Lock` 保护。

`get_limit_ratio(code)` 按板块返回涨跌停比例：

| 板块 | 代码特征 | 涨跌停比例 |
|------|----------|-----------|
| 主板 | 60/00 开头 | 10% |
| 创业板 | 30 开头 | 20% |
| 科创板 | 68 开头 | 20% |
| 北交所 | 8/4 开头 | 30% |

| 检查方法 | 检查内容 |
|----------|----------|
| `check_buy()` | 涨停过滤、单笔金额占比、资金充足（含佣金）、单只持仓上限、总持仓数量上限 |
| `check_sell()` | 持仓检查、T+1 限制、熔断检查 |
| `check_market()` | 涨跌停市场规则（买入查涨停、卖出查跌停） |
| `check_daily_loss()` | 日亏损熔断检测 |
| `check_drawdown()` | 最大回撤熔断检测 |

触发熔断后设 `_meltdown=True`，所有买卖检查均拒绝。`reset_meltdown()` 手动重置，`reset_daily()` 每日重置日计数器。

---

## Web 层 `web/`

### 鉴权策略

`web/app.py` (155 行) 的 API Key 鉴权中间件采用保守策略：

- `/api/monitor` 和 `/api/risk` 前缀：**一律鉴权**（含 GET）
- 所有 POST/PUT/DELETE：**一律鉴权**
- 非白名单 GET：**鉴权**
- 白名单内只读 GET：放行

白名单端点：`/`、`/docs`、`/openapi.json`、`/api/data/stocks`、`/api/data/sectors`、`/api/data/db-status` 等基础查询。

CORS 仅允许 localhost:8000 / 127.0.0.1:8000，限定 GET/POST 方法。

`lifespan()` 异步上下文管理资源生命周期：启动时连接 TraderManager + 初始化 Database，关闭时断开连接。

### 路由模块

| 路由文件 | 端点数 | 主要功能 |
|----------|--------|----------|
| `data_routes.py` (275 行) | 13 | K 线查询、股票/板块列表、数据下载、财务数据 |
| `strategy_routes.py` (196 行) | 6 | 策略列表、因子查询、模型训练、预测信号 |
| `backtest_routes.py` (240 行) | 5 | 回测执行、历史记录、多策略对比 |
| `monitor_routes.py` (109 行) | 7 | 持仓、委托、成交、资产、仪表盘 |
| `risk_routes.py` (126 行) | 5 | 风险状态、参数配置、熔断重置、订单检查 |

回测路由的 `POST /run` 和 `POST /run_quick` 使用 `run_in_executor` 将 CPU 密集型回测放入线程池，避免阻塞 FastAPI 事件循环。`_save_history()` / `_load_history()` 优先使用数据库持久化，失败时回退内存缓存。

策略路由使用模块级缓存（`_model_cache` 和 `_signal_cache`，5 分钟 TTL），避免每次 `/predict` 请求重新加载因子+模型，`/signals` 从缓存实例读取而非每次新建实例。

---

## 项目约定

以下约定在开发中必须遵守，违反会导致回测结果错误或实盘风险。

### 1. 后复权

xtquant 默认使用后复权（`dividend_type='back'`）。前复权在增量更新时新除权事件会改变历史价，导致基准漂移；后复权历史价固定，适合回测连续性。见 `xt_provider.py` `get_kline()`。

### 2. qlib bin 格式

`.bin` 文件为纯 float32 小端序列，长度等于全局日历天数，缺失填 NaN。旧实现曾写 `int32(日期) + float32(值)` 导致错位，已在批次 A 修正。见 `qlib_converter.py`。

### 3. 信号注入方式

backtrader 策略信号必须通过 params 在 `addstrategy(signals=...)` 时传入。策略实例化在 `cerebro.run()` 内部完成，外部无法在实例化后注入。见 `runner.py` `run_qlib_signal()`。

### 4. T+1 实现

成交（`Completed`）后才记 `_buy_date`，非 `buy()` 后立即记。`buy()` 返回时订单未撮合，资金不足会 Margin 静默拒单。见 `bt_strategy.py` `QlibSignalStrategy.notify_order()`。

### 5. 前视偏差修正

选股信号取 `<= 当前日期` 的最近信号日，不可用未来日期。见 `bt_strategy.py` `_get_target_codes()`。

### 6. 整手 100 股

size 计算后 `int(.../100)*100`，最低 100 股。见 `bt_broker.py` `AShareSizer`。

### 7. 等权资金安全系数

`per_stock_value = total_value * 0.98 / top_k`。0.98 覆盖佣金 + 滑点 + 整百股取整上溢，避免 Margin 拒单。见 `bt_strategy.py` `QlibSignalStrategy.next()`。

### 8. 滑点

`set_slippage_perc(perc=0.0001)`（万分之一）。见 `runner.py` `BacktestRunner.__init__()`。

### 9. 标签泄漏

训练时 `forward_ret_5d`（未来收益）必须从特征中排除；`fit_end_time` 应早于 valid 起点避免标签泄漏。见 `qlib_model.py`。

### 10. 时间切分

按日期切分训练/验证集（非按行数 `iloc`），避免同一日期数据散落两边造成时间泄漏。见 `qlib_model.py`。

### 11. 特征列顺序一致性

训练时保存 `_feature_cols`（特征列顺序）和 `_fillna_medians`（中位数），预测时必须复用同一顺序。LightGBM 按列位置匹配，列顺序不一致会导致预测错乱。见 `qlib_model.py`。

### 12. qlib Ref 方向

qlib 中 `Ref(x, n>0)` = n 期前的值（过去），`Ref(x, n<0)` = n 期后的值（未来）。计算收益率（今日/过去-1）应使用正数 Ref。见 `alpha_factors.py`。

---

## 已知陷阱

### xtquant

- 必须先启动 miniQMT，否则 `connect()` 失败
- `download_history_data2` 可能未加入 `__all__`，需直接调用
- `query_stock_positions` 成功返回 `[]` 而非 `None`
- 市价单在模拟环境不生效
- 成交回调可能重复推送，需幂等去重

### qlib

- 不要在仓库目录内 import qlib（会导致数据路径混乱）
- redis 未运行时缓存静默失效（不报错但不缓存）
- qlib 数据价格为前复权（首日归一化为 1），需用 `$close/$factor` 还原真实价格
- `Slope`/`Rsquare`/`Resi` 等算子依赖 Cython 编译，纯 Python 安装会报错
- 官方数据集暂时禁用，需用社区数据或自行转换

### backtrader

- 需 `numpy<1.24`（用了已删除的 `np.float`）和 `pandas<1.5`
- `PandasData` 要求数据为 `DatetimeIndex`
- 涨跌停无法模拟封板（只能过滤不交易，无法模拟排队成交）
- Margin 状态静默拒单不报错，需在 `notify_order` 中主动检查
- 作者已停更（1.9.78.123 为最后版本）

---

## 扩展指南

### 添加自定义 backtrader 策略

```python
# 1. 在 backtest/bt_strategy.py 中定义策略类
class MyStrategy(bt.Strategy):
    params = (('period', 10),)

    def __init__(self):
        self.ma = bt.indicators.SMA(self.data.close, period=self.params.period)

    def next(self):
        if self.data.close[0] > self.ma[0]:
            self.buy(size=100)
        elif self.data.close[0] < self.ma[0]:
            self.sell(size=100)

    def notify_order(self, order):
        if order.status in [order.Completed, order.Canceled, order.Margin, order.Rejected]:
            self.order = None

# 2. 注册到统一注册中心（文件末尾 _REGISTRY["bt"].update(...) 中添加）
_REGISTRY["bt"]["my_strategy"] = MyStrategy
```

### 添加自定义实盘策略

```python
from strategy.registry import register_strategy
from strategy.base import BaseStrategy, Signal

@register_strategy("live")
class MyLiveStrategy(BaseStrategy):
    name = "my_live_strategy"
    params = {"period": 10}

    def init(self, context):
        """context 包含 kline 字段"""
        pass

    def on_bar(self, index) -> list[Signal]:
        kline = self.context['kline']
        if kline['close'].iloc[index] > kline['close'].iloc[index-1]:
            return [Signal(action="BUY", symbol=kline['code'].iloc[0],
                          price=kline['close'].iloc[index], volume=100)]
        return []

    def get_params_info(self):
        return {"period": "均线周期"}
```

### 添加自定义因子

在 `strategy/alpha_factors.py` 中：

1. `FACTOR_META` 添加元信息：`"my_factor": {"category": "动量", "description": "我的因子"}`
2. `QLIB_FACTOR_EXPRESSIONS` 添加 qlib 表达式：`"$close / Mean($close, 10) - 1"`
3. `QLIB_FACTOR_NAMES` 添加因子名：`"my_factor"`
4. `_compute_factors_pandas()` 中实现 pandas 计算逻辑

三处 `assert` 会在导入时校验三者数量和集合一致。

### 添加 Web API 路由

```python
# web/routes/my_routes.py
from fastapi import APIRouter, Request

router = APIRouter(prefix="/api/my", tags=["my"])

@router.get("/data")
async def get_data(request: Request):
    # 敏感操作会被鉴权中间件拦截
    return {"data": "ok"}

# 在 web/app.py 中注册
# app.include_router(my_routes.router)
```

---

## 代码统计

| 模块 | 文件数 | 代码行数 | 测试用例数 |
|------|--------|----------|-----------|
| config/ | 3 | 134 | - |
| utils/ | 3 | 173 | - |
| data/ | 6 | 1745 | 12 |
| strategy/ | 5 | 956 | 7 |
| backtest/ | 4 | 960 | 22 |
| trading/ | 2 | 742 | 4 |
| risk/ | 1 | 274 | 26 |
| web/ | 6 | 967 | 18 |
| scripts/ | 5 | 291 | - |
| tests/ | 8 | 1001 | - |
| main.py | 1 | 32 | - |
| **合计** | **44** | **~7300** | **89** |
