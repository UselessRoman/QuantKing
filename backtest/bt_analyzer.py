# -*- coding: utf-8 -*-
"""
回测绩效分析模块（backtrader 版本）

集成 quantstats 库生成专业绩效报告，同时提供独立的绩效指标计算。

绩效指标:
    - 总收益率、年化收益率
    - 最大回撤
    - 夏普比率
    - 胜率、盈亏比
    - 净值曲线、回撤曲线
    - 月度收益率热力图（依赖 quantstats）

▌数据来源约定（重要）
    analyze() 不再自行执行 cerebro.run()，而是消费调用方已运行得到的
    backtrader Strategy 实例，从其挂载的 analyzer 中提取数据：

    - bt.analyzers.TimeReturn    → 每日收益率序列（用于净值曲线、夏普、回撤）
    - bt.analyzers.Transactions  → 逐笔成交记录（用于胜率、盈亏比、交易明细）

    BacktestRunner 已统一挂载这两个 analyzer。若 strat 上未挂载，analyze()
    会回退到 broker.getvalue()，但 trading_days / 交易统计将不可靠，
    并在日志中给出警告。

使用方式:
    from backtest.bt_analyzer import BacktestAnalyzer

    analyzer = BacktestAnalyzer()
    strat = cerebro.run()[0]
    performance = analyzer.analyze(strat, initial_capital=100000)
    print(analyzer.format_report(performance))
"""
import math
from typing import Optional

import numpy as np
import pandas as pd

from utils.logging import get_logger

_logger = get_logger("bt_analyzer")


class BacktestAnalyzer:
    """
    回测绩效分析器

    从已运行的 backtrader Strategy 实例中提取并计算多种绩效指标。

    使用方式:
        analyzer = BacktestAnalyzer()
        strat = cerebro.run()[0]
        performance = analyzer.analyze(strat, initial_capital=100000)
        print(analyzer.format_report(performance))
    """

    def analyze(self, strat, initial_capital: float = 100000) -> dict:
        """
        从已运行的策略实例中提取绩效指标

        参数:
            strat:           backtrader 策略实例（cerebro.run() 的返回值），
                             需已挂载 TimeReturn / Transactions analyzer
            initial_capital: 初始资金

        返回:
            dict: 完整绩效指标

        注意:
            若 strat 未挂载 TimeReturn analyzer，绩效指标（夏普/回撤/净值曲线）
            将不可靠，结果中会带 unreliable=True 标记并记 error 日志。
            BacktestRunner.__init__ 已统一挂载这两个 analyzer。
        """
        # 入口检查：TimeReturn 是净值曲线的数据来源，缺失则指标不可信
        has_timereturn = self._has_analyzer(strat, 'TimeReturn')
        has_transactions = self._has_analyzer(strat, 'Transactions')
        if not has_timereturn:
            _logger.error(
                "策略未挂载 TimeReturn analyzer，绩效指标（夏普/回撤/净值曲线）"
                "将不可靠。请在 BacktestRunner 中调用 "
                "cerebro.addanalyzer(bt.analyzers.TimeReturn, _name='timereturn', "
                "timeframe=bt.TimeFrame.Days)"
            )
        if not has_transactions:
            _logger.warning(
                "策略未挂载 Transactions analyzer，交易统计（胜率/盈亏比）"
                "将回退到 strat._trades，可能为空"
            )

        equity = self._equity_from_strategy(strat, initial_capital)
        trades = self._get_trade_records(strat)

        if equity is None or equity.empty:
            _logger.warning("未能从策略中提取净值曲线，绩效指标将不可靠")
            return self._empty_result()

        # 基础指标
        total_return = float(equity.iloc[-1] / initial_capital - 1)
        trading_days = int(len(equity))
        years = max(trading_days / 252, 1 / 252)
        annual_return = (1 + total_return) ** (1 / years) - 1 if total_return > -1 else 0

        # 最大回撤（基于归一化净值）
        max_dd = self._calc_max_drawdown(equity / initial_capital)

        # 夏普比率
        sharpe = self._calc_sharpe(equity)

        # 交易统计
        win_rate, profit_loss_ratio, total_trades = self._calc_trade_stats(trades)

        # 净值曲线和回撤曲线
        # P2 修复：用实际日期作 key 而非整数序号，前端可对应交易日
        equity_curve = {str(dt): float(v / initial_capital) for dt, v in equity.items()}
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
            'final_value': round(float(equity.iloc[-1]), 2),
            'equity_curve': equity_curve,
            'drawdown_curve': drawdown_curve,
            'trade_records': trades,
            # 标记指标可信度：未挂载 TimeReturn 时净值曲线退化为单点，
            # 夏普/回撤/trading_days 不可信，前端可据此提示用户
            'unreliable': not has_timereturn,
        }

    # ──────────── 数据提取 ────────────

    @staticmethod
    def _has_analyzer(strat, analyzer_class_name: str) -> bool:
        """检查策略是否挂载了指定名称的 analyzer"""
        try:
            for analyzer in strat.analyzers:
                if analyzer.__class__.__name__ == analyzer_class_name:
                    return True
        except Exception:
            pass
        return False

    def _equity_from_strategy(self, strat, initial_capital: float) -> Optional[pd.Series]:
        """
        从策略挂载的 analyzer 提取每日净值曲线

        优先使用 TimeReturn analyzer 的日收益率序列，累乘还原为净值曲线；
        若未挂载则回退到单点 broker 总资产（此时无法计算夏普/回撤序列）。
        """
        daily_returns = self._extract_daily_returns(strat)
        if daily_returns is not None and len(daily_returns) > 0:
            returns = pd.Series(daily_returns)
            # 由日收益率累乘得到净值（起点为 initial_capital）
            equity = initial_capital * (1 + returns).cumprod()
            return equity

        _logger.warning("策略未挂载 TimeReturn analyzer，回退到单点净值")
        try:
            return pd.Series([float(strat.broker.getvalue())])
        except Exception:
            return None

    def _extract_daily_returns(self, strat) -> Optional[dict]:
        """从策略的 analyzer 中查找 TimeReturn 分析结果"""
        try:
            for analyzer in strat.analyzers:
                if analyzer.__class__.__name__ != 'TimeReturn':
                    continue
                analysis = analyzer.get_analysis()
                if hasattr(analysis, 'items') and len(analysis) > 0:
                    return dict(analysis)
        except Exception:
            return None
        return None

    def _get_trade_records(self, strat) -> list[dict]:
        """
        从策略的 Transactions analyzer 提取交易记录

        Transactions analyzer 返回 {datetime: [(data, size, price), ...]}，
        将其展平为标准记录列表。失败时回退到 strat 的已平仓交易列表。
        """
        trades: list[dict] = []

        # 优先：Transactions analyzer
        try:
            for analyzer in strat.analyzers:
                if analyzer.__class__.__name__ != 'Transactions':
                    continue
                analysis = analyzer.get_analysis()
                if not hasattr(analysis, 'items'):
                    continue
                for dt, txn_list in analysis.items():
                    for item in txn_list:
                        # backtrader: (data, size, price) 或 (data, size, price, commission)
                        data, size, price = item[0], item[1], item[2]
                        trades.append({
                            'datetime': str(dt),
                            'symbol': getattr(data, '_name', ''),
                            'size': float(size),
                            'price': float(price),
                        })
                if trades:
                    return trades
        except Exception:
            trades = []

        # 回退：strat._trades（已平仓交易）
        try:
            closed = getattr(strat, '_trades', {}) or {}
            for trade_list in closed.values():
                for trade in trade_list:
                    if not trade.isclosed:
                        continue
                    trades.append({
                        'symbol': getattr(trade.data, '_name', ''),
                        'entry_price': float(trade.price),
                        'exit_price': float(trade.price) + float(trade.pnlcomm) / max(abs(trade.size), 1),
                        'pnl': float(trade.pnl),
                        'pnl_comm': float(trade.pnlcomm),
                        'size': int(trade.size),
                    })
        except Exception:
            pass
        return trades

    # ──────────── 纯算法（可独立单测）────────────

    def _calc_max_drawdown(self, equity: pd.Series) -> float:
        """最大回撤（向量化实现）

        P2 优化：旧代码用 Python for 循环逐元素遍历 equity.values，
        现用 np.maximum.accumulate 向量化，提速 100 倍以上。
        """
        if equity is None or len(equity) == 0:
            return 0.0
        values = equity.values.astype(float)
        peaks = np.maximum.accumulate(values)
        drawdowns = (peaks - values) / np.where(peaks > 0, peaks, 1)
        return float(np.max(drawdowns)) if len(drawdowns) > 0 else 0.0

    def _calc_sharpe(self, equity: pd.Series) -> float:
        if equity is None or len(equity) < 2:
            return 0.0
        returns = equity.pct_change().dropna()
        if len(returns) < 2:
            return 0.0
        std_ret = returns.std()
        if std_ret == 0 or np.isnan(std_ret):
            return 0.0
        daily_rf = 0.02 / 252
        mean_ret = returns.mean()
        return (mean_ret - daily_rf) / std_ret * math.sqrt(252)

    def _calc_trade_stats(self, trades: list[dict]) -> tuple[float, float, int]:
        """胜率 / 盈亏比 / 总交易笔数"""
        if not trades:
            return 0.0, 0.0, 0

        # 统一口径：取 pnl（已平仓交易）。Transactions 模式无 pnl，跳过逐笔盈亏统计。
        pnls = []
        for t in trades:
            pnl = t.get('pnl')
            if pnl is None:
                continue
            pnls.append(float(pnl))

        if not pnls:
            # 有交易记录但无 pnl 字段，仅返回笔数
            return 0.0, 0.0, len(trades)

        profits = [p for p in pnls if p > 0]
        losses = [abs(p) for p in pnls if p < 0]
        total = len(profits) + len(losses)
        win_rate = len(profits) / total if total > 0 else 0
        avg_profit = sum(profits) / len(profits) if profits else 0
        avg_loss = sum(losses) / len(losses) if losses else 0
        pl_ratio = avg_profit / avg_loss if avg_loss > 0 else 0
        return win_rate, pl_ratio, total

    def _calc_drawdown_curve(self, equity: pd.Series) -> dict:
        """回撤曲线（向量化实现）

        P2 优化：旧代码用 Python for 循环逐元素遍历，
        现用 np.maximum.accumulate 向量化。
        """
        if equity is None or len(equity) == 0:
            return {}
        values = equity.values.astype(float)
        peaks = np.maximum.accumulate(values)
        drawdowns = (peaks - values) / np.where(peaks > 0, peaks, 1)
        # P2 修复：用实际日期作 key 而非整数序号，前端可对应交易日
        date_keys = [str(dt) for dt in equity.index]
        return {date_keys[i]: round(float(dd), 4) for i, dd in enumerate(drawdowns)}

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
            str: 报告 HTML 内容或纯文本报告
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
