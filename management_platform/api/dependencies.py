"""API依赖注入"""

from typing import Generator
from fastapi import Depends, HTTPException, status, Request
from sqlalchemy.orm import Session
import uuid

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))

from management_platform.database.connection import get_db_session
from shared.models.user import User, UserRole, UserStatus
from shared.security.auth import get_current_user as auth_get_current_user, get_current_active_user


def get_db() -> Generator[Session, None, None]:
    """获取数据库会话依赖"""
    yield from get_db_session()


def get_db_from_request(request: Request) -> Session:
    """从请求状态获取数据库会话"""
    if not hasattr(request.state, "db"):
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Database session not available"
        )
    return request.state.db


def get_current_user_from_request(request: Request) -> User:
    """从请求状态获取当前用户"""
    if not hasattr(request.state, "current_user"):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User not authenticated"
        )
    return request.state.current_user


def get_current_user(request: Request) -> User:
    """获取当前用户（从请求状态）"""
    if hasattr(request.state, "current_user"):
        return request.state.current_user
    raise HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="User not authenticated"
    )


def require_admin(current_user: User = Depends(get_current_active_user)) -> User:
    """要求管理员权限的依赖"""
    if current_user.role != UserRole.ADMIN:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admin access required"
        )
    return current_user


def require_enterprise() -> User:
    """要求企业用户权限的依赖"""
    def enterprise_checker(current_user: User = Depends(get_current_active_user)) -> User:
        if current_user.role not in [UserRole.ENTERPRISE, UserRole.ADMIN]:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Enterprise access required"
            )
        return current_user
    return enterprise_checker


def check_user_access(target_user_id: str):
    """检查用户访问权限的依赖"""
    def access_checker(current_user: User = Depends(get_current_active_user)) -> User:
        # 管理员可以访问所有用户数据
        if current_user.role == UserRole.ADMIN:
            return current_user
        
        # 用户只能访问自己的数据
        if str(current_user.id) != target_user_id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Access denied: can only access own data"
            )
        
        return current_user
    return access_checker


def check_sufficient_credits(required_credits: float):
    """检查用户点数是否足够的依赖"""
    def credits_checker(current_user: User = Depends(get_current_active_user)) -> User:
        if not current_user.can_consume_credits(required_credits):
            raise HTTPException(
                status_code=status.HTTP_402_PAYMENT_REQUIRED,
                detail=f"Insufficient credits. Required: {required_credits}, Available: {current_user.credits}"
            )
        return current_user
    return credits_checker


class PaginationParams:
    """分页参数"""
    
    def __init__(self, page: int = 1, size: int = 20):
        if page < 1:
            page = 1
        if size < 1:
            size = 20
        if size > 100:
            size = 100
        
        self.page = page
        self.size = size
        self.offset = (page - 1) * size
        self.limit = size


def get_pagination_params(page: int = 1, size: int = 20) -> PaginationParams:
    """获取分页参数依赖"""
    return PaginationParams(page, size)


class SortParams:
    """排序参数"""
    
    def __init__(self, sort_by: str = "created_at", sort_order: str = "desc"):
        self.sort_by = sort_by
        self.sort_order = sort_order.lower()
        
        if self.sort_order not in ["asc", "desc"]:
            self.sort_order = "desc"


def get_sort_params(sort_by: str = "created_at", sort_order: str = "desc") -> SortParams:
    """获取排序参数依赖"""
    return SortParams(sort_by, sort_order)


class FilterParams:
    """过滤参数基类"""
    pass


def validate_uuid(uuid_str: str) -> str:
    """验证UUID格式"""
    import uuid
    try:
        uuid.UUID(uuid_str)
        return uuid_str
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid UUID format: {uuid_str}"
        )