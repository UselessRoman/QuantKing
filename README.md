# QuantKing — A 股量化交易平台

> 基于 **XTquant (miniQMT) + qlib + backtrader + FastAPI** 的个人量化投资系统，覆盖 **数据 → 因子 → 模型 → 回测 → 实盘 → 风控** 完整闭环。

---

## 目录

- [1. 项目概述](#1-项目概述)
- [2. 系统架构](#2-系统架构)
  - [2.1 分层架构图](#21-分层架构图)
  - [2.2 数据流图](#22-数据流图)
  - [2.3 目录结构](#23-目录结构)
- [3. 快速开始](#3-快速开始)
  - [3.1 环境要求](#31-环境要求)
  - [3.2 安装步骤](#32-安装步骤)
  - [3.3 验证安装](#33-验证安装)
  - [3.4 启动后的访问入口](#34-启动后的访问入口)
- [4. API 参考手册](#4-api-参考手册)
  - [4.1 配置模块 `config/`](#41-配置模块-config)
  - [4.2 数据模块 `data/`](#42-数据模块-data)
    - [4.2.1 `DataProvider` — XTquant 行情封装](#421-dataprovider--xtquant-行情封装)
    - [4.2.2 `Database` — SQLite + Parquet 存储引擎](#422-database--sqlite--parquet-存储引擎)
    - [4.2.3 `Downloader` — 数据下载器](#423-downloader--数据下载器)
    - [4.2.4 `XTQuantDataFeed` — backtrader 数据源适配器](#424-xtquantdatafeed--backtrader-数据源适配器)
    - [4.2.5 `qlib_converter` — qlib 格式转换](#425-qlib_converter--qlib-格式转换)
  - [4.3 策略模块 `strategy/`](#43-策略模块-strategy)
    - [4.3.1 `Signal` — 交易信号数据类](#431-signal--交易信号数据类)
    - [4.3.2 `BaseStrategy` — 策略抽象基类](#432-basestrategy--策略抽象基类)
    - [4.3.3 `FactorHandler` — qlib 因子处理器](#433-factorhandler--qlib-因子处理器)
    - [4.3.4 `QlibTrainer` — 模型训练器](#434-qlibtrainer--模型训练器)
    - [4.3.5 `SignalGenerator` — 信号生成器](#435-signalgenerator--信号生成器)
  - [4.4 回测模块 `backtest/`](#44-回测模块-backtest)
    - [4.4.1 内置策略类](#441-内置策略类)
    - [4.4.2 `BacktestRunner` — 回测执行器](#442-backtestrunner--回测执行器)
    - [4.4.3 `BacktestAnalyzer` — 绩效分析器](#443-backtestanalyzer--绩效分析器)
    - [4.4.4 `AShareCommission` / `AShareSizer` — A 股规则](#444-asharecommission--asharesizer--a-股规则)
  - [4.5 交易模块 `trading/`](#45-交易模块-trading)
    - [4.5.1 `AccountConfig` — 账号配置](#451-accountconfig--账号配置)
    - [4.5.2 `TraderManager` — 实盘交易管理器](#452-tradermanager--实盘交易管理器)
    - [4.5.3 `StrategyExecutor` — 策略执行器](#453-strategyexecutor--策略执行器)
  - [4.6 风控模块 `risk/`](#46-风控模块-risk)
    - [4.6.1 `RiskManager` — 风险管理器](#461-riskmanager--风险管理器)
  - [4.7 Web API 路由](#47-web-api-路由)
    - [4.7.1 数据路由 `/api/data`](#471-数据路由-apidata)
    - [4.7.2 策略路由 `/api/strategy`](#472-策略路由-apistrategy)
    - [4.7.3 回测路由 `/api/backtest`](#473-回测路由-apibacktest)
    - [4.7.4 监控路由 `/api/monitor`](#474-监控路由-apimonitor)
    - [4.7.5 风控路由 `/api/risk`](#475-风控路由-apirisk)
- [5. 配置参考](#5-配置参考)
  - [5.1 `config/settings.py`](#51-configsettingspy)
  - [5.2 `config/accounts.yaml`](#52-configaccountsyaml)
- [6. 命令行工具](#6-命令行工具)
- [7. 测试](#7-测试)
- [8. 常见问题](#8-常见问题)
- [9. 贡献指南](#9-贡献指南)
- [10. 许可证](#10-许可证)
- [11. 版本历史](#11-版本历史)

---

## 1. 项目概述

QuantKing 是面向 **A 股市场** 的个人量化交易系统，将策略研发、历史验证和实盘执行整合在统一环境中。

### 核心能力

| 环节 | 实现 | 技术支撑 |
|------|------|----------|
| **行情获取** | 全 A 股日/分钟 K 线、财务数据、板块分类 | XTquant SDK（miniQMT 极简模式） |
| **数据存储** | K 线→Parquet 列式文件，元数据→SQLite 索引 | pyarrow + sqlite3 |
| **因子计算** | 22+ Alpha 因子，qlib 表达式 / pandas 双模式 | qlib / pandas + numpy |
| **模型训练** | LightGBM 多因子模型训练与预测 | qlib + lightgbm + scikit-learn |
| **策略回测** | 事件驱动回测，A 股 T+1/涨跌停/佣金规则 | backtrader |
| **绩效分析** | 总收益、年化收益、最大回撤、夏普、胜率、盈亏比 | quantstats / 自研分析器 |
| **实盘交易** | 限价买卖、撤单、持仓/委托/成交/资产查询 | XTquant Trader API |
| **风险控制** | 单只上限、单笔占比、日亏损熔断、回撤熔断、涨跌停 | 自研 RiskManager |
| **Web 面板** | 仪表盘、回测、策略、数据、监控页面 | FastAPI + 纯 HTML/CSS/JS |

### 设计理念

1. **模块解耦**：数据、策略、回测、交易四层独立，可单独测试和替换
2. **双模式策略**：qlib 因子模式（专业）+ pandas 因子模式（轻量），自动降级
3. **安全第一**：所有实盘下单前强制执行多维风控检查，支持熔断机制
4. **本地优先**：行情数据全量本地缓存（Parquet），离线也可回测
5. **易于扩展**：策略通过注册表管理，新增策略只需实现接口并注册

---

## 2. 系统架构

### 2.1 分层架构图

```
┌──────────────────────────────────────────────────────────────────┐
│                   Web 展示层 (FastAPI + Static HTML)               │
│  ┌───────────┐  ┌───────────┐  ┌───────────┐  ┌──────────────┐ │
│  │ 仪表盘    │  │ 回测页面  │  │ 策略管理  │  │ 交易监控     │ │
│  └───────────┘  └───────────┘  └───────────┘  └──────────────┘ │
├──────────────────────────────────────────────────────────────────┤
│                   策略引擎层 (qlib / pandas)                       │
│  ┌───────────┐  ┌───────────────┐  ┌──────────────────────────┐ │
│  │ 因子计算  │  │ Alpha 信号生成 │  │ 模型训练与预测 (LightGBM)│ │
│  └───────────┘  └───────────────┘  └──────────────────────────┘ │
├──────────────────────────────────────────────────────────────────┤
│                   回测系统层 (backtrader)                          │
│  ┌───────────┐  ┌───────────────┐  ┌──────────────────────────┐ │
│  │ 策略执行  │  │ A股规则模拟   │  │ 绩效分析 (quantstats)    │ │
│  └───────────┘  └───────────────┘  └──────────────────────────┘ │
├──────────────────────────────────────────────────────────────────┤
│                数据层 (xtquant + 本地存储)                         │
│  ┌───────────┐  ┌───────────────┐  ┌──────────────────────────┐ │
│  │ 行情下载  │  │ SQLite+Parquet│  │ qlib 二进制数据转换      │ │
│  └───────────┘  └───────────────┘  └──────────────────────────┘ │
├──────────────────────────────────────────────────────────────────┤
│                 实盘交易层 (xtquant + 风控)                        │
│  ┌───────────┐  ┌───────────────┐  ┌──────────────────────────┐ │
│  │ 订单管理  │  │ 多维风控检查  │  │ 券商柜台对接              │ │
│  └───────────┘  └───────────────┘  └──────────────────────────┘ │
└──────────────────────────────────────────────────────────────────┘
```

### 2.2 数据流图

```
miniQMT 服务器 ──download_history──▶ XTquant 本地缓存
                                         │
                              get_market_data_ex()
                                         │
                                         ▼
                              Parquet K线文件 (data/kline/)
                                │                    │
                    ┌───────────┤                    ├──────────────┐
                    ▼           ▼                    ▼              ▼
             qlib 转换     backtrader数据源    Web API查询    因子计算
             (convert)     (XTQuantDataFeed)   (/api/data)   (FactorHandler)
                │               │                                │
                ▼               ▼                                ▼
         qlib 二进制       cerebro.adddata()           模型训练 (LightGBM)
         (features/)            │                                │
                │               ▼                                ▼
                │        backtrader 回测                   预测分数 Series
                │               │                                │
                ▼               ▼                                ▼
        qlib DataHandler  绩效报告                        SignalGenerator
                │                                            │
                ▼                                            ▼
        Alpha158 因子                                  Top-K 选股列表
                                                        │
                                                        ▼
                                               QlibSignalStrategy
                                               (回测 / 实盘)

实盘路径: SignalGenerator → StrategyExecutor → RiskManager → TraderManager → 券商柜台
```

### 2.3 目录结构

```
QuantKing/
├── config/                          # 全局配置
│   ├── __init__.py
│   ├── settings.py                  # 路径、端口、风控、日志参数
│   └── accounts.yaml                # 交易账号（敏感信息，.gitignore 排除）
├── data/                            # 数据层
│   ├── __init__.py
│   ├── xt_provider.py               # XTquant 行情封装 (DataProvider)
│   ├── database.py                  # SQLite + Parquet 存储引擎 (Database)
│   ├── downloader.py                # 数据下载器 (Downloader)
│   ├── qlib_converter.py            # Parquet → qlib 二进制转换
│   └── backtrader_feeder.py         # DataFrame → backtrader 数据源
├── strategy/                        # 策略引擎
│   ├── __init__.py
│   ├── base.py                      # 策略基类 (BaseStrategy, Signal)
│   ├── alpha_factors.py             # 22+ 因子定义与双模式计算 (FactorHandler)
│   ├── qlib_model.py                # 模型训练与预测 (QlibTrainer)
│   └── signal_generator.py          # 选股信号生成 (SignalGenerator)
├── backtest/                        # 回测系统
│   ├── __init__.py
│   ├── bt_strategy.py               # 6 个 backtrader 策略 + 注册表
│   ├── bt_broker.py                 # A 股佣金方案 (AShareCommission)
│   ├── bt_analyzer.py               # 绩效分析器 (BacktestAnalyzer)
│   └── runner.py                    # 回测执行器 (BacktestRunner)
├── trading/                         # 实盘交易
│   ├── __init__.py
│   ├── xt_trader.py                 # XTquant 实盘管理器 (TraderManager)
│   └── executor.py                  # 策略执行器 (StrategyExecutor)
├── risk/                            # 风险控制
│   ├── __init__.py
│   └── risk_manager.py              # 风控管理器 (RiskManager)
├── web/                             # Web 服务
│   ├── __init__.py
│   ├── app.py                       # FastAPI 应用入口
│   ├── routes/
│   │   ├── __init__.py
│   │   ├── data_routes.py           # /api/data/*
│   │   ├── strategy_routes.py       # /api/strategy/*
│   │   ├── backtest_routes.py       # /api/backtest/*
│   │   ├── monitor_routes.py        # /api/monitor/*
│   │   └── risk_routes.py           # /api/risk/*
│   └── static/
│       └── index.html               # 深色主题仪表盘前端
├── scripts/                         # 命令行工具
│   ├── download_data.py             # 一键下载全量数据
│   ├── convert_to_qlib.py           # qlib 格式转换
│   ├── run_backtest.py              # 命令行回测
│   ├── train_model.py               # 模型训练
│   └── run_strategy.py              # 策略运行
├── tests/                           # 测试套件
│   ├── test_data.py
│   ├── test_strategy.py
│   ├── test_backtest.py
│   └── test_web.py
├── main.py                          # 项目入口（FastAPI + 自动打开浏览器）
├── requirements.txt                 # Python 依赖清单
└── README.md                        # 本文件
```

---

## 3. 快速开始

### 3.1 环境要求

| 项目 | 要求 |
|------|------|
| 操作系统 | **Windows 10/11**（miniQMT 仅支持 Windows） |
| Python | **3.10 或更高**（推荐 3.10.11） |
| QMT 终端 | 券商提供的迅投 QMT 交易终端（需支持极简模式） |
| 磁盘空间 | ≥ 2 GB（全 A 股日 K 线约 300 MB，分钟线更大） |

### 3.2 安装步骤

```powershell
# 1. 克隆项目
git clone <repo-url>
cd QuantKing

# 2. 创建虚拟环境
python -m venv venv
.\venv\Scripts\Activate.ps1

# 3. 安装 Python 依赖
pip install -r requirements.txt

# 4. 安装 XTquant（需手动，路径以实际 QMT 安装位置为准）
pip install "<QMT安装目录>\bin\xtquant\xtquant-*.whl"

# 5. 编辑 config/accounts.yaml，填入账号信息（见 5.2 节）

# 6. 启动 miniQMT（极简模式），确认端口 58610 已监听

# 7. 首次下载数据
python scripts/download_data.py

# 8. 转换 qlib 数据（如使用因子策略）
python scripts/convert_to_qlib.py

# 9. 启动平台
python main.py
```

### 3.3 验证安装

```powershell
# 验证核心依赖
python -c "import xtquant; import qlib; import backtrader; import fastapi; print('OK')"

# 运行测试
pytest tests/ -v
```

### 3.4 启动后的访问入口

| 地址 | 功能 |
|------|------|
| `http://localhost:8000` | 首页仪表盘 |
| `http://localhost:8000/docs` | Swagger API 文档（可在线调试） |
| `http://localhost:8000/backtest` | 回测页面 |
| `http://localhost:8000/strategy` | 策略管理 |
| `http://localhost:8000/data` | 数据管理 |
| `http://localhost:8000/monitor` | 交易监控 |

---

## 4. API 参考手册

### 4.1 配置模块 `config/`

#### 全局配置常量 (`config/settings.py`)

| 常量 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| `BASE_DIR` | `Path` | 自动检测 | 项目根目录绝对路径 |
| `DB_PATH` | `Path` | `BASE_DIR / "quant.db"` | SQLite 数据库文件路径 |
| `KLINE_DIR` | `Path` | `BASE_DIR / "data" / "kline"` | Parquet K 线根目录 |
| `FINANCIAL_DIR` | `Path` | `BASE_DIR / "data" / "financial"` | Parquet 财务数据目录 |
| `QLIB_DATA_DIR` | `Path` | `BASE_DIR / "data" / "qlib_data_cn"` | qlib 二进制数据目录 |
| `XT_DATA_DIR` | `Path` | `BASE_DIR / "xtdata"` | miniQMT 行情缓存目录 |
| `XT_PORT` | `int` | `58610` | miniQMT 行情服务端口 |
| `WEB_HOST` | `str` | `"127.0.0.1"` | Web 服务监听地址 |
| `WEB_PORT` | `int` | `8000` | Web 服务监听端口 |
| `ACCOUNTS_YAML` | `Path` | `BASE_DIR / "config" / "accounts.yaml"` | 账号配置文件路径 |

#### 风控配置字典 `RISK_CONFIG`

| 键 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| `max_position_per_stock` | `int` | `100000` | 单只股票最大持仓（股） |
| `max_single_order_ratio` | `float` | `0.2` | 单笔订单最大资金占比 |
| `max_daily_loss_ratio` | `float` | `0.05` | 日最大亏损比例（触发熔断） |
| `max_drawdown_ratio` | `float` | `0.20` | 最大回撤比例（触发熔断） |
| `max_holdings_count` | `int` | `50` | 最大持仓股票数 |

---

### 4.2 数据模块 `data/`

#### 4.2.1 `DataProvider` — XTquant 行情封装

**源文件**: [data/xt_provider.py](data/xt_provider.py)

封装了 `xtdata` 模块的行情接口，隔离底层依赖。支持上下文管理器协议 (`with`)。

**设计理念**: 将所有 XTquant SDK 调用集中在一层，如果未来需要切换数据源（如换成 Tushare、Wind），只需修改此类。

##### 构造器

```python
DataProvider()
```

实例化后**不会**自动连接，需显式调用 `connect()`。

##### 方法

###### `connect(port: int | None = None) -> bool`

连接 miniQMT 行情服务。

| 参数 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| `port` | `int \| None` | `None`（使用 `XT_PORT`） | 行情服务端口号 |

| 返回 | 说明 |
|------|------|
| `bool` | 连接成功返回 `True` |

| 异常 | 触发条件 |
|------|----------|
| `ImportError` | xtquant 包未安装 |
| `ConnectionError` | 端口未监听或 miniQMT 未启动 |

```python
provider = DataProvider()
provider.connect()
# 或使用上下文管理器
with DataProvider() as provider:
    kline = provider.get_kline(["000001.SZ"])
```

###### `disconnect() -> None`

断开连接，释放网络和缓存资源。

###### `download_history(codes: list[str], period: str = '1d', start_time: str = '', end_time: str = '') -> None`

下载历史 K 线到 XTquant 本地缓存。数据缓存后 `get_kline()` 可直接读取。

| 参数 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| `codes` | `list[str]` | — | 股票代码列表 |
| `period` | `str` | `'1d'` | 周期：`'1d'` / `'1m'` / `'5m'` 等 |
| `start_time` | `str` | `''` | 起始日期，`YYYYMMDD`，空=从头 |
| `end_time` | `str` | `''` | 结束日期，`YYYYMMDD`，空=到最新 |

###### `download_history_incremental(codes: list[str], period: str = '1d') -> None`

增量下载：仅下载本地缺失部分，适合定时更新。

###### `get_kline(codes, period='1d', start_time='', end_time='', count=-1, dividend_type='front') -> pd.DataFrame`

获取已下载的 K 线数据。**必须先调用 `download_history()`**。

| 参数 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| `codes` | `list[str]` | — | 股票代码列表 |
| `period` | `str` | `'1d'` | 周期类型 |
| `start_time` | `str` | `''` | 起始日期 |
| `end_time` | `str` | `''` | 结束日期 |
| `count` | `int` | `-1` | 获取最近 N 根 K 线，`-1`=全部 |
| `dividend_type` | `str` | `'front'` | 复权方式：`'front'` / `'back'` / `'none'` |

| 返回 | 说明 |
|------|------|
| `pd.DataFrame` | index=日期，columns=`(字段, 代码)` 的 MultiIndex，字段：`open/high/low/close/volume/amount` |

###### `get_market_data(codes, period='1d', count=-1, dividend_type='front') -> pd.DataFrame`

获取实时/最新 K 线，**不需要提前下载**，直接从服务端拉取。适合盘中实时场景。

###### `get_stock_list() -> list[str]`

获取沪深 A 股全部股票代码列表。

###### `get_sector_list() -> list[str]`

获取所有板块名称列表。

###### `get_stock_list_in_sector(sector_name: str) -> list[str]`

获取指定板块（如 `"沪深300"`、`"半导体"`）的成分股。

###### `get_instrument_detail(code: str) -> dict`

获取合约基础信息。

| 返回字段 | 类型 | 说明 |
|----------|------|------|
| `InstrumentName` | `str` | 股票名称 |
| `OpenDate` | `str` | 上市日期 |

###### `get_full_tick(codes: list[str]) -> pd.DataFrame`

获取全推 Tick 数据，包含五档买卖盘口。

###### `download_financial_data(codes: list[str]) -> None`

下载财务数据到本地缓存。

###### `get_financial_data(codes: list[str]) -> dict`

获取财务数据。

| 返回 | 说明 |
|------|------|
| `dict` | `{code: {table_name: DataFrame}}` |

###### `get_divid_factors(code: str) -> pd.DataFrame`

获取除权除息因子，用于复权价格计算。

###### `is_connected() -> bool`

检查本对象连接追踪状态。注意：仅反映内存状态，不检测底层 SDK。

---

#### 4.2.2 `Database` — SQLite + Parquet 存储引擎

**源文件**: [data/database.py](data/database.py)

**混合存储设计**:

- **SQLite** 表 (`stocks`, `sectors`, `trade_records`, `kline_index`, `financial_index`)：存储元数据和索引
- **Parquet** 文件 (`data/kline/{period}/{code}.parquet`)：存储 K 线 OHLCV 数据
- 使用 **WAL 模式** 提升并发读写性能
- **非线程安全**：多线程需每个线程创建独立连接

##### 构造器

```python
Database(db_path: str | Path = DB_PATH, data_dir: str | Path = KLINE_DIR, financial_dir: str | Path = FINANCIAL_DIR)
```

| 参数 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| `db_path` | `str \| Path` | `DB_PATH` | SQLite 数据库文件路径 |
| `data_dir` | `str \| Path` | `KLINE_DIR` | Parquet K 线根目录 |
| `financial_dir` | `str \| Path` | `FINANCIAL_DIR` | Parquet 财务数据目录 |

##### 方法

###### `connect() -> None`

打开 SQLite 连接，启用 WAL 模式。

###### `close() -> None`

关闭数据库连接。

###### `initialize() -> None`

创建所有必要的表结构（`stocks` / `sectors` / `trade_records` / `kline_index` / `financial_index`）和目录。幂等操作，可重复调用。

###### `upsert_stocks(records: list[dict]) -> None`

批量写入/更新股票基本信息。

| 参数 | 说明 |
|------|------|
| `records` | 每条含 `code`, `name`, `listing_date`, `status` 键 |

###### `get_all_stocks() -> list[dict]`

返回全部股票信息，每条含 `code` / `name` / `listing_date` / `status`。

###### `insert_sector_records(sector_name: str, stock_codes: list[str]) -> None`

写入板块分类数据（先删后插，覆盖写入）。

###### `get_sector_stocks(sector_name: str) -> list[str]`

返回指定板块的成分股代码列表。

###### `get_all_sectors() -> list[str]`

返回所有已存储的板块名称。

###### `insert_trade_record(record: dict) -> int`

写入一条交易记录，返回自增 ID。

| 必填键 | 可选键 |
|--------|--------|
| `account_id`, `symbol`, `action`, `price`, `volume`, `amount`, `trade_time` | `commission`, `tax`, `status` |

###### `get_trade_records(account_id='', start_date='', end_date='') -> list[dict]`

按账号和时间范围查询交易记录，按时间倒序排列。

###### `insert_daily_kline(records: list[dict], period='1d') -> int`

写入日 K 线到 Parquet 文件（去重合并），更新 `kline_index` 索引表。返回新增记录数。

###### `get_daily_kline_df(code, period='1d', start_date='', end_date='') -> pd.DataFrame`

从 Parquet 读取单只股票 K 线，返回 DataFrame，支持日期过滤。

###### `get_daily_kline(code, start_date='', end_date='') -> list[dict]`

同 `get_daily_kline_df()`，但返回字典列表。

###### `get_latest_kline_date(code, period='1d') -> str | None`

查询某股票在 `kline_index` 中记录的最新日期，用于增量判断。

###### `insert_minute_kline(records, period='1m') -> int` / `get_minute_kline(...) -> list[dict]`

分钟 K 线的读写，复用日 K 线逻辑。

###### `insert_financial(records: list[dict]) -> int` / `get_financial_df(code) -> pd.DataFrame` / `get_financial(code) -> list[dict]`

财务数据的 Parquet 读写，使用 `report_date` 作为去重键。

###### `get_stats() -> dict`

返回 `{stocks, sectors, trades, kline_files, kline_rows}` 统计信息。

###### `get_stock_klines_summary() -> list[dict]`

返回每只股票的 K 线数据概况（起始日期、结束日期、数据条数）。

---

#### 4.2.3 `Downloader` — 数据下载器

**源文件**: [data/downloader.py](data/downloader.py)

负责将 miniQMT 行情数据批量下载并持久化到本地。

##### 构造器

```python
Downloader(provider: DataProvider | None = None, database: Database | None = None)
```

自动创建并连接 `DataProvider` 和 `Database`（如未传入）。

##### 方法

###### `download_all_a_stocks(period='1d', start_time='', end_time='') -> int`

全量下载 A 股 K 线。内置**预检索优化**：先查 SQLite 已覆盖日期，跳过已有数据。

###### `download_stock_info() -> int`

下载股票基本信息（名称、上市日期），仅处理 SQLite 中不存在的股票。

###### `download_sector_data() -> None`

下载板块分类数据并写入 `sectors` 表。

###### `incremental_update(period='1d', days=5) -> int`

增量更新 K 线。对每只股票检查最新日期是否覆盖到今天，跳过已更新的。

###### `download_all_financial() -> int`

下载全量财务数据并入库。

###### `close() -> None`

释放数据库连接（仅关闭内部创建的连接）。

---

#### 4.2.4 `XTQuantDataFeed` — backtrader 数据源适配器

**源文件**: [data/backtrader_feeder.py](data/backtrader_feeder.py)

##### 类 `XTQuantDataFeed(bt.feeds.PandasData)`

继承 backtrader 的 `PandasData`，将已处理好的 DataFrame 注入回测引擎。

```python
params = (
    ('datetime', 0),       # 第 0 列作为时间索引
    ('open', 'open'),
    ('high', 'high'),
    ('low', 'low'),
    ('close', 'close'),
    ('volume', 'volume'),
    ('openinterest', -1),  # 无持仓量
)
```

##### 函数 `load_bt_data(df: pd.DataFrame, dtformat: str = '%Y%m%d') -> bt.feeds.PandasData | None`

将 K 线 DataFrame 转换为 backtrader 数据源。自动将 `date` 列转为 `datetime` 索引。

| 异常 | 条件 |
|------|------|
| `ValueError` | DataFrame 缺少 `open/high/low/close/volume` 任一列 |

##### 函数 `load_multi_stock_data(db, codes, start_date='', end_date='', period='1d') -> dict[str, bt.feeds.PandasData]`

批量加载多只股票数据源，跳过无数据的股票并打印警告。

---

#### 4.2.5 `qlib_converter` — qlib 格式转换

**源文件**: [data/qlib_converter.py](data/qlib_converter.py)

##### 函数 `convert_kline_to_qlib_format(parquet_dir=None, output_dir=None, period='1d') -> int`

将 Parquet K 线转换为 qlib 专有二进制格式。

输出目录结构：
```
data/qlib_data_cn/
├── calendars/day.txt          # 交易日历
├── instruments/all.txt        # 股票列表（code\tstart\tend）
└── features/<code>/
    ├── open.1d.bin
    ├── high.1d.bin
    ├── low.1d.bin
    ├── close.1d.bin
    ├── volume.1d.bin
    └── amount.1d.bin
```

二进制格式：每条记录 `int32(日期) + float32(值)`，小端序。

| 返回 | 说明 |
|------|------|
| `int` | 成功转换的股票数量 |

##### 函数 `validate_qlib_data(qlib_dir=None) -> dict`

验证 qlib 数据完整性。

| 返回字段 | 说明 |
|----------|------|
| `calendars` | 交易日总数 |
| `instruments` | 股票总数 |
| `features` | 有特征目录的股票数 |
| `errors` | 抽样发现的缺失文件列表 |

---

### 4.3 策略模块 `strategy/`

#### 4.3.1 `Signal` — 交易信号数据类

**源文件**: [strategy/base.py](strategy/base.py)

```python
@dataclass
class Signal:
    action: str     # "BUY" / "SELL" / "HOLD"
    symbol: str     # 股票代码，如 "000001.SZ"
    price: float    # 目标价格
    volume: int     # 目标数量（股）
```

信号由策略 `on_bar()` 产生，由 `StrategyExecutor` 统一执行。信号本身不触发下单，只是意图表达。

#### 4.3.2 `BaseStrategy` — 策略抽象基类

**源文件**: [strategy/base.py](strategy/base.py)

```python
class BaseStrategy:
    name: str = ""           # 策略唯一标识
    params: dict = {}        # 默认参数字典

    def init(self, context: dict) -> None: ...
    def on_bar(self, index: int) -> list[Signal]: ...
    def get_params_info(self) -> dict: ...
```

**生命周期**:
1. 实例化策略对象
2. `init(context)` — 接收 `{'kline': DataFrame}`，完成指标预计算
3. 逐根 K 线调用 `on_bar(index)`，返回信号列表

**子类必须覆盖全部三个方法**。

示例：
```python
class MyMACrossStrategy(BaseStrategy):
    name = "ma_cross"
    params = {"fast": 5, "slow": 20}

    def init(self, context):
        df = context['kline']
        self.ma_fast = df['close'].rolling(self.params['fast']).mean()
        self.ma_slow = df['close'].rolling(self.params['slow']).mean()

    def on_bar(self, index):
        if index < self.params['slow']:
            return []
        if self.ma_fast.iloc[index] > self.ma_slow.iloc[index] and \
           self.ma_fast.iloc[index-1] <= self.ma_slow.iloc[index-1]:
            return [Signal("BUY", "", df['close'].iloc[index], 100)]
        return []

    def get_params_info(self):
        return {"fast": "短期均线周期", "slow": "长期均线周期"}
```

#### 4.3.3 `FactorHandler` — qlib 因子处理器

**源文件**: [strategy/alpha_factors.py](strategy/alpha_factors.py)

封装 qlib 因子计算流程，支持 **qlib 原生模式** 和 **pandas 手写模式** 双模式运行。

##### FATOR_META — 因子元信息字典

| 因子名 | 分类 | 说明 |
|--------|------|------|
| `ret_1d` ~ `ret_60d` | 动量 | 各周期收益率 |
| `std_5d`, `std_20d` | 波动率 | 收益率标准差 |
| `hl_amplitude_20d` | 波动率 | 20 日平均振幅 |
| `vol_ratio_5_20`, `vol_ratio_5_60` | 量价 | 量比 |
| `volume_trend_10d` | 量价 | 10 日量能趋势 |
| `ma5_dev` ~ `ma60_dev` | 均线偏离 | 收盘价相对均线的偏离度 |
| `rsi_14` | 技术指标 | 14 日 RSI |
| `macd_dif`, `macd_signal`, `macd_hist` | 技术指标 | MACD 三线 |
| `bb_position` | 技术指标 | 布林带位置 (0~1) |
| `reversal_3d` | 反转 | 3 日反转 |
| `turnover_5d` | 流动性 | 5 日平均换手率（近似） |

##### 构造器

```python
FactorHandler(instruments: str = 'all', start_time: str = '', end_time: str = '')
```

| 参数 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| `instruments` | `str` | `'all'` | 股票范围：`'all'` / `'csi300'` 或自定义列表 |
| `start_time` | `str` | `''` | 起始日期 `YYYYMMDD` |
| `end_time` | `str` | `''` | 结束日期 `YYYYMMDD` |

##### 方法

###### `load_factors(use_qlib: bool = True) -> pd.DataFrame`

加载并计算因子数据。`use_qlib=True` 时优先使用 qlib DataHandler，失败自动回退到 pandas 模式。

返回 MultiIndex `(datetime, instrument)` × 因子名的 DataFrame。

###### `get_factor_names() -> list[str]`

获取当前使用的因子名称列表。

###### `get_factor_meta() -> dict`

获取因子元信息，返回 `FACTOR_META` 字典。

##### qlib 模式下的表达式语法

| 表达式 | 含义 |
|--------|------|
| `$close` | 收盘价 |
| `Ref($close, n)` | n 期前的收盘价 |
| `Mean($close, n)` | n 期均值 |
| `Std($close, n)` | n 期标准差 |
| `Corr($close, $volume, n)` | n 期相关系数 |
| `Rank($close)` | 截面排名 |
| `RSI($close, 14)` | RSI 指标 |

---

#### 4.3.4 `QlibTrainer` — 模型训练器

**源文件**: [strategy/qlib_model.py](strategy/qlib_model.py)

基于 qlib 框架（或 sklearn 回退）的 LightGBM 模型训练封装。

##### 构造器

```python
QlibTrainer(model_type: str = 'LightGBM')
```

| 参数 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| `model_type` | `str` | `'LightGBM'` | 模型类型，可选 `'LightGBM'` / `'XGBoost'` |

##### 方法

###### `train(handler: FactorHandler, target_col: str = 'ret_5d') -> dict`

训练模型。

| 参数 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| `handler` | `FactorHandler` | — | 需已调用 `load_factors()` |
| `target_col` | `str` | `'ret_5d'` | 预测标签列名 |

返回字典包含 `status`, `model_type`, `features`, `feature_importance`（sklearn 模式下）。

**训练流程**：
1. 尝试 `_train_with_qlib()` — qlib 原生 `LGBModel` + `DatasetH`
2. 失败时回退 `_train_sklearn()` — 使用 `lightgbm.LGBMRegressor`，时间序列切分 7:1.5:1.5

| 异常 | 条件 |
|------|------|
| `ImportError` | qlib / lightgbm 未安装 |
| 返回 `{"error": ...}` | 因子数据为空 |

###### `predict(handler: FactorHandler) -> pd.Series`

生成预测分数。必须先调用 `train()` 或 `load()`。

| 异常 | 条件 |
|------|------|
| `RuntimeError` | 模型未训练 |
| `ValueError` | 因子数据为空 |

返回 `pd.Series`，index 为 `(datetime, instrument)`。

###### `save(path: str) -> None`

保存模型到 pickle 文件（含模型对象、类型、特征重要性）。

| 异常 | 条件 |
|------|------|
| `RuntimeError` | 没有可保存的模型 |

###### `load(path: str) -> None`

从 pickle 文件加载模型。

###### `get_feature_importance() -> pd.DataFrame | None`

获取特征重要性表（列：`feature`, `importance`），按重要性降序排列。

---

#### 4.3.5 `SignalGenerator` — 信号生成器

**源文件**: [strategy/signal_generator.py](strategy/signal_generator.py)

将模型预测分数转换为具体的选股列表和调仓指令。

##### 构造器

```python
SignalGenerator()
```

##### 方法

###### `generate(predictions: pd.Series, top_k: int = 20, min_score: float | None = None, blacklist: list[str] | None = None) -> pd.DataFrame`

按预测分数降序选取 Top-K 股票。

| 参数 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| `predictions` | `pd.Series` | — | 预测分数 |
| `top_k` | `int` | `20` | 选股数量 |
| `min_score` | `float \| None` | `None` | 最低分数阈值 |
| `blacklist` | `list[str] \| None` | `None` | 黑名单 |

返回 DataFrame，列：`date` / `code` / `score` / `rank`。

###### `generate_with_risk_control(predictions, positions, top_k=20, max_turnover=0.5) -> dict[str, str]`

生成带换手率限制的调仓指令。

| 参数 | 类型 | 说明 |
|------|------|------|
| `predictions` | `pd.Series` | 预测分数 |
| `positions` | `dict[str, dict]` | 当前持仓 `{code: {volume, cost, ...}}` |
| `top_k` | `int` | 目标持仓数 |
| `max_turnover` | `float` | 最大换手率 (0~1) |

返回 `{code: "BUY" | "SELL" | "HOLD"}`。

###### `filter_by_sector(stock_list, sector_name, database) -> list[str]`

按板块过滤股票列表。

###### `get_latest_signals() -> pd.DataFrame`

获取缓存的最新选股信号。

---

### 4.4 回测模块 `backtest/`

#### 4.4.1 内置策略类

**源文件**: [backtest/bt_strategy.py](backtest/bt_strategy.py)

所有策略继承 `bt.Strategy`，在 `STRATEGY_REGISTRY` 中注册。

| 键名 | 类名 | 策略描述 | 关键参数 |
|------|------|----------|----------|
| `ma_cross` | `MACrossStrategy` | 快慢均线金叉/死叉 | `fast=5`, `slow=20` |
| `macd` | `MACDStrategy` | MACD DIF/DEA 交叉 | `fast=12`, `slow=26`, `signal=9` |
| `rsi` | `RSIStrategy` | RSI 超买超卖 | `period=14`, `oversold=30`, `overbought=70` |
| `bollinger_bands` | `BollingerBandsStrategy` | 布林带下轨买/上轨卖 | `period=20`, `devfactor=2.0` |
| `turtle` | `TurtleStrategy` | 唐奇安通道突破 | `entry_period=20`, `exit_period=10` |
| `qlib_signal` | `QlibSignalStrategy` | qlib 模型 Top-K 选股调仓 | `top_k=20`, `rebalance_freq=20` |

`QlibSignalStrategy` 的核心逻辑：
- 每 `rebalance_freq` 根 K 线触发一次调仓
- 卖出不在目标池的持仓（遵守 T+1 限制）
- 等权买入目标池股票，数量自动调整为整百股

##### 函数 `get_strategy(name: str) -> type`

通过名称获取策略类。

| 异常 | 条件 |
|------|------|
| `ValueError` | 名称未注册 |

新增策略的注册方式：
```python
# 在 bt_strategy.py 中
STRATEGY_REGISTRY['my_strategy'] = MyStrategyClass
```

---

#### 4.4.2 `BacktestRunner` — 回测执行器

**源文件**: [backtest/runner.py](backtest/runner.py)

封装 backtrader 的 Cerebro 引擎，提供一键回测接口。

##### 构造器

```python
BacktestRunner(initial_capital: float = 100000, commission_rate: float = 0.00025)
```

自动配置：初始资金、佣金方案 (`AShareCommission`)、5 个内置 Analyzer（TradeAnalyzer / SharpeRatio / DrawDown / Returns / VWR）。

##### 方法

###### `load_data_from_db(codes, start_date='', end_date='', period='1d') -> int`

从本地 SQLite 加载 K 线到 Cerebro。返回成功加载的股票数。

###### `load_data_from_df(kline_dict: dict[str, pd.DataFrame]) -> int`

从 DataFrame 字典直接加载，无需 SQLite。

###### `set_strategy(strategy_cls_or_name: str | type, **params)`

设置回测策略。接受策略名称字符串或类引用。

###### `run() -> dict`

执行回测。

| 返回字段 | 类型 | 说明 |
|----------|------|------|
| `performance` | `dict` | 完整绩效指标 |
| `initial_capital` | `float` | 初始资金 |
| `final_value` | `float` | 最终资产 |
| `total_return_pct` | `float` | 总收益率（百分比） |
| `timestamp` | `str` | 执行时间 |

###### `run_quick(codes, strategy_name, start_date='', end_date='', **params) -> dict`

一键回测快捷方法：加载数据 → 设置策略 → 执行 → 返回结果。

```python
runner = BacktestRunner(initial_capital=100000)
result = runner.run_quick(
    codes=["000001.SZ", "600519.SH"],
    strategy_name="ma_cross",
    start_date="20230101",
    end_date="20231231",
    fast=5, slow=20
)
```

---

#### 4.4.3 `BacktestAnalyzer` — 绩效分析器

**源文件**: [backtest/bt_analyzer.py](backtest/bt_analyzer.py)

##### 构造器

```python
BacktestAnalyzer()
```

##### 方法

###### `analyze(cerebro: bt.Cerebro, initial_capital: float = 100000) -> dict`

从 Cerebro 结果中提取绩效指标。

| 返回字段 | 类型 | 说明 |
|----------|------|------|
| `total_return` | `float` | 总收益率（小数） |
| `annual_return` | `float` | 年化收益率 |
| `max_drawdown` | `float` | 最大回撤（小数） |
| `sharpe_ratio` | `float` | 年化夏普比率 |
| `win_rate` | `float` | 胜率（小数） |
| `profit_loss_ratio` | `float` | 盈亏比 |
| `total_trades` | `int` | 总交易次数 |
| `trading_days` | `int` | 交易天数 |
| `final_value` | `float` | 最终资产 |
| `equity_curve` | `dict` | 净值曲线 |
| `drawdown_curve` | `dict` | 回撤曲线 |
| `trade_records` | `list[dict]` | 交易记录详情 |

###### `generate_report(result: dict, output_path: str = '') -> str`

生成 HTML 绩效报告（依赖 quantstats）。若 quantstats 不可用则回退到纯文本格式。

###### `format_report(result: dict) -> str`

格式化打印绩效摘要。

##### 算法说明

- **年化收益率**: `(1 + total_return)^(1/years) - 1`，其中 `years = trading_days / 252`
- **最大回撤**: 遍历净值序列，记录历史最高点并计算最大回撤比例
- **夏普比率**: `(日均收益 - 无风险利率) / 日收益标准差 × √252`，无风险利率默认 2%
- **胜率/盈亏比**: 按 `trade.pnl` 正负分别统计

---

#### 4.4.4 `AShareCommission` / `AShareSizer` — A 股规则

**源文件**: [backtest/bt_broker.py](backtest/bt_broker.py)

##### `AShareCommission(bt.CommInfoBase)`

| 参数 | 默认值 | 说明 |
|------|--------|------|
| `commission` | `0.00025` | 佣金费率（万 2.5） |
| `stamp_duty` | `0.001` | 印花税率（千 1，仅卖出） |
| `min_commission` | `5.0` | 最低佣金（元） |

手续费计算公式：`max(成交金额 × 佣金率, 最低佣金) + (卖出时) 成交金额 × 印花税率`

##### `AShareSizer(bt.Sizer)`

| 参数 | 默认值 | 说明 |
|------|--------|------|
| `perc` | `0.1` | 每笔交易投入的资金比例 |

自动将买入数量调整为 100 的整数倍（A 股整百股要求）。

---

### 4.5 交易模块 `trading/`

#### 4.5.1 `AccountConfig` — 账号配置

**源文件**: [trading/xt_trader.py](trading/xt_trader.py)

```python
@dataclass
class AccountConfig:
    id: str            # 账号唯一标识，如 "real"
    label: str         # 显示标签，如 "实盘"
    miniqmt_path: str  # QMT userdata_mini 目录路径
    account_id: str    # 资金账号
    account_type: str = "STOCK"  # 账号类型
```

#### 4.5.2 `TraderManager` — 实盘交易管理器

**源文件**: [trading/xt_trader.py](trading/xt_trader.py)

封装 XTquant 实盘交易接口，与券商柜台直接通信。

> **安全警告**: 所有下单通过 `TraderManager` 直接发送至券商交易柜台，涉及真实资金。请务必在回测充分验证、风控规则合理的情况下使用。

##### 构造器

```python
TraderManager()
```

##### 方法

###### `connect_all(accounts: list[dict] = None) -> dict[str, bool]`

连接所有配置的账号。每个账号创建独立的 `XtQuantTrader` 实例和回调处理。

回调事件：
- `on_disconnected()` — 连接断开
- `on_stock_order(order)` — 委托回报
- `on_stock_trade(trade)` — 成交回报
- `on_account_status(status)` — 账号状态变更

| 返回 | 说明 |
|------|------|
| `dict[str, bool]` | `{账号ID: 连接是否成功}` |

###### `buy(account_id: str, code: str, price: float, volume: int) -> bool`

限价买入。`volume` 建议为 100 的整数倍。返回下单是否成功。

###### `sell(account_id: str, code: str, price: float, volume: int) -> bool`

限价卖出。

###### `cancel_order(account_id: str, order_id: int) -> bool`

撤单。`order_id` 为下单方法返回的委托编号。

###### `query_positions(account_id: str) -> list[dict]`

查询持仓。每条含 `stock_code` / `volume` / `can_use_volume` / `open_price` / `market_value`。

###### `query_orders(account_id: str) -> list[dict]`

查询当日委托。每条含 `order_id` / `stock_code` / `order_volume` / `traded_volume` / `price` / `status`。

###### `query_trades(account_id: str) -> list[dict]`

查询当日成交。每条含 `order_id` / `stock_code` / `traded_volume` / `traded_price` / `traded_time`。

###### `query_asset(account_id: str) -> dict | None`

查询账户资产。返回 `{account_id, total_asset, available_cash, market_value}`。

###### `is_connected(account_id: str) -> bool`

检查指定账号连接状态。

###### `get_connected_accounts() -> list[str]`

获取所有已连接账号的 ID 列表。

###### `disconnect_all() -> None`

断开所有连接并清理资源。

---

#### 4.5.3 `StrategyExecutor` — 策略执行器

**源文件**: [trading/executor.py](trading/executor.py)

提供 **行情获取 → 策略运算 → 风险管理 → 交易执行 → 记录保存** 完整流水线。

##### 构造器

```python
StrategyExecutor(account_id: str, strategy_cls: type[BaseStrategy], trader_manager: TraderManager,
                provider: DataProvider | None = None, database: Database | None = None)
```

##### 方法

###### `set_stock_list(codes: list[str]) -> None`

设置执行的股票池。

###### `run_once() -> list[dict]`

运行一次完整执行流程：

1. 股票池为空时自动取前 50 只 A 股
2. 验证账号连接状态
3. 批量下载 K 线并逐股票运行策略
4. 对每个信号执行买入/卖出风险检查
5. 通过 `TraderManager` 下达实盘指令
6. 记录成交到本地数据库

返回已执行信号列表。

###### `run_loop(interval_seconds: int = 60) -> None`

启动 daemon 线程定时循环执行。首次立即执行。

###### `stop() -> None`

停止策略循环，等待线程退出并清理资源。

---

### 4.6 风控模块 `risk/`

#### 4.6.1 `RiskManager` — 风险管理器

**源文件**: [risk/risk_manager.py](risk/risk_manager.py)

多维风险控制，所有实盘交易前需通过检查。支持熔断机制。

##### 构造器

```python
RiskManager(config: dict = None)
```

| 参数 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| `config` | `dict` | `RISK_CONFIG` | 风控参数 |

##### 方法

###### `reset_daily(equity: float, date: str = '') -> None`

每日重置风险计数器（`daily_pnl`, `daily_trade_count`, 熔断状态）。应在交易日开始时调用。

###### `check_buy(code, price, volume, cash, positions, prev_close=0) -> tuple[bool, str]`

买入前多维风险检查：

1. 熔断状态检查
2. 涨停过滤（`price >= prev_close × 1.1`）
3. 单笔金额占比（`price × volume / cash ≤ max_single_order_ratio`）
4. 资金充足性（含佣金）
5. 单只股票持仓上限
6. 总持仓数量上限

返回 `(是否通过, 拒绝原因)`。

###### `check_sell(code, volume, positions, prev_close=0, buy_date='', current_date='') -> tuple[bool, str]`

卖出前风险检查：

1. 熔断状态检查
2. 持仓充足性
3. T+1 限制（当日买入不可卖）

###### `check_market(price, prev_close, is_buy=True) -> tuple[bool, str]`

涨跌停市场规则检查。`is_buy=True` 检查涨停，`False` 检查跌停。

###### `update_daily_pnl(trade_pnl: float) -> None`

更新当日累计盈亏。

###### `check_daily_loss(current_equity: float) -> tuple[bool, str]`

检查日亏损是否触发熔断：`(start_equity - current_equity) / start_equity ≥ max_daily_loss_ratio`

###### `check_drawdown(peak_equity: float, current_equity: float) -> tuple[bool, str]`

检查最大回撤是否触发熔断：`(peak - current) / peak ≥ max_drawdown_ratio`

###### `is_meltdown() -> bool`

查询是否处于熔断状态。

###### `reset_meltdown() -> None`

手动重置熔断状态（需人工确认后调用）。

###### `get_risk_summary() -> dict`

返回 `{meltdown, meltdown_reason, daily_pnl, daily_trade_count, start_equity, daily_pnl_ratio}`。

**熔断机制流程**：
```
每个交易日开始 → reset_daily(equity)
         ↓
每笔交易前 → check_buy() / check_sell()
         ↓
收盘或定时 → check_daily_loss()
              check_drawdown()
         ↓
   熔断触发 → 当日停止所有交易
         ↓
   次日 → reset_daily() 自动复位（或手动 reset_meltdown()）
```

---

### 4.7 Web API 路由

所有 API 前缀为 `/api/`，返回 JSON 格式 `{"status": "ok", "data": ...}` 或 `{"status": "error", "message": ...}`。

#### 4.7.1 数据路由 `/api/data`

**源文件**: [web/routes/data_routes.py](web/routes/data_routes.py)

| 方法 | 路径 | 说明 |
|------|------|------|
| `GET` | `/api/data/kline` | 查询单只股票 K 线 |
| `GET` | `/api/data/stocks` | 获取全部股票列表 |
| `GET` | `/api/data/sectors` | 获取板块列表 |
| `GET` | `/api/data/sector_stocks` | 获取板块成分股 |
| `GET` | `/api/data/db-status` | 数据库统计信息 |
| `GET` | `/api/data/stock-klines` | 股票 K 线概况 |
| `GET` | `/api/data/financial` | 查询财务数据 |
| `POST` | `/api/data/stocks/sync` | 同步股票基本信息 |
| `POST` | `/api/data/sectors/sync` | 同步板块数据 |
| `POST` | `/api/data/kline/download` | 下载全量 K 线 |
| `POST` | `/api/data/kline/update` | 增量更新 K 线 |
| `POST` | `/api/data/financial/download` | 下载财务数据 |
| `POST` | `/api/data/financial/download-single` | 下载单只股票财务数据 |

##### 查询参数

**`GET /api/data/kline`**

| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `code` | `str` | 是 | 股票代码，如 `000001.SZ` |
| `period` | `str` | 否 | 周期，默认 `1d` |
| `start` | `str` | 否 | 起始日期 `YYYYMMDD` |
| `end` | `str` | 否 | 结束日期 `YYYYMMDD` |

**`POST /api/data/kline/download`**

| Body 字段 | 类型 | 必填 | 说明 |
|-----------|------|------|------|
| `period` | `str` | 否 | 周期，默认 `1d` |

##### 响应示例

```json
{
  "code": "000001.SZ",
  "count": 242,
  "data": [
    {"code": "000001.SZ", "date": "20230103", "open": 13.10, "high": 13.25, "low": 12.92, "close": 13.18, "volume": 45678900}
  ]
}
```

---

#### 4.7.2 策略路由 `/api/strategy`

**源文件**: [web/routes/strategy_routes.py](web/routes/strategy_routes.py)

| 方法 | 路径 | 说明 |
|------|------|------|
| `GET` | `/api/strategy/list` | 获取可用策略列表 |
| `GET` | `/api/strategy/factors` | 获取因子元信息（含分类） |
| `POST` | `/api/strategy/train` | 训练模型 |
| `POST` | `/api/strategy/predict` | 生成选股预测 |
| `GET` | `/api/strategy/signals` | 获取缓存的最新选股信号 |
| `GET` | `/api/strategy/importance` | 特征重要性（提示接口） |

##### `POST /api/strategy/train` 请求体 (`TrainRequest`)

| 字段 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| `instruments` | `str` | `"all"` | 股票范围 |
| `start_time` | `str` | `""` | 训练起始日期 |
| `end_time` | `str` | `""` | 训练结束日期 |
| `model_type` | `str` | `"LightGBM"` | 模型类型 |
| `top_k` | `int` | `20` | 选股数量 |

##### `POST /api/strategy/predict` 请求体 (`PredictRequest`)

| 字段 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| `instruments` | `str` | `"all"` | 股票范围 |
| `start_time` | `str` | `""` | 预测起始日期 |
| `end_time` | `str` | `""` | 预测结束日期 |
| `model_path` | `str` | `""` | 预训练模型路径（空则先训练） |
| `top_k` | `int` | `20` | 选股数量 |
| `min_score` | `float` | `None` | 最低分数阈值 |

---

#### 4.7.3 回测路由 `/api/backtest`

**源文件**: [web/routes/backtest_routes.py](web/routes/backtest_routes.py)

| 方法 | 路径 | 说明 |
|------|------|------|
| `GET` | `/api/backtest/strategies` | 获取可用回测策略及参数 |
| `POST` | `/api/backtest/run` | 执行回测（完整参数） |
| `POST` | `/api/backtest/run_quick` | 快速回测（简化参数） |
| `GET` | `/api/backtest/history` | 回测历史记录（最近 20 条） |
| `POST` | `/api/backtest/compare` | 多策略对比回测 |

##### `POST /api/backtest/run` 请求体 (`BacktestRequest`)

| 字段 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| `strategy_name` | `str` | `"ma_cross"` | 策略名称 |
| `stock_codes` | `list[str]` | `["000001.SZ"]` | 股票代码列表 |
| `start_date` | `str` | `""` | 起始日期 |
| `end_date` | `str` | `""` | 结束日期 |
| `initial_capital` | `float` | `100000` | 初始资金 |
| `params` | `dict` | `{}` | 策略参数字典 |

##### `POST /api/backtest/run_quick` 请求体 (`QuickBacktestRequest`)

| 字段 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| `strategy_name` | `str` | `"ma_cross"` | 策略名称 |
| `stock_codes` | `list[str]` | `["000001.SZ"]` | 股票代码列表 |
| `start_date` | `str` | `"20230101"` | 起始日期 |
| `end_date` | `str` | `"20231231"` | 结束日期 |
| `initial_capital` | `float` | `100000` | 初始资金 |
| `fast` | `int` | `5` | 快线参数 |
| `slow` | `int` | `20` | 慢线参数 |

##### `POST /api/backtest/compare` 请求体

| 字段 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| `stock_codes` | `list[str]` | `["000001.SZ"]` | 股票代码列表 |
| `strategies` | `list[str]` | `["ma_cross","macd"]` | 策略名称列表 |
| `start_date` | `str` | `"20230101"` | 起始日期 |
| `end_date` | `str` | `"20231231"` | 结束日期 |
| `initial_capital` | `float` | `100000` | 初始资金 |

返回按收益率降序排列的对比结果。

---

#### 4.7.4 监控路由 `/api/monitor`

**源文件**: [web/routes/monitor_routes.py](web/routes/monitor_routes.py)

| 方法 | 路径 | 说明 | 查询参数 |
|------|------|------|----------|
| `GET` | `/api/monitor/positions` | 持仓查询 | `account_id`（默认 `real`） |
| `GET` | `/api/monitor/orders` | 当日委托 | `account_id` |
| `GET` | `/api/monitor/trades` | 当日成交 | `account_id` |
| `GET` | `/api/monitor/asset` | 账户资产 | `account_id` |
| `GET` | `/api/monitor/accounts` | 账号连接状态 | — |
| `GET` | `/api/monitor/records` | 本地交易记录 | `account_id`, `start`, `end` |
| `GET` | `/api/monitor/dashboard` | 仪表盘摘要 | `account_id` |

---

#### 4.7.5 风控路由 `/api/risk`

**源文件**: [web/routes/risk_routes.py](web/routes/risk_routes.py)

| 方法 | 路径 | 说明 |
|------|------|------|
| `GET` | `/api/risk/status` | 获取当前风险状态 |
| `GET` | `/api/risk/config` | 获取风控参数配置 |
| `POST` | `/api/risk/reset` | 重置熔断状态（谨慎操作） |
| `POST` | `/api/risk/check_order` | 模拟订单风险检查 |

##### `POST /api/risk/check_order` 请求体

| 字段 | 类型 | 说明 |
|------|------|------|
| `action` | `str` | `"BUY"` / `"SELL"` |
| `code` | `str` | 股票代码 |
| `price` | `float` | 目标价格 |
| `volume` | `int` | 目标数量 |
| `cash` | `float` | 可用资金（买入时必填） |
| `positions` | `dict` | 持仓信息 |
| `prev_close` | `float` | 前收盘价 |

响应：
```json
{
  "status": "ok",
  "passed": true,
  "reason": "OK",
  "meltdown": false
}
```

---

## 5. 配置参考

### 5.1 `config/settings.py`

```python
# ── 路径配置 ──
BASE_DIR        = Path(__file__).resolve().parent.parent  # 项目根目录
DB_PATH         = BASE_DIR / "quant.db"                     # SQLite 数据库
KLINE_DIR       = BASE_DIR / "data" / "kline"               # K 线 Parquet 根目录
FINANCIAL_DIR   = BASE_DIR / "data" / "financial"           # 财务数据目录
QLIB_DATA_DIR   = BASE_DIR / "data" / "qlib_data_cn"        # qlib 二进制数据
XT_DATA_DIR     = BASE_DIR / "xtdata"                       # miniQMT 行情缓存

# ── 服务配置 ──
XT_PORT = 58610        # miniQMT 行情服务端口
WEB_HOST = "127.0.0.1" # Web 服务地址
WEB_PORT = 8000        # Web 服务端口

# ── 风控配置 ──
RISK_CONFIG = {
    "max_position_per_stock": 100000,    # 单只股票最大持仓（股）
    "max_single_order_ratio": 0.20,     # 单笔订单最大资金占比
    "max_daily_loss_ratio": 0.05,       # 日亏损熔断阈值
    "max_drawdown_ratio": 0.20,         # 最大回撤熔断阈值
    "max_holdings_count": 50,           # 最大持仓股票数
}

# ── 日志配置 ──
LOG_CONFIG = {
    "level": "INFO",
    "file": "logs/quant.log",
    "max_bytes": 10 * 1024 * 1024,      # 10 MB
    "backup_count": 5,
}
```

### 5.2 `config/accounts.yaml`

> 此文件已被 `.gitignore` 排除，包含资金账号等敏感信息，请勿提交到版本控制。

```yaml
accounts:
  - id: "real"                              # 账号唯一标识
    label: "实盘"                            # 显示标签
    miniqmt_path: "E:\\券商QMT交易端\\userdata_mini"  # QMT userdata_mini 路径
    account_id: "你的资金账号"                # 资金账号
    account_type: "STOCK"                    # 账号类型
```

支持配置多个账号（如多券商），系统会逐一连接。

---

## 6. 命令行工具

所有脚本位于 `scripts/` 目录。

```powershell
# 下载全量 A 股数据（首次使用必执行）
python scripts/download_data.py

# 转换 qlib 二进制数据（使用因子策略前必执行）
python scripts/convert_to_qlib.py

# 命令行回测
python scripts/run_backtest.py --strategy ma_cross --codes 000001.SZ --start 20230101 --end 20231231

# 训练 LightGBM 模型
python scripts/train_model.py --start 20230101 --end 20231231 --model LightGBM

# 运行实盘策略
python scripts/run_strategy.py
```

---

## 7. 测试

```powershell
# 全部测试
pytest tests/ -v

# 按模块
pytest tests/test_data.py -v      # 数据模块
pytest tests/test_strategy.py -v   # 策略模块
pytest tests/test_backtest.py -v   # 回测模块
pytest tests/test_web.py -v        # Web API
```

测试文件与模块对应关系：

| 测试文件 | 覆盖模块 |
|----------|----------|
| `test_data.py` | `xt_provider`, `database`, `downloader`, `qlib_converter` |
| `test_strategy.py` | `alpha_factors`, `qlib_model`, `signal_generator` |
| `test_backtest.py` | `bt_strategy`, `bt_broker`, `runner`, `bt_analyzer` |
| `test_web.py` | `app.py` 及各路由模块 |

---

## 8. 常见问题

<details>
<summary><strong>miniQMT 连接失败？</strong></summary>

1. 确认 QMT 交易端已登录"极简模式"
2. 确认端口 `58610` 未被占用：`netstat -ano | findstr 58610`
3. 检查防火墙是否拦截本地连接
4. 确认 xtquant 已安装：`pip list | findstr xtquant`
</details>

<details>
<summary><strong>qlib 初始化报错 "No data found"？</strong></summary>

qlib 需要专有二进制格式。运行：
```powershell
python scripts/convert_to_qlib.py
```
若不需要 qlib，因子计算会自动回退到 pandas 模式（从 Parquet 读取），无需 qlib 环境。
</details>

<details>
<summary><strong>回测返回 "未加载到任何K线数据"？</strong></summary>

目标股票尚未下载 K 线。请先运行 `python scripts/download_data.py` 或通过 Web 面板触发下载。
</details>

<details>
<summary><strong>backtrader 导入失败或与 pandas 不兼容？</strong></summary>

backtrader 暂未适配 pandas 3.x。确保 `pandas<3.0`：
```powershell
pip install "pandas>=2.0,<3.0"
```
</details>

<details>
<summary><strong>如何添加自定义回测策略？</strong></summary>

1. 在 `backtest/bt_strategy.py` 中创建继承 `bt.Strategy` 的类
2. 在 `STRATEGY_REGISTRY` 注册

```python
class MyStrategy(bt.Strategy):
    params = (('my_param', 10),)

    def __init__(self):
        self.sma = bt.indicators.SMA(self.data.close, period=self.params.my_param)

    def next(self):
        if self.data.close[0] > self.sma[0]:
            self.buy()
        elif self.position:
            self.sell()

STRATEGY_REGISTRY['my_strategy'] = MyStrategy
```

注册后可通过 API `POST /api/backtest/run` 指定 `"strategy_name": "my_strategy"` 调用。
</details>

<details>
<summary><strong>如何添加自定义因子？</strong></summary>

在 `strategy/alpha_factors.py` 中：

1. 在 `FACTOR_META` 添加元信息
2. 在 `QLIB_FACTOR_EXPRESSIONS` 添加 qlib 表达式
3. 在 `QLIB_FACTOR_NAMES` 添加因子名
4. 在 `_compute_factors_pandas()` 中实现 pandas 版本的计算逻辑
</details>

<details>
<summary><strong>实盘交易需要注意什么？</strong></summary>

1. **回测 ≠ 未来表现**，充分验证后再实盘
2. 所有实盘下单前务必通过 `RiskManager` 风控检查
3. 买卖数量为 **100 的整数倍**（A 股要求）
4. `config/accounts.yaml` 不要提交到 Git
5. 首次使用建议小资金测试，确认链路通畅
</details>

<details>
<summary><strong>如何执行定时策略？</strong></summary>

```python
from trading.executor import StrategyExecutor
from trading.xt_trader import TraderManager
from strategy.base import BaseStrategy

tm = TraderManager()
tm.connect_all()

executor = StrategyExecutor("real", MyStrategy, tm)
executor.set_stock_list(["000001.SZ", "600519.SH"])
executor.run_loop(interval_seconds=60)  # 每分钟执行一次
```
</details>

---

## 9. 贡献指南

### 开发环境

```powershell
git clone <repo-url>
cd QuantKing
python -m venv venv
.\venv\Scripts\Activate.ps1
pip install -r requirements.txt
pytest tests/ -v
```

### 代码规范

- **编码声明**: 每个 `.py` 文件首行添加 `# -*- coding: utf-8 -*-`
- **风格标准**: PEP 8
- **类型注解**: 对公开方法使用 Type Hints
- **文档字符串**: 公开类和方法编写 docstring
- **提交消息**: 使用清晰的中文或英文描述
- **分支策略**: 从 `main` 创建功能分支，完成后 PR

### 项目约定

- 配置集中在 `config/settings.py`，避免硬编码
- 新模块使用 `__init__.py` 暴露公开接口
- 所有 import 使用绝对路径从项目根目录开始（如 `from data.database import Database`）

---

## 10. 许可证

本项目采用 **MIT License**。

> **免责声明**: 本软件仅供学习和研究使用。使用本软件进行实盘交易的一切风险和后果由使用者自行承担。作者不对任何因使用本软件导致的直接或间接损失负责。投资有风险，入市需谨慎。

---

## 11. 版本历史

### v2.0.0 (2025)

- 全新架构：XTquant + qlib + backtrader + FastAPI
- 新增 qlib 多因子策略引擎（22+ Alpha 因子，qlib/pandas 双模式）
- 新增 backtrader 回测系统（6 个内置策略，A 股 T+1/涨跌停/佣金规则）
- 新增风险控制模块（多维风控 + 日亏损/回撤双熔断机制）
- 新增 Web 仪表盘和完整 REST API（33+ 接口）
- 新增策略执行器（定时循环实盘交易）
- 数据层升级为 Parquet + SQLite 混合存储
- 新增 qlib 数据转换与验证工具

### v1.0.0 (2024)

- 初始版本：基于 XTquant 的数据下载和实盘交易
- 自研回测引擎
- 基础策略框架（`BaseStrategy` + `Signal`）
- FastAPI Web 服务
