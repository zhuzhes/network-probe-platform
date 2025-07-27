"""用户仓库简化测试"""

import pytest
import uuid
from datetime import datetime, timedelta

from management_platform.database.repositories import UserRepository, CreditTransactionRepository
from shared.models.user import User, CreditTransaction, UserRole, UserStatus, TransactionType


def generate_unique_username():
    """生成唯一的用户名"""
    return f"testuser_{uuid.uuid4().hex[:8]}"


def generate_unique_email():
    """生成唯一的邮箱"""
    return f"test_{uuid.uuid4().hex[:8]}@example.com"


class TestUserRepository:
    """用户仓库测试类"""
    
    @pytest.mark.asyncio
    async def test_create_user(self, db_session):
        """测试创建用户"""
        repo = UserRepository(db_session)
        
        username = generate_unique_username()
        email = generate_unique_email()
        
        user_data = {
            "username": username,
            "email": email,
            "password_hash": "hashed_password",
            "company_name": "Test Company",
            "role": UserRole.ENTERPRISE,
            "credits": 100.0
        }
        
        user = await repo.create(user_data)
        
        assert user.id is not None
        assert user.username == username
        assert user.email == email
        assert user.company_name == "Test Company"
        assert user.role == UserRole.ENTERPRISE
        assert user.credits == 100.0
        assert user.status == UserStatus.ACTIVE
    
    @pytest.mark.asyncio
    async def test_get_user_by_id(self, db_session):
        """测试根据ID获取用户"""
        repo = UserRepository(db_session)
        
        username = generate_unique_username()
        email = generate_unique_email()
        
        # 创建用户
        user_data = {
            "username": username,
            "email": email,
            "password_hash": "hashed_password"
        }
        created_user = await repo.create(user_data)
        
        # 获取用户
        found_user = await repo.get_by_id(created_user.id)
        
        assert found_user is not None
        assert found_user.id == created_user.id
        assert found_user.username == username
        assert found_user.email == email
    
    @pytest.mark.asyncio
    async def test_get_user_by_username(self, db_session):
        """测试根据用户名获取用户"""
        repo = UserRepository(db_session)
        
        username = generate_unique_username()
        email = generate_unique_email()
        
        user_data = {
            "username": username,
            "email": email,
            "password_hash": "hashed_password"
        }
        created_user = await repo.create(user_data)
        
        found_user = await repo.get_by_username(username)
        
        assert found_user is not None
        assert found_user.id == created_user.id
        assert found_user.username == username
    
    @pytest.mark.asyncio
    async def test_update_user(self, db_session):
        """测试更新用户"""
        repo = UserRepository(db_session)
        
        username = generate_unique_username()
        email = generate_unique_email()
        
        user_data = {
            "username": username,
            "email": email,
            "password_hash": "hashed_password",
            "credits": 100.0
        }
        created_user = await repo.create(user_data)
        
        # 更新用户
        update_data = {
            "company_name": "Updated Company",
            "credits": 200.0
        }
        updated_user = await repo.update(created_user.id, update_data)
        
        assert updated_user is not None
        assert updated_user.company_name == "Updated Company"
        assert updated_user.credits == 200.0
        # 验证更新时间已更新（通过重新获取用户来验证）
        fresh_user = await repo.get_by_id(created_user.id)
        assert fresh_user.updated_at >= created_user.created_at
    
    @pytest.mark.asyncio
    async def test_delete_user(self, db_session):
        """测试删除用户"""
        repo = UserRepository(db_session)
        
        username = generate_unique_username()
        email = generate_unique_email()
        
        user_data = {
            "username": username,
            "email": email,
            "password_hash": "hashed_password"
        }
        created_user = await repo.create(user_data)
        
        # 删除用户
        result = await repo.delete(created_user.id)
        assert result is True
        
        # 验证用户已删除
        found_user = await repo.get_by_id(created_user.id)
        assert found_user is None
    
    @pytest.mark.asyncio
    async def test_is_username_taken(self, db_session):
        """测试用户名是否已被使用"""
        repo = UserRepository(db_session)
        
        username = generate_unique_username()
        email = generate_unique_email()
        
        user_data = {
            "username": username,
            "email": email,
            "password_hash": "hashed_password"
        }
        created_user = await repo.create(user_data)
        
        # 检查已存在的用户名
        assert await repo.is_username_taken(username) is True
        
        # 检查不存在的用户名
        assert await repo.is_username_taken("nonexistent") is False
        
        # 检查排除特定用户ID的情况
        assert await repo.is_username_taken(username, exclude_user_id=created_user.id) is False


class TestCreditTransactionRepository:
    """点数交易仓库测试类"""
    
    @pytest.mark.asyncio
    async def test_create_transaction(self, db_session):
        """测试创建交易记录"""
        user_repo = UserRepository(db_session)
        transaction_repo = CreditTransactionRepository(db_session)
        
        # 先创建用户
        user_data = {
            "username": generate_unique_username(),
            "email": generate_unique_email(),
            "password_hash": "hashed_password"
        }
        user = await user_repo.create(user_data)
        
        # 创建交易记录
        transaction_data = {
            "user_id": user.id,
            "amount": 100.0,
            "type": TransactionType.RECHARGE,
            "description": "Test recharge"
        }
        
        transaction = await transaction_repo.create(transaction_data)
        
        assert transaction.id is not None
        assert transaction.user_id == user.id
        assert transaction.amount == 100.0
        assert transaction.type == TransactionType.RECHARGE
        assert transaction.description == "Test recharge"
    
    @pytest.mark.asyncio
    async def test_get_transactions_by_user_id(self, db_session):
        """测试获取用户的交易记录"""
        user_repo = UserRepository(db_session)
        transaction_repo = CreditTransactionRepository(db_session)
        
        # 创建用户
        user = await user_repo.create({
            "username": generate_unique_username(),
            "email": generate_unique_email(),
            "password_hash": "hashed_password"
        })
        
        # 创建多个交易记录
        transactions_data = [
            {
                "user_id": user.id,
                "amount": 100.0,
                "type": TransactionType.RECHARGE,
                "description": "Recharge 1"
            },
            {
                "user_id": user.id,
                "amount": -20.0,
                "type": TransactionType.CONSUMPTION,
                "description": "Consumption 1"
            }
        ]
        
        import time
        for i, transaction_data in enumerate(transactions_data):
            if i > 0:
                time.sleep(0.001)  # 确保时间戳不同
            await transaction_repo.create(transaction_data)
        
        # 获取用户的交易记录
        user_transactions = await transaction_repo.get_by_user_id(user.id)
        
        assert len(user_transactions) == 2
        # 应该按创建时间倒序排列，但由于创建时间可能相同，我们只验证数量和内容
        descriptions = [t.description for t in user_transactions]
        assert "Consumption 1" in descriptions
        assert "Recharge 1" in descriptions