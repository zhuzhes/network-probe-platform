"""API中间件"""

import time
import uuid
import json
from typing import Callable
from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import JSONResponse
import structlog

# 配置结构化日志
logger = structlog.get_logger()


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    """安全头中间件"""
    
    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        response = await call_next(request)
        
        # 添加安全头
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["X-XSS-Protection"] = "1; mode=block"
        response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
        response.headers["Content-Security-Policy"] = (
            "default-src 'self'; "
            "script-src 'self' 'unsafe-inline'; "
            "style-src 'self' 'unsafe-inline'; "
            "img-src 'self' data: https:; "
            "font-src 'self'; "
            "connect-src 'self'; "
            "frame-ancestors 'none';"
        )
        
        return response


class RequestLoggingMiddleware(BaseHTTPMiddleware):
    """请求日志中间件"""
    
    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        # 生成请求ID
        request_id = str(uuid.uuid4())
        request.state.request_id = request_id
        
        # 记录请求开始时间
        start_time = time.time()
        
        # 获取客户端IP
        client_ip = self._get_client_ip(request)
        
        # 记录请求信息
        logger.info(
            "request_started",
            request_id=request_id,
            method=request.method,
            url=str(request.url),
            client_ip=client_ip,
            user_agent=request.headers.get("user-agent", ""),
        )
        
        # 处理请求
        try:
            response = await call_next(request)
            
            # 计算处理时间
            process_time = time.time() - start_time
            
            # 记录响应信息
            logger.info(
                "request_completed",
                request_id=request_id,
                status_code=response.status_code,
                process_time=process_time,
            )
            
            # 添加请求ID到响应头
            response.headers["X-Request-ID"] = request_id
            response.headers["X-Process-Time"] = str(process_time)
            
            return response
            
        except Exception as e:
            # 记录错误
            process_time = time.time() - start_time
            logger.error(
                "request_failed",
                request_id=request_id,
                error=str(e),
                process_time=process_time,
            )
            raise
    
    def _get_client_ip(self, request: Request) -> str:
        """获取客户端IP地址"""
        # 检查代理头
        forwarded_for = request.headers.get("X-Forwarded-For")
        if forwarded_for:
            return forwarded_for.split(",")[0].strip()
        
        real_ip = request.headers.get("X-Real-IP")
        if real_ip:
            return real_ip
        
        # 返回直接连接的IP
        return request.client.host if request.client else "unknown"


class RateLimitMiddleware(BaseHTTPMiddleware):
    """限流中间件"""
    
    def __init__(self, app, calls: int = 100, period: int = 60):
        super().__init__(app)
        self.calls = calls  # 允许的调用次数
        self.period = period  # 时间窗口（秒）
        self.clients = {}  # 客户端请求记录
    
    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        # 获取客户端标识
        client_id = self._get_client_id(request)
        
        # 检查限流
        if self._is_rate_limited(client_id):
            return JSONResponse(
                status_code=429,
                content={
                    "error": "Rate limit exceeded",
                    "message": f"Too many requests. Limit: {self.calls} per {self.period} seconds",
                    "retry_after": self.period
                },
                headers={"Retry-After": str(self.period)}
            )
        
        # 记录请求
        self._record_request(client_id)
        
        return await call_next(request)
    
    def _get_client_id(self, request: Request) -> str:
        """获取客户端标识"""
        # 优先使用认证用户ID
        if hasattr(request.state, "user_id"):
            return f"user:{request.state.user_id}"
        
        # 使用IP地址
        forwarded_for = request.headers.get("X-Forwarded-For")
        if forwarded_for:
            ip = forwarded_for.split(",")[0].strip()
        else:
            ip = request.client.host if request.client else "unknown"
        
        return f"ip:{ip}"
    
    def _is_rate_limited(self, client_id: str) -> bool:
        """检查是否超出限流"""
        now = time.time()
        
        if client_id not in self.clients:
            return False
        
        # 清理过期记录
        self.clients[client_id] = [
            timestamp for timestamp in self.clients[client_id]
            if now - timestamp < self.period
        ]
        
        # 检查是否超出限制
        return len(self.clients[client_id]) >= self.calls
    
    def _record_request(self, client_id: str):
        """记录请求"""
        now = time.time()
        
        if client_id not in self.clients:
            self.clients[client_id] = []
        
        self.clients[client_id].append(now)


class DatabaseMiddleware(BaseHTTPMiddleware):
    """数据库中间件"""
    
    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        # 为请求添加数据库会话
        from management_platform.database.connection import db_manager
        
        with db_manager.get_session() as db:
            request.state.db = db
            response = await call_next(request)
            return response


class AuthenticationMiddleware(BaseHTTPMiddleware):
    """认证中间件"""
    
    # 不需要认证的路径
    EXEMPT_PATHS = {
        "/",
        "/health",
        "/docs",
        "/redoc",
        "/openapi.json",
        "/docs/oauth2-redirect",
        "/api/v1/auth/login",
        "/api/v1/auth/register",
    }
    
    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        # 检查是否需要认证
        if request.url.path in self.EXEMPT_PATHS or request.url.path.startswith("/docs"):
            return await call_next(request)
        
        # 检查认证头
        authorization = request.headers.get("Authorization")
        if not authorization:
            return JSONResponse(
                status_code=401,
                content={
                    "error": "Authentication required",
                    "message": "Missing Authorization header"
                }
            )
        
        # 验证token格式
        try:
            scheme, token = authorization.split(" ", 1)
            if scheme.lower() != "bearer":
                raise ValueError("Invalid scheme")
        except ValueError:
            return JSONResponse(
                status_code=401,
                content={
                    "error": "Invalid authentication",
                    "message": "Invalid Authorization header format"
                }
            )
        
        # 验证token
        import sys
        import os
        sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))
        from shared.security.auth import verify_token, authenticate_api_key
        
        try:
            # 检查是否是API密钥
            if token.startswith("npk_"):
                user = authenticate_api_key(request.state.db, token)
                if not user:
                    raise ValueError("Invalid API key")
            else:
                # JWT token验证
                token_data = verify_token(token)
                if not token_data:
                    raise ValueError("Invalid token")
                
                # 获取用户
                from shared.models.user import User
                user = request.state.db.query(User).filter(
                    User.username == token_data.username
                ).first()
                
                if not user:
                    raise ValueError("User not found")
            
            # 将用户信息添加到请求状态
            request.state.current_user = user
            request.state.user_id = str(user.id)
            
        except Exception as e:
            logger.warning(
                "authentication_failed",
                error=str(e),
                path=request.url.path,
                client_ip=request.client.host if request.client else "unknown"
            )
            
            return JSONResponse(
                status_code=401,
                content={
                    "error": "Authentication failed",
                    "message": "Invalid or expired token"
                }
            )
        
        return await call_next(request)