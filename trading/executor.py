# -*- coding: utf-8 -*-
"""
策略执行器模块

负责将策略信号转换为实盘交易下单指令。支持单次执行和定时循环两种运行模式。

核心流程:
    1. 获取股票池行情数据（先下载到本地缓存，再读取）
    2. 逐股票运行策略，生成交易信号
    3. 对每个信号通过 RiskManager 执行完整风控检查
    4. 通过 TraderManager 向券商发送实盘下单指令
    5. 记录成交信息到本地数据库

风险检查（由 RiskManager 统一执行）:
    买入检查:
        - 熔断状态检查
        - 涨停过滤
        - 单笔金额占比上限
        - 资金充足性（含佣金）
        - 单只股票持仓上限
        - 总持仓数量上限
    卖出检查:
        - 熔断状态检查
        - 持仓充足性
        - T+1 限制

使用方式:
    executor = StrategyExecutor("real", MACrossStrategy, trader_manager,
                                risk_manager=rm)
    executor.set_stock_list(["000001.SZ", "600000.SH"])
    executor.run_once()
    # or
    executor.run_loop(interval_seconds=60)
"""
import time
import threading
import pandas as pd
from datetime import datetime
from data.xt_provider import DataProvider
from data.database import Database
from strategy.base import BaseStrategy, Signal
from trading.xt_trader import TraderManager
from risk.risk_manager import RiskManager


def _extract_single_kline(kline: pd.DataFrame, code: str) -> pd.DataFrame:
    """
    从 xtquant 返回的 DataFrame 中提取单只股票的 K 线

    xtquant 的 get_market_data_ex / get_market_data 返回的 DataFrame 有两种结构:
        - 单只股票: 普通 columns (open, high, low, close, volume, amount)
        - 多只股票: MultiIndex columns，第一层=字段名，第二层=股票代码

    此函数统一处理两种情况，返回单只股票的标准 DataFrame。

    参数:
        kline: xtquant 返回的原始 K 线 DataFrame
        code:  目标股票代码

    返回:
        pd.DataFrame: 该股票的 K 线，columns 为 open/high/low/close/volume/amount
    """
    if kline is None or kline.empty:
        return pd.DataFrame()

    if isinstance(kline.columns, pd.MultiIndex):
        try:
            df = kline.xs(code, level=1, axis=1)
        except KeyError:
            return pd.DataFrame()
    else:
        df = kline

    return df


class StrategyExecutor:
    """
    策略执行器

    提供完整的"行情获取 → 策略运算 → 风险管理 → 交易执行 → 记录保存"流水线。
    所有交易指令通过 TraderManager 下达至券商实盘交易柜台。

    属性:
        account_id:   交易账号ID
        strategy_cls: 策略类（非实例，每次运行创建新实例）
        trader:       交易管理器
        risk_manager: 统一风控管理器
        provider:     行情数据提供者
        db:           本地数据库（用于记录交易）
        _running:     循环运行标志
        _thread:      后台循环线程
        _stock_list:  当前股票池
    """

    def __init__(self, account_id: str, strategy_cls: type[BaseStrategy],
                 trader_manager: TraderManager,
                 risk_manager: RiskManager | None = None,
                 provider: DataProvider | None = None,
                 database: Database | None = None):
        """
        参数:
            account_id:     交易账号ID，如 "real"
            strategy_cls:   策略类引用（非实例）
            trader_manager: 已初始化的交易管理器实例
            risk_manager:   风控管理器，不传则自动创建
            provider:       行情提供者，不传则自动创建
            database:       数据库对象，不传则自动创建（会自动 connect + initialize）
        """
        self.account_id: str = account_id
        self.strategy_cls: type[BaseStrategy] = strategy_cls
        self.strategy_name: str = strategy_cls.name or strategy_cls.__name__
        self.trader: TraderManager = trader_manager
        self.risk_manager: RiskManager = risk_manager or RiskManager()
        self.provider: DataProvider = provider or DataProvider()
        if database is not None:
            self.db = database
            self._own_db = False
        else:
            self.db = Database()
            self.db.connect()
            self.db.initialize()
            self._own_db = True

        self._running: bool = False
        self._thread: threading.Thread | None = None
        self._stock_list: list[str] = []
        self._peak_equity: float = 0.0
        self._buy_dates: dict[str, str] = {}  # {code: buy_date} 用于 T+1 检查

    def set_stock_list(self, codes: list[str]) -> None:
        """
        设置策略执行的股票池

        参数:
            codes: 股票代码列表
        """
        self._stock_list = codes

    def run_once(self) -> list[dict]:
        """
        运行一次完整策略执行流程

        流程:
            1. 检查股票池（空时自动取沪深A股前50只作为默认池）
            2. 验证账号连接状态和熔断状态
            3. 批量下载K线到本地缓存
            4. 逐股票获取近期K线数据
            5. 运行策略，生成信号
            6. 通过 RiskManager 执行完整风控检查
            7. 通过 TraderManager 下达实盘指令
            8. 更新风控状态、记录到本地数据库

        返回:
            list[dict]: 已执行的信号记录列表
        """
        if not self._stock_list:
            # 按成交额排序取前 50 只作为默认股票池（比简单按代码排序更有意义）
            all_stocks = self.provider.get_stock_list()
            self._stock_list = all_stocks[:50]
            print(f"使用默认股票池（前50只）: {len(self._stock_list)}")

        signals_executed: list[dict] = []

        if not self.trader.is_connected(self.account_id):
            print(f"账号 {self.account_id} 未连接，跳过执行")
            return signals_executed

        if self.risk_manager.is_meltdown():
            print(f"风控熔断已触发，跳过执行: {self.risk_manager.get_risk_summary()['meltdown_reason']}")
            return signals_executed

        # 获取当前资产和持仓（一次查询，复用）
        asset = self.trader.query_asset(self.account_id)
        if asset is None:
            print("无法获取账户资产，跳过执行")
            return signals_executed

        positions_list = self.trader.query_positions(self.account_id)
        positions_dict: dict[str, dict] = {
            p['stock_code']: {'volume': p['volume'], 'can_use_volume': p['can_use_volume']}
            for p in positions_list
        }
        current_cash = asset.get('available_cash', 0)
        current_equity = asset.get('total_asset', 0)

        # 更新资产峰值
        if current_equity > self._peak_equity:
            self._peak_equity = current_equity

        # 检查熔断
        ok, reason = self.risk_manager.check_daily_loss(current_equity)
        if not ok:
            print(f"日亏损熔断: {reason}")
            return signals_executed

        ok, reason = self.risk_manager.check_drawdown(self._peak_equity, current_equity)
        if not ok:
            print(f"回撤熔断: {reason}")
            return signals_executed

        today_str = datetime.now().strftime('%Y%m%d')
        print(f"\n[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] 开始运行策略...")

        for code in self._stock_list:
            try:
                self.provider.download_history([code], period='1d')

                kline = self.provider.get_kline([code], period='1d', count=50)
                df = _extract_single_kline(kline, code)

                if df.empty:
                    continue

                prev_close = float(df['close'].iloc[-2]) if len(df) >= 2 else 0.0

                strategy = self.strategy_cls()
                strategy.init({"kline": df})

                signals: list[Signal] = strategy.on_bar(len(df) - 1)

                for sig in signals:
                    price: float = float(df['close'].iloc[-1])
                    sig.symbol = code
                    sig.price = round(price, 2)
                    sig.volume = max((sig.volume // 100) * 100, 100)

                    success: bool = False

                    if sig.action == 'BUY':
                        ok, reason = self.risk_manager.check_buy(
                            code=code, price=sig.price, volume=sig.volume,
                            cash=current_cash, positions=positions_dict,
                            prev_close=prev_close,
                        )
                        if not ok:
                            print(f"[风控拒绝-买入] {code}: {reason}")
                            continue
                        success = self._do_buy(code, sig.price, sig.volume)
                        if success:
                            self._buy_dates[code] = today_str
                            positions_dict[code] = positions_dict.get(code, {'volume': 0, 'can_use_volume': 0})
                            positions_dict[code]['volume'] = positions_dict[code].get('volume', 0) + sig.volume
                            current_cash -= sig.price * sig.volume * 1.00025

                    elif sig.action == 'SELL':
                        buy_date = self._buy_dates.get(code, '')
                        ok, reason = self.risk_manager.check_sell(
                            code=code, volume=sig.volume,
                            positions=positions_dict,
                            prev_close=prev_close,
                            buy_date=buy_date,
                            current_date=today_str,
                        )
                        if not ok:
                            print(f"[风控拒绝-卖出] {code}: {reason}")
                            continue
                        success = self._do_sell(code, sig.price, sig.volume)
                        if success:
                            self._buy_dates.pop(code, None)
                            if code in positions_dict:
                                positions_dict[code]['volume'] = positions_dict[code].get('volume', 0) - sig.volume
                            current_cash += sig.price * sig.volume * (1 - 0.00125)

                    else:
                        continue

                    if success:
                        amount = sig.price * sig.volume
                        commission = max(amount * 0.00025, 5.0)
                        record = {
                            'account_id': self.account_id,
                            'symbol': code,
                            'action': sig.action,
                            'price': sig.price,
                            'volume': sig.volume,
                            'amount': amount,
                            'commission': round(commission, 2),
                            'tax': round(amount * 0.001, 2) if sig.action == 'SELL' else 0,
                            'trade_time': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
                            'status': '已提交',
                        }
                        self.db.insert_trade_record(record)
                        signals_executed.append(record)

            except Exception as e:
                print(f"处理 {code} 异常: {e}")

        print(f"策略执行完成，共 {len(signals_executed)} 个信号被执行")
        return signals_executed

    def _do_buy(self, code: str, price: float, volume: int) -> bool:
        """执行买入（带策略名备注）"""
        return self.trader.buy(
            self.account_id, code, price, volume,
            strategy_name=self.strategy_name,
            remark=f"{self.strategy_name}-{datetime.now().strftime('%H%M')}",
        )

    def _do_sell(self, code: str, price: float, volume: int) -> bool:
        """执行卖出（带策略名备注）"""
        return self.trader.sell(
            self.account_id, code, price, volume,
            strategy_name=self.strategy_name,
            remark=f"{self.strategy_name}-{datetime.now().strftime('%H%M')}",
        )

    def run_loop(self, interval_seconds: int = 60) -> None:
        """
        定时循环执行策略

        启动一个 daemon 线程，每隔指定秒数执行一次 run_once()。
        daemon 线程在主程序退出时自动结束。

        参数:
            interval_seconds: 循环间隔秒数，默认 60 秒（分钟级）

        注意:
            - 第一次执行在 start 后立即进行，之后按间隔循环
            - 循环在 _running 被设为 False 时自动退出
            - 循环内设有异常保护，单次失败不会中断整个循环
        """
        self._running = True

        def _loop() -> None:
            print(f"策略执行器启动，账号={self.account_id}，间隔={interval_seconds}秒")
            while self._running:
                try:
                    self.run_once()
                except Exception as e:
                    print(f"策略循环执行异常: {e}")
                if self._running:
                    time.sleep(interval_seconds)
            print("策略执行器已停止")

        self._thread = threading.Thread(target=_loop, daemon=True)
        self._thread.start()

    def stop(self) -> None:
        """
        停止策略循环并清理资源

        设置停止标志后等待线程退出（最多 5 秒），然后关闭数据库连接。
        """
        self._running = False
        if self._thread:
            self._thread.join(timeout=5)
        if self._own_db:
            self.db.close()
