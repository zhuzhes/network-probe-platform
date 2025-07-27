"""权限管理"""

from enum import Enum
from typing import List, Set
from shared.models.user import User, UserRole


class Permission(str, Enum):
    """权限枚举"""
    
    # 用户管理权限
    USER_CREATE = "user:create"
    USER_READ = "user:read"
    USER_UPDATE = "user:update"
    USER_DELETE = "user:delete"
    USER_LIST = "user:list"
    
    # 任务管理权限
    TASK_CREATE = "task:create"
    TASK_READ = "task:read"
    TASK_UPDATE = "task:update"
    TASK_DELETE = "task:delete"
    TASK_LIST = "task:list"
    TASK_EXECUTE = "task:execute"
    
    # 代理管理权限
    AGENT_CREATE = "agent:create"
    AGENT_READ = "agent:read"
    AGENT_UPDATE = "agent:update"
    AGENT_DELETE = "agent:delete"
    AGENT_LIST = "agent:list"
    AGENT_MANAGE = "agent:manage"
    
    # 数据分析权限
    DATA_READ = "data:read"
    DATA_EXPORT = "data:export"
    DATA_ANALYZE = "data:analyze"
    
    # 系统管理权限
    SYSTEM_CONFIG = "system:config"
    SYSTEM_MONITOR = "system:monitor"
    SYSTEM_BACKUP = "system:backup"
    
    # 计费权限
    BILLING_READ = "billing:read"
    BILLING_MANAGE = "billing:manage"
    BILLING_RECHARGE = "billing:recharge"


# 角色权限映射
ROLE_PERMISSIONS: dict[UserRole, Set[Permission]] = {
    UserRole.ADMIN: {
        # 管理员拥有所有权限
        Permission.USER_CREATE,
        Permission.USER_READ,
        Permission.USER_UPDATE,
        Permission.USER_DELETE,
        Permission.USER_LIST,
        Permission.TASK_CREATE,
        Permission.TASK_READ,
        Permission.TASK_UPDATE,
        Permission.TASK_DELETE,
        Permission.TASK_LIST,
        Permission.TASK_EXECUTE,
        Permission.AGENT_CREATE,
        Permission.AGENT_READ,
        Permission.AGENT_UPDATE,
        Permission.AGENT_DELETE,
        Permission.AGENT_LIST,
        Permission.AGENT_MANAGE,
        Permission.DATA_READ,
        Permission.DATA_EXPORT,
        Permission.DATA_ANALYZE,
        Permission.SYSTEM_CONFIG,
        Permission.SYSTEM_MONITOR,
        Permission.SYSTEM_BACKUP,
        Permission.BILLING_READ,
        Permission.BILLING_MANAGE,
        Permission.BILLING_RECHARGE,
    },
    UserRole.ENTERPRISE: {
        # 企业用户权限
        Permission.USER_READ,  # 只能读取自己的信息
        Permission.USER_UPDATE,  # 只能更新自己的信息
        Permission.TASK_CREATE,
        Permission.TASK_READ,  # 只能读取自己的任务
        Permission.TASK_UPDATE,  # 只能更新自己的任务
        Permission.TASK_DELETE,  # 只能删除自己的任务
        Permission.TASK_LIST,  # 只能列出自己的任务
        Permission.AGENT_READ,  # 只能查看代理信息，不能管理
        Permission.AGENT_LIST,
        Permission.DATA_READ,  # 只能读取自己的数据
        Permission.DATA_EXPORT,  # 只能导出自己的数据
        Permission.BILLING_READ,  # 只能查看自己的计费信息
        Permission.BILLING_RECHARGE,  # 可以给自己充值
    }
}


def get_user_permissions(user: User) -> Set[Permission]:
    """获取用户权限"""
    return ROLE_PERMISSIONS.get(user.role, set())


def has_permission(user: User, permission: Permission) -> bool:
    """检查用户是否有特定权限"""
    user_permissions = get_user_permissions(user)
    return permission in user_permissions


def check_permission(user: User, permission: Permission) -> None:
    """检查权限，如果没有权限则抛出异常"""
    if not has_permission(user, permission):
        from fastapi import HTTPException, status
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"Permission denied: {permission.value}"
        )


def can_access_user_data(current_user: User, target_user_id: str) -> bool:
    """检查是否可以访问用户数据"""
    # 管理员可以访问所有用户数据
    if current_user.role == UserRole.ADMIN:
        return True
    
    # 用户只能访问自己的数据
    return str(current_user.id) == target_user_id


def can_access_task_data(current_user: User, task_user_id: str) -> bool:
    """检查是否可以访问任务数据"""
    # 管理员可以访问所有任务数据
    if current_user.role == UserRole.ADMIN:
        return True
    
    # 用户只能访问自己的任务数据
    return str(current_user.id) == task_user_id


def filter_user_query(current_user: User, query):
    """根据用户权限过滤查询"""
    if current_user.role == UserRole.ADMIN:
        return query
    
    # 企业用户只能查询自己的数据
    return query.filter_by(user_id=current_user.id)