# -*- coding: utf-8 -*-
"""
信号生成模块

基于模型预测结果生成选股和调仓信号。

信号类型:
    - Top-K 选股: 按预测分数排序，选取前 K 只
    - 阈值过滤: 仅选取分数超过指定阈值的股票
    - 行业中性化: 在各行业内分别选股（需要板块数据支持）

使用方式:
    from strategy.signal_generator import SignalGenerator

    sg = SignalGenerator()
    predictions = trainer.predict(handler)
    buy_list = sg.generate(predictions, top_k=20)
    orders = sg.generate_with_risk_control(predictions, positions, top_k=20)
"""
from typing import Optional
import pandas as pd
import numpy as np


class SignalGenerator:
    """
    信号生成器

    将 qlib 模型预测分数转换为具体的选股列表和调仓指令。
    支持 Top-K 选股、阈值过滤、行业中性化等策略。

    属性:
        _cache: 信号缓存 {date: [codes]}
    """

    def __init__(self):
        self._cache: dict = {}

    def generate(
        self,
        predictions: pd.Series,
        top_k: int = 20,
        min_score: Optional[float] = None,
        blacklist: Optional[list[str]] = None,
    ) -> pd.DataFrame:
        """
        生成 Top-K 选股信号

        按预测分数从高到低排序，选取前 K 只股票。

        参数:
            predictions: 预测分数 Series，index 包含日期和股票代码信息
            top_k:       选股数量
            min_score:   最低分数阈值，低于此值的股票不入选
            blacklist:   黑名单股票列表

        返回:
            pd.DataFrame: 选股结果，列: date/code/score/rank
        """
        if predictions is None or len(predictions) == 0:
            return pd.DataFrame()

        if isinstance(predictions, pd.DataFrame):
            pred_series = predictions.iloc[:, 0]
        else:
            pred_series = predictions

        # 处理 MultiIndex
        results = []
        if isinstance(pred_series.index, pd.MultiIndex):
            # 按日期分组处理
            dates = pred_series.index.get_level_values(0).unique()
            for date in dates:
                day_preds = pred_series.xs(date, level=0)
                day_stocks = self._select_top_k(day_preds, top_k, min_score, blacklist)
                for rank, (code, score) in enumerate(day_stocks):
                    results.append({'date': str(date), 'code': code, 'score': score, 'rank': rank + 1})
        else:
            # 单日预测
            day_stocks = self._select_top_k(pred_series, top_k, min_score, blacklist)
            for rank, (code, score) in enumerate(day_stocks):
                results.append({'date': 'latest', 'code': code, 'score': score, 'rank': rank + 1})

        df = pd.DataFrame(results)
        if not df.empty:
            df = df.sort_values(['date', 'rank'])

        # P2 修复：实现 _cache 写入，使 get_latest_signals() 正常工作
        # 旧代码 _cache 声明了但 generate() 从未写入，get_latest_signals() 永远返回空
        if not df.empty:
            for date, group in df.groupby('date'):
                self._cache[str(date)] = group.reset_index(drop=True)

        return df

    def _select_top_k(
        self,
        pred_series: pd.Series,
        top_k: int,
        min_score: Optional[float],
        blacklist: Optional[list[str]],
    ) -> list[tuple]:
        """单日 Top-K 选股"""
        valid = pred_series.dropna()
        if min_score is not None:
            valid = valid[valid >= min_score]
        if blacklist:
            valid = valid[~valid.index.isin(blacklist)]
        return valid.nlargest(top_k).items() if len(valid) > 0 else []

    def generate_with_risk_control(
        self,
        predictions: pd.Series,
        positions: dict[str, dict],
        top_k: int = 20,
        max_turnover: float = 0.5,
    ) -> dict[str, str]:
        """
        生成带风险控制的调仓指令

        基于现有持仓和预测信号，生成具体的买卖指令。
        控制换手率在合理范围内。

        参数:
            predictions:   预测分数
            positions:     当前持仓 {code: {volume, cost, ...}}
            top_k:         目标持仓数量
            max_turnover:  最大换手率（0~1），控制调仓幅度

        返回:
            dict: {code: action}，action 为 "BUY" / "SELL" / "HOLD"
        """
        signals_df = self.generate(predictions, top_k=top_k)
        if signals_df.empty:
            return {}

        latest_signals = signals_df[signals_df['date'] == signals_df['date'].max()]
        target_codes = set(latest_signals['code'].tolist())
        current_codes = set(positions.keys())

        to_buy = target_codes - current_codes
        to_sell = current_codes - target_codes

        changes = len(to_buy) + len(to_sell)
        if changes > top_k * max_turnover:
            # P2 修复：旧代码 list(set) 顺序不确定，可能丢弃高分股。
            # 现按预测分数排序后再截断，优先保留高分买入和低分卖出。
            max_changes = int(top_k * max_turnover)
            # 买入：按分数从高到低排序
            buy_scores = latest_signals[latest_signals['code'].isin(to_buy)].sort_values('score', ascending=False)
            to_buy = set(buy_scores['code'].head(max_changes).tolist())
            # 卖出：当前持仓不在目标中的，按预测分数从低到高排序（优先卖低分）
            sell_preds = predictions.copy()
            if isinstance(sell_preds.index, pd.MultiIndex):
                latest_date = predictions.index.get_level_values(0).max()
                sell_preds = sell_preds.xs(latest_date, level=0) if hasattr(sell_preds, 'xs') else sell_preds
            sell_scores = sell_preds[sell_preds.index.isin(to_sell)].sort_values() if len(sell_preds) > 0 else pd.Series(dtype=float)
            to_sell = set(sell_scores.index[:max_changes].tolist()) if len(sell_scores) > 0 else to_sell

        orders = {}
        for code in to_buy:
            orders[code] = "BUY"
        for code in to_sell:
            orders[code] = "SELL"
        for code in current_codes & target_codes:
            orders[code] = "HOLD"

        return orders

    def filter_by_sector(
        self,
        stock_list: list[str],
        sector_name: str,
        database,
    ) -> list[str]:
        """
        按板块过滤股票列表

        参数:
            stock_list:  待过滤的股票代码列表
            sector_name: 板块名称，如 "沪深300"、"半导体"
            database:    Database 实例（需已连接）

        返回:
            list[str]: 属于该板块的股票代码子集
        """
        if sector_name.lower() == 'all':
            return stock_list
        sector_stocks = database.get_sector_stocks(sector_name)
        return [s for s in stock_list if s in sector_stocks]

    def get_latest_signals(self) -> pd.DataFrame:
        """获取缓存的最新选股信号"""
        if not self._cache:
            return pd.DataFrame()
        latest_date = max(self._cache.keys())
        return self._cache.get(latest_date, pd.DataFrame())
