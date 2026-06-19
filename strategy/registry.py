# -*- coding: utf-8 -*-
"""
统一策略注册中心

消除 strategy/__init__.py 与 backtest/bt_strategy.py 中两套
独立 STRATEGY_REGISTRY 的重复定义。

注册表结构:
    {
        "bt": {           # backtrader 回测策略
            "ma_cross":    MACrossStrategy,
            "macd":        MACDStrategy,
            ...
        },
        "live": {         # 实盘 BaseStrategy 策略
            "my_strategy": MyStrategy,
            ...
        },
    }

使用方式:
    from strategy.registry import get_strategy, register_strategy

    # 回测
    bt_cls = get_strategy("bt", "ma_cross")
    cerebro.addstrategy(bt_cls)

    # 实盘
    live_cls = get_strategy("live", "my_strategy")
    executor = StrategyExecutor("real", live_cls, trader)
"""

REGISTRY: dict[str, dict[str, type]] = {
    "bt": {},
    "live": {},
}


def register_strategy(namespace: str = "live"):
    """
    策略注册装饰器工厂

    参数:
        namespace: "bt" 或 "live"

    使用示例:
        @register_strategy("live")
        class MyStrategy(BaseStrategy):
            name = "my_strategy"
            ...
    """
    def decorator(cls: type) -> type:
        name = getattr(cls, 'name', cls.__name__)
        REGISTRY.setdefault(namespace, {})[name] = cls
        return cls
    return decorator


def get_strategy(namespace: str, name: str) -> type:
    """
    获取注册的策略类

    参数:
        namespace: "bt" 或 "live"
        name:      策略名称

    抛出:
        KeyError: 策略未注册
    """
    if namespace not in REGISTRY:
        raise KeyError(f"未知的策略命名空间: {namespace}")
    if name not in REGISTRY[namespace]:
        raise KeyError(
            f"未注册的策略: {name} (命名空间: {namespace})，"
            f"可用: {list(REGISTRY[namespace].keys())}"
        )
    return REGISTRY[namespace][name]


def list_strategies(namespace: str = "") -> dict[str, type]:
    """列出指定命名空间的所有策略，namespace 为空则返回全部"""
    if namespace:
        return dict(REGISTRY.get(namespace, {}))
    result = {}
    for ns in REGISTRY:
        result.update(REGISTRY[ns])
    return result


def register_builtin_bt_strategies():
    """将 backtrader 内置策略注册到 'bt' 命名空间"""
    try:
        from backtest.bt_strategy import (
            MACrossStrategy, MACDStrategy, RSIStrategy,
            BollingerBandsStrategy, TurtleStrategy, QlibSignalStrategy,
        )
        REGISTRY["bt"].update({
            "ma_cross": MACrossStrategy,
            "macd": MACDStrategy,
            "rsi": RSIStrategy,
            "bollinger_bands": BollingerBandsStrategy,
            "turtle": TurtleStrategy,
            "qlib_signal": QlibSignalStrategy,
        })
    except ImportError:
        pass
