# -*- coding: utf-8 -*-
"""策略引擎层测试"""
import pytest
import pandas as pd
import numpy as np
from strategy.signal_generator import SignalGenerator
from strategy.alpha_factors import FACTOR_META, QLIB_FACTOR_NAMES, QLIB_FACTOR_EXPRESSIONS


class TestSignalGenerator:
    """信号生成器测试"""

    def test_generate_top_k_basic(self):
        sg = SignalGenerator()
        predictions = pd.Series(
            [0.8, 0.5, 0.9, 0.1, 0.7, 0.3],
            index=['A', 'B', 'C', 'D', 'E', 'F']
        )
        result = sg.generate(predictions, top_k=3)
        assert len(result) == 3
        assert result.iloc[0]['code'] == 'C'  # 最高分 0.9
        assert result.iloc[0]['score'] == 0.9

    def test_generate_with_min_score(self):
        sg = SignalGenerator()
        predictions = pd.Series(
            [0.8, 0.5, 0.9, 0.1, 0.7],
            index=['A', 'B', 'C', 'D', 'E']
        )
        result = sg.generate(predictions, top_k=5, min_score=0.6)
        assert len(result) == 3  # A, C, E 超过 0.6

    def test_generate_empty(self):
        sg = SignalGenerator()
        result = sg.generate(pd.Series(dtype=float), top_k=10)
        assert result.empty

    def test_generate_with_risk_control(self):
        sg = SignalGenerator()
        predictions = pd.Series(
            [0.8, 0.5, 0.9, 0.1, 0.7],
            index=['A', 'B', 'C', 'D', 'E']
        )
        positions = {'B': {'volume': 100}, 'D': {'volume': 200}}

        orders = sg.generate_with_risk_control(
            predictions, positions, top_k=2, max_turnover=1.0
        )

        # 选股: C(0.9), A(0.8); 持仓: B, D
        # BUY: C, A; SELL: B, D
        assert orders['C'] == 'BUY'
        assert orders['A'] == 'BUY'
        assert orders['B'] == 'SELL'
        assert orders['D'] == 'SELL'


class TestFactorMeta:
    """因子元信息测试"""

    def test_factor_count(self):
        assert len(FACTOR_META) == 22

    def test_factor_categories(self):
        categories = set(v['category'] for v in FACTOR_META.values())
        assert '动量' in categories
        assert '波动率' in categories
        assert '量价' in categories
        assert '技术指标' in categories

    def test_qlib_factor_expressions(self):
        # qlib 因子必须与 pandas 模式 FACTOR_META 的 22 个完全对齐，
        # 否则两模式特征不一致，模型切换会错位。
        assert len(QLIB_FACTOR_NAMES) == 22
        assert len(QLIB_FACTOR_EXPRESSIONS) == 22
        assert set(QLIB_FACTOR_NAMES) == set(FACTOR_META.keys())


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
