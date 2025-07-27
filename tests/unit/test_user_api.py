"""用户API端点测试"""

import pytest
import asyncio
import uuid
from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, patch
from fastapi.testclient import TestClient
from fastapi import status

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))

from shared.models.user import (
    User, UserCreate, UserUpdate, UserLogin, PasswordChange, 
    CreditRecharge, UserRole, UserStatus, TransactionType
)
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
    user.verify_password = MagicMock(return_value=True)
    user.set_password = MagicMock()
    user.generate_api_key = MagicMock(return_value="test_api_key")
    user.api_key_created_at = datetime.now()
    return user


@pytest.fixture
def mock_admin_user():
    """模拟管理员用户"""
    user = MagicMock()
    user.id = uuid.uuid4()
    user.username = "admin"
    user.email = "admin@example.com"
    user.company_name = "Admin Company"
    user.role = UserRole.ADMIN
    user.credits = 1000.0
    user.status = UserStatus.ACTIVE
    user.api_key_hash = None
    user.password_hash = "hashed_password"
    user.created_at = datetime.now()
    user.updated_at = datetime.now()
    user.last_login = None
    return user


@pytest.fixture
def mock_transaction():
    """模拟交易对象"""
    transaction = MagicMock()
    transaction.id = uuid.uuid4()
    transaction.user_id = uuid.uuid4()
    transaction.amount = 50.0
    transaction.type = TransactionType.RECHARGE
    transaction.description = "测试充值"
    transaction.reference_id = "test_ref_123"
    transaction.created_at = datetime.now()
    transaction.updated_at = datetime.now()
    return transaction


class TestUserRegistration:
    """用户注册测试"""
    
    @patch('management_platform.api.routes.users.UserRepository')
    def test_create_user_success(self, mock_repo_class, client, mock_user):
        """测试成功创建用户"""
        mock_repo = AsyncMock()
        mock_repo_class.return_value = mock_repo
        mock_repo.is_username_taken.return_value = False
        mock_repo.is_email_taken.return_value = False
        mock_repo.create.return_value = mock_user
        mock_repo.commit.return_value = None
        
        user_data = {
            "username": "newuser",
            "email": "newuser@example.com",
            "password": "Password123!",
            "company_name": "New Company"
        }
        
        response = client.post("/api/v1/users/", json=user_data)
        
        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert data["username"] == mock_user.username
        assert data["email"] == mock_user.email
        assert "password" not in data
    
    @patch('management_platform.api.routes.users.UserRepository')
    def test_create_user_username_exists(self, mock_repo_class, client):
        """测试用户名已存在"""
        mock_repo = AsyncMock()
        mock_repo_class.return_value = mock_repo
        mock_repo.is_username_taken.return_value = True
        
        user_data = {
            "username": "existinguser",
            "email": "new@example.com",
            "password": "Password123!"
        }
        
        response = client.post("/api/v1/users/", json=user_data)
        
        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert "用户名已存在" in response.json()["detail"]
    
    @patch('management_platform.api.routes.users.UserRepository')
    def test_create_user_email_exists(self, mock_repo_class, client):
        """测试邮箱已存在"""
        mock_repo = AsyncMock()
        mock_repo_class.return_value = mock_repo
        mock_repo.is_username_taken.return_value = False
        mock_repo.is_email_taken.return_value = True
        
        user_data = {
            "username": "newuser",
            "email": "existing@example.com",
            "password": "Password123!"
        }
        
        response = client.post("/api/v1/users/", json=user_data)
        
        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert "邮箱已存在" in response.json()["detail"]


class TestUserManagement:
    """用户管理测试"""
    
    @patch('management_platform.api.routes.users.require_admin')
    @patch('management_platform.api.routes.users.UserRepository')
    def test_get_users_list_admin(self, mock_repo_class, mock_auth, client, mock_admin_user):
        """测试管理员获取用户列表"""
        mock_auth.return_value = mock_admin_user
        mock_repo = AsyncMock()
        mock_repo_class.return_value = mock_repo
        mock_repo.get_all.return_value = [mock_admin_user]
        mock_repo.count.return_value = 1
        
        response = client.get("/api/v1/users/?page=1&size=20")
        
        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert "users" in data
        assert "total" in data
        assert data["total"] == 1
    
    @patch('management_platform.api.routes.users.get_current_user')
    @patch('management_platform.api.routes.users.UserRepository')
    def test_get_user_detail_self(self, mock_repo_class, mock_auth, client, mock_user):
        """测试用户获取自己的详情"""
        mock_auth.return_value = mock_user
        mock_repo = AsyncMock()
        mock_repo_class.return_value = mock_repo
        mock_repo.get_by_id.return_value = mock_user
        
        response = client.get(f"/api/v1/users/{mock_user.id}")
        
        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert data["username"] == mock_user.username
    
    @patch('management_platform.api.routes.users.get_current_user')
    @patch('management_platform.api.routes.users.UserRepository')
    def test_get_user_detail_forbidden(self, mock_repo_class, mock_auth, client, mock_user):
        """测试用户无权访问其他用户详情"""
        mock_auth.return_value = mock_user
        other_user_id = uuid.uuid4()
        
        response = client.get(f"/api/v1/users/{other_user_id}")
        
        assert response.status_code == status.HTTP_403_FORBIDDEN
    
    @patch('management_platform.api.routes.users.get_current_user')
    @patch('management_platform.api.routes.users.UserRepository')
    def test_update_user_success(self, mock_repo_class, mock_auth, client, mock_user):
        """测试成功更新用户信息"""
        mock_auth.return_value = mock_user
        mock_repo = AsyncMock()
        mock_repo_class.return_value = mock_repo
        mock_repo.get_by_id.return_value = mock_user
        mock_repo.is_username_taken.return_value = False
        mock_repo.is_email_taken.return_value = False
        mock_repo.update.return_value = mock_user
        mock_repo.commit.return_value = None
        
        update_data = {
            "username": "updateduser",
            "email": "updated@example.com"
        }
        
        response = client.put(f"/api/v1/users/{mock_user.id}", json=update_data)
        
        assert response.status_code == status.HTTP_200_OK
    
    @patch('management_platform.api.routes.users.require_admin')
    @patch('management_platform.api.routes.users.UserRepository')
    def test_delete_user_admin(self, mock_repo_class, mock_auth, client, mock_admin_user, mock_user):
        """测试管理员删除用户"""
        mock_auth.return_value = mock_admin_user
        mock_repo = AsyncMock()
        mock_repo_class.return_value = mock_repo
        mock_repo.get_by_id.return_value = mock_user
        mock_repo.delete.return_value = None
        mock_repo.commit.return_value = None
        
        response = client.delete(f"/api/v1/users/{mock_user.id}")
        
        assert response.status_code == status.HTTP_200_OK
        assert "删除成功" in response.json()["message"]


class TestPasswordManagement:
    """密码管理测试"""
    
    @patch('management_platform.api.routes.users.get_current_user')
    @patch('management_platform.api.routes.users.UserRepository')
    def test_change_password_success(self, mock_repo_class, mock_auth, client, mock_user):
        """测试成功修改密码"""
        mock_auth.return_value = mock_user
        mock_repo = AsyncMock()
        mock_repo_class.return_value = mock_repo
        mock_repo.get_by_id.return_value = mock_user
        mock_repo.update.return_value = None
        mock_repo.commit.return_value = None
        
        password_data = {
            "old_password": "oldpassword",
            "new_password": "NewPassword123!"
        }
        
        response = client.post(f"/api/v1/users/{mock_user.id}/change-password", json=password_data)
        
        assert response.status_code == status.HTTP_200_OK
        assert "密码修改成功" in response.json()["message"]
    
    @patch('management_platform.api.routes.users.get_current_user')
    @patch('management_platform.api.routes.users.UserRepository')
    def test_change_password_wrong_old_password(self, mock_repo_class, mock_auth, client, mock_user):
        """测试旧密码错误"""
        mock_user.verify_password.return_value = False
        mock_auth.return_value = mock_user
        mock_repo = AsyncMock()
        mock_repo_class.return_value = mock_repo
        mock_repo.get_by_id.return_value = mock_user
        
        password_data = {
            "old_password": "wrongpassword",
            "new_password": "NewPassword123!"
        }
        
        response = client.post(f"/api/v1/users/{mock_user.id}/change-password", json=password_data)
        
        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert "旧密码错误" in response.json()["detail"]


class TestCreditManagement:
    """点数管理测试"""
    
    @patch('management_platform.api.routes.users.get_current_user')
    @patch('management_platform.api.routes.users.UserRepository')
    @patch('management_platform.api.routes.users.CreditTransactionRepository')
    def test_recharge_credits_success(self, mock_trans_repo_class, mock_user_repo_class, 
                                    mock_auth, client, mock_user, mock_transaction):
        """测试成功充值"""
        mock_auth.return_value = mock_user
        mock_user_repo = AsyncMock()
        mock_trans_repo = AsyncMock()
        mock_user_repo_class.return_value = mock_user_repo
        mock_trans_repo_class.return_value = mock_trans_repo
        
        mock_user_repo.get_by_id.return_value = mock_user
        mock_trans_repo.create.return_value = mock_transaction
        mock_user_repo.update.return_value = None
        mock_user_repo.commit.return_value = None
        
        recharge_data = {
            "amount": 100.0,
            "payment_method": "credit_card",
            "description": "测试充值"
        }
        
        response = client.post(f"/api/v1/users/{mock_user.id}/recharge", json=recharge_data)
        
        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert data["amount"] == mock_transaction.amount
        assert data["type"] == mock_transaction.type
    
    @patch('management_platform.api.routes.users.require_admin')
    @patch('management_platform.api.routes.users.UserRepository')
    @patch('management_platform.api.routes.users.CreditTransactionRepository')
    def test_add_voucher_admin(self, mock_trans_repo_class, mock_user_repo_class, 
                              mock_auth, client, mock_admin_user, mock_user, mock_transaction):
        """测试管理员添加抵用券"""
        mock_auth.return_value = mock_admin_user
        mock_user_repo = AsyncMock()
        mock_trans_repo = AsyncMock()
        mock_user_repo_class.return_value = mock_user_repo
        mock_trans_repo_class.return_value = mock_trans_repo
        
        mock_user_repo.get_by_id.return_value = mock_user
        mock_trans_repo.create.return_value = mock_transaction
        mock_user_repo.update.return_value = None
        mock_user_repo.commit.return_value = None
        
        response = client.post(
            f"/api/v1/users/{mock_user.id}/voucher?amount=50.0&description=测试抵用券"
        )
        
        assert response.status_code == status.HTTP_200_OK
    
    @patch('management_platform.api.routes.users.get_current_user')
    @patch('management_platform.api.routes.users.CreditTransactionRepository')
    def test_get_user_transactions(self, mock_trans_repo_class, mock_auth, client, mock_user, mock_transaction):
        """测试获取用户交易记录"""
        mock_auth.return_value = mock_user
        mock_trans_repo = AsyncMock()
        mock_trans_repo_class.return_value = mock_trans_repo
        mock_trans_repo.get_by_user_id.return_value = [mock_transaction]
        
        response = client.get(f"/api/v1/users/{mock_user.id}/transactions")
        
        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert "transactions" in data
        assert len(data["transactions"]) == 1


class TestApiKeyManagement:
    """API密钥管理测试"""
    
    @patch('management_platform.api.routes.users.get_current_user')
    @patch('management_platform.api.routes.users.UserRepository')
    def test_generate_api_key_success(self, mock_repo_class, mock_auth, client, mock_user):
        """测试成功生成API密钥"""
        mock_auth.return_value = mock_user
        mock_repo = AsyncMock()
        mock_repo_class.return_value = mock_repo
        mock_repo.get_by_id.return_value = mock_user
        mock_repo.update.return_value = None
        mock_repo.commit.return_value = None
        
        response = client.post(f"/api/v1/users/{mock_user.id}/api-key")
        
        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert "api_key" in data
        assert "created_at" in data
    
    @patch('management_platform.api.routes.users.get_current_user')
    @patch('management_platform.api.routes.users.UserRepository')
    def test_revoke_api_key_success(self, mock_repo_class, mock_auth, client, mock_user):
        """测试成功撤销API密钥"""
        mock_user.api_key_hash = "some_hash"
        mock_auth.return_value = mock_user
        mock_repo = AsyncMock()
        mock_repo_class.return_value = mock_repo
        mock_repo.get_by_id.return_value = mock_user
        mock_repo.update.return_value = None
        mock_repo.commit.return_value = None
        
        response = client.delete(f"/api/v1/users/{mock_user.id}/api-key")
        
        assert response.status_code == status.HTTP_200_OK
        assert "已撤销" in response.json()["message"]
    
    @patch('management_platform.api.routes.users.get_current_user')
    @patch('management_platform.api.routes.users.UserRepository')
    def test_revoke_api_key_not_exists(self, mock_repo_class, mock_auth, client, mock_user):
        """测试撤销不存在的API密钥"""
        mock_user.api_key_hash = None
        mock_auth.return_value = mock_user
        mock_repo = AsyncMock()
        mock_repo_class.return_value = mock_repo
        mock_repo.get_by_id.return_value = mock_user
        
        response = client.delete(f"/api/v1/users/{mock_user.id}/api-key")
        
        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert "没有API密钥" in response.json()["detail"]


class TestValidation:
    """输入验证测试"""
    
    def test_create_user_invalid_data(self, client):
        """测试创建用户时的无效数据"""
        invalid_data = {
            "username": "",  # 空用户名
            "email": "invalid-email",  # 无效邮箱
            "password": "123"  # 密码太短
        }
        
        response = client.post("/api/v1/users/", json=invalid_data)
        
        assert response.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY
    
    def test_recharge_negative_amount(self, client):
        """测试充值负数金额"""
        user_id = uuid.uuid4()
        recharge_data = {
            "amount": -100.0,
            "payment_method": "credit_card"
        }
        
        response = client.post(f"/api/v1/users/{user_id}/recharge", json=recharge_data)
        
        # 应该返回422验证错误或403权限错误（取决于认证状态）
        assert response.status_code in [status.HTTP_422_UNPROCESSABLE_ENTITY, status.HTTP_403_FORBIDDEN]


if __name__ == "__main__":
    pytest.main([__file__, "-v"])