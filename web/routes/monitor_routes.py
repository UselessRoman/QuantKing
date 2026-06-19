# -*- coding: utf-8 -*-
"""
交易监控 API

提供实盘交易的持仓、委托、资产和交易记录的实时查询接口。

接口列表:
    GET  /api/monitor/positions     — 持仓查询
    GET  /api/monitor/orders        — 委托查询
    GET  /api/monitor/trades        — 成交查询
    GET  /api/monitor/asset         — 资产查询
    GET  /api/monitor/accounts      — 账号状态
    GET  /api/monitor/records       — 交易记录（从本地DB）
    GET  /api/monitor/dashboard     — 仪表盘摘要
"""
from fastapi import APIRouter, Query, Request

router = APIRouter()


def _get_trader(request: Request):
    return request.app.state.trader_manager


@router.get("/positions")
def get_positions(request: Request, account_id: str = Query("real")):
    """查询持仓"""
    trader = _get_trader(request)
    positions = trader.query_positions(account_id)
    return {"account_id": account_id, "count": len(positions), "data": positions}


@router.get("/orders")
def get_orders(request: Request, account_id: str = Query("real")):
    """查询当日委托"""
    trader = _get_trader(request)
    orders = trader.query_orders(account_id)
    return {"account_id": account_id, "count": len(orders), "data": orders}


@router.get("/trades")
def get_trades(request: Request, account_id: str = Query("real")):
    """查询当日成交"""
    trader = _get_trader(request)
    trades = trader.query_trades(account_id)
    return {"account_id": account_id, "count": len(trades), "data": trades}


@router.get("/asset")
def get_asset(request: Request, account_id: str = Query("real")):
    """查询账户资产"""
    trader = _get_trader(request)
    asset = trader.query_asset(account_id)
    return {"account_id": account_id, "data": asset}


@router.get("/accounts")
def get_accounts(request: Request):
    """获取账号连接状态"""
    from config.settings import ACCOUNTS

    trader = _get_trader(request)
    connected = trader.get_connected_accounts()
    result = []
    for acc in ACCOUNTS:
        result.append({
            "id": acc["id"],
            "label": acc["label"],
            "connected": acc["id"] in connected,
        })
    return {"data": result}


@router.get("/records")
def get_records(request: Request, account_id: str = Query(""),
                start: str = Query(""), end: str = Query("")):
    """查询本地交易记录"""
    db = request.app.state.database
    records = db.get_trade_records(account_id, start, end)
    return {"count": len(records), "data": records}


@router.get("/dashboard")
def get_dashboard(request: Request, account_id: str = Query("real")):
    """仪表盘摘要数据"""
    trader = _get_trader(request)
    db = request.app.state.database

    asset = trader.query_asset(account_id) or {}
    positions = trader.query_positions(account_id)

    # 持仓盈亏（按市值估算）
    total_market_value = sum(p.get('market_value', 0) for p in positions)
    total_cost = sum(p.get('open_price', 0) * p.get('volume', 0) for p in positions)
    unrealized_pnl = total_market_value - total_cost

    stats = db.get_stats()

    return {
        "data": {
            "account_id": account_id,
            "asset": asset,
            "positions_count": len(positions),
            "total_market_value": round(total_market_value, 2),
            "unrealized_pnl": round(unrealized_pnl, 2),
            "db_stats": stats,
            "connected": trader.is_connected(account_id),
        }
    }
