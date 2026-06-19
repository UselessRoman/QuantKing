# -*- coding: utf-8 -*-
"""
回测系统层模块

基于 backtrader 框架的策略回测环境，集成 A 股市场规则。

组件:
    bt_strategy   — backtrader 策略适配器（标准策略 + qlib 信号驱动策略）
    bt_broker      — A 股佣金方案（佣金、印花税、过户费）
    bt_analyzer    — 回测绩效分析器（集成 quantstats）
    runner         — 回测执行器（一键运行入口）
"""
try:
    from .runner import BacktestRunner
except ImportError:
    BacktestRunner = None

try:
    from .bt_strategy import MACrossStrategy, QlibSignalStrategy
except ImportError:
    MACrossStrategy = None
    QlibSignalStrategy = None

try:
    from .bt_broker import AShareCommission
except ImportError:
    AShareCommission = None

try:
    from .bt_analyzer import BacktestAnalyzer
except ImportError:
    BacktestAnalyzer = None
