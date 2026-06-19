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
    所有 /api/ 下的写操作（POST/PUT/DELETE）和敏感读操作
    （/api/monitor/*, /api/risk/*）需要 X-API-Key 请求头。
    读操作（GET /api/data/*, /api/strategy/list|factors, /api/backtest/strategies|history）
    不做鉴权要求。
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

# 需要鉴权的路径前缀
_AUTH_REQUIRED_PREFIXES = (
    "/api/monitor",
    "/api/risk/reset",
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
    """对敏感路径进行 API Key 验证"""
    path = request.url.path

    # 仅对需要鉴权的路径前缀进行检查
    requires_auth = any(path.startswith(prefix) for prefix in _AUTH_REQUIRED_PREFIXES)

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
