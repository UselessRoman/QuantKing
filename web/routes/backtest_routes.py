# -*- coding: utf-8 -*-
"""
回测管理 API

提供 backtrader 回测的执行、结果查询和历史管理。

接口列表:
    POST /api/backtest/run          — 执行回测
    POST /api/backtest/run_quick    — 快速回测（简化参数）
    GET  /api/backtest/strategies   — 获取可用回测策略
    GET  /api/backtest/history      — 回测历史记录
    GET  /api/backtest/compare      — 策略对比回测
"""
from fastapi import APIRouter, Query, Request
from pydantic import BaseModel
import json
from datetime import datetime

router = APIRouter()

# 简易回测历史（内存缓存，生产环境应使用数据库）
BACKTEST_HISTORY: list[dict] = []


class BacktestRequest(BaseModel):
    strategy_name: str = "ma_cross"
    stock_codes: list[str] = ["000001.SZ"]
    start_date: str = ""
    end_date: str = ""
    initial_capital: float = 100000
    params: dict = {}


class QuickBacktestRequest(BaseModel):
    strategy_name: str = "ma_cross"
    stock_codes: list[str] = ["000001.SZ"]
    start_date: str = "20230101"
    end_date: str = "20231231"
    initial_capital: float = 100000
    fast: int = 5
    slow: int = 20


@router.get("/strategies")
def get_backtest_strategies():
    """获取可用的回测策略列表"""
    try:
        from backtest.bt_strategy import STRATEGY_REGISTRY
    except ImportError:
        return {"count": 0, "data": [], "message": "backtrader 未安装"}

    result = []
    for name, cls in STRATEGY_REGISTRY.items():
        params = {}
        if hasattr(cls, 'params') and hasattr(cls.params, '_getpairs'):
            for p_name, p_val in cls.params._getpairs():
                params[p_name] = str(p_val)

        result.append({
            "name": name,
            "description": (cls.__doc__ or "").strip().split('\n')[0],
            "params": params,
        })

    return {"count": len(result), "data": result}


@router.post("/run")
async def run_backtest(req: BacktestRequest):
    """执行回测"""
    try:
        from backtest.runner import BacktestRunner
    except ImportError:
        return {"status": "error", "message": "backtrader 未安装，请执行 pip install backtrader"}

    try:
        runner = BacktestRunner(initial_capital=req.initial_capital)

        loaded = runner.load_data_from_db(
            req.stock_codes, req.start_date, req.end_date
        )

        if loaded == 0:
            return {"status": "error", "message": "未加载到任何K线数据，请先下载数据"}

        runner.set_strategy(req.strategy_name, **req.params)
        result = runner.run()

        # 保存到历史
        history_entry = {
            "id": len(BACKTEST_HISTORY) + 1,
            "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "strategy": req.strategy_name,
            "codes": req.stock_codes,
            "start_date": req.start_date or "最早",
            "end_date": req.end_date or "最新",
            "initial_capital": req.initial_capital,
            "performance": result.get("performance", {}),
        }
        BACKTEST_HISTORY.append(history_entry)

        return {
            "status": "ok",
            "data": result,
            "backtest_id": history_entry["id"],
        }

    except Exception as e:
        import traceback
        traceback.print_exc()
        return {"status": "error", "message": str(e)}


@router.post("/run_quick")
async def run_quick_backtest(req: QuickBacktestRequest):
    """快速回测（简化参数）"""
    try:
        from backtest.runner import BacktestRunner
    except ImportError:
        return {"status": "error", "message": "backtrader 未安装，请执行 pip install backtrader"}

    try:
        runner = BacktestRunner(initial_capital=req.initial_capital)
        result = runner.run_quick(
            codes=req.stock_codes,
            strategy_name=req.strategy_name,
            start_date=req.start_date,
            end_date=req.end_date,
            fast=req.fast,
            slow=req.slow,
        )

        if "error" in result:
            return {"status": "error", "message": result["error"]}

        history_entry = {
            "id": len(BACKTEST_HISTORY) + 1,
            "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "strategy": req.strategy_name,
            "codes": req.stock_codes,
            "start_date": req.start_date,
            "end_date": req.end_date,
            "initial_capital": req.initial_capital,
            "performance": result.get("performance", {}),
        }
        BACKTEST_HISTORY.append(history_entry)

        return {"status": "ok", "data": result, "backtest_id": history_entry["id"]}

    except Exception as e:
        import traceback
        traceback.print_exc()
        return {"status": "error", "message": str(e)}


@router.get("/history")
def get_backtest_history():
    """获取回测历史记录"""
    return {"count": len(BACKTEST_HISTORY), "data": BACKTEST_HISTORY[-20:][::-1]}


@router.post("/compare")
async def compare_strategies(request: Request):
    """策略对比回测：对多只股票运行多个策略并对比"""
    body = await request.json()
    stock_codes = body.get("stock_codes", ["000001.SZ"])
    strategies = body.get("strategies", ["ma_cross", "macd"])
    start_date = body.get("start_date", "20230101")
    end_date = body.get("end_date", "20231231")
    initial_capital = body.get("initial_capital", 100000)

    try:
        from backtest.runner import BacktestRunner
    except ImportError:
        return {"status": "error", "message": "backtrader 未安装，请执行 pip install backtrader"}

    try:
        results = []
        for s_name in strategies:
            runner = BacktestRunner(initial_capital=initial_capital)
            loaded = runner.load_data_from_db(stock_codes, start_date, end_date)
            if loaded == 0:
                continue
            runner.set_strategy(s_name)
            result = runner.run()
            results.append({
                "strategy": s_name,
                "performance": result.get("performance", {}),
            })

        # 排序对比
        if results:
            results.sort(
                key=lambda x: x["performance"].get("total_return", 0),
                reverse=True
            )

        return {"status": "ok", "count": len(results), "data": results}

    except Exception as e:
        import traceback
        traceback.print_exc()
        return {"status": "error", "message": str(e)}
