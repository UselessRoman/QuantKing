# 数据架构与质量规范

详细字段、单位、版本与测试要求见 [技术规范](TECHNICAL_STANDARDS.md)。已确认的数据源边界见 [架构决策](DECISIONS.md)。

## 目标

构建可替换、可校验、可追溯的本地 A 股日频数据仓。XTQuant 用于迁移期和历史基线；AKShare 是免费主接入候选。任一供应商不可成为业务代码的隐含依赖。

## 数据集优先级

### 第一优先级

- 证券主数据：代码、交易所、名称、上市/退市日期、状态、板块。
- 交易日历。
- 日线：`code, date, open, high, low, close, volume, amount`。
- 复权数据或公司行为数据。
- 基准指数日线。

这些数据足以支持量价因子、LightGBM 和日频组合回测。

### 第二优先级

- 停复牌、ST、涨跌停、流通股本、行业分类。
- 历史指数成分股，避免幸存者偏差。
- 财报及公告日期；只有公告日期可得时才构造基本面因子。

不采集 Tick、盘口和实时推送数据。

## 统一接口

```python
class MarketDataSource(Protocol):
    def list_instruments(self) -> pd.DataFrame: ...
    def get_trading_calendar(self, start: str, end: str) -> pd.DataFrame: ...
    def get_daily_bars(self, codes: list[str], start: str, end: str) -> pd.DataFrame: ...
    def get_adjustments(self, codes: list[str], start: str, end: str) -> pd.DataFrame: ...
    def get_index_bars(self, codes: list[str], start: str, end: str) -> pd.DataFrame: ...
```

适配器只负责供应商请求和字段映射；重试、路由、校验、存储和业务规则位于供应商之外。备用源只能在显式策略下使用，不能静默覆盖主源。

## 存储分层

```text
data/
  raw/<source>/<dataset>/             # 原始响应或原始表，禁止修改
  canonical/<dataset>/                # 统一契约后的可查询数据
  derived/<dataset_version>/          # 复权、因子、qlib 视图等派生数据
```

SQLite 保存索引、任务、质量报告与版本清单；Parquet 保存大体量表。每个批次至少记录：`source`、`dataset`、`ingested_at`、`trade_date`、`schema_version`、行数、校验结果和校验和。

## 复权规则

- 永远保存未复权 OHLCV，禁止覆盖。
- 复权价格是派生数据，必须绑定来源和算法版本。
- 一个因子、标签或回测不能混用不同供应商的复权序列。
- 回测成交价和研究收益口径必须分别明确记录。

## 质量检查

每次入库至少检查：

1. 主键 `(code, date)` 唯一，日期属于交易日历。
2. OHLC 合法：价格非负、`high >= low`、成交量和成交额非负。
3. 覆盖率：当日股票数、缺失股票数、各股票最后日期。
4. 连续性：异常跳空、停牌缺口、复权因子突变。
5. 双源抽样：抽样比较收盘价、成交量、日期和复权结果；差异进入报告。

校验失败的数据不能自动进入研究数据集；应保留原始批次并显示原因。

## 更新节奏

- 首次迁移：保留现有 XTQuant 历史快照，随后用 AKShare 对小样本进行对账。
- 日常：收盘后增量下载、校验、入库；只在成功生成新数据版本后更新因子和信号。
- 定期：每月重检历史修订、证券状态与复权变化。
