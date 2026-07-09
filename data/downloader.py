# -*- coding: utf-8 -*-
"""
数据下载模块

提供行情数据从 miniQMT 到本地 SQLite 数据库的批量下载与管理功能。
支持全量下载、并行增量更新和板块数据同步。

▌数据流转:
    miniQMT 服务器
         │ download_history_data()     ← 下载到 XTquant 本地缓存（SDK 强制）
         ▼
    XTquant 本地缓存（xtdata 管理）
         │ get_market_data_ex()         ← 从缓存读取 DataFrame
         ▼
    DataFrame → _kline_to_records()     ← 格式转换
         │
         ▼ insert_daily_kline()         ← 持久化到 Parquet
    Parquet 文件 (data/kline/)

▌并行下载:
    增量更新使用 ThreadPoolExecutor 多线程下载，
    默认 6 线程，可通过 max_workers 参数调节。

▌SQLite 预检索优化:
    每次下载前先从 SQLite 检索已有数据，跳过已覆盖的股票，
    避免对 XTquant 缓存和 SQLite 的重复操作。

典型工作流:
    1. 下载股票基础信息: download_stock_info()
    2. 下载板块数据:     download_sector_data()
    3. 下载K线数据:       download_all_a_stocks()
    4. 日常增量更新:      incremental_update()

使用方式:
    downloader = Downloader()
    downloader.download_stock_info()    # 下载股票列表
    downloader.download_all_a_stocks()  # 下载全部日K线
    downloader.close()
"""
import time
import threading
import pandas as pd
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timedelta
from data.xt_provider import DataProvider
from data.database import Database


# 全局计数器锁（并行模式下保护统计变量）
_stats_lock = threading.Lock()


class Downloader:
    """
    数据下载器

    负责将 miniQMT 行情数据下载并持久化到本地数据库。
    内部持有 DataProvider（行情源）和 Database（存储层）两个对象。
    每个线程需要独立的 DataProvider 实例以复用 XTquant 连接。

    属性:
        provider: 行情数据提供者
        db:       数据库访问层
        max_workers: 并行下载线程数
    """

    def __init__(self, provider: DataProvider | None = None, database: Database | None = None,
                 max_workers: int = 6):
        """
        参数:
            provider: 行情提供者，不传则自动创建默认实例
            database: 数据库对象，不传则自动创建默认实例
            max_workers: 并行下载最大线程数
        """
        self.provider = provider or DataProvider()
        self.max_workers = max_workers
        if database is not None:
            self.db = database
            self._own_db = False
        else:
            self.db = Database()
            self.db.connect()
            self.db.initialize()
            self._own_db = True

    def _create_worker_provider(self):
        """为工作线程创建独立的 DataProvider 实例"""
        return DataProvider()

    def download_all_a_stocks(self, period: str = '1d',
                               start_time: str = '', end_time: str = '') -> int:
        """
        下载全部A股K线数据（带 SQLite 预检索）

        流程:
            1. 从 SQLite 查询每只股票已覆盖的日期范围
            2. 对已有全量数据的股票跳过
            3. 对未覆盖的股票并行执行 download → read → write

        参数:
            period:     周期类型，"1d"（日线）/ "1m"（分钟）等，默认 "1d"
            start_time: 起始日期，YYYYMMDD 格式，空字符串表示全局最早
            end_time:   结束日期，YYYYMMDD 格式，空字符串表示到最新

        返回:
            int: 本次实际下载并写入的股票数量
        """
        codes = self.provider.get_stock_list()
        if not codes:
            print("未获取到股票列表，请确保已连接 miniQMT")
            return 0

        total = len(codes)
        print(f"共 {total} 只股票")

        # P2 优化：批量查询最新日期，替代逐股 N+1 SQL 查询
        latest_dates = self.db.get_latest_kline_dates(codes, period)
        skipped = 0
        to_fetch = []
        for code in codes:
            latest = latest_dates.get(code)
            if latest and (not end_time or latest >= end_time):
                skipped += 1
            else:
                to_fetch.append(code)

        if skipped > 0:
            print(f"跳过已覆盖的 {skipped} 只（SQLite 最新日期 ≥ 目标结束日期）")

        remaining = len(to_fetch)
        print(f"待下载 {remaining} 只股票")
        if remaining == 0:
            return 0

        success_count = 0
        completed = 0

        def _download_one(code: str) -> bool:
            """下载单只股票并写入数据库（工作线程调用）"""
            worker_provider = self._create_worker_provider()
            try:
                worker_provider.download_history(
                    [code], period=period, start_time=start_time, end_time=end_time)
                use_count = -1 if (not start_time and not end_time) else 0
                kline = worker_provider.get_kline(
                    [code], period=period, start_time=start_time, end_time=end_time,
                    count=use_count)
                if kline is not None and not kline.empty:
                    records = self._kline_to_records(code, kline)
                    if records:
                        with _stats_lock:
                            self.db.insert_daily_kline(records)
                        return True
                return False
            except Exception as e:
                print(f"下载 {code} 失败: {e}", flush=True)
                return False
            finally:
                worker_provider.disconnect()

        with ThreadPoolExecutor(max_workers=self.max_workers) as executor:
            futures = {executor.submit(_download_one, code): code for code in to_fetch}
            for future in as_completed(futures):
                completed += 1
                if future.result():
                    success_count += 1
                if completed % 50 == 0 or completed == remaining:
                    print(f"进度: {completed}/{remaining} (成功 {success_count})", flush=True)

        print(f"下载完成: 本次新增 {success_count}/{remaining} 只股票 (共 {total} 只, 跳过 {skipped} 只)", flush=True)
        return success_count

    def download_stock_info(self) -> int:
        """
        下载全部A股股票基础信息（带 SQLite 预检索）

        仅对 SQLite 中不存在的股票查询详情，已存在的不重复获取。

        返回:
            int: 本次新增的股票记录数量
        """
        codes = self.provider.get_stock_list()
        existing = {s['code'] for s in self.db.get_all_stocks()}
        new_codes = [c for c in codes if c not in existing]

        skipped = len(codes) - len(new_codes)
        if skipped:
            print(f"跳过已入库的 {skipped} 只股票")

        records: list[dict] = []
        for code in new_codes:
            try:
                info = self.provider.get_instrument_detail(code)
                records.append({
                    'code': code,
                    'name': info.get('InstrumentName', ''),
                    'listing_date': info.get('OpenDate', ''),
                    'status': '正常'
                })
            except Exception:
                records.append({'code': code, 'name': '', 'listing_date': '', 'status': '正常'})

        if records:
            self.db.upsert_stocks(records)
        print(f"股票信息: 本次新增 {len(records)} 只 (共 {len(codes)} 只, 跳过 {skipped} 只)")
        return len(records)

    def download_sector_data(self) -> None:
        """
        下载全部板块分类数据

        从 miniQMT 获取所有板块及其成分股，写入 sectors 表。
        覆盖已有的板块数据。
        """
        self.provider.download_sector_data()
        sector_list = self.provider.get_sector_list()
        for sector_name in sector_list:
            try:
                stocks = self.provider.get_stock_list_in_sector(sector_name)
                if stocks:
                    self.db.insert_sector_records(sector_name, stocks)
            except Exception as e:
                print(f"下载板块 {sector_name} 失败: {e}")

    def incremental_update(self, period: str = '1d', days: int = 5) -> int:
        """
        增量更新K线数据（并行下载）

        流程:
            1. 对每只股票查 SQLite 最新日期
            2. 若最新日期已覆盖到今天，跳过
            3. 对未覆盖的股票并行执行增量下载 + 写入

        参数:
            period: 周期类型，默认 "1d"
            days:   获取最近多少天的数据，默认 5 天

        返回:
            int: 本次有数据更新的股票数量
        """
        codes = self.provider.get_stock_list()
        total = len(codes)

        today_str = datetime.now().strftime('%Y%m%d')

        skipped = 0
        to_fetch = []
        for code in codes:
            latest = self.db.get_latest_kline_date(code)
            if latest and latest >= today_str:
                skipped += 1
            else:
                to_fetch.append(code)

        if skipped:
            print(f"跳过已覆盖到今天的 {skipped} 只")

        remaining = len(to_fetch)
        if remaining == 0:
            print("所有股票数据已是最新")
            return 0

        updated = 0
        completed = 0

        def _fetch_one(code: str) -> bool:
            """增量获取单只股票数据（工作线程调用）"""
            worker_provider = self._create_worker_provider()
            try:
                worker_provider.download_history_incremental([code], period=period)
                kline = worker_provider.get_kline([code], period=period, count=days)
                if kline is not None and not kline.empty:
                    records = self._kline_to_records(code, kline)
                    if records:
                        with _stats_lock:
                            self.db.insert_daily_kline(records)
                        return True
                return False
            except Exception as e:
                print(f"更新 {code} 失败: {e}", flush=True)
                return False
            finally:
                worker_provider.disconnect()

        with ThreadPoolExecutor(max_workers=self.max_workers) as executor:
            futures = {executor.submit(_fetch_one, code): code for code in to_fetch}
            for future in as_completed(futures):
                completed += 1
                if future.result():
                    updated += 1
                if completed % 200 == 0 or completed == remaining:
                    print(f"增量更新进度: {completed}/{remaining} (更新 {updated})", flush=True)

        print(f"增量更新完成: 本次 {updated}/{remaining} 只有更新 (共 {total} 只, 跳过 {skipped} 只)")
        return updated

    def _kline_to_records(self, code: str, df: pd.DataFrame) -> list[dict]:
        """
        将 miniQMT 返回的 DataFrame 转换为数据库记录格式

        参数:
            code: 目标股票代码
            df:   XTquant 返回的 K 线 DataFrame

        返回:
            list[dict]: 标准化记录列表

        P2 优化：旧代码用 iterrows() 逐行迭代 + 逐字段 float()/round()，
        对数千行 DataFrame 比 to_dict('records') 慢 50-100 倍。
        现改为向量化 round + to_dict('records')。
        """
        if df is None or df.empty:
            return []

        records: list[dict] = []
        try:
            if isinstance(df.columns, pd.MultiIndex):
                mask = df.columns.get_level_values(1) == code
                if not mask.any():
                    mask = df.columns.get_level_values(0) == code
                if not mask.any():
                    return records
                sub = df.loc[:, mask].copy()
                field_names = set(['open', 'high', 'low', 'close', 'volume', 'amount'])
                code_level = 0
                for lv in range(sub.columns.nlevels):
                    sample = str(sub.columns.get_level_values(lv)[0])
                    if sample in field_names:
                        code_level = 1 - lv
                        break
                sub.columns = sub.columns.droplevel(code_level)
            else:
                sub = df.copy()

            # P2 优化：向量化 round 替代逐行 float()+round()
            for col in ['open', 'high', 'low', 'close', 'amount']:
                if col in sub.columns:
                    sub[col] = sub[col].astype(float).round(2)
            for col in ['volume']:
                if col in sub.columns:
                    sub[col] = sub[col].astype(float)

            # P2 优化：用 to_dict('records') 替代 iterrows，快 50-100 倍
            sub = sub.reset_index()
            date_col = sub.columns[0]
            sub[date_col] = sub[date_col].astype(str)
            sub['code'] = code
            # 确保所需列存在，缺失填 0
            for col in ['open', 'high', 'low', 'close', 'volume', 'amount']:
                if col not in sub.columns:
                    sub[col] = 0.0

            records = sub[['code', date_col, 'open', 'high', 'low',
                           'close', 'volume', 'amount']].rename(
                columns={date_col: 'date'}
            ).to_dict('records')
        except Exception as e:
            print(f"转换 {code} K线数据失败: {e}")
        return records

    def close(self):
        if self._own_db:
            self.db.close()

    def download_all_financial(self) -> int:
        codes = self.provider.get_stock_list()
        if not codes:
            return 0
        total = len(codes)
        print(f"共 {total} 只股票待下载财务数据")
        success = 0
        for i, code in enumerate(codes):
            try:
                self.provider.download_financial_data([code])
                data = self.provider.get_financial_data([code])
                if not data or code not in data:
                    continue
                records = self._financial_to_records(code, data[code])
                if records:
                    self.db.insert_financial(records)
                    success += 1
                if (i + 1) % 100 == 0:
                    print(f"财务数据进度: {i+1}/{total}", flush=True)
            except Exception as e:
                print(f"下载 {code} 财务数据失败: {e}", flush=True)
        print(f"财务数据下载完成: {success}/{total}")
        return success

    def _financial_to_records(self, code: str, tables: dict) -> list[dict]:
        records = []
        try:
            for table_name, df in tables.items():
                if df is None or hasattr(df, 'empty') and df.empty:
                    continue
                for idx, row in df.iterrows():
                    rec = {'code': code, 'report_date': str(idx), 'table': table_name}
                    for col in df.columns:
                        val = row.get(col)
                        try:
                            rec[str(col)] = float(val) if val is not None and val != '' else None
                        except (ValueError, TypeError):
                            rec[str(col)] = None
                    records.append(rec)
        except Exception as e:
            print(f"转换 {code} 财务数据失败: {e}")
        return records
