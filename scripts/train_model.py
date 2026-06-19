# -*- coding: utf-8 -*-
"""
qlib 模型训练脚本

基于本地 Parquet 数据训练 LightGBM 多因子模型。

用法:
    python scripts/train_model.py --start 20200101 --end 20231231 --model LightGBM
"""
import sys
import argparse
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))


def main():
    parser = argparse.ArgumentParser(description="训练 qlib 多因子模型")
    parser.add_argument("--start", default="20200101", help="训练数据起始日期")
    parser.add_argument("--end", default="20231231", help="训练数据结束日期")
    parser.add_argument("--model", default="LightGBM", help="模型类型 (LightGBM/XGBoost)")
    parser.add_argument("--output", default="models/lgb_model.pkl", help="模型输出路径")
    parser.add_argument("--top-k", type=int, default=20, help="选股数量")

    args = parser.parse_args()

    print("=" * 50)
    print("  qlib 多因子模型训练")
    print("=" * 50)
    print(f"数据区间: {args.start} ~ {args.end}")
    print(f"模型类型: {args.model}")
    print("=" * 50)

    try:
        from strategy.alpha_factors import FactorHandler
        from strategy.qlib_model import QlibTrainer
        from strategy.signal_generator import SignalGenerator

        # 1. 加载因子
        print("\n[1/3] 加载因子数据...")
        handler = FactorHandler(start_time=args.start, end_time=args.end)
        factors = handler.load_factors(use_qlib=False)  # 使用 pandas 模式
        print(f"  因子数量: {len(handler.get_factor_names())}")
        print(f"  样本数量: {len(factors)}")

        # 2. 训练模型
        print("\n[2/3] 训练模型...")
        trainer = QlibTrainer(model_type=args.model)
        result = trainer.train(handler)

        if "error" in result:
            print(f"训练失败: {result['error']}")
            sys.exit(1)

        print(f"  训练完成: {result.get('features', 0)} 个特征")
        if "feature_importance" in result:
            print(f"  Top 5 重要特征:")
            for fi in result["feature_importance"][:5]:
                print(f"    {fi['feature']}: {fi['importance']:.4f}")

        # 3. 保存模型
        print(f"\n[3/3] 保存模型...")
        trainer.save(args.output)

        print("\n" + "=" * 50)
        print("模型训练完成！")
        print(f"模型文件: {args.output}")
        print("=" * 50)

    except Exception as e:
        print(f"训练失败: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()
