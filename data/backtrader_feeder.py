# -*- coding: utf-8 -*-
"""
backtrader 数据源适配模块

将本地 Parquet K线数据加载为 backtrader 可识别的数据源。

使用方式:
    from data.database import Database
    from data.backtrader_feeder import load_bt_data

    db = Database()
    db.connect()
    df = db.get_daily_kline_df("000001.SZ", "1d", "20230101", "20231231")
    data = load_bt_data(df)
    cerebro.adddata(data)
    db.close()
"""
import pandas as pd
import backtrader as bt
from datetime import datetime


class XTQuantDataFeed(bt.feeds.PandasData):
    """
    backtrader 数据源适配器

    将已有 DataFrame K线数据包装为 backtrader PandasData。

    参数:
        dataname: pandas DataFrame，需包含 date/open/high/low/close/volume 列

    使用示例:
        df = db.get_daily_kline_df("000001.SZ", "1d", "20230101", "20231231")
        data = XTQuantDataFeed(dataname=df)
        cerebro.adddata(data)
    """
    params = (
        ('datetime', 0),       # 第 0 列作为时间索引（自动从 DataFrame index 取）
        ('open', 'open'),
        ('high', 'high'),
        ('low', 'low'),
        ('close', 'close'),
        ('volume', 'volume'),
        ('openinterest', -1),  # 无持仓量数据
    )

    def __init__(self):
        super().__init__()


def load_bt_data(df: pd.DataFrame, dtformat: str = '%Y%m%d') -> bt.feeds.PandasData:
    """
    将数据库 K线 DataFrame 转换为 backtrader 数据源

    对 DataFrame 做必要预处理后返回 PandasData 实例。

    参数:
        df:       K线 DataFrame，需含 date/open/high/low/close/volume 列
        dtformat: 日期格式字符串

    返回:
        bt.feeds.PandasData: backtrader 可用的数据源
    """
    if df.empty:
        return None

    # 复制以避免修改原数据
    df = df.copy()

    # 将 date 列转换为 datetime 并设为 index
    if 'date' in df.columns:
        df['datetime'] = pd.to_datetime(df['date'], format=dtformat, errors='coerce')
        df = df.set_index('datetime')

    # 确保所需列存在
    required_cols = ['open', 'high', 'low', 'close', 'volume']
    for col in required_cols:
        if col not in df.columns:
            raise ValueError(f"DataFrame 缺少必要列: {col}")

    return XTQuantDataFeed(dataname=df)


def load_multi_stock_data(
    db,
    codes: list[str],
    start_date: str = '',
    end_date: str = '',
    period: str = '1d'
) -> dict[str, bt.feeds.PandasData]:
    """
    批量加载多只股票的 backtrader 数据源

    参数:
        db:         Database 实例（需已连接）
        codes:      股票代码列表
        start_date: 起始日期，YYYYMMDD
        end_date:   结束日期，YYYYMMDD
        period:     K线周期

    返回:
        dict: {股票代码: bt.feeds.PandasData}
    """
    data_feeds = {}
    for code in codes:
        df = db.get_daily_kline_df(code, period, start_date, end_date)
        if df.empty:
            print(f"警告: {code} 无数据，跳过")
            continue
        feed = load_bt_data(df)
        if feed is not None:
            data_feeds[code] = feed
    return data_feeds
