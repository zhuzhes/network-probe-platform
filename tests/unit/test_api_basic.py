"""基础API测试"""

import pytest
import asyncio
import httpx
import sys
import os

# 添加项目根目录到路径
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))

from management_platform.api.main import setup_middleware, setup_exception_handlers, register_routes
from management_platform.database.connection import db_manager
from fastapi import FastAPI


def create_test_app() -> FastAPI:
    """创建测试用的FastAPI应用"""
    
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
def app():
    """测试应用"""
    return create_test_app()


@pytest.mark.asyncio
async def test_health_check_with_httpx(app):
    """使用httpx测试健康检查端点"""
    async with httpx.AsyncClient(app=app, base_url="http://test") as client:
        response = await client.get("/health")
        assert response.status_code == 200
        
        data = response.json()
        assert data["status"] == "healthy"
        assert "timestamp" in data
        assert "version" in data


@pytest.mark.asyncio
async def test_root_endpoint_with_httpx(app):
    """使用httpx测试根端点"""
    async with httpx.AsyncClient(app=app, base_url="http://test") as client:
        response = await client.get("/")
        assert response.status_code == 200
        
        data = response.json()
        assert "message" in data
        assert "version" in data


@pytest.mark.asyncio
async def test_security_headers_with_httpx(app):
    """使用httpx测试安全头"""
    async with httpx.AsyncClient(app=app, base_url="http://test") as client:
        response = await client.get("/health")
        
        # 检查安全头
        assert response.headers["X-Content-Type-Options"] == "nosniff"
        assert response.headers["X-Frame-Options"] == "DENY"
        assert response.headers["X-XSS-Protection"] == "1; mode=block"
        assert "Strict-Transport-Security" in response.headers
        assert "Content-Security-Policy" in response.headers


@pytest.mark.asyncio
async def test_request_id_header_with_httpx(app):
    """使用httpx测试请求ID头"""
    async with httpx.AsyncClient(app=app, base_url="http://test") as client:
        response = await client.get("/health")
        
        # 检查请求ID头
        assert "X-Request-ID" in response.headers
        assert "X-Process-Time" in response.headers


@pytest.mark.asyncio
async def test_404_error_with_httpx(app):
    """使用httpx测试404错误处理"""
    async with httpx.AsyncClient(app=app, base_url="http://test") as client:
        response = await client.get("/nonexistent")
        assert response.status_code == 404
        
        data = response.json()
        assert data["error"] == "HTTP Error"
        assert "request_id" in data


@pytest.mark.asyncio
async def test_openapi_docs_with_httpx(app):
    """使用httpx测试OpenAPI文档"""
    async with httpx.AsyncClient(app=app, base_url="http://test") as client:
        response = await client.get("/openapi.json")
        assert response.status_code == 200
        
        data = response.json()
        assert data["info"]["title"] == "网络拨测平台API"
        assert "paths" in data


def test_app_creation():
    """测试应用创建"""
    app = create_test_app()
    assert app is not None
    assert app.title == "网络拨测平台API"
    
    # 检查路由是否注册
    routes = [route.path for route in app.routes if hasattr(route, 'path')]
    assert "/health" in routes
    assert "/" in routes
    assert "/openapi.json" in routes


def test_database_initialization():
    """测试数据库初始化"""
    # 数据库应该已经在应用创建时初始化
    assert db_manager._engine is not None
    assert db_manager._session_factory is not None
    
    # 测试健康检查
    assert db_manager.sync_health_check() is True


if __name__ == "__main__":
    pytest.main([__file__])