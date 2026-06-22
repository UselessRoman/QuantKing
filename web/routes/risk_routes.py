# -*- coding: utf-8 -*-
"""
风险控制 API

提供风险状态的查询、配置和熔断管理。

接口列表:
    GET  /api/risk/status      — 获取当前风险状态
    GET  /api/risk/config       — 获取风控参数配置
    POST /api/risk/config       — 更新风控参数（热更新 + 持久化 yaml）
    POST /api/risk/reset        — 重置熔断状态
    POST /api/risk/check_order  — 模拟订单风险检查
"""
from fastapi import APIRouter, Request
from config.settings import RISK_CONFIG, RISK_CONFIG_PATH

router = APIRouter()


def get_risk_manager(request: Request):
    """从 app.state 获取风险管理器实例（应用启动时初始化）"""
    from risk.risk_manager import RiskManager

    if not hasattr(request.app.state, 'risk_manager'):
        request.app.state.risk_manager = RiskManager()
    return request.app.state.risk_manager


@router.get("/status")
def get_risk_status(request: Request):
    """获取当前风险状态"""
    rm = get_risk_manager(request)
    summary = rm.get_risk_summary()
    return {"status": "ok", "data": summary}


@router.get("/config")
def get_risk_config():
    """获取风控参数配置"""
    return {"status": "ok", "data": RISK_CONFIG}


@router.post("/config")
async def update_risk_config(request: Request):
    """更新风控参数配置（热更新内存 + 持久化到 risk.yaml）。

    Body: 部分风控参数，如 {"max_daily_loss_ratio": 0.03}
    """
    from utils.logging import get_logger
    _logger = get_logger("risk_routes")

    body = await request.json()
    # 只允许更新已知键，防止注入未知参数
    allowed = set(RISK_CONFIG.keys())
    updates = {k: v for k, v in body.items() if k in allowed}
    if not updates:
        return {"status": "error", "message": "没有有效的风控参数可更新"}

    RISK_CONFIG.update(updates)

    # 持久化到 yaml
    try:
        import yaml
        with open(RISK_CONFIG_PATH, 'w', encoding='utf-8') as f:
            yaml.dump(RISK_CONFIG, f, allow_unicode=True, default_flow_style=False)
    except Exception as e:
        _logger.error("风控参数持久化失败: %s", e)
        return {"status": "ok", "data": RISK_CONFIG,
                "warning": f"内存已更新但持久化失败: {e}"}

    # 同步更新当前 risk_manager 实例的配置
    rm = get_risk_manager(request)
    rm.config = dict(RISK_CONFIG)

    _logger.info("风控参数已更新: %s", updates)
    return {"status": "ok", "data": RISK_CONFIG}


@router.post("/reset")
async def reset_meltdown(request: Request):
    """重置熔断状态（需谨慎操作）"""
    rm = get_risk_manager(request)
    rm.reset_meltdown()
    return {"status": "ok", "message": "熔断状态已重置"}


@router.post("/check_order")
async def check_order(request: Request):
    """
    模拟订单风险检查

    Body:
    {
        "action": "BUY" | "SELL",
        "code": "000001.SZ",
        "price": 12.5,
        "volume": 1000,
        "cash": 50000,              // 可用资金（买入时必填）
        "positions": {...},          // 持仓信息
        "prev_close": 12.0
    }
    """
    body = await request.json()
    rm = get_risk_manager(request)

    action = body.get("action", "BUY")
    code = body.get("code", "")
    price = body.get("price", 0)
    volume = body.get("volume", 0)
    cash = body.get("cash", 0)
    positions = body.get("positions", {})
    prev_close = body.get("prev_close", 0)

    if action == "BUY":
        ok, reason = rm.check_buy(code, price, volume, cash, positions, prev_close)
    elif action == "SELL":
        ok, reason = rm.check_sell(code, volume, positions, prev_close)
    else:
        return {"status": "error", "message": f"不支持的操作类型: {action}"}

    return {
        "status": "ok",
        "passed": ok,
        "reason": reason,
        "meltdown": rm.is_meltdown(),
    }
