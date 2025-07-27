"""测试配置"""

import os
from typing import Optional


class TestDatabaseConfig:
    """测试数据库配置"""
    
    def __init__(self):
        self.host = os.getenv("TEST_DB_HOST", "localhost")
        self.port = int(os.getenv("TEST_DB_PORT", "5432"))
        self.name = os.getenv("TEST_DB_NAME", "test_network_probe")
        self.user = os.getenv("TEST_DB_USER", "postgres")
        self.password = os.getenv("TEST_DB_PASSWORD", "")
    
    @property
    def url(self) -> str:
        """获取数据库连接URL"""
        return f"postgresql://{self.user}:{self.password}@{self.host}:{self.port}/{self.name}"
    
    @property
    def async_url(self) -> str:
        """获取异步数据库连接URL"""
        return f"postgresql+asyncpg://{self.user}:{self.password}@{self.host}:{self.port}/{self.name}"


class TestSecurityConfig:
    """测试安全配置"""
    
    def __init__(self):
        self.secret_key = "test_secret_key_for_testing_only"
        self.jwt_algorithm = "HS256"
        self.jwt_expire_minutes = 30


class TestAppConfig:
    """测试应用配置"""
    
    def __init__(self):
        self.database = TestDatabaseConfig()
        self.security = TestSecurityConfig()


# 测试配置实例
test_app_config = TestAppConfig()