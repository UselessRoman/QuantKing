# -*- coding: utf-8 -*-
"""
qlib 因子处理模块

基于 qlib 框架定义多因子表达式，计算 Alpha 因子值。
支持 Alpha158 和自定义因子表达式。

qlib 因子表达式语法:
    $close          — 收盘价
    $open           — 开盘价
    $high           — 最高价
    $low            — 最低价
    $volume         — 成交量
    Ref(x, n)       — n 期前的 x 值
    Mean(x, n)      — x 的 n 期均值
    Std(x, n)       — x 的 n 期标准差
    Max(x, n)       — x 的 n 期最大值
    Min(x, n)       — x 的 n 期最小值
    Corr(x, y, n)   — x 和 y 的 n 期相关系数
    Rank(x)         — 截面排名
    $x / $y - 1     — 比值减1（偏离率）

使用方式:
    from strategy.alpha_factors import FactorHandler
    handler = FactorHandler(start_time="2023-01-01", end_time="2023-12-31")
    factors = handler.load_factors()
    names = handler.get_factor_names()
"""
import pandas as pd
import numpy as np
from typing import Optional

# 因子元信息定义 — 与现有 research/factors.py 保持一致
FACTOR_META = {
    "ret_1d":            {"category": "动量",     "desc": "1日收益率"},
    "ret_5d":            {"category": "动量",     "desc": "5日收益率"},
    "ret_10d":           {"category": "动量",     "desc": "10日收益率"},
    "ret_20d":           {"category": "动量",     "desc": "20日收益率"},
    "ret_60d":           {"category": "动量",     "desc": "60日收益率"},
    "std_5d":            {"category": "波动率",   "desc": "5日收益率标准差"},
    "std_20d":           {"category": "波动率",   "desc": "20日收益率标准差"},
    "hl_amplitude_20d":  {"category": "波动率",   "desc": "20日平均振幅"},
    "vol_ratio_5_20":    {"category": "量价",     "desc": "5日均量/20日均量"},
    "vol_ratio_5_60":    {"category": "量价",     "desc": "5日均量/60日均量"},
    "volume_trend_10d":  {"category": "量价",     "desc": "10日量能趋势"},
    "ma5_dev":           {"category": "均线偏离", "desc": "收盘价/MA5 - 1"},
    "ma10_dev":          {"category": "均线偏离", "desc": "收盘价/MA10 - 1"},
    "ma20_dev":          {"category": "均线偏离", "desc": "收盘价/MA20 - 1"},
    "ma60_dev":          {"category": "均线偏离", "desc": "收盘价/MA60 - 1"},
    "rsi_14":            {"category": "技术指标", "desc": "14日 RSI"},
    "macd_dif":          {"category": "技术指标", "desc": "MACD DIF 线"},
    "macd_signal":       {"category": "技术指标", "desc": "MACD Signal 线"},
    "macd_hist":         {"category": "技术指标", "desc": "MACD 柱"},
    "bb_position":       {"category": "技术指标", "desc": "布林带位置"},
    "reversal_3d":       {"category": "反转",     "desc": "3日反转信号"},
    "turnover_5d":       {"category": "流动性",   "desc": "5日换手率"},
}

# ──── qlib 因子表达式定义 ────
# 对应现有 research/factors.py 中的计算逻辑
QLIB_FACTOR_EXPRESSIONS = [
    # 动量类
    "Ref($close, -1) / Ref($close, -2) - 1",                              # ret_1d
    "Ref($close, -1) / Ref($close, -6) - 1",                              # ret_5d
    "Ref($close, -1) / Ref($close, -11) - 1",                             # ret_10d
    "Ref($close, -1) / Ref($close, -21) - 1",                             # ret_20d
    "Ref($close, -1) / Ref($close, -61) - 1",                             # ret_60d
    # 波动率类
    "Std(Ref($close, -1) / Ref($close, -2) - 1, 5)",                      # std_5d
    "Std(Ref($close, -1) / Ref($close, -2) - 1, 20)",                     # std_20d
    "Mean(($high - $low) / $close, 20)",                                   # hl_amplitude_20d
    # 量价类
    "Mean($volume, 5) / (Mean($volume, 20) + 1e-8)",                      # vol_ratio_5_20
    "Mean($volume, 5) / (Mean($volume, 60) + 1e-8)",                      # vol_ratio_5_60
    # 均线偏离类
    "$close / Mean($close, 5) - 1",                                       # ma5_dev
    "$close / Mean($close, 10) - 1",                                      # ma10_dev
    "$close / Mean($close, 20) - 1",                                      # ma20_dev
    "$close / Mean($close, 60) - 1",                                      # ma60_dev
    # 技术指标类
    "RSI($close, 14)",                                                     # rsi_14
]

QLIB_FACTOR_NAMES = [
    "ret_1d", "ret_5d", "ret_10d", "ret_20d", "ret_60d",
    "std_5d", "std_20d", "hl_amplitude_20d",
    "vol_ratio_5_20", "vol_ratio_5_60",
    "ma5_dev", "ma10_dev", "ma20_dev", "ma60_dev",
    "rsi_14",
]


class FactorHandler:
    """
    qlib 因子处理器

    封装 qlib 数据加载和因子计算流程，提供统一的因子获取接口。

    属性:
        instruments: 股票池，如 'all' / 'csi300' / ['000001.SZ', ...]
        start_time:  数据起始时间
        end_time:    数据结束时间
        _factors:    缓存的计算结果 DataFrame
    """

    def __init__(
        self,
        instruments: str = 'all',
        start_time: str = '',
        end_time: str = ''
    ):
        """
        参数:
            instruments: 股票范围，qlib 格式如 'all', 'csi300' 或自定义列表
            start_time:  起始日期 YYYYMMDD
            end_time:    结束日期 YYYYMMDD
        """
        self.instruments = instruments
        self.start_time = start_time
        self.end_time = end_time
        self._factors: Optional[pd.DataFrame] = None
        self._qlib_initialized = False

    def _init_qlib(self):
        """初始化 qlib 环境"""
        if self._qlib_initialized:
            return
        try:
            import qlib
            from qlib.config import REG_CN
            from config.settings import QLIB_DATA_DIR

            provider_uri = str(QLIB_DATA_DIR)
            qlib.init(provider_uri=provider_uri, region=REG_CN)
            self._qlib_initialized = True
        except ImportError:
            raise ImportError("请安装 qlib: pip install pyqlib")
        except Exception as e:
            raise RuntimeError(f"qlib 初始化失败: {e}\n请先运行 scripts/convert_to_qlib.py 转换数据")

    def load_factors(self, use_qlib: bool = True) -> pd.DataFrame:
        """
        加载因子数据

        支持两种模式:
            - qlib 模式: 使用 qlib DataHandler 计算因子（需要 qlib 数据）
            - pandas 模式: 使用本地 Parquet 数据 + 手写因子计算（不需要 qlib）

        参数:
            use_qlib: 是否使用 qlib 模式（默认 True）

        返回:
            pd.DataFrame: 因子数据，MultiIndex (datetime, instrument) × factor_names
        """
        if use_qlib:
            try:
                return self._load_factors_qlib()
            except Exception as e:
                print(f"qlib 模式失败 ({e})，回退到 pandas 模式")
                return self._load_factors_pandas()

        return self._load_factors_pandas()

    def _load_factors_qlib(self) -> pd.DataFrame:
        """使用 qlib DataHandler 计算因子"""
        self._init_qlib()

        from qlib.data import D
        from qlib.data.dataset.handler import DataHandlerLP

        # 配置 qlib DataHandler
        handler_config = {
            "start_time": self.start_time or "2010-01-01",
            "end_time": self.end_time or "2025-12-31",
            "fit_start_time": self.start_time or "2010-01-01",
            "fit_end_time": self.end_time or "2025-12-31",
            "instruments": self.instruments,
        }

        # 尝试使用 Alpha158 因子集
        try:
            from qlib.contrib.data.handler import Alpha158
            handler = Alpha158(**handler_config)
            factors = handler.fetch(col_set="feature")
            self._factors = factors
            return factors
        except ImportError:
            pass

        # 回退到 DataHandlerLP
        try:
            handler = DataHandlerLP(
                **handler_config,
                data_loader_kwargs={"backend": {"class": "DataLoader"}},
            )
            factors = handler.fetch(col_set="feature")
            self._factors = factors
            return factors
        except Exception:
            raise

    def _load_factors_pandas(self) -> pd.DataFrame:
        """使用 pandas 从 Parquet 数据批量向量化计算因子"""
        from data.database import Database
        from concurrent.futures import ThreadPoolExecutor, as_completed

        db = Database()
        db.connect()

        all_stocks = db.get_all_stocks()
        codes = [s['code'] for s in all_stocks]
        max_stocks = getattr(self, '_max_stocks', None) or len(codes)
        codes = codes[:max_stocks]

        # 批量加载所有股票数据并合并为一个大 DataFrame
        all_frames = []
        for code in codes:
            df = db.get_daily_kline_df(code, '1d', self.start_time, self.end_time)
            if df.empty or len(df) < 120:
                continue
            df = df.copy()
            df['code'] = code
            all_frames.append(df)

        db.close()

        if not all_frames:
            self._factors = pd.DataFrame()
            return self._factors

        # 合并为统一 DataFrame: (date, code) + OHLCV
        combined = pd.concat(all_frames, ignore_index=True)

        # 向量化计算因子：按 code 分组，每组内按 date 排序后计算
        def _compute_group(grp: pd.DataFrame) -> pd.DataFrame:
            grp = grp.sort_values('date')
            close = grp['close'].astype(float)
            high = grp.get('high', close).astype(float)
            low = grp.get('low', close).astype(float)
            volume = grp['volume'].astype(float)

            r = pd.DataFrame(index=grp.index)
            r['date'] = grp['date'].values
            r['code'] = grp['code'].values

            r['ret_1d'] = close.pct_change(1)
            r['ret_5d'] = close.pct_change(5)
            r['ret_10d'] = close.pct_change(10)
            r['ret_20d'] = close.pct_change(20)
            r['ret_60d'] = close.pct_change(60)

            daily_ret = close.pct_change()
            r['std_5d'] = daily_ret.rolling(5).std()
            r['std_20d'] = daily_ret.rolling(20).std()
            r['hl_amplitude_20d'] = ((high - low) / (close + 1e-8)).rolling(20).mean()

            r['vol_ratio_5_20'] = volume.rolling(5).mean() / (volume.rolling(20).mean() + 1e-8)
            r['vol_ratio_5_60'] = volume.rolling(5).mean() / (volume.rolling(60).mean() + 1e-8)

            for w in [5, 10, 20, 60]:
                r[f'ma{w}_dev'] = close / close.rolling(w).mean() - 1

            r['rsi_14'] = self._calc_rsi(close, 14)
            dif, dea, hist = self._calc_macd(close)
            r['macd_dif'] = dif
            r['macd_signal'] = dea
            r['macd_hist'] = hist
            r['bb_position'] = self._calc_bb_position(close)
            r['reversal_3d'] = -close.pct_change(3)
            r['turnover_5d'] = volume.rolling(5).mean() / (volume.rolling(5).mean().shift(1) + 1e-8)

            return r

        # 使用 groupby 批量计算（比逐只循环快 5x+）
        result = combined.groupby('code', group_keys=False).apply(_compute_group)
        result = result.dropna()
        result = result.set_index(['date', 'code'])

        self._factors = result
        return result

    @staticmethod
    def _calc_rsi(close: pd.Series, period: int = 14) -> pd.Series:
        delta = close.diff()
        gain = delta.where(delta > 0, 0.0)
        loss = (-delta).where(delta < 0, 0.0)
        avg_gain = gain.ewm(alpha=1 / period, adjust=False).mean()
        avg_loss = loss.ewm(alpha=1 / period, adjust=False).mean()
        rs = avg_gain / avg_loss.replace(0, np.nan)
        return 100.0 - (100.0 / (1.0 + rs))

    @staticmethod
    def _calc_macd(close: pd.Series, fast: int = 12, slow: int = 26, signal: int = 9):
        ema_fast = close.ewm(span=fast, adjust=False).mean()
        ema_slow = close.ewm(span=slow, adjust=False).mean()
        dif = ema_fast - ema_slow
        dea = dif.ewm(span=signal, adjust=False).mean()
        hist = 2 * (dif - dea)
        return dif, dea, hist

    @staticmethod
    def _calc_bb_position(close: pd.Series, period: int = 20, num_std: float = 2.0) -> pd.Series:
        mid = close.rolling(period).mean()
        std = close.rolling(period).std()
        upper = mid + num_std * std
        lower = mid - num_std * std
        pos = (close - lower) / (upper - lower + 1e-8)
        return pos.clip(0, 1)

    def get_factor_names(self) -> list[str]:
        """获取当前使用的因子名称列表"""
        if self._factors is not None and not self._factors.empty:
            # DataFrame 列名即为因子名
            cols = list(self._factors.columns)
            # 过滤掉可能的元数据列
            return [c for c in cols if c in FACTOR_META]
        return list(FACTOR_META.keys())

    def get_factor_meta(self) -> dict:
        """获取因子元信息（类别和描述）"""
        return FACTOR_META
