# -*- coding: utf-8 -*-
"""
项目全局配置

集中管理所有可配置参数，修改后重启应用生效。

路径说明:
    BASE_DIR:      项目根目录（config/ 的上级目录）
    DB_PATH:       SQLite 元数据库文件路径（stocks/sectors/trade_records）
    KLINE_DIR:     Parquet K线数据目录
    FINANCIAL_DIR: Parquet 财务数据目录
    QLIB_DATA_DIR: qlib 二进制数据目录
    XT_DATA_DIR:   miniQMT 行情数据缓存目录

网络配置:
    XT_PORT:  miniQMT 行情服务端口号（默认 58610）
    WEB_HOST: Web 服务监听地址
    WEB_PORT: Web 服务监听端口

账号配置:
    ACCOUNTS: 实盘交易账号列表，每条配置对应一个 QMT 实盘交易端接入点。
    所有交易操作通过 XTquant SDK 直接下达至券商交易柜台。

安全提醒:
    账号信息涉及真实资金操作，请妥善保管配置文件，避免泄露。
    建议生产环境通过环境变量注入敏感参数。
"""
import os
import sys
from pathlib import Path

# 项目根目录
BASE_DIR = Path(__file__).resolve().parent.parent

# 将项目根目录加入 Python 包搜索路径
sys.path.insert(0, str(BASE_DIR))

# SQLite 元数据库文件路径
DB_PATH = BASE_DIR / "quant.db"

# Parquet K线数据目录 — 结构: data/kline/{1d,1m,...}/{code}.parquet
KLINE_DIR = BASE_DIR / "data" / "kline"

# Parquet 财务数据目录 — 结构: data/financial/{code}.parquet
FINANCIAL_DIR = BASE_DIR / "data" / "financial"

# qlib 二进制数据目录
QLIB_DATA_DIR = BASE_DIR / "data" / "qlib_data_cn"

# miniQMT 行情服务端口号
XT_PORT = 58610

# miniQMT 行情数据本地缓存目录
XT_DATA_DIR = BASE_DIR / "xtdata"

# Web 服务配置
WEB_HOST = "127.0.0.1"
WEB_PORT = 8000

# API 鉴权密钥（生产环境请通过环境变量 WEB_API_KEY 注入）
# 默认值仅用于本地开发，若不设置则无鉴权要求。
WEB_API_KEY = os.environ.get("WEB_API_KEY", "quant-local-dev")

# 账号配置文件路径
ACCOUNTS_YAML = BASE_DIR / "config" / "accounts.yaml"

# 实盘交易账号配置列表
# 每条配置包含:
#   id:           账号唯一标识（用于 API 调用）
#   label:        显示名称（用于日志和前端展示）
#   miniqmt_path: 券商 QMT 交易端的 userdata_mini 目录绝对路径
#   account_id:   资金账号
#   account_type: 账号类型，"STOCK" 表示股票账户
#
# 账号信息统一从 config/accounts.yaml 加载，settings.py 中不再硬编码。
# 如果 yaml 文件不存在或解析失败，ACCOUNTS 为空列表并记录日志便于排查。
_ACCOUNTS_PATH = BASE_DIR / "config" / "accounts.yaml"
ACCOUNTS: list = []
try:
    import yaml as _yaml
    if _ACCOUNTS_PATH.exists():
        with open(_ACCOUNTS_PATH, 'r', encoding='utf-8') as _f:
            _raw = _yaml.safe_load(_f)
            if isinstance(_raw, dict):
                ACCOUNTS = _raw.get('accounts', [])
            else:
                import logging
                logging.getLogger(__name__).error(
                    "accounts.yaml 顶层应为 dict，实际为 %s，ACCOUNTS 置空",
                    type(_raw).__name__
                )
    else:
        import logging
        logging.getLogger(__name__).warning(
            "账号配置文件不存在: %s，实盘交易功能不可用", _ACCOUNTS_PATH
        )
except _yaml.YAMLError as _e:
    import logging
    logging.getLogger(__name__).error(
        "accounts.yaml 解析失败: %s，ACCOUNTS 置空", _e
    )
except Exception as _e:
    import logging
    logging.getLogger(__name__).error(
        "加载 accounts.yaml 时发生意外错误: %s，ACCOUNTS 置空", _e
    )

# 风险控制参数
# 优先从 config/risk.yaml 加载（支持运行时热更新），文件缺失或解析失败
# 则回退到下面的默认值，保证系统可启动。
_RISK_DEFAULTS = {
    "max_position_per_stock": 100000,     # 单只股票最大持仓（股）
    "max_single_order_ratio": 0.2,        # 单笔订单最大资金占比
    "max_daily_loss_ratio": 0.05,         # 日最大亏损比例（触发熔断）
    "max_drawdown_ratio": 0.20,           # 最大回撤比例（触发熔断）
    "max_holdings_count": 50,             # 最大持仓股票数
}

RISK_CONFIG_PATH = BASE_DIR / "config" / "risk.yaml"
RISK_CONFIG: dict = dict(_RISK_DEFAULTS)
try:
    import yaml as _yaml
    if RISK_CONFIG_PATH.exists():
        with open(RISK_CONFIG_PATH, 'r', encoding='utf-8') as _f:
            _risk_raw = _yaml.safe_load(_f)
        if isinstance(_risk_raw, dict):
            # 用 yaml 值覆盖默认值（缺失键保留默认）
            RISK_CONFIG.update(_risk_raw)
        else:
            import logging
            logging.getLogger(__name__).error(
                "risk.yaml 顶层应为 dict，实际为 %s，使用默认风控参数",
                type(_risk_raw).__name__
            )
except _yaml.YAMLError as _e:
    import logging
    logging.getLogger(__name__).error(
        "risk.yaml 解析失败: %s，使用默认风控参数", _e
    )
except Exception as _e:
    import logging
    logging.getLogger(__name__).error(
        "加载 risk.yaml 失败: %s，使用默认风控参数", _e
    )

# 日志配置
LOG_CONFIG = {
    "level": "INFO",
    "format": "%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    "file": str(BASE_DIR / "logs" / "quant.log"),
    "max_bytes": 10 * 1024 * 1024,       # 10MB
    "backup_count": 5,
}
