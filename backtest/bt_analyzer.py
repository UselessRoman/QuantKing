# -*- coding: utf-8 -*-
"""
回测绩效分析模块（backtrader 版本）

集成 quantstats 库生成专业绩效报告，同时复用现有项目
backtest/analyzer.py 中的计算逻辑。

绩效指标:
    - 总收益率、年化收益率
    - 最大回撤
    - 夏普比率
    - 胜率、盈亏比
    - 净值曲线、回撤曲线
    - 月度收益率热力图（依赖 quantstats）

使用方式:
    from backtest.bt_analyzer import BacktestAnalyzer

    analyzer = BacktestAnalyzer()
    result = analyzer.analyze(cerebro, initial_capital)
    analyzer.generate_report(result, "report.html")
"""
import math
import pandas as pd
import numpy as np
from datetime import datetime


class BacktestAnalyzer:
    """
    回测绩效分析器

    从 backtrader 的 Cerebro 结果中提取并计算多种绩效指标。

    使用方式:
        analyzer = BacktestAnalyzer()
        performance = analyzer.analyze(cerebro, initial_capital=100000)
        print(analyzer.format_report(performance))
    """

    def analyze(self, cerebro, initial_capital: float = 100000) -> dict:
        """
        从 Cerebro 运行结果中提取绩效指标

        参数:
            cerebro:         backtrader.Cerebro 实例（需已执行 run()）
            initial_capital: 初始资金

        返回:
            dict: 完整绩效指标
        """
        try:
            # 获取净值曲线
            equity = self._get_equity_curve(cerebro)
        except Exception:
            equity = pd.Series()

        try:
            trades = self._get_trade_records(cerebro)
        except Exception:
            trades = []

        if equity.empty:
            return self._empty_result()

        # 基础指标
        total_return = equity.iloc[-1] / initial_capital - 1 if len(equity) > 0 else 0
        trading_days = len(equity)
        years = max(trading_days / 252, 1 / 252)
        annual_return = (1 + total_return) ** (1 / years) - 1 if total_return > -1 else 0

        # 最大回撤
        max_dd = self._calc_max_drawdown(equity / initial_capital)

        # 夏普比率
        sharpe = self._calc_sharpe(equity)

        # 交易统计
        win_rate, profit_loss_ratio, total_trades = self._calc_trade_stats(trades)

        # 净值曲线和回撤曲线
        equity_curve = {str(i): float(v / initial_capital) for i, v in enumerate(equity.values)}
        drawdown_curve = self._calc_drawdown_curve(equity / initial_capital)

        return {
            'total_return': round(total_return, 4),
            'annual_return': round(annual_return, 4),
            'max_drawdown': round(max_dd, 4),
            'sharpe_ratio': round(sharpe, 4),
            'win_rate': round(win_rate, 4),
            'profit_loss_ratio': round(profit_loss_ratio, 4),
            'total_trades': total_trades,
            'trading_days': trading_days,
            'final_value': round(float(equity.iloc[-1]), 2) if len(equity) > 0 else initial_capital,
            'equity_curve': equity_curve,
            'drawdown_curve': drawdown_curve,
            'trade_records': trades,
        }

    def _get_equity_curve(self, cerebro) -> pd.Series:
        """从 Cerebro 提取净值曲线"""
        try:
            stats = cerebro.run()
            if not stats:
                return pd.Series()

            strat = stats[0]
            # 尝试使用 analyzers
            values = []
            for analyzer in strat.analyzers:
                analysis = analyzer.get_analysis()
                if hasattr(analysis, 'items'):
                    for k, v in analysis.items():
                        if 'value' in str(k).lower() or 'equity' in str(k).lower():
                            if isinstance(v, (int, float)):
                                values.append(v)

            if values:
                return pd.Series(values)

            # 回退：使用 broker 最终值
            return pd.Series([cerebro.broker.getvalue()])

        except Exception:
            return pd.Series()

    def _get_trade_records(self, cerebro) -> list[dict]:
        """从 Cerebro 提取交易记录"""
        trades = []
        try:
            stats = cerebro.run()
            if not stats:
                return trades

            for strat in stats:
                for trade in strat.trades:
                    # backtrader 的 trade 对象中:
                    # - trade.price 是平均成交价（trade 关闭时可用）
                    # - 历史交易需从 trade.history 中获取开仓细节
                    entry_price = trade.price if hasattr(trade, 'price') else 0
                    exit_price = entry_price  # backtrader 单价格记录
                    trades.append({
                        'symbol': trade.data._name if hasattr(trade.data, '_name') else '',
                        'entry_date': str(trade.dtopen) if trade.dtopen else '',
                        'exit_date': str(trade.dtclose) if trade.dtclose else '',
                        'entry_price': entry_price,
                        'exit_price': exit_price,
                        'pnl': trade.pnl,
                        'pnl_comm': trade.pnlcomm,
                        'size': trade.size,
                    })
        except Exception:
            pass
        return trades

    def _calc_max_drawdown(self, equity: pd.Series) -> float:
        peak = equity.iloc[0]
        max_dd = 0.0
        for v in equity.values:
            if v > peak:
                peak = v
            dd = (peak - v) / peak if peak > 0 else 0
            max_dd = max(max_dd, dd)
        return max_dd

    def _calc_sharpe(self, equity: pd.Series) -> float:
        returns = equity.pct_change().dropna()
        if len(returns) < 2 or returns.std() == 0:
            return 0.0
        daily_rf = 0.02 / 252
        mean_ret = returns.mean()
        std_ret = returns.std()
        return (mean_ret - daily_rf) / std_ret * math.sqrt(252) if std_ret > 0 else 0.0

    def _calc_trade_stats(self, trades: list[dict]) -> tuple[float, float, int]:
        if not trades:
            return 0.0, 0.0, 0

        profits = [t['pnl'] for t in trades if t.get('pnl', 0) > 0]
        losses = [abs(t['pnl']) for t in trades if t.get('pnl', 0) < 0]

        total = len(profits) + len(losses)
        win_rate = len(profits) / total if total > 0 else 0

        avg_profit = sum(profits) / len(profits) if profits else 0
        avg_loss = sum(losses) / len(losses) if losses else 0
        pl_ratio = avg_profit / avg_loss if avg_loss > 0 else 0

        return win_rate, pl_ratio, total

    def _calc_drawdown_curve(self, equity: pd.Series) -> dict:
        dd_curve = {}
        peak = equity.iloc[0]
        for i, v in equity.items():
            if v > peak:
                peak = v
            dd = (peak - v) / peak if peak > 0 else 0
            dd_curve[str(i)] = round(dd, 4)
        return dd_curve

    def _empty_result(self) -> dict:
        return {
            'total_return': 0, 'annual_return': 0,
            'max_drawdown': 0, 'sharpe_ratio': 0,
            'win_rate': 0, 'profit_loss_ratio': 0,
            'total_trades': 0, 'trading_days': 0,
            'final_value': 0,
            'equity_curve': {}, 'drawdown_curve': {},
            'trade_records': [],
        }

    def generate_report(self, result: dict, output_path: str = '') -> str:
        """
        生成 HTML 绩效报告

        参数:
            result:      analyze() 返回的绩效字典
            output_path: 输出文件路径

        返回:
            str: 报告 HTML 内容
        """
        try:
            import quantstats as qs

            # 重建净值序列
            equity_curve = result.get('equity_curve', {})
            if equity_curve:
                returns = pd.Series(equity_curve).pct_change().dropna()
                qs.reports.html(returns, output=output_path or 'backtest_report.html',
                                title='回测绩效报告')
                return f"报告已生成: {output_path or 'backtest_report.html'}"
        except ImportError:
            pass

        # 回退：生成纯文本报告
        return self.format_report(result)

    def format_report(self, result: dict) -> str:
        """格式化输出绩效报告"""
        lines = [
            "=" * 60,
            "                   回 测 绩 效 报 告",
            "=" * 60,
            f"总收益率:      {result['total_return']*100:.2f}%",
            f"年化收益率:    {result['annual_return']*100:.2f}%",
            f"最大回撤:      {result['max_drawdown']*100:.2f}%",
            f"夏普比率:      {result['sharpe_ratio']:.2f}",
            f"胜率:          {result['win_rate']*100:.2f}%",
            f"盈亏比:        {result['profit_loss_ratio']:.2f}",
            f"总交易次数:    {result['total_trades']}",
            f"交易天数:      {result.get('trading_days', 0)}",
            f"最终资产:      {result.get('final_value', 0):,.2f} 元",
            "=" * 60,
        ]
        return "\n".join(lines)
