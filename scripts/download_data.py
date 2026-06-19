# -*- coding: utf-8 -*-
"""
数据下载脚本

一键下载 A 股全量日K线数据、股票基础信息和板块分类。

用法:
    python scripts/download_data.py

选项:
    --period 1d     K线周期（默认日线）
    --incremental   仅增量更新
"""
import sys
import argparse
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from data.xt_provider import DataProvider
from data.database import Database
from data.downloader import Downloader


def main():
    parser = argparse.ArgumentParser(description="下载A股数据到本地数据库")
    parser.add_argument("--period", default="1d", help="K线周期")
    parser.add_argument("--incremental", action="store_true", help="仅增量更新")
    parser.add_argument("--stocks-only", action="store_true", help="仅下载股票信息")
    parser.add_argument("--sectors-only", action="store_true", help="仅下载板块数据")
    parser.add_argument("--financial", action="store_true", help="下载财务数据")

    args = parser.parse_args()

    provider = DataProvider()
    db = Database()
    db.connect()
    db.initialize()
    downloader = Downloader(provider, db)

    try:
        provider.connect()
        print("miniQMT 行情连接成功")

        if args.stocks_only:
            downloader.download_stock_info()
        elif args.sectors_only:
            downloader.download_sector_data()
        elif args.financial:
            downloader.download_all_financial()
        elif args.incremental:
            downloader.incremental_update(period=args.period, days=5)
        else:
            # 全量下载
            print("=" * 50)
            print("开始全量数据下载...")
            print("=" * 50)

            print("\n[1/3] 下载股票基础信息...")
            downloader.download_stock_info()

            print("\n[2/3] 下载板块分类数据...")
            downloader.download_sector_data()

            print("\n[3/3] 下载日K线数据...")
            downloader.download_all_a_stocks(period=args.period)

            stats = db.get_stats()
            print("\n" + "=" * 50)
            print("下载完成！数据库统计:")
            print(f"  股票数量: {stats['stocks']}")
            print(f"  板块数量: {stats['sectors']}")
            print(f"  K线文件数: {stats['kline_files']}")
            print(f"  K线总行数: {stats['kline_rows']:,}")
            print("=" * 50)

    except ConnectionError as e:
        print(f"连接失败: {e}")
        print("请确保 miniQMT 已启动且端口 58610 已监听")
        sys.exit(1)
    except ImportError as e:
        print(f"导入失败: {e}")
        print("请确保已安装 xtquant 包")
        sys.exit(1)
    finally:
        provider.disconnect()
        downloader.close()
        db.close()


if __name__ == "__main__":
    main()
