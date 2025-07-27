"""API框架测试"""

import pytest
from fastapi.testclient import TestClient
from unittest.mock import patch, MagicMock

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))

from management_platform.api.main import create_app


@pytest.fixture
def client():
    """测试客户端"""
    app = create_app()
    return TestClient(app)


@pytest.fixture
def mock_db_session():
    """模拟数据库会话"""
    with patch('management_platform.database.connection.get_database_session') as mock:
        mock_session = MagicMock()
        mock.__enter__ = MagicMock(return_value=mock_session)
        mock.__exit__ = MagicMock(return_value=None)
        mock.return_value = mock
        yield mock_session


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


def test_cors_headers(client):
    """测试CORS头"""
    response = client.options("/health")
    
    # 检查CORS头
    assert "Access-Control-Allow-Origin" in response.headers
    assert "Access-Control-Allow-Methods" in response.headers


def test_rate_limiting(client):
    """测试限流"""
    # 发送大量请求
    responses = []
    for i in range(105):  # 超过默认限制100
        response = client.get("/health")
        responses.append(response)
    
    # 检查是否有429响应
    status_codes = [r.status_code for r in responses]
    assert 429 in status_codes


def test_404_error(client):
    """测试404错误处理"""
    response = client.get("/nonexistent")
    assert response.status_code == 404
    
    data = response.json()
    assert data["error"] == "HTTP Error"
    assert "request_id" in data


def test_validation_error(client):
    """测试验证错误处理"""
    # 发送无效的JSON数据
    response = client.post(
        "/api/v1/test",  # 假设的端点
        json={"invalid": "data"},
        headers={"Content-Type": "application/json"}
    )
    
    # 应该返回404（因为端点不存在）或422（如果端点存在但数据无效）
    assert response.status_code in [404, 422]


@patch('management_platform.database.connection.get_database_session')
def test_database_middleware(mock_db, client):
    """测试数据库中间件"""
    mock_session = MagicMock()
    mock_db.return_value.__enter__.return_value = mock_session
    
    response = client.get("/health")
    assert response.status_code == 200
    
    # 验证数据库会话被创建
    mock_db.assert_called()


def test_openapi_docs(client):
    """测试OpenAPI文档"""
    response = client.get("/openapi.json")
    assert response.status_code == 200
    
    data = response.json()
    assert data["info"]["title"] == "网络拨测平台API"
    assert "paths" in data
    assert "components" in data


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


class TestMiddleware:
    """中间件测试"""
    
    def test_security_headers_middleware(self, client):
        """测试安全头中间件"""
        response = client.get("/health")
        
        required_headers = [
            "X-Content-Type-Options",
            "X-Frame-Options", 
            "X-XSS-Protection",
            "Strict-Transport-Security",
            "Referrer-Policy",
            "Content-Security-Policy"
        ]
        
        for header in required_headers:
            assert header in response.headers
    
    def test_request_logging_middleware(self, client):
        """测试请求日志中间件"""
        response = client.get("/health")
        
        # 检查日志相关头
        assert "X-Request-ID" in response.headers
        assert "X-Process-Time" in response.headers
        
        # 验证UUID格式
        import uuid
        request_id = response.headers["X-Request-ID"]
        uuid.UUID(request_id)  # 如果不是有效UUID会抛出异常
    
    def test_rate_limit_middleware(self, client):
        """测试限流中间件"""
        # 快速发送多个请求
        responses = []
        for _ in range(10):
            response = client.get("/health")
            responses.append(response.status_code)
        
        # 大部分请求应该成功
        success_count = responses.count(200)
        assert success_count >= 8  # 允许少量限流


class TestExceptionHandlers:
    """异常处理器测试"""
    
    def test_http_exception_format(self, client):
        """测试HTTP异常格式"""
        response = client.get("/nonexistent")
        assert response.status_code == 404
        
        data = response.json()
        required_fields = ["error", "message", "status_code", "request_id"]
        for field in required_fields:
            assert field in data
    
    def test_request_id_in_error(self, client):
        """测试错误响应中的请求ID"""
        response = client.get("/nonexistent")
        
        data = response.json()
        request_id = data["request_id"]
        
        # 验证UUID格式
        import uuid
        uuid.UUID(request_id)


if __name__ == "__main__":
    pytest.main([__file__])