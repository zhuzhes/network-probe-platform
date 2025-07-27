"""用户相关数据模型"""

import uuid
from datetime import datetime
from enum import Enum
from typing import Optional, List
from sqlalchemy import (
    Column, String, Float, DateTime, Enum as SQLEnum,
    ForeignKey, Text, Boolean
)
from sqlalchemy.orm import relationship
from pydantic import BaseModel, EmailStr, Field, field_validator
from passlib.context import CryptContext

from .base import BaseModel as DBBaseModel, BaseSchema, GUID


# 密码加密上下文
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


class UserRole(str, Enum):
    """用户角色枚举"""
    ADMIN = "admin"
    ENTERPRISE = "enterprise"


class UserStatus(str, Enum):
    """用户状态枚举"""
    ACTIVE = "active"
    INACTIVE = "inactive"
    SUSPENDED = "suspended"


class TransactionType(str, Enum):
    """交易类型枚举"""
    RECHARGE = "recharge"
    CONSUMPTION = "consumption"
    REFUND = "refund"
    VOUCHER = "voucher"


class User(DBBaseModel):
    """用户模型"""
    
    __tablename__ = "users"
    
    username = Column(String(50), unique=True, nullable=False, index=True)
    email = Column(String(255), unique=True, nullable=False, index=True)
    password_hash = Column(String(255), nullable=False)
    company_name = Column(String(255), nullable=True)
    role = Column(SQLEnum(UserRole), nullable=False, default=UserRole.ENTERPRISE)
    credits = Column(Float, nullable=False, default=0.0)
    last_login = Column(DateTime(timezone=True), nullable=True)
    status = Column(SQLEnum(UserStatus), nullable=False, default=UserStatus.ACTIVE)
    
    # API密钥相关
    api_key_hash = Column(String(255), unique=True, nullable=True, index=True)
    api_key_created_at = Column(DateTime(timezone=True), nullable=True)
    
    # 关联关系
    credit_transactions = relationship(
        "CreditTransaction", 
        back_populates="user",
        cascade="all, delete-orphan"
    )
    # tasks = relationship(
    #     "Task",
    #     back_populates="user",
    #     cascade="all, delete-orphan"
    # )
    
    def set_password(self, password: str) -> None:
        """设置密码"""
        self.password_hash = pwd_context.hash(password)
    
    def verify_password(self, password: str) -> bool:
        """验证密码"""
        return pwd_context.verify(password, self.password_hash)
    
    def generate_api_key(self) -> str:
        """生成API密钥"""
        import secrets
        import hashlib
        
        # 生成API密钥
        api_key = f"npk_{secrets.token_hex(32)}"
        
        # 存储哈希值
        self.api_key_hash = hashlib.sha256(api_key.encode()).hexdigest()
        self.api_key_created_at = datetime.utcnow()
        
        return api_key
    
    def can_consume_credits(self, amount: float) -> bool:
        """检查是否有足够的点数"""
        return self.credits >= amount
    
    def consume_credits(self, amount: float, description: str = "") -> bool:
        """消费点数"""
        if not self.can_consume_credits(amount):
            return False
        
        self.credits -= amount
        
        # 创建交易记录
        transaction = CreditTransaction(
            user_id=self.id,
            amount=-amount,
            type=TransactionType.CONSUMPTION,
            description=description
        )
        self.credit_transactions.append(transaction)
        
        return True
    
    def add_credits(self, amount: float, transaction_type: TransactionType, 
                   description: str = "", reference_id: str = None) -> None:
        """增加点数"""
        self.credits += amount
        
        # 创建交易记录
        transaction = CreditTransaction(
            user_id=self.id,
            amount=amount,
            type=transaction_type,
            description=description,
            reference_id=reference_id
        )
        self.credit_transactions.append(transaction)


class CreditTransaction(DBBaseModel):
    """点数交易记录模型"""
    
    __tablename__ = "credit_transactions"
    
    user_id = Column(GUID(), ForeignKey("users.id"), nullable=False)
    amount = Column(Float, nullable=False)
    type = Column(SQLEnum(TransactionType), nullable=False)
    description = Column(Text, nullable=True)
    reference_id = Column(String(255), nullable=True)  # 关联的任务ID或订单ID
    
    # 关联关系
    user = relationship("User", back_populates="credit_transactions")


# Pydantic模型用于API序列化

class UserBase(BaseModel):
    """用户基础模型"""
    username: str = Field(..., min_length=3, max_length=50)
    email: EmailStr
    company_name: Optional[str] = Field(None, max_length=255)
    role: UserRole = UserRole.ENTERPRISE


class UserCreate(UserBase):
    """用户创建模型"""
    password: str = Field(..., min_length=8, max_length=128)
    
    @field_validator('password')
    @classmethod
    def validate_password(cls, v):
        """密码验证"""
        if len(v) < 8:
            raise ValueError('密码长度至少8位')
        if not any(c.isupper() for c in v):
            raise ValueError('密码必须包含至少一个大写字母')
        if not any(c.islower() for c in v):
            raise ValueError('密码必须包含至少一个小写字母')
        if not any(c.isdigit() for c in v):
            raise ValueError('密码必须包含至少一个数字')
        return v


class UserUpdate(BaseModel):
    """用户更新模型"""
    username: Optional[str] = Field(None, min_length=3, max_length=50)
    email: Optional[EmailStr] = None
    company_name: Optional[str] = Field(None, max_length=255)
    password: Optional[str] = Field(None, min_length=8, max_length=128)
    
    @field_validator('password')
    @classmethod
    def validate_password(cls, v):
        """密码验证"""
        if v is None:
            return v
        if len(v) < 8:
            raise ValueError('密码长度至少8位')
        return v


class UserResponse(BaseSchema):
    """用户响应模型"""
    username: str
    email: str
    company_name: Optional[str]
    role: UserRole
    credits: float
    last_login: Optional[datetime]
    status: UserStatus
    has_api_key: bool = False


class UserLogin(BaseModel):
    """用户登录模型"""
    username: str
    password: str


class PasswordChange(BaseModel):
    """密码修改模型"""
    old_password: str
    new_password: str = Field(..., min_length=8, max_length=128)
    
    @field_validator('new_password')
    @classmethod
    def validate_new_password(cls, v):
        """新密码验证"""
        if len(v) < 8:
            raise ValueError('密码长度至少8位')
        return v


class CreditRecharge(BaseModel):
    """点数充值模型"""
    amount: float = Field(..., gt=0, description="充值金额")
    payment_method: str = Field(..., description="支付方式")
    description: Optional[str] = Field(None, description="充值说明")


class CreditTransactionResponse(BaseSchema):
    """点数交易响应模型"""
    user_id: uuid.UUID
    amount: float
    type: TransactionType
    description: Optional[str]
    reference_id: Optional[str]


class ApiKeyResponse(BaseModel):
    """API密钥响应模型"""
    api_key: str
    created_at: datetime