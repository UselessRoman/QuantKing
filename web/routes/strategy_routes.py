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
import time

router = APIRouter()

# P3 架构优化：模块级缓存，避免每次请求重新加载因子/模型
# 旧代码每次 /predict 请求都 new FactorHandler + load_factors + trainer.load，
# 每次 /signals 请求都 new SignalGenerator（_cache 永远为空）。
_model_cache: dict = {}        # {(instruments, start, end): (trainer, handler, timestamp)}
_signal_cache: dict = {}       # {(instruments, start, end): (SignalGenerator, timestamp)}
_CACHE_TTL = 300               # 5 分钟 TTL


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
    """生成选股预测

    P3 架构优化：使用模块级缓存避免每次请求重新加载因子+模型。
    缓存键为 (instruments, start_time, end_time)，TTL 5 分钟。
    """
    try:
        from strategy.alpha_factors import FactorHandler
        from strategy.qlib_model import QlibTrainer
        from strategy.signal_generator import SignalGenerator

        cache_key = (req.instruments, req.start_time, req.end_time)
        now = time.time()

        # P3 优化：从缓存获取已训练的 trainer + handler
        cached = _model_cache.get(cache_key)
        if cached and (now - cached[2]) < _CACHE_TTL:
            trainer, handler = cached[0], cached[1]
        else:
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

            _model_cache[cache_key] = (trainer, handler, now)

        predictions = trainer.predict(handler)

        # P3 优化：缓存 SignalGenerator 实例（保留 _cache）
        sg_cached = _signal_cache.get(cache_key)
        if sg_cached and (now - sg_cached[1]) < _CACHE_TTL:
            sg = sg_cached[0]
        else:
            sg = SignalGenerator()
            _signal_cache[cache_key] = (sg, now)

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
    """获取最新选股信号（从缓存）

    P3 架构优化：从模块级缓存的 SignalGenerator 实例读取信号，
    而非每次请求 new 一个新实例（旧代码 _cache 永远为空）。
    """
    from strategy.signal_generator import SignalGenerator

    # P3 优化：从缓存获取 SignalGenerator（保留 _cache 中的信号数据）
    sg = None
    for cached_sg, ts in _signal_cache.values():
        sg = cached_sg
        break

    if sg is None:
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
