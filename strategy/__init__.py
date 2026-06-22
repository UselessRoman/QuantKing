# -*- coding: utf-8 -*-
"""
策略引擎层模块

基于 qlib 框架的多因子策略开发，包括因子计算、模型训练与信号生成。

组件:
    FactorHandler    — qlib 因子处理器（Alpha158 + 自定义因子表达式）
    QlibTrainer      — qlib 模型训练器（LightGBM 等）
    SignalGenerator  — 选股信号生成器（Top-K / 阈值过滤 / 行业中性化）
    BaseStrategy     — 策略抽象基类（实盘执行兼容接口）
    Signal           — 交易信号数据类

策略注册:
    统一使用 strategy.registry 作为唯一注册中心，按命名空间组织：
        REGISTRY["bt"]   — backtrader 回测策略
        REGISTRY["live"] — 实盘 BaseStrategy 策略
    通过 register_strategy 装饰器注册，即可被回测引擎、执行器和 Web 发现。
"""
from .alpha_factors import FactorHandler
from .qlib_model import QlibTrainer
from .signal_generator import SignalGenerator
from .base import BaseStrategy, Signal

# 统一从 registry 再导出，避免出现第二套 STRATEGY_REGISTRY
from .registry import REGISTRY, register_strategy, get_strategy, list_strategies
