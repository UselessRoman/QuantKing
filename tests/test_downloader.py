# -*- coding: utf-8 -*-
"""数据下载与验证测试"""
import pytest
import pandas as pd
import tempfile
from pathlib import Path
from data.data_validator import DataValidator
from data.database import Database


class TestDataValidator:
    """数据健康检查测试"""

    def test_validate_clean_data(self):
        validator = DataValidator()
        df = pd.DataFrame({
            'date': ['20230101', '20230102', '20230103'],
            'open':  [10.0, 10.2, 10.1],
            'high':  [10.5, 10.5, 10.3],
            'low':   [9.8, 10.0, 10.0],
            'close': [10.2, 10.1, 10.3],
            'volume': [100000, 120000, 110000],
        })
        result = validator.validate_kline(df, "000001.SZ")
        assert result['passed'] is True
        assert result['jump_count'] == 0
        assert len(result['issues']) == 0

    def test_validate_missing_columns(self):
        validator = DataValidator()
        df = pd.DataFrame({
            'date': ['20230101'],
            'close': [10.0],
        })
        result = validator.validate_kline(df)
        assert result['passed'] is False
        assert any('缺少必需列' in i for i in result['issues'])

    def test_validate_null_values(self):
        validator = DataValidator()
        df = pd.DataFrame({
            'date': ['20230101', '20230102'],
            'open':  [10.0, None],
            'high':  [10.5, 10.5],
            'low':   [9.8, 10.0],
            'close': [10.2, None],
            'volume': [100000, 120000],
        })
        result = validator.validate_kline(df)
        assert result['passed'] is False
        assert result['null_close_count'] == 1

    def test_validate_price_jump(self):
        validator = DataValidator()
        df = pd.DataFrame({
            'date': ['20230101', '20230102'],
            'open':  [10.0, 12.0],
            'high':  [10.5, 12.5],
            'low':   [9.8, 11.5],
            'close': [10.0, 12.1],  # 跳变 21% > 11%
            'volume': [100000, 120000],
        })
        result = validator.validate_kline(df)
        assert result['jump_count'] >= 1

    def test_validate_high_low(self):
        validator = DataValidator()
        df = pd.DataFrame({
            'date': ['20230101'],
            'open':  [10.0],
            'high':  [9.0],   # high < low
            'low':   [10.0],
            'close': [9.5],
            'volume': [100000],
        })
        result = validator.validate_kline(df)
        assert not result['passed']

    def test_validate_parquet_file(self, tmp_path):
        """验证 Parquet 文件健康检查"""
        validator = DataValidator()
        df = pd.DataFrame({
            'date': ['20230101', '20230102'],
            'open':  [10.0, 10.2],
            'high':  [10.5, 10.5],
            'low':   [9.8, 10.0],
            'close': [10.2, 10.1],
            'volume': [100000, 120000],
        })
        file_path = tmp_path / "test.parquet"
        df.to_parquet(file_path)

        result = validator.validate_parquet_file(str(file_path))
        assert result['passed'] is True


class TestDatabaseAudit:
    """审计日志测试"""

    def test_log_and_read_audit(self, tmp_path):
        db_path = tmp_path / "test.db"
        db = Database(db_path=db_path)
        db.connect()
        db.initialize()

        # 写入审计日志
        rid = db.log_audit("ORDER_PLACED", "real", "BUY 000001.SZ 100@10.5")
        assert rid > 0

        # 读取审计日志
        logs = db.get_audit_logs(limit=10)
        assert len(logs) >= 1
        assert logs[0]['event_type'] == "ORDER_PLACED"

        db.close()

    def test_invalid_parquet(self, tmp_path):
        """无效 parquet 文件测试"""
        validator = DataValidator()
        bad_file = tmp_path / "bad.parquet"
        bad_file.write_text("not a parquet file")
        result = validator.validate_parquet_file(str(bad_file))
        assert not result['passed']
        assert any('文件读取失败' in i for i in result['issues'])


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
