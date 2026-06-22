# -*- coding: utf-8 -*-
"""
策略管理 API

提供 qlib 策略的因子查询、模型训练、预测和信号生成接口。

接口列表:
    GET  /api/strategy/list         — 获取可用策略列表
    GET  /api/strategy/factors      — 获取因子元信息
    POST /api/strategy/train        — 训练 qlib 模型
    POST /api/strategy/predict      — 运行预测
    GET  /api/strategy/signals      — 获取选股信号
    GET  /api/strategy/importance   — 获取特征重要性
"""
from fastapi import APIRouter, Query, Request
from pydantic import BaseModel

router = APIRouter()


class TrainRequest(BaseModel):
    instruments: str = "all"
    start_time: str = ""
    end_time: str = ""
    model_type: str = "LightGBM"
    top_k: int = 20


class PredictRequest(BaseModel):
    instruments: str = "all"
    start_time: str = ""
    end_time: str = ""
    model_path: str = ""
    top_k: int = 20
    min_score: float = None


@router.get("/list")
def list_strategies():
    """获取可用策略列表"""
    try:
        from backtest.bt_strategy import STRATEGY_REGISTRY
    except ImportError:
        return {"count": 0, "data": [], "message": "backtrader 未安装"}

    result = []
    for name, cls in STRATEGY_REGISTRY.items():
        params_info = {}
        if hasattr(cls, 'params') and hasattr(cls.params, '_getpairs'):
            # _getpairs() 在 backtrader 1.9.78+ 返回 OrderedDict，需用 .items()
            # 遍历；旧版返回 list[tuple]，.items() 对 OrderedDict 适用，
            # 对 tuple list 不适用，故做兼容处理。
            pairs = cls.params._getpairs()
            items = pairs.items() if hasattr(pairs, 'items') else pairs
            for p_name, p_val in items:
                if p_name not in ('stocklike', 'commtype', 'percabs'):
                    params_info[p_name] = str(p_val)

        result.append({
            "name": name,
            "description": cls.__doc__.split('\n')[0] if cls.__doc__ else "",
            "params": params_info,
        })

    return {"count": len(result), "data": result}


@router.get("/factors")
def get_factors():
    """获取因子元信息"""
    from strategy.alpha_factors import FACTOR_META

    factors = []
    for name, meta in FACTOR_META.items():
        factors.append({
            "name": name,
            "category": meta["category"],
            "description": meta["desc"],
        })

    categories = {}
    for f in factors:
        cat = f["category"]
        if cat not in categories:
            categories[cat] = []
        categories[cat].append(f)

    return {
        "count": len(factors),
        "categories": categories,
        "data": factors,
    }


@router.post("/train")
async def train_model(req: TrainRequest):
    """训练 qlib 模型"""
    try:
        from strategy.alpha_factors import FactorHandler
        from strategy.qlib_model import QlibTrainer

        handler = FactorHandler(
            instruments=req.instruments,
            start_time=req.start_time,
            end_time=req.end_time,
        )

        handler.load_factors(use_qlib=True)
        factor_names = handler.get_factor_names()

        trainer = QlibTrainer(model_type=req.model_type)
        result = trainer.train(handler)

        if "error" in result:
            return {"status": "error", "message": result["error"]}

        importance = trainer.get_feature_importance()
        if importance is not None and not importance.empty:
            result["feature_importance"] = importance.head(15).to_dict('records')

        result["factor_names"] = factor_names
        result["factor_count"] = len(factor_names)

        return {"status": "ok", "data": result}

    except Exception as e:
        import traceback
        traceback.print_exc()
        return {"status": "error", "message": str(e)}


@router.post("/predict")
async def predict_signals(req: PredictRequest):
    """生成选股预测"""
    try:
        from strategy.alpha_factors import FactorHandler
        from strategy.qlib_model import QlibTrainer
        from strategy.signal_generator import SignalGenerator

        handler = FactorHandler(
            instruments=req.instruments,
            start_time=req.start_time,
            end_time=req.end_time,
        )
        handler.load_factors(use_qlib=True)

        trainer = QlibTrainer()
        if req.model_path:
            trainer.load(req.model_path)
        else:
            train_result = trainer.train(handler)
            if "error" in train_result:
                return {"status": "error", "message": train_result["error"]}

        predictions = trainer.predict(handler)

        sg = SignalGenerator()
        signals = sg.generate(predictions, top_k=req.top_k, min_score=req.min_score)

        return {
            "status": "ok",
            "count": len(signals),
            "data": signals.head(req.top_k * 5).to_dict('records') if not signals.empty else [],
        }

    except Exception as e:
        import traceback
        traceback.print_exc()
        return {"status": "error", "message": str(e)}


@router.get("/signals")
def get_signals(request: Request, top_k: int = Query(20)):
    """获取最新选股信号（从缓存）"""
    from strategy.signal_generator import SignalGenerator

    sg = SignalGenerator()
    latest = sg.get_latest_signals()

    if latest.empty:
        return {"status": "ok", "count": 0, "data": [], "message": "暂无缓存的选股信号，请先执行 predict"}

    return {
        "status": "ok",
        "count": min(len(latest), top_k),
        "data": latest.head(top_k).to_dict('records'),
    }


@router.get("/importance")
def get_feature_importance():
    """获取最近一次训练的特征重要性"""
    return {
        "status": "ok",
        "message": "请通过 POST /api/strategy/train 获取特征重要性",
    }
