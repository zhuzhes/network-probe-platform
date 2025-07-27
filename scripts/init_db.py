#!/usr/bin/env python3
"""数据库初始化脚本"""

import asyncio
import logging
import sys
from pathlib import Path

# 添加项目根目录到Python路径
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from management_platform.database import db_manager
from management_platform.database.migrations import migration_manager

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


async def main():
    """主函数"""
    try:
        logger.info("开始初始化数据库...")
        
        # 初始化数据库管理器
        db_manager.initialize()
        
        # 检查数据库连接
        if not await db_manager.health_check():
            logger.error("数据库连接失败")
            return 1
        
        logger.info("数据库连接正常")
        
        # 初始化数据库模式
        migration_manager.initialize_database()
        
        logger.info("数据库初始化完成")
        return 0
        
    except Exception as e:
        logger.error(f"数据库初始化失败: {e}")
        return 1
    finally:
        await db_manager.close()


if __name__ == "__main__":
    exit_code = asyncio.run(main())
    sys.exit(exit_code)