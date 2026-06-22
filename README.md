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
  - [4.2 工具模块 `utils/`](#42-工具模块-utils)
    - [4.2.1 `logging` — 统一日志](#421-logging--统一日志)
    - [4.2.2 `retry` — 重试装饰器](#422-retry--重试装饰器)
    - [4.2.3 `trading_hours` — 交易时段判断](#423-trading_hours--交易时段判断)
  - [4.3 数据模块 `data/`](#43-数据模块-data)
    - [4.3.1 `DataProvider` — XTquant 行情封装](#431-dataprovider--xtquant-行情封装)
    - [4.3.2 `Database` — SQLite + Parquet 存储引擎](#432-database--sqlite--parquet-存储引擎)
    - [4.3.3 `Downloader` — 数据下载器](#433-downloader--数据下载器)
    - [4.3.4 `XTQuantDataFeed` — backtrader 数据源适配器](#434-xtquantdatafeed--backtrader-数据源适配器)
    - [4.3.5 `qlib_converter` — qlib 格式转换](#435-qlib_converter--qlib-格式转换)
    - [4.3.6 `DataValidator` — 数据健康检查](#436-datavalidator--数据健康检查)
  - [4.4 策略模块 `strategy/`](#44-策略模块-strategy)
    - [4.4.1 `Signal` — 交易信号数据类](#441-signal--交易信号数据类)
    - [4.4.2 `BaseStrategy` — 策略抽象基类](#442-basestrategy--策略抽象基类)
    - [4.4.3 `strategy.registry` — 统一策略注册中心](#443-strategyregistry--统一策略注册中心)
    - [4.4.4 `FactorHandler` — qlib 因子处理器](#444-factorhandler--qlib-因子处理器)
    - [4.4.5 `QlibTrainer` — 模型训练器](#445-qlibtrainer--模型训练器)
    - [4.4.6 `SignalGenerator` — 信号生成器](#446-signalgenerator--信号生成器)
  - [4.5 回测模块 `backtest/`](#45-回测模块-backtest)
    - [4.5.1 内置策略类](#451-内置策略类)
    - [4.5.2 `BacktestRunner` — 回测执行器](#452-backtestrunner--回测执行器)
    - [4.5.3 `BacktestAnalyzer` — 绩效分析器](#453-backtestanalyzer--绩效分析器)
    - [4.5.4 `AShareCommission` / `AShareSizer` — A 股规则](#454-asharecommission--asharesizer--a-股规则)
  - [4.6 交易模块 `trading/`](#46-交易模块-trading)
    - [4.6.1 `AccountConfig` — 账号配置](#461-accountconfig--账号配置)
    - [4.6.2 `TraderManager` — 实盘交易管理器](#462-tradermanager--实盘交易管理器)
    - [4.6.3 `StrategyExecutor` — 策略执行器](#463-strategyexecutor--策略执行器)
  - [4.7 风控模块 `risk/`](#47-风控模块-risk)
    - [4.7.1 `RiskManager` — 风险管理器](#471-riskmanager--风险管理器)
  - [4.8 Web API 路由](#48-web-api-路由)
    - [4.8.1 鉴权中间件](#481-鉴权中间件)
    - [4.8.2 数据路由 `/api/data`](#482-数据路由-apidata)
    - [4.8.3 策略路由 `/api/strategy`](#483-策略路由-apistrategy)
    - [4.8.4 回测路由 `/api/backtest`](#484-回测路由-apibacktest)
    - [4.8.5 监控路由 `/api/monitor`](#485-监控路由-apimonitor)
    - [4.8.6 风控路由 `/api/risk`](#486-风控路由-apirisk)
- [5. 配置参考](#5-配置参考)
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
| **风险控制** | 单只上限、单笔占比、日亏损熔断、回撤熔断、按板块涨跌停 | 自研 RiskManager |
| **Web 面板** | 仪表盘、回测、策略、数据、监控页面 + API Key 鉴权 | FastAPI + 纯 HTML/CSS/JS |
| **基础设施** | 统一日志、指数退避重试、交易时段判断、审计日志 | 自研 utils/ |

### 设计理念

1. **模块解耦**：数据、策略、回测、交易四层独立，可单独测试和替换
2. **双模式策略**：qlib 因子模式（专业）+ pandas 因子模式（轻量），自动降级
3. **安全第一**：Web API Key 鉴权 + 所有实盘下单前多维风控检查 + 审计日志 + 熔断机制
4. **本地优先**：行情数据全量本地缓存（Parquet），离线也可回测
5. **易于扩展**：统一的策略注册中心（`strategy.registry`），支持装饰器注册

---

## 2. 系统架构

### 2.1 分层架构图

```
┌──────────────────────────────────────────────────────────────────┐
│                   Web 展示层 (FastAPI + API Key 鉴权)              │
│  ┌───────────┐  ┌───────────┐  ┌───────────┐  ┌──────────────┐ │
│  │ 仪表盘    │  │ 回测页面  │  │ 策略管理  │  │ 交易监控     │ │
│  └───────────┘  └───────────┘  └───────────┘  └──────────────┘ │
├──────────────────────────────────────────────────────────────────┤
│                   策略引擎层 (qlib / pandas)                       │
│  ┌───────────┐  ┌───────────────┐  ┌──────────────────────────┐ │
│  │ 因子计算  │  │ Alpha 信号生成 │  │ 模型训练与预测 (LightGBM)│ │
│  └───────────┘  └───────────────┘  └──────────────────────────┘ │
│  ┌───────────────────────────────────────────────────────────┐  │
│  │           strategy.registry — 统一策略注册中心              │  │
│  └───────────────────────────────────────────────────────────┘  │
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
├──────────────────────────────────────────────────────────────────┤
│                基础设施层 (utils/)                                 │
│  ┌───────────┐  ┌───────────────┐  ┌──────────────────────────┐ │
│  │ 统一日志  │  │ 重试装饰器    │  │ 交易时段判断              │ │
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
                                         ┌─ QlibSignalStrategy (回测)
                                         └─ StrategyExecutor   (实盘)

实盘路径: SignalGenerator → StrategyExecutor → RiskManager → TraderManager → 券商柜台
```

### 2.3 目录结构

```
QuantKing/
├── config/                          # 全局配置
│   ├── __init__.py
│   ├── settings.py                  # 路径、端口、风控、日志、API Key
│   ├── accounts.yaml                # 交易账号（敏感信息，.gitignore 排除）
│   └── risk.yaml                    # 风控参数（可选，覆盖默认值）
├── utils/                           # 基础设施工具
│   ├── __init__.py
│   ├── logging.py                   # 统一日志工厂 (get_logger)
│   ├── retry.py                     # 指数退避重试装饰器 (retry_on_failure)
│   └── trading_hours.py             # 交易时段常量与判断函数
├── data/                            # 数据层
│   ├── __init__.py
│   ├── xt_provider.py               # XTquant 行情封装 (DataProvider)
│   ├── database.py                  # SQLite + Parquet 存储引擎 (Database)
│   ├── downloader.py                # 数据下载器 (Downloader)
│   ├── qlib_converter.py            # Parquet → qlib 二进制转换
│   ├── backtrader_feeder.py         # DataFrame → backtrader 数据源
│   └── data_validator.py            # K 线数据健康检查器 (DataValidator)
├── strategy/                        # 策略引擎
│   ├── __init__.py                  # 公开接口导出
│   ├── base.py                      # 策略基类 (BaseStrategy, Signal)
│   ├── registry.py                  # 统一策略注册中心 (REGISTRY)
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
│   ├── app.py                       # FastAPI 应用入口 + API Key 鉴权中间件
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
│   ├── __init__.py
│   ├── download_data.py             # 数据下载（支持多参数）
│   ├── convert_to_qlib.py           # qlib 格式转换
│   ├── run_backtest.py              # 命令行回测
│   ├── train_model.py               # 模型训练
│   └── run_strategy.py              # 策略运行
├── tests/                           # 测试套件
│   ├── __init__.py
│   ├── test_data.py                 # 数据存储与 qlib 转换
│   ├── test_downloader.py           # 数据健康检查 (DataValidator)
│   ├── test_strategy.py             # 因子、模型、信号、注册中心
│   ├── test_backtest.py             # 回测策略、佣金、执行器、分析器
│   ├── test_risk.py                 # 风控与熔断
│   ├── test_trading.py              # 账号配置与交易管理器（mock）
│   ├── test_web.py                  # Web API 与路由
│   └── test_batch_a_fixes.py        # 批次 A 修复回归测试
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

# 5. 编辑 config/accounts.yaml，填入账号信息

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

> 敏感 API（如 `/api/monitor`、`/api/risk`）需要 `X-API-Key` 请求头鉴权。默认 Key 为 `quant-local-dev`，可通过环境变量 `WEB_API_KEY` 覆盖。

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
| `WEB_API_KEY` | `str` | `os.environ.get("WEB_API_KEY", "quant-local-dev")` | API 鉴权密钥 |
| `ACCOUNTS_YAML` | `Path` | `BASE_DIR / "config" / "accounts.yaml"` | 账号配置文件路径 |
| `RISK_CONFIG_PATH` | `Path` | `BASE_DIR / "config" / "risk.yaml"` | 风控配置文件路径（可选） |
| `ACCOUNTS` | `list` | 从 accounts.yaml 加载 | 实盘交易账号配置列表 |
| `RISK_CONFIG` | `dict` | 见下表 | 风险控制参数（可被 risk.yaml 覆盖） |
| `LOG_CONFIG` | `dict` | 日志配置字典 | level/file/max_bytes/backup_count |

**`ACCOUNTS` 从 YAML 加载逻辑**：优先读取 `accounts.yaml`，失败时使用代码中的默认配置。

#### 风控配置 `RISK_CONFIG`

| 键 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| `max_position_per_stock` | `int` | `100000` | 单只股票最大持仓（股） |
| `max_single_order_ratio` | `float` | `0.2` | 单笔订单最大资金占比 |
| `max_daily_loss_ratio` | `float` | `0.05` | 日最大亏损比例（触发熔断） |
| `max_drawdown_ratio` | `float` | `0.20` | 最大回撤比例（触发熔断） |
| `max_holdings_count` | `int` | `50` | 最大持仓股票数 |

> 可在 `config/risk.yaml` 中覆盖以上参数，格式同 `RISK_CONFIG` 字典。

---

### 4.2 工具模块 `utils/`

#### 4.2.1 `logging` — 统一日志

**源文件**: [utils/logging.py](utils/logging.py)

所有模块通过此工厂函数获取统一的日志器实例，确保日志格式一致。

##### `get_logger(name: str) -> logging.Logger`

创建或获取一个命名日志器。自动从 `LOG_CONFIG` 读取日志级别和格式。

| 参数 | 类型 | 说明 |
|------|------|------|
| `name` | `str` | 日志器名称，通常传 `__name__` |

```python
from utils.logging import get_logger
logger = get_logger(__name__)
logger.info("策略开始执行")
```

---

#### 4.2.2 `retry` — 重试装饰器

**源文件**: [utils/retry.py](utils/retry.py)

提供指数退避重试机制，适用于网络调用等瞬时故障场景。

##### `retry_on_failure(max_retries: int = 3, base_delay: float = 1.0, exceptions: tuple = (Exception,), logger=None) -> Callable`

装饰器工厂，返回一个装饰器。被装饰的函数在抛出指定异常时自动重试。

| 参数 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| `max_retries` | `int` | `3` | 最大重试次数 |
| `base_delay` | `float` | `1.0` | 基础延迟（秒），每次重试延迟翻倍 |
| `exceptions` | `tuple` | `(Exception,)` | 触发重试的异常类型元组 |
| `logger` | `Logger \| None` | `None` | 日志器，不传则用 `print` |

算法：第 n 次重试等待 `base_delay × 2^(n-1)` 秒。

```python
from utils.retry import retry_on_failure

@retry_on_failure(max_retries=5, base_delay=0.5, exceptions=(ConnectionError, TimeoutError))
def fetch_data():
    return requests.get("http://api.example.com/data")
```

---

#### 4.2.3 `trading_hours` — 交易时段判断

**源文件**: [utils/trading_hours.py](utils/trading_hours.py)

##### 模块级常量

| 常量 | 类型 | 值 | 说明 |
|------|------|------|------|
| `MORNING_START` | `datetime.time` | `time(9, 30)` | 早盘开盘 |
| `MORNING_END` | `datetime.time` | `time(11, 30)` | 早盘收盘 |
| `AFTERNOON_START` | `datetime.time` | `time(13, 0)` | 午盘开盘 |
| `AFTERNOON_END` | `datetime.time` | `time(15, 0)` | 午盘收盘 |
| `HOLIDAYS` | `set[str]` | `set()` | 节假日日期集合（`YYYYMMDD`） |

##### 函数

###### `is_weekend(dt: datetime) -> bool`

判断是否为周末（周六/周日）。

###### `is_holiday(dt: datetime) -> bool`

判断是否为节假日。需在 `HOLIDAYS` 中预先注册。

###### `is_trading_day(dt: datetime = None) -> bool`

判断是否为交易日。非周末且非节假日即为交易日。

###### `is_trading_time(dt: datetime = None) -> bool`

判断当前是否在交易时段内（9:30—11:30 或 13:00—15:00）。

###### `next_trading_seconds(dt: datetime = None) -> int`

计算距离下一个交易时段开始的秒数。若当前处于交易时段中则返回 0。

---

### 4.3 数据模块 `data/`

#### 4.3.1 `DataProvider` — XTquant 行情封装

**源文件**: [data/xt_provider.py](data/xt_provider.py)

封装 `xtdata` 模块的所有行情接口，隔离底层依赖。支持上下文管理器协议。

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

###### `get_kline(codes, period='1d', start_time='', end_time='', count=-1, dividend_type='back') -> pd.DataFrame`

获取已下载的 K 线数据。**必须先调用 `download_history()`**。

| 参数 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| `codes` | `list[str]` | — | 股票代码列表 |
| `period` | `str` | `'1d'` | 周期类型 |
| `start_time` | `str` | `''` | 起始日期 |
| `end_time` | `str` | `''` | 结束日期 |
| `count` | `int` | `-1` | 获取最近 N 根 K 线，`-1`=全部 |
| `dividend_type` | `str` | `'back'` | 复权方式：`'front'` / `'back'` / `'none'` |

| 返回 | 说明 |
|------|------|
| `pd.DataFrame` | index=日期，columns=`(字段, 代码)` 的 MultiIndex，字段：`open/high/low/close/volume/amount` |

###### `get_market_data(codes, period='1d', count=-1, dividend_type='front') -> pd.DataFrame`

获取实时/最新 K 线，**不需要提前下载**，直接从服务端拉取。

###### `get_stock_list() -> list[str]`

获取沪深 A 股全部股票代码列表。

###### `get_sector_list() -> list[str]`

获取所有板块名称列表。

###### `get_stock_list_in_sector(sector_name: str) -> list[str]`

获取指定板块的成分股。

###### `get_instrument_detail(code: str) -> dict`

获取合约基础信息。关键字段：`InstrumentName`（股票名称）、`OpenDate`（上市日期）。

###### `get_full_tick(codes: list[str]) -> pd.DataFrame`

获取全推 Tick 数据，包含五档买卖盘口。

###### `download_financial_data(codes: list[str]) -> None`

下载财务数据到本地缓存。

###### `get_financial_data(codes: list[str]) -> dict`

获取财务数据，返回 `{code: {table_name: DataFrame}}`。

###### `get_divid_factors(code: str) -> pd.DataFrame`

获取除权除息因子，用于复权价格计算。

###### `download_sector_data() -> None`

下载板块分类数据到本地缓存。

###### `is_connected() -> bool`

检查本对象连接追踪状态。

---

#### 4.3.2 `Database` — SQLite + Parquet 存储引擎

**源文件**: [data/database.py](data/database.py)

混合存储设计：SQLite 存元数据和索引，Parquet 存 K 线 OHLCV 数据。WAL 模式提升并发性能。非线程安全。

##### 构造器

```python
Database(db_path: str | Path = DB_PATH, data_dir: str | Path = KLINE_DIR, financial_dir: str | Path = FINANCIAL_DIR)
```

##### 连接管理

| 方法 | 说明 |
|------|------|
| `connect() -> None` | 打开 SQLite 连接，启用 WAL |
| `close() -> None` | 关闭连接，清除缓存 |
| `clear_cache() -> None` | 清除内部缓存（不关闭连接） |

##### 表结构初始化

`initialize() -> None` — 创建 7 张表（幂等）：

| 表名 | 用途 | 关键列 |
|------|------|--------|
| `stocks` | 股票基本信息 | `code`, `name`, `listing_date`, `status` |
| `sectors` | 板块分类 | `sector_name`, `stock_code` (联合主键) |
| `trade_records` | 交易记录 | `account_id`, `symbol`, `action`, `price`, `volume`, `amount`, `trade_time` |
| `kline_index` | K 线 Parquet 索引 | `code`, `period`, `file_path`, `start_date`, `end_date`, `row_count` |
| `financial_index` | 财务数据索引 | `code`, `file_path`, `report_count`, `latest_report` |
| `audit_log` | 审计日志 | `event_type`, `account_id`, `detail`, `created_at` |
| `backtest_history` | 回测历史 | `strategy_name`, `codes`, `performance`, `params` |

##### stocks 操作

| 方法 | 说明 |
|------|------|
| `upsert_stocks(records: list[dict]) -> None` | 批量写入/更新（每条含 `code`, `name`, `listing_date`, `status`） |
| `get_all_stocks() -> list[dict]` | 返回全部股票信息 |

##### sectors 操作

| 方法 | 说明 |
|------|------|
| `insert_sector_records(sector_name: str, stock_codes: list[str]) -> None` | 覆盖写入板块成分股 |
| `get_sector_stocks(sector_name: str) -> list[str]` | 查询板块成分股 |
| `get_all_sectors() -> list[str]` | 查询所有板块名称 |

##### trade_records 操作

| 方法 | 说明 |
|------|------|
| `insert_trade_record(record: dict) -> int` | 写入一条交易记录，返回自增 ID |
| `get_trade_records(account_id='', start_date='', end_date='') -> list[dict]` | 按条件查询，时间倒序 |

##### backtest_history 操作

| 方法 | 说明 |
|------|------|
| `insert_backtest_history(entry: dict) -> int` | 写入回测历史记录 |
| `get_backtest_history(limit: int = 20) -> list[dict]` | 获取最近 N 条回测记录 |

##### K 线 Parquet 操作

| 方法 | 说明 |
|------|------|
| `insert_daily_kline(records: list[dict], period='1d') -> int` | 写入 K 线（去重合并），更新索引 |
| `get_daily_kline_df(code, period='1d', start_date='', end_date='') -> pd.DataFrame` | 读取 K 线为 DataFrame |
| `get_daily_kline(code, start_date='', end_date='') -> list[dict]` | 读取 K 线为字典列表 |
| `get_latest_kline_date(code, period='1d') -> str \| None` | 查询最新日期 |
| `insert_minute_kline(records, period='1m') -> int` | 写入分钟 K 线 |
| `get_minute_kline(code, start_dt='', end_dt='') -> list[dict]` | 读取分钟 K 线 |

##### 财务数据

| 方法 | 说明 |
|------|------|
| `insert_financial(records: list[dict]) -> int` | 写入财务数据（Parquet） |
| `get_financial_df(code) -> pd.DataFrame` | 读取财务数据为 DataFrame |
| `get_financial(code) -> list[dict]` | 读取财务数据为字典列表 |

##### 除权因子

| 方法 | 说明 |
|------|------|
| `insert_divid_factors(code: str, df: pd.DataFrame) -> int` | 写入除权因子数据 |
| `get_divid_factors(code: str) -> pd.DataFrame` | 读取除权因子 |

##### 审计日志

| 方法 | 说明 |
|------|------|
| `log_audit(event_type: str, account_id: str = '', detail: str = '') -> int` | 写入审计日志，返回 ID |
| `get_audit_logs(limit: int = 100) -> list[dict]` | 获取最近 N 条审计日志 |

##### 统计

| 方法 | 说明 |
|------|------|
| `get_stats() -> dict` | 返回 `{stocks, sectors, trades, kline_files, kline_rows}` |
| `get_stock_klines_summary() -> list[dict]` | 每只股票的 K 线数据概况 |

---

#### 4.3.3 `Downloader` — 数据下载器

**源文件**: [data/downloader.py](data/downloader.py)

##### 构造器

```python
Downloader(provider: DataProvider | None = None, database: Database | None = None, max_workers: int = 6)
```

| 参数 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| `provider` | `DataProvider \| None` | `None` | 行情提供者 |
| `database` | `Database \| None` | `None` | 数据库对象 |
| `max_workers` | `int` | `6` | 并行下载线程数 |

##### 方法

###### `download_all_a_stocks(period='1d', start_time='', end_time='') -> int`

全量下载 A 股 K 线。内置预检索优化：跳过 SQLite 已覆盖的股票。支持多线程并行。

###### `download_stock_info() -> int`

下载股票基本信息，仅处理 SQLite 中不存在的股票。

###### `download_sector_data() -> None`

下载板块分类数据并写入 `sectors` 表。

###### `incremental_update(period='1d', days=5) -> int`

增量更新 K 线。跳过最新日期已覆盖今天的股票。

###### `download_all_financial() -> int`

下载全量财务数据并入库。

###### `close() -> None`

释放数据库连接（仅关闭内部创建的连接）。

---

#### 4.3.4 `XTQuantDataFeed` — backtrader 数据源适配器

**源文件**: [data/backtrader_feeder.py](data/backtrader_feeder.py)

##### 类 `XTQuantDataFeed(bt.feeds.PandasData)`

将 DataFrame 注入回测引擎。列映射：

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

##### `load_bt_data(df: pd.DataFrame, dtformat: str = '%Y%m%d') -> bt.feeds.PandasData | None`

将 K 线 DataFrame 转换为 backtrader 数据源。自动将 `date` 列转为 `datetime` 索引。

| 异常 | 条件 |
|------|------|
| `ValueError` | DataFrame 缺少必要列 |

##### `load_multi_stock_data(db, codes, start_date='', end_date='', period='1d') -> dict[str, bt.feeds.PandasData]`

批量加载多只股票数据源，跳过无数据股票并打印警告。

---

#### 4.3.5 `qlib_converter` — qlib 格式转换

**源文件**: [data/qlib_converter.py](data/qlib_converter.py)

使用 `utils.logging.get_logger` 获取专用日志器。

##### `convert_kline_to_qlib_format(parquet_dir=None, output_dir=None, period='1d') -> int`

将 Parquet K 线转换为 qlib 二进制格式。

输出结构：
```
data/qlib_data_cn/
├── calendars/day.txt           # 交易日历
├── instruments/all.txt         # 股票列表（code\tstart\tend）
└── features/<code>/
    ├── open.1d.bin, high.1d.bin, low.1d.bin, close.1d.bin, volume.1d.bin, amount.1d.bin
```

二进制格式：每条记录 `int32(日期) + float32(值)`，小端序。返回成功转换的股票数。

##### `validate_qlib_data(qlib_dir=None) -> dict`

验证 qlib 数据完整性。

| 返回字段 | 说明 |
|----------|------|
| `calendars` | 交易日总数 |
| `instruments` | 股票总数 |
| `features` | 有特征目录的股票数 |
| `errors` | 抽样发现的缺失文件列表 |

---

#### 4.3.6 `DataValidator` — 数据健康检查

**源文件**: [data/data_validator.py](data/data_validator.py)

对 K 线数据进行多维度质量验证，确保数据正确可用于回测和策略。基于 XTquant 官方数据健康检查建议实现。

##### 构造器

```python
DataValidator(price_jump_threshold: float = 0.11)
```

| 参数 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| `price_jump_threshold` | `float` | `0.11` | 日涨跌幅异常检测阈值（A 股主板 10%，创业板/科创板 20%，留 1% 容差） |

##### 类常量

`REQUIRED_COLUMNS = {'open', 'high', 'low', 'close', 'volume'}` — K 线必需字段集合。

##### 方法

###### `validate_kline(df: pd.DataFrame, code: str = '') -> dict`

对单只股票 K 线 DataFrame 执行全面健康检查。

**检查维度**：

1. **必需列**：是否缺少 OHLCV 任一列
2. **空值**：各列空值计数（收盘价空值单独统计）
3. **价格跳变**：逐日涨跌幅超过 `price_jump_threshold` 视为异常
4. **价格合理性**：是否存在 `high < low` 的记录

| 返回字段 | 类型 | 说明 |
|----------|------|------|
| `passed` | `bool` | 是否通过所有检查 |
| `code` | `str` | 股票代码 |
| `row_count` | `int` | 总行数 |
| `missing_count` | `int` | 缺失值计数 |
| `null_close_count` | `int` | 收盘价空值数 |
| `jump_count` | `int` | 异常跳变次数 |
| `issues` | `list[str]` | 问题描述列表 |
| `checks_passed` | `bool` | 列完整且无跳变 |

###### `validate_parquet_file(file_path: str) -> dict`

验证单个 Parquet K 线文件，返回格式同 `validate_kline`。文件读取失败时返回 `passed=False` 的结果。

###### `validate_all(kline_dir: str, period: str = '1d', max_files: int = 0) -> dict`

批量验证 K 线目录下所有 Parquet 文件。

| 参数 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| `kline_dir` | `str` | — | Parquet K 线根目录 |
| `period` | `str` | `'1d'` | 周期，实际扫描 `<kline_dir>/<period>/` |
| `max_files` | `int` | `0` | 最大检查文件数，`0`=全部 |

返回 `{total, passed, failed, issues_summary}`，目录不存在时额外返回 `error` 字段。

---

### 4.4 策略模块 `strategy/`

#### 4.4.1 `Signal` — 交易信号数据类

**源文件**: [strategy/base.py](strategy/base.py)

```python
@dataclass
class Signal:
    action: str     # "BUY" / "SELL" / "HOLD"
    symbol: str     # 股票代码，如 "000001.SZ"
    price: float    # 目标价格
    volume: int     # 目标数量（股）
```

信号由策略 `on_bar()` 产生，由 `StrategyExecutor` 统一执行。

#### 4.4.2 `BaseStrategy` — 策略抽象基类

**源文件**: [strategy/base.py](strategy/base.py)

```python
class BaseStrategy:
    name: str = ""           # 策略唯一标识
    params: dict = {}        # 默认参数字典

    def init(self, context: dict) -> None: ...
    def on_bar(self, index: int) -> list[Signal]: ...
    def get_params_info(self) -> dict: ...
```

**生命周期**：

1. 实例化 → 2. `init(context)` 接收 `{'kline': DataFrame}` → 3. 逐 K 线调用 `on_bar(index)` 返回信号

子类必须覆盖全部三个方法。完整使用示例：

```python
from strategy.base import BaseStrategy, Signal

class MACrossStrategy(BaseStrategy):
    name = "ma_cross"
    params = {"fast": 5, "slow": 20}

    def init(self, context):
        df = context['kline']
        self.ma_fast = df['close'].rolling(self.params['fast']).mean()
        self.ma_slow = df['close'].rolling(self.params['slow']).mean()

    def on_bar(self, index):
        if index < self.params['slow']:
            return []
        # 金叉买入
        if (self.ma_fast.iloc[index] > self.ma_slow.iloc[index] and
            self.ma_fast.iloc[index-1] <= self.ma_slow.iloc[index-1]):
            price = self.context['kline']['close'].iloc[index]
            return [Signal("BUY", "", price, 100)]
        # 死叉卖出
        if (self.ma_fast.iloc[index] < self.ma_slow.iloc[index] and
            self.ma_fast.iloc[index-1] >= self.ma_slow.iloc[index-1]):
            price = self.context['kline']['close'].iloc[index]
            return [Signal("SELL", "", price, 100)]
        return []

    def get_params_info(self):
        return {"fast": "短期均线周期", "slow": "长期均线周期"}
```

#### 4.4.3 `strategy.registry` — 统一策略注册中心

**源文件**: [strategy/registry.py](strategy/registry.py)

集中管理所有策略（回测和实盘）的注册与查询。

##### 模块级变量

`REGISTRY: dict[str, dict[str, type]]` — 双层命名空间字典：

```python
REGISTRY = {
    "bt":   {"ma_cross": MACrossStrategy, "macd": MACDStrategy, ...},  # backtrader 策略
    "live": {"ma_cross": MyLiveStrategy, ...}                           # 实盘策略
}
```

##### `register_strategy(namespace: str = "live") -> Callable`

装饰器工厂。将策略类注册到指定命名空间。

```python
from strategy.registry import register_strategy

@register_strategy("live")
class MyLiveStrategy(BaseStrategy):
    name = "my_strategy"
    ...
```

算法：装饰器将策略类的 `name` 属性作为键注册到 `REGISTRY[namespace]` 中。

##### `get_strategy(namespace: str, name: str) -> type`

从注册中心获取策略类。

| 异常 | 条件 |
|------|------|
| `ValueError` | 命名空间或策略名不存在 |

##### `list_strategies(namespace: str = "") -> dict[str, type]`

列出已注册策略。`namespace=""` 时返回所有命名空间的合并结果。

##### `register_builtin_bt_strategies() -> None`

自动注册 `backtest/bt_strategy.py` 中的 6 个内置 backtrader 策略到 `REGISTRY["bt"]`。

#### 4.4.4 `FactorHandler` — qlib 因子处理器

**源文件**: [strategy/alpha_factors.py](strategy/alpha_factors.py)

##### 因子元信息 `FACTOR_META`（22 个因子）

| 因子名 | 分类 | 说明 |
|--------|------|------|
| `ret_1d`, `ret_5d`, `ret_10d`, `ret_20d`, `ret_60d` | 动量 | 各周期收益率 |
| `std_5d`, `std_20d` | 波动率 | 收益率标准差 |
| `hl_amplitude_20d` | 波动率 | 20 日平均振幅 |
| `vol_ratio_5_20`, `vol_ratio_5_60` | 量价 | 量比 |
| `volume_trend_10d` | 量价 | 10 日量能趋势 |
| `ma5_dev`, `ma10_dev`, `ma20_dev`, `ma60_dev` | 均线偏离 | 收盘价/MA - 1 |
| `rsi_14` | 技术指标 | 14 日 RSI |
| `macd_dif`, `macd_signal`, `macd_hist` | 技术指标 | MACD 三线 |
| `bb_position` | 技术指标 | 布林带位置 (0~1) |
| `reversal_3d` | 反转 | 3 日反转 |
| `turnover_5d` | 流动性 | 5 日平均换手率（近似） |

##### 构造器

```python
FactorHandler(instruments: str = 'all', start_time: str = '', end_time: str = '')
```

##### 方法

###### `load_factors(use_qlib: bool = True) -> pd.DataFrame`

加载并计算因子。`use_qlib=True` 时优先 qlib DataHandler，失败自动回退 pandas。返回 MultiIndex `(datetime, instrument)` × 因子名 的 DataFrame。

###### `get_factor_names() -> list[str]`

获取当前使用的因子名称列表。

###### `get_factor_meta() -> dict`

返回 `FACTOR_META` 字典。

##### 静态方法

| 方法 | 说明 |
|------|------|
| `_calc_rsi(close: pd.Series, period: int = 14) -> pd.Series` | 计算 RSI（指数移动平均法） |
| `_calc_macd(close: pd.Series, fast: int = 12, slow: int = 26, signal: int = 9) -> tuple` | 计算 MACD，返回 `(dif, dea, hist)` |
| `_calc_bb_position(close: pd.Series, period: int = 20, num_std: float = 2.0) -> pd.Series` | 计算布林带位置 (0~1) |

##### qlib 模式表达式语法

| 表达式 | 含义 |
|--------|------|
| `$close` / `$open` / `$high` / `$low` / `$volume` | 行情字段 |
| `Ref($close, n)` | n 期前收盘价 |
| `Mean(x, n)` | n 期均值 |
| `Std(x, n)` | n 期标准差 |
| `Corr(x, y, n)` | n 期相关系数 |
| `Rank(x)` | 截面排名 |
| `RSI($close, 14)` | 14 日 RSI |

#### 4.4.5 `QlibTrainer` — 模型训练器

**源文件**: [strategy/qlib_model.py](strategy/qlib_model.py)

##### 构造器

```python
QlibTrainer(model_type: str = 'LightGBM')
```

##### 方法

###### `train(handler: FactorHandler, target_col: str = 'ret_5d') -> dict`

训练模型。

**算法流程**：

1. 获取 handler 已计算的因子 DataFrame
2. 尝试 `_train_with_qlib()`：使用 qlib 原生 `LGBModel` + `DatasetH`，超参：`num_leaves=64, max_depth=6, lr=0.05, n_estimators=500, early_stopping=50`
3. 失败时回退 `_train_sklearn()`：使用 `lightgbm.LGBMRegressor`，时间序列 7:1.5:1.5 切分，超参：`n_estimators=300, max_depth=6, num_leaves=31`

| 异常 | 条件 |
|------|------|
| `ImportError` | qlib / lightgbm 未安装 |
| 返回 `{"error": ...}` | 因子数据为空 |

返回：`{status, model_type, features, feature_importance, best_iteration}`。

###### `predict(handler: FactorHandler) -> pd.Series`

生成预测分数。必须先调用 `train()` 或 `load()`。

| 异常 | 条件 |
|------|------|
| `RuntimeError` | 模型未训练 |
| `ValueError` | 因子数据为空 |

###### `save(path: str) -> None`

保存模型到 pickle 文件（含模型对象、类型、特征重要性）。

###### `load(path: str) -> None`

从 pickle 文件加载模型。

###### `get_feature_importance() -> pd.DataFrame | None`

获取特征重要性表（列：`feature`, `importance`），降序排列。

#### 4.4.6 `SignalGenerator` — 信号生成器

**源文件**: [strategy/signal_generator.py](strategy/signal_generator.py)

##### 构造器

```python
SignalGenerator()
```

##### 方法

###### `generate(predictions: pd.Series, top_k: int = 20, min_score: float | None = None, blacklist: list[str] | None = None) -> pd.DataFrame`

按预测分数降序选取 Top-K 股票。返回 DataFrame（列：`date`, `code`, `score`, `rank`）。

**边缘情况处理**：

- `predictions` 为空或 `None` → 返回空 DataFrame
- `predictions` 为 DataFrame → 自动取第一列
- MultiIndex 索引 → 按日期分组处理
- `min_score` 过滤 → 仅保留分数 ≥ 阈值的股票
- `blacklist` 过滤 → 排除黑名单中的代码

###### `generate_with_risk_control(predictions, positions, top_k=20, max_turnover=0.5) -> dict[str, str]`

生成带换手率限制的调仓指令。返回 `{code: "BUY" | "SELL" | "HOLD"}`。

###### `filter_by_sector(stock_list, sector_name, database) -> list[str]`

按板块过滤股票列表。`sector_name="all"` 时不过滤。

###### `get_latest_signals() -> pd.DataFrame`

获取缓存的最新选股信号。

---

### 4.5 回测模块 `backtest/`

#### 4.5.1 内置策略类

**源文件**: [backtest/bt_strategy.py](backtest/bt_strategy.py)

所有策略继承 `bt.Strategy`。`STRATEGY_REGISTRY` 指向 `_REGISTRY["bt"]`，由 `register_builtin_bt_strategies()` 自动注册。

| 键名 | 类名 | 策略描述 | 关键参数 |
|------|------|----------|----------|
| `ma_cross` | `MACrossStrategy` | 快慢均线金叉/死叉 | `fast=5`, `slow=20` |
| `macd` | `MACDStrategy` | MACD DIF/DEA 交叉 | `fast=12`, `slow=26`, `signal=9` |
| `rsi` | `RSIStrategy` | RSI 超买超卖 | `period=14`, `oversold=30`, `overbought=70` |
| `bollinger_bands` | `BollingerBandsStrategy` | 布林带下轨买/上轨卖 | `period=20`, `devfactor=2.0` |
| `turtle` | `TurtleStrategy` | 唐奇安通道突破 | `entry_period=20`, `exit_period=10`, `atr_period=20` |
| `qlib_signal` | `QlibSignalStrategy` | qlib 模型 Top-K 选股调仓 | `signals`, `codes`, `top_k=20`, `rebalance_freq=20` |

`QlibSignalStrategy` 逻辑：每 `rebalance_freq` 根 K 线触发调仓 → 卖出不在目标池的持仓（遵守 T+1）→ 等权买入目标股票（整百股）。额外方法：

- `set_signals(signals: dict)` — 设置预生成信号 `{date: [codes]}`
- `set_codes(codes: list[str])` — 设置股票池

##### `get_strategy(name: str) -> type`

从注册表获取策略类。

| 异常 | 条件 |
|------|------|
| `ValueError` | 名称未注册 |

#### 4.5.2 `BacktestRunner` — 回测执行器

**源文件**: [backtest/runner.py](backtest/runner.py)

##### 构造器

```python
BacktestRunner(initial_capital: float = 100000, commission_rate: float = 0.00025)
```

自动配置 `AShareCommission` 佣金方案、**0.01% 比例滑点**（`set_slippage_perc(perc=0.0001)`，模拟成交价劣化、避免回测过于乐观），以及 7 个 Analyzer：

| Analyzer | `_name` | 用途 |
|----------|---------|------|
| `TimeReturn` | `timereturn` | 每日收益率序列 → `BacktestAnalyzer` 数据源 |
| `Transactions` | `transactions` | 逐笔成交 → 胜率/盈亏比/交易明细 |
| `TradeAnalyzer` | `trades` | 交易统计（交叉核对） |
| `SharpeRatio` | `sharpe` | 夏普比率（`riskfreerate=0.02`, 年化） |
| `DrawDown` | `drawdown` | 回撤 |
| `Returns` | `returns` | 收益率 |
| `VWR` | `vwr` | 波动率加权收益率 |

> `TimeReturn` 与 `Transactions` 是 `BacktestAnalyzer` 的数据来源，必须挂载；其余为内置指标便于交叉核对。

##### 方法

###### `load_data_from_db(codes, start_date='', end_date='', period='1d') -> int`

从本地 SQLite 加载 K 线到 Cerebro。返回成功加载的股票数。

###### `load_data_from_df(kline_dict: dict[str, pd.DataFrame]) -> int`

从 DataFrame 字典直接加载，无需 SQLite。

###### `set_strategy(strategy_cls_or_name: str | type, **params)`

设置回测策略。接受策略名称字符串或类引用。

###### `run() -> dict`

执行回测。返回 `{performance, initial_capital, final_value, total_return_pct, timestamp}`。

###### `run_qlib_signal(codes, signals, start_date='', end_date='', top_k=20, rebalance_freq=20, period='1d') -> dict`

直接使用 qlib 选股信号执行回测。

| 参数 | 类型 | 说明 |
|------|------|------|
| `codes` | `list[str]` | 待回测股票池 |
| `signals` | `dict[str, list[str]]` | 预生成选股信号 `{date: [codes]}` |
| `start_date` | `str` | 起始日期 |
| `end_date` | `str` | 结束日期 |
| `top_k` | `int` | 持仓数量 |
| `rebalance_freq` | `int` | 调仓频率 |
| `period` | `str` | K 线周期 |

内部流程：加载数据 → 创建 `QlibSignalStrategy` 实例 → 注入信号和股票池 → 运行。

###### `run_quick(codes, strategy_name, start_date='', end_date='', **params) -> dict`

一键回测。便捷封装：加载数据 → 设置策略 → 执行。

```python
runner = BacktestRunner(initial_capital=100000)
result = runner.run_quick(
    codes=["000001.SZ", "600519.SH"],
    strategy_name="ma_cross",
    start_date="20230101", end_date="20231231",
    fast=5, slow=20
)
print(f"收益率: {result['total_return_pct']}%")
```

#### 4.5.3 `BacktestAnalyzer` — 绩效分析器

**源文件**: [backtest/bt_analyzer.py](backtest/bt_analyzer.py)

使用 `utils.logging.get_logger` 获取专用日志器。

##### 构造器

```python
BacktestAnalyzer()
```

##### 方法

###### `analyze(strat, initial_capital: float = 100000) -> dict`

从策略实例中提取所有绩效指标。

| 参数 | 类型 | 说明 |
|------|------|------|
| `strat` | `bt.Strategy` | **已执行**的策略实例（而非 Cerebro） |

| 返回字段 | 类型 | 说明 |
|----------|------|------|
| `total_return` | `float` | 总收益率（小数） |
| `annual_return` | `float` | 年化收益率 |
| `max_drawdown` | `float` | 最大回撤（小数） |
| `sharpe_ratio` | `float` | 年化夏普比率 |
| `win_rate` | `float` | 胜率 |
| `profit_loss_ratio` | `float` | 盈亏比 |
| `total_trades` | `int` | 总交易次数 |
| `trading_days` | `int` | 交易天数 |
| `final_value` | `float` | 最终资产 |
| `equity_curve` | `dict` | 净值曲线 |
| `drawdown_curve` | `dict` | 回撤曲线 |
| `trade_records` | `list[dict]` | 交易记录 |

**数据来源约定（重要）**：

`analyze()` **不再自行执行 `cerebro.run()`**，而是消费调用方已运行得到的 backtrader Strategy 实例，从其挂载的 analyzer 中提取数据：

| Analyzer | 用途 |
|----------|------|
| `bt.analyzers.TimeReturn` | 每日收益率序列 → 净值曲线、夏普、回撤 |
| `bt.analyzers.Transactions` | 逐笔成交记录 → 胜率、盈亏比、交易明细 |

`BacktestRunner` 已统一挂载这两个 analyzer。若 `strat` 上未挂载，`analyze()` 会回退到 `broker.getvalue()`，但 `trading_days` / 交易统计将不可靠，并在日志中给出警告。

**指标算法说明**：

- **年化收益率**: `(1 + total_return)^(252/trading_days) - 1`
- **最大回撤**: 基于净值序列，记录最高点计算最大回撤比例
- **夏普比率**: `(日均收益 - 0.02/252) / 日收益标准差 × √252`（无风险利率 2%）
- **胜率/盈亏比**: 按 `Transactions` 的逐笔 `pnl` 正负分组统计

###### `generate_report(result: dict, output_path: str = '') -> str`

生成 HTML 绩效报告（依赖 quantstats）。不可用时回退纯文本。

###### `format_report(result: dict) -> str`

格式化打印绩效摘要。

#### 4.5.4 `AShareCommission` / `AShareSizer` — A 股规则

**源文件**: [backtest/bt_broker.py](backtest/bt_broker.py)

##### `AShareCommission(bt.CommInfoBase)`

| 参数 | 默认值 | 说明 |
|------|--------|------|
| `commission` | `0.00025` | 佣金费率（万 2.5） |
| `stamp_duty` | `0.001` | 印花税率（千 1，仅卖出） |
| `transfer_fee` | `0.00001` | 过户费（万 0.1） |
| `min_commission` | `5.0` | 最低佣金（元） |

手续费 = `max(金额 × commission, min_commission) + (卖出时) 金额 × stamp_duty + 金额 × transfer_fee`

##### `AShareSizer(bt.Sizer)`

| 参数 | 默认值 | 说明 |
|------|--------|------|
| `perc` | `0.1` | 每笔交易投入的资金比例 |

自动调整为 100 的整数倍。

---

### 4.6 交易模块 `trading/`

#### 4.6.1 `AccountConfig` — 账号配置

**源文件**: [trading/xt_trader.py](trading/xt_trader.py)

```python
@dataclass
class AccountConfig:
    id: str                # 账号唯一标识，如 "real"
    label: str             # 显示标签，如 "实盘"
    miniqmt_path: str      # QMT userdata_mini 目录路径
    account_id: str        # 资金账号
    account_type: str = "STOCK"
```

#### 4.6.2 `TraderManager` — 实盘交易管理器

**源文件**: [trading/xt_trader.py](trading/xt_trader.py)

封装 XTquant 实盘交易接口。使用 `utils.logging.get_logger` 统一日志。

> **安全警告**: 所有下单通过 `TraderManager` 直接发送至券商交易柜台，涉及真实资金。

##### 构造器

```python
TraderManager()
```

##### 方法

###### `connect_all(accounts: list[dict] = None) -> dict[str, bool]`

连接所有配置的账号。使用 `retry_on_failure` 装饰器自动重试。

每个账号独立创建 `XtQuantTrader` 实例和回调处理。回调事件：`on_disconnected`, `on_stock_order`, `on_stock_trade`, `on_account_status`。

返回 `{账号ID: 连接是否成功}`。

###### `buy(account_id, code, price, volume, strategy_name='', remark='') -> bool`

限价买入。`strategy_name` 和 `remark` 用于订单备注追踪。

###### `sell(account_id, code, price, volume, strategy_name='', remark='') -> bool`

限价卖出。

###### `cancel_order(account_id: str, order_id: int) -> bool`

撤单。

###### `query_positions(account_id: str) -> list[dict]`

查询持仓。每条含 `stock_code`, `volume`, `can_use_volume`, `open_price`, `market_value`。

###### `query_orders(account_id: str) -> list[dict]`

查询当日委托。每条含 `order_id`, `stock_code`, `order_volume`, `traded_volume`, `price`, `status`。

###### `query_trades(account_id: str) -> list[dict]`

查询当日成交。每条含 `order_id`, `stock_code`, `traded_volume`, `traded_price`, `traded_time`。

###### `query_asset(account_id: str) -> dict | None`

查询账户资产。返回 `{account_id, total_asset, available_cash, market_value}`。

###### `is_connected(account_id: str) -> bool`

检查指定账号连接状态。

###### `get_connected_accounts() -> list[str]`

获取已连接账号 ID 列表。

###### `disconnect_all() -> None`

断开所有连接并清理资源。

#### 4.6.3 `StrategyExecutor` — 策略执行器

**源文件**: [trading/executor.py](trading/executor.py)

提供 **行情获取 → 策略运算 → 风险管理 → 交易执行 → 记录保存** 完整流水线。使用 `_EXEC_LOCK` 线程锁保护 `run_once()`。

##### 构造器

```python
StrategyExecutor(account_id: str, strategy_cls: type[BaseStrategy],
                trader_manager: TraderManager,
                risk_manager: RiskManager | None = None,
                provider: DataProvider | None = None,
                database: Database | None = None)
```

| 新增参数 | 说明 |
|----------|------|
| `risk_manager` | 可注入外部风控实例，不传则内部创建 |

##### 方法

###### `set_stock_list(codes: list[str]) -> None`

设置执行的股票池。

###### `run_once() -> list[dict]`

运行一次完整执行流程（线程安全）。逐股票：下载 K 线 → 运行策略 → 风控检查 → 下单 → 记录审计日志。返回已执行信号列表。

###### `run_loop(interval_seconds: int = 60) -> None`

启动 daemon 线程定时循环执行。首次立即执行。

###### `stop() -> None`

停止循环，等待线程退出（最多 5 秒），清理数据库连接。

---

### 4.7 风控模块 `risk/`

#### 4.7.1 `RiskManager` — 风险管理器

**源文件**: [risk/risk_manager.py](risk/risk_manager.py)

##### 模块级函数 `get_limit_ratio(code: str) -> float`

根据股票代码前缀判断涨跌停比例：

| 代码前缀 | 涨跌停比例 | 板块 |
|----------|-----------|------|
| `'3'` | `0.20` | 创业板 |
| `'688'` | `0.20` | 科创板 |
| `'8'` 或 `'4'` | `0.30` | 北交所 |
| 其他 | `0.10` | 主板 |

##### 构造器

```python
RiskManager(config: dict = None)
```

##### 方法

###### `reset_daily(equity: float, date: str = '') -> None`

每日重置风险计数器（`daily_pnl`, `daily_trade_count`, 熔断状态）。

###### `check_buy(code, price, volume, cash, positions, prev_close=0) -> tuple[bool, str]`

买入前多维检查：熔断状态 → 涨停过滤（按板块） → 单笔金额占比 → 资金充足性 → 单只持仓上限 → 总持仓数量上限。

###### `check_sell(code, volume, positions, prev_close=0, buy_date='', current_date='') -> tuple[bool, str]`

卖出前检查：熔断 → 跌停过滤（按板块） → 持仓充足性 → T+1 限制。

###### `check_market(price, prev_close, is_buy=True, code='') -> tuple[bool, str]`

涨跌停市场规则检查。`code` 用于按板块确定涨跌停比例。

###### `update_daily_pnl(trade_pnl: float) -> None`

更新当日累计盈亏。

###### `check_daily_loss(current_equity: float) -> tuple[bool, str]`

检查日亏损熔断：`(start_equity - current_equity) / start_equity ≥ max_daily_loss_ratio`

###### `check_drawdown(peak_equity, current_equity) -> tuple[bool, str]`

检查回撤熔断：`(peak - current) / peak ≥ max_drawdown_ratio`

###### `is_meltdown() -> bool` / `reset_meltdown() -> None` / `get_risk_summary() -> dict`

状态查询与控制。

**熔断机制流程**：
```
交易日开始 → reset_daily(equity)
     ↓
每笔交易前 → check_buy() / check_sell()
     ↓
定时检查 → check_daily_loss() / check_drawdown()
     ↓
熔断触发 → 当日停止所有交易
     ↓
次日 → reset_daily() 自动复位（或手动 reset_meltdown()）
```

---

### 4.8 Web API 路由

所有 API 返回 `{"status": "ok", "data": ...}` 或 `{"status": "error", "message": ...}`。

#### 4.8.1 鉴权中间件

**源文件**: [web/app.py](web/app.py)

##### `api_key_middleware` (HTTP 中间件)

通过 `X-API-Key` 请求头进行鉴权。

**鉴权规则**（判定顺序）：

| 路由类型 | 要求 |
|----------|------|
| `_AUTH_REQUIRED_PREFIXES` 前缀（`/api/monitor`、`/api/risk`） | **一律鉴权**（含 GET） |
| 所有 `POST` / `PUT` / `DELETE` | **一律鉴权** |
| `_READONLY_WHITELIST` 中的 GET 路径 | **无需鉴权**（如 `/api/data/kline`, `/api/data/stocks`, `/api/backtest/strategies`, `/api/backtest/history` 等） |
| 其他非白名单 GET | **也鉴权**（保守策略，未知端点默认不放行） |

鉴权失败返回 **`401 Unauthorized`**（响应体 `{"status": "error", "message": "未授权访问，请提供有效的 X-API-Key"}`）。

默认 Key: `quant-local-dev`，通过环境变量 `WEB_API_KEY` 覆盖。

#### 4.8.2 数据路由 `/api/data`

**源文件**: [web/routes/data_routes.py](web/routes/data_routes.py)

| 方法 | 路径 | 说明 | 参数 |
|------|------|------|------|
| `GET` | `/api/data/kline` | 查询 K 线 | `code`, `period="1d"`, `start`, `end` |
| `GET` | `/api/data/stocks` | 股票列表 | — |
| `GET` | `/api/data/sectors` | 板块列表 | — |
| `GET` | `/api/data/sector_stocks` | 板块成分股 | `sector_name` |
| `GET` | `/api/data/db-status` | 数据库统计 | — |
| `GET` | `/api/data/stock-klines` | K 线概况 | — |
| `GET` | `/api/data/financial` | 财务数据 | `code` |
| `POST` | `/api/data/stocks/sync` | 同步股票信息 | — |
| `POST` | `/api/data/sectors/sync` | 同步板块数据 | — |
| `POST` | `/api/data/kline/download` | 下载全量 K 线 | body: `{period}` |
| `POST` | `/api/data/kline/update` | 增量更新 K 线 | body: `{period}` |
| `POST` | `/api/data/financial/download` | 下载全量财务 | — |
| `POST` | `/api/data/financial/download-single` | 下载单只财务 | body: `{code}` |

#### 4.8.3 策略路由 `/api/strategy`

**源文件**: [web/routes/strategy_routes.py](web/routes/strategy_routes.py)

##### Pydantic 模型

**`TrainRequest`**：`instruments="all"`, `start_time=""`, `end_time=""`, `model_type="LightGBM"`, `top_k=20`

**`PredictRequest`**：`instruments="all"`, `start_time=""`, `end_time=""`, `model_path=""`, `top_k=20`, `min_score=None`

##### 路由

| 方法 | 路径 | 说明 |
|------|------|------|
| `GET` | `/api/strategy/list` | 可用策略列表 |
| `GET` | `/api/strategy/factors` | 因子元信息（含分类） |
| `POST` | `/api/strategy/train` | 训练模型 |
| `POST` | `/api/strategy/predict` | 生成选股预测 |
| `GET` | `/api/strategy/signals` | 缓存的最新选股信号 |
| `GET` | `/api/strategy/importance` | 特征重要性（提示接口） |

#### 4.8.4 回测路由 `/api/backtest`

**源文件**: [web/routes/backtest_routes.py](web/routes/backtest_routes.py)

回测历史优先写入 `Database.backtest_history`，数据库不可用时回退到内存缓存。

##### Pydantic 模型

**`BacktestRequest`**：`strategy_name="ma_cross"`, `stock_codes=["000001.SZ"]`, `start_date=""`, `end_date=""`, `initial_capital=100000`, `params={}`

**`QuickBacktestRequest`**：`strategy_name="ma_cross"`, `stock_codes=["000001.SZ"]`, `start_date="20230101"`, `end_date="20231231"`, `initial_capital=100000`, `fast=5`, `slow=20`

##### 路由

| 方法 | 路径 | 说明 |
|------|------|------|
| `GET` | `/api/backtest/strategies` | 可用策略及参数 |
| `POST` | `/api/backtest/run` | 执行回测（完整参数） |
| `POST` | `/api/backtest/run_quick` | 快速回测（简化参数） |
| `GET` | `/api/backtest/history` | 回测历史（最近 20 条） |
| `POST` | `/api/backtest/compare` | 多策略对比回测 |

对比回测请求体：`{stock_codes, strategies, start_date, end_date, initial_capital}`，返回按收益率降序排列的结果。

#### 4.8.5 监控路由 `/api/monitor`

**源文件**: [web/routes/monitor_routes.py](web/routes/monitor_routes.py)

> 此路由组一律需要 API Key 鉴权。

| 方法 | 路径 | 说明 | 参数 |
|------|------|------|------|
| `GET` | `/api/monitor/positions` | 持仓查询 | `account_id="real"` |
| `GET` | `/api/monitor/orders` | 当日委托 | `account_id="real"` |
| `GET` | `/api/monitor/trades` | 当日成交 | `account_id="real"` |
| `GET` | `/api/monitor/asset` | 账户资产 | `account_id="real"` |
| `GET` | `/api/monitor/accounts` | 账号连接状态 | — |
| `GET` | `/api/monitor/records` | 本地交易记录 | `account_id`, `start`, `end` |
| `GET` | `/api/monitor/dashboard` | 仪表盘摘要 | `account_id="real"` |

#### 4.8.6 风控路由 `/api/risk`

**源文件**: [web/routes/risk_routes.py](web/routes/risk_routes.py)

> 此路由组一律需要 API Key 鉴权。

| 方法 | 路径 | 说明 |
|------|------|------|
| `GET` | `/api/risk/status` | 当前风险状态 |
| `GET` | `/api/risk/config` | 风控参数配置 |
| `POST` | `/api/risk/config` | 更新风控参数（动态调整） |
| `POST` | `/api/risk/reset` | 重置熔断状态 |
| `POST` | `/api/risk/check_order` | 模拟订单风险检查 |

##### `POST /api/risk/config` 请求体

任意 `RISK_CONFIG` 中的键值对，如 `{"max_daily_loss_ratio": 0.03}`。仅更新传入的字段。

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

---

## 5. 配置参考

### `config/settings.py`

```python
# ── 路径 ──
BASE_DIR        = Path(__file__).resolve().parent.parent
DB_PATH         = BASE_DIR / "quant.db"
KLINE_DIR       = BASE_DIR / "data" / "kline"
FINANCIAL_DIR   = BASE_DIR / "data" / "financial"
QLIB_DATA_DIR   = BASE_DIR / "data" / "qlib_data_cn"
XT_DATA_DIR     = BASE_DIR / "xtdata"

# ── 服务 ──
XT_PORT      = 58610
WEB_HOST     = "127.0.0.1"
WEB_PORT     = 8000
WEB_API_KEY  = os.environ.get("WEB_API_KEY", "quant-local-dev")

# ── 账号 ──
ACCOUNTS_YAML    = BASE_DIR / "config" / "accounts.yaml"
RISK_CONFIG_PATH = BASE_DIR / "config" / "risk.yaml"
# ACCOUNTS 从 accounts.yaml 加载，失败使用默认配置

# ── 风控 ──
RISK_CONFIG = {
    "max_position_per_stock": 100000,
    "max_single_order_ratio": 0.20,
    "max_daily_loss_ratio": 0.05,
    "max_drawdown_ratio": 0.20,
    "max_holdings_count": 50,
}

# ── 日志 ──
LOG_CONFIG = {
    "level": "INFO",
    "file": "logs/quant.log",
    "max_bytes": 10 * 1024 * 1024,
    "backup_count": 5,
}
```

### `config/accounts.yaml`

```yaml
accounts:
  - id: "real"
    label: "实盘"
    miniqmt_path: "E:\\券商QMT交易端\\userdata_mini"
    account_id: "你的资金账号"
    account_type: "STOCK"
```

### `config/risk.yaml`（可选）

```yaml
max_daily_loss_ratio: 0.03
max_drawdown_ratio: 0.15
```

> 此文件不存在时使用 `RISK_CONFIG` 默认值。存在时逐键覆盖。

---

## 6. 命令行工具

```powershell
# 下载全量 A 股数据
python scripts/download_data.py
python scripts/download_data.py --stocks-only        # 仅股票信息
python scripts/download_data.py --sectors-only       # 仅板块数据
python scripts/download_data.py --financial          # 仅财务数据
python scripts/download_data.py --incremental         # 增量更新

# 转换 qlib 数据
python scripts/convert_to_qlib.py

# 命令行回测（支持 --report 生成 HTML 报告）
python scripts/run_backtest.py --strategy ma_cross --codes 000001.SZ \
    --start 20230101 --end 20231231 --capital 200000 --fast 10 --slow 30 --report

# 训练模型
python scripts/train_model.py --start 20230101 --end 20231231 \
    --model LightGBM --output models/my_model.pkl --top-k 30

# 运行选股策略
python scripts/run_strategy.py --start 20240101 --end 20240131 \
    --top-k 20 --model models/my_model.pkl --sector 沪深300
```

---

## 7. 测试

```powershell
pytest tests/ -v                         # 全部
pytest tests/test_data.py -v             # 数据存储与 qlib 转换
pytest tests/test_downloader.py -v       # 数据健康检查 (DataValidator)
pytest tests/test_strategy.py -v         # 策略模块
pytest tests/test_backtest.py -v         # 回测模块
pytest tests/test_risk.py -v             # 风控与熔断
pytest tests/test_trading.py -v          # 交易模块（mock）
pytest tests/test_web.py -v              # Web API
pytest tests/test_batch_a_fixes.py -v    # 批次 A 修复回归
```

| 测试文件 | 覆盖模块 |
|----------|----------|
| `test_data.py` | `xt_provider`, `database`, `qlib_converter` |
| `test_downloader.py` | `data_validator` (DataValidator) |
| `test_strategy.py` | `alpha_factors`, `qlib_model`, `signal_generator`, `registry` |
| `test_backtest.py` | `bt_strategy`, `bt_broker`, `runner`, `bt_analyzer` |
| `test_risk.py` | `risk_manager` (RiskManager 熔断机制) |
| `test_trading.py` | `xt_trader` (AccountConfig / TraderManager mock) |
| `test_web.py` | `app.py` 及所有路由模块 |
| `test_batch_a_fixes.py` | qlib 二进制格式、analyzer 纯算法、信号注入回归 |

> 依赖 backtrader 的用例在未安装 backtrader 时自动 `skip`，避免精简环境误报。

---

## 8. 常见问题

<details>
<summary><strong>miniQMT 连接失败？</strong></summary>

1. QMT 交易端是否处于"极简模式"
2. 端口 58610 是否被占用：`netstat -ano | findstr 58610`
3. xtquant 是否安装：`pip list | findstr xtquant`
</details>

<details>
<summary><strong>qlib 初始化报错？</strong></summary>

运行 `python scripts/convert_to_qlib.py` 转换数据格式。不需要 qlib 时因子计算自动回退 pandas 模式。
</details>

<details>
<summary><strong>回测返回 "未加载到任何K线数据"？</strong></summary>

请先执行 `python scripts/download_data.py` 下载数据。
</details>

<details>
<summary><strong>Web API 返回 401 Unauthorized？</strong></summary>

敏感 API 需要 `X-API-Key` 请求头。默认值为 `quant-local-dev`，可通过环境变量 `WEB_API_KEY` 修改。注意 `/api/monitor/*`、`/api/risk/*` 即使是 GET 也需鉴权，且非白名单的 GET 端点默认也鉴权。Swagger 文档中可点击 🔒 按钮设置。
</details>

<details>
<summary><strong>如何添加自定义策略？</strong></summary>

使用装饰器注册到统一注册中心：

```python
from strategy.registry import register_strategy
from strategy.base import BaseStrategy, Signal

@register_strategy("bt")      # 注册为 backtrader 策略
@register_strategy("live")    # 同时注册为实盘策略
class MyStrategy(BaseStrategy):
    name = "my_strategy"
    params = {"period": 10}

    def init(self, context): ...
    def on_bar(self, index) -> list[Signal]: ...
    def get_params_info(self): return {"period": "周期"}
```

或者直接添加到 `STRATEGY_REGISTRY` 字典。
</details>

<details>
<summary><strong>如何添加自定义因子？</strong></summary>

在 `strategy/alpha_factors.py` 中：
1. `FACTOR_META` 添加元信息
2. `QLIB_FACTOR_EXPRESSIONS` 添加 qlib 表达式
3. `QLIB_FACTOR_NAMES` 添加名称
4. `_compute_factors_pandas()` 中实现 pandas 计算逻辑
</details>

<details>
<summary><strong>git 克隆后 web/static/index.html 不存在？</strong></summary>

`.gitignore` 中 `*.html` 规则会一并忽略前端页面 `web/static/index.html` 和回测报告 HTML。若需将前端页面纳入版本控制，可在 `.gitignore` 中追加 `!web/static/index.html` 取反规则，或用 `git add -f web/static/index.html` 强制添加。
</details>

<details>
<summary><strong>实盘交易需要注意什么？</strong></summary>

1. 回测 ≠ 未来表现，充分验证后再实盘
2. 所有实盘下单前务必通过 `RiskManager` 风控检查
3. 买卖数量为 100 的整数倍
4. `config/accounts.yaml` 和 `config/risk.yaml` 不要提交到 Git
5. 生产环境务必修改 `WEB_API_KEY`
</details>

---

## 9. 贡献指南

### 开发环境

```powershell
git clone <repo-url> && cd QuantKing
python -m venv venv && .\venv\Scripts\Activate.ps1
pip install -r requirements.txt
pytest tests/ -v
```

### 代码规范

- **编码声明**: 每个 `.py` 文件首行 `# -*- coding: utf-8 -*-`
- **日志**: 统一使用 `from utils.logging import get_logger`
- **风格**: PEP 8 + Type Hints
- **文档**: 公开类和方法必须编写 docstring
- **重试**: 网络调用使用 `@retry_on_failure` 装饰器
- **策略注册**: 通过 `strategy.registry` 装饰器或显式调用注册
- **提交消息**: 清晰的中文或英文描述

---

## 10. 许可证

本项目采用 **MIT License**。

> **免责声明**: 本软件仅供学习和研究使用。使用本软件进行实盘交易的一切风险和后果由使用者自行承担。作者不对任何因使用本软件导致的直接或间接损失负责。投资有风险，入市需谨慎。

---

## 11. 版本历史

### v2.1.0 (2025)

- 新增 `utils/` 基础设施层：统一日志、指数退避重试、交易时段判断
- 新增 `strategy/registry.py` 统一策略注册中心，支持装饰器注册
- 新增 Web API Key 鉴权中间件（`X-API-Key`）
- 新增 `Database` 审计日志（`audit_log`）、回测历史持久化（`backtest_history`）、除权因子读写
- 新增 `BacktestRunner.run_qlib_signal()` 一键信号回测
- 新增 `RiskManager` 按板块（主板/创业板/科创板/北交所）区分涨跌停比例
- 新增 `POST /api/risk/config` 动态调整风控参数
- 新增 `Downloader` 多线程并行下载（`max_workers`）
- `TraderManager.buy()/sell()` 支持 `strategy_name` 和 `remark` 参数
- `web/app.py` 添加 API Key 鉴权中间件
- `settings.py` 添加 `WEB_API_KEY`、`RISK_CONFIG_PATH`，ACCOUNTS 从 YAML 加载
- 脚本 `download_data.py` 新增 `--stocks-only/--sectors-only/--financial` 参数
- 脚本 `run_backtest.py` 新增 `--report` 生成 HTML 报告

### v2.0.0

- 全新架构：XTquant + qlib + backtrader + FastAPI
- 22+ Alpha 因子双模式计算
- 回测系统（6 个策略，A 股规则）
- 风险控制 + 双熔断机制
- Web 仪表盘 + REST API

### v1.0.0

- 基于 XTquant 的数据下载和实盘交易
- 自研回测引擎
- 基础策略框架
