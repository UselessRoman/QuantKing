# -*- coding: utf-8 -*-
"""回测系统测试"""
import pytest
import pandas as pd
import numpy as np
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

# 检查 backtrader 是否可用
try:
    import backtrader
    _BT_AVAILABLE = True
except ImportError:
    _BT_AVAILABLE = False


class TestBacktestAnalyzer:
    """回测绩效分析器测试"""

    def test_empty_result(self):
        from backtest.bt_analyzer import BacktestAnalyzer
        analyzer = BacktestAnalyzer()
        result = analyzer._empty_result()
        assert result['total_return'] == 0
        assert result['total_trades'] == 0

    def test_max_drawdown(self):
        from backtest.bt_analyzer import BacktestAnalyzer
        analyzer = BacktestAnalyzer()
        equity = pd.Series([1.0, 0.9, 0.8, 0.85, 0.95, 1.05])
        dd = analyzer._calc_max_drawdown(equity)
        assert dd == pytest.approx(0.2, rel=0.01)  # (1.0 - 0.8) / 1.0

    def test_sharpe_zero_variance(self):
        from backtest.bt_analyzer import BacktestAnalyzer
        analyzer = BacktestAnalyzer()
        equity = pd.Series([1.0, 1.0, 1.0, 1.0])
        sharpe = analyzer._calc_sharpe(equity)
        assert sharpe == 0.0

    def test_format_report(self):
        from backtest.bt_analyzer import BacktestAnalyzer
        analyzer = BacktestAnalyzer()
        result = {
            'total_return': 0.15, 'annual_return': 0.10,
            'max_drawdown': 0.08, 'sharpe_ratio': 1.5,
            'win_rate': 0.55, 'profit_loss_ratio': 1.8,
            'total_trades': 120, 'trading_days': 252,
            'final_value': 115000,
        }
        report = analyzer.format_report(result)
        assert '15.00%' in report
        assert '1.50' in report


@pytest.mark.skipif(not _BT_AVAILABLE, reason="backtrader 未安装")
class TestBacktestBroker:
    """A股佣金方案测试（需要 backtrader）"""

    def test_commission_buy(self):
        """买入：佣金最低5元 + 过户费万0.1"""
        from backtest.bt_broker import AShareCommission
        comm = AShareCommission()
        cost = comm._getcommission(1000, 10.0, False)
        # 佣金 max(10000*0.00025, 5)=5，过户费 10000*0.00001=0.1
        assert cost == 5.1

    def test_commission_sell_with_stamp(self):
        """卖出：佣金5 + 印花税10 + 过户费0.1"""
        from backtest.bt_broker import AShareCommission
        comm = AShareCommission()
        cost = comm._getcommission(-1000, 10.0, False)
        # 佣金5 + 印花 10000*0.001=10 + 过户 0.1 = 15.1
        assert cost == 15.1

    def test_commission_min(self):
        """小额交易触发最低佣金 + 过户费"""
        from backtest.bt_broker import AShareCommission
        comm = AShareCommission()
        cost = comm._getcommission(100, 5.0, False)
        # 佣金 max(500*0.00025, 5)=5，过户费 500*0.00001=0.005
        assert cost == 5.005


@pytest.mark.skipif(not _BT_AVAILABLE, reason="backtrader 未安装")
class TestStrategyRegistry:
    """策略注册表测试"""

    def test_get_existing_strategy(self):
        from backtest.bt_strategy import get_strategy, STRATEGY_REGISTRY
        assert len(STRATEGY_REGISTRY) >= 5
        cls = get_strategy('ma_cross')
        assert cls.__name__ == 'MACrossStrategy'

    def test_get_nonexistent_strategy(self):
        from backtest.bt_strategy import get_strategy
        with pytest.raises(ValueError):
            get_strategy('nonexistent')


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
