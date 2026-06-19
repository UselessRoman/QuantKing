# -*- coding: utf-8 -*-
"""
回测运行脚本

一键运行 backtrader 回测并输出绩效报告。

用法:
    python scripts/run_backtest.py --strategy ma_cross --codes 000001.SZ,600000.SH --start 20230101 --end 20231231
"""
import sys
import argparse
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from backtest.runner import BacktestRunner
from backtest.bt_strategy import get_strategy


def main():
    parser = argparse.ArgumentParser(description="运行 backtrader 回测")
    parser.add_argument("--strategy", default="ma_cross", help="策略名称")
    parser.add_argument("--codes", default="000001.SZ", help="股票代码，逗号分隔")
    parser.add_argument("--start", default="20230101", help="起始日期 YYYYMMDD")
    parser.add_argument("--end", default="20231231", help="结束日期 YYYYMMDD")
    parser.add_argument("--capital", type=float, default=100000, help="初始资金")
    parser.add_argument("--fast", type=int, default=5, help="短期参数")
    parser.add_argument("--slow", type=int, default=20, help="长期参数")
    parser.add_argument("--report", default="", help="输出HTML报告路径")

    args = parser.parse_args()

    codes = [c.strip() for c in args.codes.split(",")]

    print("=" * 60)
    print("           backtrader 回测运行器")
    print("=" * 60)
    print(f"策略: {args.strategy}")
    print(f"股票: {', '.join(codes)}")
    print(f"区间: {args.start} ~ {args.end}")
    print(f"资金: {args.capital:,.0f} 元")
    print("=" * 60)

    try:
        runner = BacktestRunner(initial_capital=args.capital)

        loaded = runner.load_data_from_db(codes, args.start, args.end)
        if loaded == 0:
            print("错误: 未加载到K线数据，请先运行 scripts/download_data.py 下载数据")
            sys.exit(1)

        runner.set_strategy(args.strategy, fast=args.fast, slow=args.slow)

        result = runner.run()

        # 输出报告
        from backtest.bt_analyzer import BacktestAnalyzer
        analyzer = BacktestAnalyzer()
        print()
        print(analyzer.format_report(result['performance']))

        if args.report:
            report_html = analyzer.generate_report(result['performance'], args.report)
            print(f"\n{report_html}")

    except Exception as e:
        print(f"回测失败: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()
