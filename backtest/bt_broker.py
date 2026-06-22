# -*- coding: utf-8 -*-
"""
backtrader A股佣金方案模块

实现 A 股市场交易费率，包括佣金、印花税和过户费。

费率说明:
    佣金费率:  0.025%（万2.5），最低 5 元（买卖双向）
    印花税率:  0.1%（千1），仅卖出收取
    过户费:    0.001%（万0.1），沪市双向收取（深市无）

使用方式:
    from backtest.bt_broker import AShareCommission
    cerebro.broker.addcommissioninfo(AShareCommission())
"""
import backtrader as bt


class AShareCommission(bt.CommInfoBase):
    """
    A 股佣金方案

    继承 backtrader 的 CommInfoBase，实现符合 A 股市场规则的佣金计算。

    参数:
        commission:    佣金费率（默认万2.5）
        stamp_duty:    印花税率（默认千1，仅卖出）
        transfer_fee:  过户费率（默认万0.1，仅沪市双向）
        min_commission: 最低佣金（默认5元）
        stocklike:      True 表示股票类交易
        commtype:       CommInfoBase.COMM_PERC 按比例计算佣金
    """
    params = (
        ('commission', 0.00025),      # 佣金费率: 万2.5
        ('stamp_duty', 0.001),        # 印花税: 千1（仅卖出）
        ('transfer_fee', 0.00001),    # 过户费: 万0.1（沪市双向）
        ('min_commission', 5.0),      # 最低佣金: 5元
        ('stocklike', True),
        ('commtype', bt.CommInfoBase.COMM_PERC),
        ('percabs', True),            # 佣金按绝对值百分比计算
    )

    def _getcommission(self, size: float, price: float, pseudoexec: bool) -> float:
        """
        计算单笔交易的佣金

        参数:
            size:       交易数量（正=买入，负=卖出）
            price:      成交价格
            pseudoexec: 是否为伪执行

        返回:
            float: 佣金金额（含印花税、过户费）
        """
        abs_size = abs(size)
        amount = abs_size * price
        commission = max(amount * self.p.commission, self.p.min_commission)

        # 卖出时额外收取印花税
        if size < 0:
            stamp = amount * self.p.stamp_duty
            commission += stamp

        # 过户费：沪市双向收取。data._name 形如 "600000.SH"。
        # 注意：backtrader 调用 _getcommission 时不传 data，无法在此判断
        # 沪深，故统一按沪深都收取（深市实际无过户费，金额极小可忽略）。
        # 精确区分需在策略层按 code 判断后调整，此处为统一近似。
        transfer = amount * self.p.transfer_fee
        commission += transfer

        return commission


class AShareSizer(bt.Sizer):
    """
    A 股仓位调整器

    根据资金比例计算每笔交易的买入数量，自动调整为 100 的整数倍。

    参数:
        perc: 每笔交易使用的资金比例（默认 0.1 = 10%）
    """
    params = (
        ('perc', 0.1),
    )

    def _getsizing(self, comminfo, cash, data, isbuy):
        if not isbuy:
            return self.broker.getposition(data).size

        price = data.close[0]
        available = cash * self.p.perc
        size = int(available / price / 100) * 100
        return max(size, 100)
