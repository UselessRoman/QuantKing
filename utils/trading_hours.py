# -*- coding: utf-8 -*-
"""
A 股交易时段判断工具

提供交易时段判断，避免实盘策略在非交易时段（夜间/午间/周末/节假日）
空转下单。节假日判断依赖自维护的节假日表（见 HOLIDAYS），需每年更新。

使用方式:
    from utils.trading_hours import is_trading_time, next_trading_seconds
    if is_trading_time():
        executor.run_once()
    else:
        time.sleep(next_trading_seconds())
"""
from datetime import datetime, time as dtime, timedelta

# A 股交易时段（北京时间）
MORNING_START = dtime(9, 30)
MORNING_END = dtime(11, 30)
AFTERNOON_START = dtime(13, 0)
AFTERNOON_END = dtime(15, 0)

# 自维护节假日表（YYYYMMDD）。需每年更新；若某日期在此集合中，即使
# 是工作日也不交易。这里只列已知节假日，缺失日期按工作日判断。
# TODO: 接入 exchange_calendars 或从交易所官方日历自动同步。
HOLIDAYS: set[str] = set()


def is_weekend(dt: datetime) -> bool:
    """判断是否周末"""
    return dt.weekday() >= 5


def is_holiday(dt: datetime) -> bool:
    """判断是否节假日（基于自维护表）"""
    return dt.strftime('%Y%m%d') in HOLIDAYS


def is_trading_day(dt: datetime = None) -> bool:
    """判断是否交易日（非周末且非节假日）"""
    dt = dt or datetime.now()
    return not is_weekend(dt) and not is_holiday(dt)


def is_trading_time(dt: datetime = None) -> bool:
    """判断当前是否处于 A 股交易时段内。

    交易时段（北京时间）：
        上午 09:30 - 11:30
        下午 13:00 - 15:00
    非交易日（周末/节假日）直接返回 False。
    """
    dt = dt or datetime.now()
    if not is_trading_day(dt):
        return False
    t = dt.time()
    in_morning = MORNING_START <= t <= MORNING_END
    in_afternoon = AFTERNOON_START <= t <= AFTERNOON_END
    return in_morning or in_afternoon


def next_trading_seconds(dt: datetime = None) -> int:
    """距下一个交易时段开始的秒数（用于 sleep）。

    若当前已在交易时段内返回 0；否则计算到下一个交易时段起点的秒数。
    为避免长时间 sleep 卡住无法响应停止信号，上限返回 60 秒
    （调用方循环 sleep，到点自然会进入交易时段）。
    """
    dt = dt or datetime.now()
    if is_trading_time(dt):
        return 0

    # 简化策略：非交易时段一律 sleep 较短时间（60秒），让循环快速重检。
    # 精确计算到下一个 09:30/13:00 的秒数意义不大，因为调用方是固定间隔
    # 循环；这里返回一个合理上限，避免单次 sleep 过久。
    return 60
