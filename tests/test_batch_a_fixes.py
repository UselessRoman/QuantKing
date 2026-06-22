# -*- coding: utf-8 -*-
"""
批次 A 修复的回归测试

覆盖三处修复的核心契约，按依赖最小化原则设计:
    - #2 qlib_converter:   纯 numpy+pandas 可端到端验证二进制格式
    - #1 bt_analyzer:      纯算法（回撤/夏普/交易统计）不依赖 backtrader 即可验证
    - #1/#6 runner/strategy: 依赖 backtrader，用 skipif 守护，真实环境运行

不依赖 xtquant / qlib / backtrader 的部分用标准 pytest 断言；
依赖 backtrader 的部分自动跳过，避免在精简环境误报。
"""
import struct
import math
import numpy as np
import pandas as pd
import pytest
from pathlib import Path

import sys
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

# backtrader 可选
try:
    import backtrader  # noqa: F401
    _BT_AVAILABLE = True
except ImportError:
    _BT_AVAILABLE = False


# ════════════════════════════════════════════════════════════
# #2 qlib 二进制格式修复
# ════════════════════════════════════════════════════════════

class TestQlibConverterFormat:
    """验证 qlib converter 产出的二进制格式符合 qlib 标准"""

    def _make_parquet(self, kline_dir: Path, code: str, dates_and_closes):
        """构造一只股票的 Parquet K线"""
        rows = []
        for date, close in dates_and_closes:
            rows.append({
                'code': code, 'date': date,
                'open': close, 'high': close + 0.5, 'low': close - 0.5,
                'close': close, 'volume': 10000.0, 'amount': close * 10000,
            })
        df = pd.DataFrame(rows)
        period_dir = kline_dir / '1d'
        period_dir.mkdir(parents=True, exist_ok=True)
        df.to_parquet(period_dir / f"{code}.parquet", index=False)

    def test_binary_is_pure_float32_aligned_to_calendar(self, tmp_path):
        """
        核心回归: .bin 必须是纯 float32 序列，长度 = 日历天数，
        且每只股票上市前/退市后/停牌日为 NaN（而非 0 或日期整数）。
        """
        from data.qlib_converter import convert_kline_to_qlib_format, validate_qlib_data

        kline_dir = tmp_path / "kline"
        qlib_dir = tmp_path / "qlib_data"

        # 股票 A: 3 个交易日（2023-01-03/04/05）
        self._make_parquet(kline_dir, '000001.SZ', [
            ('20230103', 10.0), ('20230104', 10.5), ('20230105', 11.0),
        ])
        # 股票 B: 与 A 错开的交易日（2023-01-04/05/06），制造日历并集
        self._make_parquet(kline_dir, '600000.SH', [
            ('20230104', 20.0), ('20230105', 21.0), ('20230106', 22.0),
        ])

        n = convert_kline_to_qlib_format(
            parquet_dir=str(kline_dir), output_dir=str(qlib_dir), period='1d')
        assert n == 2

        # 日历应为 4 个交易日的并集（0103/0104/0105/0106），ISO 格式
        cal = (qlib_dir / "calendars" / "day.txt").read_text(encoding='utf-8').split('\n')
        cal = [c for c in cal if c.strip()]
        assert cal == ['2023-01-03', '2023-01-04', '2023-01-05', '2023-01-06']

        # 读取股票 A 的 close.bin，校验格式
        bin_path = qlib_dir / "features" / "000001.SZ" / "close.1d.bin"
        assert bin_path.exists()
        raw = bin_path.read_bytes()
        # 长度 = 4 (日历天数) * 4 字节，绝不能再是 8 字节/条
        assert len(raw) == 4 * 4, f"bin 长度应为 16 字节，实际 {len(raw)}"
        arr = np.frombuffer(raw, dtype='<f4')
        assert len(arr) == 4

        # A 在 01-03 有值，01-06（不在其交易日里）应为 NaN
        assert arr[0] == pytest.approx(10.0)
        assert math.isnan(arr[3]), "日历对齐：缺失日必须是 NaN 而非 0"

    def test_validate_detects_old_broken_format(self, tmp_path):
        """validate 应能识别旧版损坏格式（int32+float32）"""
        from data.qlib_converter import validate_qlib_data

        qdir = tmp_path / "qlib_data"
        (qdir / "calendars").mkdir(parents=True)
        (qdir / "instruments").mkdir()
        feat = qdir / "features" / "000001.SZ"
        feat.mkdir(parents=True)

        # 写一个真实的日历
        (qdir / "calendars" / "day.txt").write_text(
            "2023-01-03\n2023-01-04\n2023-01-05\n2023-01-06\n", encoding='utf-8')
        (qdir / "instruments" / "all.txt").write_text(
            "000001.SZ\t2023-01-03\t2023-01-06\n", encoding='utf-8')

        # 故意写旧格式: 每条 int32(date)+float32(value) → 32 字节 ≠ 日历 4 天
        with open(feat / "close.1d.bin", 'wb') as f:
            for d in (20230103, 20230104, 20230105, 20230106):
                f.write(struct.pack('<i', d))
                f.write(struct.pack('<f', 10.0))

        result = validate_qlib_data(str(qdir))
        assert result["calendars"] == 4
        assert any("记录数" in e or "4 的倍数" in e for e in result["errors"]), \
            f"应检测出旧格式未对齐，errors={result['errors']}"

    def test_normalize_date_formats(self):
        from data.qlib_converter import _normalize_date
        assert _normalize_date('20230103') == '2023-01-03'
        assert _normalize_date(20230103) == '2023-01-03'
        assert _normalize_date('2023-01-03') == '2023-01-03'
        assert _normalize_date('') == ''
        assert _normalize_date(None) == ''


# ════════════════════════════════════════════════════════════
# #1 BacktestAnalyzer 纯算法（不依赖 backtrader）
# ════════════════════════════════════════════════════════════

class TestAnalyzerAlgorithms:
    """验证 analyzer 的纯算法函数，无需 backtrader"""

    def test_max_drawdown(self):
        from backtest.bt_analyzer import BacktestAnalyzer
        a = BacktestAnalyzer()
        # 1.0 → 0.8（回撤 20%）→ 1.2
        eq = pd.Series([1.0, 0.9, 0.8, 0.85, 0.95, 1.2])
        assert a._calc_max_drawdown(eq) == pytest.approx(0.2, rel=0.01)

    def test_max_drawdown_empty(self):
        from backtest.bt_analyzer import BacktestAnalyzer
        a = BacktestAnalyzer()
        assert a._calc_max_drawdown(pd.Series(dtype=float)) == 0.0
        assert a._calc_max_drawdown(None) == 0.0

    def test_sharpe_zero_variance(self):
        from backtest.bt_analyzer import BacktestAnalyzer
        a = BacktestAnalyzer()
        assert a._calc_sharpe(pd.Series([1.0, 1.0, 1.0, 1.0])) == 0.0

    def test_sharpe_too_short(self):
        from backtest.bt_analyzer import BacktestAnalyzer
        a = BacktestAnalyzer()
        assert a._calc_sharpe(pd.Series([1.0])) == 0.0
        assert a._calc_sharpe(None) == 0.0

    def test_trade_stats_with_pnl(self):
        from backtest.bt_analyzer import BacktestAnalyzer
        a = BacktestAnalyzer()
        trades = [
            {'pnl': 100}, {'pnl': -50}, {'pnl': 200}, {'pnl': -100},
        ]
        win_rate, pl_ratio, total = a._calc_trade_stats(trades)
        assert total == 4
        assert win_rate == 0.5
        # 平均盈利 (100+200)/2=150, 平均亏损 (50+100)/2=75 → 比值 2.0
        assert pl_ratio == pytest.approx(2.0, rel=0.01)

    def test_trade_stats_transactions_mode_no_pnl(self):
        """Transactions analyzer 模式无 pnl 字段，应只返回笔数不报错"""
        from backtest.bt_analyzer import BacktestAnalyzer
        a = BacktestAnalyzer()
        trades = [{'symbol': 'A', 'size': 100, 'price': 10.0}]
        win_rate, pl_ratio, total = a._calc_trade_stats(trades)
        assert total == 1
        assert win_rate == 0.0

    def test_trade_stats_empty(self):
        from backtest.bt_analyzer import BacktestAnalyzer
        a = BacktestAnalyzer()
        assert a._calc_trade_stats([]) == (0.0, 0.0, 0)

    def test_equity_reconstruction_from_daily_returns(self):
        """
        验证净值曲线由日收益率累乘还原（TimeReturn 路径的核心逻辑）
        """
        from backtest.bt_analyzer import BacktestAnalyzer
        a = BacktestAnalyzer()
        initial = 100000.0

        # 构造一个假的 strat，模拟 TimeReturn analyzer 输出
        # 类名必须是 'TimeReturn' 才能被 analyzer 识别
        class TimeReturn:
            def get_analysis(self):
                return {pd.Timestamp('2023-01-03'): 0.01,
                        pd.Timestamp('2023-01-04'): 0.02,
                        pd.Timestamp('2023-01-05'): -0.01}

        class _FakeStrat:
            analyzers = [TimeReturn()]

        equity = a._equity_from_strategy(_FakeStrat(), initial)
        # 100000 * 1.01 * 1.02 * 0.99
        expected = initial * 1.01 * 1.02 * 0.99
        assert equity is not None
        assert len(equity) == 3
        assert equity.iloc[-1] == pytest.approx(expected, rel=1e-6)

    def test_format_report_contains_expected_fields(self):
        from backtest.bt_analyzer import BacktestAnalyzer
        a = BacktestAnalyzer()
        result = {
            'total_return': 0.15, 'annual_return': 0.10,
            'max_drawdown': 0.08, 'sharpe_ratio': 1.5,
            'win_rate': 0.55, 'profit_loss_ratio': 1.8,
            'total_trades': 120, 'trading_days': 252,
            'final_value': 115000,
        }
        report = a.format_report(result)
        assert '15.00%' in report
        assert '1.50' in report


# ════════════════════════════════════════════════════════════
# #6 QlibSignalStrategy 信号注入（依赖 backtrader）
# ════════════════════════════════════════════════════════════

@pytest.mark.skipif(not _BT_AVAILABLE, reason="backtrader 未安装")
class TestQlibSignalInjection:
    """验证 qlib 信号策略通过 params 注入并实际产生交易"""

    def test_strategy_accepts_signals_via_params(self):
        """策略必须能通过 params.signals 接收信号（而非依赖 set_signals）"""
        from backtest.bt_strategy import QlibSignalStrategy
        import backtrader as bt

        cerebro = bt.Cerebro()
        # 构造一段合成 K 线数据
        dates = pd.date_range('2023-01-03', periods=30, freq='B')
        df = pd.DataFrame({
            'date': dates.strftime('%Y%m%d'),
            'open': np.linspace(10, 12, 30),
            'high': np.linspace(10.5, 12.5, 30),
            'low': np.linspace(9.5, 11.5, 30),
            'close': np.linspace(10, 12, 30),
            'volume': np.full(30, 1000000.0),
        })
        feed = bt.feeds.PandasData(
            dataname=df.assign(datetime=dates).set_index('datetime'),
            open='open', high='high', low='low', close='close', volume='volume',
            openinterest=-1)
        feed._name = '000001.SZ'
        cerebro.adddata(feed)
        cerebro.broker.setcash(1_000_000)

        # 通过 params 注入信号：第 1 个交易日 000001.SZ 入选
        cerebro.addstrategy(
            QlibSignalStrategy,
            signals={'20230103': ['000001.SZ']},
            top_k=1, rebalance_freq=1,
        )

        # 挂载 analyzer 用于验证交易发生
        cerebro.addanalyzer(bt.analyzers.Transactions, _name='transactions')
        # 注意：cerebro.run() 只能调用一次。旧测试调了两次，第二次 run 会在
        # 已结束的 broker 状态上继续，行为未定义。
        strat = cerebro.run()[0]
        txns = strat.analyzers.transactions.get_analysis()
        n_deals = sum(len(v) for v in txns.values())
        assert n_deals > 0, "信号已通过 params 注入，策略应当产生买入交易"


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
