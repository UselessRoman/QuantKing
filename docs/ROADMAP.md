# 更新方向

本文件梳理 QuantKing 当前的已知局限、技术债务和后续改进计划，按优先级和领域分类组织。每项标注了影响范围和实现难度，供后续开发参考。

---

## 高优先级：正确性与可靠性

### 交易日历接入 exchange_calendars

`utils/trading_hours.py` 中的 `HOLIDAYS` 集合当前为空，`is_holiday()` 始终返回 False，导致国庆、春节等法定节假日被误判为交易日。实盘执行器 `StrategyExecutor.run_loop()` 依赖 `is_trading_time()` 判断是否下单，节假日误判会导致无意义的空转循环。

代码中已标注 TODO（第 25 行），建议接入 `exchange_calendars` 库（`pip install exchange_calendars`，使用 `XSHG` 日历）或从交易所官方日历自动同步。实现后需补充节假日场景的测试用例。

**影响**: 实盘交易 / **难度**: 低

### Database LRU 缓存失效策略

v2.2.0 引入的读侧 LRU 缓存（`OrderedDict`，上限 200 条）在增量下载新数据后可能返回过期数据。`insert_daily_kline_df()` 写入新数据后未失效对应缓存条目。建议在写入方法中清除对应的缓存 key，或增加缓存版本号机制。

**影响**: 数据一致性 / **难度**: 低

### 策略路由缓存过期风险

v2.2.0 引入的 `_model_cache` 和 `_signal_cache`（5 分钟 TTL）在活跃交易时段可能返回过期预测。如果用户在缓存有效期内重新训练了模型，`/predict` 仍返回旧模型结果。建议在 `POST /train` 时清除对应缓存条目。

**影响**: 策略预测 / **难度**: 低

### 数据下载增量逻辑健壮性

`Downloader` 的增量更新依赖 `Database.get_latest_kline_date()` 判断是否跳过。当某只股票因停牌导致 Parquet 文件存在但数据不完整时，增量逻辑可能错误跳过该股票。建议增加"最后更新日期距今超过 N 天则强制重下"的兜底机制。

**影响**: 数据完整性 / **难度**: 中

---

## 中优先级：功能完善

### 分钟级 K 线回测支持

当前回测系统以日 K 线为主。`Database` 已实现 `insert_minute_kline()` 方法，`DataProvider.get_kline()` 支持 `period='1m'` 等分钟周期，但 `BacktestRunner` 和 `backtrader_feeder` 未针对分钟数据做适配（DatetimeIndex 频率、数据量、内存占用）。backtrader 本身支持分钟级回测，主要工作在于数据加载层和策略参数调整。

**影响**: 回测精度 / **难度**: 中

### 因子 IC 分析集成

项目从 v1.0 迁移时遗留了 `research/factor_analysis.py`（IC / Rank IC / ICIR 计算），但当前 `strategy/` 模块未集成因子有效性检验。建议在 `FactorHandler` 中增加 `compute_ic(factors, forward_returns)` 方法，或在 Web 策略路由中增加 `GET /api/strategy/ic_report` 端点，输出各因子的 IC 时序和 ICIR 排名。

**影响**: 策略研发 / **难度**: 中

### 组合优化器

`SignalGenerator` 当前仅做 Top-K 等权选股。实际量化投资中，等权组合在股票数量较少时集中度过高。可引入组合优化（均值-方差、风险平价、最小方差），在 `SignalGenerator.generate()` 之后增加 `PortfolioOptimizer.optimize(predictions, cov_matrix)` 步骤。qlib 的 `Portfolio` 模块（`qlib.contrib.strategy`）提供了 `EnhancedIndexingStrategy` 可参考。

**影响**: 策略表现 / **难度**: 高

### 多模型集成

`QlibTrainer` 当前仅支持单模型训练（LightGBM）。v2.2.0 修复后 qlib 模式委托给 sklearn 模式训练，未使用 qlib 原生 `LGBModel` + `DatasetH`。可扩展为多模型集成（LightGBM + XGBoost + LSTM），通过加权平均或 Stacking 提升预测稳定性。qlib 框架本身支持 `Ensemble` 模型，可直接集成。

**影响**: 预测精度 / **难度**: 中

---

## 中优先级：依赖与兼容性

### backtrader 停更与 numpy 版本冲突

backtrader 最后版本为 1.9.78.123，作者已停更，代码中使用了 `numpy.float`（在 numpy >= 1.24 中已删除）。当前项目 `requirements.txt` 要求 `numpy>=1.24`（其他模块需要），但 backtrader 需要 `numpy<1.24`。这形成版本冲突。

短期方案是安装 `numpy==1.23.5` 牺牲其他模块的新特性。中长期可考虑：
- 使用 backtrader 社区 fork 版本（如 `backtrader2`）修复 numpy 兼容性
- 逐步迁移到 `vectorbt` 或 `backtesting.py` 等活跃维护的回测框架
- 自研轻量回测引擎（v1.0 已有自研回测引擎基础）

**影响**: 环境兼容性 / **难度**: 高（迁移）/ **难度**: 低（fork 版本）

### qlib 官方数据集不可用

qlib 官方提供的预置数据集暂时禁用，项目通过 `qlib_converter` 从本地 Parquet 自行转换。社区数据 [chenditc/investment_data](https://github.com/chenditc/investment_data/releases) 可作为补充，但需验证数据格式和覆盖率。建议在 `scripts/` 中增加社区数据导入脚本。

**影响**: 数据覆盖 / **难度**: 低

### pandas 版本约束

backtrader 要求 `pandas<1.5`（部分 API 在高版本中变更），但项目其他模块使用 `pandas>=2.0`。当前依赖 backtrader 的测试用例在 `pandas>=2.0` 环境下可能不稳定。需确认 backtrader 在 pandas 2.x 下的实际兼容情况，必要时打 monkey-patch。

**影响**: 环境兼容性 / **难度**: 中

---

## 低优先级：代码质量与体验

### 前端页面版本控制

`.gitignore` 中 `*.html` 规则一并忽略了 `web/static/index.html` 和回测报告 HTML。克隆仓库后前端页面缺失，需手动创建。建议在 `.gitignore` 中追加 `!web/static/index.html` 取反规则，或改用 `!web/static/` 目录级排除。

**影响**: 开发体验 / **难度**: 低

### 回测历史对比与可视化

`backtest/backtest_routes.py` 已实现 `POST /api/backtest/compare` 多策略对比，但对比结果仅为 JSON 排序。可增加净值曲线叠加图、收益分布对比图等可视化（前端 Canvas 或后端 matplotlib 出图）。

**影响**: 用户体验 / **难度**: 中

### 审计日志查询与告警

`Database.audit_log` 表已实现写入和查询，但缺少定期审查和异常告警机制。可在 `StrategyExecutor` 中增加审计日志的自动分析，如检测到异常下单频率或大额亏损时触发告警（日志告警 / Web 推送）。

**影响**: 安全审计 / **难度**: 中

### ~~DataValidator 向量化优化~~ (v2.2.0 已解决)

~~`DataValidator.validate_kline()` 使用逐日 `for` 循环检测价格跳变，对 5000+ 只 A 股批量验证时性能较慢。~~ v2.2.0 已改为 `pct_change()` 向量化计算后过滤超阈值行。

### 配置热加载

当前 `config/settings.py` 在导入时加载配置，修改后需重启服务。`risk.yaml` 已支持通过 `POST /api/risk/config` 热更新，但其他配置（如 `WEB_API_KEY`、`LOG_CONFIG`）仍需重启。可引入配置文件监听（`watchdog`）实现部分配置的热加载。

**影响**: 运维体验 / **难度**: 中

---

## 长期方向：架构演进

### 实盘-回测一致性

当前实盘策略（`BaseStrategy.on_bar()`）和回测策略（`bt.Strategy.next()`）是两套独立接口。同一策略逻辑需要分别实现两次，存在不一致风险。可设计统一的策略描述层（如 YAML/JSON 策略配置 + 通用执行引擎），让实盘和回测共享同一份策略定义。

**影响**: 策略一致性 / **难度**: 高

### 数据源扩展

`DataProvider` 封装了 xtquant，但接口设计已为多数据源预留空间。可增加 Tushare、AKShare 等备选数据源，通过统一接口（`DataSource` 协议）实现数据源可插拔。这对脱离 miniQMT 环境做离线研发有价值。

**影响**: 数据灵活性 / **难度**: 中

### 回测引擎并行化

backtrader 是单线程事件驱动引擎，全市场 5000 只股票回测耗时较长。v2.2.0 已实现数据加载层的 `ThreadPoolExecutor` 并行预加载（N=20 股加速 3-5 倍），但回测引擎本身仍是单线程。进一步可探索：
- 向量化回测（`vectorbt` 原生支持多股票向量化回测）
- 多进程回测（按股票分组并行，结果合并）
- 增量回测（只重算变化部分）

**影响**: 回测效率 / **难度**: 高

### 模型版本管理

`QlibTrainer.save()/load()` 使用 pickle 序列化，缺少模型版本管理。可引入 MLflow 或简单的模型注册表，记录训练数据范围、超参数、IC 指标等元信息，支持模型对比和回滚。

**影响**: 模型管理 / **难度**: 中
