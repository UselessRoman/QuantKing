# -*- coding: utf-8 -*-
"""交易模块测试（TraderManager mock 测试）"""
import pytest
from dataclasses import dataclass


# 模拟 XTquant 不可用时的行为
class TestAccountConfig:
    """账号配置测试"""

    def test_create_config(self):
        from trading.xt_trader import AccountConfig
        config = AccountConfig(
            id="test", label="测试", miniqmt_path="/tmp",
            account_id="123456", account_type="STOCK"
        )
        assert config.id == "test"
        assert config.account_type == "STOCK"


class TestTraderManagerWithoutXT:
    """XTquant 不可用时 TraderManager 的行为"""

    def test_connect_all_no_xt(self):
        """XTquant 未安装时应优雅降级"""
        from trading.xt_trader import TraderManager
        import trading.xt_trader as tm_mod

        # 模拟 xtquant 不可用
        saved = tm_mod._XT_TRADER_AVAILABLE
        tm_mod._XT_TRADER_AVAILABLE = False
        try:
            manager = TraderManager()
            results = manager.connect_all(accounts=[])
            assert results == {}

            # 未连接时查询应返回空/None
            assert manager.query_positions("nonexistent") == []
            assert manager.query_asset("nonexistent") is None
            assert not manager.is_connected("nonexistent")
        finally:
            tm_mod._XT_TRADER_AVAILABLE = saved

    def test_get_connected_accounts(self):
        """已连接账号列表"""
        from trading.xt_trader import TraderManager
        manager = TraderManager()
        connected = manager.get_connected_accounts()
        assert isinstance(connected, list)
        assert len(connected) == 0  # 初始无连接


class TestStrategyExecutor:
    """策略执行器测试"""

    def test_set_stock_list(self):
        import trading.xt_trader as tm_mod
        from trading.executor import StrategyExecutor
        from trading.xt_trader import TraderManager
        from strategy.base import BaseStrategy, Signal

        class DummyStrategy(BaseStrategy):
            name = "dummy"
            def init(self, context): pass
            def on_bar(self, index): return []
            def get_params_info(self): return {}

        saved = tm_mod._XT_TRADER_AVAILABLE
        tm_mod._XT_TRADER_AVAILABLE = False
        try:
            tm = TraderManager()
            executor = StrategyExecutor("test", DummyStrategy, tm)
            executor.set_stock_list(["000001.SZ", "600000.SH"])
            assert executor._stock_list == ["000001.SZ", "600000.SH"]
            assert executor.strategy_name == "dummy"
        finally:
            tm_mod._XT_TRADER_AVAILABLE = saved


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
