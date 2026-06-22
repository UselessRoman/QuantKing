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

    信号注入方式（重要）:
        backtrader 在 cerebro.run() 时自行实例化策略，外部无法在实例化后
        再调用方法注入数据。因此信号必须通过 params 在 addstrategy 时传入：

            cerebro.addstrategy(
                QlibSignalStrategy,
                signals={'20230103': ['000001.SZ', ...]},  # {date_str: [codes]}
                codes=['000001.SZ', ...],                  # 可选，股票池
                top_k=20, rebalance_freq=20,
            )

        推荐使用 BacktestRunner.run_qlib_signal() 一步到位。

    参数:
        signals:        选股信号 {date_str(YYYYMMDD): [股票代码]}
        codes:          可选股票池（用于校验/过滤）
        top_k:          持仓数量
        rebalance_freq: 调仓频率（交易日数），默认 20
    """
    params = (
        ('signals', None),
        ('codes', None),
        ('top_k', 20),
        ('rebalance_freq', 20),
    )

    def __init__(self):
        # 转为按整数日期排序的列表，便于按调仓日就近匹配
        raw = self.params.signals or {}
        self._signals: dict[str, list[str]] = {
            str(d): list(cs) for d, cs in raw.items()
        }
        self._sorted_signal_dates: list[str] = sorted(self._signals.keys())
        self._bar_count = 0
        self._buy_date: dict[str, str] = {}  # {code: buy_date} T+1 记录
        # 待确认买单: {order_ref: code}。
        # backtrader 的 buy() 是异步的，订单要等 notify_order 才知道是否成交。
        # 只有成交后才记 _buy_date；Margin/Rejected 的单子不能记，否则会
        # 错误触发 T+1 限制，并掩盖"资金不足未买"的事实。
        self._pending_buys: dict[int, str] = {}

    def set_signals(self, signals: dict):
        """
        ⚠ 兼容旧接口，运行期注入无效。

        backtrader 实例化策略发生在 cerebro.run() 内部，此方法在 run 之后
        调用无法影响已完成的回测。请改用 params（addstrategy(signals=...)）
        或 BacktestRunner.run_qlib_signal() 注入信号。
        """
        # 仍更新内部状态，便于单元测试构造场景
        self._signals = {str(d): list(cs) for d, cs in (signals or {}).items()}
        self._sorted_signal_dates = sorted(self._signals.keys())

    def set_codes(self, codes: list[str]):
        """设置股票池（兼容旧接口，建议通过 params.codes 传入）"""
        self.params.codes = codes

    def _is_rebalance_day(self) -> bool:
        """判断是否为调仓日"""
        return self._bar_count % self.params.rebalance_freq == 0

    def _get_target_codes(self, current_date: str) -> list[str]:
        """取当前日期及之前最近的信号日的选股列表。

        旧实现用 abs(int(d)-int(current_date)) 选最近信号日，会选到未来
        日期的信号（前视偏差）。这里改为只取 <= 当前日期的信号中最近的，
        没有则返回空（即建仓前不动）。
        """
        if not self._sorted_signal_dates:
            return []
        cur = int(current_date)
        # _sorted_signal_dates 已升序，取 <= cur 的最后一个
        past = [d for d in self._sorted_signal_dates if int(d) <= cur]
        if not past:
            return []
        closest_date = past[-1]
        return self._signals.get(closest_date, [])

    def next(self):
        self._bar_count += 1

        if not self._is_rebalance_day():
            return

        if not self._signals:
            return

        current_date = self.datas[0].datetime.date(0).strftime('%Y%m%d')
        target_codes = self._get_target_codes(current_date)
        if not target_codes:
            return

        # 计算等权资金：留出 buffer 给佣金/滑点/整百股取整上溢。
        # 旧实现 per_stock_value = total_value / top_k 在 top_k 较小或股价
        # 较高时，取整百股后买入金额会顶满甚至超过可用资金，backtrader 判定
        # Margin 拒单，导致策略静默不交易。0.98 的安全系数覆盖了佣金(万2.5)
        # + 滑点 + 取整上溢的余量。
        total_value = self.broker.getvalue()
        per_stock_value = total_value * 0.98 / self.params.top_k

        # 卖出不在目标池的持仓
        for data in self.datas:
            pos = self.getposition(data)
            code = data._name
            if pos.size > 0 and code not in target_codes:
                # T+1 检查：当日买入不可卖
                if self._buy_date.get(code) == current_date:
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
                # 按成交价的 1.01 倍估算 size，防止下一根开盘跳空导致 Margin
                size = int(per_stock_value / (price * 1.01) / 100) * 100
                if size >= 100:
                    order = self.buy(data=data, size=size)
                    self._pending_buys[order.ref] = code

    def notify_order(self, order):
        """订单状态回调：成交才记 T+1 日期，失败单子清理掉。

        backtrader 的 buy() 返回时订单尚未撮合，资金是否足够要等
        notify_order 的 Margin/Rejected 状态才知道。旧代码在 buy() 之后
        立即记 _buy_date，会掩盖资金不足未买的事实，并误触发 T+1 限制。
        """
        if order.status == order.Completed:
            code = self._pending_buys.pop(order.ref, None)
            if code is not None:
                current_date = self.datas[0].datetime.date(0).strftime('%Y%m%d')
                self._buy_date[code] = current_date
        elif order.status in (order.Margin, order.Rejected, order.Canceled):
            self._pending_buys.pop(order.ref, None)


# ─── 策略注册表 ───
# 统一使用 strategy.registry.REGISTRY["bt"] 作为唯一真相源，消除项目里
# 三套注册表（bt_strategy / strategy.__init__ / strategy.registry）的不一致。
# STRATEGY_REGISTRY 保留为 REGISTRY["bt"] 的引用，向后兼容现有 import。
from strategy.registry import REGISTRY as _REGISTRY

# 注册内置 backtrader 策略到 'bt' 命名空间
_REGISTRY["bt"].update({
    'ma_cross': MACrossStrategy,
    'macd': MACDStrategy,
    'rsi': RSIStrategy,
    'bollinger_bands': BollingerBandsStrategy,
    'turtle': TurtleStrategy,
    'qlib_signal': QlibSignalStrategy,
})

# 向后兼容：现有代码 `from backtest.bt_strategy import STRATEGY_REGISTRY`
# 指向同一字典对象，后续 register_strategy 装饰器注册的策略也会自动可见。
STRATEGY_REGISTRY = _REGISTRY["bt"]


def get_strategy(name: str) -> type:
    """通过名称获取策略类"""
    if name not in STRATEGY_REGISTRY:
        raise ValueError(f"未注册的策略: {name}，可用策略: {list(STRATEGY_REGISTRY.keys())}")
    return STRATEGY_REGISTRY[name]
