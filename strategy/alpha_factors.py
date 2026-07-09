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
    "turnover_5d":       {"category": "流动性",   "desc": "5日均量环比变化率"},
}

# ──── qlib 因子表达式定义 ────
# 对应现有 research/factors.py 中的计算逻辑
# 注意：QLIB_FACTOR_EXPRESSIONS / QLIB_FACTOR_NAMES 必须与 FACTOR_META 的 22 个
# 因子完全对齐，否则 qlib 模式与 pandas 模式特征不一致，模型在两模式间切换会错位。
QLIB_FACTOR_EXPRESSIONS = [
    # 动量类：今日收盘 / N日前收盘 - 1
    # P0-3a 修复：旧代码用 Ref($close, -1)（未来值）计算收益率，方向反了。
    # qlib 中 Ref(x, n>0) = n期前的值（过去），Ref(x, n<0) = n期后的值（未来）。
    # 收益率 = 今日 / 过去 - 1，应使用正数 Ref。
    "$close / Ref($close, 1) - 1",                                        # ret_1d
    "$close / Ref($close, 5) - 1",                                        # ret_5d
    "$close / Ref($close, 10) - 1",                                       # ret_10d
    "$close / Ref($close, 20) - 1",                                       # ret_20d
    "$close / Ref($close, 60) - 1",                                       # ret_60d
    # 波动率类
    "Std($close / Ref($close, 1) - 1, 5)",                                # std_5d
    "Std($close / Ref($close, 1) - 1, 20)",                               # std_20d
    "Mean(($high - $low) / $close, 20)",                                   # hl_amplitude_20d
    # 量价类
    "Mean($volume, 5) / (Mean($volume, 20) + 1e-8)",                      # vol_ratio_5_20
    "Mean($volume, 5) / (Mean($volume, 60) + 1e-8)",                      # vol_ratio_5_60
    "Mean($volume, 10) / (Mean($volume, 60) + 1e-8)",                      # volume_trend_10d
    # 均线偏离类
    "$close / Mean($close, 5) - 1",                                       # ma5_dev
    "$close / Mean($close, 10) - 1",                                      # ma10_dev
    "$close / Mean($close, 20) - 1",                                      # ma20_dev
    "$close / Mean($close, 60) - 1",                                      # ma60_dev
    # 技术指标类
    "RSI($close, 14)",                                                     # rsi_14
    # MACD：qlib 无内置 MACD 算子，用 EMA 表达式实现
    # DIF = EMA(close,12) - EMA(close,26)
    "EMA($close, 12) - EMA($close, 26)",                                  # macd_dif
    # Signal = EMA(DIF, 9)
    "EMA(EMA($close, 12) - EMA($close, 26), 9)",                           # macd_signal
    # Hist = (DIF - Signal) * 2  （与 pandas 版 _calc_macd 的 *2 保持一致）
    "(EMA($close, 12) - EMA($close, 26) - EMA(EMA($close, 12) - EMA($close, 26), 9)) * 2",  # macd_hist
    # 布林带位置：(close - MA20) / (Std20 * 2)，归一化到 [-1, 1] 区间
    "($close - Mean($close, 20)) / (Std($close, 20) * 2 + 1e-8)",          # bb_position
    # 反转类
    "-($close / Ref($close, 3) - 1)",                                     # reversal_3d
    # 流动性类：5日均量相对前一日的环比变化率（与 pandas 版一致）
    "Mean($volume, 5) / Ref(Mean($volume, 5), 1) - 1",                      # turnover_5d
]

# 因子名清单——顺序与 QLIB_FACTOR_EXPRESSIONS 一一对应
QLIB_FACTOR_NAMES = [
    "ret_1d", "ret_5d", "ret_10d", "ret_20d", "ret_60d",
    "std_5d", "std_20d", "hl_amplitude_20d",
    "vol_ratio_5_20", "vol_ratio_5_60", "volume_trend_10d",
    "ma5_dev", "ma10_dev", "ma20_dev", "ma60_dev",
    "rsi_14",
    "macd_dif", "macd_signal", "macd_hist",
    "bb_position", "reversal_3d", "turnover_5d",
]

# 断言：两模式因子必须对齐，防止再次出现 22 vs 15 的不一致
assert len(QLIB_FACTOR_NAMES) == len(QLIB_FACTOR_EXPRESSIONS), \
    "QLIB_FACTOR_NAMES 与 QLIB_FACTOR_EXPRESSIONS 数量不一致"
assert set(QLIB_FACTOR_NAMES) == set(FACTOR_META.keys()), \
    f"qlib 因子名与 FACTOR_META 不一致: " \
    f"仅 qlib 有 {set(QLIB_FACTOR_NAMES) - set(FACTOR_META.keys())}, " \
    f"仅 meta 有 {set(FACTOR_META.keys()) - set(QLIB_FACTOR_NAMES)}"


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
        """使用 qlib D.features() 计算自定义因子（与 pandas 模式一致）

        P0-3a 修复：旧代码直接用 Alpha158（~158 因子），与 pandas 模式的
        22 个自定义因子完全不同，导致 qlib/pandas 模式切换时特征集错位、
        模型失效。改为使用 QLIB_FACTOR_EXPRESSIONS 通过 D.features() 计算
        与 pandas 模式完全对齐的 22 个因子 + forward_ret_5d 标签。
        """
        self._init_qlib()

        from qlib.data import D

        start = self.start_time or "2010-01-01"
        end = self.end_time or "2025-12-31"

        # 使用自定义因子表达式，确保与 pandas 模式产出完全一致
        # 标签：未来5日收益率 Ref($close, -5) / $close - 1（负数 Ref 取未来值）
        label_expr = "Ref($close, -5) / $close - 1"
        fields = QLIB_FACTOR_EXPRESSIONS + [label_expr]
        names = QLIB_FACTOR_NAMES + ["forward_ret_5d"]

        factors = D.features(
            instruments=self.instruments,
            fields=fields,
            start_time=start,
            end_time=end,
        )
        # D.features 返回的列名为表达式字符串，重命名为因子名
        factors.columns = names

        # 与 pandas 模式一致：丢弃因滚动窗口不足产生 NaN 的行
        factors = factors.dropna()

        self._factors = factors
        return factors

    def _load_factors_pandas(self) -> pd.DataFrame:
        """使用 pandas 从 Parquet 数据批量向量化计算因子

        P2 架构优化：
        - 用 ThreadPoolExecutor 并行加载 Parquet（替代串行逐股读）
        - 用 df.assign(code=code) 替代 df.copy() + df['code']=code
        - 分块计算因子：每批 500 股加载→计算因子→append，避免全量 concat 内存峰值
        """
        from data.database import Database
        from concurrent.futures import ThreadPoolExecutor, as_completed

        db = Database()
        db.connect()

        all_stocks = db.get_all_stocks()
        codes = [s['code'] for s in all_stocks]
        max_stocks = getattr(self, '_max_stocks', None) or len(codes)
        codes = codes[:max_stocks]

        factor_columns = ['date', 'open', 'high', 'low', 'close', 'volume']

        # P2 优化：并行预加载 DataFrame
        def _read_one(code):
            df = db.get_daily_kline_df(code, '1d', self.start_time, self.end_time,
                                       columns=factor_columns)
            if df.empty or len(df) < 120:
                return code, None
            # P2 优化：用 assign 替代 copy + 赋值，少一次内存拷贝
            return code, df.assign(code=code)

        loaded_frames = []
        max_workers = min(8, len(codes)) if len(codes) > 1 else 1
        if max_workers > 1:
            with ThreadPoolExecutor(max_workers=max_workers) as executor:
                futures = {executor.submit(_read_one, c): c for c in codes}
                for future in as_completed(futures):
                    code, df = future.result()
                    if df is not None:
                        loaded_frames.append(df)
        else:
            for code in codes:
                c, df = _read_one(code)
                if df is not None:
                    loaded_frames.append(df)

        db.close()

        if not loaded_frames:
            self._factors = pd.DataFrame()
            return self._factors

        # P2 优化：分块计算因子，避免全量 concat 内存峰值
        # 每批 500 股：concat → 计算因子 → dropna → 收集结果
        batch_size = 500
        result_parts = []

        for i in range(0, len(loaded_frames), batch_size):
            batch = loaded_frames[i:i + batch_size]
            combined = pd.concat(batch, ignore_index=True)
            combined = self._compute_factors(combined)
            if not combined.empty:
                result_parts.append(combined)

        if not result_parts:
            self._factors = pd.DataFrame()
            return self._factors

        # 最终合并各批结果
        result = pd.concat(result_parts, ignore_index=False)
        result = result.sort_index()

        self._factors = result
        return result

    def _compute_factors(self, combined: pd.DataFrame) -> pd.DataFrame:
        """对合并后的 DataFrame 计算全部因子，返回 set_index 后的结果。

        从 _load_factors_pandas 抽取，支持分块调用。
        """
        combined = combined.sort_values(['code', 'date']).reset_index(drop=True)
        combined['close'] = combined['close'].astype(float)
        combined['high'] = combined.get('high', combined['close']).astype(float)
        combined['low'] = combined.get('low', combined['close']).astype(float)
        combined['volume'] = combined['volume'].astype(float)

        g = combined.groupby('code', group_keys=False)
        close = combined['close']

        # 动量类
        for w, name in [(1, 'ret_1d'), (5, 'ret_5d'), (10, 'ret_10d'),
                        (20, 'ret_20d'), (60, 'ret_60d')]:
            combined[name] = g['close'].transform(lambda s: s.pct_change(w))

        # 波动率类
        daily_ret = g['close'].transform(lambda s: s.pct_change())
        combined['std_5d'] = daily_ret.rolling(5).std()
        combined['std_20d'] = daily_ret.rolling(20).std()
        combined['_hl_ratio'] = (combined['high'] - combined['low']) / (close + 1e-8)
        combined['hl_amplitude_20d'] = g['_hl_ratio'].transform(lambda s: s.rolling(20).mean())
        combined = combined.drop(columns=['_hl_ratio'])

        # 量价类
        vol_ma5 = g['volume'].transform(lambda s: s.rolling(5).mean())
        vol_ma20 = g['volume'].transform(lambda s: s.rolling(20).mean())
        vol_ma60 = g['volume'].transform(lambda s: s.rolling(60).mean())
        combined['vol_ratio_5_20'] = vol_ma5 / (vol_ma20 + 1e-8)
        combined['vol_ratio_5_60'] = vol_ma5 / (vol_ma60 + 1e-8)

        # 均线偏离类
        for w in [5, 10, 20, 60]:
            ma = g['close'].transform(lambda s: s.rolling(w).mean())
            combined[f'ma{w}_dev'] = close / ma - 1

        # 技术指标类
        combined['rsi_14'] = g['close'].transform(lambda s: self._calc_rsi(s, 14))

        def _calc_macd_cols(s):
            dif, dea, hist = FactorHandler._calc_macd(s)
            return pd.DataFrame({'dif': dif, 'dea': dea, 'hist': hist}, index=s.index)
        macd_result = g['close'].apply(_calc_macd_cols)
        combined['macd_dif'] = macd_result['dif']
        combined['macd_signal'] = macd_result['dea']
        combined['macd_hist'] = macd_result['hist']

        combined['bb_position'] = g['close'].transform(self._calc_bb_position)

        # 反转 / 流动性
        combined['reversal_3d'] = g['close'].transform(lambda s: -s.pct_change(3))
        vol_ma5_shift1 = g['volume'].transform(lambda s: s.rolling(5).mean().shift(1))
        combined['turnover_5d'] = vol_ma5 / (vol_ma5_shift1 + 1e-8)

        # 训练标签
        combined['forward_ret_5d'] = g['close'].transform(lambda s: s.shift(-5) / s - 1)

        result = combined.dropna()
        result = result.set_index(['date', 'code'])
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
