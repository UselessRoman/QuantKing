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
import numpy as np
import pandas as pd
from pathlib import Path
from datetime import datetime
from config.settings import KLINE_DIR, QLIB_DATA_DIR
from data.database import Database
from utils.logging import get_logger

_logger = get_logger("qlib_converter")


def _normalize_date(date_str) -> str:
    """
    将各种日期格式统一为 qlib 日频日历要求的 YYYY-MM-DD

    支持输入: '20230103' / '20230103' / 20230103 / '2023-01-03' / Timestamp
    """
    if date_str is None or date_str == '':
        return ''
    s = str(date_str).strip()
    if not s:
        return ''
    # 已经是 ISO 格式
    if len(s) == 10 and s[4] == '-' and s[7] == '-':
        return s
    # YYYYMMDD 数字串或整数
    digits = s.replace('-', '').replace('/', '')
    if len(digits) == 8 and digits.isdigit():
        return f"{digits[0:4]}-{digits[4:6]}-{digits[6:8]}"
    # 兜底：交给 pandas 解析
    try:
        return pd.to_datetime(s).strftime('%Y-%m-%d')
    except Exception:
        return ''


def _write_bin_file(file_path: Path, values: np.ndarray):
    """
    写入单个 qlib 二进制特征文件

    qlib 的 features/<code>/<field>.day.bin 格式为**纯 float32 小端序列**，
    长度必须等于 calendars/day.txt 的总交易日数，按日历顺序对齐——
    股票在该交易日无数据的位置填 NaN。

    历史 BUG: 旧实现每条记录写 int32(日期)+float32(值)，qlib 按 float32
    读取会把日期当作价格，整份数据错位损坏。本实现已修正为纯 float32。

    参数:
        file_path: 输出 .bin 路径
        values:    已与全局日历对齐的 float32 数组（缺失值用 np.nan）
    """
    file_path.parent.mkdir(parents=True, exist_ok=True)
    arr = np.asarray(values, dtype='<f4')  # 小端 float32，NaN 原生支持
    arr.tofile(file_path)


def convert_kline_to_qlib_format(
    parquet_dir: str = None,
    output_dir: str = None,
    period: str = "1d"
) -> int:
    """
    将现有 Parquet K线数据转换为 qlib 二进制格式

    产出 qlib 标准目录结构（日频）:
        data/qlib_data_cn/
        ├── calendars/day.txt        # 全市场交易日并集（YYYY-MM-DD，每行一个）
        ├── instruments/all.txt      # code<TAB>start<TAB>end（YYYY-MM-DD）
        └── features/<code>/
            ├── open.1d.bin          # 纯 float32 序列，长度 = 日历天数
            ├── high.1d.bin
            ├── low.1d.bin
            ├── close.1d.bin
            ├── volume.1d.bin
            └── amount.1d.bin

    对齐规则: 每只股票的特征数组按全局日历对齐，上市前/退市后/停牌日填 NaN。

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
        _logger.error("Parquet 数据目录不存在: %s", parquet_path)
        return 0

    calendars_dir = qlib_dir / "calendars"
    instruments_dir = qlib_dir / "instruments"
    features_dir = qlib_dir / "features"
    for d in (calendars_dir, instruments_dir, features_dir):
        d.mkdir(parents=True, exist_ok=True)

    parquet_files = list(parquet_path.glob("*.parquet"))
    if not parquet_files:
        _logger.error("未找到 Parquet 文件: %s", parquet_path)
        return 0

    _logger.info("找到 %d 个 Parquet 文件，开始转换...", len(parquet_files))

    field_map = {
        'open': 'open', 'high': 'high', 'low': 'low',
        'close': 'close', 'volume': 'volume', 'amount': 'amount',
    }

    # ── 第一遍：扫描所有 Parquet 收集日期并集（不保留 DF）──
    # P2 架构优化：旧代码将全部股票 DF 存入 stock_data dict 常驻内存，
    # 5000 股 × 10 年日线 ≈ 数 GB 峰值。改为两遍流式扫描：
    # 第一遍只收集日期并集（不存 DF），第二遍逐文件重新读→对齐→写 bin。
    all_iso_dates: set[str] = set()
    valid_files: list[tuple[str, Path]] = []

    for i, pq_file in enumerate(parquet_files):
        try:
            code = pq_file.stem
            df = pd.read_parquet(pq_file)
            if df.empty or 'date' not in df.columns:
                continue

            df = df.sort_values('date').reset_index(drop=True)
            date_strs = df['date'].astype(str).str.strip()
            parsed = pd.to_datetime(date_strs, errors='coerce', format=None)
            iso_dates = parsed.dt.strftime('%Y-%m-%d').fillna('').to_numpy()
            mask = iso_dates != ''
            if not mask.all():
                iso_dates = iso_dates[mask]
            if len(iso_dates) == 0:
                continue

            all_iso_dates.update(iso_dates.tolist())
            valid_files.append((code, pq_file))

            if (i + 1) % 500 == 0:
                _logger.info("扫描进度: %d/%d", i + 1, len(parquet_files))
        except Exception as e:
            _logger.warning("扫描 %s 失败: %s", pq_file.name, e)

    if not valid_files:
        _logger.error("没有可转换的有效数据")
        return 0

    # ── 建立全局日历（交易日并集，升序）──
    calendar: list[str] = sorted(all_iso_dates)
    cal_index = {d: i for i, d in enumerate(calendar)}
    n_cal = len(calendar)

    _logger.info("全局交易日历: %d 天 (%s ~ %s)", n_cal, calendar[0], calendar[-1])

    # 写日历
    with open(calendars_dir / "day.txt", 'w', encoding='utf-8') as f:
        f.write("\n".join(calendar))

    # ── 第二遍：逐文件重新读取 → 对齐 → 写 bin（不保留 DF）──
    instruments: list[tuple[str, str, str]] = []
    success_count = 0

    for idx, (code, pq_file) in enumerate(valid_files):
        try:
            df = pd.read_parquet(pq_file)
            if df.empty or 'date' not in df.columns:
                continue

            df = df.sort_values('date').reset_index(drop=True)
            date_strs = df['date'].astype(str).str.strip()
            parsed = pd.to_datetime(date_strs, errors='coerce', format=None)
            iso_dates = parsed.dt.strftime('%Y-%m-%d').fillna('').to_numpy()
            mask = iso_dates != ''
            if not mask.all():
                df = df[mask].reset_index(drop=True)
                iso_dates = iso_dates[mask]
            if len(df) == 0:
                continue

            start_date, end_date = str(iso_dates[0]), str(iso_dates[-1])
            instruments.append((code, start_date, end_date))

            stock_dir = features_dir / code
            stock_dir.mkdir(parents=True, exist_ok=True)

            positions = pd.Series(iso_dates).map(cal_index).to_numpy()

            for field, filename in field_map.items():
                if field not in df.columns:
                    continue
                aligned = np.full(n_cal, np.nan, dtype='<f4')
                values = df[field].to_numpy(dtype=np.float64)
                aligned[positions] = values
                _write_bin_file(stock_dir / f"{filename}.{period}.bin", aligned)

            success_count += 1
            if (idx + 1) % 500 == 0:
                _logger.info("转换进度: %d/%d", idx + 1, len(valid_files))
        except Exception as e:
            _logger.warning("转换 %s 失败: %s", code, e)

    # 写股票列表
    with open(instruments_dir / "all.txt", 'w', encoding='utf-8') as f:
        for code, start_date, end_date in sorted(instruments):
            f.write(f"{code}\t{start_date}\t{end_date}\n")

    _logger.info("qlib 数据转换完成: %d/%d 只股票", success_count, len(valid_files))
    return success_count


def validate_qlib_data(qlib_dir: str = None) -> dict:
    """
    验证 qlib 数据完整性

    校验内容:
        - calendars/day.txt    行数（全局交易日数）
        - instruments/all.txt  行数（股票数）
        - features/<code>/     子目录数
        - 抽样: 必需字段文件齐全，且每个 .bin 的 float32 记录数 = 日历天数
          （记录数不匹配通常意味着格式错误，如旧版 int32+float32 写法）

    参数:
        qlib_dir: qlib 数据目录

    返回:
        dict: 验证结果，包含 calendars/instruments/features 统计与 errors
    """
    qdir = Path(qlib_dir) if qlib_dir else Path(QLIB_DATA_DIR)

    result = {"calendars": 0, "instruments": 0, "features": 0, "errors": []}

    cal_file = qdir / "calendars" / "day.txt"
    if cal_file.exists():
        with open(cal_file, 'r', encoding='utf-8') as f:
            result["calendars"] = sum(1 for line in f if line.strip())

    ins_file = qdir / "instruments" / "all.txt"
    if ins_file.exists():
        with open(ins_file, 'r', encoding='utf-8') as f:
            result["instruments"] = sum(1 for line in f if line.strip())

    features_dir = qdir / "features"
    if features_dir.exists():
        stock_dirs = [d for d in features_dir.iterdir() if d.is_dir()]
        result["features"] = len(stock_dirs)

        # 抽样检查一个股票的文件完整性与记录数对齐
        if stock_dirs and result["calendars"] > 0:
            sample = stock_dirs[0]
            expected_files = ['open', 'high', 'low', 'close', 'volume']
            for ef in expected_files:
                bin_file = sample / f"{ef}.1d.bin"
                if not bin_file.exists():
                    result["errors"].append(f"{sample.name} 缺少 {ef}.1d.bin")
                    continue
                # 每个 float32 占 4 字节，记录数必须等于日历天数
                size_bytes = bin_file.stat().st_size
                if size_bytes % 4 != 0:
                    result["errors"].append(
                        f"{sample.name}/{ef}.1d.bin 字节数 {size_bytes} 非 4 的倍数（格式损坏）")
                    continue
                n_records = size_bytes // 4
                if n_records != result["calendars"]:
                    result["errors"].append(
                        f"{sample.name}/{ef}.1d.bin 记录数 {n_records} != 日历天数 "
                        f"{result['calendars']}（未按日历对齐）")

    return result
