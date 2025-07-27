"""认证相关功能"""

import secrets
import hashlib
from datetime import datetime, timedelta
from typing import Optional, Union, Dict, Any
from jose import JWTError, jwt
from passlib.context import CryptContext
from fastapi import Depends, HTTPException, status, Request
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from sqlalchemy.orm import Session
import logging

import os

# 根据环境选择配置
if os.getenv('TESTING'):
    from tests.test_config import test_app_config as app_config
else:
    try:
        from shared.config import app_config
    except Exception:
        # 测试环境下使用测试配置
        from tests.test_config import test_app_config as app_config
from shared.models.user import User, UserRole, UserStatus

# 导入数据库会话
try:
    from management_platform.database.connection import get_db_session
except ImportError:
    # 如果无法导入，创建一个占位符函数
    def get_db_session():
        raise NotImplementedError("Database session not available")

logger = logging.getLogger(__name__)

# 密码加密上下文
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

# HTTP Bearer认证
security = HTTPBearer()


class TokenData:
    """Token数据"""
    def __init__(self, username: Optional[str] = None, user_id: Optional[str] = None):
        self.username = username
        self.user_id = user_id


class APIKeyManager:
    """API密钥管理器"""
    
    @staticmethod
    def generate_api_key(prefix: str = "npk") -> str:
        """生成API密钥"""
        # 生成32字节的随机数据
        random_bytes = secrets.token_bytes(32)
        # 转换为十六进制字符串
        key_suffix = random_bytes.hex()
        return f"{prefix}_{key_suffix}"
    
    @staticmethod
    def hash_api_key(api_key: str) -> str:
        """对API密钥进行哈希"""
        return hashlib.sha256(api_key.encode()).hexdigest()
    
    @staticmethod
    def verify_api_key(api_key: str, hashed_key: str) -> bool:
        """验证API密钥"""
        return APIKeyManager.hash_api_key(api_key) == hashed_key
    
    @staticmethod
    def is_api_key_format(key: str) -> bool:
        """检查是否为API密钥格式"""
        return key.startswith("npk_") and len(key) == 68  # npk_ + 64字符十六进制


def get_password_hash(password: str) -> str:
    """获取密码哈希"""
    return pwd_context.hash(password)


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """验证密码"""
    return pwd_context.verify(plain_password, hashed_password)


def create_access_token(data: dict, expires_delta: Optional[timedelta] = None) -> str:
    """创建访问令牌"""
    to_encode = data.copy()
    
    if expires_delta:
        expire = datetime.utcnow() + expires_delta
    else:
        expire = datetime.utcnow() + timedelta(
            minutes=app_config.security.jwt_expire_minutes
        )
    
    # 添加标准JWT声明
    to_encode.update({
        "exp": expire,
        "iat": datetime.utcnow(),
        "iss": "network-probe-platform",
        "aud": "network-probe-platform-users"
    })
    
    encoded_jwt = jwt.encode(
        to_encode,
        app_config.security.secret_key,
        algorithm=app_config.security.jwt_algorithm
    )
    
    return encoded_jwt


def create_refresh_token(data: dict) -> str:
    """创建刷新令牌"""
    to_encode = data.copy()
    expire = datetime.utcnow() + timedelta(days=7)  # 刷新令牌7天有效期
    
    to_encode.update({
        "exp": expire,
        "iat": datetime.utcnow(),
        "iss": "network-probe-platform",
        "aud": "network-probe-platform-users",
        "type": "refresh"
    })
    
    encoded_jwt = jwt.encode(
        to_encode,
        app_config.security.secret_key,
        algorithm=app_config.security.jwt_algorithm
    )
    
    return encoded_jwt


def verify_token(token: str) -> Optional[TokenData]:
    """验证令牌"""
    try:
        payload = jwt.decode(
            token,
            app_config.security.secret_key,
            algorithms=[app_config.security.jwt_algorithm],
            audience="network-probe-platform-users",
            issuer="network-probe-platform"
        )
        
        username: str = payload.get("sub")
        user_id: str = payload.get("user_id")
        token_type: str = payload.get("type", "access")
        
        if username is None or token_type != "access":
            return None
            
        return TokenData(username=username, user_id=user_id)
    except JWTError as e:
        logger.warning(f"JWT verification failed: {e}")
        return None


def verify_refresh_token(token: str) -> Optional[TokenData]:
    """验证刷新令牌"""
    try:
        payload = jwt.decode(
            token,
            app_config.security.secret_key,
            algorithms=[app_config.security.jwt_algorithm],
            audience="network-probe-platform-users",
            issuer="network-probe-platform"
        )
        
        username: str = payload.get("sub")
        user_id: str = payload.get("user_id")
        token_type: str = payload.get("type")
        
        if username is None or token_type != "refresh":
            return None
            
        return TokenData(username=username, user_id=user_id)
    except JWTError as e:
        logger.warning(f"Refresh token verification failed: {e}")
        return None


def authenticate_user(db: Session, username: str, password: str) -> Optional[User]:
    """认证用户"""
    try:
        user = db.query(User).filter(User.username == username).first()
        if not user:
            logger.warning(f"User not found: {username}")
            return None
            
        if user.status != UserStatus.ACTIVE:
            logger.warning(f"User not active: {username}")
            return None
            
        if not verify_password(password, user.password_hash):
            logger.warning(f"Invalid password for user: {username}")
            return None
            
        # 更新最后登录时间
        user.last_login = datetime.utcnow()
        db.commit()
        
        logger.info(f"User authenticated successfully: {username}")
        return user
        
    except Exception as e:
        logger.error(f"Authentication error for user {username}: {e}")
        return None


def authenticate_api_key(db: Session, api_key: str) -> Optional[User]:
    """通过API密钥认证用户"""
    try:
        if not APIKeyManager.is_api_key_format(api_key):
            logger.warning("Invalid API key format")
            return None
            
        # 对API密钥进行哈希以查找用户
        hashed_key = APIKeyManager.hash_api_key(api_key)
        user = db.query(User).filter(User.api_key_hash == hashed_key).first()
        
        if not user:
            logger.warning("API key not found")
            return None
            
        if user.status != UserStatus.ACTIVE:
            logger.warning(f"User not active for API key: {user.username}")
            return None
            
        # 更新最后登录时间
        user.last_login = datetime.utcnow()
        db.commit()
        
        logger.info(f"User authenticated via API key: {user.username}")
        return user
        
    except Exception as e:
        logger.error(f"API key authentication error: {e}")
        return None


def create_user_api_key(db: Session, user: User) -> str:
    """为用户创建API密钥"""
    try:
        # 生成新的API密钥
        api_key = APIKeyManager.generate_api_key()
        
        # 存储哈希后的密钥
        user.api_key_hash = APIKeyManager.hash_api_key(api_key)
        user.api_key_created_at = datetime.utcnow()
        
        db.commit()
        
        logger.info(f"API key created for user: {user.username}")
        return api_key
        
    except Exception as e:
        logger.error(f"Error creating API key for user {user.username}: {e}")
        db.rollback()
        raise


def revoke_user_api_key(db: Session, user: User) -> None:
    """撤销用户的API密钥"""
    try:
        user.api_key_hash = None
        user.api_key_created_at = None
        
        db.commit()
        
        logger.info(f"API key revoked for user: {user.username}")
        
    except Exception as e:
        logger.error(f"Error revoking API key for user {user.username}: {e}")
        db.rollback()
        raise


async def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(security),
    db: Session = Depends(lambda: next(get_db_session()))  # 这里需要依赖注入数据库会话
) -> User:
    """获取当前用户"""
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    
    try:
        token = credentials.credentials
        
        # 检查是否是API密钥
        if APIKeyManager.is_api_key_format(token):
            user = authenticate_api_key(db, token)
            if user is None:
                raise credentials_exception
            return user
        
        # JWT令牌验证
        token_data = verify_token(token)
        if token_data is None:
            raise credentials_exception
        
        # 优先使用user_id查找用户
        if token_data.user_id:
            user = db.query(User).filter(User.id == token_data.user_id).first()
        else:
            user = db.query(User).filter(User.username == token_data.username).first()
            
        if user is None:
            raise credentials_exception
        
        if user.status != UserStatus.ACTIVE:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="User account is not active"
            )
        
        return user
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting current user: {e}")
        raise credentials_exception


async def get_current_user_optional(
    request: Request,
    db: Session = Depends()
) -> Optional[User]:
    """获取当前用户（可选）"""
    try:
        auth_header = request.headers.get("Authorization")
        if not auth_header or not auth_header.startswith("Bearer "):
            return None
            
        token = auth_header.split(" ")[1]
        
        # 检查是否是API密钥
        if APIKeyManager.is_api_key_format(token):
            return authenticate_api_key(db, token)
        
        # JWT令牌验证
        token_data = verify_token(token)
        if token_data is None:
            return None
        
        # 优先使用user_id查找用户
        if token_data.user_id:
            user = db.query(User).filter(User.id == token_data.user_id).first()
        else:
            user = db.query(User).filter(User.username == token_data.username).first()
            
        if user and user.status == UserStatus.ACTIVE:
            return user
            
        return None
        
    except Exception as e:
        logger.error(f"Error getting optional current user: {e}")
        return None


async def get_current_active_user(
    current_user: User = Depends(get_current_user)
) -> User:
    """获取当前活跃用户"""
    if current_user.status != UserStatus.ACTIVE:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Inactive user"
        )
    return current_user


def require_role(required_role: UserRole):
    """要求特定角色的装饰器"""
    def role_checker(current_user: User = Depends(get_current_active_user)) -> User:
        if current_user.role != required_role and current_user.role != UserRole.ADMIN:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Not enough permissions"
            )
        return current_user
    return role_checker


def require_admin(current_user: User = Depends(get_current_active_user)) -> User:
    """要求管理员权限"""
    if current_user.role != UserRole.ADMIN:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admin access required"
        )
    return current_user


class SecurityLogger:
    """安全日志记录器"""
    
    @staticmethod
    def log_login_attempt(username: str, success: bool, ip_address: str = None):
        """记录登录尝试"""
        if success:
            logger.info(f"Successful login: {username} from {ip_address}")
        else:
            logger.warning(f"Failed login attempt: {username} from {ip_address}")
    
    @staticmethod
    def log_api_key_usage(username: str, endpoint: str, ip_address: str = None):
        """记录API密钥使用"""
        logger.info(f"API key used: {username} accessed {endpoint} from {ip_address}")
    
    @staticmethod
    def log_permission_denied(username: str, resource: str, ip_address: str = None):
        """记录权限拒绝"""
        logger.warning(f"Permission denied: {username} tried to access {resource} from {ip_address}")
    
    @staticmethod
    def log_token_refresh(username: str, ip_address: str = None):
        """记录令牌刷新"""
        logger.info(f"Token refreshed: {username} from {ip_address}")


class RateLimiter:
    """简单的内存速率限制器"""
    
    def __init__(self):
        self.attempts = {}  # {key: [(timestamp, count), ...]}
        self.max_attempts = 5
        self.window_minutes = 15
    
    def is_rate_limited(self, key: str) -> bool:
        """检查是否被速率限制"""
        now = datetime.utcnow()
        window_start = now - timedelta(minutes=self.window_minutes)
        
        # 清理过期记录
        if key in self.attempts:
            self.attempts[key] = [
                (timestamp, count) for timestamp, count in self.attempts[key]
                if timestamp > window_start
            ]
        
        # 计算当前窗口内的尝试次数
        current_attempts = sum(
            count for timestamp, count in self.attempts.get(key, [])
        )
        
        return current_attempts >= self.max_attempts
    
    def record_attempt(self, key: str, count: int = 1):
        """记录尝试"""
        now = datetime.utcnow()
        
        if key not in self.attempts:
            self.attempts[key] = []
        
        self.attempts[key].append((now, count))
    
    def reset_attempts(self, key: str):
        """重置尝试计数"""
        if key in self.attempts:
            del self.attempts[key]


# 全局速率限制器实例
rate_limiter = RateLimiter()


def check_rate_limit(identifier: str) -> None:
    """检查速率限制"""
    if rate_limiter.is_rate_limited(identifier):
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Too many authentication attempts. Please try again later."
        )


def record_auth_attempt(identifier: str, success: bool):
    """记录认证尝试"""
    if success:
        rate_limiter.reset_attempts(identifier)
    else:
        rate_limiter.record_attempt(identifier)


class TokenBlacklist:
    """令牌黑名单（简单内存实现）"""
    
    def __init__(self):
        self.blacklisted_tokens = set()
    
    def add_token(self, token: str):
        """添加令牌到黑名单"""
        self.blacklisted_tokens.add(token)
    
    def is_blacklisted(self, token: str) -> bool:
        """检查令牌是否在黑名单中"""
        return token in self.blacklisted_tokens
    
    def remove_token(self, token: str):
        """从黑名单中移除令牌"""
        self.blacklisted_tokens.discard(token)


# 全局令牌黑名单实例
token_blacklist = TokenBlacklist()


def logout_user(token: str):
    """用户登出，将令牌加入黑名单"""
    token_blacklist.add_token(token)
    logger.info("User logged out, token blacklisted")


def is_token_valid(token: str) -> bool:
    """检查令牌是否有效（未被拉黑）"""
    return not token_blacklist.is_blacklisted(token)


# 增强的认证依赖，包含速率限制和令牌黑名单检查
async def get_current_user_secure(
    request: Request,
    credentials: HTTPAuthorizationCredentials = Depends(security),
    db: Session = Depends()
) -> User:
    """获取当前用户（包含安全检查）"""
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    
    try:
        token = credentials.credentials
        client_ip = request.client.host if request.client else "unknown"
        
        # 检查令牌是否被拉黑
        if not is_token_valid(token):
            logger.warning(f"Blacklisted token used from {client_ip}")
            raise credentials_exception
        
        # 检查速率限制
        check_rate_limit(client_ip)
        
        # 检查是否是API密钥
        if APIKeyManager.is_api_key_format(token):
            user = authenticate_api_key(db, token)
            if user is None:
                record_auth_attempt(client_ip, False)
                SecurityLogger.log_login_attempt("unknown", False, client_ip)
                raise credentials_exception
            
            record_auth_attempt(client_ip, True)
            SecurityLogger.log_api_key_usage(user.username, request.url.path, client_ip)
            return user
        
        # JWT令牌验证
        token_data = verify_token(token)
        if token_data is None:
            record_auth_attempt(client_ip, False)
            SecurityLogger.log_login_attempt("unknown", False, client_ip)
            raise credentials_exception
        
        # 查找用户
        if token_data.user_id:
            user = db.query(User).filter(User.id == token_data.user_id).first()
        else:
            user = db.query(User).filter(User.username == token_data.username).first()
            
        if user is None or user.status != UserStatus.ACTIVE:
            record_auth_attempt(client_ip, False)
            SecurityLogger.log_login_attempt(token_data.username or "unknown", False, client_ip)
            raise credentials_exception
        
        record_auth_attempt(client_ip, True)
        return user
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error in secure authentication: {e}")
        raise credentials_exception