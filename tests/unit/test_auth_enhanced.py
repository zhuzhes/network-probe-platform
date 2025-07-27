"""增强认证系统测试"""

import pytest
from datetime import datetime, timedelta
from unittest.mock import Mock, patch
from fastapi import HTTPException
from sqlalchemy.orm import Session

from shared.security.auth import (
    APIKeyManager, TokenData, create_access_token, create_refresh_token,
    verify_token, verify_refresh_token, authenticate_user, authenticate_api_key,
    create_user_api_key, revoke_user_api_key, SecurityLogger, RateLimiter,
    TokenBlacklist, check_rate_limit, record_auth_attempt, logout_user,
    is_token_valid, get_password_hash, verify_password
)
from shared.models.user import User, UserRole, UserStatus


class TestAPIKeyManager:
    """API密钥管理器测试"""
    
    def test_generate_api_key(self):
        """测试生成API密钥"""
        api_key = APIKeyManager.generate_api_key()
        
        assert api_key.startswith("npk_")
        assert len(api_key) == 68  # npk_ + 64字符
        
        # 生成的密钥应该不同
        api_key2 = APIKeyManager.generate_api_key()
        assert api_key != api_key2
    
    def test_generate_api_key_custom_prefix(self):
        """测试生成自定义前缀的API密钥"""
        api_key = APIKeyManager.generate_api_key("test")
        
        assert api_key.startswith("test_")
        assert len(api_key) == 69  # test_ + 64字符
    
    def test_hash_api_key(self):
        """测试API密钥哈希"""
        api_key = "npk_test123"
        hashed = APIKeyManager.hash_api_key(api_key)
        
        assert isinstance(hashed, str)
        assert len(hashed) == 64  # SHA256哈希长度
        
        # 相同密钥应该产生相同哈希
        hashed2 = APIKeyManager.hash_api_key(api_key)
        assert hashed == hashed2
    
    def test_verify_api_key(self):
        """测试API密钥验证"""
        api_key = "npk_test123"
        hashed = APIKeyManager.hash_api_key(api_key)
        
        # 正确的密钥应该验证成功
        assert APIKeyManager.verify_api_key(api_key, hashed) is True
        
        # 错误的密钥应该验证失败
        assert APIKeyManager.verify_api_key("npk_wrong", hashed) is False
    
    def test_is_api_key_format(self):
        """测试API密钥格式检查"""
        # 正确格式
        valid_key = APIKeyManager.generate_api_key()
        assert APIKeyManager.is_api_key_format(valid_key) is True
        
        # 错误格式
        assert APIKeyManager.is_api_key_format("invalid") is False
        assert APIKeyManager.is_api_key_format("npk_short") is False
        assert APIKeyManager.is_api_key_format("wrong_" + "a" * 64) is False


class TestTokenData:
    """Token数据测试"""
    
    def test_token_data_creation(self):
        """测试Token数据创建"""
        token_data = TokenData(username="test_user", user_id="123")
        
        assert token_data.username == "test_user"
        assert token_data.user_id == "123"
    
    def test_token_data_optional_fields(self):
        """测试Token数据可选字段"""
        token_data = TokenData(username="test_user")
        
        assert token_data.username == "test_user"
        assert token_data.user_id is None


class TestJWTFunctions:
    """JWT功能测试"""
    
    def test_create_access_token(self):
        """测试创建访问令牌"""
        data = {"sub": "test_user", "user_id": "123"}
        token = create_access_token(data)
        
        assert isinstance(token, str)
        assert len(token) > 0
    
    def test_create_access_token_with_expiry(self):
        """测试创建带过期时间的访问令牌"""
        data = {"sub": "test_user", "user_id": "123"}
        expires_delta = timedelta(minutes=15)
        token = create_access_token(data, expires_delta)
        
        assert isinstance(token, str)
        assert len(token) > 0
    
    def test_create_refresh_token(self):
        """测试创建刷新令牌"""
        data = {"sub": "test_user", "user_id": "123"}
        token = create_refresh_token(data)
        
        assert isinstance(token, str)
        assert len(token) > 0
    
    def test_verify_token_valid(self):
        """测试验证有效令牌"""
        data = {"sub": "test_user", "user_id": "123"}
        token = create_access_token(data)
        
        token_data = verify_token(token)
        
        assert token_data is not None
        assert token_data.username == "test_user"
        assert token_data.user_id == "123"
    
    def test_verify_token_invalid(self):
        """测试验证无效令牌"""
        invalid_token = "invalid.token.here"
        
        token_data = verify_token(invalid_token)
        
        assert token_data is None
    
    def test_verify_refresh_token_valid(self):
        """测试验证有效刷新令牌"""
        data = {"sub": "test_user", "user_id": "123"}
        token = create_refresh_token(data)
        
        token_data = verify_refresh_token(token)
        
        assert token_data is not None
        assert token_data.username == "test_user"
        assert token_data.user_id == "123"
    
    def test_verify_refresh_token_with_access_token(self):
        """测试用访问令牌验证刷新令牌应该失败"""
        data = {"sub": "test_user", "user_id": "123"}
        access_token = create_access_token(data)
        
        token_data = verify_refresh_token(access_token)
        
        assert token_data is None


class TestPasswordFunctions:
    """密码功能测试"""
    
    def test_get_password_hash(self):
        """测试获取密码哈希"""
        password = "test_password"
        hashed = get_password_hash(password)
        
        assert isinstance(hashed, str)
        assert len(hashed) > 0
        assert hashed != password
    
    def test_verify_password_correct(self):
        """测试验证正确密码"""
        password = "test_password"
        hashed = get_password_hash(password)
        
        assert verify_password(password, hashed) is True
    
    def test_verify_password_incorrect(self):
        """测试验证错误密码"""
        password = "test_password"
        wrong_password = "wrong_password"
        hashed = get_password_hash(password)
        
        assert verify_password(wrong_password, hashed) is False


class TestUserAuthentication:
    """用户认证测试"""
    
    @pytest.fixture
    def mock_db(self):
        """模拟数据库会话"""
        return Mock(spec=Session)
    
    @pytest.fixture
    def mock_user(self):
        """模拟用户"""
        user = Mock(spec=User)
        user.id = "123"
        user.username = "test_user"
        user.password_hash = get_password_hash("test_password")
        user.status = UserStatus.ACTIVE
        user.api_key_hash = None
        user.last_login = None
        return user
    
    def test_authenticate_user_success(self, mock_db, mock_user):
        """测试用户认证成功"""
        mock_db.query.return_value.filter.return_value.first.return_value = mock_user
        
        result = authenticate_user(mock_db, "test_user", "test_password")
        
        assert result == mock_user
        assert mock_user.last_login is not None
        mock_db.commit.assert_called_once()
    
    def test_authenticate_user_not_found(self, mock_db):
        """测试用户不存在"""
        mock_db.query.return_value.filter.return_value.first.return_value = None
        
        result = authenticate_user(mock_db, "nonexistent", "password")
        
        assert result is None
    
    def test_authenticate_user_wrong_password(self, mock_db, mock_user):
        """测试密码错误"""
        mock_db.query.return_value.filter.return_value.first.return_value = mock_user
        
        result = authenticate_user(mock_db, "test_user", "wrong_password")
        
        assert result is None
    
    def test_authenticate_user_inactive(self, mock_db, mock_user):
        """测试用户未激活"""
        mock_user.status = UserStatus.INACTIVE
        mock_db.query.return_value.filter.return_value.first.return_value = mock_user
        
        result = authenticate_user(mock_db, "test_user", "test_password")
        
        assert result is None
    
    def test_authenticate_api_key_success(self, mock_db, mock_user):
        """测试API密钥认证成功"""
        api_key = APIKeyManager.generate_api_key()
        mock_user.api_key_hash = APIKeyManager.hash_api_key(api_key)
        mock_db.query.return_value.filter.return_value.first.return_value = mock_user
        
        result = authenticate_api_key(mock_db, api_key)
        
        assert result == mock_user
        assert mock_user.last_login is not None
        mock_db.commit.assert_called_once()
    
    def test_authenticate_api_key_invalid_format(self, mock_db):
        """测试API密钥格式无效"""
        result = authenticate_api_key(mock_db, "invalid_key")
        
        assert result is None
    
    def test_authenticate_api_key_not_found(self, mock_db):
        """测试API密钥不存在"""
        api_key = APIKeyManager.generate_api_key()
        mock_db.query.return_value.filter.return_value.first.return_value = None
        
        result = authenticate_api_key(mock_db, api_key)
        
        assert result is None
    
    def test_create_user_api_key(self, mock_db, mock_user):
        """测试创建用户API密钥"""
        api_key = create_user_api_key(mock_db, mock_user)
        
        assert APIKeyManager.is_api_key_format(api_key)
        assert mock_user.api_key_hash is not None
        assert mock_user.api_key_created_at is not None
        mock_db.commit.assert_called_once()
    
    def test_revoke_user_api_key(self, mock_db, mock_user):
        """测试撤销用户API密钥"""
        mock_user.api_key_hash = "some_hash"
        mock_user.api_key_created_at = datetime.utcnow()
        
        revoke_user_api_key(mock_db, mock_user)
        
        assert mock_user.api_key_hash is None
        assert mock_user.api_key_created_at is None
        mock_db.commit.assert_called_once()


class TestSecurityLogger:
    """安全日志测试"""
    
    @patch('shared.security.auth.logger')
    def test_log_login_attempt_success(self, mock_logger):
        """测试记录成功登录"""
        SecurityLogger.log_login_attempt("test_user", True, "127.0.0.1")
        
        mock_logger.info.assert_called_once()
        args = mock_logger.info.call_args[0][0]
        assert "Successful login" in args
        assert "test_user" in args
        assert "127.0.0.1" in args
    
    @patch('shared.security.auth.logger')
    def test_log_login_attempt_failure(self, mock_logger):
        """测试记录失败登录"""
        SecurityLogger.log_login_attempt("test_user", False, "127.0.0.1")
        
        mock_logger.warning.assert_called_once()
        args = mock_logger.warning.call_args[0][0]
        assert "Failed login attempt" in args
        assert "test_user" in args
        assert "127.0.0.1" in args
    
    @patch('shared.security.auth.logger')
    def test_log_api_key_usage(self, mock_logger):
        """测试记录API密钥使用"""
        SecurityLogger.log_api_key_usage("test_user", "/api/test", "127.0.0.1")
        
        mock_logger.info.assert_called_once()
        args = mock_logger.info.call_args[0][0]
        assert "API key used" in args
        assert "test_user" in args
        assert "/api/test" in args
        assert "127.0.0.1" in args


class TestRateLimiter:
    """速率限制器测试"""
    
    def test_rate_limiter_initial_state(self):
        """测试速率限制器初始状态"""
        limiter = RateLimiter()
        
        assert limiter.is_rate_limited("test_key") is False
    
    def test_rate_limiter_under_limit(self):
        """测试未超过限制"""
        limiter = RateLimiter()
        
        # 记录4次尝试（低于5次限制）
        for _ in range(4):
            limiter.record_attempt("test_key")
        
        assert limiter.is_rate_limited("test_key") is False
    
    def test_rate_limiter_over_limit(self):
        """测试超过限制"""
        limiter = RateLimiter()
        
        # 记录5次尝试（达到限制）
        for _ in range(5):
            limiter.record_attempt("test_key")
        
        assert limiter.is_rate_limited("test_key") is True
    
    def test_rate_limiter_reset(self):
        """测试重置尝试计数"""
        limiter = RateLimiter()
        
        # 记录5次尝试
        for _ in range(5):
            limiter.record_attempt("test_key")
        
        assert limiter.is_rate_limited("test_key") is True
        
        # 重置
        limiter.reset_attempts("test_key")
        
        assert limiter.is_rate_limited("test_key") is False
    
    def test_check_rate_limit_success(self):
        """测试速率限制检查成功"""
        # 应该不抛出异常
        check_rate_limit("new_key")
    
    def test_check_rate_limit_failure(self):
        """测试速率限制检查失败"""
        # 先触发限制
        for _ in range(5):
            record_auth_attempt("test_key", False)
        
        # 应该抛出异常
        with pytest.raises(HTTPException) as exc_info:
            check_rate_limit("test_key")
        
        assert exc_info.value.status_code == 429


class TestTokenBlacklist:
    """令牌黑名单测试"""
    
    def test_token_blacklist_initial_state(self):
        """测试令牌黑名单初始状态"""
        blacklist = TokenBlacklist()
        
        assert blacklist.is_blacklisted("test_token") is False
    
    def test_add_token_to_blacklist(self):
        """测试添加令牌到黑名单"""
        blacklist = TokenBlacklist()
        
        blacklist.add_token("test_token")
        
        assert blacklist.is_blacklisted("test_token") is True
    
    def test_remove_token_from_blacklist(self):
        """测试从黑名单移除令牌"""
        blacklist = TokenBlacklist()
        
        blacklist.add_token("test_token")
        assert blacklist.is_blacklisted("test_token") is True
        
        blacklist.remove_token("test_token")
        assert blacklist.is_blacklisted("test_token") is False
    
    def test_logout_user(self):
        """测试用户登出"""
        token = "test_token"
        
        assert is_token_valid(token) is True
        
        logout_user(token)
        
        assert is_token_valid(token) is False