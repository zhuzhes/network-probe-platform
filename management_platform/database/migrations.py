"""数据库迁移管理"""

import logging
import subprocess
import sys
from pathlib import Path
from typing import Optional

from alembic import command
from alembic.config import Config
from alembic.runtime.migration import MigrationContext
from alembic.script import ScriptDirectory
from sqlalchemy import inspect

from .connection import db_manager

logger = logging.getLogger(__name__)


class MigrationManager:
    """数据库迁移管理器"""
    
    def __init__(self):
        self.project_root = Path(__file__).parent.parent.parent
        self.alembic_cfg_path = self.project_root / "alembic.ini"
        self.migrations_dir = self.project_root / "migrations"
    
    def get_alembic_config(self) -> Config:
        """获取Alembic配置"""
        if not self.alembic_cfg_path.exists():
            raise FileNotFoundError(f"Alembic配置文件不存在: {self.alembic_cfg_path}")
        
        config = Config(str(self.alembic_cfg_path))
        config.set_main_option("script_location", str(self.migrations_dir))
        return config
    
    def create_migration(self, message: str, autogenerate: bool = True) -> None:
        """创建新的迁移文件"""
        try:
            config = self.get_alembic_config()
            
            if autogenerate:
                command.revision(config, message=message, autogenerate=True)
            else:
                command.revision(config, message=message)
            
            logger.info(f"迁移文件创建成功: {message}")
        except Exception as e:
            logger.error(f"创建迁移文件失败: {e}")
            raise
    
    def upgrade_database(self, revision: str = "head") -> None:
        """升级数据库到指定版本"""
        try:
            config = self.get_alembic_config()
            command.upgrade(config, revision)
            logger.info(f"数据库升级成功到版本: {revision}")
        except Exception as e:
            logger.error(f"数据库升级失败: {e}")
            raise
    
    def downgrade_database(self, revision: str) -> None:
        """降级数据库到指定版本"""
        try:
            config = self.get_alembic_config()
            command.downgrade(config, revision)
            logger.info(f"数据库降级成功到版本: {revision}")
        except Exception as e:
            logger.error(f"数据库降级失败: {e}")
            raise
    
    def get_current_revision(self) -> Optional[str]:
        """获取当前数据库版本"""
        try:
            with db_manager.get_session() as session:
                context = MigrationContext.configure(session.connection())
                return context.get_current_revision()
        except Exception as e:
            logger.error(f"获取当前版本失败: {e}")
            return None
    
    def get_migration_history(self) -> list:
        """获取迁移历史"""
        try:
            config = self.get_alembic_config()
            script = ScriptDirectory.from_config(config)
            
            with db_manager.get_session() as session:
                context = MigrationContext.configure(session.connection())
                current_rev = context.get_current_revision()
                
                history = []
                for revision in script.walk_revisions():
                    history.append({
                        'revision': revision.revision,
                        'down_revision': revision.down_revision,
                        'message': revision.doc,
                        'is_current': revision.revision == current_rev
                    })
                
                return history
        except Exception as e:
            logger.error(f"获取迁移历史失败: {e}")
            return []
    
    def check_database_schema(self) -> dict:
        """检查数据库模式状态"""
        try:
            with db_manager.get_session() as session:
                inspector = inspect(session.bind)
                
                # 获取所有表
                tables = inspector.get_table_names()
                
                # 检查是否存在alembic版本表
                has_alembic_table = 'alembic_version' in tables
                
                # 获取当前版本
                current_revision = self.get_current_revision() if has_alembic_table else None
                
                return {
                    'tables': tables,
                    'has_alembic_table': has_alembic_table,
                    'current_revision': current_revision,
                    'is_initialized': has_alembic_table and current_revision is not None
                }
        except Exception as e:
            logger.error(f"检查数据库模式失败: {e}")
            return {
                'tables': [],
                'has_alembic_table': False,
                'current_revision': None,
                'is_initialized': False
            }
    
    def initialize_database(self) -> None:
        """初始化数据库（创建表和初始迁移）"""
        try:
            schema_info = self.check_database_schema()
            
            if not schema_info['is_initialized']:
                logger.info("初始化数据库...")
                
                # 如果没有alembic版本表，先标记当前状态
                if not schema_info['has_alembic_table']:
                    config = self.get_alembic_config()
                    command.stamp(config, "head")
                    logger.info("数据库版本标记完成")
                
                # 升级到最新版本
                self.upgrade_database()
                logger.info("数据库初始化完成")
            else:
                logger.info("数据库已初始化")
        except Exception as e:
            logger.error(f"数据库初始化失败: {e}")
            raise


# 全局迁移管理器实例
migration_manager = MigrationManager()