# -*- coding: utf-8 -*-
"""
实盘交易管理模块

基于 XtQuant 的实盘交易管理器，封装了 QMT 交易接口的核心操作：
账号连接、限价买卖、撤单、持仓/委托/资产查询、成交查询。

架构说明:
    TraderManager 管理实盘交易账号，通过 account_id 区分不同账号，
    底层持有 XtQuantTrader 实例与 QMT 交易端通信，所有订单直接下达至券商柜台。

典型使用流程:
    manager = TraderManager()
    manager.connect_all()                          # 连接实盘账号
    manager.buy("real", "000001.SZ", 12.50, 100)   # 下买入单
    positions = manager.query_positions("real")    # 查询持仓
    manager.disconnect_all()                       # 断开连接

注意事项:
    - 需要 QMT 交易端运行且 xtquant 包已安装
    - 下单参数 price_type=2 表示限价单，STOCK_BUY/STOCK_SELL 为股票买卖类型
    - 所有方法均有异常保护，失败时返回 False/空列表/None
    - TraderManager 非线程安全，多线程场景需外部加锁
    - 实盘交易涉及真实资金，请务必做好充分的风控措施和回测验证

XTquant API 参考:
    - order_stock(account, stock_code, order_type, order_volume, price_type, price, ...)
        price_type: 2=限价(LATEST_PRICE_FIFTH), 5=对方最优, 11=五档即成剩撤 ...
    - cancel_order(order_id, account)  -- 返回 0 表示成功
    - query_stock_positions(account)   -- 返回持仓列表
    - query_stock_orders(account)      -- 返回当日委托列表
    - query_stock_trades(account)      -- 返回当日成交列表
    - query_stock_asset(account)       -- 返回账户资产
"""
from dataclasses import dataclass, field
from config.settings import ACCOUNTS

try:
    from xtquant.xttrader import XtQuantTrader, XtQuantTraderCallback
    from xtquant.xttype import StockAccount
    from xtquant import xtconstant
    _XT_TRADER_AVAILABLE = True
except ImportError:
    XtQuantTrader = None
    XtQuantTraderCallback = None
    StockAccount = None
    xtconstant = None
    _XT_TRADER_AVAILABLE = False


@dataclass
class AccountConfig:
    """
    交易账号配置

    属性:
        id:           账号唯一标识，如 "real"（实盘）
        label:        账号显示标签，用于日志输出
        miniqmt_path: QMT 交易端的 userdata_mini 目录路径
        account_id:   资金账号
        account_type: 账号类型，"STOCK" 表示股票账户（A 股）
    """
    id: str
    label: str
    miniqmt_path: str
    account_id: str
    account_type: str = "STOCK"


class TraderManager:
    """
    实盘交易管理器

    封装 XtQuantTrader 接口，提供统一的买卖、查询和管理功能，
    用于实盘交易环境，所有订单直接下达至券商交易柜台。

    内部状态:
        _traders:    {账号ID: XtQuantTrader 实例}
        _callbacks:  {账号ID: 回调对象实例}，用于接收交易推送
        _connected:  {账号ID: 连接状态 bool}
        _accounts:   {账号ID: AccountConfig 配置对象}
    """

    def __init__(self):
        self._traders: dict[str, object] = {}
        self._callbacks: dict[str, object] = {}
        self._connected: dict[str, bool] = {}
        self._accounts: dict[str, AccountConfig] = {}

    def connect_all(self, accounts: list[dict] = None) -> dict[str, bool]:
        """
        连接所有配置的账号

        遍历账号列表，逐个创建 XtQuantTrader 实例并连接。
        每个账号有独立的回调实例，打印关键事件（断连、委托、成交、状态变更）。

        参数:
            accounts: 账号配置列表，None 时使用 config.settings.ACCOUNTS
                      每条配置需含 id/label/miniqmt_path/account_id 字段

        返回:
            dict[str, bool]: {账号ID: 连接是否成功}
        """
        if accounts is None:
            accounts = ACCOUNTS

        results = {}
        for acc in accounts:
            config = AccountConfig(**{k: v for k, v in acc.items()
                                      if k in AccountConfig.__dataclass_fields__})
            self._accounts[config.id] = config
            ok = self._connect_one(config)
            results[config.id] = ok

        return results

    def _connect_one(self, config: AccountConfig) -> bool:
        """
        连接单个交易账号

        步骤:
            1. 检查 XtQuant 模块是否可用
            2. 创建回调类实例，绑定事件处理
            3. 创建 XtQuantTrader 实例并启动
            4. 连接服务器
            5. 订阅账号（订阅后才能接收推送和下单）

        参数:
            config: 账号配置对象

        返回:
            bool: 连接成功返回 True
        """
        if not _XT_TRADER_AVAILABLE:
            print("xtquant 交易模块未安装，无法初始化交易功能")
            self._connected[config.id] = False
            return False

        try:
            from pathlib import Path
            from datetime import datetime

            class _Callback(XtQuantTraderCallback):
                def on_disconnected(self):
                    print(f"[{config.label}] 交易连接断开")

                def on_stock_order(self, order):
                    print(f"[{config.label}] 委托回报: {order.stock_code} "
                          f"{order.order_volume}股 订单号={order.order_id}")

                def on_stock_trade(self, trade):
                    print(f"[{config.label}] 成交回报: {trade.stock_code} "
                          f"{trade.traded_volume}股@{trade.traded_price}")

                def on_account_status(self, status):
                    print(f"[{config.label}] 账号状态变更: {status}")

            import time
            callback = _Callback()
            miniqmt_path = str(Path(config.miniqmt_path).resolve())
            session_id = int(str(time.time_ns())[-9:])
            trader = XtQuantTrader(miniqmt_path, session_id, callback)
            trader.start()
            connect_result = trader.connect()

            if connect_result != 0:
                print(f"[{config.label}] 连接失败，返回码: {connect_result}")
                self._connected[config.id] = False
                return False

            import time
            time.sleep(1)

            account = StockAccount(config.account_id, config.account_type)
            subscribe_result = trader.subscribe(account)

            if subscribe_result != 0:
                print(f"[{config.label}] 订阅账号失败（返回码 {subscribe_result}），尝试重试...")
                time.sleep(2)
                subscribe_result = trader.subscribe(account)

            if subscribe_result != 0:
                print(f"[{config.label}] 订阅账号仍然失败（返回码 {subscribe_result}）")
                print(f"  账号ID: {config.account_id}，类型: {config.account_type}")
                print(f"  请确认 QMT 交易端已登录该资金账号")
                self._connected[config.id] = False
                return False

            self._traders[config.id] = trader
            self._callbacks[config.id] = callback
            self._connected[config.id] = True
            print(f"[{config.label}] 连接成功")
            return True

        except Exception as e:
            print(f"[{config.label}] 连接异常: {e}")
            self._connected[config.id] = False
            return False

    def buy(self, account_id: str, code: str, price: float, volume: int,
            strategy_name: str = '', remark: str = '') -> bool:
        """
        限价买入

        参数:
            account_id:    账号ID，如 "real"
            code:          股票代码，如 "000001.SZ"
            price:         限价买入价格
            volume:        买入股数（建议为 100 的整数倍）
            strategy_name: 策略名称（用于审计追踪）
            remark:        订单备注（用于审计追踪）

        返回:
            bool: 下单成功返回 True，失败或未连接返回 False
        """
        if account_id not in self._traders or not self._connected.get(account_id):
            print(f"账号 {account_id} 未连接")
            return False

        if not _XT_TRADER_AVAILABLE:
            return False

        try:
            trader = self._traders[account_id]
            config = self._accounts[account_id]
            account = StockAccount(config.account_id, config.account_type)

            order_id = trader.order_stock(account, code, xtconstant.STOCK_BUY, volume,
                                          xtconstant.LATEST_PRICE_FIFTH, price,
                                          strategy_name=strategy_name, order_remark=remark)
            if order_id == -1:
                print(f"[{config.label}] 下单失败: {code} {volume}股 @ {price}")
                return False

            print(f"[{config.label}] 下单成功: {code} {volume}股 @ {price}, 订单号={order_id}")
            return True

        except Exception as e:
            print(f"[{account_id}] 买入异常: {e}")
            return False

    def sell(self, account_id: str, code: str, price: float, volume: int,
             strategy_name: str = '', remark: str = '') -> bool:
        """
        限价卖出

        参数:
            account_id:    账号ID
            code:          股票代码
            price:         限价卖出价格
            volume:        卖出股数（建议为 100 的整数倍）
            strategy_name: 策略名称（用于审计追踪）
            remark:        订单备注（用于审计追踪）

        返回:
            bool: 下单成功返回 True
        """
        if account_id not in self._traders or not self._connected.get(account_id):
            print(f"账号 {account_id} 未连接")
            return False

        if not _XT_TRADER_AVAILABLE:
            return False

        try:
            trader = self._traders[account_id]
            config = self._accounts[account_id]
            account = StockAccount(config.account_id, config.account_type)

            order_id = trader.order_stock(account, code, xtconstant.STOCK_SELL, volume,
                                          xtconstant.LATEST_PRICE_FIFTH, price,
                                          strategy_name=strategy_name, order_remark=remark)
            if order_id == -1:
                print(f"[{config.label}] 下单失败: {code} {volume}股 @ {price}")
                return False

            print(f"[{config.label}] 下单成功: {code} {volume}股 @ {price}, 订单号={order_id}")
            return True

        except Exception as e:
            print(f"[{account_id}] 卖出异常: {e}")
            return False

    def cancel_order(self, account_id: str, order_id: int) -> bool:
        """
        撤单

        根据 XTquant 官方文档，cancel_order 需要传入 order_id 和 account 两个参数。

        参数:
            account_id: 账号ID
            order_id:   待撤销的委托单号（由下单方法返回）

        返回:
            bool: 撤单成功返回 True（cancel_order 返回 0 表示成功）
        """
        if account_id not in self._traders or not self._connected.get(account_id):
            return False

        if not _XT_TRADER_AVAILABLE:
            return False

        try:
            trader = self._traders[account_id]
            config = self._accounts[account_id]
            account = StockAccount(config.account_id, config.account_type)
            result = trader.cancel_order(order_id, account)
            return result == 0
        except Exception as e:
            print(f"[{account_id}] 撤单异常: {e}")
            return False

    def query_positions(self, account_id: str) -> list[dict]:
        """
        查询持仓

        参数:
            account_id: 账号ID

        返回:
            list[dict]: 持仓明细列表，每条包含:
                stock_code/can_use_volume/open_price/market_value/volume
        """
        if account_id not in self._traders or not self._connected.get(account_id):
            return []

        if not _XT_TRADER_AVAILABLE:
            return []

        try:
            trader = self._traders[account_id]
            config = self._accounts[account_id]
            account = StockAccount(config.account_id, config.account_type)

            positions = trader.query_stock_positions(account)
            result = []
            for pos in positions:
                result.append({
                    'stock_code': pos.stock_code,
                    'volume': pos.volume,
                    'can_use_volume': pos.can_use_volume,
                    'open_price': pos.open_price,
                    'market_value': pos.market_value,
                })
            return result
        except Exception as e:
            print(f"[{account_id}] 查询持仓异常: {e}")
            return []

    def query_orders(self, account_id: str) -> list[dict]:
        """
        查询当日委托

        参数:
            account_id: 账号ID

        返回:
            list[dict]: 当日委托列表，每条包含:
                order_id/stock_code/order_volume/traded_volume/price/order_type/status
        """
        if account_id not in self._traders or not self._connected.get(account_id):
            return []

        if not _XT_TRADER_AVAILABLE:
            return []

        try:
            trader = self._traders[account_id]
            config = self._accounts[account_id]
            account = StockAccount(config.account_id, config.account_type)

            orders = trader.query_stock_orders(account)
            result = []
            for order in orders:
                result.append({
                    'order_id': order.order_id,
                    'stock_code': order.stock_code,
                    'order_volume': order.order_volume,
                    'traded_volume': order.traded_volume,
                    'price': order.price,
                    'order_type': order.order_type,
                    'status': order.order_status,
                })
            return result
        except Exception as e:
            print(f"[{account_id}] 查询委托异常: {e}")
            return []

    def query_trades(self, account_id: str) -> list[dict]:
        """
        查询当日成交

        参数:
            account_id: 账号ID

        返回:
            list[dict]: 当日成交列表，每条包含:
                order_id/stock_code/traded_volume/traded_price/traded_time
        """
        if account_id not in self._traders or not self._connected.get(account_id):
            return []

        if not _XT_TRADER_AVAILABLE:
            return []

        try:
            trader = self._traders[account_id]
            config = self._accounts[account_id]
            account = StockAccount(config.account_id, config.account_type)

            trades = trader.query_stock_trades(account)
            result = []
            for t in trades:
                result.append({
                    'order_id': t.order_id,
                    'stock_code': t.stock_code,
                    'traded_volume': t.traded_volume,
                    'traded_price': t.traded_price,
                    'traded_time': t.traded_time,
                })
            return result
        except Exception as e:
            print(f"[{account_id}] 查询成交异常: {e}")
            return []

    def query_asset(self, account_id: str) -> dict | None:
        """
        查询账户资产

        参数:
            account_id: 账号ID

        返回:
            dict | None: 资产信息，包含:
                account_id/total_asset/available_cash/market_value
                未连接或查询失败返回 None
        """
        if account_id not in self._traders or not self._connected.get(account_id):
            return None

        if not _XT_TRADER_AVAILABLE:
            return None

        try:
            trader = self._traders[account_id]
            config = self._accounts[account_id]
            account = StockAccount(config.account_id, config.account_type)

            asset = trader.query_stock_asset(account)
            return {
                'account_id': account_id,
                'total_asset': asset.total_asset,
                'available_cash': asset.cash,
                'market_value': asset.market_value,
            }
        except Exception as e:
            print(f"[{account_id}] 查询资产异常: {e}")
            return None

    def is_connected(self, account_id: str) -> bool:
        """检查指定账号是否处于连接状态"""
        return self._connected.get(account_id, False)

    def get_connected_accounts(self) -> list[str]:
        """获取当前所有已连接账号的 ID 列表"""
        return [aid for aid, connected in self._connected.items() if connected]

    def disconnect_all(self):
        """断开所有交易连接并清理资源"""
        for aid, trader in self._traders.items():
            try:
                trader.stop()
            except Exception as e:
                print(f"[{aid}] 断开连接异常: {e}")
        self._traders.clear()
        self._callbacks.clear()
        self._connected.clear()
