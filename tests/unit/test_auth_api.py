"""认证API端点测试"""

import pytest
import uuid
from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, patch
from fastapi.testclient import TestClient
from fastapi import status

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))

from shared.models.user import User, UserLogin, UserRole, UserStatus
from management_platform.api.main import create_app


@pytest.fixture
def client():
    """创建测试客户端"""
    app = create_app()
    return TestClient(app)


@pytest.fixture
def mock_user():
    """模拟用户对象"""
    user = MagicMock()
    user.id = uuid.uuid4()
    user.username = "testuser"
    user.email = "test@example.com"
    user.company_name = "Test Company"
    user.role = UserRole.ENTERPRISE
    user.credits = 100.0
    user.status = UserStatus.ACTIVE
    user.api_key_hash = None
    user.password_hash = "hashed_password"
    user.created_at = datetime.now()
    user.updated_at = datetime.now()
    user.last_login = None
    return user


class TestLogin:
    """登录测试"""
    
    @patch('management_platform.api.routes.auth.authenticate_user')
    @patch('management_platform.api.routes.auth.check_rate_limit')
    @patch('management_platform.api.routes.auth.record_auth_attempt')
    @patch('management_platform.api.routes.auth.SecurityLogger')
    def test_login_success(self, mock_logger, mock_record, mock_rate_limit, 
                          mock_auth, client, mock_user):
        """测试成功登录"""
        mock_rate_limit.return_value = None
        mock_auth.return_value = mock_user
        mock_record.return_value = None
        
        login_data = {
            "username": "testuser",
            "password": "password123"
        }
        
        response = client.post("/api/v1/auth/login", json=login_data)
        
        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert "access_token" in data
        assert "refresh_token" in data
        assert data["token_type"] == "bearer"
        assert "user" in data
        assert data["user"]["username"] == mock_user.username
    
    @patch('management_platform.api.routes.auth.authenticate_user')
    @patch('management_platform.api.routes.auth.check_rate_limit')
    @patch('management_platform.api.routes.auth.record_auth_attempt')
    @patch('management_platform.api.routes.auth.SecurityLogger')
    def test_login_invalid_credentials(self, mock_logger, mock_record, 
                                     mock_rate_limit, mock_auth, client):
        """测试无效凭据登录"""
        mock_rate_limit.return_value = None
        mock_auth.return_value = None  # 认证失败
        mock_record.return_value = None
        
        login_data = {
            "username": "testuser",
            "password": "wrongpassword"
        }
        
        response = client.post("/api/v1/auth/login", json=login_data)
        
        assert response.status_code == status.HTTP_401_UNAUTHORIZED
        assert "用户名或密码错误" in response.json()["detail"]
    
    @patch('management_platform.api.routes.auth.check_rate_limit')
    def test_login_rate_limited(self, mock_rate_limit, client):
        """测试登录速率限制"""
        from shared.security.auth import RateLimitExceeded
        mock_rate_limit.side_effect = RateLimitExceeded("Rate limit exceeded")
        
        login_data = {
            "username": "testuser",
            "password": "password123"
        }
        
        with pytest.raises(RateLimitExceeded):
            client.post("/api/v1/auth/login", json=login_data)
    
    def test_login_invalid_data(self, client):
        """测试无效登录数据"""
        invalid_data = {
            "username": "",  # 空用户名
            "password": ""   # 空密码
        }
        
        response = client.post("/api/v1/auth/login", json=invalid_data)
        
        assert response.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY


class TestRefreshToken:
    """刷新令牌测试"""
    
    @patch('management_platform.api.routes.auth.verify_refresh_token')
    @patch('management_platform.api.routes.auth.UserRepository')
    @patch('management_platform.api.routes.auth.SecurityLogger')
    def test_refresh_token_success(self, mock_logger, mock_repo_class, 
                                  mock_verify, client, mock_user):
        """测试成功刷新令牌"""
        # 模拟令牌数据
        token_data = MagicMock()
        token_data.username = mock_user.username
        token_data.user_id = str(mock_user.id)
        
        mock_verify.return_value = token_data
        
        mock_repo = AsyncMock()
        mock_repo_class.return_value = mock_repo
        mock_repo.get_by_id.return_value = mock_user
        
        refresh_data = {
            "refresh_token": "valid_refresh_token"
        }
        
        response = client.post("/api/v1/auth/refresh", json=refresh_data)
        
        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert "access_token" in data
        assert "refresh_token" in data
        assert data["token_type"] == "bearer"
        assert "user" in data
    
    @patch('management_platform.api.routes.auth.verify_refresh_token')
    def test_refresh_token_invalid(self, mock_verify, client):
        """测试无效刷新令牌"""
        mock_verify.return_value = None
        
        refresh_data = {
            "refresh_token": "invalid_refresh_token"
        }
        
        response = client.post("/api/v1/auth/refresh", json=refresh_data)
        
        assert response.status_code == status.HTTP_401_UNAUTHORIZED
        assert "无效的刷新令牌" in response.json()["detail"]
    
    @patch('management_platform.api.routes.auth.verify_refresh_token')
    @patch('management_platform.api.routes.auth.UserRepository')
    def test_refresh_token_user_not_found(self, mock_repo_class, mock_verify, client):
        """测试刷新令牌时用户不存在"""
        token_data = MagicMock()
        token_data.username = "nonexistent"
        token_data.user_id = str(uuid.uuid4())
        
        mock_verify.return_value = token_data
        
        mock_repo = AsyncMock()
        mock_repo_class.return_value = mock_repo
        mock_repo.get_by_id.return_value = None
        
        refresh_data = {
            "refresh_token": "valid_refresh_token"
        }
        
        response = client.post("/api/v1/auth/refresh", json=refresh_data)
        
        assert response.status_code == status.HTTP_401_UNAUTHORIZED
        assert "用户不存在或已被禁用" in response.json()["detail"]
    
    @patch('management_platform.api.routes.auth.verify_refresh_token')
    @patch('management_platform.api.routes.auth.UserRepository')
    def test_refresh_token_user_inactive(self, mock_repo_class, mock_verify, client, mock_user):
        """测试刷新令牌时用户已被禁用"""
        mock_user.status = UserStatus.INACTIVE
        
        token_data = MagicMock()
        token_data.username = mock_user.username
        token_data.user_id = str(mock_user.id)
        
        mock_verify.return_value = token_data
        
        mock_repo = AsyncMock()
        mock_repo_class.return_value = mock_repo
        mock_repo.get_by_id.return_value = mock_user
        
        refresh_data = {
            "refresh_token": "valid_refresh_token"
        }
        
        response = client.post("/api/v1/auth/refresh", json=refresh_data)
        
        assert response.status_code == status.HTTP_401_UNAUTHORIZED
        assert "用户不存在或已被禁用" in response.json()["detail"]


class TestLogout:
    """登出测试"""
    
    @patch('management_platform.api.routes.auth.get_current_user')
    @patch('management_platform.api.routes.auth.logout_user')
    @patch('management_platform.api.routes.auth.SecurityLogger')
    def test_logout_success(self, mock_logger, mock_logout, mock_auth, client, mock_user):
        """测试成功登出"""
        mock_auth.return_value = mock_user
        mock_logout.return_value = None
        
        headers = {"Authorization": "Bearer valid_token"}
        response = client.post("/api/v1/auth/logout", headers=headers)
        
        assert response.status_code == status.HTTP_200_OK
        assert "登出成功" in response.json()["message"]
    
    @patch('management_platform.api.routes.auth.get_current_user')
    @patch('management_platform.api.routes.auth.logout_user')
    def test_logout_without_token(self, mock_logout, mock_auth, client, mock_user):
        """测试无令牌登出"""
        mock_auth.return_value = mock_user
        mock_logout.return_value = None
        
        response = client.post("/api/v1/auth/logout")
        
        assert response.status_code == status.HTTP_200_OK
        assert "登出成功" in response.json()["message"]


class TestGetCurrentUser:
    """获取当前用户测试"""
    
    @patch('management_platform.api.routes.auth.get_current_user')
    def test_get_current_user_success(self, mock_auth, client, mock_user):
        """测试成功获取当前用户信息"""
        mock_auth.return_value = mock_user
        
        headers = {"Authorization": "Bearer valid_token"}
        response = client.get("/api/v1/auth/me", headers=headers)
        
        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert data["username"] == mock_user.username
        assert data["email"] == mock_user.email
        assert data["role"] == mock_user.role
        assert "password" not in data
    
    def test_get_current_user_unauthorized(self, client):
        """测试未授权获取当前用户信息"""
        response = client.get("/api/v1/auth/me")
        
        # 应该返回401或403，取决于中间件实现
        assert response.status_code in [status.HTTP_401_UNAUTHORIZED, status.HTTP_403_FORBIDDEN]


class TestSecurityFeatures:
    """安全功能测试"""
    
    @patch('management_platform.api.routes.auth.authenticate_user')
    @patch('management_platform.api.routes.auth.check_rate_limit')
    @patch('management_platform.api.routes.auth.record_auth_attempt')
    @patch('management_platform.api.routes.auth.SecurityLogger')
    def test_security_logging(self, mock_logger, mock_record, mock_rate_limit, 
                            mock_auth, client, mock_user):
        """测试安全日志记录"""
        mock_rate_limit.return_value = None
        mock_auth.return_value = mock_user
        
        login_data = {
            "username": "testuser",
            "password": "password123"
        }
        
        response = client.post("/api/v1/auth/login", json=login_data)
        
        assert response.status_code == status.HTTP_200_OK
        
        # 验证安全日志被调用
        mock_logger.log_login_attempt.assert_called()
        mock_record.assert_called()
    
    @patch('management_platform.api.routes.auth.authenticate_user')
    @patch('management_platform.api.routes.auth.check_rate_limit')
    @patch('management_platform.api.routes.auth.record_auth_attempt')
    @patch('management_platform.api.routes.auth.SecurityLogger')
    def test_failed_login_logging(self, mock_logger, mock_record, mock_rate_limit, 
                                mock_auth, client):
        """测试失败登录日志记录"""
        mock_rate_limit.return_value = None
        mock_auth.return_value = None  # 认证失败
        
        login_data = {
            "username": "testuser",
            "password": "wrongpassword"
        }
        
        response = client.post("/api/v1/auth/login", json=login_data)
        
        assert response.status_code == status.HTTP_401_UNAUTHORIZED
        
        # 验证失败登录被记录
        mock_record.assert_called_with("127.0.0.1", False)
        mock_logger.log_login_attempt.assert_called_with("testuser", False, "127.0.0.1")


class TestTokenValidation:
    """令牌验证测试"""
    
    def test_login_response_structure(self, client):
        """测试登录响应结构"""
        with patch('management_platform.api.routes.auth.authenticate_user') as mock_auth, \
             patch('management_platform.api.routes.auth.check_rate_limit'), \
             patch('management_platform.api.routes.auth.record_auth_attempt'), \
             patch('management_platform.api.routes.auth.SecurityLogger'):
            
            mock_user = MagicMock()
            mock_user.id = uuid.uuid4()
            mock_user.username = "testuser"
            mock_user.email = "test@example.com"
            mock_user.company_name = "Test Company"
            mock_user.role = UserRole.ENTERPRISE
            mock_user.credits = 100.0
            mock_user.status = UserStatus.ACTIVE
            mock_user.api_key_hash = None
            mock_user.created_at = datetime.now()
            mock_user.updated_at = datetime.now()
            mock_user.last_login = None
            
            mock_auth.return_value = mock_user
            
            login_data = {
                "username": "testuser",
                "password": "password123"
            }
            
            response = client.post("/api/v1/auth/login", json=login_data)
            
            assert response.status_code == status.HTTP_200_OK
            data = response.json()
            
            # 验证响应结构
            required_fields = ["access_token", "refresh_token", "token_type", "expires_in", "user"]
            for field in required_fields:
                assert field in data
            
            # 验证用户信息结构
            user_data = data["user"]
            user_fields = ["id", "username", "email", "role", "credits", "status"]
            for field in user_fields:
                assert field in user_data
            
            # 确保敏感信息不在响应中
            assert "password" not in user_data
            assert "password_hash" not in user_data
            assert "api_key_hash" not in user_data


if __name__ == "__main__":
    pytest.main([__file__, "-v"])