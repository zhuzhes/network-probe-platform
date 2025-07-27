"""增强的单元测试覆盖率"""

import pytest
import asyncio
import uuid
import json
import tempfile
import os
from datetime import datetime, timedelta
from unittest.mock import Mock, patch, AsyncMock, MagicMock
from typing import Dict, Any, List

# 导入需要测试的模块
from shared.models.user import User, CreditTransaction, TransactionType
from shared.models.task import Task, TaskResult, TaskStatus, ProtocolType
from shared.models.agent import Agent, AgentStatus, AgentResource
from shared.security.auth import APIKeyManager, TokenData, pwd_context
# from shared.security.permissions import PermissionManager, Permission
from agent.protocols.base import ProtocolPlugin, ProtocolResult, ProtocolTestStatus, ProtocolConfig
from agent.core.config import AgentConfigManager
from management_platform.database.connection import DatabaseManager


class TestUserModelEnhanced:
    """用户模型增强测试"""
    
    def test_user_creation_with_all_fields(self):
        """测试创建包含所有字段的用户"""
        user = User(
            username="testuser",
            email="test@example.com",
            password_hash="hashed_password",
            company_name="Test Company",
            role="enterprise",
            credits=100.0,
            status="active"
        )
        
        assert user.username == "testuser"
        assert user.email == "test@example.com"
        assert user.company_name == "Test Company"
        assert user.role == "enterprise"
        assert user.credits == 100.0
        assert user.status == "active"
        # ID and timestamps are set by the database, not the model
        assert hasattr(user, 'id')
        assert hasattr(user, 'created_at')
    
    def test_user_password_validation(self):
        """测试用户密码验证"""
        user = User(
            username="testuser",
            email="test@example.com",
            password_hash="hashed_password"
        )
        
        # 测试密码验证方法（如果存在）
        assert hasattr(user, 'password_hash')
        assert user.password_hash == "hashed_password"
    
    def test_user_credit_operations(self):
        """测试用户点数操作"""
        user = User(
            username="testuser",
            email="test@example.com",
            credits=100.0
        )
        
        # 测试点数扣除
        original_credits = user.credits
        deduction = 10.0
        user.credits -= deduction
        assert user.credits == original_credits - deduction
        
        # 测试点数充值
        recharge = 50.0
        user.credits += recharge
        assert user.credits == original_credits - deduction + recharge
    
    def test_credit_transaction_creation(self):
        """测试点数交易记录创建"""
        user_id = uuid.uuid4()
        transaction = CreditTransaction(
            user_id=user_id,
            amount=50.0,
            type=TransactionType.RECHARGE,
            description="账户充值",
            reference_id="order_123"
        )
        
        assert transaction.user_id == user_id
        assert transaction.amount == 50.0
        assert transaction.type == TransactionType.RECHARGE
        assert transaction.description == "账户充值"
        assert transaction.reference_id == "order_123"
        # Timestamp is set by the database, not the model
        assert hasattr(transaction, 'created_at')


class TestTaskModelEnhanced:
    """任务模型增强测试"""
    
    def test_task_creation_with_all_protocols(self):
        """测试创建不同协议的任务"""
        protocols = [
            ProtocolType.ICMP,
            ProtocolType.TCP,
            ProtocolType.UDP,
            ProtocolType.HTTP,
            ProtocolType.HTTPS
        ]
        
        for protocol in protocols:
            task = Task(
                user_id=uuid.uuid4(),
                name=f"Test {protocol.value} Task",
                protocol=protocol,
                target="example.com",
                port=80 if protocol in [ProtocolType.HTTP, ProtocolType.TCP] else None,
                parameters={"timeout": 30},
                frequency=60,
                status=TaskStatus.ACTIVE
            )
            
            assert task.protocol == protocol
            assert task.target == "example.com"
            assert task.name == f"Test {protocol.value} Task"
            assert task.status == TaskStatus.ACTIVE
    
    def test_task_status_transitions(self):
        """测试任务状态转换"""
        task = Task(
            user_id=uuid.uuid4(),
            name="Test Task",
            protocol=ProtocolType.HTTP,
            target="example.com",
            status=TaskStatus.ACTIVE
        )
        
        # 测试状态转换
        assert task.status == TaskStatus.ACTIVE
        
        task.status = TaskStatus.PAUSED
        assert task.status == TaskStatus.PAUSED
        
        task.status = TaskStatus.COMPLETED
        assert task.status == TaskStatus.COMPLETED
    
    def test_task_result_creation(self):
        """测试任务结果创建"""
        task_id = uuid.uuid4()
        agent_id = uuid.uuid4()
        
        result = TaskResult(
            task_id=task_id,
            agent_id=agent_id,
            execution_time=datetime.utcnow(),
            duration=150.5,
            status="success",
            metrics={"response_time": 100, "status_code": 200},
            raw_data={"response": "OK"}
        )
        
        assert result.task_id == task_id
        assert result.agent_id == agent_id
        assert result.duration == 150.5
        assert result.status == "success"
        assert result.metrics["response_time"] == 100
        assert result.raw_data["response"] == "OK"
    
    def test_task_parameter_validation(self):
        """测试任务参数验证"""
        # 测试HTTP任务参数
        http_task = Task(
            user_id=uuid.uuid4(),
            name="HTTP Task",
            protocol=ProtocolType.HTTP,
            target="example.com",
            port=80,
            parameters={
                "method": "GET",
                "headers": {"User-Agent": "TestAgent"},
                "timeout": 30
            }
        )
        
        assert http_task.parameters["method"] == "GET"
        assert http_task.parameters["headers"]["User-Agent"] == "TestAgent"
        assert http_task.parameters["timeout"] == 30
        
        # 测试ICMP任务参数
        icmp_task = Task(
            user_id=uuid.uuid4(),
            name="ICMP Task",
            protocol=ProtocolType.ICMP,
            target="8.8.8.8",
            parameters={
                "count": 4,
                "interval": 1.0,
                "timeout": 5
            }
        )
        
        assert icmp_task.parameters["count"] == 4
        assert icmp_task.parameters["interval"] == 1.0


class TestAgentModelEnhanced:
    """代理模型增强测试"""
    
    def test_agent_creation_with_location(self):
        """测试创建包含位置信息的代理"""
        agent = Agent(
            name="test-agent",
            ip_address="192.168.1.100",
            country="China",
            city="Beijing",
            latitude=39.9042,
            longitude=116.4074,
            isp="China Telecom",
            version="1.0.0",
            capabilities=["icmp", "tcp", "udp", "http", "https"],
            status=AgentStatus.ONLINE
        )
        
        assert agent.name == "test-agent"
        assert agent.ip_address == "192.168.1.100"
        assert agent.country == "China"
        assert agent.city == "Beijing"
        assert agent.isp == "China Telecom"
        assert agent.version == "1.0.0"
        assert "http" in agent.capabilities
        assert agent.status == AgentStatus.ONLINE
    
    def test_agent_status_transitions(self):
        """测试代理状态转换"""
        agent = Agent(
            name="test-agent",
            ip_address="192.168.1.100",
            status=AgentStatus.OFFLINE
        )
        
        # 测试状态转换
        assert agent.status == AgentStatus.OFFLINE
        
        agent.status = AgentStatus.ONLINE
        assert agent.status == AgentStatus.ONLINE
        
        agent.status = AgentStatus.BUSY
        assert agent.status == AgentStatus.BUSY
        
        agent.status = AgentStatus.MAINTENANCE
        assert agent.status == AgentStatus.MAINTENANCE
    
    def test_agent_resource_monitoring(self):
        """测试代理资源监控"""
        agent_id = uuid.uuid4()
        
        resource = AgentResource(
            agent_id=agent_id,
            timestamp=datetime.utcnow(),
            cpu_usage=45.5,
            memory_usage=60.2,
            disk_usage=30.0,
            network_in=1024.0,
            network_out=2048.0,
            load_average=1.5
        )
        
        assert resource.agent_id == agent_id
        assert resource.cpu_usage == 45.5
        assert resource.memory_usage == 60.2
        assert resource.disk_usage == 30.0
        assert resource.network_in == 1024.0
        assert resource.network_out == 2048.0
        assert resource.load_average == 1.5
    
    def test_agent_performance_metrics(self):
        """测试代理性能指标"""
        agent = Agent(
            name="test-agent",
            ip_address="192.168.1.100",
            version="1.0.0",
            availability=0.995,
            avg_response_time=150.0,
            success_rate=0.982
        )
        
        assert agent.availability == 0.995
        assert agent.avg_response_time == 150.0
        assert agent.success_rate == 0.982


class TestPasswordHashingEnhanced:
    """密码哈希增强测试"""
    
    def test_password_hashing(self):
        """测试密码哈希"""
        password = "test_password_123"
        hashed = pwd_context.hash(password)
        
        assert hashed != password
        assert len(hashed) > 0
        assert pwd_context.verify(password, hashed)
        assert not pwd_context.verify("wrong_password", hashed)
    
    def test_password_strength_validation(self):
        """测试密码强度验证"""
        def validate_password_strength(password: str) -> bool:
            """简单的密码强度验证"""
            if len(password) < 8:
                return False
            if not any(c.isupper() for c in password):
                return False
            if not any(c.islower() for c in password):
                return False
            if not any(c.isdigit() for c in password):
                return False
            return True
        
        # 测试强密码
        strong_password = "StrongPass123!"
        assert validate_password_strength(strong_password)
        
        # 测试弱密码
        weak_passwords = [
            "123456",
            "password",
            "abc",
            "12345678",
            "PASSWORD"
        ]
        
        for weak_password in weak_passwords:
            assert not validate_password_strength(weak_password)
    
    def test_user_authentication(self):
        """测试用户认证"""
        # 创建测试用户
        password = "test_password"
        user = User(
            username="testuser",
            email="test@example.com",
            password_hash=pwd_context.hash(password)
        )
        
        # 测试正确认证
        assert pwd_context.verify(password, user.password_hash)
        
        # 测试错误认证
        assert not pwd_context.verify("wrong_password", user.password_hash)


class TestTokenDataEnhanced:
    """令牌数据增强测试"""
    
    def test_token_data_creation(self):
        """测试令牌数据创建"""
        token_data = TokenData(
            username="testuser",
            user_id=str(uuid.uuid4())
        )
        
        assert token_data.username == "testuser"
        assert token_data.user_id is not None
    
    def test_token_data_optional_fields(self):
        """测试令牌数据可选字段"""
        # 测试只有用户名
        token_data1 = TokenData(username="testuser")
        assert token_data1.username == "testuser"
        assert token_data1.user_id is None
        
        # 测试只有用户ID
        user_id = str(uuid.uuid4())
        token_data2 = TokenData(user_id=user_id)
        assert token_data2.username is None
        assert token_data2.user_id == user_id
        
        # 测试空构造
        token_data3 = TokenData()
        assert token_data3.username is None
        assert token_data3.user_id is None


class TestProtocolPluginEnhanced:
    """协议插件增强测试"""
    
    def test_protocol_result_creation(self):
        """测试协议结果创建"""
        result = ProtocolResult(
            protocol="http",
            target="example.com",
            port=80,
            status=ProtocolTestStatus.SUCCESS,
            duration_ms=150.5,
            metrics={
                "status_code": 200,
                "response_size": 1024,
                "headers": {"content-type": "text/html"}
            },
            raw_data={"response": "OK"}
        )
        
        assert result.protocol == "http"
        assert result.target == "example.com"
        assert result.port == 80
        assert result.status == ProtocolTestStatus.SUCCESS
        assert result.duration_ms == 150.5
        assert result.metrics["status_code"] == 200
        assert result.raw_data["response"] == "OK"
    
    def test_protocol_result_serialization(self):
        """测试协议结果序列化"""
        result = ProtocolResult(
            protocol="tcp",
            target="example.com",
            port=22,
            status=ProtocolTestStatus.SUCCESS,
            duration_ms=50.0
        )
        
        result_dict = result.to_dict()
        
        assert result_dict["protocol"] == "tcp"
        assert result_dict["target"] == "example.com"
        assert result_dict["port"] == 22
        assert result_dict["status"] == "success"
        assert result_dict["duration_ms"] == 50.0
    
    def test_protocol_config_validation(self):
        """测试协议配置验证"""
        config = ProtocolConfig(
            target="example.com",
            port=80,
            timeout=30.0,
            parameters={
                "method": "GET",
                "headers": {"User-Agent": "TestAgent"}
            }
        )
        
        assert config.target == "example.com"
        assert config.port == 80
        assert config.timeout == 30.0
        assert config.parameters["method"] == "GET"


class TestAgentConfigManagerEnhanced:
    """代理配置管理器增强测试"""
    
    def test_config_file_operations(self):
        """测试配置文件操作"""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
            test_config = {
                "agent_name": "test-agent",
                "heartbeat_interval": 15,
                "resource_report_interval": 30,
                "custom_setting": "test_value"
            }
            json.dump(test_config, f)
            config_file = f.name
        
        try:
            # 测试加载配置文件
            config_manager = AgentConfigManager(config_file=config_file)
            
            assert config_manager.get("agent_name") == "test-agent"
            assert config_manager.get("heartbeat_interval") == 15
            assert config_manager.get("resource_report_interval") == 30
            assert config_manager.get("custom_setting") == "test_value"
            
            # 测试设置和保存配置
            config_manager.set("new_setting", "new_value")
            config_manager.save_local_config()
            
            # 重新加载验证
            new_config_manager = AgentConfigManager(config_file=config_file)
            assert new_config_manager.get("new_setting") == "new_value"
            
        finally:
            os.unlink(config_file)
    
    def test_config_default_values(self):
        """测试配置默认值"""
        with tempfile.NamedTemporaryFile(delete=True) as f:
            non_existent_path = f.name + "_non_existent"
        
        config_manager = AgentConfigManager(config_file=non_existent_path)
        
        # 测试默认值
        assert config_manager.get("unknown_key", "default_value") == "default_value"
        assert config_manager.get("agent_name") == "probe-agent"
        assert config_manager.get("heartbeat_interval") == 30
    
    def test_config_batch_update(self):
        """测试配置批量更新"""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
            json.dump({}, f)
            config_file = f.name
        
        try:
            config_manager = AgentConfigManager(config_file=config_file)
            
            # 批量更新配置
            updates = {
                "setting1": "value1",
                "setting2": "value2",
                "setting3": 123
            }
            config_manager.update(updates)
            
            # 验证更新
            assert config_manager.get("setting1") == "value1"
            assert config_manager.get("setting2") == "value2"
            assert config_manager.get("setting3") == 123
            
        finally:
            os.unlink(config_file)


class TestDatabaseManagerEnhanced:
    """数据库管理器增强测试"""
    
    @pytest.fixture
    def db_manager(self):
        """创建数据库管理器实例"""
        manager = DatabaseManager()
        manager.initialize(test_mode=True)
        return manager
    
    def test_database_initialization(self, db_manager):
        """测试数据库初始化"""
        assert db_manager._test_mode is True
        assert db_manager._engine is not None
        assert db_manager._async_engine is not None
        assert db_manager._session_factory is not None
        assert db_manager._async_session_factory is not None
    
    def test_sync_session_context_manager(self, db_manager):
        """测试同步会话上下文管理器"""
        with db_manager.get_session() as session:
            assert session is not None
            # 测试简单查询
            from sqlalchemy import text
            result = session.execute(text("SELECT 1")).scalar()
            assert result == 1
    
    @pytest.mark.asyncio
    async def test_async_session_context_manager(self, db_manager):
        """测试异步会话上下文管理器"""
        async with db_manager.get_async_session() as session:
            assert session is not None
            # 测试简单查询
            from sqlalchemy import text
            result = await session.execute(text("SELECT 1"))
            assert result.scalar() == 1
    
    def test_sync_health_check(self, db_manager):
        """测试同步健康检查"""
        assert db_manager.sync_health_check() is True
    
    @pytest.mark.asyncio
    async def test_async_health_check(self, db_manager):
        """测试异步健康检查"""
        result = await db_manager.health_check()
        assert result is True
    
    @pytest.mark.asyncio
    async def test_table_operations(self, db_manager):
        """测试表操作"""
        # 测试创建表
        await db_manager.create_tables()
        
        # 测试删除表
        await db_manager.drop_tables()


class TestErrorHandlingEnhanced:
    """错误处理增强测试"""
    
    def test_protocol_error_handling(self):
        """测试协议错误处理"""
        from agent.protocols.base import ProtocolError
        
        error = ProtocolError(
            message="Connection failed",
            protocol="http",
            target="example.com"
        )
        
        assert str(error) == "Connection failed"
        assert error.protocol == "http"
        assert error.target == "example.com"
    
    def test_database_error_handling(self):
        """测试数据库错误处理"""
        db_manager = DatabaseManager()
        
        # 测试未初始化时的错误
        with pytest.raises(RuntimeError, match="数据库未初始化"):
            with db_manager.get_session():
                pass
    
    def test_config_error_handling(self):
        """测试配置错误处理"""
        # 测试无效JSON文件
        with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
            f.write("invalid json content")
            invalid_config_file = f.name
        
        try:
            # 应该能够处理无效JSON文件而不崩溃
            config_manager = AgentConfigManager(config_file=invalid_config_file)
            # 应该回退到默认配置
            assert config_manager.get("agent_name") == "probe-agent"
        finally:
            os.unlink(invalid_config_file)


class TestBoundaryConditions:
    """边界条件测试"""
    
    def test_empty_values(self):
        """测试空值处理"""
        # 测试空字符串
        user = User(username="", email="test@example.com")
        assert user.username == ""
        
        # 测试None值
        task = Task(
            user_id=uuid.uuid4(),
            name="Test Task",
            protocol=ProtocolType.HTTP,
            target="example.com",
            port=None
        )
        assert task.port is None
    
    def test_extreme_values(self):
        """测试极值处理"""
        # 测试大数值
        large_credits = 999999999.99
        user = User(
            username="testuser",
            email="test@example.com",
            credits=large_credits
        )
        assert user.credits == large_credits
        
        # 测试长字符串
        long_description = "x" * 1000
        task = Task(
            user_id=uuid.uuid4(),
            name="Test Task",
            protocol=ProtocolType.HTTP,
            target="example.com",
            description=long_description
        )
        assert len(task.description) == 1000
    
    def test_unicode_handling(self):
        """测试Unicode字符处理"""
        unicode_name = "测试用户名"
        unicode_company = "测试公司名称"
        
        user = User(
            username=unicode_name,
            email="test@example.com",
            company_name=unicode_company
        )
        
        assert user.username == unicode_name
        assert user.company_name == unicode_company


class TestConcurrencyScenarios:
    """并发场景测试"""
    
    @pytest.mark.asyncio
    async def test_concurrent_database_operations(self):
        """测试并发数据库操作"""
        db_manager = DatabaseManager()
        db_manager.initialize(test_mode=True)
        
        async def perform_query():
            async with db_manager.get_async_session() as session:
                from sqlalchemy import text
                result = await session.execute(text("SELECT 1"))
                return result.scalar()
        
        # 并发执行多个查询
        tasks = [perform_query() for _ in range(10)]
        results = await asyncio.gather(*tasks)
        
        # 验证所有查询都成功
        assert all(result == 1 for result in results)
        assert len(results) == 10
    
    @pytest.mark.asyncio
    async def test_concurrent_config_operations(self):
        """测试并发配置操作"""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
            json.dump({}, f)
            config_file = f.name
        
        try:
            config_manager = AgentConfigManager(config_file=config_file)
            
            async def update_config(key, value):
                config_manager.set(key, value)
                return config_manager.get(key)
            
            # 并发更新配置
            tasks = [
                update_config(f"key_{i}", f"value_{i}")
                for i in range(10)
            ]
            results = await asyncio.gather(*tasks)
            
            # 验证所有更新都成功
            for i, result in enumerate(results):
                assert result == f"value_{i}"
                
        finally:
            os.unlink(config_file)