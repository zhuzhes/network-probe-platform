"""数据库连接管理"""

import logging
from contextlib import asynccontextmanager, contextmanager
from typing import AsyncGenerator, Generator, Optional

from sqlalchemy import create_engine, event, text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool, QueuePool

from shared.config import app_config

logger = logging.getLogger(__name__)


class DatabaseManager:
    """数据库管理器"""
    
    def __init__(self):
        self._engine = None
        self._async_engine = None
        self._session_factory = None
        self._async_session_factory = None
        self._test_mode = False
    
    def initialize(self, test_mode: bool = False) -> None:
        """初始化数据库连接"""
        self._test_mode = test_mode
        
        if test_mode:
            # 测试模式使用内存数据库
            database_url = "sqlite:///:memory:"
            async_database_url = "sqlite+aiosqlite:///:memory:"
            
            # SQLite 配置
            self._engine = create_engine(
                database_url,
                poolclass=StaticPool,
                connect_args={
                    "check_same_thread": False,
                },
                echo=app_config.debug
            )
            
            self._async_engine = create_async_engine(
                async_database_url,
                poolclass=StaticPool,
                connect_args={
                    "check_same_thread": False,
                },
                echo=app_config.debug
            )
        else:
            # 生产模式使用 PostgreSQL
            database_url = app_config.database.url
            async_database_url = app_config.database.async_url
            
            # PostgreSQL 配置
            self._engine = create_engine(
                database_url,
                poolclass=QueuePool,
                pool_size=20,
                max_overflow=30,
                pool_pre_ping=True,
                pool_recycle=3600,
                pool_timeout=30,
                echo=app_config.debug
            )
            
            self._async_engine = create_async_engine(
                async_database_url,
                poolclass=QueuePool,
                pool_size=20,
                max_overflow=30,
                pool_pre_ping=True,
                pool_recycle=3600,
                pool_timeout=30,
                echo=app_config.debug
            )
        
        # 创建会话工厂
        self._session_factory = sessionmaker(
            bind=self._engine,
            autocommit=False,
            autoflush=False
        )
        
        self._async_session_factory = async_sessionmaker(
            bind=self._async_engine,
            class_=AsyncSession,
            autocommit=False,
            autoflush=False,
            expire_on_commit=False
        )
        
        # 添加连接事件监听器
        self._setup_event_listeners()
        
        logger.info(f"数据库连接已初始化 (测试模式: {test_mode})")
    
    def _setup_event_listeners(self) -> None:
        """设置数据库事件监听器"""
        
        @event.listens_for(self._engine, "connect")
        def set_sqlite_pragma(dbapi_connection, connection_record):
            """SQLite 特定配置"""
            if self._test_mode:
                cursor = dbapi_connection.cursor()
                cursor.execute("PRAGMA foreign_keys=ON")
                cursor.execute("PRAGMA journal_mode=WAL")
                cursor.close()
        
        @event.listens_for(self._engine, "connect")
        def set_postgresql_settings(dbapi_connection, connection_record):
            """PostgreSQL 特定配置"""
            if not self._test_mode:
                with dbapi_connection.cursor() as cursor:
                    cursor.execute("SET timezone TO 'UTC'")
        
        @event.listens_for(self._engine, "checkout")
        def receive_checkout(dbapi_connection, connection_record, connection_proxy):
            """连接检出时的处理"""
            logger.debug("数据库连接已检出")
        
        @event.listens_for(self._engine, "checkin")
        def receive_checkin(dbapi_connection, connection_record):
            """连接检入时的处理"""
            logger.debug("数据库连接已检入")
        
        @event.listens_for(self._engine, "invalidate")
        def receive_invalidate(dbapi_connection, connection_record, exception):
            """连接失效时的处理"""
            logger.warning(f"数据库连接失效: {exception}")
        
        @event.listens_for(self._engine, "soft_invalidate")
        def receive_soft_invalidate(dbapi_connection, connection_record, exception):
            """连接软失效时的处理"""
            logger.info(f"数据库连接软失效: {exception}")
    
    @contextmanager
    def get_session(self) -> Generator[Session, None, None]:
        """获取同步数据库会话"""
        if not self._session_factory:
            raise RuntimeError("数据库未初始化，请先调用 initialize()")
        
        session = self._session_factory()
        try:
            yield session
            session.commit()
        except Exception:
            session.rollback()
            raise
        finally:
            session.close()
    
    @asynccontextmanager
    async def get_async_session(self) -> AsyncGenerator[AsyncSession, None]:
        """获取异步数据库会话"""
        if not self._async_session_factory:
            raise RuntimeError("数据库未初始化，请先调用 initialize()")
        
        async with self._async_session_factory() as session:
            try:
                yield session
                await session.commit()
            except Exception:
                await session.rollback()
                raise
    
    async def create_tables(self) -> None:
        """创建数据库表"""
        if not self._async_engine:
            raise RuntimeError("数据库未初始化，请先调用 initialize()")
        
        # 导入所有模型以确保它们被注册
        from shared.models.base import Base
        from shared.models.user import User, CreditTransaction
        from shared.models.task import Task, TaskResult
        from shared.models.agent import Agent, AgentResource
        
        async with self._async_engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        
        logger.info("数据库表创建完成")
    
    async def drop_tables(self) -> None:
        """删除数据库表"""
        if not self._async_engine:
            raise RuntimeError("数据库未初始化，请先调用 initialize()")
        
        # 导入所有模型以确保它们被注册
        from shared.models.base import Base
        from shared.models.user import User, CreditTransaction
        from shared.models.task import Task, TaskResult
        from shared.models.agent import Agent, AgentResource
        
        async with self._async_engine.begin() as conn:
            await conn.run_sync(Base.metadata.drop_all)
        
        logger.info("数据库表删除完成")
    
    async def health_check(self) -> bool:
        """数据库健康检查"""
        try:
            async with self.get_async_session() as session:
                await session.execute(text("SELECT 1"))
                return True
        except Exception as e:
            logger.error(f"数据库健康检查失败: {e}")
            return False
    
    def sync_health_check(self) -> bool:
        """同步数据库健康检查"""
        try:
            with self.get_session() as session:
                session.execute(text("SELECT 1"))
                return True
        except Exception as e:
            logger.error(f"数据库健康检查失败: {e}")
            return False
    
    async def close(self) -> None:
        """关闭数据库连接"""
        if self._async_engine:
            await self._async_engine.dispose()
        
        if self._engine:
            self._engine.dispose()
        
        logger.info("数据库连接已关闭")
    
    @property
    def engine(self):
        """获取同步引擎"""
        return self._engine
    
    @property
    def async_engine(self):
        """获取异步引擎"""
        return self._async_engine


# 全局数据库管理器实例
db_manager = DatabaseManager()


# 便捷函数
def get_db_session() -> Generator[Session, None, None]:
    """获取数据库会话的便捷函数"""
    with db_manager.get_session() as session:
        yield session


async def get_async_db_session() -> AsyncGenerator[AsyncSession, None]:
    """获取异步数据库会话的便捷函数"""
    async with db_manager.get_async_session() as session:
        yield session