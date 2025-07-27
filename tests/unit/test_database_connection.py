"""数据库连接测试"""

import pytest
from sqlalchemy import text

from management_platform.database.connection import DatabaseManager
from management_platform.database.migrations import MigrationManager


class TestDatabaseConnection:
    """数据库连接测试类"""
    
    def test_database_manager_initialization(self):
        """测试数据库管理器初始化"""
        manager = DatabaseManager()
        
        # 初始化前应该没有引擎
        assert manager.engine is None
        assert manager.async_engine is None
        
        # 初始化
        manager.initialize(test_mode=True)
        
        # 初始化后应该有引擎
        assert manager.engine is not None
        assert manager.async_engine is not None
    
    def test_sync_session_context_manager(self, sync_db_session):
        """测试同步会话上下文管理器"""
        # 执行简单查询
        result = sync_db_session.execute(text("SELECT 1 as test"))
        row = result.fetchone()
        assert row[0] == 1
    
    @pytest.mark.asyncio
    async def test_async_session_context_manager(self, db_session):
        """测试异步会话上下文管理器"""
        # 执行简单查询
        result = await db_session.execute(text("SELECT 1 as test"))
        row = result.fetchone()
        assert row[0] == 1
    
    @pytest.mark.asyncio
    async def test_table_creation_and_cleanup(self):
        """测试表创建和清理"""
        manager = DatabaseManager()
        manager.initialize(test_mode=True)
        
        # 创建表
        await manager.create_tables()
        
        # 验证表存在（通过查询系统表）
        async with manager.get_async_session() as session:
            # SQLite 中查询表是否存在
            result = await session.execute(
                text("SELECT name FROM sqlite_master WHERE type='table'")
            )
            tables = [row[0] for row in result.fetchall()]
            
            # 应该包含我们的模型表
            expected_tables = ['users', 'tasks', 'task_results', 'agents', 'agent_resources', 'credit_transactions']
            for table in expected_tables:
                assert table in tables
        
        # 删除表
        await manager.drop_tables()
        
        # 验证表已删除
        async with manager.get_async_session() as session:
            result = await session.execute(
                text("SELECT name FROM sqlite_master WHERE type='table'")
            )
            tables = [row[0] for row in result.fetchall()]
            
            # 不应该包含我们的模型表
            for table in expected_tables:
                assert table not in tables
        
        await manager.close()
    
    @pytest.mark.asyncio
    async def test_health_check(self):
        """测试数据库健康检查"""
        manager = DatabaseManager()
        manager.initialize(test_mode=True)
        
        # 异步健康检查
        assert await manager.health_check() is True
        
        # 同步健康检查
        assert manager.sync_health_check() is True
        
        await manager.close()
    
    def test_database_url_configuration(self):
        """测试数据库URL配置"""
        from shared.config import app_config
        
        # 测试PostgreSQL URL格式
        db_config = app_config.database
        url = db_config.url
        async_url = db_config.async_url
        
        assert url.startswith("postgresql://")
        assert async_url.startswith("postgresql+asyncpg://")
        assert db_config.host in url
        assert str(db_config.port) in url
        assert db_config.name in url
    
    def test_migration_manager_initialization(self):
        """测试迁移管理器初始化"""
        migration_manager = MigrationManager()
        
        # 检查路径配置
        assert migration_manager.alembic_cfg_path.exists()
        assert migration_manager.migrations_dir.exists()
        
        # 获取Alembic配置
        config = migration_manager.get_alembic_config()
        assert config is not None
    
    @pytest.mark.asyncio
    async def test_database_session_error_handling(self):
        """测试数据库会话错误处理"""
        manager = DatabaseManager()
        manager.initialize(test_mode=True)
        
        # 测试异步会话错误处理
        try:
            async with manager.get_async_session() as session:
                # 执行一个会导致错误的查询
                await session.execute(text("SELECT * FROM non_existent_table"))
                await session.commit()
        except Exception:
            # 应该能正确处理异常
            pass
        
        # 测试同步会话错误处理
        try:
            with manager.get_session() as session:
                # 执行一个会导致错误的查询
                session.execute(text("SELECT * FROM non_existent_table"))
                session.commit()
        except Exception:
            # 应该能正确处理异常
            pass
        
        await manager.close()