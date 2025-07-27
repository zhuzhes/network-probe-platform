"""用户模型单元测试"""

import pytest
from datetime import datetime
from shared.models.user import (
    User, CreditTransaction, UserRole, UserStatus, TransactionType
)


class TestUser:
    """用户模型测试"""
    
    def test_create_user(self):
        """测试创建用户"""
        user = User(
            username="testuser",
            email="test@example.com",
            company_name="Test Company",
            role=UserRole.ENTERPRISE,
            credits=0.0,
            status=UserStatus.ACTIVE
        )
        
        assert user.username == "testuser"
        assert user.email == "test@example.com"
        assert user.company_name == "Test Company"
        assert user.role == UserRole.ENTERPRISE
        assert user.credits == 0.0
        assert user.status == UserStatus.ACTIVE
    
    def test_set_password(self):
        """测试设置密码"""
        user = User(username="testuser", email="test@example.com")
        password = "TestPassword123"
        
        user.set_password(password)
        
        assert user.password_hash is not None
        assert user.password_hash != password
        assert user.verify_password(password) is True
        assert user.verify_password("wrongpassword") is False
    
    def test_generate_api_key(self):
        """测试生成API密钥"""
        user = User(username="testuser", email="test@example.com")
        
        api_key = user.generate_api_key()
        
        assert api_key is not None
        assert api_key.startswith("npk_")
        assert user.api_key == api_key
        assert user.api_key_created_at is not None
    
    def test_can_consume_credits(self):
        """测试检查点数是否足够"""
        user = User(username="testuser", email="test@example.com")
        user.credits = 100.0
        
        assert user.can_consume_credits(50.0) is True
        assert user.can_consume_credits(100.0) is True
        assert user.can_consume_credits(150.0) is False
    
    def test_consume_credits_success(self):
        """测试成功消费点数"""
        user = User(username="testuser", email="test@example.com")
        user.credits = 100.0
        
        result = user.consume_credits(30.0, "Test consumption")
        
        assert result is True
        assert user.credits == 70.0
        assert len(user.credit_transactions) == 1
        
        transaction = user.credit_transactions[0]
        assert transaction.amount == -30.0
        assert transaction.type == TransactionType.CONSUMPTION
        assert transaction.description == "Test consumption"
    
    def test_consume_credits_insufficient(self):
        """测试点数不足时消费失败"""
        user = User(username="testuser", email="test@example.com")
        user.credits = 50.0
        
        result = user.consume_credits(100.0, "Test consumption")
        
        assert result is False
        assert user.credits == 50.0
        assert len(user.credit_transactions) == 0
    
    def test_add_credits(self):
        """测试增加点数"""
        user = User(username="testuser", email="test@example.com")
        user.credits = 50.0
        
        user.add_credits(
            100.0, 
            TransactionType.RECHARGE, 
            "Test recharge",
            "order_123"
        )
        
        assert user.credits == 150.0
        assert len(user.credit_transactions) == 1
        
        transaction = user.credit_transactions[0]
        assert transaction.amount == 100.0
        assert transaction.type == TransactionType.RECHARGE
        assert transaction.description == "Test recharge"
        assert transaction.reference_id == "order_123"


class TestCreditTransaction:
    """点数交易测试"""
    
    def test_create_transaction(self):
        """测试创建交易记录"""
        import uuid
        user_id = uuid.uuid4()
        
        transaction = CreditTransaction(
            user_id=user_id,
            amount=100.0,
            type=TransactionType.RECHARGE,
            description="Test recharge",
            reference_id="order_123"
        )
        
        assert transaction.user_id == user_id
        assert transaction.amount == 100.0
        assert transaction.type == TransactionType.RECHARGE
        assert transaction.description == "Test recharge"
        assert transaction.reference_id == "order_123"


class TestUserValidation:
    """用户验证测试"""
    
    def test_user_create_validation(self):
        """测试用户创建验证"""
        from shared.models.user import UserCreate
        from pydantic import ValidationError
        
        # 有效数据
        valid_data = {
            "username": "testuser",
            "email": "test@example.com",
            "password": "TestPassword123",
            "company_name": "Test Company"
        }
        
        user = UserCreate(**valid_data)
        assert user.username == "testuser"
        assert user.email == "test@example.com"
        
        # 无效邮箱
        with pytest.raises(ValidationError):
            UserCreate(**{**valid_data, "email": "invalid-email"})
        
        # 密码太短
        with pytest.raises(ValidationError):
            UserCreate(**{**valid_data, "password": "123"})
        
        # 用户名太短
        with pytest.raises(ValidationError):
            UserCreate(**{**valid_data, "username": "ab"})
    
    def test_password_validation(self):
        """测试密码验证"""
        from shared.models.user import UserCreate
        from pydantic import ValidationError
        
        base_data = {
            "username": "testuser",
            "email": "test@example.com",
            "company_name": "Test Company"
        }
        
        # 有效密码
        UserCreate(**{**base_data, "password": "TestPassword123"})
        
        # 无大写字母
        with pytest.raises(ValidationError, match="密码必须包含至少一个大写字母"):
            UserCreate(**{**base_data, "password": "testpassword123"})
        
        # 无小写字母
        with pytest.raises(ValidationError, match="密码必须包含至少一个小写字母"):
            UserCreate(**{**base_data, "password": "TESTPASSWORD123"})
        
        # 无数字
        with pytest.raises(ValidationError, match="密码必须包含至少一个数字"):
            UserCreate(**{**base_data, "password": "TestPassword"})
    
    def test_credit_recharge_validation(self):
        """测试点数充值验证"""
        from shared.models.user import CreditRecharge
        from pydantic import ValidationError
        
        # 有效数据
        recharge = CreditRecharge(
            amount=100.0,
            payment_method="alipay",
            description="Test recharge"
        )
        assert recharge.amount == 100.0
        
        # 金额必须大于0
        with pytest.raises(ValidationError):
            CreditRecharge(amount=0, payment_method="alipay")
        
        with pytest.raises(ValidationError):
            CreditRecharge(amount=-10, payment_method="alipay")