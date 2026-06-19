# -*- coding: utf-8 -*-
"""Web API 测试"""
import pytest
from fastapi.testclient import TestClient
from web.app import app


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


class TestRiskAPI:
    """风控 API 测试"""

    def test_get_status(self):
        response = client.get("/api/risk/status")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "ok"

    def test_get_config(self):
        response = client.get("/api/risk/config")
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
