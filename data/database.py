# -*- coding: utf-8 -*-
"""
本地数据库 + Parquet K线存储模块

SQLite 存储: stocks / sectors / trade_records / kline_index
Parquet 存储: daily_kline / minute_kline（按股票代码分文件）

数据库文件:
    默认路径由 config.settings.DB_PATH 指定，通常为项目根目录下的 quant.db。
    使用 WAL（Write-Ahead Logging）模式以提升并发读写性能。

K线 Parquet 目录结构:
    {DATA_DIR}/kline/{period}/{code}.parquet
    例: data/kline/1d/000001.SZ.parquet

使用方式:
    db = Database()
    db.connect()
    db.initialize()
    db.insert_daily_kline(records)     # 写 Parquet + 更新 kline_index
    df = db.get_daily_kline_df(code)   # 读 Parquet 返回 DataFrame
    db.close()

注意事项:
    - SQLite 连接为非线程安全，多线程场景需为每个线程创建独立连接
    - Parquet 文件读取是线程安全的，可并发
    - kline_index 表是 Parquet 文件的目录索引，需与文件保持同步
"""
import sqlite3
import sys
import json
from pathlib import Path
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from config.settings import DB_PATH, KLINE_DIR as DATA_DIR, FINANCIAL_DIR


class Database:
    """
    SQLite + Parquet 混合存储访问层

    SQLite 表:
        stocks         — 股票基础信息
        sectors        — 板块分类
        trade_records  — 交易记录
        kline_index    — K线 Parquet 文件索引

    Parquet 文件:
        data/kline/{period}/{code}.parquet  — K线数据

    属性:
        conn:   sqlite3.Connection 对象
        db_path: SQLite 数据库文件路径
        data_dir: Parquet K线根目录
    """

    def __init__(self, db_path: str | Path = DB_PATH, data_dir: str | Path = DATA_DIR,
                 financial_dir: str | Path = FINANCIAL_DIR):
        self.db_path = str(db_path)
        self.data_dir = Path(data_dir)
        self.financial_dir = Path(financial_dir)
        self.conn: sqlite3.Connection | None = None
        # 增量写入缓存: 避免每次全量读取 Parquet 做去重
        # {file_path: set of (code, date) tuples}
        self._date_cache: dict[str, set] = {}
        # P2 优化：读侧 LRU 缓存 {(code, period, start, end): DataFrame}
        # 用 OrderedDict 实现简易 LRU，上限 200 条防内存膨胀
        from collections import OrderedDict
        self._read_cache: OrderedDict = OrderedDict()
        self._read_cache_max = 200

    # ──────────── 连接管理 ────────────

    def connect(self):
        self.conn = sqlite3.connect(self.db_path, check_same_thread=False)
        self.conn.execute("PRAGMA journal_mode=WAL")

    def close(self):
        if self.conn:
            self.conn.close()
            self.conn = None
        self._date_cache.clear()
        self._read_cache.clear()

    def initialize(self):
        self.conn.executescript("""
            CREATE TABLE IF NOT EXISTS stocks (
                code TEXT PRIMARY KEY,
                name TEXT,
                listing_date TEXT,
                status TEXT DEFAULT '正常'
            );

            CREATE TABLE IF NOT EXISTS sectors (
                sector_name TEXT NOT NULL,
                stock_code TEXT NOT NULL,
                PRIMARY KEY (sector_name, stock_code)
            );

            CREATE TABLE IF NOT EXISTS trade_records (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                account_id TEXT NOT NULL,
                symbol TEXT NOT NULL,
                action TEXT NOT NULL,
                price REAL NOT NULL,
                volume INTEGER NOT NULL,
                commission REAL DEFAULT 0,
                tax REAL DEFAULT 0,
                amount REAL NOT NULL,
                trade_time TEXT NOT NULL,
                status TEXT DEFAULT '已成交'
            );

            CREATE TABLE IF NOT EXISTS kline_index (
                code TEXT NOT NULL,
                period TEXT NOT NULL,
                file_path TEXT NOT NULL,
                start_date TEXT,
                end_date TEXT,
                row_count INTEGER DEFAULT 0,
                PRIMARY KEY (code, period)
            );

            CREATE TABLE IF NOT EXISTS financial_index (
                code TEXT PRIMARY KEY,
                file_path TEXT NOT NULL,
                report_count INTEGER DEFAULT 0,
                latest_report TEXT,
                updated_at TEXT
            );

            CREATE TABLE IF NOT EXISTS audit_log (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                event_type TEXT NOT NULL,
                account_id TEXT DEFAULT '',
                detail TEXT,
                created_at TEXT NOT NULL DEFAULT (datetime('now', 'localtime'))
            );

            CREATE TABLE IF NOT EXISTS backtest_history (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                strategy TEXT NOT NULL,
                params_json TEXT,
                result_json TEXT,
                initial_capital REAL,
                codes_json TEXT,
                start_date TEXT,
                end_date TEXT,
                created_at TEXT NOT NULL DEFAULT (datetime('now', 'localtime'))
            );
        """)
        self.conn.commit()
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self.financial_dir.mkdir(parents=True, exist_ok=True)

    # ──────────── stocks ────────────

    def upsert_stocks(self, records: list[dict]) -> None:
        sql = "INSERT OR REPLACE INTO stocks (code, name, listing_date, status) VALUES (?, ?, ?, ?)"
        data = [(r['code'], r.get('name', ''), r.get('listing_date', ''), r.get('status', '正常')) for r in records]
        self.conn.executemany(sql, data)
        self.conn.commit()

    def get_all_stocks(self) -> list[dict]:
        cursor = self.conn.execute("SELECT code, name, listing_date, status FROM stocks")
        return [dict(zip(['code', 'name', 'listing_date', 'status'], row)) for row in cursor.fetchall()]

    # ──────────── sectors ────────────

    def insert_sector_records(self, sector_name: str, stock_codes: list[str]) -> None:
        self.conn.execute("DELETE FROM sectors WHERE sector_name = ?", (sector_name,))
        data = [(sector_name, code) for code in stock_codes]
        self.conn.executemany("INSERT INTO sectors (sector_name, stock_code) VALUES (?, ?)", data)
        self.conn.commit()

    def get_sector_stocks(self, sector_name: str) -> list[str]:
        cursor = self.conn.execute("SELECT stock_code FROM sectors WHERE sector_name = ?", (sector_name,))
        return [row[0] for row in cursor.fetchall()]

    def get_all_sectors(self) -> list[str]:
        cursor = self.conn.execute("SELECT DISTINCT sector_name FROM sectors ORDER BY sector_name")
        return [row[0] for row in cursor.fetchall()]

    # ──────────── trade_records ────────────

    def insert_trade_record(self, record: dict) -> int:
        sql = """INSERT INTO trade_records (account_id, symbol, action, price, volume,
                 commission, tax, amount, trade_time, status)
                 VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)"""
        params = (
            record['account_id'], record['symbol'], record['action'],
            record['price'], record['volume'],
            record.get('commission', 0), record.get('tax', 0),
            record['amount'], record['trade_time'],
            record.get('status', '已成交')
        )
        cursor = self.conn.execute(sql, params)
        self.conn.commit()
        return cursor.lastrowid

    def get_trade_records(self, account_id: str = '', start_date: str = '',
                          end_date: str = '') -> list[dict]:
        sql = "SELECT * FROM trade_records WHERE 1=1"
        params = []
        if account_id:
            sql += " AND account_id = ?"
            params.append(account_id)
        if start_date:
            sql += " AND trade_time >= ?"
            params.append(start_date)
        if end_date:
            sql += " AND trade_time <= ?"
            params.append(end_date)
        sql += " ORDER BY trade_time DESC"
        cursor = self.conn.execute(sql, params)
        cols = [desc[0] for desc in cursor.description]
        return [dict(zip(cols, row)) for row in cursor.fetchall()]

    # ──────────── backtest_history ────────────

    def insert_backtest_history(self, entry: dict) -> int:
        """插入一条回测历史记录，返回新记录 id。

        Args:
            entry: 包含 strategy/params/result/initial_capital/codes/
                   start_date/end_date 的字典（result/params/codes 会被
                   JSON 序列化存储）
        """
        sql = """INSERT INTO backtest_history
                 (strategy, params_json, result_json, initial_capital,
                  codes_json, start_date, end_date)
                 VALUES (?, ?, ?, ?, ?, ?, ?)"""
        params = (
            entry.get('strategy', ''),
            json.dumps(entry.get('params', {}), ensure_ascii=False, default=str),
            json.dumps(entry.get('performance', {}), ensure_ascii=False, default=str),
            entry.get('initial_capital', 0),
            json.dumps(entry.get('codes', []), ensure_ascii=False, default=str),
            entry.get('start_date', ''),
            entry.get('end_date', ''),
        )
        cursor = self.conn.execute(sql, params)
        self.conn.commit()
        return cursor.lastrowid

    def get_backtest_history(self, limit: int = 20) -> list[dict]:
        """获取最近的回测历史记录（默认 20 条，按时间倒序）"""
        import json as _json
        cursor = self.conn.execute(
            "SELECT * FROM backtest_history ORDER BY id DESC LIMIT ?",
            (limit,)
        )
        cols = [desc[0] for desc in cursor.description]
        rows = [dict(zip(cols, row)) for row in cursor.fetchall()]
        # 反序列化 JSON 字段，补充前端期望的字段名
        for row in rows:
            try:
                row['params'] = _json.loads(row.pop('params_json', '{}'))
            except (ValueError, TypeError):
                row['params'] = {}
            try:
                row['performance'] = _json.loads(row.pop('result_json', '{}'))
            except (ValueError, TypeError):
                row['performance'] = {}
            try:
                row['codes'] = _json.loads(row.pop('codes_json', '[]'))
            except (ValueError, TypeError):
                row['codes'] = []
        return rows

    # ════════════ Parquet 通用增量写入 ════════════

    def _incremental_write_parquet(
        self,
        records: list[dict],
        file_path: Path,
        key_columns: list[str],
        sort_column: str,
        use_cache: bool = True,
    ) -> tuple[int, pd.DataFrame]:
        """通用 Parquet 增量写入：去重 → 合并 → 排序 → 写入。

        P2 优化：
        - 旧代码单次插入读 Parquet 2-3 次（seen 构建 + concat + _update_kline_index），
          现复用已读的 existing/merged，降至 0-1 次。
        - seen 集合改用 set(existing[date]) 替代 to_dict('records') 全表序列化。
        - 无新记录时直接返回已读的 existing，不再重读。

        Args:
            records: 待写入的记录列表
            file_path: Parquet 文件路径
            key_columns: 去重键列（如 ['code', 'date']）
            sort_column: 排序列
            use_cache: 是否使用 ``_date_cache`` 内存缓存避免重复读取 Parquet

        Returns:
            (新增记录数, 最终 DataFrame)
        """
        if not records:
            return 0, pd.DataFrame()

        df = pd.DataFrame(records)
        file_key = str(file_path)

        if file_path.exists():
            existing = pd.read_parquet(file_path)
            if use_cache and file_key in self._date_cache:
                seen = self._date_cache[file_key]
            else:
                # P2 优化：同文件内 code 固定，只需按 date 去重
                if len(key_columns) == 2 and sort_column in key_columns:
                    seen = set(existing[sort_column].astype(str))
                else:
                    seen = set(existing[key_columns[0]].astype(str))
                if use_cache:
                    self._date_cache[file_key] = seen

            new_records = [r for r in records
                           if str(r[sort_column if len(key_columns) == 2 else key_columns[0]]) not in seen]
            if new_records:
                new_df = pd.DataFrame(new_records)
                # P2 优化：复用已读的 existing，不再 pd.read_parquet 第二次
                merged = pd.concat([existing, new_df], ignore_index=True)
                merged = merged.drop_duplicates(subset=key_columns, keep='last')
                merged.sort_values(sort_column, inplace=True)
                merged.to_parquet(file_path, index=False)

                if use_cache:
                    for r in new_records:
                        self._date_cache[file_key].add(str(r[sort_column if len(key_columns) == 2 else key_columns[0]]))

                return len(new_records), merged
            else:
                # P2 优化：无新记录时直接返回已读的 existing，不再重读
                return 0, existing
        else:
            df.sort_values(sort_column, inplace=True)
            df.to_parquet(file_path, index=False)

            if use_cache:
                self._date_cache[file_key] = set(df[sort_column].astype(str))

            return len(records), df

    # ════════════ Parquet K线操作 ════════════

    def _kline_path(self, code: str, period: str) -> Path:
        dir_path = self.data_dir / period
        dir_path.mkdir(parents=True, exist_ok=True)
        return dir_path / f"{code}.parquet"

    def insert_daily_kline(self, records: list[dict], period: str = '1d') -> int:
        """写入日K线到 Parquet 文件（增量去重优化版）。"""
        if not records:
            return 0
        code = records[0]['code']
        file_path = self._kline_path(code, period)

        # P2 优化：复用 _incremental_write_parquet 返回的 merged DataFrame，
        # 避免 _update_kline_index 再次 read_parquet
        count, merged_df = self._incremental_write_parquet(
            records=records,
            file_path=file_path,
            key_columns=['code', 'date'],
            sort_column='date',
            use_cache=True,
        )

        self._update_kline_index(code, period, str(file_path), count, merged_df)
        return count

    def _update_kline_index(self, code: str, period: str, file_path: str,
                            added: int, df: pd.DataFrame = None):
        file = Path(file_path)
        if not file.exists():
            return
        # P2 优化：优先使用传入的 df（已合并的 DataFrame），避免重读 Parquet
        if df is None:
            df = pd.read_parquet(file_path)
        start_date = str(df['date'].iloc[0]) if len(df) > 0 else ''
        end_date = str(df['date'].iloc[-1]) if len(df) > 0 else ''
        row_count = len(df)
        sql = """INSERT OR REPLACE INTO kline_index (code, period, file_path, start_date, end_date, row_count)
                 VALUES (?, ?, ?, ?, ?, ?)"""
        self.conn.execute(sql, (code, period, file_path, start_date, end_date, row_count))
        self.conn.commit()

    def get_daily_kline_df(self, code: str, period: str = '1d',
                           start_date: str = '', end_date: str = '') -> pd.DataFrame:
        file_path = self._kline_path(code, period)
        if not file_path.exists():
            return pd.DataFrame()
        # P2 优化：读侧 LRU 缓存，避免回测/因子计算反复读盘
        cache_key = (code, period, start_date, end_date)
        if hasattr(self, '_read_cache') and cache_key in self._read_cache:
            return self._read_cache[cache_key].copy()

        df = pd.read_parquet(file_path)
        if start_date:
            df = df[df['date'] >= start_date]
        if end_date:
            df = df[df['date'] <= end_date]

        if hasattr(self, '_read_cache'):
            self._read_cache[cache_key] = df
            # LRU 淘汰
            if len(self._read_cache) > self._read_cache_max:
                self._read_cache.popitem(last=False)
        return df

    def get_daily_kline(self, code: str, start_date: str = '',
                        end_date: str = '') -> list[dict]:
        df = self.get_daily_kline_df(code, '1d', start_date, end_date)
        if df.empty:
            return []
        return df.to_dict('records')

    def get_latest_kline_date(self, code: str, period: str = '1d') -> str | None:
        cursor = self.conn.execute(
            "SELECT end_date FROM kline_index WHERE code = ? AND period = ?",
            (code, period)
        )
        row = cursor.fetchone()
        return row[0] if row and row[0] else None

    def get_latest_kline_dates(self, codes: list[str], period: str = '1d') -> dict[str, str]:
        """P2 优化：批量查询多只股票的最新K线日期，替代 N+1 逐股查询。

        返回 {code: end_date}，无记录的 code 不包含在结果中。
        """
        if not codes:
            return {}
        # 用 IN 批量查询；codes 多时分批防 SQL 参数上限
        result = {}
        batch_size = 500
        for i in range(0, len(codes), batch_size):
            batch = codes[i:i + batch_size]
            placeholders = ','.join('?' * len(batch))
            cursor = self.conn.execute(
                f"SELECT code, end_date FROM kline_index "
                f"WHERE period = ? AND code IN ({placeholders})",
                [period] + batch
            )
            for code, end_date in cursor.fetchall():
                if end_date:
                    result[code] = end_date
        return result

    # ──────────── 分钟K线 ────────────

    def insert_minute_kline(self, records: list[dict], period: str = '1m') -> int:
        return self.insert_daily_kline(records, period)

    def get_minute_kline(self, code: str, start_dt: str = '',
                         end_dt: str = '') -> list[dict]:
        df = self.get_daily_kline_df(code, '1m', start_dt, end_dt)
        if df.empty:
            return []
        return df.to_dict('records')

    # ──────────── 财务数据 ────────────

    def _financial_path(self, code: str) -> Path:
        self.financial_dir.mkdir(parents=True, exist_ok=True)
        return self.financial_dir / f"{code}.parquet"

    def insert_financial(self, records: list[dict]) -> int:
        """写入财务数据到 Parquet 文件（增量去重）。"""
        if not records:
            return 0
        code = records[0]['code']
        file_path = self._financial_path(code)

        count, df = self._incremental_write_parquet(
            records=records,
            file_path=file_path,
            key_columns=['code', 'report_date'],
            sort_column='report_date',
            use_cache=False,
        )

        last = df['report_date'].iloc[-1] if len(df) > 0 else ''
        self.conn.execute(
            "INSERT OR REPLACE INTO financial_index (code, file_path, report_count, latest_report, updated_at) "
            "VALUES (?, ?, ?, ?, datetime('now', 'localtime'))",
            (code, str(file_path), len(df), str(last))
        )
        self.conn.commit()
        return count

    def get_financial_df(self, code: str) -> pd.DataFrame:
        file_path = self._financial_path(code)
        if not file_path.exists():
            return pd.DataFrame()
        return pd.read_parquet(file_path)

    def get_financial(self, code: str) -> list[dict]:
        df = self.get_financial_df(code)
        if df.empty:
            return []
        return df.to_dict('records')

    # ──────────── 除权因子 ────────────

    def _divid_path(self, code: str) -> Path:
        divid_dir = self.data_dir.parent / "divid"
        divid_dir.mkdir(parents=True, exist_ok=True)
        return divid_dir / f"{code}.parquet"

    def insert_divid_factors(self, code: str, df: pd.DataFrame) -> int:
        """写入除权除息因子数据"""
        if df is None or df.empty:
            return 0
        file_path = self._divid_path(code)
        df.to_parquet(file_path, index=False)
        return len(df)

    def get_divid_factors(self, code: str) -> pd.DataFrame:
        """读取除权除息因子"""
        file_path = self._divid_path(code)
        if not file_path.exists():
            return pd.DataFrame()
        return pd.read_parquet(file_path)

    # ──────────── 审计日志 ────────────

    def log_audit(self, event_type: str, account_id: str = '', detail: str = '') -> int:
        """写入审计日志"""
        sql = "INSERT INTO audit_log (event_type, account_id, detail) VALUES (?, ?, ?)"
        cursor = self.conn.execute(sql, (event_type, account_id, detail))
        self.conn.commit()
        return cursor.lastrowid

    def get_audit_logs(self, limit: int = 100) -> list[dict]:
        """获取最近的审计日志"""
        cursor = self.conn.execute(
            "SELECT id, event_type, account_id, detail, created_at "
            "FROM audit_log ORDER BY id DESC LIMIT ?", (limit,))
        return [dict(zip(['id', 'event_type', 'account_id', 'detail', 'created_at'], row))
                for row in cursor.fetchall()]

    # ──────────── 统计与摘要 ────────────

    def get_stats(self) -> dict:
        n_stocks = self.conn.execute("SELECT COUNT(*) FROM stocks").fetchone()[0]
        n_sectors = self.conn.execute("SELECT COUNT(DISTINCT sector_name) FROM sectors").fetchone()[0]
        n_trades = self.conn.execute("SELECT COUNT(*) FROM trade_records").fetchone()[0]
        n_kline = self.conn.execute(
            "SELECT COUNT(*), COALESCE(SUM(row_count),0) FROM kline_index WHERE period='1d'"
        ).fetchone()
        return {
            'stocks': n_stocks,
            'sectors': n_sectors,
            'trades': n_trades,
            'kline_files': n_kline[0],
            'kline_rows': n_kline[1],
        }

    def get_stock_klines_summary(self) -> list[dict]:
        sql = """SELECT s.code, s.name, s.listing_date,
                        k.start_date AS kline_start, k.end_date AS kline_end,
                        k.row_count
                 FROM stocks s
                 LEFT JOIN kline_index k ON s.code = k.code AND k.period = '1d'
                 ORDER BY s.code"""
        cursor = self.conn.execute(sql)
        cols = ['code', 'name', 'listing_date', 'kline_start', 'kline_end', 'row_count']
        return [dict(zip(cols, row)) for row in cursor.fetchall()]
