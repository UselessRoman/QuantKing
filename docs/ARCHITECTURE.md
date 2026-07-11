# 架构说明

## 文档状态

本文同时描述当前 2.x 代码边界和已确认的 V3 目标架构。V3 是后续开发准则，不代表当前功能已经完成。

## 当前实现

当前仓库是一个 Python 模块化单体：

```text
web/ FastAPI
  ├─ data/      XTQuant、SQLite、Parquet、下载与转换
  ├─ strategy/  因子、LightGBM 原型、信号生成
  ├─ backtest/  Backtrader 与绩效分析
  ├─ trading/   XTQuant 自动交易原型
  ├─ risk/      实盘订单风控原型
  └─ utils/     日志、重试、交易时段
```

`trading/` 与 `risk/` 中面向自动下单的能力不再是产品主链路；它们在 V3 迁移期仅作为历史参考，不应扩展新功能。

## V3 目标架构

```text
界面 / CLI
    ↓
应用服务：数据更新、研究实验、回测、调仓、组合账本
    ↓
领域模型：Instrument、Bar、DatasetVersion、Experiment、Signal、Portfolio、RebalancePlan、Fill
    ↓
端口：MarketDataSource、Repository、FactorEngine、ModelRunner、BacktestEngine
    ↓
适配器：XTQuant、AKShare、Parquet/SQLite、qlib、LightGBM、Backtrader
```

这是本地模块化单体，不引入微服务、消息队列或远程鉴权。模块边界必须可测试，业务逻辑不可依赖 FastAPI `Request`、全局状态或具体供应商 SDK。

## 模块职责

| 模块 | 职责 | 不负责 |
|---|---|---|
| `data` | 数据源接入、标准化、校验、版本和存储 | 因子、模型、页面逻辑 |
| `research` | 股票池、因子、标签、训练、实验记录 | 供应商请求、人工成交 |
| `backtest` | 成本/交易规则下的历史组合评估 | 实时交易、模型训练 |
| `portfolio` | 当前组合、目标权重、调仓计划、成交登记 | 券商自动下单 |
| `web` | 本地操作界面与任务展示 | 领域规则和长耗时计算 |

`strategy/` 将逐步演进为 `research/` 与 `portfolio/`。同一策略应产生统一的“日期 × 股票 → 分数 → 目标权重”输出，不能分别维护独立的回测与实盘策略逻辑。

## 关键约束

- 只支持本机 `127.0.0.1` 使用；Web 不承担多用户认证。
- 日频数据是第一优先级；不建设 Tick、盘口和自动交易能力。
- XTQuant 与 AKShare 都是适配器，不能成为数据模型或因子代码的依赖。
- 每次研究和回测必须记录数据版本、股票池、因子版本、标签、参数和成本假设。
- 回测使用的交易规则必须与调仓计划一致：调仓日、价格、手续费、滑点、涨跌停、停牌和 T+1。

## 迁移规则

1. 新能力先按 V3 边界实现，不向旧 `xt_provider.py`、`executor.py` 添加业务逻辑。
2. 旧模块只在有回归测试保护时替换。
3. 每完成一个阶段，补齐单元测试和小规模端到端验证后再进入下一阶段。
4. 自动下单代码只有在用户明确恢复该需求时才重新纳入架构。
