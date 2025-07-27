"""
健康检查API端点
"""

import asyncio
import time
from typing import Dict, Any

from fastapi import APIRouter, HTTPException, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import text
import redis.asyncio as redis
import aiohttp

from management_platform.database.connection import get_db
from management_platform.api.dependencies import get_redis_client
from shared.config import get_settings

router = APIRouter(prefix="/health", tags=["健康检查"])
settings = get_settings()


@router.get("/")
async def health_check():
    """基本健康检查"""
    return {
        "status": "healthy",
        "timestamp": time.time(),
        "version": "1.0.0",
        "environment": settings.ENVIRONMENT
    }


@router.get("/detailed")
async def detailed_health_check(
    db: AsyncSession = Depends(get_db),
    redis_client: redis.Redis = Depends(get_redis_client)
) -> Dict[str, Any]:
    """详细健康检查，包括所有依赖服务"""
    
    health_status = {
        "status": "healthy",
        "timestamp": time.time(),
        "version": "1.0.0",
        "environment": settings.ENVIRONMENT,
        "checks": {}
    }
    
    # 检查数据库连接
    try:
        start_time = time.time()
        result = await db.execute(text("SELECT 1"))
        db_response_time = (time.time() - start_time) * 1000
        
        health_status["checks"]["database"] = {
            "status": "healthy",
            "response_time_ms": round(db_response_time, 2),
            "details": "PostgreSQL connection successful"
        }
    except Exception as e:
        health_status["status"] = "unhealthy"
        health_status["checks"]["database"] = {
            "status": "unhealthy",
            "error": str(e),
            "details": "PostgreSQL connection failed"
        }
    
    # 检查Redis连接
    try:
        start_time = time.time()
        await redis_client.ping()
        redis_response_time = (time.time() - start_time) * 1000
        
        health_status["checks"]["redis"] = {
            "status": "healthy",
            "response_time_ms": round(redis_response_time, 2),
            "details": "Redis connection successful"
        }
    except Exception as e:
        health_status["status"] = "unhealthy"
        health_status["checks"]["redis"] = {
            "status": "unhealthy",
            "error": str(e),
            "details": "Redis connection failed"
        }
    
    # 检查RabbitMQ连接
    try:
        import pika
        start_time = time.time()
        
        connection = pika.BlockingConnection(
            pika.URLParameters(settings.RABBITMQ_URL)
        )
        channel = connection.channel()
        channel.queue_declare(queue='health_check', durable=False, auto_delete=True)
        connection.close()
        
        rabbitmq_response_time = (time.time() - start_time) * 1000
        
        health_status["checks"]["rabbitmq"] = {
            "status": "healthy",
            "response_time_ms": round(rabbitmq_response_time, 2),
            "details": "RabbitMQ connection successful"
        }
    except Exception as e:
        health_status["status"] = "unhealthy"
        health_status["checks"]["rabbitmq"] = {
            "status": "unhealthy",
            "error": str(e),
            "details": "RabbitMQ connection failed"
        }
    
    # 检查磁盘空间
    try:
        import shutil
        disk_usage = shutil.disk_usage("/")
        free_space_gb = disk_usage.free / (1024**3)
        total_space_gb = disk_usage.total / (1024**3)
        usage_percent = ((disk_usage.total - disk_usage.free) / disk_usage.total) * 100
        
        disk_status = "healthy" if usage_percent < 90 else "warning" if usage_percent < 95 else "critical"
        
        health_status["checks"]["disk"] = {
            "status": disk_status,
            "free_space_gb": round(free_space_gb, 2),
            "total_space_gb": round(total_space_gb, 2),
            "usage_percent": round(usage_percent, 2),
            "details": f"Disk usage at {usage_percent:.1f}%"
        }
        
        if disk_status != "healthy":
            health_status["status"] = "degraded"
            
    except Exception as e:
        health_status["checks"]["disk"] = {
            "status": "unknown",
            "error": str(e),
            "details": "Unable to check disk usage"
        }
    
    # 检查内存使用
    try:
        import psutil
        memory = psutil.virtual_memory()
        memory_usage_percent = memory.percent
        
        memory_status = "healthy" if memory_usage_percent < 80 else "warning" if memory_usage_percent < 90 else "critical"
        
        health_status["checks"]["memory"] = {
            "status": memory_status,
            "usage_percent": memory_usage_percent,
            "available_gb": round(memory.available / (1024**3), 2),
            "total_gb": round(memory.total / (1024**3), 2),
            "details": f"Memory usage at {memory_usage_percent:.1f}%"
        }
        
        if memory_status != "healthy":
            health_status["status"] = "degraded"
            
    except Exception as e:
        health_status["checks"]["memory"] = {
            "status": "unknown",
            "error": str(e),
            "details": "Unable to check memory usage"
        }
    
    return health_status


@router.get("/readiness")
async def readiness_check(
    db: AsyncSession = Depends(get_db),
    redis_client: redis.Redis = Depends(get_redis_client)
):
    """就绪检查 - 检查服务是否准备好接收请求"""
    
    checks = []
    
    # 检查数据库
    try:
        await db.execute(text("SELECT 1"))
        checks.append(("database", True))
    except Exception:
        checks.append(("database", False))
    
    # 检查Redis
    try:
        await redis_client.ping()
        checks.append(("redis", True))
    except Exception:
        checks.append(("redis", False))
    
    # 所有检查都必须通过
    all_ready = all(check[1] for check in checks)
    
    if not all_ready:
        raise HTTPException(status_code=503, detail="Service not ready")
    
    return {
        "status": "ready",
        "timestamp": time.time(),
        "checks": {name: "ready" if status else "not_ready" for name, status in checks}
    }


@router.get("/liveness")
async def liveness_check():
    """存活检查 - 检查服务是否还活着"""
    return {
        "status": "alive",
        "timestamp": time.time(),
        "uptime": time.time() - start_time if 'start_time' in globals() else 0
    }


# 记录启动时间
start_time = time.time()


@router.get("/metrics")
async def metrics_endpoint():
    """Prometheus指标端点"""
    try:
        from prometheus_client import generate_latest, CONTENT_TYPE_LATEST
        return generate_latest()
    except ImportError:
        return {"error": "Prometheus client not available"}