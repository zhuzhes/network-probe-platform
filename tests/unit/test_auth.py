"""认证功能单元测试"""

import pytest
from datetime import datetime, timedelta
from unittest.mock import Mock, patch
from jose import jwt

from shared.security.auth import (
    get_password_hash,
    verify_password,
    create_access_token,
    verify_token,
    authenticate_user,
    authenticate_api_key,
    TokenData
)
from shared.models.user import User, UserRole, UserStatus
from tests.test_config import test_app_config as app_config


class TestPasswordHashing:
    """密码哈希测试"""
    
    def test_password_hashing(self):
        """测试密码哈希和验证"""
        password = "TestPassword123"
        hashed = get_password_hash(password)
        
        assert hashed != password
        assert verify_password(password, hashed) is True
        assert verify_password("wrongpassword", hashed) is False


class TestJWTToken:
    """JWT令牌测试"""
    
    def test_create_access_token(self):
        """测试创建访问令牌"""
        data = {"sub": "testuser"}
        token = create_access_token(data)
        
        assert token is not None
        assert isinstance(token, str)
        
        # 验证令牌内容
        token_data = verify_token(token)
        assert token_data is not None
        assert token_data.username == "testuser"
    
    def test_create_access_token_with_expiry(self):
        """测试创建带过期时间的访问令牌"""
        data = {"sub": "testuser"}
        expires_delta = timedelta(minutes=15)
        token = create_access_token(data, expires_delta)
        
        # 验证令牌内容
        token_data = verify_token(token)
        assert token_data is not None
        assert token_data.username == "testuser"
    
    def test_verify_token_valid(self):
        """测试验证有效令牌"""
        data = {"sub": "testuser"}
        token = create_access_token(data)
        
        token_data = verify_token(token)
        
        assert token_data is not None
        assert token_data.username == "testuser"
    
    def test_verify_token_invalid(self):
        """测试验证无效令牌"""
        invalid_token = "invalid.token.here"
        
        token_data = verify_token(invalid_token)
        
        assert token_data is None
    
    def test_verify_token_expired(self):
        """测试验证过期令牌"""
        data = {"sub": "testuser"}
        # 创建已过期的令牌
        expires_delta = timedelta(seconds=-1)
        token = create_access_token(data, expires_delta)
        
        token_data = verify_token(token)
        
        assert token_data is None


class TestUserAuthentication:
    """用户认证测试"""
    
    def test_authenticate_user_success(self):
        """测试成功认证用户"""
        # 创建模拟用户
        user = User(
            username="testuser",
            email="test@example.com",
            role=UserRole.ENTERPRISE,
            status=UserStatus.ACTIVE
        )
        user.set_password("TestPassword123")
        
        # 创建模拟数据库会话
        mock_db = Mock()
        mock_db.query.return_value.filter.return_value.first.return_value = user
        
        result = authenticate_user(mock_db, "testuser", "TestPassword123")
        
        assert result == user
        mock_db.query.assert_called_once_with(User)
    
    def test_authenticate_user_not_found(self):
        """测试用户不存在"""
        mock_db = Mock()
        mock_db.query.return_value.filter.return_value.first.return_value = None
        
        result = authenticate_user(mock_db, "nonexistent", "password")
        
        assert result is None
    
    def test_authenticate_user_wrong_password(self):
        """测试密码错误"""
        user = User(
            username="testuser",
            email="test@example.com",
            role=UserRole.ENTERPRISE,
            status=UserStatus.ACTIVE
        )
        user.set_password("TestPassword123")
        
        mock_db = Mock()
        mock_db.query.return_value.filter.return_value.first.return_value = user
        
        result = authenticate_user(mock_db, "testuser", "wrongpassword")
        
        assert result is None
    
    def test_authenticate_api_key_success(self):
        """测试API密钥认证成功"""
        user = User(
            username="testuser",
            email="test@example.com",
            role=UserRole.ENTERPRISE,
            status=UserStatus.ACTIVE
        )
        api_key = user.generate_api_key()
        
        mock_db = Mock()
        mock_db.query.return_value.filter.return_value.first.return_value = user
        
        result = authenticate_api_key(mock_db, api_key)
        
        assert result == user
    
    def test_authenticate_api_key_not_found(self):
        """测试API密钥不存在"""
        mock_db = Mock()
        mock_db.query.return_value.filter.return_value.first.return_value = None
        
        result = authenticate_api_key(mock_db, "npk_invalid_key")
        
        assert result is None
    
    def test_authenticate_api_key_inactive_user(self):
        """测试API密钥对应的用户不活跃"""
        user = User(
            username="testuser",
            email="test@example.com",
            role=UserRole.ENTERPRISE,
            status=UserStatus.INACTIVE
        )
        api_key = user.generate_api_key()
        
        mock_db = Mock()
        mock_db.query.return_value.filter.return_value.first.return_value = user
        
        result = authenticate_api_key(mock_db, api_key)
        
        assert result is None


class TestTokenData:
    """TokenData测试"""
    
    def test_token_data_creation(self):
        """测试TokenData创建"""
        token_data = TokenData(username="testuser")
        
        assert token_data.username == "testuser"
    
    def test_token_data_none_username(self):
        """测试TokenData无用户名"""
        token_data = TokenData()
        
        assert token_data.username is None