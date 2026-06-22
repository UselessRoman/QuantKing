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
        # 标签列 forward_ret_5d（未来5日收益）必须从特征中排除，否则会造成
        # 数据泄漏：用未来收益当特征预测未来收益，模型近乎完美拟合但实盘失效。
        # 旧代码 y = X.get('ret_5d') 把动量因子 ret_5d 当标签，而 ret_5d 同时
        # 是特征列（过去5日收益），并非未来收益，属于标签构造错误。
        meta_cols = ['code', 'date']
        label_col = 'forward_ret_5d'
        feature_cols = [
            c for c in factors.columns
            if c not in meta_cols and c != label_col
        ]

        if not feature_cols:
            return {"error": "没有可用的特征列"}

        if label_col not in factors.columns:
            return {
                "error": f"缺少标签列 {label_col}，请确认 FactorHandler 已构造未来收益标签"
            }

        # 去掉标签缺失的样本（最后5日无未来收益）
        factors = factors.dropna(subset=[label_col])

        X = factors[feature_cols].copy()
        X = X.replace([np.inf, -np.inf], np.nan)
        X = X.fillna(X.median())
        y = factors[label_col].copy()

        # 按日期切分训练/验证集，而非按行数。
        # 旧代码按 iloc[:0.7] 切分，但 factors 是 groupby('code') concat 后的，
        # 同一日期不同股票的行被打散到不同位置，切分点可能把同一天数据一半进
        # 训练一半进验证，造成时间泄漏。改为按交易日历切分。
        # factors 的 index 为 (date, code)（load_factors 里 set_index），date
        # 在 index 的 level 0；若被还原成列则直接取列。
        if 'date' in factors.columns:
            date_series = factors['date'].copy()
        elif factors.index.nlevels >= 2:
            date_series = factors.index.get_level_values(0)
            # 转为 object 数组便于比较
            date_series = pd.Series(date_series, index=factors.index)
        else:
            return {"error": "无法确定日期列，factors 既无 date 列也无多级索引"}

        unique_dates = sorted(pd.unique(date_series))
        if len(unique_dates) < 10:
            return {"error": "交易日数不足 10，无法切分训练/验证集"}
        train_end_date = unique_dates[int(len(unique_dates) * 0.7)]
        valid_end_date = unique_dates[int(len(unique_dates) * 0.85)]

        train_mask = date_series <= train_end_date
        valid_mask = (date_series > train_end_date) & (date_series <= valid_end_date)

        X_train, y_train = X[train_mask], y[train_mask]
        X_valid, y_valid = X[valid_mask], y[valid_mask]

        if len(X_train) == 0 or len(X_valid) == 0:
            return {"error": "训练集或验证集为空，请检查数据时间范围"}

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
