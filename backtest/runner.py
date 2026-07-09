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
from concurrent.futures import ThreadPoolExecutor, as_completed
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
                           end_date: str = '', period: str = '1d',
                           db: 'Database' = None) -> int:
        """
        从本地数据库加载K线数据到 cerebro

        P1 架构优化：多股 Parquet 并行预加载。
        旧代码串行逐股读 Parquet，N=20 股 = 20 次串行 IO。
        现用 ThreadPoolExecutor 并行读 DataFrame（Parquet 读取线程安全），
        再串行构建 PandasData feed。N=20 股预计加速 3-5 倍。

        参数:
            codes:      股票代码列表
            start_date: 起始日期 YYYYMMDD
            end_date:   结束日期 YYYYMMDD
            period:     K线周期
            db:         外部传入的 Database 实例

        返回:
            int: 成功加载的股票数量
        """
        own_db = db is None
        if own_db:
            db = Database()
            db.connect()
        self._db = db

        loaded = 0
        try:
            # P1 优化：并行预加载 DataFrame
            bt_columns = ['date', 'open', 'high', 'low', 'close', 'volume']
            df_cache: dict[str, pd.DataFrame] = {}

            def _read_one(code):
                return code, db.get_daily_kline_df(
                    code, period, start_date, end_date, columns=bt_columns
                )

            max_workers = min(8, len(codes)) if len(codes) > 1 else 1
            if max_workers > 1:
                with ThreadPoolExecutor(max_workers=max_workers) as executor:
                    futures = {executor.submit(_read_one, c): c for c in codes}
                    for future in as_completed(futures):
                        code, df = future.result()
                        if not df.empty:
                            df_cache[code] = df
            else:
                for code in codes:
                    c, df = _read_one(code)
                    if not df.empty:
                        df_cache[c] = df

            # 串行构建 PandasData feed（backtrader 非线程安全）
            for code in codes:
                df = df_cache.get(code)
                if df is None or df.empty:
                    print(f"警告: {code} 无数据，跳过")
                    continue
                data = load_bt_data(df)
                if data is not None:
                    data._name = code
                    self.cerebro.adddata(data, name=code)
                    loaded += 1
        finally:
            if own_db:
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

        # P2 修复：防止重复调用导致注册多个策略实例
        # 旧代码每次调用都 cerebro.addstrategy，多次调用会注册多个策略
        if hasattr(self, '_strategy_added') and self._strategy_added:
            # 清空已有策略再添加（cerebro 无直接 remove，通过重建策略列表实现）
            self.cerebro.strats = []
        self._strategy_added = True

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
