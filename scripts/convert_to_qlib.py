# -*- coding: utf-8 -*-
"""
qlib 数据转换脚本

将本地 Parquet K线数据转换为 qlib 所需的二进制格式。

用法:
    python scripts/convert_to_qlib.py

前置条件:
    1. 已通过 scripts/download_data.py 下载了K线数据
    2. data/kline/1d/ 目录下有 *.parquet 文件
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from data.qlib_converter import convert_kline_to_qlib_format, validate_qlib_data


def main():
    print("=" * 50)
    print("开始转换 Parquet K线 → qlib 二进制格式")
    print("=" * 50)

    count = convert_kline_to_qlib_format()

    if count > 0:
        print("\n" + "=" * 50)
        print("验证 qlib 数据完整性...")
        validation = validate_qlib_data()
        print(f"  交易日历: {validation['calendars']} 天")
        print(f"  股票数量: {validation['instruments']}")
        print(f"  特征目录: {validation['features']} 个")
        if validation['errors']:
            print(f"  ⚠ 错误: {validation['errors']}")
        print("=" * 50)
        print("转换完成！qlib 数据已就绪。")
    else:
        print("转换失败，请检查 data/kline/1d/ 目录是否有数据。")
        sys.exit(1)


if __name__ == "__main__":
    main()
