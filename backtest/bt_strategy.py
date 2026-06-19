# -*- coding: utf-8 -*-
"""
backtrader 策略模块

提供基于 backtrader 框架的策略实现，包括:
    - 标准技术指标策略（均线交叉、MACD、RSI 等）
    - qlib 信号驱动策略（组合选股调仓）

A 股规则:
    - T+1 交易制度（当日买入次日才能卖出）
    - 涨跌停限制（±10%，创业板/科创板 ±20%）
    - 最少交易 100 股（整百股）

使用方式:
    from backtest.bt_strategy import MACrossStrategy, QlibSignalStrategy

    cerebro.addstrategy(MACrossStrategy, fast=5, slow=20)
    cerebro.addstrategy(QlibSignalStrategy, signal_provider=sg, top_k=20)
"""
from datetime import datetime
import pandas as pd
import backtrader as bt


class MACrossStrategy(bt.Strategy):
    """
    均线交叉策略（backtrader 版本）

    金叉买入，死叉卖出。使用 backtrader 内置的 SMA 和 CrossOver 指标。
    对应旧项目的 strategies/ma_cross.py。

    参数:
        fast: 短期均线周期（默认5）
        slow: 长期均线周期（默认20）
    """
    params = (
        ('fast', 5),
        ('slow', 20),
    )

    def __init__(self):
        self.fast_ma = bt.indicators.SMA(self.data.close, period=self.params.fast)
        self.slow_ma = bt.indicators.SMA(self.data.close, period=self.params.slow)
        self.crossover = bt.indicators.CrossOver(self.fast_ma, self.slow_ma)
        self.order = None

    def next(self):
        if self.order:
            return

        if not self.position:
            if self.crossover > 0:
                self.order = self.buy()
        else:
            if self.crossover < 0:
                self.order = self.sell()

    def notify_order(self, order):
        if order.status in [order.Completed, order.Canceled, order.Margin]:
            self.order = None


class MACDStrategy(bt.Strategy):
    """
    MACD 策略（backtrader 版本）

    DIF 上穿 DEA 买入，DIF 下穿 DEA 卖出。
    对应旧项目的 strategies/macd.py。
    """
    params = (
        ('fast', 12),
        ('slow', 26),
        ('signal', 9),
    )

    def __init__(self):
        self.macd = bt.indicators.MACD(
            self.data.close,
            period_me1=self.params.fast,
            period_me2=self.params.slow,
            period_signal=self.params.signal
        )
        self.crossover = bt.indicators.CrossOver(self.macd.macd, self.macd.signal)
        self.order = None

    def next(self):
        if self.order:
            return
        if not self.position:
            if self.crossover > 0:
                self.order = self.buy()
        else:
            if self.crossover < 0:
                self.order = self.sell()

    def notify_order(self, order):
        if order.status in [order.Completed, order.Canceled, order.Margin]:
            self.order = None


class RSIStrategy(bt.Strategy):
    """
    RSI 超买超卖策略（backtrader 版本）

    RSI 低于 oversold 买入，高于 overbought 卖出。
    对应旧项目的 strategies/rsi.py。
    """
    params = (
        ('period', 14),
        ('oversold', 30),
        ('overbought', 70),
    )

    def __init__(self):
        self.rsi = bt.indicators.RSI(self.data.close, period=self.params.period)
        self.order = None

    def next(self):
        if self.order:
            return
        if not self.position:
            if self.rsi < self.params.oversold:
                self.order = self.buy()
        else:
            if self.rsi > self.params.overbought:
                self.order = self.sell()

    def notify_order(self, order):
        if order.status in [order.Completed, order.Canceled, order.Margin]:
            self.order = None


class BollingerBandsStrategy(bt.Strategy):
    """
    布林带策略（backtrader 版本）

    价格触及下轨买入，触及上轨卖出。
    对应旧项目的 strategies/bollinger_bands.py。
    """
    params = (
        ('period', 20),
        ('devfactor', 2.0),
    )

    def __init__(self):
        self.bb = bt.indicators.BollingerBands(
            self.data.close,
            period=self.params.period,
            devfactor=self.params.devfactor
        )
        self.order = None

    def next(self):
        if self.order:
            return
        if not self.position:
            if self.data.close < self.bb.lines.bot:
                self.order = self.buy()
        else:
            if self.data.close > self.bb.lines.top:
                self.order = self.sell()

    def notify_order(self, order):
        if order.status in [order.Completed, order.Canceled, order.Margin]:
            self.order = None


class TurtleStrategy(bt.Strategy):
    """
    海龟交易策略（backtrader 版本）

    突破 N 日高点买入，跌破 N 日低点卖出。
    对应旧项目的 strategies/turtle.py。
    """
    params = (
        ('entry_period', 20),
        ('exit_period', 10),
        ('atr_period', 20),
        ('risk_ratio', 0.02),
    )

    def __init__(self):
        self.entry_high = bt.indicators.Highest(self.data.high, period=self.params.entry_period)
        self.exit_low = bt.indicators.Lowest(self.data.low, period=self.params.exit_period)
        self.atr = bt.indicators.ATR(self.data, period=self.params.atr_period)
        self.order = None

    def next(self):
        if self.order:
            return
        if not self.position:
            if self.data.close > self.entry_high[-1]:
                self.order = self.buy()
        else:
            if self.data.close < self.exit_low:
                self.order = self.sell()

    def notify_order(self, order):
        if order.status in [order.Completed, order.Canceled, order.Margin]:
            self.order = None


# ─── qlib 信号驱动策略 ───

class QlibSignalStrategy(bt.Strategy):
    """
    qlib 信号驱动的组合选股策略

    在每个调仓日读取 qlib 预测信号，买入 Top-K 股票，
    卖出落选持仓。等权分配资金。

    参数:
        signal_provider: 信号生成器实例（SignalGenerator）
        top_k:           持仓数量
        rebalance_freq:  调仓频率（交易日数），默认 20
        codes:           可选股票池列表
    """
    params = (
        ('top_k', 20),
        ('rebalance_freq', 20),
    )

    def __init__(self):
        self._signals: dict = {}        # {date_str: [codes]}
        self._signal_provider = None
        self._codes = None
        self._bar_count = 0
        self._buy_date: dict[str, str] = {}  # {code: buy_date} T+1 记录

    def set_signals(self, signals: dict):
        """设置预先生成的选股信号 {date: [codes]}"""
        self._signals = signals

    def set_codes(self, codes: list[str]):
        """设置股票池"""
        self._codes = codes

    def _is_rebalance_day(self) -> bool:
        """判断是否为调仓日"""
        return self._bar_count % self.params.rebalance_freq == 0

    def next(self):
        self._bar_count += 1

        if not self._is_rebalance_day():
            return

        current_date = self.datas[0].datetime.date(0).strftime('%Y%m%d')

        # 获取当前信号的选股列表
        target_codes = []
        if self._signals:
            closest_date = min(self._signals.keys(),
                               key=lambda d: abs(int(d) - int(current_date)))
            target_codes = self._signals.get(closest_date, [])

        if not target_codes:
            return

        # 计算等权资金
        total_value = self.broker.getvalue()
        per_stock_value = total_value / len(target_codes)

        # 卖出不在目标池的持仓
        for data in self.datas:
            pos = self.getposition(data)
            code = data._name
            if pos.size > 0 and code not in target_codes:
                # T+1 检查
                if code in self._buy_date and self._buy_date[code] == current_date:
                    continue
                self.close(data=data)

        # 买入目标股票
        for data in self.datas:
            code = data._name
            if code not in target_codes:
                continue
            pos = self.getposition(data)
            if pos.size == 0:
                price = data.close[0]
                size = int(per_stock_value / price / 100) * 100
                if size >= 100:
                    self.buy(data=data, size=size)
                    self._buy_date[code] = current_date

    def notify_order(self, order):
        if order.status == order.Completed:
            pass


# ─── 策略注册表 ───

STRATEGY_REGISTRY = {
    'ma_cross': MACrossStrategy,
    'macd': MACDStrategy,
    'rsi': RSIStrategy,
    'bollinger_bands': BollingerBandsStrategy,
    'turtle': TurtleStrategy,
    'qlib_signal': QlibSignalStrategy,
}


def get_strategy(name: str) -> type:
    """通过名称获取策略类"""
    if name not in STRATEGY_REGISTRY:
        raise ValueError(f"未注册的策略: {name}，可用策略: {list(STRATEGY_REGISTRY.keys())}")
    return STRATEGY_REGISTRY[name]
