"""pytest配置文件"""

import pytest
import asyncio
from typing import Generator, AsyncGenerator
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession

from shared.config import app_config


@pytest.fixture(scope="session")
def event_loop() -> Generator[asyncio.AbstractEventLoop, None, None]:
    """创建事件循环"""
    loop = asyncio.get_event_loop_policy().new_event_loop()
    yield loop
    loop.close()


@pytest.fixture(scope="session")
def test_db_url() -> str:
    """测试数据库URL"""
    return app_config.database.url.replace(
        app_config.database.name, f"test_{app_config.database.name}"
    )


@pytest.fixture(scope="session")
def test_async_db_url() -> str:
    """测试异步数据库URL"""
    return app_config.database.async_url.replace(
        app_config.database.name, f"test_{app_config.database.name}"
    )


@pytest.fixture(scope="session")
def sync_engine(test_db_url: str):
    """同步数据库引擎"""
    engine = create_engine(test_db_url)
    yield engine
    engine.dispose()


@pytest.fixture(scope="session")
async def async_engine(test_async_db_url: str):
    """异步数据库引擎"""
    engine = create_async_engine(test_async_db_url)
    yield engine
    await engine.dispose()


@pytest.fixture
def sync_session(sync_engine):
    """同步数据库会话"""
    Session = sessionmaker(bind=sync_engine)
    session = Session()
    try:
        yield session
    finally:
        session.rollback()
        session.close()


@pytest.fixture
async def async_session(async_engine) -> AsyncGenerator[AsyncSession, None]:
    """异步数据库会话"""
    async with AsyncSession(async_engine) as session:
        yield session
        await session.rollback()