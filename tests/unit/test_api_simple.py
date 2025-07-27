"""简单API测试"""

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
import sys
import os

# 添加项目根目录到路径
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))

from management_platform.api.main import setup_middleware, setup_exception_handlers, register_routes
from management_platform.database.connection import db_manager


def create_test_app() -> FastAPI:
    """创建测试用的FastAPI应用（不使用lifespan）"""
    
    app = FastAPI(
        title="网络拨测平台API",
        version="1.0.0",
        description="网络拨测平台管理API",
        docs_url="/docs",
        redoc_url="/redoc",
        openapi_url="/openapi.json"
    )
    
    # 初始化数据库（测试模式）
    db_manager.initialize(test_mode=True)
    
    # 设置中间件（跳过认证中间件以简化测试）
    from management_platform.api.middleware import (
        SecurityHeadersMiddleware,
        RequestLoggingMiddleware,
        DatabaseMiddleware
    )
    
    app.add_middleware(DatabaseMiddleware)
    app.add_middleware(SecurityHeadersMiddleware)
    app.add_middleware(RequestLoggingMiddleware)
    
    # 设置异常处理器
    setup_exception_handlers(app)
    
    # 注册路由
    register_routes(app)
    
    return app


@pytest.fixture
def client():
    """测试客户端"""
    app = create_test_app()
    return TestClient(app)


def test_health_check(client):
    """测试健康检查端点"""
    response = client.get("/health")
    assert response.status_code == 200
    
    data = response.json()
    assert data["status"] == "healthy"
    assert "timestamp" in data
    assert "version" in data


def test_root_endpoint(client):
    """测试根端点"""
    response = client.get("/")
    assert response.status_code == 200
    
    data = response.json()
    assert "message" in data
    assert "version" in data


def test_security_headers(client):
    """测试安全头"""
    response = client.get("/health")
    
    # 检查安全头
    assert response.headers["X-Content-Type-Options"] == "nosniff"
    assert response.headers["X-Frame-Options"] == "DENY"
    assert response.headers["X-XSS-Protection"] == "1; mode=block"
    assert "Strict-Transport-Security" in response.headers
    assert "Content-Security-Policy" in response.headers


def test_request_id_header(client):
    """测试请求ID头"""
    response = client.get("/health")
    
    # 检查请求ID头
    assert "X-Request-ID" in response.headers
    assert "X-Process-Time" in response.headers


def test_404_error(client):
    """测试404错误处理"""
    response = client.get("/nonexistent")
    assert response.status_code == 404
    
    data = response.json()
    assert data["error"] == "HTTP Error"
    assert "request_id" in data


def test_openapi_docs(client):
    """测试OpenAPI文档"""
    response = client.get("/openapi.json")
    assert response.status_code == 200
    
    data = response.json()
    assert data["info"]["title"] == "网络拨测平台API"
    assert "paths" in data


def test_swagger_ui(client):
    """测试Swagger UI"""
    response = client.get("/docs")
    assert response.status_code == 200
    assert "text/html" in response.headers["content-type"]


def test_redoc_ui(client):
    """测试ReDoc UI"""
    response = client.get("/redoc")
    assert response.status_code == 200
    assert "text/html" in response.headers["content-type"]


if __name__ == "__main__":
    pytest.main([__file__])