"""认证相关API路由"""

from datetime import datetime, timedelta
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, status, Request
from pydantic import BaseModel
import uuid

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', '..'))

from shared.models.user import UserLogin, UserResponse, User, UserRole, UserStatus
from shared.security.auth import (
    create_access_token, create_refresh_token, authenticate_user,
    SecurityLogger, record_auth_attempt, check_rate_limit
)
from management_platform.database.repositories import UserRepository
from ..dependencies import get_db_session, get_current_user

router = APIRouter()

# JWT配置
ACCESS_TOKEN_EXPIRE_MINUTES = 30


class Token(BaseModel):
    """令牌响应模型"""
    access_token: str
    refresh_token: str
    token_type: str
    expires_in: int
    user: UserResponse


class RefreshTokenRequest(BaseModel):
    """刷新令牌请求模型"""
    refresh_token: str


@router.post("/login", response_model=Token, summary="用户登录")
async def login(
    user_login: UserLogin,
    request: Request,
    session = Depends(get_db_session)
):
    """
    用户登录接口
    
    - **username**: 用户名
    - **password**: 密码
    """
    client_ip = request.client.host if request.client else "unknown"
    
    try:
        # 检查速率限制
        check_rate_limit(client_ip)
        
        # 使用共享的认证函数
        user = authenticate_user(session, user_login.username, user_login.password)
        
        if not user:
            record_auth_attempt(client_ip, False)
            SecurityLogger.log_login_attempt(user_login.username, False, client_ip)
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="用户名或密码错误"
            )
        
        # 记录成功登录
        record_auth_attempt(client_ip, True)
        SecurityLogger.log_login_attempt(user.username, True, client_ip)
        
        # 创建访问令牌和刷新令牌
        access_token_expires = timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
        access_token = create_access_token(
            data={"sub": user.username, "user_id": str(user.id)}, 
            expires_delta=access_token_expires
        )
        
        refresh_token = create_refresh_token(
            data={"sub": user.username, "user_id": str(user.id)}
        )
        
        # 构建用户响应
        user_response = UserResponse(
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
        
        return Token(
            access_token=access_token,
            refresh_token=refresh_token,
            token_type="bearer",
            expires_in=ACCESS_TOKEN_EXPIRE_MINUTES * 60,
            user=user_response
        )
        
    except HTTPException:
        raise
    except Exception as e:
        record_auth_attempt(client_ip, False)
        SecurityLogger.log_login_attempt(user_login.username, False, client_ip)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="登录过程中发生错误"
        )


@router.post("/refresh", response_model=Token, summary="刷新令牌")
async def refresh_token(
    refresh_request: RefreshTokenRequest,
    request: Request,
    session = Depends(get_db_session)
):
    """
    使用刷新令牌获取新的访问令牌
    """
    from shared.security.auth import verify_refresh_token
    
    client_ip = request.client.host if request.client else "unknown"
    
    try:
        # 验证刷新令牌
        token_data = verify_refresh_token(refresh_request.refresh_token)
        if not token_data:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="无效的刷新令牌"
            )
        
        # 查找用户
        user_repo = UserRepository(session)
        if token_data.user_id:
            user = await user_repo.get_by_id(uuid.UUID(token_data.user_id))
        else:
            user = await user_repo.get_by_username(token_data.username)
        
        if not user or user.status != UserStatus.ACTIVE:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="用户不存在或已被禁用"
            )
        
        # 记录令牌刷新
        SecurityLogger.log_token_refresh(user.username, client_ip)
        
        # 创建新的访问令牌和刷新令牌
        access_token_expires = timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
        access_token = create_access_token(
            data={"sub": user.username, "user_id": str(user.id)}, 
            expires_delta=access_token_expires
        )
        
        new_refresh_token = create_refresh_token(
            data={"sub": user.username, "user_id": str(user.id)}
        )
        
        # 构建用户响应
        user_response = UserResponse(
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
        
        return Token(
            access_token=access_token,
            refresh_token=new_refresh_token,
            token_type="bearer",
            expires_in=ACCESS_TOKEN_EXPIRE_MINUTES * 60,
            user=user_response
        )
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="刷新令牌过程中发生错误"
        )


@router.post("/logout", summary="用户登出")
async def logout(
    request: Request,
    current_user: User = Depends(get_current_user)
):
    """
    用户登出接口
    
    将当前令牌加入黑名单
    """
    from shared.security.auth import logout_user
    
    try:
        # 从请求头获取令牌
        auth_header = request.headers.get("Authorization")
        if auth_header and auth_header.startswith("Bearer "):
            token = auth_header.split(" ")[1]
            logout_user(token)
        
        client_ip = request.client.host if request.client else "unknown"
        SecurityLogger.log_login_attempt(current_user.username, True, client_ip)
        
        return {"message": "登出成功"}
        
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="登出过程中发生错误"
        )


@router.get("/me", response_model=UserResponse, summary="获取当前用户信息")
async def get_current_user_info(current_user: User = Depends(get_current_user)):
    """
    获取当前登录用户的信息
    """
    return UserResponse(
        id=current_user.id,
        username=current_user.username,
        email=current_user.email,
        company_name=current_user.company_name,
        role=current_user.role,
        credits=current_user.credits,
        last_login=current_user.last_login,
        status=current_user.status,
        has_api_key=bool(current_user.api_key_hash),
        created_at=current_user.created_at,
        updated_at=current_user.updated_at
    )