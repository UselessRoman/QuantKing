# -*- coding: utf-8 -*-
"""Web API 测试"""
import pytest
from fastapi.testclient import TestClient
from web.app import app


# ─── 测试夹具：为 app.state 注入轻量 mock，避免触发 lifespan ───
# TestClient(app) 不进入 with 上下文时不会触发 lifespan，因此
# app.state.database / trader_manager 不会被初始化，data/monitor 路由会抛
# AttributeError。这里用 session 级 autouse fixture 提前注入 mock 对象，
# 让测试不依赖真实数据库和交易连接，既快又隔离。
# （不要改用 `with TestClient(app)`，那会触发 lifespan 去连 xtquant 实盘账号。）
@pytest.fixture(scope="session", autouse=True)
def _inject_mock_state():
    from unittest.mock import MagicMock

    # mock database：让各查询方法返回结构正确但为空的数据
    mock_db = MagicMock()
    mock_db.get_all_stocks.return_value = []
    mock_db.get_all_sectors.return_value = []
    mock_db.get_stats.return_value = {
        "stocks": 0, "sectors": 0, "trades": 0,
        "kline_files": 0, "kline_rows": 0,
    }
    mock_db.get_trade_records.return_value = []

    # mock trader_manager：get_connected_accounts 返回空列表
    mock_trader = MagicMock()
    mock_trader.get_connected_accounts.return_value = []

    app.state.database = mock_db
    app.state.trader_manager = mock_trader
    yield
    # session 结束清理，避免影响其他测试模块
    for attr in ("database", "trader_manager"):
        if hasattr(app.state, attr):
            delattr(app.state, attr)


client = TestClient(app)

# API Key for sensitive endpoints
_AUTH_HEADERS = {"X-API-Key": "quant-local-dev"}


class TestDataAPI:
    """数据查询 API 测试"""

    def test_get_stocks(self):
        response = client.get("/api/data/stocks")
        assert response.status_code == 200
        data = response.json()
        assert "count" in data
        assert "data" in data

    def test_get_db_status(self):
        response = client.get("/api/data/db-status")
        assert response.status_code == 200
        data = response.json()
        assert "data" in data
        assert "stock_count" in data["data"]

    def test_get_sectors(self):
        response = client.get("/api/data/sectors")
        assert response.status_code == 200


class TestStrategyAPI:
    """策略管理 API 测试"""

    def test_list_strategies(self):
        response = client.get("/api/strategy/list")
        assert response.status_code == 200
        data = response.json()
        assert "count" in data
        assert "data" in data

    def test_get_factors(self):
        response = client.get("/api/strategy/factors")
        assert response.status_code == 200
        data = response.json()
        assert "count" in data
        assert "categories" in data


class TestBacktestAPI:
    """回测 API 测试"""

    def test_get_strategies(self):
        response = client.get("/api/backtest/strategies")
        assert response.status_code == 200
        data = response.json()
        assert "count" in data
        assert len(data["data"]) >= 5

    def test_get_history(self):
        response = client.get("/api/backtest/history")
        assert response.status_code == 200
        data = response.json()
        assert "count" in data


class TestMonitorAPI:
    """监控 API 测试"""

    def test_get_accounts(self):
        response = client.get("/api/monitor/accounts", headers=_AUTH_HEADERS)
        assert response.status_code == 200
        data = response.json()
        assert "data" in data

    def test_unauthorized_access(self):
        """未提供 API Key 应返回 401"""
        response = client.get("/api/monitor/accounts")
        assert response.status_code == 401


class TestAuthPolicy:
    """鉴权策略测试：默认鉴权 + 白名单放行只读"""

    def test_readonly_whitelist_get_ok(self):
        """白名单内的只读 GET 无需 API Key"""
        response = client.get("/api/data/stocks")
        assert response.status_code == 200

    def test_write_post_requires_auth(self):
        """所有 POST 写操作必须鉴权"""
        response = client.post("/api/backtest/run", json={})
        assert response.status_code == 401

    def test_non_whitelist_get_requires_auth(self):
        """非白名单的 GET 路径也需鉴权（保守策略）"""
        # /api/data/kline/download 是 POST，这里用一个确实存在但不在白名单的 GET
        # 实际上现有 GET 端点大多在白名单，用一个不存在的 GET 验证默认鉴权
        response = client.get("/api/data/nonexistent_endpoint")
        # 不存在端点：鉴权先于路由匹配，未带 key 应返回 401 而非 404
        assert response.status_code == 401

    def test_write_post_with_auth_passes_auth(self):
        """带 API Key 的写操作通过鉴权层（路由逻辑由后续处理）"""
        response = client.post("/api/backtest/run", json={}, headers=_AUTH_HEADERS)
        # 通过鉴权后，因参数不全应由路由返回错误（非 401）
        assert response.status_code != 401


class TestRiskAPI:
    """风控 API 测试"""

    # 风控路径属于敏感信息，所有端点（含 GET）均需鉴权
    def test_get_status(self):
        response = client.get("/api/risk/status", headers=_AUTH_HEADERS)
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "ok"

    def test_get_status_unauthorized(self):
        """风控状态未鉴权应 401"""
        response = client.get("/api/risk/status")
        assert response.status_code == 401

    def test_get_config(self):
        response = client.get("/api/risk/config", headers=_AUTH_HEADERS)
        assert response.status_code == 200
        data = response.json()
        assert "data" in data
        assert "max_position_per_stock" in data["data"]

    def test_reset_unauthorized(self):
        """重置熔断需鉴权"""
        response = client.post("/api/risk/reset")
        assert response.status_code == 401

    def test_reset_authorized(self):
        """提供 API Key 可重置熔断"""
        response = client.post("/api/risk/reset", headers=_AUTH_HEADERS)
        assert response.status_code == 200


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
