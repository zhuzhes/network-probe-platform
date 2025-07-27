"""测试配置"""

import asyncio
import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from management_platform.database.connection import DatabaseManager


@pytest.fixture(scope="session")
def event_loop():
    """创建事件循环"""
    loop = asyncio.get_event_loop_policy().new_event_loop()
    yield loop
    loop.close()


@pytest_asyncio.fixture(scope="session")
async def db_manager():
    """创建测试数据库管理器"""
    manager = DatabaseManager()
    manager.initialize(test_mode=True)
    
    # 创建所有表
    await manager.create_tables()
    
    yield manager
    
    # 清理
    await manager.drop_tables()
    await manager.close()


@pytest_asyncio.fixture
async def db_session(db_manager):
    """创建测试数据库会话"""
    async with db_manager.get_async_session() as session:
        yield session
        # 回滚事务以确保测试之间的隔离
        await session.rollback()


@pytest.fixture
def sync_db_session():
    """创建同步测试数据库会话"""
    manager = DatabaseManager()
    manager.initialize(test_mode=True)
    
    with manager.get_session() as session:
        yield session
        # 回滚事务以确保测试之间的隔离
        session.rollback()