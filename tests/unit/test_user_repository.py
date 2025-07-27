"""用户仓库测试"""

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
        
        user_data = {
            "username": "testuser",
            "email": "test@example.com",
            "password_hash": "hashed_password"
        }
        created_user = await repo.create(user_data)
        
        found_user = await repo.get_by_username("testuser")
        
        assert found_user is not None
        assert found_user.id == created_user.id
        assert found_user.username == "testuser"
    
    @pytest.mark.asyncio
    async def test_get_user_by_email(self, db_session):
        """测试根据邮箱获取用户"""
        repo = UserRepository(db_session)
        
        user_data = {
            "username": "testuser",
            "email": "test@example.com",
            "password_hash": "hashed_password"
        }
        created_user = await repo.create(user_data)
        
        found_user = await repo.get_by_email("test@example.com")
        
        assert found_user is not None
        assert found_user.id == created_user.id
        assert found_user.email == "test@example.com"
    
    @pytest.mark.asyncio
    async def test_get_user_by_api_key(self, db_session):
        """测试根据API密钥获取用户"""
        repo = UserRepository(db_session)
        
        user_data = {
            "username": "testuser",
            "email": "test@example.com",
            "password_hash": "hashed_password",
            "api_key": "test_api_key_123"
        }
        created_user = await repo.create(user_data)
        
        found_user = await repo.get_by_api_key("test_api_key_123")
        
        assert found_user is not None
        assert found_user.id == created_user.id
        assert found_user.api_key == "test_api_key_123"
    
    @pytest.mark.asyncio
    async def test_update_user(self, db_session):
        """测试更新用户"""
        repo = UserRepository(db_session)
        
        user_data = {
            "username": "testuser",
            "email": "test@example.com",
            "password_hash": "hashed_password",
            "credits": 100.0
        }
        created_user = await repo.create(user_data)
        original_updated_at = created_user.updated_at
        
        # 更新用户
        update_data = {
            "company_name": "Updated Company",
            "credits": 200.0
        }
        updated_user = await repo.update(created_user.id, update_data)
        
        assert updated_user is not None
        assert updated_user.company_name == "Updated Company"
        assert updated_user.credits == 200.0
        assert updated_user.updated_at > original_updated_at
    
    @pytest.mark.asyncio
    async def test_delete_user(self, db_session):
        """测试删除用户"""
        repo = UserRepository(db_session)
        
        user_data = {
            "username": "testuser",
            "email": "test@example.com",
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
    async def test_search_users(self, db_session):
        """测试搜索用户"""
        repo = UserRepository(db_session)
        
        # 创建多个用户
        users_data = [
            {
                "username": "alice",
                "email": "alice@example.com",
                "password_hash": "hash1",
                "company_name": "Alice Corp"
            },
            {
                "username": "bob",
                "email": "bob@test.com",
                "password_hash": "hash2",
                "company_name": "Bob Inc"
            },
            {
                "username": "charlie",
                "email": "charlie@example.com",
                "password_hash": "hash3",
                "company_name": "Charlie LLC"
            }
        ]
        
        for user_data in users_data:
            await repo.create(user_data)
        
        # 搜索用户
        results = await repo.search("alice")
        assert len(results) == 1
        assert results[0].username == "alice"
        
        results = await repo.search("example.com")
        assert len(results) == 2
        
        results = await repo.search("Corp")
        assert len(results) == 1
        assert results[0].company_name == "Alice Corp"
    
    @pytest.mark.asyncio
    async def test_count_users(self, db_session):
        """测试用户计数"""
        repo = UserRepository(db_session)
        
        initial_count = await repo.count()
        
        # 创建用户
        user_data = {
            "username": "testuser",
            "email": "test@example.com",
            "password_hash": "hashed_password"
        }
        await repo.create(user_data)
        
        new_count = await repo.count()
        assert new_count == initial_count + 1
    
    @pytest.mark.asyncio
    async def test_is_username_taken(self, db_session):
        """测试用户名是否已被使用"""
        repo = UserRepository(db_session)
        
        user_data = {
            "username": "testuser",
            "email": "test@example.com",
            "password_hash": "hashed_password"
        }
        created_user = await repo.create(user_data)
        
        # 检查已存在的用户名
        assert await repo.is_username_taken("testuser") is True
        
        # 检查不存在的用户名
        assert await repo.is_username_taken("nonexistent") is False
        
        # 检查排除特定用户ID的情况
        assert await repo.is_username_taken("testuser", exclude_user_id=created_user.id) is False
    
    @pytest.mark.asyncio
    async def test_is_email_taken(self, db_session):
        """测试邮箱是否已被使用"""
        repo = UserRepository(db_session)
        
        user_data = {
            "username": "testuser",
            "email": "test@example.com",
            "password_hash": "hashed_password"
        }
        created_user = await repo.create(user_data)
        
        # 检查已存在的邮箱
        assert await repo.is_email_taken("test@example.com") is True
        
        # 检查不存在的邮箱
        assert await repo.is_email_taken("nonexistent@example.com") is False
        
        # 检查排除特定用户ID的情况
        assert await repo.is_email_taken("test@example.com", exclude_user_id=created_user.id) is False
    
    @pytest.mark.asyncio
    async def test_update_last_login(self, db_session):
        """测试更新最后登录时间"""
        repo = UserRepository(db_session)
        
        user_data = {
            "username": "testuser",
            "email": "test@example.com",
            "password_hash": "hashed_password"
        }
        created_user = await repo.create(user_data)
        
        original_login_time = created_user.last_login
        
        # 更新最后登录时间
        result = await repo.update_last_login(created_user.id)
        assert result is True
        
        # 验证时间已更新
        updated_user = await repo.get_by_id(created_user.id)
        assert updated_user.last_login is not None
        assert updated_user.last_login != original_login_time
    
    @pytest.mark.asyncio
    async def test_get_users_with_low_credits(self, db_session):
        """测试获取点数不足的用户"""
        repo = UserRepository(db_session)
        
        # 创建不同点数的用户
        users_data = [
            {
                "username": "rich_user",
                "email": "rich@example.com",
                "password_hash": "hash1",
                "credits": 100.0
            },
            {
                "username": "poor_user",
                "email": "poor@example.com",
                "password_hash": "hash2",
                "credits": 5.0
            },
            {
                "username": "broke_user",
                "email": "broke@example.com",
                "password_hash": "hash3",
                "credits": 0.0
            }
        ]
        
        for user_data in users_data:
            await repo.create(user_data)
        
        # 获取点数不足的用户（默认阈值10.0）
        low_credit_users = await repo.get_users_with_low_credits()
        
        assert len(low_credit_users) == 2
        usernames = [user.username for user in low_credit_users]
        assert "poor_user" in usernames
        assert "broke_user" in usernames
        assert "rich_user" not in usernames


class TestCreditTransactionRepository:
    """点数交易仓库测试类"""
    
    @pytest.mark.asyncio
    async def test_create_transaction(self, db_session):
        """测试创建交易记录"""
        user_repo = UserRepository(db_session)
        transaction_repo = CreditTransactionRepository(db_session)
        
        # 先创建用户
        user_data = {
            "username": "testuser",
            "email": "test@example.com",
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
    async def test_get_transaction_by_id(self, db_session):
        """测试根据ID获取交易记录"""
        user_repo = UserRepository(db_session)
        transaction_repo = CreditTransactionRepository(db_session)
        
        # 创建用户和交易
        user = await user_repo.create({
            "username": "testuser",
            "email": "test@example.com",
            "password_hash": "hashed_password"
        })
        
        transaction_data = {
            "user_id": user.id,
            "amount": 50.0,
            "type": TransactionType.CONSUMPTION,
            "description": "Test consumption"
        }
        created_transaction = await transaction_repo.create(transaction_data)
        
        # 获取交易记录
        found_transaction = await transaction_repo.get_by_id(created_transaction.id)
        
        assert found_transaction is not None
        assert found_transaction.id == created_transaction.id
        assert found_transaction.amount == 50.0
        assert found_transaction.type == TransactionType.CONSUMPTION
    
    @pytest.mark.asyncio
    async def test_get_transactions_by_user_id(self, db_session):
        """测试获取用户的交易记录"""
        user_repo = UserRepository(db_session)
        transaction_repo = CreditTransactionRepository(db_session)
        
        # 创建用户
        user = await user_repo.create({
            "username": "testuser",
            "email": "test@example.com",
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
            },
            {
                "user_id": user.id,
                "amount": 50.0,
                "type": TransactionType.VOUCHER,
                "description": "Voucher 1"
            }
        ]
        
        for transaction_data in transactions_data:
            await transaction_repo.create(transaction_data)
        
        # 获取用户的交易记录
        user_transactions = await transaction_repo.get_by_user_id(user.id)
        
        assert len(user_transactions) == 3
        # 检查所有交易记录都存在
        descriptions = [t.description for t in user_transactions]
        assert "Voucher 1" in descriptions
        assert "Consumption 1" in descriptions
        assert "Recharge 1" in descriptions
    
    @pytest.mark.asyncio
    async def test_get_transactions_by_type(self, db_session):
        """测试根据交易类型获取记录"""
        user_repo = UserRepository(db_session)
        transaction_repo = CreditTransactionRepository(db_session)
        
        # 创建用户
        user = await user_repo.create({
            "username": "testuser",
            "email": "test@example.com",
            "password_hash": "hashed_password"
        })
        
        # 创建不同类型的交易记录
        transactions_data = [
            {
                "user_id": user.id,
                "amount": 100.0,
                "type": TransactionType.RECHARGE,
                "description": "Recharge 1"
            },
            {
                "user_id": user.id,
                "amount": 200.0,
                "type": TransactionType.RECHARGE,
                "description": "Recharge 2"
            },
            {
                "user_id": user.id,
                "amount": -20.0,
                "type": TransactionType.CONSUMPTION,
                "description": "Consumption 1"
            }
        ]
        
        for transaction_data in transactions_data:
            await transaction_repo.create(transaction_data)
        
        # 获取充值类型的交易记录
        recharge_transactions = await transaction_repo.get_by_type(TransactionType.RECHARGE)
        
        assert len(recharge_transactions) == 2
        for transaction in recharge_transactions:
            assert transaction.type == TransactionType.RECHARGE
    
    @pytest.mark.asyncio
    async def test_get_user_total_spent(self, db_session):
        """测试获取用户总消费"""
        user_repo = UserRepository(db_session)
        transaction_repo = CreditTransactionRepository(db_session)
        
        # 创建用户
        user = await user_repo.create({
            "username": "testuser",
            "email": "test@example.com",
            "password_hash": "hashed_password"
        })
        
        # 创建消费记录
        transactions_data = [
            {
                "user_id": user.id,
                "amount": -20.0,
                "type": TransactionType.CONSUMPTION,
                "description": "Consumption 1"
            },
            {
                "user_id": user.id,
                "amount": -30.0,
                "type": TransactionType.CONSUMPTION,
                "description": "Consumption 2"
            },
            {
                "user_id": user.id,
                "amount": 100.0,
                "type": TransactionType.RECHARGE,
                "description": "Recharge 1"
            }
        ]
        
        for transaction_data in transactions_data:
            await transaction_repo.create(transaction_data)
        
        # 获取总消费
        total_spent = await transaction_repo.get_user_total_spent(user.id)
        
        assert total_spent == 50.0  # 20 + 30
    
    @pytest.mark.asyncio
    async def test_get_user_total_recharged(self, db_session):
        """测试获取用户总充值"""
        user_repo = UserRepository(db_session)
        transaction_repo = CreditTransactionRepository(db_session)
        
        # 创建用户
        user = await user_repo.create({
            "username": "testuser",
            "email": "test@example.com",
            "password_hash": "hashed_password"
        })
        
        # 创建充值记录
        transactions_data = [
            {
                "user_id": user.id,
                "amount": 100.0,
                "type": TransactionType.RECHARGE,
                "description": "Recharge 1"
            },
            {
                "user_id": user.id,
                "amount": 50.0,
                "type": TransactionType.VOUCHER,
                "description": "Voucher 1"
            },
            {
                "user_id": user.id,
                "amount": -20.0,
                "type": TransactionType.CONSUMPTION,
                "description": "Consumption 1"
            }
        ]
        
        for transaction_data in transactions_data:
            await transaction_repo.create(transaction_data)
        
        # 获取总充值
        total_recharged = await transaction_repo.get_user_total_recharged(user.id)
        
        assert total_recharged == 150.0  # 100 + 50