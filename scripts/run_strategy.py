# -*- coding: utf-8 -*-
"""
策略运行脚本

运行选股策略并输出信号列表。

用法:
    python scripts/run_strategy.py --start 20240101 --end 20240331 --top-k 20
"""
import sys
import argparse
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))


def main():
    parser = argparse.ArgumentParser(description="运行选股策略生成信号")
    parser.add_argument("--start", default="20240101", help="数据起始日期")
    parser.add_argument("--end", default="20240331", help="数据结束日期")
    parser.add_argument("--top-k", type=int, default=20, help="选股数量")
    parser.add_argument("--model", default="models/lgb_model.pkl", help="模型文件路径")
    parser.add_argument("--sector", default="all", help="限制板块")

    args = parser.parse_args()

    print("=" * 50)
    print("  选股策略运行器")
    print("=" * 50)

    try:
        from strategy.alpha_factors import FactorHandler
        from strategy.qlib_model import QlibTrainer
        from strategy.signal_generator import SignalGenerator

        # 1. 加载因子
        print(f"\n[1/3] 加载因子数据 ({args.start} ~ {args.end})...")
        handler = FactorHandler(start_time=args.start, end_time=args.end)
        handler.load_factors(use_qlib=False)

        # 2. 加载模型或训练新模型
        trainer = QlibTrainer()
        model_path = Path(args.model)
        if model_path.exists():
            print(f"\n[2/3] 加载已有模型: {args.model}")
            trainer.load(args.model)
        else:
            print(f"\n[2/3] 模型不存在，开始训练...")
            result = trainer.train(handler)
            if "error" in result:
                print(f"训练失败: {result['error']}")
                sys.exit(1)
            trainer.save(args.model)

        # 3. 预测并生成信号
        print(f"\n[3/3] 计算预测分数...")
        predictions = trainer.predict(handler)

        sg = SignalGenerator()
        signals = sg.generate(predictions, top_k=args.top_k)

        if signals.empty:
            print("未生成任何选股信号")
            sys.exit(0)

        print(f"\n选股结果 (Top-{args.top_k}):")
        print("-" * 50)
        for _, row in signals.iterrows():
            print(f"  #{int(row['rank']):2d}  {row['code']:12s}  分数: {row['score']:.4f}  日期: {row['date']}")
        print("-" * 50)
        print(f"共选出 {len(signals)} 只股票")

    except Exception as e:
        print(f"运行失败: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()
