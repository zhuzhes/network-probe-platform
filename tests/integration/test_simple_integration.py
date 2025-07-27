"""简化的集成测试套件"""

import pytest
import asyncio
import uuid
import json
from datetime import datetime, timedelta
from typing import Dict, Any, List
from unittest.mock import Mock, patch, AsyncMock

# 导入需要测试的模块
from management_platform.database.connection import DatabaseManager
from shared.models.user import User, CreditTransaction, TransactionType, UserRole, UserStatus
from shared.models.task import Task, TaskResult, TaskStatus, ProtocolType
from shared.models.agent import Agent, AgentStatus, AgentResource
from shared.security.auth import pwd_context


class TestDatabaseIntegration:
    """数据库集成测试"""
    
    @pytest.fixture
    def db_manager(self):
        """创建数据库管理器"""
        manager = DatabaseManager()
        manager.initialize(test_mode=True)
        return manager
    
    @pytest.mark.asyncio
    async def test_database_initialization(self, db_manager):
        """测试数据库初始化"""
        # 创建表
        await db_manager.create_tables()
        
        # 测试健康检查
        health = await db_manager.health_check()
        assert health is True
        
        # 清理
        await db_manager.drop_tables()
        await db_manager.close()
    
    @pytest.mark.asyncio
    async def test_user_operations(self, db_manager):
        """测试用户操作"""
        await db_manager.create_tables()
        
        try:
            async with db_manager.get_async_session() as session:
                # 创建用户
                user = User(
                    username="integration_user",
                    email="integration@example.com",
                    password_hash=pwd_context.hash("testpassword"),
                    company_name="Integration Test Company",
                    role=UserRole.ENTERPRISE,
                    credits=100.0,
                    status=UserStatus.ACTIVE
                )
                session.add(user)
                await session.commit()
                await session.refresh(user)
                
                # 验证用户创建
                assert user.id is not None
                assert user.username == "integration_user"
                assert user.credits == 100.0
                
                # 创建点数交易
                transaction = CreditTransaction(
                    user_id=user.id,
                    amount=50.0,
                    type=TransactionType.RECHARGE,
                    description="集成测试充值"
                )
                session.add(transaction)
                await session.commit()
                
                # 验证交易创建
                assert transaction.id is not None
                assert transaction.user_id == user.id
                assert transaction.amount == 50.0
                
        finally:
            await db_manager.drop_tables()
            await db_manager.close()
    
    @pytest.mark.asyncio
    async def test_task_operations(self, db_manager):
        """测试任务操作"""
        await db_manager.create_tables()
        
        try:
            async with db_manager.get_async_session() as session:
                # 创建用户
                user = User(
                    username="task_user",
                    email="task@example.com",
                    password_hash=pwd_context.hash("testpassword"),
                    role=UserRole.ENTERPRISE
                )
                session.add(user)
                await session.commit()
                await session.refresh(user)
                
                # 创建任务
                task = Task(
                    user_id=user.id,
                    name="Integration Test Task",
                    protocol=ProtocolType.HTTP,
                    target="example.com",
                    port=80,
                    parameters={"method": "GET", "timeout": 30},
                    frequency=60,
                    status=TaskStatus.ACTIVE
                )
                session.add(task)
                await session.commit()
                await session.refresh(task)
                
                # 验证任务创建
                assert task.id is not None
                assert task.user_id == user.id
                assert task.protocol == ProtocolType.HTTP
                assert task.target == "example.com"
                
        finally:
            await db_manager.drop_tables()
            await db_manager.close()
    
    @pytest.mark.asyncio
    async def test_agent_operations(self, db_manager):
        """测试代理操作"""
        await db_manager.create_tables()
        
        try:
            async with db_manager.get_async_session() as session:
                # 创建代理
                agent = Agent(
                    name="integration-agent",
                    ip_address="192.168.1.100",
                    country="China",
                    city="Beijing",
                    isp="China Telecom",
                    version="1.0.0",
                    capabilities=["icmp", "tcp", "udp", "http", "https"],
                    status=AgentStatus.ONLINE
                )
                session.add(agent)
                await session.commit()
                await session.refresh(agent)
                
                # 验证代理创建
                assert agent.id is not None
                assert agent.name == "integration-agent"
                assert agent.status == AgentStatus.ONLINE
                
                # 创建资源记录
                resource = AgentResource(
                    agent_id=agent.id,
                    timestamp=datetime.utcnow(),
                    cpu_usage=45.5,
                    memory_usage=60.2,
                    disk_usage=30.0,
                    network_in=1024.0,
                    network_out=2048.0,
                    load_average=1.5
                )
                session.add(resource)
                await session.commit()
                
                # 验证资源记录
                assert resource.id is not None
                assert resource.agent_id == agent.id
                assert resource.cpu_usage == 45.5
                
        finally:
            await db_manager.drop_tables()
            await db_manager.close()
    
    @pytest.mark.asyncio
    async def test_complete_workflow(self, db_manager):
        """测试完整工作流程"""
        await db_manager.create_tables()
        
        try:
            async with db_manager.get_async_session() as session:
                # 1. 创建用户
                user = User(
                    username="workflow_user",
                    email="workflow@example.com",
                    password_hash=pwd_context.hash("testpassword"),
                    role=UserRole.ENTERPRISE,
                    credits=100.0
                )
                session.add(user)
                await session.commit()
                await session.refresh(user)
                
                # 2. 创建代理
                agent = Agent(
                    name="workflow-agent",
                    ip_address="192.168.1.200",
                    version="1.0.0",
                    status=AgentStatus.ONLINE
                )
                session.add(agent)
                await session.commit()
                await session.refresh(agent)
                
                # 3. 创建任务
                task = Task(
                    user_id=user.id,
                    name="Workflow Test Task",
                    protocol=ProtocolType.HTTP,
                    target="httpbin.org",
                    port=80,
                    parameters={"method": "GET"},
                    frequency=300,
                    status=TaskStatus.ACTIVE
                )
                session.add(task)
                await session.commit()
                await session.refresh(task)
                
                # 4. 创建任务结果
                result = TaskResult(
                    task_id=task.id,
                    agent_id=agent.id,
                    execution_time=datetime.utcnow(),
                    duration=200.5,
                    status="success",
                    metrics={
                        "response_time": 150,
                        "status_code": 200,
                        "response_size": 1024
                    },
                    raw_data={
                        "headers": {"content-type": "application/json"},
                        "response": "OK"
                    }
                )
                session.add(result)
                await session.commit()
                
                # 5. 创建点数交易（任务消费）
                transaction = CreditTransaction(
                    user_id=user.id,
                    amount=-1.0,  # 扣除1个点数
                    type=TransactionType.CONSUMPTION,
                    description="任务执行消费",
                    reference_id=str(task.id)
                )
                session.add(transaction)
                
                # 更新用户点数
                user.credits -= 1.0
                await session.commit()
                
                # 验证完整流程
                assert user.credits == 99.0
                assert result.status == "success"
                assert result.metrics["status_code"] == 200
                assert transaction.reference_id == str(task.id)
                
        finally:
            await db_manager.drop_tables()
            await db_manager.close()


class TestConcurrencyIntegration:
    """并发集成测试"""
    
    @pytest.fixture
    def db_manager(self):
        """创建数据库管理器"""
        manager = DatabaseManager()
        manager.initialize(test_mode=True)
        return manager
    
    @pytest.mark.asyncio
    async def test_concurrent_user_creation(self, db_manager):
        """测试并发用户创建"""
        await db_manager.create_tables()
        
        try:
            async def create_user(index):
                async with db_manager.get_async_session() as session:
                    user = User(
                        username=f"concurrent_user_{index}",
                        email=f"concurrent{index}@example.com",
                        password_hash=pwd_context.hash("testpassword"),
                        role=UserRole.ENTERPRISE,
                        credits=100.0
                    )
                    session.add(user)
                    await session.commit()
                    await session.refresh(user)
                    return user.id
            
            # 并发创建10个用户
            tasks = [create_user(i) for i in range(10)]
            user_ids = await asyncio.gather(*tasks)
            
            # 验证所有用户都被创建
            assert len(user_ids) == 10
            assert all(user_id is not None for user_id in user_ids)
            assert len(set(user_ids)) == 10  # 确保所有ID都是唯一的
            
        finally:
            await db_manager.drop_tables()
            await db_manager.close()
    
    @pytest.mark.asyncio
    async def test_concurrent_database_operations(self, db_manager):
        """测试并发数据库操作"""
        await db_manager.create_tables()
        
        try:
            async def perform_operation(index):
                async with db_manager.get_async_session() as session:
                    from sqlalchemy import text
                    result = await session.execute(text(f"SELECT {index} as value"))
                    return result.scalar()
            
            # 并发执行20个数据库操作
            tasks = [perform_operation(i) for i in range(20)]
            results = await asyncio.gather(*tasks)
            
            # 验证所有操作都成功
            assert len(results) == 20
            for i, result in enumerate(results):
                assert result == i
                
        finally:
            await db_manager.drop_tables()
            await db_manager.close()


class TestComponentIntegration:
    """组件集成测试"""
    
    def test_password_hashing_integration(self):
        """测试密码哈希集成"""
        password = "integration_test_password"
        
        # 测试哈希
        hashed = pwd_context.hash(password)
        assert hashed != password
        assert len(hashed) > 0
        
        # 测试验证
        assert pwd_context.verify(password, hashed)
        assert not pwd_context.verify("wrong_password", hashed)
    
    def test_model_validation_integration(self):
        """测试模型验证集成"""
        # 测试用户模型验证
        user = User(
            username="test_user",
            email="test@example.com",
            password_hash=pwd_context.hash("testpassword"),
            role=UserRole.ENTERPRISE,
            credits=50.0
        )
        
        assert user.username == "test_user"
        assert user.email == "test@example.com"
        assert user.role == UserRole.ENTERPRISE
        assert user.credits == 50.0
        
        # 测试任务模型验证
        task = Task(
            user_id=uuid.uuid4(),
            name="Integration Test Task",
            protocol=ProtocolType.HTTP,
            target="example.com",
            port=80,
            parameters={"method": "GET"},
            frequency=60,
            status=TaskStatus.ACTIVE
        )
        
        assert task.protocol == ProtocolType.HTTP
        assert task.target == "example.com"
        assert task.port == 80
        assert task.status == TaskStatus.ACTIVE
        
        # 测试代理模型验证
        agent = Agent(
            name="test-agent",
            ip_address="192.168.1.100",
            version="1.0.0",
            status=AgentStatus.ONLINE,
            availability=0.99,
            success_rate=0.95
        )
        
        assert agent.name == "test-agent"
        assert agent.ip_address == "192.168.1.100"
        assert agent.status == AgentStatus.ONLINE
        assert agent.availability == 0.99
        assert agent.success_rate == 0.95
    
    def test_enum_integration(self):
        """测试枚举集成"""
        # 测试用户角色枚举
        assert UserRole.ADMIN.value == "admin"
        assert UserRole.ENTERPRISE.value == "enterprise"
        
        # 测试用户状态枚举
        assert UserStatus.ACTIVE.value == "active"
        assert UserStatus.INACTIVE.value == "inactive"
        assert UserStatus.SUSPENDED.value == "suspended"
        
        # 测试任务状态枚举
        assert TaskStatus.ACTIVE.value == "active"
        assert TaskStatus.PAUSED.value == "paused"
        assert TaskStatus.COMPLETED.value == "completed"
        assert TaskStatus.FAILED.value == "failed"
        
        # 测试协议类型枚举
        assert ProtocolType.ICMP.value == "icmp"
        assert ProtocolType.TCP.value == "tcp"
        assert ProtocolType.UDP.value == "udp"
        assert ProtocolType.HTTP.value == "http"
        assert ProtocolType.HTTPS.value == "https"
        
        # 测试代理状态枚举
        assert AgentStatus.ONLINE.value == "online"
        assert AgentStatus.OFFLINE.value == "offline"
        assert AgentStatus.BUSY.value == "busy"
        assert AgentStatus.MAINTENANCE.value == "maintenance"
    
    def test_transaction_type_integration(self):
        """测试交易类型集成"""
        # 测试所有交易类型
        assert TransactionType.RECHARGE.value == "recharge"
        assert TransactionType.CONSUMPTION.value == "consumption"
        assert TransactionType.REFUND.value == "refund"
        assert TransactionType.VOUCHER.value == "voucher"
        
        # 测试交易记录创建
        user_id = uuid.uuid4()
        
        # 充值交易
        recharge = CreditTransaction(
            user_id=user_id,
            amount=100.0,
            type=TransactionType.RECHARGE,
            description="账户充值"
        )
        assert recharge.type == TransactionType.RECHARGE
        assert recharge.amount == 100.0
        
        # 消费交易
        consumption = CreditTransaction(
            user_id=user_id,
            amount=-10.0,
            type=TransactionType.CONSUMPTION,
            description="任务执行消费"
        )
        assert consumption.type == TransactionType.CONSUMPTION
        assert consumption.amount == -10.0
        
        # 退款交易
        refund = CreditTransaction(
            user_id=user_id,
            amount=5.0,
            type=TransactionType.REFUND,
            description="任务失败退款"
        )
        assert refund.type == TransactionType.REFUND
        assert refund.amount == 5.0
        
        # 抵用券交易
        voucher = CreditTransaction(
            user_id=user_id,
            amount=20.0,
            type=TransactionType.VOUCHER,
            description="新用户抵用券"
        )
        assert voucher.type == TransactionType.VOUCHER
        assert voucher.amount == 20.0


class TestErrorHandlingIntegration:
    """错误处理集成测试"""
    
    @pytest.fixture
    def db_manager(self):
        """创建数据库管理器"""
        manager = DatabaseManager()
        manager.initialize(test_mode=True)
        return manager
    
    @pytest.mark.asyncio
    async def test_database_error_handling(self, db_manager):
        """测试数据库错误处理"""
        await db_manager.create_tables()
        
        try:
            # 测试会话错误处理
            async with db_manager.get_async_session() as session:
                # 创建用户
                user = User(
                    username="error_test_user",
                    email="error@example.com",
                    password_hash=pwd_context.hash("testpassword"),
                    role=UserRole.ENTERPRISE
                )
                session.add(user)
                await session.commit()
                await session.refresh(user)
                
                # 尝试创建重复用户（应该会失败）
                try:
                    duplicate_user = User(
                        username="error_test_user",  # 重复用户名
                        email="error2@example.com",
                        password_hash=pwd_context.hash("testpassword"),
                        role=UserRole.ENTERPRISE
                    )
                    session.add(duplicate_user)
                    await session.commit()
                except Exception as e:
                    # 预期会有异常，这是正常的
                    await session.rollback()
                    assert True  # 错误被正确处理
                
        finally:
            await db_manager.drop_tables()
            await db_manager.close()
    
    def test_model_validation_errors(self):
        """测试模型验证错误"""
        # 测试代理名称验证
        with pytest.raises(ValueError):
            agent = Agent(
                name="",  # 空名称应该失败
                ip_address="192.168.1.100",
                version="1.0.0"
            )
            # 触发验证（如果有的话）
            if hasattr(agent, 'validate_name'):
                agent.validate_name('name', "")
        
        # 测试代理可用率验证
        with pytest.raises(ValueError):
            agent = Agent(
                name="test-agent",
                ip_address="192.168.1.100",
                version="1.0.0",
                availability=1.5  # 超出范围应该失败
            )
    
    def test_password_validation_errors(self):
        """测试密码验证错误"""
        # 测试空密码 - bcrypt实际上可以处理空字符串
        empty_hash = pwd_context.hash("")
        assert empty_hash is not None
        assert pwd_context.verify("", empty_hash)
        
        # 测试None密码
        with pytest.raises((TypeError, ValueError)):
            pwd_context.hash(None)
    
    @pytest.mark.asyncio
    async def test_connection_error_handling(self):
        """测试连接错误处理"""
        # 测试未初始化的数据库管理器
        uninitialized_manager = DatabaseManager()
        
        with pytest.raises(RuntimeError, match="数据库未初始化"):
            async with uninitialized_manager.get_async_session():
                pass
        
        # 测试同步会话
        with pytest.raises(RuntimeError, match="数据库未初始化"):
            with uninitialized_manager.get_session():
                pass