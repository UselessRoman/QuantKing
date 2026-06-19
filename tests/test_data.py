# -*- coding: utf-8 -*-
"""数据层单元测试"""
import pytest
import pandas as pd
from pathlib import Path
from data.database import Database
from data.qlib_converter import validate_qlib_data


class TestDatabase:
    """SQLite + Parquet 存储层测试"""

    def test_connect_and_initialize(self, tmp_path):
        db_path = tmp_path / "test.db"
        db = Database(db_path=db_path, data_dir=tmp_path / "kline")
        db.connect()
        db.initialize()

        # 验证表已创建
        tables = db.conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        ).fetchall()
        table_names = {row[0] for row in tables}
        assert 'stocks' in table_names
        assert 'sectors' in table_names
        assert 'trade_records' in table_names
        assert 'kline_index' in table_names

        db.close()

    def test_insert_and_query_kline(self, tmp_path):
        db_path = tmp_path / "test.db"
        kline_dir = tmp_path / "kline"
        kline_dir.mkdir(parents=True)

        db = Database(db_path=db_path, data_dir=kline_dir)
        db.connect()
        db.initialize()

        records = [
            {'code': '000001.SZ', 'date': '20230103', 'open': 10.0, 'high': 10.5,
             'low': 9.8, 'close': 10.2, 'volume': 1000000, 'amount': 10200000},
            {'code': '000001.SZ', 'date': '20230104', 'open': 10.2, 'high': 10.8,
             'low': 10.1, 'close': 10.5, 'volume': 1200000, 'amount': 12600000},
        ]

        count = db.insert_daily_kline(records)
        assert count == 2

        df = db.get_daily_kline_df('000001.SZ', '1d')
        assert len(df) == 2
        assert df['close'].iloc[-1] == 10.5

        db.close()

    def test_upsert_stocks(self, tmp_path):
        db_path = tmp_path / "test.db"
        db = Database(db_path=db_path)
        db.connect()
        db.initialize()

        records = [
            {'code': '000001.SZ', 'name': '平安银行', 'listing_date': '19910403'},
            {'code': '600000.SH', 'name': '浦发银行', 'listing_date': '19991110'},
        ]
        db.upsert_stocks(records)

        stocks = db.get_all_stocks()
        assert len(stocks) == 2
        assert stocks[0]['code'] in ('000001.SZ', '600000.SH')

        db.close()


class TestQlibConverter:
    """qlib 数据转换测试"""

    def test_validate_empty_dir(self, tmp_path):
        result = validate_qlib_data(str(tmp_path))
        assert result['calendars'] == 0
        assert result['instruments'] == 0
        assert result['features'] == 0


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
