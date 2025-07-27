"""权限管理单元测试"""

import pytest
from unittest.mock import Mock
from fastapi import HTTPException

from shared.security.permissions import (
    Permission,
    get_user_permissions,
    has_permission,
    check_permission,
    can_access_user_data,
    can_access_task_data,
    filter_user_query
)
from shared.models.user import User, UserRole, UserStatus


class TestPermissions:
    """权限测试"""
    
    def test_admin_permissions(self):
        """测试管理员权限"""
        admin_user = User(
            username="admin",
            email="admin@example.com",
            role=UserRole.ADMIN,
            status=UserStatus.ACTIVE
        )
        
        permissions = get_user_permissions(admin_user)
        
        # 管理员应该有所有权限
        assert Permission.USER_CREATE in permissions
        assert Permission.USER_DELETE in permissions
        assert Permission.AGENT_MANAGE in permissions
        assert Permission.SYSTEM_CONFIG in permissions
        assert Permission.BILLING_MANAGE in permissions
    
    def test_enterprise_permissions(self):
        """测试企业用户权限"""
        enterprise_user = User(
            username="enterprise",
            email="enterprise@example.com",
            role=UserRole.ENTERPRISE,
            status=UserStatus.ACTIVE
        )
        
        permissions = get_user_permissions(enterprise_user)
        
        # 企业用户应该有基本权限
        assert Permission.TASK_CREATE in permissions
        assert Permission.TASK_READ in permissions
        assert Permission.DATA_READ in permissions
        assert Permission.BILLING_READ in permissions
        
        # 企业用户不应该有管理权限
        assert Permission.USER_DELETE not in permissions
        assert Permission.AGENT_MANAGE not in permissions
        assert Permission.SYSTEM_CONFIG not in permissions
        assert Permission.BILLING_MANAGE not in permissions
    
    def test_has_permission_admin(self):
        """测试管理员权限检查"""
        admin_user = User(
            username="admin",
            email="admin@example.com",
            role=UserRole.ADMIN,
            status=UserStatus.ACTIVE
        )
        
        assert has_permission(admin_user, Permission.USER_CREATE) is True
        assert has_permission(admin_user, Permission.SYSTEM_CONFIG) is True
        assert has_permission(admin_user, Permission.AGENT_MANAGE) is True
    
    def test_has_permission_enterprise(self):
        """测试企业用户权限检查"""
        enterprise_user = User(
            username="enterprise",
            email="enterprise@example.com",
            role=UserRole.ENTERPRISE,
            status=UserStatus.ACTIVE
        )
        
        assert has_permission(enterprise_user, Permission.TASK_CREATE) is True
        assert has_permission(enterprise_user, Permission.DATA_READ) is True
        assert has_permission(enterprise_user, Permission.SYSTEM_CONFIG) is False
        assert has_permission(enterprise_user, Permission.AGENT_MANAGE) is False
    
    def test_check_permission_success(self):
        """测试权限检查成功"""
        admin_user = User(
            username="admin",
            email="admin@example.com",
            role=UserRole.ADMIN,
            status=UserStatus.ACTIVE
        )
        
        # 不应该抛出异常
        check_permission(admin_user, Permission.USER_CREATE)
    
    def test_check_permission_failure(self):
        """测试权限检查失败"""
        enterprise_user = User(
            username="enterprise",
            email="enterprise@example.com",
            role=UserRole.ENTERPRISE,
            status=UserStatus.ACTIVE
        )
        
        # 应该抛出HTTPException
        with pytest.raises(HTTPException) as exc_info:
            check_permission(enterprise_user, Permission.SYSTEM_CONFIG)
        
        assert exc_info.value.status_code == 403
        assert "Permission denied" in str(exc_info.value.detail)


class TestDataAccess:
    """数据访问权限测试"""
    
    def test_admin_can_access_any_user_data(self):
        """测试管理员可以访问任何用户数据"""
        admin_user = User(
            username="admin",
            email="admin@example.com",
            role=UserRole.ADMIN,
            status=UserStatus.ACTIVE
        )
        admin_user.id = "admin-id"
        
        assert can_access_user_data(admin_user, "other-user-id") is True
        assert can_access_user_data(admin_user, "admin-id") is True
    
    def test_enterprise_can_only_access_own_data(self):
        """测试企业用户只能访问自己的数据"""
        enterprise_user = User(
            username="enterprise",
            email="enterprise@example.com",
            role=UserRole.ENTERPRISE,
            status=UserStatus.ACTIVE
        )
        enterprise_user.id = "enterprise-id"
        
        assert can_access_user_data(enterprise_user, "enterprise-id") is True
        assert can_access_user_data(enterprise_user, "other-user-id") is False
    
    def test_admin_can_access_any_task_data(self):
        """测试管理员可以访问任何任务数据"""
        admin_user = User(
            username="admin",
            email="admin@example.com",
            role=UserRole.ADMIN,
            status=UserStatus.ACTIVE
        )
        admin_user.id = "admin-id"
        
        assert can_access_task_data(admin_user, "other-user-id") is True
        assert can_access_task_data(admin_user, "admin-id") is True
    
    def test_enterprise_can_only_access_own_tasks(self):
        """测试企业用户只能访问自己的任务"""
        enterprise_user = User(
            username="enterprise",
            email="enterprise@example.com",
            role=UserRole.ENTERPRISE,
            status=UserStatus.ACTIVE
        )
        enterprise_user.id = "enterprise-id"
        
        assert can_access_task_data(enterprise_user, "enterprise-id") is True
        assert can_access_task_data(enterprise_user, "other-user-id") is False
    
    def test_filter_user_query_admin(self):
        """测试管理员查询过滤"""
        admin_user = User(
            username="admin",
            email="admin@example.com",
            role=UserRole.ADMIN,
            status=UserStatus.ACTIVE
        )
        
        mock_query = Mock()
        result = filter_user_query(admin_user, mock_query)
        
        # 管理员应该返回原始查询，不进行过滤
        assert result == mock_query
        mock_query.filter_by.assert_not_called()
    
    def test_filter_user_query_enterprise(self):
        """测试企业用户查询过滤"""
        enterprise_user = User(
            username="enterprise",
            email="enterprise@example.com",
            role=UserRole.ENTERPRISE,
            status=UserStatus.ACTIVE
        )
        enterprise_user.id = "enterprise-id"
        
        mock_query = Mock()
        result = filter_user_query(enterprise_user, mock_query)
        
        # 企业用户应该过滤查询，只返回自己的数据
        mock_query.filter_by.assert_called_once_with(user_id=enterprise_user.id)
        assert result == mock_query.filter_by.return_value


class TestUnknownRole:
    """未知角色测试"""
    
    def test_unknown_role_no_permissions(self):
        """测试未知角色没有权限"""
        # 创建一个具有未知角色的用户（这在实际中不应该发生）
        user = User(
            username="unknown",
            email="unknown@example.com",
            status=UserStatus.ACTIVE
        )
        # 手动设置一个不存在的角色
        user.role = "unknown_role"
        
        permissions = get_user_permissions(user)
        
        # 未知角色应该没有任何权限
        assert len(permissions) == 0
        assert has_permission(user, Permission.USER_READ) is False