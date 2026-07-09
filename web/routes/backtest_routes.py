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

from utils.logging import get_logger

_logger = get_logger("backtest_routes")

router = APIRouter()

# 内存回测历史缓存：当数据库不可用时（如测试环境 mock）作为回退，
# 保证回测功能不因历史落库失败而中断。生产环境优先落 SQLite。
BACKTEST_HISTORY: list[dict] = []


def _save_history(request: Request, entry: dict) -> int:
    """将回测历史写入数据库，失败时回退到内存缓存。

    返回历史记录 id。db 不可用或写入失败时落内存并记 warning。
    """
    db = getattr(request.app.state, 'database', None)
    if db is not None:
        try:
            return db.insert_backtest_history(entry)
        except Exception as e:
            _logger.warning("回测历史落库失败，回退到内存: %s", e)
    # 回退：内存缓存
    entry['id'] = len(BACKTEST_HISTORY) + 1
    BACKTEST_HISTORY.append(entry)
    return entry['id']


def _load_history(request: Request, limit: int = 20) -> list[dict]:
    """从数据库读取回测历史，失败时回退到内存缓存"""
    db = getattr(request.app.state, 'database', None)
    if db is not None:
        try:
            return db.get_backtest_history(limit)
        except Exception as e:
            _logger.warning("回测历史读取失败，回退到内存: %s", e)
    return BACKTEST_HISTORY[-limit:][::-1]


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
            # _getpairs() 在 backtrader 1.9.78+ 返回 OrderedDict，需用 .items()
            # 遍历；旧版返回 list[tuple]，做兼容处理。
            pairs = cls.params._getpairs()
            items = pairs.items() if hasattr(pairs, 'items') else pairs
            for p_name, p_val in items:
                params[p_name] = str(p_val)

        result.append({
            "name": name,
            "description": (cls.__doc__ or "").strip().split('\n')[0],
            "params": params,
        })

    return {"count": len(result), "data": result}


@router.post("/run")
async def run_backtest(request: Request, req: BacktestRequest):
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

        # 保存到历史（落库，失败回退内存）
        history_entry = {
            "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "strategy": req.strategy_name,
            "params": req.params,
            "codes": req.stock_codes,
            "start_date": req.start_date or "最早",
            "end_date": req.end_date or "最新",
            "initial_capital": req.initial_capital,
            "performance": result.get("performance", {}),
        }
        backtest_id = _save_history(request, history_entry)

        return {
            "status": "ok",
            "data": result,
            "backtest_id": backtest_id,
        }

    except Exception as e:
        import traceback
        traceback.print_exc()
        return {"status": "error", "message": str(e)}


@router.post("/run_quick")
async def run_quick_backtest(request: Request, req: QuickBacktestRequest):
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
            "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "strategy": req.strategy_name,
            "params": {"fast": req.fast, "slow": req.slow},
            "codes": req.stock_codes,
            "start_date": req.start_date,
            "end_date": req.end_date,
            "initial_capital": req.initial_capital,
            "performance": result.get("performance", {}),
        }
        backtest_id = _save_history(request, history_entry)

        return {"status": "ok", "data": result, "backtest_id": backtest_id}

    except Exception as e:
        _logger.error("快速回测异常: %s", e, exc_info=True)
        return {"status": "error", "message": str(e)}


@router.get("/history")
def get_backtest_history(request: Request):
    """获取回测历史记录（从数据库读取，失败回退内存）"""
    history = _load_history(request, limit=20)
    return {"count": len(history), "data": history}


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
        # P2 优化：旧代码每个策略都新建 BacktestRunner 并重复 load_data_from_db，
        # N 策略 × M 股票 = N×M 次 Parquet 读取。现预加载一次 DataFrame，
        # 用 load_data_from_df 复用，仅 N 次 backtrader feed 构建（不可避免）。
        db = request.app.state.database
        from data.database import Database
        from data.backtrader_feeder import load_bt_data
        import backtrader as bt

        kline_dict = {}
        for code in stock_codes:
            df = db.get_daily_kline_df(code, '1d', start_date, end_date)
            if not df.empty:
                kline_dict[code] = df

        if not kline_dict:
            return {"status": "error", "message": "无可用K线数据"}

        results = []
        for s_name in strategies:
            runner = BacktestRunner(initial_capital=initial_capital)
            # 复用已加载的 DataFrame，避免重复读 Parquet
            loaded = runner.load_data_from_df(kline_dict)
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
