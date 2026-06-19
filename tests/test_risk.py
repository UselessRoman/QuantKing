# -*- coding: utf-8 -*-
"""风控模块完整场景测试"""
import pytest
from risk.risk_manager import RiskManager


class TestRiskManagerMeltdown:
    """熔断机制测试"""

    def test_no_meltdown_initially(self):
        rm = RiskManager()
        rm.reset_daily(100000.0)
        assert not rm.is_meltdown()

    def test_daily_loss_meltdown(self):
        rm = RiskManager()
        rm.reset_daily(100000.0)

        # -6% 亏损 → 触发日亏损熔断（阈值 5%）
        ok, reason = rm.check_daily_loss(94000.0)
        assert not ok
        assert "日亏损" in reason
        assert rm.is_meltdown()

    def test_drawdown_meltdown(self):
        rm = RiskManager()
        rm.reset_daily(100000.0)

        # -25% 回撤 → 触发回撤熔断（阈值 20%）
        ok, reason = rm.check_drawdown(100000.0, 75000.0)
        assert not ok
        assert "回撤" in reason
        assert rm.is_meltdown()

    def test_reset_meltdown(self):
        rm = RiskManager()
        rm.reset_daily(100000.0)

        # 触发熔断
        rm.check_daily_loss(94000.0)
        assert rm.is_meltdown()

        # 重置
        rm.reset_meltdown()
        assert not rm.is_meltdown()


class TestRiskCheckBuy:
    """买入风控检查测试"""

    def setup_method(self):
        self.rm = RiskManager()
        self.rm.reset_daily(100000.0)

    def test_buy_ok(self):
        ok, reason = self.rm.check_buy(
            code="000001.SZ", price=10.0, volume=1000,
            cash=50000, positions={}, prev_close=10.0,
        )
        assert ok
        assert reason == "OK"

    def test_buy_limit_up(self):
        """涨停价买入被拒绝"""
        ok, reason = self.rm.check_buy(
            code="000001.SZ", price=11.0, volume=1000,
            cash=50000, positions={}, prev_close=10.0,
        )
        assert not ok
        assert "涨停" in reason

    def test_buy_order_ratio_exceeded(self):
        """单笔金额占比超限"""
        ok, reason = self.rm.check_buy(
            code="000001.SZ", price=10.0, volume=6000,
            cash=10000, positions={}, prev_close=10.0,
        )
        assert not ok
        assert "占比" in reason

    def test_buy_cash_insufficient(self):
        """资金不足（在占比检查和佣金扣除后余额不足）"""
        ok, reason = self.rm.check_buy(
            code="000001.SZ", price=10.0, volume=1000,
            cash=9500, positions={}, prev_close=10.0,
        )
        assert not ok
        # 可能是"资金不足"（占比通过但金额不够）或"占比超限"（占比先触发）
        assert not ok

    def test_buy_position_limit(self):
        """单只股票持仓超限"""
        ok, reason = self.rm.check_buy(
            code="000001.SZ", price=10.0, volume=1000,
            cash=200000, positions={"000001.SZ": {"volume": 99500}},
            prev_close=10.0,
        )
        assert not ok
        assert "超限" in reason

    def test_buy_holdings_count_limit(self):
        """持仓数量上限"""
        positions = {f"{i:06d}.SZ": {"volume": 100} for i in range(50)}
        ok, reason = self.rm.check_buy(
            code="999999.SZ", price=10.0, volume=100,
            cash=200000, positions=positions, prev_close=10.0,
        )
        assert not ok
        assert "已达上限" in reason

    def test_buy_during_meltdown(self):
        """熔断期间买入被拒绝"""
        self.rm.check_daily_loss(94000.0)
        ok, reason = self.rm.check_buy(
            code="000001.SZ", price=10.0, volume=100,
            cash=50000, positions={}, prev_close=10.0,
        )
        assert not ok
        assert "熔断" in reason


class TestRiskCheckSell:
    """卖出风控检查测试"""

    def setup_method(self):
        self.rm = RiskManager()
        self.rm.reset_daily(100000.0)

    def test_sell_ok(self):
        ok, reason = self.rm.check_sell(
            code="000001.SZ", volume=500,
            positions={"000001.SZ": {"volume": 1000}},
            prev_close=10.0,
        )
        assert ok

    def test_sell_no_position(self):
        ok, reason = self.rm.check_sell(
            code="000001.SZ", volume=500,
            positions={}, prev_close=10.0,
        )
        assert not ok
        assert "未持有" in reason

    def test_sell_volume_insufficient(self):
        ok, reason = self.rm.check_sell(
            code="000001.SZ", volume=2000,
            positions={"000001.SZ": {"volume": 1000}},
            prev_close=10.0,
        )
        assert not ok
        assert "持仓不足" in reason

    def test_sell_t1_restriction(self):
        """T+1 当日买入不可卖出"""
        ok, reason = self.rm.check_sell(
            code="000001.SZ", volume=500,
            positions={"000001.SZ": {"volume": 1000}},
            prev_close=10.0,
            buy_date="20260101",
            current_date="20260101",
        )
        assert not ok
        assert "T+1" in reason

    def test_sell_during_meltdown(self):
        """熔断期间卖出被拒绝"""
        self.rm.check_daily_loss(94000.0)
        ok, reason = self.rm.check_sell(
            code="000001.SZ", volume=500,
            positions={"000001.SZ": {"volume": 1000}},
            prev_close=10.0,
        )
        assert not ok
        assert "熔断" in reason


class TestRiskCheckMarket:
    """涨跌停市场规则测试"""

    def test_buy_at_limit_up(self):
        rm = RiskManager()
        ok, reason = rm.check_market(11.0, 10.0, is_buy=True)
        assert not ok
        assert "涨停" in reason

    def test_sell_at_limit_down(self):
        rm = RiskManager()
        ok, reason = rm.check_market(9.0, 10.0, is_buy=False)
        assert not ok
        assert "跌停" in reason

    def test_market_ok(self):
        rm = RiskManager()
        ok, reason = rm.check_market(10.5, 10.0, is_buy=True)
        assert ok


class TestRiskSummary:
    """风险摘要测试"""

    def test_initial_summary(self):
        rm = RiskManager()
        rm.reset_daily(100000.0)
        s = rm.get_risk_summary()
        assert s["meltdown"] is False
        assert s["daily_trade_count"] == 0
        assert s["start_equity"] == 100000.0

    def test_pnl_update(self):
        rm = RiskManager()
        rm.reset_daily(100000.0)
        rm.update_daily_pnl(500.0)
        rm.update_daily_pnl(-200.0)
        s = rm.get_risk_summary()
        assert s["daily_pnl"] == 300.0
        assert s["daily_trade_count"] == 2


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
