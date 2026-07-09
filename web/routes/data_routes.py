# -*- coding: utf-8 -*-
from datetime import datetime
from fastapi import APIRouter, Query, Request
import pandas as pd
from data.downloader import Downloader
from data.xt_provider import DataProvider

router = APIRouter()


def _get_downloader(request: Request) -> Downloader:
    """P2 优化：复用 app.state 中的 provider，避免每次请求新建 xtquant 连接"""
    # 优先复用 app.state 中的 provider（如果存在）
    provider = getattr(request.app.state, 'provider', None)
    if provider is None:
        provider = DataProvider()
        provider.connect()
        request.app.state.provider = provider
    elif not provider._connected:
        provider.connect()
    return Downloader(provider, request.app.state.database)


def _now() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


# ─── 查询接口 ───

@router.get("/kline")
def get_kline(request: Request, code: str = Query(...), period: str = Query("1d"),
              start: str = Query(""), end: str = Query("")):
    db = request.app.state.database
    df = db.get_daily_kline_df(code, period, start, end)
    if df.empty:
        return {"code": code, "count": 0, "data": []}
    records = df.to_dict('records')
    return {"code": code, "count": len(records), "data": records}


@router.get("/stocks")
def get_stocks(request: Request):
    db = request.app.state.database
    stocks = db.get_all_stocks()
    return {"count": len(stocks), "data": stocks}


@router.get("/sectors")
def get_sectors(request: Request):
    db = request.app.state.database
    sectors = db.get_all_sectors()
    return {"count": len(sectors), "data": sectors}


@router.get("/sector_stocks")
def get_sector_stocks(request: Request, sector_name: str = Query(...)):
    db = request.app.state.database
    stocks = db.get_sector_stocks(sector_name)
    return {"sector": sector_name, "count": len(stocks), "data": stocks}


@router.get("/db-status")
def get_db_status(request: Request):
    db = request.app.state.database
    stats = db.get_stats()
    return {"data": {
        "stock_count": stats["stocks"],
        "kline_count": stats["kline_rows"],
        "sector_count": stats["sectors"],
        "trade_count": stats["trades"],
        "kline_start": "",
        "kline_end": "",
    }}


@router.get("/stock-klines")
def get_stock_klines(request: Request):
    db = request.app.state.database
    summary = db.get_stock_klines_summary()
    data = [
        {
            "code": s["code"],
            "name": s["name"],
            "listing_date": s["listing_date"],
            "kline_start": s["kline_start"] or "",
            "kline_end": s["kline_end"] or "",
            "kline_count": s["row_count"] or 0,
        }
        for s in summary
    ]
    return {"count": len(data), "data": data}


# ─── 股票信息: 增量下载股票基本信息 ───

@router.post("/stocks/sync")
def stocks_sync(request: Request):
    try:
        dl = _get_downloader(request)
        count = dl.download_stock_info()
        dl.close()
        return {"status": "ok", "message": f"已同步 {count} 只股票基本信息",
                "count": count, "timestamp": _now()}
    except Exception as e:
        return {"status": "error", "message": str(e), "timestamp": _now()}


# ─── 财务数据 ───

@router.get("/financial")
def get_financial(request: Request, code: str = Query(...)):
    import math
    db = request.app.state.database
    df = db.get_financial_df(code)
    if df.empty:
        return {"code": code, "count": 0, "data": []}
    def _clean(v):
        if isinstance(v, float) and (math.isnan(v) or math.isinf(v)):
            return None
        return v
    records = [{k: _clean(v) for k, v in row.items()} for row in df.to_dict('records')]
    return {"code": code, "count": len(records), "data": records}


@router.post("/financial/download")
async def financial_download(request: Request):
    try:
        dl = _get_downloader(request)
        count = dl.download_all_financial()
        dl.close()
        return {"status": "ok", "message": f"财务数据下载完成，成功 {count} 只",
                "count": count, "timestamp": _now()}
    except Exception as e:
        return {"status": "error", "message": str(e), "timestamp": _now()}


@router.post("/financial/download-single")
async def financial_download_single(request: Request):
    """下载单只股票的财务数据"""
    body = await request.json()
    code = body.get("code", "")
    if not code:
        return {"status": "error", "message": "缺少股票代码"}
    try:
        dl = _get_downloader(request)
        dl.provider.download_financial_data([code])
        data = dl.provider.get_financial_data([code])
        if data and code in data and any(
            hasattr(v, 'empty') and not v.empty for v in data[code].values()
            if hasattr(v, 'empty')
        ):
            records = dl._financial_to_records(code, data[code])
            if records:
                dl.db.insert_financial(records)
                dl.close()
                return {"status": "ok", "message": f"{code} 财务数据已入库，{len(records)} 条",
                        "count": len(records), "timestamp": _now()}
        dl.close()
        return {"status": "ok", "message": f"{code} 无可用财务数据", "count": 0, "timestamp": _now()}
    except Exception as e:
        import traceback
        traceback.print_exc()
        return {"status": "error", "message": str(e), "timestamp": _now()}


# ─── 板块信息: 增量下载板块分类数据 ───

@router.post("/sectors/sync")
def sectors_sync(request: Request):
    try:
        dl = _get_downloader(request)
        dl.download_sector_data()
        total = len(dl.provider.get_sector_list())

        db = request.app.state.database
        written = 0
        db.conn.execute("BEGIN")
        try:
            for sector_name in dl.provider.get_sector_list():
                stocks = dl.provider.get_stock_list_in_sector(sector_name)
                if stocks:
                    db.insert_sector_records(sector_name, stocks)
                    written += 1
            db.conn.execute("COMMIT")
        except Exception:
            db.conn.execute("ROLLBACK")
            raise

        dl.close()
        return {"status": "ok", "message": f"已同步 {written}/{total} 个板块",
                "count": written, "total": total, "timestamp": _now()}
    except Exception as e:
        return {"status": "error", "message": str(e), "timestamp": _now()}


# ─── K线数据: 下载（仅无K线记录的股票，全量） ───

@router.post("/kline/download")
async def kline_download(request: Request):
    """下载K线数据：仅对 kline_index 中不存在的股票，获取完整历史K线并存储"""
    body = await request.json()
    period = body.get("period", "1d")
    try:
        dl = _get_downloader(request)
        db = request.app.state.database
        all_codes = dl.provider.get_stock_list()
        indexed = set()
        cursor = db.conn.execute("SELECT code FROM kline_index WHERE period = ?", (period,))
        for row in cursor.fetchall():
            indexed.add(row[0])
        new_codes = [c for c in all_codes if c not in indexed]

        if not new_codes:
            dl.close()
            return {"status": "ok", "message": "所有股票已有K线数据，无需下载",
                    "count": 0, "total": len(all_codes), "timestamp": _now()}

        success = 0
        for i, code in enumerate(new_codes):
            try:
                dl.provider.download_history([code], period=period)
                kline = dl.provider.get_kline([code], period=period, count=-1)
                if kline is not None and hasattr(kline, 'empty') and not kline.empty:
                    records = dl._kline_to_records(code, kline)
                    if records:
                        db.insert_daily_kline(records, period)
                        success += 1
                if (i + 1) % 50 == 0:
                    print(f"下载K线进度: {i+1}/{len(new_codes)}", flush=True)
            except Exception as e:
                print(f"下载 {code} K线失败: {e}", flush=True)

        dl.close()
        return {"status": "ok",
                "message": f"K线下载完成: 新增 {success}/{len(new_codes)} 只",
                "count": success, "total": len(new_codes), "timestamp": _now()}
    except Exception as e:
        return {"status": "error", "message": str(e), "timestamp": _now()}


# ─── K线数据: 更新（仅已有K线记录的股票，增量） ───

@router.post("/kline/update")
async def kline_update(request: Request):
    """更新K线数据：仅对 kline_index 中已存在的股票，补充从上次截止日期至今的增量"""
    body = await request.json()
    period = body.get("period", "1d")
    try:
        dl = _get_downloader(request)
        db = request.app.state.database
        cursor = db.conn.execute(
            "SELECT code, end_date FROM kline_index WHERE period = ? AND end_date IS NOT NULL AND end_date != ''",
            (period,)
        )
        existing = [(row[0], row[1]) for row in cursor.fetchall()]

        if not existing:
            dl.close()
            return {"status": "ok", "message": "无已有K线记录的股票，请先下载K线数据",
                    "count": 0, "timestamp": _now()}

        success = 0
        for i, (code, last_date) in enumerate(existing):
            try:
                dl.provider.download_history([code], period=period, start_time=last_date)
                kline = dl.provider.get_kline([code], period=period, start_time=last_date, count=0)
                if kline is not None and hasattr(kline, 'empty') and not kline.empty:
                    records = dl._kline_to_records(code, kline)
                    if records:
                        db.insert_daily_kline(records, period)
                        success += 1
                if (i + 1) % 100 == 0:
                    print(f"更新K线进度: {i+1}/{len(existing)}", flush=True)
            except Exception as e:
                print(f"更新 {code} K线失败: {e}", flush=True)

        dl.close()
        return {"status": "ok",
                "message": f"K线更新完成: {success}/{len(existing)} 只有新数据",
                "count": success, "total": len(existing), "timestamp": _now()}
    except Exception as e:
        return {"status": "error", "message": str(e), "timestamp": _now()}
