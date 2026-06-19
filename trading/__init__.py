# -*- coding: utf-8 -*-
"""
交易执行层模块

提供实盘交易接口封装和策略执行调度。

组件:
    TraderManager    — 实盘交易管理器（XTquant 交易接口封装）
    StrategyExecutor — 策略执行器（行情→策略→风控→下单→记录）
"""
from .xt_trader import TraderManager, AccountConfig
from .executor import StrategyExecutor
