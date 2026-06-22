# -*- coding: utf-8 -*-
"""
Web 应用主入口

基于 FastAPI 构建的量化交易平台 REST API 服务和静态页面托管。

路由前缀:
    /api/data       — 行情数据查询与下载
    /api/strategy   — qlib 策略管理（因子、训练、预测）
    /api/backtest   — backtrader 回测执行与结果查询
    /api/monitor    — 实时交易监控（持仓、委托、资产）
    /api/risk       — 风险控制状态与配置
    /               — 前端静态页面（index.html）

鉴权机制:
    默认所有 /api/ 请求都需 X-API-Key 鉴权；仅下列公开只读 GET 放行：
        /api/data/kline|stocks|sectors|sector_stocks|db-status|stock-klines|financial
        /api/strategy/list|factors|signals|importance
        /api/backtest/strategies|history
    监控（/api/monitor/*）、风控（/api/risk/*）及所有写操作（POST/PUT/DELETE）
    一律需鉴权。
"""
from contextlib import asynccontextmanager
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import JSONResponse
from pathlib import Path
from config.settings import WEB_API_KEY
from trading.xt_trader import TraderManager
from data.database import Database
from web.routes import data_routes, strategy_routes, backtest_routes, monitor_routes, risk_routes

# 公开只读 GET 白名单（无需 API Key）。
# 原则：只放行不涉及敏感账号/风控状态、且为查询性质的 GET 端点；
#       所有 POST/PUT/DELETE 及 monitor/risk 一律鉴权。
_READONLY_WHITELIST = {
    "/api/data/kline",
    "/api/data/stocks",
    "/api/data/sectors",
    "/api/data/sector_stocks",
    "/api/data/db-status",
    "/api/data/stock-klines",
    "/api/data/financial",
    "/api/strategy/list",
    "/api/strategy/factors",
    "/api/strategy/signals",
    "/api/strategy/importance",
    "/api/backtest/strategies",
    "/api/backtest/history",
}

# 一律鉴权的路径前缀（即使方法是 GET）
_AUTH_REQUIRED_PREFIXES = (
    "/api/monitor",
    "/api/risk",
)


@asynccontextmanager
async def lifespan(application: FastAPI):
    """应用生命周期管理"""
    trader = TraderManager()
    print("正在连接实盘交易账号...")
    results = trader.connect_all()
    for aid, ok in results.items():
        if ok:
            print(f"  [{aid}] 连接成功")
        else:
            print(f"  [{aid}] 连接失败")
    application.state.trader_manager = trader

    db = Database()
    db.connect()
    db.initialize()
    application.state.database = db
    print("数据库已连接并初始化")

    yield

    trader.disconnect_all()
    db.close()
    print("交易连接已断开，数据库已关闭")


app = FastAPI(
    title="量化交易平台",
    description="基于 XTquant + qlib + backtrader 的个人量化投资平台",
    version="2.0.0",
    lifespan=lifespan,
)


# ─── API Key 鉴权中间件 ───
@app.middleware("http")
async def api_key_middleware(request: Request, call_next):
    """API Key 鉴权：默认全部鉴权，仅白名单只读 GET 放行。

    判定顺序：
        1. monitor/risk 前缀 → 一律鉴权（含 GET）
        2. 非白名单的 GET → 鉴权
        3. 所有 POST/PUT/DELETE → 鉴权
        4. 白名单内的 GET → 放行
    """
    path = request.url.path
    method = request.method

    # 只对 /api/ 路径做鉴权，静态资源和根路径放行
    if not path.startswith("/api/"):
        return await call_next(request)

    requires_auth = False
    if any(path.startswith(prefix) for prefix in _AUTH_REQUIRED_PREFIXES):
        requires_auth = True
    elif method in ("POST", "PUT", "DELETE"):
        requires_auth = True
    elif path not in _READONLY_WHITELIST:
        # 非白名单的 GET 也鉴权（保守策略）
        requires_auth = True

    if requires_auth:
        api_key = request.headers.get("X-API-Key", "")
        if not api_key or api_key != WEB_API_KEY:
            return JSONResponse(
                status_code=401,
                content={"status": "error", "message": "未授权访问，请提供有效的 X-API-Key"},
            )

    response = await call_next(request)
    return response


# CORS 中间件 — 仅允许本地来源
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:8000",
        "http://127.0.0.1:8000",
    ],
    allow_credentials=True,
    allow_methods=["GET", "POST"],
    allow_headers=["X-API-Key", "Content-Type"],
)

# 路由注册
app.include_router(data_routes.router, prefix="/api/data", tags=["数据"])
app.include_router(strategy_routes.router, prefix="/api/strategy", tags=["策略"])
app.include_router(backtest_routes.router, prefix="/api/backtest", tags=["回测"])
app.include_router(monitor_routes.router, prefix="/api/monitor", tags=["监控"])
app.include_router(risk_routes.router, prefix="/api/risk", tags=["风控"])

# 静态文件
static_dir = Path(__file__).parent / "static"
static_dir.mkdir(parents=True, exist_ok=True)
app.mount("/", StaticFiles(directory=str(static_dir), html=True), name="static")
