# 修改历史

本文件记录 QuantKing 项目的版本演进，包括功能变更、缺陷修复和技术决策。内容综合自 git 提交历史、代码内注释和版本标记。

---

## v2.2.0 (2026-07-09)

### 策略正确性修复 — P0 级

**`strategy/qlib_model.py`** 三处 P0 修复，涉及模型训练和预测的正确性：

- **P0-1 标签泄漏**：`predict()` 排除特征时用的是 `'ret_5d'`（过去 5 日收益动量因子），而非 `'forward_ret_5d'`（未来 5 日收益标签），导致标签列被当作特征喂给模型。修复为排除正确的标签列名
- **P0-2 特征列顺序不一致**：`train()` 按 DataFrame 列顺序取特征，`predict()` 按 `feature_importance` 排序取特征，LightGBM 按列位置匹配导致预测错乱。修复为训练时保存 `_feature_cols`（特征列列表）和 `_fillna_medians`（中位数），预测时复用同一顺序和中位数（旧代码 predict 用全量数据中位数含预测期，属于轻微信息泄漏）
- **P0-3b qlib 训练路径失效**：`_train_with_qlib()` 新建 Alpha158 DatasetH 完全忽略 `handler._factors`，segments 日期硬编码为 2010-2025，且 `predict()` 调用了不存在的 `handler._get_dataset()`。修复为确保 qlib 初始化后委托给 sklearn 模式训练，保证特征处理与预测路径完全一致

**`strategy/alpha_factors.py`** P0-3a 修复：

- **qlib/pandas 模式特征错位**：旧代码 `_load_factors_qlib()` 直接用 Alpha158（约 158 个因子），与 pandas 模式的 22 个自定义因子完全不同，导致模式切换时特征集错位、模型失效。改为使用 `QLIB_FACTOR_EXPRESSIONS` 通过 `D.features()` 计算与 pandas 模式完全对齐的 22 个因子
- **Ref 方向错误**：旧代码用 `Ref($close, -1)`（未来值）计算收益率，方向反了。qlib 中 `Ref(x, n>0)` = n 期前的值（过去），`Ref(x, n<0)` = n 期后的值（未来）。收益率应使用正数 Ref

### 架构性能优化 — 消除冗余序列化/IO/内存拷贝

**P0 数据传输路径优化**：
- `data/downloader.py`：新增 `_kline_to_df()` 直接返回 DataFrame，消除旧代码 DF→`list[dict]`→DF 的序列化往返
- `data/database.py`：新增 `insert_daily_kline_df()` 接受 DataFrame 直传写入 Parquet，`insert_daily_kline()` 保留兼容但内部委托给 DF 版本

**P1 Parquet 谓词下推 + 列裁剪**：
- `data/database.py`：`get_daily_kline_df()` 使用 pyarrow `filters` 参数做日期过滤下推（IO 层面完成，不再全文件读入后内存过滤），`columns` 参数做列裁剪（回测只需 OHLCV 5 列）。单文件读取量减少 30-70%

**P1 回测多股并行预加载**：
- `backtest/runner.py`：`load_data_from_db()` 用 `ThreadPoolExecutor`（最多 8 线程）并行读取 Parquet DataFrame（Parquet 读取线程安全），再串行构建 PandasData feed。N=20 股预计加速 3-5 倍

**P2 消除回测双拷贝**：
- `data/database.py`：读侧 LRU 缓存（`OrderedDict`，上限 200 条）命中时返回视图（不 copy）
- `data/backtrader_feeder.py`：`load_bt_data()` 统一做 `df.copy()`，消除旧代码 cache.copy + load_bt_data.copy 的双拷贝

**P2 因子分块计算**：
- `strategy/alpha_factors.py`：`_load_factors_pandas()` 用 `ThreadPoolExecutor` 并行加载 Parquet，分块计算因子（每批 500 股：concat→计算→dropna→收集），避免全量 concat 内存峰值。MACD 三线（dif/signal/hist）从分别计算改为一次计算复用

**P2 qlib_converter 流式两遍扫描**：
- `data/qlib_converter.py`：旧代码将全部股票 DF 存入 `stock_data` dict 常驻内存，5000 股 × 10 年日线约数 GB 峰值。改为两遍流式扫描：第一遍只收集日期并集（不存 DF），第二遍逐文件重新读→对齐→写 bin。日期解析从 `pd.to_datetime` 改为向量化字符串操作

**P2 绩效分析向量化**：
- `backtest/bt_analyzer.py`：`_calc_max_drawdown()` 和 `_calc_drawdown_curve()` 从 Python for 循环改为 `np.maximum.accumulate` 向量化，提速 100 倍以上。回撤曲线用实际交易日作 key 而非整数序号

**P3 Web 回测异步化**：
- `web/routes/backtest_routes.py`：`POST /run` 和 `POST /run_quick` 使用 `run_in_executor` 将 CPU 密集型回测放入线程池，避免阻塞 FastAPI 事件循环

**P3 模型/信号缓存**：
- `web/routes/strategy_routes.py`：模块级 `_model_cache` 和 `_signal_cache`（5 分钟 TTL），避免每次 `/predict` 请求重新加载因子+模型，`/signals` 从缓存实例读取而非每次 new 新实例

### 其他优化

- `strategy/signal_generator.py`：`generate()` 实现 `_cache` 写入（旧代码声明了但从未写入，`get_latest_signals()` 永远返回空），`generate_with_risk_control()` 按 score 排序后再选 Top-K
- `data/data_validator.py`：价格跳变检测从逐日 for 循环改为 `pct_change()` 向量化
- `backtest/runner.py`：`load_data_from_db()` 支持传入外部 Database 实例，`set_strategy()` 防止重复注册
- `web/routes/data_routes.py`：复用 `app.state.provider` 而非每次请求新建 DataProvider
- `data/downloader.py`：移除下载间 sleep，`_kline_to_records()` 向量化转换

### 附带修复

- `backtest/bt_analyzer.py`：回撤曲线 key 从整数序号改为实际交易日日期，前端可对应交易日
- `data/qlib_converter.py`：日期归一化从 `pd.to_datetime` 改为向量化字符串操作

---

## v2.1.0 (2025)

### 新增功能

**基础设施层 `utils/`**
- `logging.py`：统一日志工厂 `get_logger()`，控制台 + 文件双输出，RotatingFileHandler 轮转（10MB/5 份），替代散落各处的 `print()` 调用
- `retry.py`：指数退避重试装饰器 `@retry_on_failure`，用于 xtquant 网络调用等易失败操作
- `trading_hours.py`：A 股交易时段判断（上午 9:30-11:30 / 下午 13:00-15:00），含 `next_trading_seconds()` 简化 sleep 策略

**策略注册中心**
- `strategy/registry.py`：统一策略注册中心 `REGISTRY`，按命名空间组织 `{"bt": {}, "live": {}}`，支持 `@register_strategy` 装饰器注册。解决了此前 `bt_strategy.py`、`strategy/__init__.py`、`registry.py` 三处独立注册表不一致的问题，`REGISTRY` 成为唯一真相源

**Web 安全**
- API Key 鉴权中间件：请求头 `X-API-Key` 校验，策略为"默认全部鉴权，仅白名单只读 GET 放行"，`/api/monitor/*` 和 `/api/risk/*` 前缀强制鉴权（含 GET）
- CORS 中间件：仅允许 localhost:8000 / 127.0.0.1:8000，限定 GET/POST 方法

**数据层增强**
- `Database` 审计日志：`audit_log` 表 + `log_audit()` / `get_audit_logs()` 方法
- `Database` 回测历史持久化：`backtest_history` 表 + `insert_backtest_history()` / `get_backtest_history()`，JSON 序列化存储 params/result/codes
- `Database` 除权因子读写：`insert_divid_factors()` / `get_divid_factors()`
- `Downloader` 多线程并行下载：`ThreadPoolExecutor`（6 线程），每线程独立 DataProvider，`_stats_lock` 保护数据库写入

**回测增强**
- `BacktestRunner.run_qlib_signal()`：QlibSignalStrategy 专用一键信号回测入口，封装 load→addstrategy→run 流程
- `BacktestRunner.run_quick()`：最简一键回测
- 回测引入滑点 `set_slippage_perc(perc=0.0001)`（万分之一），旧版无滑点偏乐观

**风控增强**
- `RiskManager` 按板块区分涨跌停比例：主板 10% / 创业板科创板 20% / 北交所 30%
- `POST /api/risk/config`：动态调整风控参数，热更新内存 + 持久化到 `risk.yaml`
- `POST /api/risk/check_order`：模拟订单风险检查接口

**其他**
- `settings.py` 新增 `WEB_API_KEY`、`RISK_CONFIG_PATH`，ACCOUNTS 从 `accounts.yaml` 加载（含完整容错）
- `TraderManager.buy()/sell()` 支持 `strategy_name` 和 `remark` 参数
- 脚本 `download_data.py` 新增 `--stocks-only` / `--sectors-only` / `--financial` 参数
- 脚本 `run_backtest.py` 新增 `--report` 生成 HTML 绩效报告

---

## 批次 A 修复（2025-06）

批次 A 是一组针对回测正确性的关键修复，每项修复均配有回归测试（`tests/test_batch_a_fixes.py`，13 个用例）。

### fix #1：BacktestAnalyzer 重复 run 问题

**文件**: `backtest/bt_analyzer.py`、`backtest/runner.py`

**问题**: 旧版 `analyzer.analyze()` 内部会再次调用 `cerebro.run()`，导致回测被执行两次。第二次 run 时 Cerebro 状态已被消费，产生的净值序列和交易记录不正确。

**修复**: `analyze()` 改为接收已运行的 `strat` 实例（Strategy 对象），从中提取 `TimeReturn` analyzer 的日收益率序列累乘还原净值曲线，不再重复 run。`BacktestRunner` 在 `__init__` 时预挂载 7 个 analyzer（TimeReturn / Transactions / TradeAnalyzer / SharpeRatio / DrawDown / Returns / VWR），其中前两个是 Analyzer 的数据源。

### fix #2：qlib 二进制格式错误

**文件**: `data/qlib_converter.py`

**问题**: 旧版 `.bin` 文件写入 `int32(日期) + float32(值)` 的混合格式，导致 qlib 读取时数据错位。qlib 的 `.bin` 格式规范为**纯 float32 小端序列**，长度等于全局日历天数，缺失日期填 NaN。

**修复**: `_write_bin_file()` 改为只写 float32 小端序列。`convert_kline_to_qlib_format()` 改为两遍扫描：第一遍读所有 Parquet 收集全局交易日历并集，第二遍按日历对齐写各股票特征（缺失填 NaN）。新增 `validate_qlib_data()` 抽样验证日历行数与 .bin 记录数对齐。

### fix #6：QlibSignalStrategy 信号注入时机

**文件**: `backtest/bt_strategy.py`、`backtest/runner.py`

**问题**: 旧版试图在策略实例化后通过 `set_signals()` 注入选股信号。但 backtrader 在 `cerebro.run()` 内部实例化策略，外部无法在实例化后注入——`set_signals()` 调用时策略尚未创建，信号丢失。

**修复**: 信号改为通过 `params.signals` 在 `addstrategy(signals=...)` 时传入。`run_qlib_signal()` 方法封装了这一流程。`set_signals()` / `set_codes()` 方法保留但标注 `⚠` 兼容性提示（运行期无效）。

### 附带修复：前视偏差与 T+1 误判

在批次 A 修复过程中，顺带修正了 `QlibSignalStrategy` 的两处逻辑缺陷：

- **前视偏差**: `_get_target_codes()` 旧版用 `abs()` 比较日期差，可能选到未来日期的信号。修正为只取 `<= 当前日期` 的最近信号日。
- **T+1 误判**: `notify_order()` 旧版在 `buy()` 返回后立即记录 `_buy_date`，但此时订单未撮合，资金不足会被静默拒单（Margin 状态），却已记录为"已买入"。修正为只有 `Completed` 状态才记 `_buy_date`，`Margin/Rejected` 状态清理 `_pending_buys`。

### 附带修复：等权资金安全系数

`QlibSignalStrategy.next()` 中等权资金分配改为 `per_stock_value = total_value * 0.98 / top_k`。0.98 安全系数覆盖佣金 + 滑点 + 整百股取整上溢，避免因资金不足触发 Margin 静默拒单。

### 附带修复：标签泄漏与时间切分

`QlibTrainer._train_sklearn()` 两处修正：
- 训练标签从 `ret_5d`（过去 5 日收益动量因子）改为 `forward_ret_5d`（未来 5 日收益），避免"用未来收益预测未来收益"的标签泄漏
- 训练/验证集切分从按行数 `iloc` 改为按日期切分，避免同一日期的数据散落在训练集和验证集两边造成时间泄漏

---

## v2.0.0

全新架构版本，从 v1.0 的自研回测引擎迁移到 XTquant + qlib + backtrader + FastAPI 技术栈。

### 核心建设

- **数据层**: `DataProvider`（xtquant 行情封装）、`Database`（SQLite + Parquet 混合存储）、`Downloader`（多线程下载器）、`qlib_converter`（Parquet→qlib 二进制转换）、`backtrader_feeder`（backtrader 数据源适配）
- **策略层**: `FactorHandler`（22+ Alpha 因子，qlib / pandas 双模式计算）、`QlibTrainer`（LightGBM 模型训练，qlib / sklearn 双模式）、`SignalGenerator`（Top-K 选股 + 换手率控制）、`BaseStrategy` + `Signal`（实盘策略抽象基类）
- **回测层**: 6 个 backtrader 策略（MACross / MACD / RSI / BollingerBands / Turtle / QlibSignal）、`AShareCommission`（A 股佣金印花税过户费）、`AShareSizer`（整百股仓位）、`BacktestRunner`（回测执行器）、`BacktestAnalyzer`（绩效分析 + quantstats 报告）
- **交易层**: `TraderManager`（实盘交易管理，限价买卖/撤单/查询）、`StrategyExecutor`（策略执行器，行情→策略→风控→下单→记录流水线）
- **风控层**: `RiskManager`（5 项检查 + 双熔断机制：日亏损熔断 + 回撤熔断）
- **Web 层**: FastAPI 应用 + 5 组路由（data/strategy/backtest/monitor/risk）+ 前端页面
- **脚本**: `download_data.py`、`convert_to_qlib.py`、`run_backtest.py`、`train_model.py`、`run_strategy.py`

### 关键设计决策

- 复权方式选用**后复权**（back）：前复权在增量更新时新除权事件会改变历史价，导致基准漂移；后复权历史价固定，适合回测连续性
- 因子计算采用**双模式降级**：优先 qlib 原生表达式，qlib 不可用时自动回退 pandas 向量化计算（`groupby.transform` 避免 `groupby.apply` 逐组调用 Python 函数的性能问题）
- xtquant 采用**可选导入**：`_XT_AVAILABLE` 标志位，缺失时方法返回空值不报错，保证无 miniQMT 环境下代码可导入和测试

---

## v1.0.0

项目初始版本，基于 XTquant 的数据下载和实盘交易，使用自研回测引擎和基础策略框架。

- XTquant 行情数据下载与本地存储
- 自研回测引擎（非 backtrader）
- 5 个基础策略（均线交叉、MACD、RSI、海龟、布林带）
- 基础 Web 界面
- 实盘交易接口

---

## Git 提交历史

| 提交哈希 | 说明 |
|----------|------|
| `13732d3` | Initial commit: QuantKing 量化交易系统 |
| `f25cf67` | chore: baseline before batch A optimization |
| `9ec2954` | fix(backtest): #1 analyzer 不再重复 run，改用 TimeReturn 取真实净值序列 |
| `9c30c48` | fix(backtest): #6 QlibSignalStrategy 改为通过 params 注入选股信号 |
| `c0f400a` | fix(data): #2 qlib 二进制格式改为纯 float32 并按全局日历对齐 |
| `ec859a7` | test: 批次 A 回归测试（qlib 二进制格式 + analyzer 纯算法 + 信号注入） |
| `5cf9099` | 6.22GLM5.2 修改 |
| `889d21e` | perf(architecture): 数据传输架构优化 - 消除冗余序列化/IO/内存拷贝 |
| `6d5da1c` | fix(strategy): 修复P0数据泄露/特征错位/qlib模式失效 + P1/P2性能优化 |
