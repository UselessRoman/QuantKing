# -*- coding: utf-8 -*-
"""
回测运行器模块

封装 backtrader.Cerebro 的创建、配置和执行流程，
对外提供简洁的一键运行接口。

使用方式:
    from backtest.runner import BacktestRunner

    runner = BacktestRunner(initial_capital=100000)
    runner.load_data_from_db(codes=["000001.SZ"], start_date="20230101", end_date="20231231")
    runner.set_strategy(MACrossStrategy, fast=5, slow=20)
    result = runner.run()
    print(result['performance'])
"""
import pandas as pd
import backtrader as bt
from datetime import datetime
from data.database import Database
from data.backtrader_feeder import load_bt_data
from backtest.bt_broker import AShareCommission
from backtest.bt_analyzer import BacktestAnalyzer
from backtest.bt_strategy import get_strategy


class BacktestRunner:
    """
    回测执行器

    封装了 backtrader 回测的完整流程:
        数据加载 → 策略配置 → 回测执行 → 绩效分析

    属性:
        cerebro:         backtrader.Cerebro 实例
        initial_capital: 初始资金
        analyzer:        绩效分析器
        _db:             数据库连接
    """

    def __init__(self, initial_capital: float = 100000,
                 commission_rate: float = 0.00025):
        """
        参数:
            initial_capital: 初始资金
            commission_rate: 佣金费率
        """
        self.initial_capital = initial_capital
        self.commission_rate = commission_rate
        self.cerebro = bt.Cerebro()
        self.analyzer = BacktestAnalyzer()
        self._db = None

        # 设置默认配置
        self.cerebro.broker.setcash(initial_capital)
        self.cerebro.broker.setcommission(commission=commission_rate)
        self.cerebro.broker.addcommissioninfo(AShareCommission())
        # 滑点：万分之一（0.01%），模拟成交价劣化，避免回测过于乐观。
        # 旧版无滑点，回测收益偏乐观；加_perc按比例滑点更贴近实盘。
        self.cerebro.broker.set_slippage_perc(perc=0.0001)

        # 添加默认分析器
        #   TimeReturn / Transactions 是 BacktestAnalyzer 的数据来源（必须挂载），
        #   其余为 backtrader 内置指标，便于直接 get_analysis() 交叉核对。
        self.cerebro.addanalyzer(bt.analyzers.TimeReturn, _name='timereturn',
                                 timeframe=bt.TimeFrame.Days)
        self.cerebro.addanalyzer(bt.analyzers.Transactions, _name='transactions')
        self.cerebro.addanalyzer(bt.analyzers.TradeAnalyzer, _name='trades')
        self.cerebro.addanalyzer(bt.analyzers.SharpeRatio, _name='sharpe',
                                 riskfreerate=0.02, annualize=True)
        self.cerebro.addanalyzer(bt.analyzers.DrawDown, _name='drawdown')
        self.cerebro.addanalyzer(bt.analyzers.Returns, _name='returns')
        self.cerebro.addanalyzer(bt.analyzers.VWR, _name='vwr')

    def load_data_from_db(self, codes: list[str], start_date: str = '',
                           end_date: str = '', period: str = '1d') -> int:
        """
        从本地数据库加载K线数据到 cerebro

        参数:
            codes:      股票代码列表
            start_date: 起始日期 YYYYMMDD
            end_date:   结束日期 YYYYMMDD
            period:     K线周期

        返回:
            int: 成功加载的股票数量
        """
        db = Database()
        db.connect()
        self._db = db

        loaded = 0
        try:
            for code in codes:
                df = db.get_daily_kline_df(code, period, start_date, end_date)
                if df.empty:
                    print(f"警告: {code} 无数据，跳过")
                    continue

                data = load_bt_data(df)
                if data is not None:
                    # 设置数据名称用于策略中识别
                    data._name = code
                    self.cerebro.adddata(data, name=code)
                    loaded += 1
        finally:
            db.close()

        print(f"已加载 {loaded}/{len(codes)} 只股票的K线数据")
        return loaded

    def load_data_from_df(self, kline_dict: dict[str, pd.DataFrame]) -> int:
        """
        从 DataFrame 字典加载K线数据

        参数:
            kline_dict: {股票代码: K线 DataFrame}

        返回:
            int: 成功加载的股票数量
        """
        loaded = 0
        for code, df in kline_dict.items():
            if df.empty:
                continue
            data = load_bt_data(df)
            if data is not None:
                data._name = code
                self.cerebro.adddata(data, name=code)
                loaded += 1
        print(f"已加载 {loaded}/{len(kline_dict)} 只股票的数据")
        return loaded

    def set_strategy(self, strategy_cls_or_name, **params):
        """
        设置回测策略

        参数:
            strategy_cls_or_name: 策略类 或 策略名称字符串
            **params:             策略参数
        """
        if isinstance(strategy_cls_or_name, str):
            strategy_cls = get_strategy(strategy_cls_or_name)
        else:
            strategy_cls = strategy_cls_or_name

        self.cerebro.addstrategy(strategy_cls, **params)
        print(f"已设置策略: {strategy_cls.__name__}")

    def run(self) -> dict:
        """
        执行回测并返回完整结果

        返回:
            dict: 包含以下字段:
                - performance:   绩效指标
                - initial_capital: 初始资金
                - final_value:   最终资产
                - timestamp:     执行时间
        """
        print(f"开始回测... 初始资金: {self.initial_capital:,.0f} 元")

        start_value = self.cerebro.broker.getvalue()
        results = self.cerebro.run()
        end_value = self.cerebro.broker.getvalue()

        # analyze() 接收已运行的策略实例（cerebro.run 的返回值），
        # 从其挂载的 analyzer 提取净值/交易数据，不再重复执行回测。
        strat = results[0] if results else None
        performance = self.analyzer.analyze(strat, self.initial_capital) if strat else self.analyzer._empty_result()

        # 补充最终资产信息
        performance['final_value'] = round(end_value, 2)
        performance['initial_capital'] = self.initial_capital

        return {
            'performance': performance,
            'initial_capital': self.initial_capital,
            'final_value': round(end_value, 2),
            'total_return_pct': round((end_value / start_value - 1) * 100, 2),
            'timestamp': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
        }

    def run_qlib_signal(self, codes: list[str], signals: dict[str, list[str]],
                        start_date: str = '', end_date: str = '',
                        top_k: int = 20, rebalance_freq: int = 20,
                        period: str = '1d') -> dict:
        """
        qlib 信号驱动回测专用入口

        QlibSignalStrategy 的选股信号必须通过 params 在 cerebro 实例化策略时注入，
        普通的 set_strategy 路径无法传递，因此提供此专用方法。

        参数:
            codes:           回测股票池
            signals:         {date_str(YYYYMMDD): [入选股票代码]}
            start_date:      数据起始日期
            end_date:        数据结束日期
            top_k:           目标持仓数
            rebalance_freq:  调仓间隔（交易日）
            period:          K线周期

        返回:
            dict: 回测结果（同 run()）
        """
        from backtest.bt_strategy import QlibSignalStrategy

        loaded = self.load_data_from_db(codes, start_date, end_date, period=period)
        if loaded == 0:
            return {'error': '未加载到任何K线数据'}

        self.cerebro.addstrategy(
            QlibSignalStrategy,
            signals=signals,
            codes=codes,
            top_k=top_k,
            rebalance_freq=rebalance_freq,
        )
        print(f"已设置 qlib 信号策略: 持仓 {top_k} 只, 调仓间隔 {rebalance_freq} 天, "
              f"信号日期数 {len(signals)}")
        return self.run()

    def run_quick(self, codes: list[str], strategy_name: str,
                  start_date: str = '', end_date: str = '',
                  **params) -> dict:
        """
        快速回测：一键加载数据、设置策略、运行、分析

        参数:
            codes:         股票代码列表
            strategy_name: 策略名称（如 'ma_cross'）
            start_date:    起始日期
            end_date:      结束日期
            **params:      策略参数

        返回:
            dict: 回测结果
        """
        loaded = self.load_data_from_db(codes, start_date, end_date)
        if loaded == 0:
            return {'error': '未加载到任何K线数据'}

        self.set_strategy(strategy_name, **params)
        return self.run()
