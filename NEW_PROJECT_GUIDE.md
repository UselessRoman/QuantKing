# 量化交易系统新项目搭建指导文档

> **目标**: 基于现有项目资产，使用 xtquant + qlib + backtrader + Web 技术栈，搭建个人量化交易平台。
> **受众**: 新的开发 Agent，需具备该文档独立完成项目搭建。
> **现有项目路径**: `e:\Realdemo`

---

## 目录

1. [项目架构设计](#1-项目架构设计)
2. [环境配置指南](#2-环境配置指南)
3. [模块开发规范](#3-模块开发规范)
4. [现有资源迁移方案](#4-现有资源迁移方案)
5. [开发流程建议](#5-开发流程建议)
6. [测试与验证方法](#6-测试与验证方法)

---

## 1. 项目架构设计

### 1.1 整体架构图

```
┌─────────────────────────────────────────────────────────────┐
│                       Web 展示层 (Flask/FastAPI)              │
│   ┌──────────┐  ┌──────────┐  ┌──────────┐  ┌────────────┐ │
│   │ 策略结果  │  │ 账户信息  │  │ 市场数据  │  │ 回测报告    │ │
│   └──────────┘  └──────────┘  └──────────┘  └────────────┘ │
├─────────────────────────────────────────────────────────────┤
│                   策略引擎层 (qlib)                           │
│   ┌──────────┐  ┌──────────────┐  ┌──────────────────────┐ │
│   │ 因子计算  │  │ Alpha 信号   │  │ 模型训练与预测        │ │
│   └──────────┘  └──────────────┘  └──────────────────────┘ │
├─────────────────────────────────────────────────────────────┤
│                   回测系统层 (backtrader)                     │
│   ┌──────────┐  ┌──────────────┐  ┌──────────────────────┐ │
│   │ 策略执行  │  │ 模拟交易     │  │ 绩效分析 (quantstats) │ │
│   └──────────┘  └──────────────┘  └──────────────────────┘ │
├─────────────────────────────────────────────────────────────┤
│                 数据层 (xtquant + 本地存储)                   │
│   ┌──────────┐  ┌──────────────┐  ┌──────────────────────┐ │
│   │ 行情下载  │  │ K线/财务存储  │  │ qlib 数据转换         │ │
│   │(xtquant) │  │(SQLite+Parquet)│  │(Parquet→qlib bin)  │ │
│   └──────────┘  └──────────────┘  └──────────────────────┘ │
└─────────────────────────────────────────────────────────────┘
```

### 1.2 模块职责与交互关系

| 模块 | 职责 | 依赖 | 对外接口 |
|------|------|------|----------|
| **data/** | 数据获取、存储、格式转换 | xtquant, pandas, pyarrow | REST API + Python 函数调用 |
| **strategy/** | qlib 多因子策略定义、信号生成 | qlib, pandas | `strategy.predict()` 方法 |
| **backtest/** | backtrader 策略回测执行与分析 | backtrader, pandas | `BacktestRunner.run()` 方法 |
| **web/** | Web 可视化的 API 和页面 | FastAPI/Flask | HTTP REST API |
| **config/** | 全局配置管理 | yaml/py | `config.yaml` 配置文件 |

### 1.3 数据流向

```
miniQMT 服务器
     │ xtdata.download_history_data()
     ▼
本地 Parquet K线缓存 (data/kline/1d/*.parquet)
     │
     ├──→ qlib 数据转换脚本 (convert_data.py)
     │        │
     │        ▼
     │    qlib 二进制数据 (data/qlib_data/)
     │        │
     │        ▼
     │    qlib 策略引擎 → 因子计算 → Alpha 信号
     │
     ├──→ backtrader 数据加载
     │        │
     │        ▼
     │    backtrader 回测引擎 → 策略执行 → 绩效报告
     │
     └──→ Web API 查询 (FastAPI)
              │
              ▼
         前端可视化 (图表/表格)
```

### 1.4 技术选型说明

| 技术 | 版本要求 | 用途 | 选型理由 |
|------|---------|------|----------|
| **xtquant** | latest (miniQMT) | A股行情下载、实盘交易接口 | 官方SDK，唯一稳定A股数据源 |
| **qlib** | ≥0.9.0 | 多因子策略开发、模型训练 | 微软开源，因子→模型→回测一体化 |
| **backtrader** | ≥1.9.0 | 策略回测框架 | 成熟稳定，社区活跃，A股规则可定制 |
| **FastAPI** | ≥0.100.0 | Web API 服务 | 异步高性能，自动生成文档 |
| **pandas** | ≥2.0.0 | 数据分析和处理 | 量化标配 |
| **pyarrow** | ≥14.0.0 | Parquet 文件读写 | 列式存储，高效读写 |
| **SQLite** | 内置 | 元数据索引存储 | 轻量免安装 |

### 1.5 新项目目录结构

```
quant_trading/                      # 新项目根目录
├── config/
│   ├── __init__.py
│   ├── settings.py                 # 全局配置（路径、端口等）
│   └── accounts.yaml               # 交易账号配置（独立文件，安全考虑）
├── data/
│   ├── __init__.py
│   ├── xt_provider.py              # [可直接复用] XTquant 行情封装
│   ├── database.py                 # [可直接复用] SQLite+Parquet 存储
│   ├── downloader.py               # [可直接复用] 数据下载器
│   ├── qlib_converter.py           # [新建] Parquet→qlib 二进制格式转换
│   └── backtrader_feeder.py        # [新建] Parquet→backtrader 数据源适配
├── strategy/
│   ├── __init__.py
│   ├── alpha_factors.py            # [新建] qlib 因子表达式定义
│   ├── qlib_model.py               # [新建] qlib 模型训练与预测
│   └── signal_generator.py         # [新建] 信号生成与选股
├── backtest/
│   ├── __init__.py
│   ├── bt_strategy.py              # [新建] backtrader 策略适配器
│   ├── bt_broker.py                # [新建] backtrader 模拟券商（A股规则）
│   ├── bt_analyzer.py              # [新建] backtrader 分析器集成
│   └── runner.py                   # [新建] 回测运行入口
├── web/
│   ├── __init__.py
│   ├── app.py                      # [可参考现有] FastAPI 应用
│   ├── routes/
│   │   ├── __init__.py
│   │   ├── data_routes.py          # [可参考现有] 数据查询接口
│   │   ├── strategy_routes.py      # [可参考现有] 策略管理接口
│   │   ├── backtest_routes.py      # [新建] 回测执行与结果接口
│   │   └── monitor_routes.py       # [新建] 实时监控接口
│   └── static/
│       └── index.html              # [新建] 前端页面
├── scripts/
│   ├── download_data.py            # [可直接复用] 数据下载脚本
│   ├── convert_to_qlib.py          # [新建] qlib 数据转换脚本
│   ├── run_backtest.py             # [参考现有，重写] backtrader 回测脚本
│   ├── train_model.py              # [新建] qlib 模型训练脚本
│   └── run_strategy.py             # [参考现有] 策略运行脚本
├── tests/
│   ├── test_data.py
│   ├── test_strategy.py
│   ├── test_backtest.py
│   └── test_web.py
├── requirements.txt
├── main.py
└── README.md
```

---

## 2. 环境配置指南

### 2.1 基础环境

**操作系统**: Windows 10/11（miniQMT 仅支持 Windows）

**Python 版本**: 3.10+（推荐 3.10.11，与 qlib 和 backtrader 兼容性最佳）

### 2.2 虚拟环境创建

```powershell
# 创建项目目录
mkdir quant_trading
cd quant_trading

# 创建虚拟环境
python -m venv venv

# 激活虚拟环境
.\venv\Scripts\Activate.ps1

# 升级 pip
python -m pip install --upgrade pip setuptools wheel
```

### 2.3 依赖包安装

创建 `requirements.txt`:

```text
# 核心数据处理
pandas>=2.0.0
numpy>=1.24.0
pyarrow>=14.0.0

# qlib 策略引擎（微软量化框架）
pyqlib>=0.9.0

# backtrader 回测框架
backtrader>=1.9.76
matplotlib>=3.7.0

# Web 服务
fastapi>=0.100.0
uvicorn[standard]>=0.23.0
jinja2>=3.1.0

# 机器学习（qlib 可能需要）
scikit-learn>=1.3.0
lightgbm>=4.0.0

# 绩效可视化
quantstats>=0.0.62

# 测试
pytest>=8.0.0
httpx>=0.27.0

# YAML 配置
pyyaml>=6.0

# XTquant 需要手动安装：
# 从 miniQMT 安装目录的 bin 文件夹下找到 xtquant 包并安装
# pip install xtquant-xxxxx.whl
```

安装命令:

```powershell
pip install -r requirements.txt

# XTquant 手动安装（路径以实际 miniQMT 安装位置为准）
# 一般位于: <QMT安装目录>\bin\xtquant\
# pip install "E:\国金证券QMT交易端\bin\xtquant\xtquant-xxxxx.whl"
```

### 2.4 miniQMT 环境准备

1. 下载并安装券商提供的 QMT（迅投量化交易终端）
2. 启动 miniQMT（极简模式），确认端口 58610 已监听
3. 验证数据连接:

```python
from xtquant import xtdata
xtdata.connect(port=58610)
codes = xtdata.get_stock_list_in_sector('沪深A股')
print(f"共 {len(codes)} 只 A 股股票")
xtdata.disconnect()
```

### 2.5 qlib 数据初始化

qlib 需要将原始K线数据转换为专有的二进制格式：

```python
# scripts/convert_to_qlib.py
from qlib.data import D
from qlib.data.dataset.loader import QlibDataLoader
from qlib.contrib.data.handler import Alpha158

# qlib 数据存放目录
QLIB_DIR = "data/qlib_data_cn"

# 数据格式要求（每只股票一个 CSV/Parquet，columns 需包含 OHLCV）
# 从现有 Parquet 数据转换
```

qlib 数据目录结构（需手动建立）:
```
data/qlib_data_cn/
├── calendars/
│   └── day.txt              # 沪深交易日历
├── instruments/
│   └── all.txt              # 股票列表及上市退市日期
└── features/
    └── <stock_code>/
        ├── open.day.bin
        ├── high.day.bin
        ├── low.day.bin
        ├── close.day.bin
        ├── volume.day.bin
        ├── amount.day.bin
        └── ...
```

### 2.6 配置文件说明

`config/settings.py`:

```python
import os
from pathlib import Path

# 项目根目录
BASE_DIR = Path(__file__).resolve().parent.parent

# SQLite 元数据库
DB_PATH = BASE_DIR / "quant.db"

# K线 Parquet 存储
KLINE_DIR = BASE_DIR / "data" / "kline"

# 财务数据 Parquet 存储
FINANCIAL_DIR = BASE_DIR / "data" / "financial"

# qlib 数据目录
QLIB_DATA_DIR = BASE_DIR / "data" / "qlib_data_cn"

# XTquant 配置
XT_PORT = 58610
XT_DATA_DIR = BASE_DIR / "xtdata"

# Web 服务
WEB_HOST = "127.0.0.1"
WEB_PORT = 8000

# 交易账号（从 yaml 文件读取更安全）
ACCOUNTS_YAML = BASE_DIR / "config" / "accounts.yaml"
```

`config/accounts.yaml`:

```yaml
accounts:
  - id: "real"
    label: "实盘"
    miniqmt_path: "E:\\国金证券QMT交易端\\userdata_mini"
    account_id: "8887100825"
    account_type: "STOCK"
```

---

## 3. 模块开发规范

### 3.1 数据获取模块 (data/)

#### 3.1.1 职责

- 通过 xtquant 从 miniQMT 获取 A 股行情数据
- 将原始数据持久化到本地 SQLite + Parquet 存储
- 提供统一的数据查询接口
- 将数据转换为 qlib 和 backtrader 所需格式

#### 3.1.2 核心接口定义

```python
# data/xt_provider.py [可直接复用现有]
class DataProvider:
    """XTquant 行情数据封装层"""
    def connect(self, port: int = 58610) -> bool: ...
    def disconnect(self) -> None: ...
    def download_history(self, codes: list[str], period: str = '1d',
                         start_time: str = '', end_time: str = '') -> None: ...
    def download_history_incremental(self, codes: list[str], period: str = '1d') -> None: ...
    def get_kline(self, codes: list[str], period: str = '1d',
                  start_time: str = '', end_time: str = '',
                  count: int = -1, dividend_type: str = 'front') -> pd.DataFrame: ...
    def get_stock_list(self) -> list[str]: ...
    def get_sector_list(self) -> list[str]: ...
    def get_stock_list_in_sector(self, sector_name: str) -> list[str]: ...
    def get_instrument_detail(self, code: str) -> dict: ...
    def download_financial_data(self, codes: list[str]) -> None: ...
    def get_financial_data(self, codes: list[str]) -> dict: ...

# data/database.py [可直接复用现有]
class Database:
    """SQLite + Parquet 混合存储"""
    def connect(self) -> None: ...
    def close(self) -> None: ...
    def initialize(self) -> None: ...
    def insert_daily_kline(self, records: list[dict], period: str = '1d') -> int: ...
    def get_daily_kline_df(self, code: str, period: str = '1d',
                           start_date: str = '', end_date: str = '') -> pd.DataFrame: ...
    def upsert_stocks(self, records: list[dict]) -> None: ...
    def get_all_stocks(self) -> list[dict]: ...
    def get_stats(self) -> dict: ...

# data/downloader.py [可直接复用现有]
class Downloader:
    """数据下载器"""
    def download_all_a_stocks(self, period: str = '1d', ...) -> int: ...
    def download_stock_info(self) -> int: ...
    def download_sector_data(self) -> None: ...
    def incremental_update(self, period: str = '1d', days: int = 5) -> int: ...
    def download_all_financial(self) -> int: ...

# data/qlib_converter.py [新建]
def convert_kline_to_qlib_format(
    parquet_dir: str = "data/kline",
    output_dir: str = "data/qlib_data_cn",
    period: str = "1d"
) -> None:
    """
    将现有 Parquet K线数据转换为 qlib 二进制格式

    qlib 要求的数据格式:
        - features/<code>/open.day.bin 等二进制文件
        - calendars/day.txt 交易日历
        - instruments/all.txt 股票列表
    """
    ...

# data/backtrader_feeder.py [新建]
class XTQuantDataFeed(bt.feeds.PandasData):
    """
    backtrader 数据源适配器

    将现有 Parquet/DataFrame K线数据加载为 backtrader 可识别的数据源。
    从 Database.get_daily_kline_df(code) 获取 DataFrame 后注入。

    使用示例:
        db = Database()
        db.connect()
        df = db.get_daily_kline_df("000001.SZ", "1d", "20230101", "20231231")
        data = XTQuantDataFeed(dataname=df)
        cerebro.adddata(data)
    """
    params = (
        ('datetime', 'date'),
        ('open', 'open'),
        ('high', 'high'),
        ('low', 'low'),
        ('close', 'close'),
        ('volume', 'volume'),
        ('openinterest', -1),
    )
```

#### 3.1.3 实现标准

- **DataProvider**: 完全复用现有代码，不做修改。路径: `e:\Realdemo\data\xt_provider.py`
- **Database**: 完全复用现有代码。路径: `e:\Realdemo\data\database.py`
- **Downloader**: 完全复用现有代码。路径: `e:\Realdemo\data\downloader.py`
- **qlib_converter**: 新建，从 Parquet 读取所有股票K线，按 qlib 的 `convert_csv` 工具链转换
- **backtrader_feeder**: 新建，将 DataFrame 包装成 backtrader 的 `PandasData` 即可

### 3.2 策略开发模块 (strategy/)

#### 3.2.1 职责

- 使用 qlib 框架定义多因子表达式
- 训练预测模型（LightGBM/XGBoost/LSTM）
- 生成选股信号（Top-K 排序）
- 为 backtrader 回测提供信号输入

#### 3.2.2 核心接口定义

```python
# strategy/alpha_factors.py [新建]
from qlib.contrib.data.handler import Alpha158

class FactorHandler:
    """
    qlib 因子处理器

    基于 qlib 的 Alpha158 或自定义因子表达式，计算因子值。
    复用现有 research/factors.py 中的 20+ 因子计算逻辑，
    在 qlib 框架中以表达式形式重写。

    现有可用因子（来自现有项目 research/factors.py）:
        动量类: ret_1d, ret_5d, ret_10d, ret_20d, ret_60d
        波动率类: std_5d, std_20d, hl_amplitude_20d
        量价类: vol_ratio_5_20, vol_ratio_5_60, volume_trend_10d
        均线偏离类: ma5_dev, ma10_dev, ma20_dev, ma60_dev
        技术指标类: rsi_14, macd_dif, macd_signal, macd_hist, bb_position
        反转类: reversal_3d
        流动性: turnover_5d
    """
    def __init__(self, instruments: str = 'all', start_time: str = '', end_time: str = ''): ...
    def load_factors(self) -> pd.DataFrame: ...
    def get_factor_names(self) -> list[str]: ...

# strategy/qlib_model.py [新建]
class QlibTrainer:
    """
    qlib 模型训练器

    参考现有项目 research/model_train.py 中的 FactorModel 类，
    迁移到 qlib 框架下，利用 qlib.Model 和 qlib.Dataset 标准化训练流程。

    主要改动:
        1. 使用 qlib 的 DatasetH 处理数据加载（替代手写的 prepare_data）
        2. 使用 qlib 的 Model 接口封装模型训练（替代直接调用 lightgbm）
        3. 使用 qlib 的 backtest 模块进行策略回测
    """
    def __init__(self, model_type: str = 'LightGBM'): ...
    def train(self, handler: FactorHandler) -> dict: ...
    def predict(self, handler: FactorHandler) -> pd.Series: ...
    def save(self, path: str) -> None: ...
    def load(self, path: str) -> None: ...
    def get_feature_importance(self) -> pd.DataFrame: ...

# strategy/signal_generator.py [新建]
class SignalGenerator:
    """
    信号生成器

    基于模型预测结果，生成选股信号：
    - Top-K 选股
    - 阈值过滤
    - 行业中性化
    """
    def generate(self, predictions: pd.Series, top_k: int = 20,
                 min_score: float = None) -> list[str]:
        """返回入选股票代码列表"""
        ...

    def generate_with_risk_control(self, predictions: pd.Series,
                                    positions: dict, top_k: int = 20) -> dict:
        """返回调仓指令 {code: action(BUY/SELL/HOLD)}"""
        ...
```

#### 3.2.3 qlib 因子表达式示例

qlib 使用表达式字符串定义因子，对应现有项目 `factors.py` 的计算：

```python
# ===== qlib 因子表达式 =====
# 对应现有因子 → 重写为以下格式

qlib_factors = [
    # 动量类 (ret_1d → $close / Ref($close, 1) - 1)
    "Ref($close, -1) / Ref($close, -2) - 1",                                    # ret_1d
    "Ref($close, -1) / Ref($close, -6) - 1",                                    # ret_5d

    # 波动率类 (std_5d)
    "Std(Ref($close, -1) / Ref($close, -2) - 1, 5)",                            # std_5d

    # 均线偏离类 (ma5_dev → $close / Mean($close, 5) - 1)
    "$close / Mean($close, 5) - 1",                                             # ma5_dev

    # 技术指标类 (rsi_14)
    "RSI($close, 14)",                                                           # rsi_14
]
```

#### 3.2.4 因子到模型的标准流程

```
原始K线数据 (Parquet)
     │
     ▼
qlib DataHandler (Alpha158/自定义表达式)
     │ → DataFrame (code × date × factors)
     ▼
qlib DatasetH (数据切分: train/valid/test)
     │
     ▼
qlib Model (LightGBM)
     │ → 训练 → 预测
     ▼
SignalGenerator → Top-K 选股列表
     │
     ▼
backtrader 回测策略 → 执行买卖 → 绩效分析
```

### 3.3 回测系统模块 (backtest/)

#### 3.3.1 职责

- 基于 backtrader 框架提供完整的策略回测环境
- 实现 A 股市场规则（T+1、涨跌停、佣金印花税）
- 集成 qlib 策略信号，实现信号驱动回测
- 输出绩效指标（收益率、回撤、夏普、胜率等）

#### 3.3.2 核心接口定义

```python
# backtest/bt_strategy.py [新建]
import backtrader as bt

class QlibSignalStrategy(bt.Strategy):
    """
    qlib 信号驱动的 backtrader 策略

    在每个调仓日读取 qlib 预测信号，买入 Top-K 股票，
    卖出落选持仓。等权分配资金。

    参数:
        signal_provider: 信号生成器实例
        top_k:           持仓数量
        rebalance_freq:  调仓频率（交易日数）
    """
    params = (
        ('top_k', 20),
        ('rebalance_freq', 20),
    )

    def __init__(self): ...
    def next(self):
        """每个 bar 调用一次"""
        if self._is_rebalance_day():
            sell_list, buy_list = self._get_rebalance_signals()
            self._execute_sells(sell_list)
            self._execute_buys(buy_list)

    def notify_order(self, order):
        """订单状态回调"""
        ...

# backtest/bt_broker.py [新建]
class AShareCommission(bt.CommInfoBase):
    """
    A 股佣金方案

    费率:
        佣金: 万2.5（最低5元）
        印花税: 千1（仅卖出收）
        过户费: 暂不计
    """
    params = (
        ('commission', 0.00025),
        ('stamp_duty', 0.001),
        ('min_commission', 5.0),
    )
    def _getcommission(self, size, price, pseudoexec):
        """计算佣金"""
        ...

# backtest/bt_analyzer.py [新建]
class BacktestAnalyzer:
    """
    回测性能分析

    集成 quantstats 库生成专业绩效报告。
    同时也复用现有项目 backtest/analyzer.py 中的计算逻辑。
    """
    def analyze(self, cerebro: bt.Cerebro) -> dict:
        """从 cerebro 结果中提取绩效指标"""
        ...

    def generate_report(self, result: dict, output_path: str) -> str:
        """生成 HTML 绩效报告"""
        ...

    def get_equity_curve(self, cerebro) -> pd.DataFrame:
        """获取净值曲线"""
        ...

# backtest/runner.py [新建]
class BacktestRunner:
    """
    回测执行器

    封装 backtrader.Cerebro 的创建、配置和执行流程，
    对外提供简洁的 run() 接口。
    """
    def __init__(self, initial_capital: float = 100000, commission_rate: float = 0.00025): ...

    def load_data(self, codes: list[str], start_date: str, end_date: str) -> None:
        """从本地数据库加载K线数据到 cerebro"""
        ...

    def set_strategy(self, strategy_cls, **params) -> None:
        """设置回测策略"""
        ...

    def run(self) -> dict:
        """执行回测并返回结果"""
        return {
            'performance': ...,  # 绩效指标
            'equity_curve': ..., # 净值曲线
            'trade_log': ...,    # 交易记录
        }
```

#### 3.3.3 需要重新开发的部分

| 现有组件 | 新项目方案 | 迁移难度 |
|----------|-----------|---------|
| `backtest/engine.py` - 自研回测引擎 | 使用 backtrader 替代 | 高（接口完全不同） |
| `backtest/broker.py` - 自研模拟券商 | 继承 `bt.CommInfoBase` 重写 | 中（逻辑可参考但接口不同） |
| `backtest/analyzer.py` - 自研分析器 | 复用计算逻辑，加 quantstats | 低（核心逻辑可保留） |
| `strategies/base.py` - 策略基类 | 改用 `bt.Strategy` 基类 | 中（接口模式变化） |
| 5 个现有策略 | 重写为 backtrader Strategy | 中（信号逻辑保留，接口重写） |

#### 3.3.4 backtrader 策略示例（均线交叉）

```python
# 将现有 strategies/ma_cross.py 改写为 backtrader 策略
import backtrader as bt

class MACrossStrategy(bt.Strategy):
    """均线交叉策略（backtrader 版本）"""
    params = (
        ('fast', 5),
        ('slow', 20),
    )

    def __init__(self):
        self.fast_ma = bt.indicators.SMA(self.data.close, period=self.params.fast)
        self.slow_ma = bt.indicators.SMA(self.data.close, period=self.params.slow)
        self.crossover = bt.indicators.CrossOver(self.fast_ma, self.slow_ma)

    def next(self):
        if self.crossover > 0:           # 金叉
            self.buy(size=100)
        elif self.crossover < 0:         # 死叉
            self.sell(size=100)
```

### 3.4 Web 展示模块 (web/)

#### 3.4.1 职责

- 提供策略结果、账户信息、市场数据的可视化展示
- REST API 供前端页面调用
- 实时监控面板（持仓、委托、资产变化）

#### 3.4.2 核心接口定义

```python
# web/app.py [参考现有项目重写]
from fastapi import FastAPI

app = FastAPI(title="量化交易平台", version="2.0.0")

# 路由注册
# /api/data/*        — 行情数据查询
# /api/strategy/*    — qlib 策略管理
# /api/backtest/*    — 回测执行与结果
# /api/monitor/*     — 实时监控

# web/routes/data_routes.py [可直接复用现有]
"""
GET  /api/data/kline          — 查询K线数据
GET  /api/data/stocks          — 查询股票列表
GET  /api/data/stock-klines    — 查询股票K线概览
POST /api/data/stocks/sync     — 同步股票信息
POST /api/data/kline/download  — 下载K线数据
POST /api/data/kline/update    — 增量更新K线
POST /api/data/sectors/sync    — 同步板块数据
POST /api/data/financial/download — 下载财务数据
GET  /api/data/financial       — 查询财务数据
"""

# web/routes/strategy_routes.py [新建]
"""
GET  /api/strategy/list        — 获取可用策略列表
POST /api/strategy/train       — 训练 qlib 模型
POST /api/strategy/predict     — 运行预测
GET  /api/strategy/signals     — 获取选股信号
GET  /api/strategy/factors     — 获取因子分析报告
"""

# web/routes/backtest_routes.py [新建]
"""
POST /api/backtest/run          — 执行回测
GET  /api/backtest/result/{id}  — 获取回测结果
GET  /api/backtest/history      — 回测历史记录
GET  /api/backtest/report/{id}  — 获取绩效报告
"""

# web/routes/monitor_routes.py [可参考现有 trading_routes.py]
"""
GET  /api/monitor/positions     — 持仓查询
GET  /api/monitor/orders        — 委托查询
GET  /api/monitor/asset         — 资产查询
GET  /api/monitor/accounts      — 账号状态
"""
```

#### 3.4.3 前端页面规划

使用 Jinja2 模板 + 轻量 JavaScript 实现，不引入重型前端框架：

| 页面 | 路径 | 功能 |
|------|------|------|
| 首页仪表盘 | `/` | 资产总览、净值曲线、最近信号 |
| 回测页面 | `/backtest` | 策略选择、参数配置、回测执行、结果展示 |
| 策略管理 | `/strategy` | 因子配置、模型训练、信号查看 |
| 数据管理 | `/data` | 数据下载、更新、状态查看 |
| 交易监控 | `/monitor` | 实时持仓、委托、成交记录 |

### 3.5 qlib 与 backtrader 的集成方案

这是新项目的核心难点。推荐方案：

```
数据流:
  Parquet K线 → qlib Converter → qlib 二进制数据
                                    │
                                    ▼
                              qlib DataHandler
                                    │
                                    ▼
                              因子计算 (Alpha158)
                                    │
                                    ▼
                              qlib Model (LightGBM)
                                    │
                                    ▼
                              预测分数 (pd.Series)
                                    │
                                    ├──→ SignalGenerator → 选股列表
                                    │
  Parquet K线 → XTQuantDataFeed → backtrader Cerebro
                                    │
                                    ▼
                              QlibSignalStrategy ← 信号接入
                                    │
                                    ▼
                              Cerebro.run() → 绩效报告
```

关键集成代码:

```python
# 在 backtrader 策略中使用 qlib 信号
class QlibSignalStrategy(bt.Strategy):
    def __init__(self):
        # 从 qlib 加载预计算信号
        self.signals = self._load_qlib_signals()  # {date: [codes]}

    def _load_qlib_signals(self):
        """加载 qlib 预测的选股信号"""
        # 调用 signal_generator 获取每日选股列表
        ...

    def next(self):
        current_date = self.datas[0].datetime.date(0)
        if current_date in self.signals:
            target_codes = self.signals[current_date]
            # 卖出不在目标池的持仓
            # 买入新入选的股票
            ...
```

---

## 4. 现有资源迁移方案

### 4.1 可直接复用的代码（零修改）

| 源文件 | 目标位置 | 复用原因 |
|--------|----------|----------|
| `data/xt_provider.py` | `data/xt_provider.py` | 完善的 XTquant 封装，完全不依赖现有业务 |
| `data/database.py` | `data/database.py` | SQLite+Parquet 存储层，与后端框架无关 |
| `data/downloader.py` | `data/downloader.py` | 数据下载器，基于 DataProvider + Database |
| `config/settings.py` | `config/settings.py` | 全局配置，仅需改路径即可 |
| `trading/xt_trader.py` | `trading/xt_trader.py` | 实盘交易管理，与回测系统无关 |
| `trading/executor.py` | `trading/executor.py` | 策略执行器，基于策略基类信号 |

### 4.2 可部分参考的代码

| 源文件 | 复用什么 | 需变更什么 |
|--------|----------|-----------|
| `strategies/base.py` | `Signal` 数据类 | 策略基类改用 `bt.Strategy` |
| `strategies/ma_cross.py` 等5个策略 | 信号判断逻辑（金叉/死叉） | 重写为 backtrader 策略格式 |
| `backtest/analyzer.py` | 夏普/回撤/胜率计算逻辑 | 输入从自定义格式改为 backtrader 结果 |
| `backtest/broker.py` | A股交易规则（T+1/涨跌停/费率） | 改用 backtrader CommInfoBase + Sizer |
| `web/app.py` | FastAPI 应用框架结构 | 路由模块调整 |
| `web/routes/*.py` | data_routes 可复用 | 新增 strategy/backtest 路由 |
| `signals/screener.py` | 批量选股逻辑 | 与 qlib SignalGenerator 整合 |
| `scripts/download_data.py` | shell 脚本结构 | 可直接复用 |
| `research/factors.py` | 20+ 因子计算公式 | 迁移到 qlib 表达式格式 |
| `research/model_train.py` | LightGBM 训练流程 | 使用 qlib 封装的 train/predict |
| `research/ml_backtest_engine.py` | 组合调仓逻辑 | 迁移到 backtrader Strategy |
| `research/factor_analysis.py` | IC/Rank IC/ICIR 计算 | 可直接复用 |

### 4.3 可直接复用的数据

| 数据 | 路径 | 大小 |
|------|------|------|
| A股日K线 (约3000+只) | `data/kline/1d/*.parquet` | ~300MB |
| SQLite 元数据库 | `quant.db` | ~5MB |
| 财务数据（如有） | `data/financial/*.parquet` | 视下载量 |

迁移命令:
```powershell
# 直接复制整个 data 目录
xcopy e:\Realdemo\data\kline quant_trading\data\kline\ /E /I
xcopy e:\Realdemo\data\financial quant_trading\data\financial\ /E /I
copy e:\Realdemo\quant.db quant_trading\quant.db
```

### 4.4 需要重新开发的部分

| 模块 | 说明 |
|------|------|
| `data/qlib_converter.py` | 全新，Parquet→qlib 二进制转换 |
| `data/backtrader_feeder.py` | 全新，DataFrame→backtrader 数据源 |
| `strategy/qlib_model.py` | 全新，基于 qlib 框架的模型训练 |
| `backtest/bt_strategy.py` | 全新，backtrader 策略适配器 |
| `backtest/bt_broker.py` | 全新，A股佣金方案 |
| `backtest/runner.py` | 全新，回测运行封装 |
| `backtest/bt_analyzer.py` | 新模块，quantstats 集成 |
| `web/static/` 前端页面 | 全新 HTML/CSS/JS |

### 4.5 迁移检查清单

- [ ] 复制 `data/kline/` 目录到新项目
- [ ] 复制 `quant.db` 到新项目
- [ ] 复制 `data/xt_provider.py`, `data/database.py`, `data/downloader.py`
- [ ] 复制 `config/settings.py`，调整路径
- [ ] 复制 `trading/xt_trader.py`, `trading/executor.py`
- [ ] 复制 `research/factors.py` 中的因子计算公式
- [ ] 新建 `data/qlib_converter.py`
- [ ] 新建 `data/backtrader_feeder.py`
- [ ] 新建 `backtest/` 下全部文件
- [ ] 新建 `strategy/` 下全部文件
- [ ] 重写 `web/` 下全部文件（可参考现有路由结构）
- [ ] 安装 qlib 并初始化数据

---

## 5. 开发流程建议

### 5.1 分阶段任务分解

#### 阶段 1：环境搭建与数据准备（预计 1-2 天）

**目标**: 可运行的开发环境，数据可用

| 任务 | 优先级 | 验证标准 |
|------|--------|----------|
| 1.1 安装 Python 3.10 + 创建虚拟环境 | P0 | `python --version` 正确 |
| 1.2 安装依赖包 (requirements.txt) | P0 | `pip list` 无报错 |
| 1.3 安装 miniQMT + xtquant | P0 | `from xtquant import xtdata` 成功 |
| 1.4 复制现有 data/kline/ 数据 | P0 | 文件数量正确 |
| 1.5 验证 Database 读写 | P0 | 可读取K线到 DataFrame |
| 1.6 新建项目目录结构 | P0 | 所有目录存在 |
| 1.7 安装 qlib，初始化数据目录 | P1 | `import qlib` 成功 |
| 1.8 开发 qlib_converter.py | P1 | 将 Parquet 转为 qlib 格式可读 |
| 1.9 验证 qlib 数据加载 | P1 | `qlib.data.D.features()` 返回数据 |

#### 阶段 2：策略引擎开发（预计 2-3 天）

**目标**: qlib 多因子策略可训练和预测

| 任务 | 优先级 | 验证标准 |
|------|--------|----------|
| 2.1 开发 qlib 因子表达式 (Alpha158+自定义) | P0 | 因子 DataFrame 生成正确 |
| 2.2 开发 FactorHandler 封装类 | P0 | load_factors() 返回有效数据 |
| 2.3 开发 QlibTrainer 训练流程 | P1 | train() 返回模型 |
| 2.4 开发预测和选股逻辑 | P1 | predict() 返回有序分数 |
| 2.5 因子 IC/ICIR 分析 | P2 | 复用 research/factor_analysis.py |
| 2.6 模型保存与加载 | P2 | 模型持久化正常工作 |

#### 阶段 3：回测系统开发（预计 2-3 天）

**目标**: backtrader 回测可正常运行并输出报告

| 任务 | 优先级 | 验证标准 |
|------|--------|----------|
| 3.1 开发 XTQuantDataFeed | P0 | 数据成功注入 cerebro |
| 3.2 开发 AShareCommission (A股费率) | P0 | 买入/卖出成本计算正确 |
| 3.3 实现简单均线策略 (backtrader版本) | P0 | 与原回测结果可对比 |
| 3.4 开发 QlibSignalStrategy (组合选股) | P1 | 按信号调仓 |
| 3.5 集成 T+1 和涨跌停限制 | P1 | 策略不违规交易 |
| 3.6 开发 Runner 封装 | P1 | run() 一键执行 |
| 3.7 开发 Analyzer + quantstats 报告 | P2 | 生成 HTML 报告 |
| 3.8 现有 5 个策略改写为 backtrader 版本 | P2 | 各策略在 backtrader 中运行 |

#### 阶段 4：Web 展示开发（预计 2-3 天）

**目标**: Web 网站可展示策略结果、数据、监控信息

| 任务 | 优先级 | 验证标准 |
|------|--------|----------|
| 4.1 搭建 FastAPI 应用框架 | P0 | `python main.py` 启动成功 |
| 4.2 实现 data_routes（参考现有） | P0 | 数据查询 API 可用 |
| 4.3 实现 backtest_routes | P1 | 回测执行+结果查询 API |
| 4.4 实现 strategy_routes | P1 | 策略管理 API |
| 4.5 实现 monitor_routes | P2 | 实时监控 API |
| 4.6 开发首页仪表盘 HTML | P1 | 资产总览可视化 |
| 4.7 开发回测页面 HTML | P2 | 策略配置+结果展示 |
| 4.8 开发策略管理页面 | P2 | 因子查看+模型管理 |
| 4.9 开发交易监控页面 | P2 | 持仓+委托实时展示 |

#### 阶段 5：集成测试与优化（预计 1-2 天）

**目标**: 全流程跑通，性能达标

| 任务 | 优先级 | 验证标准 |
|------|--------|----------|
| 5.1 端到端回测测试 | P0 | 数据→因子→模型→信号→回测→报告 |
| 5.2 Web 全接口测试 | P0 | 所有 API 返回正确 |
| 5.3 性能测试 (全A股因子计算) | P1 | 5000+ 股票，< 5分钟 |
| 5.4 修复边界问题 + 异常处理 | P1 | 空数据/断连等场景不崩溃 |
| 5.5 编写 README 和 API 文档 | P2 | 新人可依据文档上手 |

### 5.2 关键里程碑

```
Day 1-2  [M1] 环境跑通，可读写K线数据
Day 3-5  [M2] qlib 因子+模型可训练预测
Day 6-8  [M3] backtrader 回测可运行
Day 9-11 [M4] Web 页面可展示
Day 12-13 [M5] 全流程集成测试通过
```

---

## 6. 测试与验证方法

### 6.1 数据模块测试

```python
# tests/test_data.py

def test_xt_provider_connection():
    """测试 miniQMT 连接"""
    from data.xt_provider import DataProvider
    p = DataProvider()
    p.connect()
    assert p.is_connected()
    p.disconnect()

def test_database_kline():
    """测试 K 线读写"""
    from data.database import Database
    db = Database()
    db.connect()
    db.initialize()
    df = db.get_daily_kline_df("000001.SZ", "1d")
    assert not df.empty
    assert 'close' in df.columns
    db.close()

def test_downloader_incremental():
    """测试增量下载"""
    from data.downloader import Downloader
    d = Downloader()
    count = d.incremental_update(days=3)
    assert count >= 0
    d.close()

def test_qlib_converter():
    """测试 qlib 数据转换"""
    from data.qlib_converter import convert_kline_to_qlib_format
    convert_kline_to_qlib_format()
    # 验证 qlib 可读取
    import qlib
    from qlib.config import REG_CN
    qlib.init(provider_uri="data/qlib_data_cn", region=REG_CN)
    from qlib.data import D
    instruments = D.instruments(market='all')
    assert len(instruments) > 0
```

### 6.2 策略模块测试

```python
# tests/test_strategy.py

def test_factor_computation():
    """测试因子计算"""
    from strategy.alpha_factors import FactorHandler
    handler = FactorHandler(start_time="2023-01-01", end_time="2023-06-30")
    factors = handler.load_factors()
    assert not factors.empty
    assert 'rsi_14' in factors.columns or len(factors.columns) > 0

def test_model_training():
    """测试模型训练"""
    from strategy.qlib_model import QlibTrainer
    trainer = QlibTrainer(model_type='LightGBM')
    result = trainer.train(handler)
    assert 'IC' in result or 'loss' in result

def test_signal_generation():
    """测试信号生成"""
    from strategy.signal_generator import SignalGenerator
    sg = SignalGenerator()
    predictions = pd.Series({code: score for code, score in ...})
    signals = sg.generate(predictions, top_k=20)
    assert len(signals) == 20
    assert all(isinstance(c, str) for c in signals)
```

### 6.3 回测模块测试

```python
# tests/test_backtest.py

import backtrader as bt
from data.database import Database
from backtest.bt_strategy import MACrossStrategy
from backtest.bt_broker import AShareCommission

def test_simple_backtest():
    """测试简单均线策略回测"""
    db = Database()
    db.connect()
    df = db.get_daily_kline_df("000001.SZ", "1d", "20230101", "20231231")
    db.close()

    cerebro = bt.Cerebro()
    data = bt.feeds.PandasData(dataname=df)
    cerebro.adddata(data)
    cerebro.addstrategy(MACrossStrategy)
    cerebro.broker.setcash(100000)
    cerebro.addcommissioninfo(AShareCommission())

    start_value = cerebro.broker.getvalue()
    cerebro.run()
    end_value = cerebro.broker.getvalue()

    # 不做收益断言（策略可亏可赚），只验证流程正常
    assert end_value > 0
    print(f"初始资金: {start_value:.2f}, 最终资金: {end_value:.2f}")
    print(f"收益率: {(end_value/start_value - 1)*100:.2f}%")

def test_qlib_signal_backtest():
    """测试 qlib 信号驱动的回测"""
    cerebro = bt.Cerebro()
    # 加载多只股票数据
    # 设置 QlibSignalStrategy
    cerebro.run()
    # 验证有交易记录
    ...

def test_a_share_rules():
    """测试 A 股规则正确性"""
    # 1. T+1：当日买入次日才能卖出
    # 2. 涨停不买入
    # 3. 跌停不卖出
    # 4. 佣金最低5元
    ...
```

### 6.4 Web 模块测试

```python
# tests/test_web.py
from httpx import AsyncClient
from web.app import app

def test_data_api():
    """测试数据 API"""
    with TestClient(app) as client:
        r = client.get("/api/data/stocks")
        assert r.status_code == 200
        assert r.json()["count"] > 0

def test_backtest_api():
    """测试回测 API"""
    with TestClient(app) as client:
        r = client.post("/api/backtest/run", json={
            "strategy": "ma_cross",
            "codes": ["000001.SZ"],
            "start_date": "20230101",
            "end_date": "20231231",
            "initial_capital": 100000,
        })
        assert r.status_code == 200
        assert "performance" in r.json()
```

### 6.5 性能验证标准

| 测试项 | 数据规模 | 性能指标 | 验证方法 |
|--------|---------|---------|----------|
| K线数据批量下载 | 5000只股票 | < 30 分钟 | `download_all_a_stocks` 执行计时 |
| 全市场因子计算 | 5000只股票×200天 | < 5 分钟 | `FactorHandler.load_factors` 计时 |
| qlib 模型训练 | 5000只×200天 | < 10 分钟 | `QlibTrainer.train` 计时 |
| backtrader 回测 | 20 只股票×1年 | < 30 秒 | `Runner.run` 计时 |
| Web API 响应 | 单次查询 | < 500ms | httpx 请求计时 |

### 6.6 回归测试对比

新项目回测结果需与现有项目对比验证（以均线策略为例）：

```python
def test_regression():
    """回归测试：新 backtrader 回测 vs 旧自研回测"""
    # 相同的策略参数、股票、时间范围、初始资金

    # 旧项目结果
    old_result = run_old_backtest(...)

    # 新项目结果
    new_result = run_new_backtest_with_backtrader(...)

    # 允许小于 1% 的差异（因成交价计算略有不同）
    diff = abs(old_result['total_return'] - new_result['total_return'])
    assert diff < 0.01, f"回归测试失败: 差异 {diff:.2%}"
```

### 6.7 一键验证脚本

```python
# scripts/verify_all.py
"""
一键运行全部验证
用法: python scripts/verify_all.py
"""
import subprocess
import sys

tests = [
    "pytest tests/test_data.py -v",
    "pytest tests/test_strategy.py -v",
    "pytest tests/test_backtest.py -v",
    "pytest tests/test_web.py -v",
]

for test in tests:
    print(f"\n{'='*60}")
    print(f"执行: {test}")
    result = subprocess.run(test, shell=True)
    if result.returncode != 0:
        print("验证失败!")
        sys.exit(1)

print("\n全部验证通过!")
```

---

## 附录

### A. 现有项目文件索引

```
e:\Realdemo\
├── main.py                          # [C] Web 启动入口（8000）
├── config/settings.py               # [M] 全局配置
├── data/
│   ├── xt_provider.py               # [M] xtquant 行情封装
│   ├── database.py                  # [M] SQLite+Parquet 存储
│   ├── downloader.py                # [M] 数据下载器
│   └── kline/1d/*.parquet           # [M] ~3000+ 只 A 股日线
├── strategies/
│   ├── base.py                      # [R] 策略基类 Signal/BaseStrategy
│   ├── ma_cross.py                  # [R] 均线交叉
│   ├── macd.py                      # [R] MACD
│   ├── rsi.py                       # [R] RSI
│   ├── turtle.py                    # [R] 海龟交易
│   └── bollinger_bands.py           # [R] 布林带
├── backtest/
│   ├── engine.py                    # [R] 自研回测引擎
│   ├── broker.py                    # [R] 模拟券商 A 股规则
│   └── analyzer.py                  # [R] 绩效分析
├── trading/
│   ├── xt_trader.py                 # [M] xtquant 实盘交易
│   └── executor.py                  # [M] 策略执行器
├── web/
│   ├── app.py                       # [R] FastAPI 应用
│   └── routes/*.py                  # [R] API 路由
├── research/
│   ├── factors.py                   # [M] 20+ 因子计算
│   ├── factor_analysis.py           # [M] IC/ICIR 分析
│   ├── model_train.py               # [R] LightGBM 训练
│   ├── ml_backtest_engine.py        # [R] ML 回测引擎
│   ├── advanced_metrics.py          # [R] 高级度量
│   └── visualization.py             # [R] 可视化
├── signals/screener.py              # [R] 选股筛选器
├── scripts/
│   ├── download_data.py             # [M] 数据下载
│   ├── run_backtest.py              # [R] 回测脚本
│   └── run_strategy.py              # [R] 策略执行脚本
└── tests/                           # 完整测试套件
```

> 图例: [M]=可完整复用, [R]=需参考改写, [C]=可直接使用

### B. 关键依赖版本对照

| 包名 | 现有项目 | 新项目 | 兼容性 |
|------|---------|--------|--------|
| Python | 3.10+ | 3.10.11 | 完全兼容 |
| pandas | 2.0+ | 2.0+ | 完全兼容 |
| xtquant | latest | latest | 需手动安装 |
| fastapi | 0.100+ | 0.100+ | 完全兼容 |
| backtrader | 无 | 1.9.76+ | 新增 |
| qlib | 无 | 0.9.0+ | 新增 |
| lightgbm | 在 research 中使用 | qlib 内部使用 | 兼容 |
| pyarrow | 14.0+ | 14.0+ | 完全兼容 |

### C. 常见问题与注意事项

1. **xtquant 安装**: 只能从 miniQMT 安装目录手动安装 wheel，pip 仓库无此包
2. **qlib 数据初始化**: 需要先有 Parquet 数据才能转换，且 qlib 对日期格式有特殊要求
3. **backtrader 与 pandas**: 确保 `pandas<3.0`，backtrader 暂未适配 pandas 3.x
4. **Windows 编码**: 所有 `.py` 文件首行加上 `# -*- coding: utf-8 -*-`，避免中文路径和注释问题
5. **A 股交易规则**: T+1 需在 backtrader 的 `next()` 中手动实现（记录买入日期 + 禁止当日卖出）
6. **涨跌停处理**: 涨停不买、跌停不卖，需在订单提交前过滤
7. **账号安全**: 包含资金账号的配置文件不要提交到 Git，使用 `.gitignore` 排除
