# -*- coding: utf-8 -*-
"""
qlib 模型训练与预测模块

基于 qlib 框架的标准化模型训练流程，支持:
    - LightGBM 模型训练
    - 模型持久化（保存/加载）
    - 特征重要性分析
    - 预测分数输出

使用方式:
    from strategy.alpha_factors import FactorHandler
    from strategy.qlib_model import QlibTrainer

    handler = FactorHandler(start_time="2020-01-01", end_time="2023-12-31")
    factors = handler.load_factors()

    trainer = QlibTrainer(model_type='LightGBM')
    result = trainer.train(handler)
    predictions = trainer.predict(handler)
    trainer.save("models/lgb_model.pkl")
"""
import os
import pickle
from pathlib import Path
from typing import Optional
import pandas as pd
import numpy as np


class QlibTrainer:
    """
    qlib 模型训练器

    支持 qlib 原生模式和 sklearn 兼容模式的模型训练。
    当 qlib 不可用时自动回退到 sklearn LightGBM。

    属性:
        model_type: 模型类型，如 'LightGBM', 'XGBoost'
        _model:     训练好的模型实例
        _feature_importance: 特征重要性 DataFrame
    """

    def __init__(self, model_type: str = 'LightGBM'):
        """
        参数:
            model_type: 模型类型，可选 'LightGBM', 'XGBoost'
        """
        self.model_type = model_type
        self._model = None
        self._feature_importance: Optional[pd.DataFrame] = None
        self._use_qlib = False

    def train(self, handler, target_col: str = 'ret_5d') -> dict:
        """
        训练模型

        参数:
            handler:     FactorHandler 实例（需已调用 load_factors）
            target_col:  目标列名（预测标签），如 'ret_5d' 表示预测未来5日收益率

        返回:
            dict: 训练结果，包含 loss/IC 等指标
        """
        factors = handler._factors
        if factors is None or factors.empty:
            return {"error": "因子数据为空，请先调用 handler.load_factors()"}

        # 尝试使用 qlib 原生训练
        try:
            return self._train_with_qlib(handler)
        except Exception as e:
            print(f"qlib 训练失败 ({e})，回退到 sklearn 模式")
            return self._train_sklearn(factors)

    def _train_with_qlib(self, handler) -> dict:
        """使用 qlib 框架训练"""
        try:
            import qlib
            from qlib.contrib.model.gbdt import LGBModel
            from qlib.data.dataset import DatasetH
            from qlib.data.dataset.handler import DataHandlerLP

            self._use_qlib = True

            handler._init_qlib()
            factors = handler._factors

            if factors is None or factors.empty:
                return {"error": "因子数据为空"}

            # 准备数据集
            feature_cols = [c for c in factors.columns
                            if c in handler.get_factor_meta()]

            # 使用 qlib DatasetH
            dataset_config = {
                "class": "DatasetH",
                "module_path": "qlib.data.dataset",
                "kwargs": {
                    "handler": {
                        "class": "Alpha158",
                        "module_path": "qlib.contrib.data.handler",
                        "kwargs": {
                            "start_time": handler.start_time or "2010-01-01",
                            "end_time": handler.end_time or "2025-12-31",
                            "fit_start_time": handler.start_time or "2010-01-01",
                            "fit_end_time": handler.end_time or "2025-12-31",
                            "instruments": handler.instruments,
                        },
                    },
                    "segments": {
                        "train": ("2010-01-01", "2020-12-31"),
                        "valid": ("2021-01-01", "2022-12-31"),
                        "test": ("2023-01-01", "2025-12-31"),
                    },
                },
            }

            # LightGBM 模型参数
            model = LGBModel(
                loss="mse",
                num_leaves=64,
                max_depth=6,
                learning_rate=0.05,
                n_estimators=500,
                early_stopping_rounds=50,
                lambda_l1=1.0,
                lambda_l2=1.0,
            )

            dataset = DatasetH(**dataset_config["kwargs"])
            model.fit(dataset)

            self._model = model
            self._feature_importance = model.get_feature_importance()

            return {
                "status": "success",
                "model_type": self.model_type,
                "features": len(feature_cols),
            }

        except ImportError:
            raise ImportError("请安装 qlib: pip install pyqlib")

    def _train_sklearn(self, factors: pd.DataFrame) -> dict:
        """使用 sklearn LightGBM 训练（qlib 不可用时的回退方案）"""
        try:
            import lightgbm as lgb
        except ImportError:
            return {"error": "请安装 lightgbm: pip install lightgbm"}

        # 准备特征和标签
        meta_cols = ['code', 'date']
        feature_cols = [c for c in factors.columns if c not in meta_cols]

        if not feature_cols:
            return {"error": "没有可用的特征列"}

        X = factors[feature_cols].copy()
        X = X.replace([np.inf, -np.inf], np.nan)
        X = X.fillna(X.median())

        # 目标: 未来5日收益率
        y = X.get('ret_5d', pd.Series(0, index=X.index))
        # 去掉目标列作为特征
        if 'ret_5d' in X.columns:
            X = X.drop(columns=['ret_5d'])
        feature_cols = list(X.columns)

        # 时间顺序切分
        n = len(X)
        train_end = int(n * 0.7)
        valid_end = int(n * 0.85)

        X_train, y_train = X.iloc[:train_end], y.iloc[:train_end]
        X_valid, y_valid = X.iloc[train_end:valid_end], y.iloc[train_end:valid_end]

        # 训练
        model = lgb.LGBMRegressor(
            n_estimators=300,
            max_depth=6,
            num_leaves=31,
            learning_rate=0.05,
            subsample=0.8,
            colsample_bytree=0.8,
            reg_alpha=0.1,
            reg_lambda=0.1,
            random_state=42,
            verbose=-1,
        )

        model.fit(
            X_train, y_train,
            eval_set=[(X_valid, y_valid)],
            callbacks=[lgb.early_stopping(50), lgb.log_evaluation(100)],
        )

        self._model = model
        self._use_qlib = False

        # 特征重要性
        importance = pd.DataFrame({
            'feature': feature_cols,
            'importance': model.feature_importances_,
        }).sort_values('importance', ascending=False)

        self._feature_importance = importance

        return {
            "status": "success",
            "model_type": self.model_type,
            "features": len(feature_cols),
            "best_iteration": model.best_iteration_ if hasattr(model, 'best_iteration_') else 300,
            "feature_importance": importance.head(10).to_dict('records'),
        }

    def predict(self, handler) -> pd.Series:
        """
        生成预测分数

        参数:
            handler: FactorHandler 实例（需已调用 load_factors）

        返回:
            pd.Series: 预测分数，index 为 (datetime, instrument)
        """
        if self._model is None:
            raise RuntimeError("模型未训练，请先调用 train()")

        factors = handler._factors
        if factors is None or factors.empty:
            raise ValueError("因子数据为空")

        if self._use_qlib:
            try:
                # qlib 模型的 predict 接口
                predictions = self._model.predict(handler._get_dataset())
                return predictions
            except Exception:
                pass

        # sklearn 模式
        meta_cols = ['code', 'date']
        feature_cols = [c for c in self._feature_importance['feature']
                        if c in factors.columns and c not in meta_cols]

        if not feature_cols:
            # 回退：使用所有因子列
            feature_cols = [c for c in factors.columns if c not in meta_cols and c != 'ret_5d']

        X = factors[feature_cols].copy()
        X = X.replace([np.inf, -np.inf], np.nan)
        X = X.fillna(X.median())

        predictions = self._model.predict(X)
        return pd.Series(predictions, index=factors.index)

    def save(self, path: str) -> None:
        """
        保存模型到文件

        参数:
            path: 文件路径，如 "models/lgb_model.pkl"
        """
        if self._model is None:
            raise RuntimeError("没有可保存的模型")

        Path(path).parent.mkdir(parents=True, exist_ok=True)
        data = {
            'model': self._model,
            'model_type': self.model_type,
            'use_qlib': self._use_qlib,
            'feature_importance': self._feature_importance,
        }
        with open(path, 'wb') as f:
            pickle.dump(data, f)
        print(f"模型已保存到: {path}")

    def load(self, path: str) -> None:
        """
        从文件加载模型

        参数:
            path: 模型文件路径
        """
        with open(path, 'rb') as f:
            data = pickle.load(f)

        self._model = data['model']
        self.model_type = data.get('model_type', 'LightGBM')
        self._use_qlib = data.get('use_qlib', False)
        self._feature_importance = data.get('feature_importance')

        print(f"模型已加载: {path}")

    def get_feature_importance(self) -> Optional[pd.DataFrame]:
        """获取特征重要性"""
        return self._feature_importance
