"""配置管理模块"""

import os
from typing import Optional
from pydantic import Field
from pydantic_settings import BaseSettings


class DatabaseConfig(BaseSettings):
    """数据库配置"""
    
    host: str = Field(default="localhost", env="DB_HOST")
    port: int = Field(default=5432, env="DB_PORT")
    name: str = Field(default="network_probe", env="DB_NAME")
    user: str = Field(default="postgres", env="DB_USER")
    password: str = Field(default="", env="DB_PASSWORD")
    
    @property
    def url(self) -> str:
        """获取数据库连接URL"""
        return f"postgresql://{self.user}:{self.password}@{self.host}:{self.port}/{self.name}"
    
    @property
    def async_url(self) -> str:
        """获取异步数据库连接URL"""
        return f"postgresql+asyncpg://{self.user}:{self.password}@{self.host}:{self.port}/{self.name}"


class RedisConfig(BaseSettings):
    """Redis配置"""
    
    host: str = Field(default="localhost", env="REDIS_HOST")
    port: int = Field(default=6379, env="REDIS_PORT")
    db: int = Field(default=0, env="REDIS_DB")
    password: Optional[str] = Field(default=None, env="REDIS_PASSWORD")
    
    @property
    def url(self) -> str:
        """获取Redis连接URL"""
        auth = f":{self.password}@" if self.password else ""
        return f"redis://{auth}{self.host}:{self.port}/{self.db}"


class RabbitMQConfig(BaseSettings):
    """RabbitMQ配置"""
    
    host: str = Field(default="localhost", env="RABBITMQ_HOST")
    port: int = Field(default=5672, env="RABBITMQ_PORT")
    user: str = Field(default="guest", env="RABBITMQ_USER")
    password: str = Field(default="guest", env="RABBITMQ_PASSWORD")
    vhost: str = Field(default="/", env="RABBITMQ_VHOST")
    
    @property
    def url(self) -> str:
        """获取RabbitMQ连接URL"""
        return f"amqp://{self.user}:{self.password}@{self.host}:{self.port}{self.vhost}"


class SecurityConfig(BaseSettings):
    """安全配置"""
    
    secret_key: str = Field(env="SECRET_KEY")
    jwt_algorithm: str = Field(default="HS256", env="JWT_ALGORITHM")
    jwt_expire_minutes: int = Field(default=30, env="JWT_EXPIRE_MINUTES")
    password_min_length: int = Field(default=8, env="PASSWORD_MIN_LENGTH")
    
    model_config = {"env_file": ".env", "extra": "ignore"}


class AppConfig(BaseSettings):
    """应用配置"""
    
    name: str = Field(default="Network Probe Platform", env="APP_NAME")
    version: str = Field(default="0.1.0", env="APP_VERSION")
    debug: bool = Field(default=False, env="DEBUG")
    host: str = Field(default="0.0.0.0", env="HOST")
    port: int = Field(default=8000, env="PORT")
    
    # 数据库配置
    database: DatabaseConfig = DatabaseConfig()
    
    # Redis配置
    redis: RedisConfig = RedisConfig()
    
    # RabbitMQ配置
    rabbitmq: RabbitMQConfig = RabbitMQConfig()
    
    # 安全配置
    security: SecurityConfig = SecurityConfig()
    
    model_config = {"env_file": ".env", "extra": "ignore"}


class AgentConfig(BaseSettings):
    """代理配置"""
    
    agent_id: Optional[str] = Field(default=None, env="AGENT_ID")
    agent_name: str = Field(default="probe-agent", env="AGENT_NAME")
    server_url: str = Field(default="ws://localhost:8000", env="SERVER_URL")
    server_port: int = Field(default=8000, env="SERVER_PORT")
    
    # 认证配置
    api_key: str = Field(default="test-api-key", env="AGENT_API_KEY")
    cert_file: Optional[str] = Field(default=None, env="CERT_FILE")
    key_file: Optional[str] = Field(default=None, env="KEY_FILE")
    
    # 监控配置
    heartbeat_interval: int = Field(default=30, env="HEARTBEAT_INTERVAL")
    resource_report_interval: int = Field(default=60, env="RESOURCE_REPORT_INTERVAL")
    
    # 任务配置
    max_concurrent_tasks: int = Field(default=10, env="MAX_CONCURRENT_TASKS")
    task_timeout: int = Field(default=300, env="TASK_TIMEOUT")
    
    model_config = {"env_file": ".env", "extra": "ignore"}


# 全局配置实例
app_config = AppConfig()
agent_config = AgentConfig()