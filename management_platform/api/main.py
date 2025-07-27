"""FastAPI主应用程序"""

from fastapi import FastAPI, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.trustedhost import TrustedHostMiddleware
from fastapi.responses import JSONResponse
from fastapi.exceptions import RequestValidationError
from starlette.exceptions import HTTPException as StarletteHTTPException
import time
import uuid
from contextlib import asynccontextmanager

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))

from shared.config import app_config
from management_platform.database.connection import db_manager
from .middleware import (
    SecurityHeadersMiddleware,
    RequestLoggingMiddleware,
    RateLimitMiddleware,
    DatabaseMiddleware,
    AuthenticationMiddleware
)
from .exceptions import setup_exception_handlers
from .docs import setup_docs


@asynccontextmanager
async def lifespan(app: FastAPI):
    """应用生命周期管理"""
    # 启动时执行
    print(f"启动 {app_config.name} v{app_config.version}")
    
    # 初始化数据库
    try:
        db_manager.initialize(test_mode=True)  # 使用测试模式避免需要PostgreSQL
        if db_manager.sync_health_check():
            print("数据库连接成功")
        else:
            raise Exception("数据库健康检查失败")
    except Exception as e:
        print(f"数据库连接失败: {e}")
        raise
    
    yield
    
    # 关闭时执行
    print("应用关闭")


def create_app() -> FastAPI:
    """创建FastAPI应用"""
    
    app = FastAPI(
        title=app_config.name,
        version=app_config.version,
        description="网络拨测平台管理API",
        docs_url="/docs" if app_config.debug else None,
        redoc_url="/redoc" if app_config.debug else None,
        openapi_url="/openapi.json" if app_config.debug else None,
        lifespan=lifespan
    )
    
    # 设置中间件
    setup_middleware(app)
    
    # 设置异常处理器
    setup_exception_handlers(app)
    
    # 设置API文档
    setup_docs(app)
    
    # 注册路由
    register_routes(app)
    
    return app


def setup_middleware(app: FastAPI):
    """设置中间件"""
    
    # 数据库中间件（必须在认证中间件之前）
    app.add_middleware(DatabaseMiddleware)
    
    # 认证中间件
    app.add_middleware(AuthenticationMiddleware)
    
    # 安全头中间件
    app.add_middleware(SecurityHeadersMiddleware)
    
    # 请求日志中间件
    app.add_middleware(RequestLoggingMiddleware)
    
    # 限流中间件
    app.add_middleware(RateLimitMiddleware)
    
    # CORS中间件
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"] if app_config.debug else [
            "https://yourdomain.com",
            "https://www.yourdomain.com"
        ],
        allow_credentials=True,
        allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
        allow_headers=["*"],
        expose_headers=["X-Request-ID"]
    )
    
    # 受信任主机中间件
    if not app_config.debug:
        app.add_middleware(
            TrustedHostMiddleware,
            allowed_hosts=["yourdomain.com", "*.yourdomain.com"]
        )


def register_routes(app: FastAPI):
    """注册路由"""
    
    # 健康检查
    @app.get("/health", tags=["系统"])
    async def health_check():
        """健康检查端点"""
        return {
            "status": "healthy",
            "timestamp": time.time(),
            "version": app_config.version
        }
    
    # 根路径
    @app.get("/", tags=["系统"])
    async def root():
        """根路径"""
        return {
            "message": f"欢迎使用{app_config.name}",
            "version": app_config.version,
            "docs": "/docs" if app_config.debug else None
        }
    
    # WebSocket端点
    try:
        from .websocket import websocket_endpoint, get_advanced_connection_manager, get_message_dispatcher_instance
        
        @app.websocket("/ws/agent")
        async def websocket_agent_endpoint(websocket):
            """代理WebSocket连接端点"""
            await websocket_endpoint(websocket)
        
        @app.get("/api/v1/websocket/stats", tags=["WebSocket"])
        async def get_websocket_stats():
            """获取WebSocket连接统计信息"""
            manager = get_advanced_connection_manager()
            return manager.get_connection_stats()
        
        @app.get("/api/v1/websocket/agents", tags=["WebSocket"])
        async def get_connected_agents():
            """获取已连接的代理列表"""
            manager = get_advanced_connection_manager()
            return {
                "connected_agents": list(manager.get_connected_agents()),
                "available_agents": manager.get_available_agents(),
                "total_connections": len(manager.get_connected_agents())
            }
        
        @app.get("/api/v1/websocket/agents/{agent_id}", tags=["WebSocket"])
        async def get_agent_info(agent_id: str):
            """获取代理详细信息"""
            manager = get_advanced_connection_manager()
            agent_info = manager.get_agent_info(agent_id)
            if not agent_info:
                from fastapi import HTTPException
                raise HTTPException(status_code=404, detail="Agent not found")
            return agent_info
        
        @app.get("/api/v1/message-dispatcher/stats", tags=["消息分发"])
        async def get_message_dispatcher_stats():
            """获取消息分发系统统计信息"""
            dispatcher = get_message_dispatcher_instance()
            return dispatcher.get_stats()
        
        @app.post("/api/v1/message-dispatcher/broadcast", tags=["消息分发"])
        async def broadcast_system_message(message: str, level: str = "info"):
            """广播系统消息"""
            dispatcher = get_message_dispatcher_instance()
            count = await dispatcher.send_system_notification(message, level)
            return {"message": "Broadcast sent", "recipients": count}
        
        @app.post("/api/v1/message-dispatcher/agent/{agent_id}/command", tags=["消息分发"])
        async def send_agent_command(agent_id: str, command: str, parameters: dict = None):
            """发送代理命令"""
            dispatcher = get_message_dispatcher_instance()
            success = await dispatcher.send_agent_command(agent_id, command, parameters)
            if success:
                return {"message": "Command sent successfully"}
            else:
                from fastapi import HTTPException
                raise HTTPException(status_code=400, detail="Failed to send command")
        
        @app.get("/api/v1/message-dispatcher/distribution-strategy", tags=["消息分发"])
        async def get_distribution_strategy():
            """获取当前任务分发策略"""
            dispatcher = get_message_dispatcher_instance()
            stats = dispatcher.get_stats()
            return {
                "current_strategy": stats["task_distributor"]["current_strategy"],
                "available_strategies": stats["task_distributor"]["available_strategies"]
            }
        
        @app.post("/api/v1/message-dispatcher/distribution-strategy", tags=["消息分发"])
        async def set_distribution_strategy(strategy: str):
            """设置任务分发策略"""
            dispatcher = get_message_dispatcher_instance()
            dispatcher.set_distribution_strategy(strategy)
            return {"message": f"Distribution strategy set to {strategy}"}
        
    except ImportError as e:
        print(f"警告: 无法导入WebSocket模块: {e}")
    
    # 导入并注册API路由
    try:
        from .routes import auth, users, tasks, agents, analytics, health
        app.include_router(auth.router, prefix="/api/v1/auth", tags=["认证"])
        app.include_router(users.router, prefix="/api/v1/users", tags=["用户"])
        app.include_router(tasks.router, prefix="/api/v1/tasks", tags=["任务"])
        app.include_router(agents.router, prefix="/api/v1/agents", tags=["代理"])
        app.include_router(analytics.router, prefix="/api/v1/analytics", tags=["数据分析"])
        app.include_router(health.router, tags=["健康检查"])
    except ImportError as e:
        print(f"警告: 无法导入API路由: {e}")


# 创建应用实例
app = create_app()