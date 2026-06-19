# -*- coding: utf-8 -*-
"""
qlib 数据格式转换模块

将本地 Parquet K线数据转换为 qlib 所需的二进制格式。

qlib 数据目录结构:
    data/qlib_data_cn/
    ├── calendars/
    │   └── day.txt              # 沪深交易日历
    ├── instruments/
    │   └── all.txt              # 股票列表及上市退市日期
    └── features/
        └── <stock_code>/
            ├── open.day.bin
            ├── high.day.bin
            ├── low.day.bin
            ├── close.day.bin
            ├── volume.day.bin
            ├── amount.day.bin
            └── ...

使用方式:
    from data.qlib_converter import convert_kline_to_qlib_format
    convert_kline_to_qlib_format()
"""
import os
import struct
import numpy as np
import pandas as pd
from pathlib import Path
from datetime import datetime
from config.settings import KLINE_DIR, QLIB_DATA_DIR
from data.database import Database


def _write_bin_file(file_path: Path, dates: list, values: list):
    """写入单个 qlib 二进制特征文件"""
    file_path.parent.mkdir(parents=True, exist_ok=True)
    with open(file_path, 'wb') as f:
        for date_str, val in zip(dates, values):
            # qlib 格式: date(int64) + value(float32)
            try:
                date_int = int(date_str)
            except (ValueError, TypeError):
                continue
            try:
                f.write(struct.pack('<i', date_int))  # 日期 int32
                f.write(struct.pack('<f', float(val) if not np.isnan(val) else 0.0))  # float32
            except (TypeError, ValueError):
                continue


def convert_kline_to_qlib_format(
    parquet_dir: str = None,
    output_dir: str = None,
    period: str = "1d"
) -> int:
    """
    将现有 Parquet K线数据转换为 qlib 二进制格式

    参数:
        parquet_dir: Parquet 数据目录，默认使用 KLINE_DIR
        output_dir:  qlib 输出目录，默认使用 QLIB_DATA_DIR
        period:      K线周期，默认 "1d"

    返回:
        int: 成功转换的股票数量
    """
    kline_dir = Path(parquet_dir) if parquet_dir else Path(KLINE_DIR)
    qlib_dir = Path(output_dir) if output_dir else Path(QLIB_DATA_DIR)
    parquet_path = kline_dir / period

    if not parquet_path.exists():
        print(f"Parquet 数据目录不存在: {parquet_path}")
        return 0

    # 创建 qlib 目录结构
    calendars_dir = qlib_dir / "calendars"
    instruments_dir = qlib_dir / "instruments"
    features_dir = qlib_dir / "features"
    calendars_dir.mkdir(parents=True, exist_ok=True)
    instruments_dir.mkdir(parents=True, exist_ok=True)
    features_dir.mkdir(parents=True, exist_ok=True)

    # 收集所有 parquet 文件
    parquet_files = list(parquet_path.glob("*.parquet"))
    if not parquet_files:
        print(f"未找到 Parquet 文件: {parquet_path}")
        return 0

    print(f"找到 {len(parquet_files)} 个 Parquet 文件，开始转换...")

    all_dates: set[str] = set()
    instruments: list[tuple[str, str, str]] = []  # (code, start_date, end_date)
    success_count = 0

    for i, pq_file in enumerate(parquet_files):
        try:
            code = pq_file.stem  # 文件名即股票代码
            df = pd.read_parquet(pq_file)

            if df.empty or 'date' not in df.columns:
                continue

            # 收集日期
            dates = sorted(df['date'].unique())
            all_dates.update(dates)

            # 记录股票信息
            start_date = dates[0]
            end_date = dates[-1]
            instruments.append((code, start_date, end_date))

            # 创建股票特征目录
            stock_dir = features_dir / code
            stock_dir.mkdir(parents=True, exist_ok=True)

            # 转换各字段
            field_map = {
                'open': 'open',
                'high': 'high',
                'low': 'low',
                'close': 'close',
                'volume': 'volume',
                'amount': 'amount',
            }

            for field, filename in field_map.items():
                if field not in df.columns:
                    continue
                bin_file = stock_dir / f"{filename}.{period}.bin"
                df_sorted = df.sort_values('date')
                values = df_sorted[field].tolist()
                file_dates = df_sorted['date'].tolist()
                _write_bin_file(bin_file, file_dates, values)

            success_count += 1

            if (i + 1) % 100 == 0:
                print(f"qlib 转换进度: {i + 1}/{len(parquet_files)}")

        except Exception as e:
            print(f"转换 {pq_file.name} 失败: {e}")

    # 写入交易日历
    sorted_dates = sorted(all_dates)
    with open(calendars_dir / "day.txt", 'w', encoding='utf-8') as f:
        f.write("\n".join(sorted_dates))

    # 写入股票列表
    with open(instruments_dir / "all.txt", 'w', encoding='utf-8') as f:
        for code, start_date, end_date in sorted(instruments):
            f.write(f"{code}\t{start_date}\t{end_date}\n")

    print(f"qlib 数据转换完成: {success_count}/{len(parquet_files)} 只股票")
    print(f"交易日历: {len(sorted_dates)} 天 ({sorted_dates[0]} ~ {sorted_dates[-1]})")
    return success_count


def validate_qlib_data(qlib_dir: str = None) -> dict:
    """
    验证 qlib 数据完整性

    参数:
        qlib_dir: qlib 数据目录

    返回:
        dict: 验证结果，包含 calendars/instruments/features 统计
    """
    qdir = Path(qlib_dir) if qlib_dir else Path(QLIB_DATA_DIR)

    result = {"calendars": 0, "instruments": 0, "features": 0, "errors": []}

    cal_file = qdir / "calendars" / "day.txt"
    if cal_file.exists():
        with open(cal_file, 'r') as f:
            result["calendars"] = len(f.readlines())

    ins_file = qdir / "instruments" / "all.txt"
    if ins_file.exists():
        with open(ins_file, 'r') as f:
            result["instruments"] = len(f.readlines())

    features_dir = qdir / "features"
    if features_dir.exists():
        stock_dirs = [d for d in features_dir.iterdir() if d.is_dir()]
        result["features"] = len(stock_dirs)

        # 抽样检查一个股票的文件完整性
        if stock_dirs:
            sample = stock_dirs[0]
            expected_files = ['open', 'high', 'low', 'close', 'volume']
            for ef in expected_files:
                if not (sample / f"{ef}.1d.bin").exists():
                    result["errors"].append(f"{sample.name} 缺少 {ef}.1d.bin")

    return result
