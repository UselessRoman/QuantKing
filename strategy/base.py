# -*- coding: utf-8 -*-
"""
策略基类模块

提供 BaseStrategy 和 Signal 接口，定义策略的标准生命周期。
兼容 trading/executor.py 的实盘执行流程。

信号接口:
    Signal: 交易信号数据类（action, symbol, price, volume）
    BaseStrategy: 策略抽象基类（init / on_bar / get_params_info）

使用方式:
    from strategy.base import BaseStrategy, Signal

    class MyStrategy(BaseStrategy):
        name = "my_strategy"
        params = {"param1": 10}

        def init(self, context):
            ...

        def on_bar(self, index):
            return [Signal("BUY", "000001.SZ", 10.0, 100)]
"""
from dataclasses import dataclass


@dataclass
class Signal:
    """
    交易信号

    表示策略在某根K线上产生的一个交易意图。
    信号本身不触发实际下单，由执行层统一处理。

    属性:
        action: "BUY" / "SELL" / "HOLD"
        symbol: 股票代码
        price:  目标价格
        volume: 目标数量（股）
    """
    action: str
    symbol: str
    price: float
    volume: int


class BaseStrategy:
    """
    策略基类

    所有实盘策略的抽象基类，定义了策略的标准生命周期:
        1. 实例化
        2. init(context) — 初始化，完成指标预计算
        3. on_bar(index) — 逐根K线回调，返回信号列表

    子类必须覆盖:
        - init(context)
        - on_bar(index) -> list[Signal]
        - get_params_info() -> dict

    类属性:
        name:   策略唯一标识
        params: 默认参数字典
    """
    name: str = ""
    params: dict = {}

    def init(self, context: dict) -> None:
        """策略初始化，context 必须包含 'kline' 字段（K线 DataFrame）"""
        raise NotImplementedError

    def on_bar(self, index: int) -> list[Signal]:
        """逐根K线回调，返回信号列表"""
        raise NotImplementedError

    def get_params_info(self) -> dict:
        """返回参数中文说明"""
        raise NotImplementedError
