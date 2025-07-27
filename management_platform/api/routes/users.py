"""用户管理API路由"""

from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, status, Query
from pydantic import BaseModel
import uuid

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', '..'))

from shared.models.user import (
    User, UserCreate, UserUpdate, UserResponse, PasswordChange,
    CreditRecharge, CreditTransactionResponse, ApiKeyResponse,
    TransactionType, UserRole, UserStatus
)
from management_platform.database.repositories import UserRepository, CreditTransactionRepository
from ..dependencies import get_db_session, get_current_user, require_admin

router = APIRouter()


class UserListResponse(BaseModel):
    """用户列表响应模型"""
    users: List[UserResponse]
    total: int
    page: int
    size: int


class CreditTransactionListResponse(BaseModel):
    """点数交易列表响应模型"""
    transactions: List[CreditTransactionResponse]
    total: int
    page: int
    size: int


@router.post("/", response_model=UserResponse, summary="注册新用户")
async def create_user(
    user_data: UserCreate,
    session = Depends(get_db_session)
):
    """
    注册新用户
    
    - **username**: 用户名（3-50字符）
    - **email**: 邮箱地址
    - **password**: 密码（至少8位，包含大小写字母和数字）
    - **company_name**: 公司名称（可选）
    - **role**: 用户角色（默认为enterprise）
    """
    user_repo = UserRepository(session)
    
    # 检查用户名是否已存在
    if await user_repo.is_username_taken(user_data.username):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="用户名已存在"
        )
    
    # 检查邮箱是否已存在
    if await user_repo.is_email_taken(user_data.email):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="邮箱已存在"
        )
    
    # 创建用户
    user = User(
        username=user_data.username,
        email=user_data.email,
        company_name=user_data.company_name,
        role=user_data.role,
        status=UserStatus.ACTIVE
    )
    user.set_password(user_data.password)
    
    created_user = await user_repo.create({
        "username": user.username,
        "email": user.email,
        "password_hash": user.password_hash,
        "company_name": user.company_name,
        "role": user.role,
        "status": user.status,
        "credits": 0.0
    })
    
    await user_repo.commit()
    
    return UserResponse(
        id=created_user.id,
        username=created_user.username,
        email=created_user.email,
        company_name=created_user.company_name,
        role=created_user.role,
        credits=created_user.credits,
        last_login=created_user.last_login,
        status=created_user.status,
        has_api_key=bool(created_user.api_key_hash),
        created_at=created_user.created_at,
        updated_at=created_user.updated_at
    )


@router.get("/", response_model=UserListResponse, summary="获取用户列表")
async def get_users(
    page: int = Query(1, ge=1, description="页码"),
    size: int = Query(20, ge=1, le=100, description="每页数量"),
    search: Optional[str] = Query(None, description="搜索关键词"),
    current_user: User = Depends(require_admin),
    session = Depends(get_db_session)
):
    """
    获取用户列表（仅管理员）
    
    - **page**: 页码（从1开始）
    - **size**: 每页数量（1-100）
    - **search**: 搜索关键词（可选，搜索用户名、邮箱、公司名）
    """
    user_repo = UserRepository(session)
    
    skip = (page - 1) * size
    
    if search:
        users = await user_repo.search(search, skip=skip, limit=size)
    else:
        users = await user_repo.get_all(skip=skip, limit=size)
    
    total = await user_repo.count()
    
    user_responses = [
        UserResponse(
            id=user.id,
            username=user.username,
            email=user.email,
            company_name=user.company_name,
            role=user.role,
            credits=user.credits,
            last_login=user.last_login,
            status=user.status,
            has_api_key=bool(user.api_key_hash),
            created_at=user.created_at,
            updated_at=user.updated_at
        )
        for user in users
    ]
    
    return UserListResponse(
        users=user_responses,
        total=total,
        page=page,
        size=size
    )


@router.get("/{user_id}", response_model=UserResponse, summary="获取用户详情")
async def get_user(
    user_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    session = Depends(get_db_session)
):
    """
    获取用户详情
    
    - 普通用户只能查看自己的信息
    - 管理员可以查看任何用户的信息
    """
    user_repo = UserRepository(session)
    
    # 检查权限
    if current_user.role != UserRole.ADMIN and current_user.id != user_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="无权访问其他用户信息"
        )
    
    user = await user_repo.get_by_id(user_id)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="用户不存在"
        )
    
    return UserResponse(
        id=user.id,
        username=user.username,
        email=user.email,
        company_name=user.company_name,
        role=user.role,
        credits=user.credits,
        last_login=user.last_login,
        status=user.status,
        has_api_key=bool(user.api_key_hash),
        created_at=user.created_at,
        updated_at=user.updated_at
    )


@router.put("/{user_id}", response_model=UserResponse, summary="更新用户信息")
async def update_user(
    user_id: uuid.UUID,
    user_data: UserUpdate,
    current_user: User = Depends(get_current_user),
    session = Depends(get_db_session)
):
    """
    更新用户信息
    
    - 普通用户只能更新自己的信息
    - 管理员可以更新任何用户的信息
    """
    user_repo = UserRepository(session)
    
    # 检查权限
    if current_user.role != UserRole.ADMIN and current_user.id != user_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="无权修改其他用户信息"
        )
    
    user = await user_repo.get_by_id(user_id)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="用户不存在"
        )
    
    # 准备更新数据
    update_data = {}
    
    if user_data.username is not None:
        if await user_repo.is_username_taken(user_data.username, exclude_user_id=user_id):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="用户名已存在"
            )
        update_data["username"] = user_data.username
    
    if user_data.email is not None:
        if await user_repo.is_email_taken(user_data.email, exclude_user_id=user_id):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="邮箱已存在"
            )
        update_data["email"] = user_data.email
    
    if user_data.company_name is not None:
        update_data["company_name"] = user_data.company_name
    
    if user_data.password is not None:
        temp_user = User()
        temp_user.set_password(user_data.password)
        update_data["password_hash"] = temp_user.password_hash
    
    if update_data:
        updated_user = await user_repo.update(user_id, update_data)
        await user_repo.commit()
        
        return UserResponse(
            id=updated_user.id,
            username=updated_user.username,
            email=updated_user.email,
            company_name=updated_user.company_name,
            role=updated_user.role,
            credits=updated_user.credits,
            last_login=updated_user.last_login,
            status=updated_user.status,
            has_api_key=bool(updated_user.api_key_hash),
            created_at=updated_user.created_at,
            updated_at=updated_user.updated_at
        )
    
    return UserResponse(
        id=user.id,
        username=user.username,
        email=user.email,
        company_name=user.company_name,
        role=user.role,
        credits=user.credits,
        last_login=user.last_login,
        status=user.status,
        has_api_key=bool(user.api_key_hash),
        created_at=user.created_at,
        updated_at=user.updated_at
    )


@router.delete("/{user_id}", summary="删除用户")
async def delete_user(
    user_id: uuid.UUID,
    current_user: User = Depends(require_admin),
    session = Depends(get_db_session)
):
    """
    删除用户（仅管理员）
    """
    user_repo = UserRepository(session)
    
    user = await user_repo.get_by_id(user_id)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="用户不存在"
        )
    
    # 不能删除自己
    if user_id == current_user.id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="不能删除自己的账户"
        )
    
    await user_repo.delete(user_id)
    await user_repo.commit()
    
    return {"message": "用户删除成功"}


@router.post("/{user_id}/change-password", summary="修改密码")
async def change_password(
    user_id: uuid.UUID,
    password_data: PasswordChange,
    current_user: User = Depends(get_current_user),
    session = Depends(get_db_session)
):
    """
    修改用户密码
    
    - 普通用户只能修改自己的密码
    - 管理员可以修改任何用户的密码（无需提供旧密码）
    """
    user_repo = UserRepository(session)
    
    # 检查权限
    if current_user.role != UserRole.ADMIN and current_user.id != user_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="无权修改其他用户密码"
        )
    
    user = await user_repo.get_by_id(user_id)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="用户不存在"
        )
    
    # 非管理员需要验证旧密码
    if current_user.role != UserRole.ADMIN:
        if not user.verify_password(password_data.old_password):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="旧密码错误"
            )
    
    # 更新密码
    temp_user = User()
    temp_user.set_password(password_data.new_password)
    
    await user_repo.update(user_id, {"password_hash": temp_user.password_hash})
    await user_repo.commit()
    
    return {"message": "密码修改成功"}


@router.post("/{user_id}/recharge", response_model=CreditTransactionResponse, summary="账户充值")
async def recharge_credits(
    user_id: uuid.UUID,
    recharge_data: CreditRecharge,
    current_user: User = Depends(get_current_user),
    session = Depends(get_db_session)
):
    """
    账户充值
    
    - 普通用户只能为自己充值
    - 管理员可以为任何用户充值
    """
    user_repo = UserRepository(session)
    transaction_repo = CreditTransactionRepository(session)
    
    # 检查权限
    if current_user.role != UserRole.ADMIN and current_user.id != user_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="无权为其他用户充值"
        )
    
    user = await user_repo.get_by_id(user_id)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="用户不存在"
        )
    
    # 创建充值交易记录
    transaction = await transaction_repo.create({
        "user_id": user_id,
        "amount": recharge_data.amount,
        "type": TransactionType.RECHARGE,
        "description": recharge_data.description or f"充值 - {recharge_data.payment_method}",
        "reference_id": f"recharge_{uuid.uuid4().hex[:8]}"
    })
    
    # 更新用户余额
    await user_repo.update(user_id, {"credits": user.credits + recharge_data.amount})
    await user_repo.commit()
    
    return CreditTransactionResponse(
        id=transaction.id,
        user_id=transaction.user_id,
        amount=transaction.amount,
        type=transaction.type,
        description=transaction.description,
        reference_id=transaction.reference_id,
        created_at=transaction.created_at,
        updated_at=transaction.updated_at
    )


@router.post("/{user_id}/voucher", response_model=CreditTransactionResponse, summary="添加抵用券")
async def add_voucher(
    user_id: uuid.UUID,
    amount: float,
    description: str = "管理员添加抵用券",
    current_user: User = Depends(require_admin),
    session = Depends(get_db_session)
):
    """
    为用户添加抵用券（仅管理员）
    """
    user_repo = UserRepository(session)
    transaction_repo = CreditTransactionRepository(session)
    
    user = await user_repo.get_by_id(user_id)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="用户不存在"
        )
    
    if amount <= 0:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="抵用券金额必须大于0"
        )
    
    # 创建抵用券交易记录
    transaction = await transaction_repo.create({
        "user_id": user_id,
        "amount": amount,
        "type": TransactionType.VOUCHER,
        "description": description,
        "reference_id": f"voucher_{uuid.uuid4().hex[:8]}"
    })
    
    # 更新用户余额
    await user_repo.update(user_id, {"credits": user.credits + amount})
    await user_repo.commit()
    
    return CreditTransactionResponse(
        id=transaction.id,
        user_id=transaction.user_id,
        amount=transaction.amount,
        type=transaction.type,
        description=transaction.description,
        reference_id=transaction.reference_id,
        created_at=transaction.created_at,
        updated_at=transaction.updated_at
    )


@router.get("/{user_id}/transactions", response_model=CreditTransactionListResponse, summary="获取交易记录")
async def get_user_transactions(
    user_id: uuid.UUID,
    page: int = Query(1, ge=1, description="页码"),
    size: int = Query(20, ge=1, le=100, description="每页数量"),
    current_user: User = Depends(get_current_user),
    session = Depends(get_db_session)
):
    """
    获取用户的点数交易记录
    
    - 普通用户只能查看自己的交易记录
    - 管理员可以查看任何用户的交易记录
    """
    transaction_repo = CreditTransactionRepository(session)
    
    # 检查权限
    if current_user.role != UserRole.ADMIN and current_user.id != user_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="无权查看其他用户的交易记录"
        )
    
    skip = (page - 1) * size
    transactions = await transaction_repo.get_by_user_id(user_id, skip=skip, limit=size)
    
    # 简单计算总数（实际应该有专门的count方法）
    all_transactions = await transaction_repo.get_by_user_id(user_id, skip=0, limit=10000)
    total = len(all_transactions)
    
    transaction_responses = [
        CreditTransactionResponse(
            id=transaction.id,
            user_id=transaction.user_id,
            amount=transaction.amount,
            type=transaction.type,
            description=transaction.description,
            reference_id=transaction.reference_id,
            created_at=transaction.created_at,
            updated_at=transaction.updated_at
        )
        for transaction in transactions
    ]
    
    return CreditTransactionListResponse(
        transactions=transaction_responses,
        total=total,
        page=page,
        size=size
    )


@router.post("/{user_id}/api-key", response_model=ApiKeyResponse, summary="生成API密钥")
async def generate_api_key(
    user_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    session = Depends(get_db_session)
):
    """
    为用户生成API密钥
    
    - 普通用户只能为自己生成API密钥
    - 管理员可以为任何用户生成API密钥
    """
    user_repo = UserRepository(session)
    
    # 检查权限
    if current_user.role != UserRole.ADMIN and current_user.id != user_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="无权为其他用户生成API密钥"
        )
    
    user = await user_repo.get_by_id(user_id)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="用户不存在"
        )
    
    # 生成新的API密钥
    api_key = user.generate_api_key()
    
    # 更新数据库
    await user_repo.update(user_id, {
        "api_key_hash": user.api_key_hash,
        "api_key_created_at": user.api_key_created_at
    })
    await user_repo.commit()
    
    return ApiKeyResponse(
        api_key=api_key,
        created_at=user.api_key_created_at
    )


@router.delete("/{user_id}/api-key", summary="删除API密钥")
async def revoke_api_key(
    user_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    session = Depends(get_db_session)
):
    """
    撤销用户的API密钥
    
    - 普通用户只能撤销自己的API密钥
    - 管理员可以撤销任何用户的API密钥
    """
    user_repo = UserRepository(session)
    
    # 检查权限
    if current_user.role != UserRole.ADMIN and current_user.id != user_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="无权撤销其他用户的API密钥"
        )
    
    user = await user_repo.get_by_id(user_id)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="用户不存在"
        )
    
    if not user.api_key_hash:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="用户没有API密钥"
        )
    
    # 删除API密钥
    await user_repo.update(user_id, {
        "api_key_hash": None,
        "api_key_created_at": None
    })
    await user_repo.commit()
    
    return {"message": "API密钥已撤销"}