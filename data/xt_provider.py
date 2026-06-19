# -*- coding: utf-8 -*-
"""
XTquant 行情数据封装层

对 XTquant SDK 的行情接口进行统一封装，隔离底层依赖，方便后续替换数据源。

数据返回格式:
    调用 get_kline 等方法返回的数据格式与 xtdata.get_market_data_ex 一致:
    返回 DataFrame，index 为日期，columns 为 (字段名, 股票代码) 的 MultiIndex。

连接管理:
    - 实例化 DataProvider 不会自动连接，需显式调用 connect()
    - 调用 disconnect() 可断开连接并释放资源

依赖:
    需要 miniQMT 环境，且 xtquant 包已安装才能正常工作。
"""
import pandas as pd
from config.settings import XT_PORT, XT_DATA_DIR
from utils.retry import retry_on_failure

try:
    from xtquant import xtdata
    _XT_AVAILABLE = True
except ImportError:
    xtdata = None
    _XT_AVAILABLE = False


class DataProvider:
    """
    XTquant 行情数据封装层

    封装了 xtdata 模块的常用行情接口，提供:
        - 行情连接管理
        - 历史/实时K线数据获取与下载
        - 股票列表与板块信息查询
        - 合约详情与财务数据
        - Tick 数据与除权除息信息
    """

    def __init__(self):
        self._connected = False

    @retry_on_failure(max_retries=3, base_delay=1.0, exceptions=(ConnectionError, OSError))
    def connect(self, port: int | None = None) -> bool:
        """
        连接 miniQMT 行情服务

        参数:
            port: 行情服务端口号，默认使用 settings.XT_PORT（58610）

        返回:
            bool: 连接成功返回 True

        异常:
            ImportError:     xtquant 包未安装
            ConnectionError: 连接失败（如端口未监听、miniQMT 未启动）
        """
        if not _XT_AVAILABLE:
            raise ImportError("xtquant 未安装，请先安装 xtquant 包")

        actual_port = port if port is not None else XT_PORT
        try:
            xtdata.connect(port=actual_port)
            self._connected = True
            return True
        except Exception as e:
            raise ConnectionError(f"连接 miniQMT 失败: {e}")

    def disconnect(self) -> None:
        """
        断开与 miniQMT 行情服务的连接

        释放 xtdata 占用的网络和缓存资源。
        """
        if not _XT_AVAILABLE or not self._connected:
            return
        try:
            xtdata.disconnect()
        except Exception:
            pass
        finally:
            self._connected = False

    def download_history(self, codes: list[str], period: str = '1d',
                         start_time: str = '', end_time: str = '') -> None:
        """
        下载历史K线数据到本地缓存

        数据会缓存在 XTquant 的本地数据目录中，后续 get_kline 可直接读取。

        参数:
            codes:      股票代码列表，如 ["000001.SZ", "600000.SH"]
            period:     周期类型，可选 "1d"（日线）/ "1m"（1分钟）/ "5m"（5分钟）等
            start_time: 起始时间，格式 YYYYMMDD，空字符串表示从头下载
            end_time:   结束时间，格式 YYYYMMDD，空字符串表示到最新
        """
        if not _XT_AVAILABLE:
            return
        for code in codes:
            xtdata.download_history_data(code, period=period,
                                         start_time=start_time, end_time=end_time)

    def download_history_incremental(self, codes: list[str], period: str = '1d') -> None:
        """
        增量下载历史K线数据

        仅下载本地缺失的部分，比全量下载更快。适合定时更新场景。

        参数:
            codes:  股票代码列表
            period: 周期类型，默认 "1d"
        """
        if not _XT_AVAILABLE:
            return
        for code in codes:
            xtdata.download_history_data(code, period=period, incrementally=True)

    def get_kline(self, codes: list[str], period: str = '1d',
                  start_time: str = '', end_time: str = '',
                  count: int = -1, dividend_type: str = 'front') -> pd.DataFrame:
        """
        获取K线数据

        必须先调用 download_history 下载数据，否则可能返回空或不全。

        参数:
            codes:         股票代码列表
            period:        周期类型，"1d"/"1m"/"5m" 等
            start_time:    起始时间，YYYYMMDD 格式
            end_time:      结束时间，YYYYMMDD 格式
            count:         获取最近多少根K线，-1 表示全部
            dividend_type: 复权方式: "front"(前复权) / "back"(后复权) / "none"(不复权)

        返回:
            pd.DataFrame: index 为日期/时间，
                         columns 为 (字段, 股票代码) 的 MultiIndex，
                         字段: open/high/low/close/volume/amount
        """
        if not _XT_AVAILABLE:
            return pd.DataFrame()
        fields = ['open', 'high', 'low', 'close', 'volume', 'amount']
        result = xtdata.get_market_data_ex(
            fields, codes, period=period,
            start_time=start_time, end_time=end_time,
            count=count, dividend_type=dividend_type
        )
        if result is None:
            return pd.DataFrame()
        if isinstance(result, pd.DataFrame):
            return result
        if isinstance(result, dict):
            if not result:
                return pd.DataFrame()
            try:
                return pd.DataFrame(result)
            except Exception:
                pass
            try:
                frames = {}
                for key, val in result.items():
                    if isinstance(val, pd.DataFrame):
                        frames[key] = val
                if frames:
                    merged = pd.concat(frames, axis=1)
                    if isinstance(merged.columns, pd.MultiIndex):
                        return merged
                    merged.columns = pd.MultiIndex.from_product([list(frames.keys()), codes])
                    return merged
            except Exception:
                pass
        return pd.DataFrame()

    def get_market_data(self, codes: list[str], period: str = '1d',
                        count: int = -1, dividend_type: str = 'front') -> pd.DataFrame:
        """
        获取实时/最新K线数据（不依赖本地缓存）

        与 get_kline 不同，此方法直接从 miniQMT 服务端拉取数据，
        无需提前调用 download_history。适合盘中实时策略场景。

        参数:
            codes:         股票代码列表
            period:        周期类型
            count:         获取最近K线数量
            dividend_type: 复权方式

        返回:
            pd.DataFrame: 与 get_kline 格式一致
        """
        if not _XT_AVAILABLE:
            return pd.DataFrame()
        fields = ['open', 'high', 'low', 'close', 'volume', 'amount']
        result = xtdata.get_market_data(
            fields, codes, period=period,
            count=count, dividend_type=dividend_type
        )
        if isinstance(result, dict):
            return pd.DataFrame()
        if result is None:
            return pd.DataFrame()
        return result

    def get_full_tick(self, codes: list[str]) -> pd.DataFrame:
        """
        获取全推Tick数据

        返回当前最新的全推行情快照，包含买卖五档价格和数量。
        适用于盘中实时监控场景。

        参数:
            codes: 股票代码列表

        返回:
            pd.DataFrame: 全推行情数据，含 lastPrice/bidPrice/askPrice 等字段
        """
        if not _XT_AVAILABLE:
            return pd.DataFrame()
        return xtdata.get_full_tick(codes)

    def get_stock_list(self) -> list[str]:
        """
        获取沪深A股全部股票代码列表

        返回:
            list[str]: 沪深A股所有股票的代码列表，如 ["000001.SZ", "000002.SZ", ...]
        """
        if not _XT_AVAILABLE:
            return []
        return xtdata.get_stock_list_in_sector('沪深A股')

    def get_sector_list(self) -> list[str]:
        """
        获取所有板块名称列表

        返回:
            list[str]: 如 ["沪深A股", "沪深300", "创业板", "半导体", ...]
        """
        if not _XT_AVAILABLE:
            return []
        return xtdata.get_sector_list()

    def get_stock_list_in_sector(self, sector_name: str) -> list[str]:
        """
        获取指定板块的成分股列表

        参数:
            sector_name: 板块名称，如 "沪深300"

        返回:
            list[str]: 该板块包含的股票代码列表
        """
        if not _XT_AVAILABLE:
            return []
        return xtdata.get_stock_list_in_sector(sector_name)

    def download_financial_data(self, codes: list[str]) -> None:
        """下载财务数据到本地缓存"""
        if not _XT_AVAILABLE:
            return
        xtdata.download_financial_data2(codes)

    def get_financial_data(self, codes: list[str]) -> dict:
        """获取财务数据: 返回 {code: {table_name: DataFrame}}"""
        if not _XT_AVAILABLE:
            return {}
        return xtdata.get_financial_data(codes)

    def get_instrument_detail(self, code: str) -> dict:
        """
        获取合约基础信息

        参数:
            code: 股票代码，如 "000001.SZ"

        返回:
            dict: 合约详情，关键字段:
                - InstrumentName: 股票名称
                - OpenDate:       上市日期
        """
        if not _XT_AVAILABLE:
            return {}
        return xtdata.get_instrument_detail(code)

    def get_divid_factors(self, code: str) -> pd.DataFrame:
        """
        获取除权除息因子

        用于股票的前/后复权价格计算。

        参数:
            code: 股票代码

        返回:
            pd.DataFrame: 除权除息数据
        """
        if not _XT_AVAILABLE:
            return pd.DataFrame()
        return xtdata.get_divid_factors(code)

    def download_sector_data(self) -> None:
        """下载板块分类数据到本地缓存"""
        if not _XT_AVAILABLE:
            return
        xtdata.download_sector_data()

    def is_connected(self) -> bool:
        """
        检查当前实例是否处于已连接状态

        注意: 仅反映本对象的连接追踪状态，不检测底层 SDK 的实际连接

        返回:
            bool: 已连接返回 True
        """
        return self._connected

    def __enter__(self):
        self.connect()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.disconnect()
        return False
