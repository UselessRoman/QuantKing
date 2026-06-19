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
    通过 register_strategy 装饰器将策略注册到 STRATEGY_REGISTRY，
    即可被回测引擎、策略执行器和 Web 接口发现与调用。
"""
from .alpha_factors import FactorHandler
from .qlib_model import QlibTrainer
from .signal_generator import SignalGenerator
from .base import BaseStrategy, Signal

# 全局策略注册表：策略名 → 策略类
STRATEGY_REGISTRY: dict[str, type] = {}


def register_strategy(cls: type) -> type:
    """
    策略注册装饰器

    自动将策略类注册到全局注册表中。策略类必须定义 name 属性。

    使用示例:
        @register_strategy
        class MACrossStrategy(BaseStrategy):
            name = "ma_cross"
    """
    STRATEGY_REGISTRY[cls.name] = cls
    return cls
