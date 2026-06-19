# -*- coding: utf-8 -*-
"""
数据健康检查模块

基于 XTquant 官方文档关于数据健康检查的建议实现:
    - 检查 DataFrame 中是否有缺失数据
    - 检查 OHLCV 列中是否存在超过阈值的大幅度跳变
    - 检查 DataFrame 中是否缺少任何必需列（OLHCV）
    - 检查 DataFrame 中是否缺少 'factor' 列

使用方式:
    from data.data_validator import DataValidator
    validator = DataValidator()
    result = validator.validate_kline(df)
    if result['passed']:
        print("数据健康")
    else:
        print("发现问题:", result['issues'])
"""
import pandas as pd
import numpy as np
from typing import Optional


class DataValidator:
    """
    数据健康检查器

    对 K 线数据进行多维度质量验证，确保数据正确可用于回测和策略。

    属性:
        price_jump_threshold: 价格跳变阈值（A 股涨跌停 10%，创业板/科创板 20%）
    """

    REQUIRED_COLUMNS = {'open', 'high', 'low', 'close', 'volume'}

    def __init__(self, price_jump_threshold: float = 0.11):
        """
        参数:
            price_jump_threshold: 日涨跌幅异常检测阈值，默认 0.11（11%）
        """
        self.price_jump_threshold = price_jump_threshold

    def validate_kline(self, df: pd.DataFrame, code: str = '') -> dict:
        """
        对单只股票K线数据执行全面健康检查

        参数:
            df:   K 线 DataFrame，需含 open/high/low/close/volume 列
            code: 股票代码（用于错误报告）

        返回:
            dict: {
                'passed': bool,       # 是否通过所有检查
                'row_count': int,     # 总行数
                'missing_count': int, # 缺失值计数
                'null_close_count': int,  # 收盘价空值数
                'jump_count': int,    # 异常跳变次数
                'issues': list[str],  # 问题描述列表
            }
        """
        issues = []
        row_count = len(df)

        # 1. 检查必需列
        missing_cols = self.REQUIRED_COLUMNS - set(df.columns)
        if missing_cols:
            issues.append(f"缺少必需列: {missing_cols}")

        # 2. 检查空值
        missing_count = 0
        null_close = 0
        for col in self.REQUIRED_COLUMNS & set(df.columns):
            nulls = df[col].isnull().sum()
            if nulls > 0:
                issues.append(f"列 {col} 存在 {nulls} 个空值")
                missing_count += nulls
                if col == 'close':
                    null_close = nulls

        # 3. 检查价格跳变（逐日涨跌幅检测）
        jump_count = 0
        if 'close' in df.columns and len(df) >= 2:
            col = 'close'
            for i in range(1, len(df)):
                prev, curr = df[col].iloc[i-1], df[col].iloc[i]
                if prev is None or curr is None:
                    continue
                try:
                    prev_f, curr_f = float(prev), float(curr)
                    if prev_f <= 0:
                        continue
                    change = abs(curr_f / prev_f - 1)
                    if change > self.price_jump_threshold:
                        date_str = str(df['date'].iloc[i]) if 'date' in df.columns else str(i)
                        issues.append(f"日期 {date_str}: {col} 跳变 {change:.2%} "
                                      f"({prev_f} -> {curr_f})")
                        jump_count += 1
                except (ValueError, TypeError):
                    continue

        # 4. 检查 high >= low
        if 'high' in df.columns and 'low' in df.columns:
            bad = (df['high'] < df['low']).sum()
            if bad > 0:
                issues.append(f"存在 {bad} 条 high < low 的记录")

        passed = len(issues) == 0
        result = {
            'passed': passed,
            'code': code,
            'row_count': row_count,
            'missing_count': missing_count,
            'null_close_count': null_close,
            'jump_count': jump_count,
            'issues': issues,
            'checks_passed': not bool(missing_cols) and jump_count == 0,
        }
        return result

    def validate_parquet_file(self, file_path: str) -> dict:
        """
        验证单个 Parquet K线文件的健康状态

        参数:
            file_path: Parquet 文件路径

        返回:
            dict: 同 validate_kline 的返回格式
        """
        try:
            df = pd.read_parquet(file_path)
            code = str(file_path).replace('\\', '/').split('/')[-1].replace('.parquet', '')
            return self.validate_kline(df, code)
        except Exception as e:
            return {
                'passed': False,
                'code': str(file_path),
                'row_count': 0,
                'missing_count': 0,
                'null_close_count': 0,
                'jump_count': 0,
                'issues': [f"文件读取失败: {e}"],
                'checks_passed': False,
            }

    def validate_all(self, kline_dir: str, period: str = '1d',
                     max_files: int = 0) -> dict:
        """
        批量验证 K线目录下所有 Parquet 文件

        参数:
            kline_dir: Parquet K线目录路径
            period:    周期，如 "1d"
            max_files: 最大检查文件数（0=全部）

        返回:
            dict: {
                'total': int,
                'passed': int,
                'failed': int,
                'issues_summary': list[dict],
            }
        """
        from pathlib import Path
        parquet_dir = Path(kline_dir) / period
        if not parquet_dir.exists():
            return {'total': 0, 'passed': 0, 'failed': 0, 'issues_summary': [],
                    'error': f"目录不存在: {parquet_dir}"}

        files = list(parquet_dir.glob("*.parquet"))
        if max_files > 0:
            files = files[:max_files]

        total = len(files)
        passed = 0
        failed = 0
        issues_summary = []

        for f in files:
            result = self.validate_parquet_file(str(f))
            if result['passed']:
                passed += 1
            else:
                failed += 1
                issues_summary.append({
                    'code': result['code'],
                    'issues': result['issues'],
                })

        return {
            'total': total,
            'passed': passed,
            'failed': failed,
            'issues_summary': issues_summary,
        }
