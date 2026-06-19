# -*- coding: utf-8 -*-
"""
风险控制管理模块

提供统一的风险控制接口，在交易执行前进行多维度的风险评估。

风险检查维度:
    1. 资金风险:  单笔订单资金占比、日亏损限制
    2. 持仓风险:  单只股票持仓上限、总持仓数量限制
    3. 市场风险:  涨跌停检查、流动性检查
    4. 熔断机制:  日亏损/最大回撤触发自动暂停交易

使用方式:
    from risk.risk_manager import RiskManager

    rm = RiskManager()
    ok, reason = rm.check_buy(code="000001.SZ", price=12.5, volume=1000, cash=50000)
    if not ok:
        print(f"买入被拒绝: {reason}")
"""
import time
import threading
from datetime import datetime
from typing import Optional, Tuple
from config.settings import RISK_CONFIG


class RiskManager:
    """
    统一风险控制管理器

    在每笔交易执行前进行风险检查，防止超出预设的风险阈值。
    所有涉及状态变更的方法均为线程安全。

    属性:
        config:          风险控制参数配置
        daily_pnl:       当日累计盈亏
        daily_trade_count: 当日交易次数
        start_equity:    当日起始权益
        _meltdown:       是否已触发熔断
        _last_check_time: 上次检查时间
    """

    def __init__(self, config: dict = None):
        """
        参数:
            config: 风险控制参数，默认使用 settings.RISK_CONFIG
        """
        self.config = config or RISK_CONFIG
        self.daily_pnl: float = 0.0
        self.daily_trade_count: int = 0
        self.start_equity: float = 0.0
        self._meltdown: bool = False
        self._meltdown_reason: str = ""
        self._last_check_time: datetime = datetime.now()
        self._current_date: str = ""
        self._lock = threading.Lock()

    def reset_daily(self, equity: float, date: str = ""):
        """
        每日重置风险计数器

        应在每个交易日开始时调用。

        参数:
            equity: 当日起始总资产
            date:   当前日期
        """
        with self._lock:
            self.daily_pnl = 0.0
            self.daily_trade_count = 0
            self.start_equity = equity
            self._meltdown = False
            self._meltdown_reason = ""
            if date and date != self._current_date:
                self._current_date = date

    def check_buy(
        self,
        code: str,
        price: float,
        volume: int,
        cash: float,
        positions: dict[str, dict],
        prev_close: float = 0,
    ) -> Tuple[bool, str]:
        """
        买入前风险检查

        参数:
            code:       股票代码
            price:      买入价格
            volume:     买入数量
            cash:       当前可用资金
            positions:  当前持仓 {code: {volume, ...}}
            prev_close: 前收盘价

        返回:
            Tuple[bool, str]: (是否通过, 拒绝原因)
        """
        if self._meltdown:
            return False, f"熔断已触发: {self._meltdown_reason}"

        # 1. 涨跌停检查
        if prev_close > 0:
            limit_up = round(prev_close * 1.1, 2)
            if price >= limit_up:
                return False, f"涨停价无法买入 (涨停价={limit_up})"

        # 2. 单笔金额占比检查
        order_amount = price * volume
        order_ratio = order_amount / cash if cash > 0 else 1.0
        max_ratio = self.config.get("max_single_order_ratio", 0.2)
        if order_ratio > max_ratio:
            return False, f"单笔金额占比超限 ({order_ratio:.1%} > {max_ratio:.1%})"

        # 3. 资金充足检查
        commission = max(order_amount * 0.00025, 5.0)
        total_cost = order_amount + commission
        if total_cost > cash:
            return False, f"资金不足 (需要 {total_cost:.2f}, 可用 {cash:.2f})"

        # 4. 单只股票持仓上限
        max_pos = self.config.get("max_position_per_stock", 100000)
        current_volume = positions.get(code, {}).get('volume', 0)
        if current_volume + volume > max_pos:
            return False, f"单只股票持仓超限 ({code} 将达到 {current_volume + volume} > {max_pos})"

        # 5. 总持仓数量限制
        max_holdings = self.config.get("max_holdings_count", 50)
        if code not in positions and len(positions) >= max_holdings:
            return False, f"持仓数量已达上限 ({max_holdings})"

        return True, "OK"

    def check_sell(
        self,
        code: str,
        volume: int,
        positions: dict[str, dict],
        prev_close: float = 0,
        buy_date: str = "",
        current_date: str = "",
    ) -> Tuple[bool, str]:
        """
        卖出前风险检查

        参数:
            code:         股票代码
            volume:       卖出数量
            positions:    当前持仓
            prev_close:   前收盘价
            buy_date:     买入日期（用于 T+1 检查）
            current_date: 当前日期

        返回:
            Tuple[bool, str]: (是否通过, 拒绝原因)
        """
        if self._meltdown:
            return False, f"熔断已触发: {self._meltdown_reason}"

        # 1. 跌停检查（由调用方在外部完成）

        # 2. 持仓检查
        pos = positions.get(code)
        if pos is None:
            return False, f"未持有 {code}"

        if pos.get('volume', 0) < volume:
            return False, f"持仓不足 ({code}: 持有 {pos.get('volume', 0)} < 卖出 {volume})"

        # 3. T+1 检查
        if buy_date and current_date and buy_date == current_date:
            return False, f"T+1 限制: {code} 当日买入不可卖出"

        return True, "OK"

    def check_market(self, price: float, prev_close: float,
                     is_buy: bool = True) -> Tuple[bool, str]:
        """
        涨跌停市场规则检查

        参数:
            price:      当前价格
            prev_close: 前收盘价
            is_buy:     True=买入检查, False=卖出检查

        返回:
            Tuple[bool, str]: (是否可交易, 原因)
        """
        if prev_close <= 0:
            return True, "OK"

        if is_buy:
            limit = round(prev_close * 1.1, 2)
            if price >= limit:
                return False, f"涨停 ({price} >= {limit})"
        else:
            limit = round(prev_close * 0.9, 2)
            if price <= limit:
                return False, f"跌停 ({price} <= {limit})"

        return True, "OK"

    def update_daily_pnl(self, trade_pnl: float):
        """
        更新当日累计盈亏

        参数:
            trade_pnl: 单笔交易盈亏
        """
        with self._lock:
            self.daily_pnl += trade_pnl
            self.daily_trade_count += 1

    def check_daily_loss(self, current_equity: float) -> Tuple[bool, str]:
        """
        检查日亏损是否触发熔断

        参数:
            current_equity: 当前总资产

        返回:
            Tuple[bool, str]: (是否正常, 熔断原因)
        """
        with self._lock:
            if self.start_equity <= 0:
                return True, "OK"

            daily_loss_ratio = (self.start_equity - current_equity) / self.start_equity
            max_daily_loss = self.config.get("max_daily_loss_ratio", 0.05)

            if daily_loss_ratio >= max_daily_loss:
                self._meltdown = True
                self._meltdown_reason = f"日亏损触发熔断 ({daily_loss_ratio:.2%} >= {max_daily_loss:.2%})"
                return False, self._meltdown_reason

            return True, "OK"

    def check_drawdown(self, peak_equity: float, current_equity: float) -> Tuple[bool, str]:
        """
        检查最大回撤是否触发熔断

        参数:
            peak_equity:    历史最高资产
            current_equity: 当前资产

        返回:
            Tuple[bool, str]: (是否正常, 熔断原因)
        """
        with self._lock:
            if peak_equity <= 0:
                return True, "OK"

            dd = (peak_equity - current_equity) / peak_equity
            max_dd = self.config.get("max_drawdown_ratio", 0.20)

            if dd >= max_dd:
                self._meltdown = True
                self._meltdown_reason = f"最大回撤触发熔断 ({dd:.2%} >= {max_dd:.2%})"
                return False, self._meltdown_reason

            return True, "OK"

    def is_meltdown(self) -> bool:
        """检查是否处于熔断状态"""
        with self._lock:
            return self._meltdown

    def reset_meltdown(self):
        """手动重置熔断状态（需要人工确认）"""
        with self._lock:
            self._meltdown = False
            self._meltdown_reason = ""
        print("熔断状态已手动重置")

    def get_risk_summary(self) -> dict:
        """获取当前风险状态摘要"""
        with self._lock:
            return {
                "meltdown": self._meltdown,
                "meltdown_reason": self._meltdown_reason,
                "daily_pnl": round(self.daily_pnl, 2),
                "daily_trade_count": self.daily_trade_count,
                "start_equity": round(self.start_equity, 2),
                "daily_pnl_ratio": round(self.daily_pnl / self.start_equity, 4)
                    if self.start_equity > 0 else 0,
            }
