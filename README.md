# QuantKing — A 股量化交易平台

> 基于 **XTquant (miniQMT) + qlib + backtrader + FastAPI** 的个人量化投资系统，覆盖 **数据 → 因子 → 模型 → 回测 → 实盘 → 风控** 完整闭环。

## 项目概述

QuantKing 面向 A 股市场，将策略研发、历史验证和实盘执行整合在统一环境中。系统采用分层解耦设计，数据、策略、回测、交易四层独立运行，可单独测试和替换。

| 环节 | 实现 | 技术支撑 |
|------|------|----------|
| 行情获取 | 全 A 股日/分钟 K 线、财务数据、板块分类 | XTquant SDK（miniQMT 极简模式） |
| 数据存储 | K 线→Parquet 列式文件，元数据→SQLite 索引 | pyarrow + sqlite3 |
| 因子计算 | 22+ Alpha 因子，qlib 表达式 / pandas 双模式 | qlib / pandas + numpy |
| 模型训练 | LightGBM 多因子模型训练与预测 | qlib + lightgbm + scikit-learn |
| 策略回测 | 事件驱动回测，A 股 T+1/涨跌停/佣金规则 | backtrader |
| 绩效分析 | 总收益、年化、最大回撤、夏普、胜率、盈亏比 | quantstats / 自研分析器 |
| 实盘交易 | 限价买卖、撤单、持仓/委托/成交/资产查询 | XTquant Trader API |
| 风险控制 | 单只上限、单笔占比、日亏损熔断、回撤熔断、按板块涨跌停 | 自研 RiskManager |
| Web 面板 | 仪表盘、回测、策略、数据、监控页面 + API Key 鉴权 | FastAPI + 纯 HTML/CSS/JS |

## 系统架构

### 分层架构

```
┌──────────────────────────────────────────────────────────────────┐
│                   Web 展示层 (FastAPI + API Key 鉴权)              │
│  ┌───────────┐  ┌───────────┐  ┌───────────┐  ┌──────────────┐   │
│  │ 仪表盘     │  │ 回测页面   │  │ 策略管理    │  │ 交易监控      │   │
│  └───────────┘  └───────────┘  └───────────┘  └──────────────┘   │
├──────────────────────────────────────────────────────────────────┤
│                   策略引擎层 (qlib / pandas)                       │
│  ┌───────────┐  ┌───────────────┐  ┌──────────────────────────┐  │
│  │ 因子计算   │  │ Alpha 信号生成  │  │ 模型训练与预测 (LightGBM)  │  │
│  └───────────┘  └───────────────┘  └──────────────────────────┘  │
│  ┌───────────────────────────────────────────────────────────┐   │
│  │           strategy.registry — 统一策略注册中心               │   │
│  └───────────────────────────────────────────────────────────┘   │
├──────────────────────────────────────────────────────────────────┤
│                   回测系统层 (backtrader)                          │
│  ┌───────────┐  ┌───────────────┐  ┌──────────────────────────┐  │
│  │ 策略执行   │  │ A股规则模拟     │  │ 绩效分析 (quantstats)      │  │
│  └───────────┘  └───────────────┘  └──────────────────────────┘  │
├──────────────────────────────────────────────────────────────────┤
│                数据层 (xtquant + 本地存储)                         │
│  ┌───────────┐  ┌───────────────┐  ┌──────────────────────────┐  │
│  │ 行情下载   │  │ SQLite+Parquet│  │ qlib 二进制数据转换         │  │
│  └───────────┘  └───────────────┘  └──────────────────────────┘  │
├──────────────────────────────────────────────────────────────────┤
│                 实盘交易层 (xtquant + 风控)                        │
│  ┌───────────┐  ┌───────────────┐  ┌──────────────────────────┐  │
│  │ 订单管理   │  │ 多维风控检查    │  │ 券商柜台对接                │  │
│  └───────────┘  └───────────────┘  └──────────────────────────┘  │
├──────────────────────────────────────────────────────────────────┤
│                基础设施层 (utils/)                                 │
│  ┌───────────┐  ┌───────────────┐  ┌──────────────────────────┐  │
│  │ 统一日志   │  │ 重试装饰器      │  │ 交易时段判断               │  │
│  └───────────┘  └───────────────┘  └──────────────────────────┘  │
└──────────────────────────────────────────────────────────────────┘
```

### 数据流

```
miniQMT ──download_history──▶ XTquant 本地缓存
                                  │
                       get_market_data_ex()
                                  ▼
                         Parquet K线文件 (data/kline/)
                           │                    │
               ┌───────────┤                    ├──────────────┐
               ▼           ▼                    ▼              ▼
        qlib 转换    backtrader数据源      Web API查询    因子计算
        (convert)    (XTQuantDataFeed)    (/api/data)   (FactorHandler)
           │               │                                │
           ▼               ▼                                ▼
    qlib 二进制      cerebro.adddata()            模型训练 (LightGBM)
    (features/)          │                                │
           │             ▼                                ▼
           │     backtrader 回测                   预测分数 Series
           │             │                                │
           ▼             ▼                                ▼
   qlib DataHandler  绩效报告                    SignalGenerator
           │                                         │
           ▼                                         ▼
   22+ Alpha 因子                              Top-K 选股列表
                                               │
                                               ▼
                                ┌─ QlibSignalStrategy (回测)
                                └─ StrategyExecutor   (实盘)

实盘路径: SignalGenerator → StrategyExecutor → RiskManager → TraderManager → 券商柜台
```

## 目录结构

```
QuantKing/
├── config/                          # 全局配置
│   ├── settings.py                  # 路径、端口、风控、日志、API Key
│   ├── accounts.yaml                # 交易账号（敏感信息，.gitignore 排除）
│   └── risk.yaml                    # 风控参数（可选，覆盖默认值）
├── utils/                           # 基础设施工具
│   ├── logging.py                   # 统一日志工厂 (get_logger)
│   ├── retry.py                     # 指数退避重试装饰器 (retry_on_failure)
│   └── trading_hours.py             # 交易时段常量与判断函数
├── data/                            # 数据层
│   ├── xt_provider.py               # XTquant 行情封装 (DataProvider)
│   ├── database.py                  # SQLite + Parquet 存储引擎 (Database)
│   ├── downloader.py                # 数据下载器 (Downloader)
│   ├── qlib_converter.py            # Parquet → qlib 二进制转换
│   ├── backtrader_feeder.py         # DataFrame → backtrader 数据源
│   └── data_validator.py            # K 线数据健康检查器 (DataValidator)
├── strategy/                        # 策略引擎
│   ├── base.py                      # 策略基类 (BaseStrategy, Signal)
│   ├── registry.py                  # 统一策略注册中心 (REGISTRY)
│   ├── alpha_factors.py             # 22+ 因子定义与双模式计算 (FactorHandler)
│   ├── qlib_model.py                # 模型训练与预测 (QlibTrainer)
│   └── signal_generator.py          # 选股信号生成 (SignalGenerator)
├── backtest/                        # 回测系统
│   ├── bt_strategy.py               # 6 个 backtrader 策略 + 注册表对接
│   ├── bt_broker.py                 # A 股佣金方案 (AShareCommission/Sizer)
│   ├── runner.py                    # 回测执行器 (BacktestRunner)
│   └── bt_analyzer.py              # 绩效分析器 (BacktestAnalyzer)
├── trading/                         # 实盘交易
│   ├── xt_trader.py                 # 实盘交易管理器 (TraderManager)
│   └── executor.py                  # 策略执行器 (StrategyExecutor)
├── risk/                            # 风险控制
│   └── risk_manager.py              # 风险管理器 (RiskManager)
├── web/                             # Web 展示层
│   ├── app.py                       # FastAPI 应用 + API Key 鉴权中间件
│   └── routes/                      # data/strategy/backtest/monitor/risk 路由
├── scripts/                         # 命令行工具
│   ├── download_data.py             # 数据下载
│   ├── convert_to_qlib.py           # qlib 数据转换
│   ├── run_backtest.py              # 回测执行
│   ├── train_model.py               # 模型训练
│   └── run_strategy.py              # 选股策略运行
├── tests/                           # 测试套件（89 个用例）
├── docs/                            # 项目文档
│   ├── ARCHITECTURE.md              # 架构与开发指南
│   ├── CHANGELOG.md                 # 修改历史
│   ├── ROADMAP.md                   # 下一步更新方向
│   └── quant-packages-api-reference.md  # xtquant/qlib/backtrader API 速查
├── data/kline/1d/                   # 日K线 Parquet 文件（3000+ 只 A 股）
├── main.py                          # 启动入口
└── requirements.txt                 # 依赖清单
```

## 快速开始

### 环境要求

- **操作系统**: Windows 10/11（miniQMT 仅支持 Windows）
- **Python**: 3.10+（推荐 3.10.11，与 qlib 和 backtrader 兼容性最佳）
- **miniQMT**: 需安装券商提供的 QMT 交易端并以极简模式运行

### 安装步骤

```powershell
git clone <repo-url> && cd QuantKing
python -m venv venv
.\venv\Scripts\Activate.ps1
pip install -r requirements.txt

# XTquant 需从 miniQMT 安装目录手动安装 wheel
# 一般位于: <QMT安装目录>\bin\xtquant\xtquant-xxxxx.whl
pip install "E:\券商QMT交易端\bin\xtquant\xtquant-xxxxx.whl"
```

### 验证安装

```powershell
# 1. 验证 xtquant 连接（需先启动 miniQMT）
python -c "from xtquant import xtdata; xtdata.connect(port=58610); print(len(xtdata.get_stock_list_in_sector('沪深A股')), '只A股')"

# 2. 运行测试套件
pytest tests/ -v
```

### 启动服务

```powershell
# 下载全量 A 股数据（首次使用）
python scripts/download_data.py

# 转换 qlib 数据格式
python scripts/convert_to_qlib.py

# 启动 Web 平台
python main.py
# 浏览器访问 http://127.0.0.1:8000
```

### 命令行工具

```powershell
# 数据管理
python scripts/download_data.py                          # 全量下载
python scripts/download_data.py --incremental             # 增量更新
python scripts/download_data.py --stocks-only             # 仅股票信息
python scripts/convert_to_qlib.py                         # qlib 格式转换

# 策略与回测
python scripts/run_backtest.py --strategy ma_cross --codes 000001.SZ \
    --start 20230101 --end 20231231 --capital 200000 --report
python scripts/train_model.py --start 20230101 --end 20231231 --output models/my_model.pkl
python scripts/run_strategy.py --start 20240101 --end 20240131 --top-k 20
```

## 配置

核心配置集中在 `config/settings.py`，敏感信息分离到 YAML 文件：

| 配置项 | 位置 | 说明 |
|--------|------|------|
| 路径/端口/日志 | `config/settings.py` | `BASE_DIR`、`XT_PORT=58610`、`WEB_PORT=8000` |
| API Key | 环境变量 `WEB_API_KEY` | 默认 `quant-local-dev`，生产环境务必修改 |
| 交易账号 | `config/accounts.yaml` | miniQMT 路径、资金账号（勿提交 Git） |
| 风控参数 | `config/risk.yaml` | 5 项参数，可热更新，不存在时用默认值 |

风控默认参数：

```python
RISK_CONFIG = {
    "max_position_per_stock": 100000,   # 单只持仓上限（股）
    "max_single_order_ratio": 0.20,     # 单笔占比上限
    "max_daily_loss_ratio": 0.05,       # 日亏损熔断阈值
    "max_drawdown_ratio": 0.20,         # 回撤熔断阈值
    "max_holdings_count": 50,           # 最大持仓数量
}
```

## 测试

```powershell
pytest tests/ -v                         # 全部（89 个用例）
pytest tests/test_data.py -v             # 数据存储与 qlib 转换
pytest tests/test_strategy.py -v         # 策略模块
pytest tests/test_backtest.py -v         # 回测模块
pytest tests/test_risk.py -v             # 风控与熔断
pytest tests/test_web.py -v              # Web API
```

依赖 backtrader 的用例在未安装时自动 `skip`，避免精简环境误报。

## Web API 概览

所有敏感 API 需通过 `X-API-Key` 请求头鉴权。`/api/monitor/*` 和 `/api/risk/*` 即使 GET 也强制鉴权。

| 路由组 | 前缀 | 主要功能 |
|--------|------|----------|
| 数据 | `/api/data` | K 线查询、股票/板块列表、数据下载、财务数据 |
| 策略 | `/api/strategy` | 策略列表、因子查询、模型训练、预测信号 |
| 回测 | `/api/backtest` | 回测执行、历史记录、多策略对比 |
| 监控 | `/api/monitor` | 持仓、委托、成交、资产、仪表盘（强制鉴权） |
| 风控 | `/api/risk` | 风险状态、参数配置、熔断重置、订单检查（强制鉴权） |

启动后访问 `http://127.0.0.1:8000/docs` 查看 Swagger 文档。

## 文档索引

| 文档 | 内容 |
|------|------|
| [架构与开发指南](docs/ARCHITECTURE.md) | 模块设计详解、数据流、项目约定、已知陷阱、扩展方法 |
| [修改历史](docs/CHANGELOG.md) | 版本演进记录、批次修复详情、git 提交历史 |
| [更新方向](docs/ROADMAP.md) | 已知技术债务、改进机会、后续开发计划 |
| [三件套 API 速查](docs/quant-packages-api-reference.md) | xtquant / qlib / backtrader 官方 API 速查与项目集成规范 |
| [搭建指导（历史）](NEW_PROJECT_GUIDE.md) | 项目初始搭建与迁移方案（存档参考） |

## 常见问题

<details>
<summary><strong>miniQMT 连接失败？</strong></summary>

1. 确认 QMT 交易端处于"极简模式"
2. 检查端口 58610：`netstat -ano | findstr 58610`
3. 确认 xtquant 已安装：`pip list | findstr xtquant`
</details>

<details>
<summary><strong>qlib 初始化报错？</strong></summary>

运行 `python scripts/convert_to_qlib.py` 转换数据格式。不需要 qlib 时因子计算自动回退 pandas 模式。
</details>

<details>
<summary><strong>回测返回 "未加载到任何K线数据"？</strong></summary>

先执行 `python scripts/download_data.py` 下载数据。
</details>

<details>
<summary><strong>Web API 返回 401 Unauthorized？</strong></summary>

敏感 API 需要 `X-API-Key` 请求头。默认值为 `quant-local-dev`，可通过环境变量 `WEB_API_KEY` 修改。Swagger 文档中点击锁形按钮设置。
</details>

<details>
<summary><strong>如何添加自定义策略？</strong></summary>

使用装饰器注册到统一注册中心：

```python
from strategy.registry import register_strategy
from strategy.base import BaseStrategy, Signal

@register_strategy("bt")       # 注册为 backtrader 策略
@register_strategy("live")     # 同时注册为实盘策略
class MyStrategy(BaseStrategy):
    name = "my_strategy"
    params = {"period": 10}

    def init(self, context): ...
    def on_bar(self, index) -> list[Signal]: ...
    def get_params_info(self): return {"period": "周期"}
```
</details>

<details>
<summary><strong>git 克隆后 web/static/index.html 不存在？</strong></summary>

`.gitignore` 中 `*.html` 规则会一并忽略前端页面。若需纳入版本控制，追加 `!web/static/index.html` 取反规则，或用 `git add -f` 强制添加。
</details>

## 贡献指南

- 每个 `.py` 文件首行加 `# -*- coding: utf-8 -*-`
- 日志统一使用 `from utils.logging import get_logger`
- 网络调用使用 `@retry_on_failure` 装饰器
- 策略通过 `strategy.registry` 装饰器注册
- 遵循 PEP 8 + Type Hints，公开类和方法编写 docstring

## 许可证

MIT License。

> **免责声明**: 本软件仅供学习和研究使用。使用本软件进行实盘交易的一切风险和后果由使用者自行承担。投资有风险，入市需谨慎。
