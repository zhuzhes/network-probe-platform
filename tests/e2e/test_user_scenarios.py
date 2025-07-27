"""端到端用户场景测试"""

import pytest
import asyncio
import uuid
import json
from datetime import datetime, timedelta
from typing import Dict, Any, List
from unittest.mock import Mock, patch, AsyncMock
from sqlalchemy import and_

# 导入需要测试的模块
from management_platform.database.connection import DatabaseManager
from shared.models.user import User, CreditTransaction, TransactionType, UserRole, UserStatus
from shared.models.task import Task, TaskResult, TaskStatus, ProtocolType
from shared.models.agent import Agent, AgentStatus, AgentResource
from shared.security.auth import pwd_context
from agent.protocols.base import ProtocolResult, ProtocolTestStatus, ProtocolConfig


class TestCompleteUserWorkflow:
    """完整用户工作流程测试"""
    
    @pytest.fixture
    def db_manager(self):
        """创建数据库管理器"""
        manager = DatabaseManager()
        manager.initialize(test_mode=True)
        return manager
    
    @pytest.mark.asyncio
    async def test_enterprise_user_complete_journey(self, db_manager):
        """测试企业用户完整使用流程"""
        await db_manager.create_tables()
        
        try:
            # 第一阶段：用户注册和初始化
            async with db_manager.get_async_session() as session:
                # 1. 企业用户注册
                user = User(
                    username="enterprise_user",
                    email="enterprise@company.com",
                    password_hash=pwd_context.hash("SecurePassword123!"),
                    company_name="Test Enterprise Corp",
                    role=UserRole.ENTERPRISE,
                    credits=0.0,  # 初始无点数
                    status=UserStatus.ACTIVE
                )
                session.add(user)
                await session.commit()
                await session.refresh(user)
                
                # 验证用户创建
                assert user.id is not None
                assert user.username == "enterprise_user"
                assert user.role == UserRole.ENTERPRISE
                assert user.credits == 0.0
                
                # 2. 用户充值
                recharge_amount = 500.0
                recharge_transaction = CreditTransaction(
                    user_id=user.id,
                    amount=recharge_amount,
                    type=TransactionType.RECHARGE,
                    description="初始充值",
                    reference_id="order_001"
                )
                session.add(recharge_transaction)
                user.credits += recharge_amount
                await session.commit()
                
                # 验证充值
                assert user.credits == 500.0
                assert recharge_transaction.amount == 500.0
                
            # 第二阶段：代理部署和注册
            async with db_manager.get_async_session() as session:
                # 3. 部署多个代理
                agents = []
                locations = [
                    {"country": "China", "city": "Beijing", "isp": "China Telecom"},
                    {"country": "China", "city": "Shanghai", "isp": "China Unicom"},
                    {"country": "USA", "city": "New York", "isp": "Verizon"},
                    {"country": "Germany", "city": "Frankfurt", "isp": "Deutsche Telekom"}
                ]
                
                for i, location in enumerate(locations):
                    agent = Agent(
                        name=f"probe-agent-{i+1}",
                        ip_address=f"192.168.{i+1}.100",
                        country=location["country"],
                        city=location["city"],
                        isp=location["isp"],
                        version="1.0.0",
                        capabilities=["icmp", "tcp", "udp", "http", "https"],
                        status=AgentStatus.ONLINE,
                        availability=0.99,
                        success_rate=0.95
                    )
                    session.add(agent)
                    agents.append(agent)
                
                await session.commit()
                for agent in agents:
                    await session.refresh(agent)
                
                # 验证代理部署
                assert len(agents) == 4
                assert all(agent.status == AgentStatus.ONLINE for agent in agents)
                
            # 第三阶段：创建和管理拨测任务
            async with db_manager.get_async_session() as session:
                # 4. 创建多种类型的拨测任务
                tasks = []
                
                # HTTP任务
                http_task = Task(
                    user_id=user.id,
                    name="HTTP Website Monitoring",
                    protocol=ProtocolType.HTTP,
                    target="www.example.com",
                    port=80,
                    parameters={
                        "method": "GET",
                        "timeout": 30,
                        "expected_status": 200
                    },
                    frequency=300,  # 5分钟
                    status=TaskStatus.ACTIVE
                )
                session.add(http_task)
                tasks.append(http_task)
                
                # HTTPS任务
                https_task = Task(
                    user_id=user.id,
                    name="HTTPS API Monitoring",
                    protocol=ProtocolType.HTTPS,
                    target="api.example.com",
                    port=443,
                    parameters={
                        "method": "GET",
                        "path": "/health",
                        "timeout": 30
                    },
                    frequency=60,  # 1分钟
                    status=TaskStatus.ACTIVE
                )
                session.add(https_task)
                tasks.append(https_task)
                
                # ICMP任务
                icmp_task = Task(
                    user_id=user.id,
                    name="Network Connectivity Check",
                    protocol=ProtocolType.ICMP,
                    target="8.8.8.8",
                    parameters={
                        "count": 4,
                        "interval": 1.0,
                        "timeout": 5
                    },
                    frequency=120,  # 2分钟
                    status=TaskStatus.ACTIVE
                )
                session.add(icmp_task)
                tasks.append(icmp_task)
                
                # TCP任务
                tcp_task = Task(
                    user_id=user.id,
                    name="Database Connection Check",
                    protocol=ProtocolType.TCP,
                    target="db.example.com",
                    port=5432,
                    parameters={
                        "timeout": 10
                    },
                    frequency=600,  # 10分钟
                    status=TaskStatus.ACTIVE
                )
                session.add(tcp_task)
                tasks.append(tcp_task)
                
                await session.commit()
                for task in tasks:
                    await session.refresh(task)
                
                # 验证任务创建
                assert len(tasks) == 4
                assert all(task.status == TaskStatus.ACTIVE for task in tasks)
                assert all(task.user_id == user.id for task in tasks)
                
            # 第四阶段：模拟任务执行和结果收集
            async with db_manager.get_async_session() as session:
                # 5. 模拟任务执行结果
                execution_results = []
                
                for task in tasks:
                    for agent in agents[:2]:  # 使用前两个代理执行任务
                        # 模拟成功的执行结果
                        result = TaskResult(
                            task_id=task.id,
                            agent_id=agent.id,
                            execution_time=datetime.utcnow(),
                            duration=100.0 + (hash(str(task.id) + str(agent.id)) % 100),
                            status="success",
                            metrics=self._generate_task_metrics(task.protocol),
                            raw_data=self._generate_raw_data(task.protocol)
                        )
                        session.add(result)
                        execution_results.append(result)
                        
                        # 扣除用户点数（每次执行消费1点数）
                        consumption = CreditTransaction(
                            user_id=user.id,
                            amount=-1.0,
                            type=TransactionType.CONSUMPTION,
                            description=f"任务执行: {task.name}",
                            reference_id=str(task.id)
                        )
                        session.add(consumption)
                        user.credits -= 1.0
                
                await session.commit()
                
                # 验证执行结果
                assert len(execution_results) == 8  # 4个任务 × 2个代理
                assert all(result.status == "success" for result in execution_results)
                assert user.credits == 500.0 - 8.0  # 初始500点数 - 8次执行
                
            # 第五阶段：代理资源监控
            async with db_manager.get_async_session() as session:
                # 6. 收集代理资源数据
                for agent in agents:
                    # 模拟一段时间内的资源数据
                    for i in range(5):
                        timestamp = datetime.utcnow() - timedelta(minutes=i*5)
                        resource = AgentResource(
                            agent_id=agent.id,
                            timestamp=timestamp,
                            cpu_usage=30.0 + (i * 5) + (hash(str(agent.id)) % 20),
                            memory_usage=40.0 + (i * 3) + (hash(str(agent.id)) % 15),
                            disk_usage=20.0 + (i * 1) + (hash(str(agent.id)) % 10),
                            network_in=1000.0 + (i * 100),
                            network_out=2000.0 + (i * 200),
                            load_average=1.0 + (i * 0.2)
                        )
                        session.add(resource)
                
                await session.commit()
                
                # 验证资源数据收集
                from sqlalchemy import select, func
                stmt = select(func.count(AgentResource.id))
                result = await session.execute(stmt)
                resource_count = result.scalar()
                assert resource_count == 20  # 4个代理 × 5个时间点
                
            # 第六阶段：数据分析和报告
            async with db_manager.get_async_session() as session:
                # 7. 生成分析报告
                from sqlalchemy import select, func, and_
                
                # 任务成功率统计
                success_stmt = select(
                    Task.name,
                    func.count(TaskResult.id).label('total_executions'),
                    func.sum(
                        func.case((TaskResult.status == 'success', 1), else_=0)
                    ).label('successful_executions')
                ).select_from(
                    Task.join(TaskResult)
                ).where(
                    Task.user_id == user.id
                ).group_by(Task.id, Task.name)
                
                result = await session.execute(success_stmt)
                task_stats = result.all()
                
                # 验证统计数据
                assert len(task_stats) == 4
                for stat in task_stats:
                    assert stat.total_executions == 2  # 每个任务被2个代理执行
                    assert stat.successful_executions == 2  # 所有执行都成功
                
                # 代理性能统计
                agent_stmt = select(
                    Agent.name,
                    Agent.country,
                    Agent.city,
                    func.count(TaskResult.id).label('tasks_executed'),
                    func.avg(TaskResult.duration).label('avg_duration')
                ).select_from(
                    Agent.join(TaskResult)
                ).group_by(Agent.id, Agent.name, Agent.country, Agent.city)
                
                result = await session.execute(agent_stmt)
                agent_stats = result.all()
                
                # 验证代理统计
                assert len(agent_stats) == 2  # 只有前两个代理执行了任务
                for stat in agent_stats:
                    assert stat.tasks_executed == 4  # 每个代理执行了4个任务
                    assert stat.avg_duration > 0
                
            # 第七阶段：用户账户管理
            async with db_manager.get_async_session() as session:
                # 8. 查看账户余额和交易历史
                from sqlalchemy import select, desc
                
                # 获取用户当前状态
                user_stmt = select(User).where(User.id == user.id)
                result = await session.execute(user_stmt)
                current_user = result.scalar_one()
                
                # 获取交易历史
                transaction_stmt = select(CreditTransaction).where(
                    CreditTransaction.user_id == user.id
                ).order_by(desc(CreditTransaction.created_at))
                result = await session.execute(transaction_stmt)
                transactions = result.scalars().all()
                
                # 验证账户状态
                assert current_user.credits == 492.0  # 500 - 8
                assert len(transactions) == 9  # 1次充值 + 8次消费
                
                # 验证交易类型分布
                recharge_count = sum(1 for t in transactions if t.type == TransactionType.RECHARGE)
                consumption_count = sum(1 for t in transactions if t.type == TransactionType.CONSUMPTION)
                
                assert recharge_count == 1
                assert consumption_count == 8
                
                # 9. 模拟余额不足场景
                # 将用户余额设置为很低
                current_user.credits = 2.0
                await session.commit()
                
                # 尝试执行更多任务（应该在余额不足时停止）
                remaining_credits = current_user.credits
                tasks_can_execute = int(remaining_credits)  # 每个任务消费1点数
                
                assert tasks_can_execute == 2
                
        finally:
            await db_manager.drop_tables()
            await db_manager.close()
    
    def _generate_task_metrics(self, protocol: ProtocolType) -> Dict[str, Any]:
        """根据协议类型生成相应的指标数据"""
        base_metrics = {
            "execution_time": datetime.utcnow().isoformat(),
            "success": True
        }
        
        if protocol in [ProtocolType.HTTP, ProtocolType.HTTPS]:
            return {
                **base_metrics,
                "status_code": 200,
                "response_time": 150.5,
                "response_size": 1024,
                "dns_time": 10.2,
                "connect_time": 25.3,
                "ssl_time": 45.1 if protocol == ProtocolType.HTTPS else 0
            }
        elif protocol == ProtocolType.ICMP:
            return {
                **base_metrics,
                "packets_sent": 4,
                "packets_received": 4,
                "packet_loss": 0.0,
                "min_rtt": 10.1,
                "max_rtt": 15.8,
                "avg_rtt": 12.5,
                "stddev_rtt": 2.1
            }
        elif protocol in [ProtocolType.TCP, ProtocolType.UDP]:
            return {
                **base_metrics,
                "connect_time": 25.3,
                "response_time": 100.2,
                "port_open": True
            }
        else:
            return base_metrics
    
    def _generate_raw_data(self, protocol: ProtocolType) -> Dict[str, Any]:
        """根据协议类型生成相应的原始数据"""
        if protocol in [ProtocolType.HTTP, ProtocolType.HTTPS]:
            return {
                "headers": {
                    "content-type": "text/html",
                    "server": "nginx/1.18.0",
                    "content-length": "1024"
                },
                "response_body": "<html><body>OK</body></html>"
            }
        elif protocol == ProtocolType.ICMP:
            return {
                "ping_output": "PING 8.8.8.8: 56 data bytes\n64 bytes from 8.8.8.8: icmp_seq=0 ttl=118 time=12.5 ms"
            }
        elif protocol in [ProtocolType.TCP, ProtocolType.UDP]:
            return {
                "connection_info": "Connected successfully",
                "socket_info": {"local_port": 12345, "remote_port": 5432}
            }
        else:
            return {"raw_response": "OK"}


class TestSystemPerformanceScenarios:
    """系统性能场景测试"""
    
    @pytest.fixture
    def db_manager(self):
        """创建数据库管理器"""
        manager = DatabaseManager()
        manager.initialize(test_mode=True)
        return manager
    
    @pytest.mark.asyncio
    async def test_high_load_scenario(self, db_manager):
        """测试高负载场景"""
        await db_manager.create_tables()
        
        try:
            # 创建多个用户
            users = []
            async with db_manager.get_async_session() as session:
                for i in range(10):
                    user = User(
                        username=f"load_user_{i}",
                        email=f"load{i}@example.com",
                        password_hash=pwd_context.hash("testpassword"),
                        role=UserRole.ENTERPRISE,
                        credits=1000.0
                    )
                    session.add(user)
                    users.append(user)
                
                await session.commit()
                for user in users:
                    await session.refresh(user)
            
            # 创建多个代理
            agents = []
            async with db_manager.get_async_session() as session:
                for i in range(20):
                    agent = Agent(
                        name=f"load-agent-{i}",
                        ip_address=f"10.0.{i//10}.{i%10}",
                        version="1.0.0",
                        status=AgentStatus.ONLINE
                    )
                    session.add(agent)
                    agents.append(agent)
                
                await session.commit()
                for agent in agents:
                    await session.refresh(agent)
            
            # 创建大量任务
            tasks = []
            async with db_manager.get_async_session() as session:
                for user in users:
                    for j in range(5):  # 每个用户5个任务
                        task = Task(
                            user_id=user.id,
                            name=f"Load Test Task {j}",
                            protocol=ProtocolType.HTTP,
                            target=f"test{j}.example.com",
                            port=80,
                            parameters={"method": "GET"},
                            frequency=60,
                            status=TaskStatus.ACTIVE
                        )
                        session.add(task)
                        tasks.append(task)
                
                await session.commit()
                for task in tasks:
                    await session.refresh(task)
            
            # 验证创建的数据量
            assert len(users) == 10
            assert len(agents) == 20
            assert len(tasks) == 50  # 10用户 × 5任务
            
            # 模拟并发任务执行
            async def execute_task_batch(task_batch, agent_batch):
                results = []
                async with db_manager.get_async_session() as session:
                    for task in task_batch:
                        for agent in agent_batch:
                            result = TaskResult(
                                task_id=task.id,
                                agent_id=agent.id,
                                execution_time=datetime.utcnow(),
                                duration=50.0 + (hash(str(task.id) + str(agent.id)) % 100),
                                status="success",
                                metrics={"response_time": 100, "status_code": 200},
                                raw_data={"response": "OK"}
                            )
                            session.add(result)
                            results.append(result)
                    
                    await session.commit()
                    return len(results)
            
            # 分批并发执行
            batch_size = 10
            task_batches = [tasks[i:i+batch_size] for i in range(0, len(tasks), batch_size)]
            agent_batches = [agents[i:i+5] for i in range(0, len(agents), 5)]
            
            execution_tasks = []
            for task_batch in task_batches:
                for agent_batch in agent_batches:
                    execution_tasks.append(execute_task_batch(task_batch, agent_batch))
            
            # 等待所有执行完成
            results = await asyncio.gather(*execution_tasks)
            total_results = sum(results)
            
            # 验证执行结果
            assert total_results > 0
            print(f"Total task results created: {total_results}")
            
        finally:
            await db_manager.drop_tables()
            await db_manager.close()
    
    @pytest.mark.asyncio
    async def test_concurrent_user_operations(self, db_manager):
        """测试并发用户操作"""
        await db_manager.create_tables()
        
        try:
            async def user_workflow(user_index):
                """单个用户的完整工作流程"""
                async with db_manager.get_async_session() as session:
                    # 创建用户
                    user = User(
                        username=f"concurrent_user_{user_index}",
                        email=f"concurrent{user_index}@example.com",
                        password_hash=pwd_context.hash("testpassword"),
                        role=UserRole.ENTERPRISE,
                        credits=100.0
                    )
                    session.add(user)
                    await session.commit()
                    await session.refresh(user)
                    
                    # 创建任务
                    task = Task(
                        user_id=user.id,
                        name=f"Concurrent Task {user_index}",
                        protocol=ProtocolType.HTTP,
                        target=f"test{user_index}.example.com",
                        port=80,
                        parameters={"method": "GET"},
                        frequency=300,
                        status=TaskStatus.ACTIVE
                    )
                    session.add(task)
                    await session.commit()
                    await session.refresh(task)
                    
                    return user.id, task.id
            
            # 并发执行多个用户工作流程
            concurrent_users = 20
            workflow_tasks = [user_workflow(i) for i in range(concurrent_users)]
            results = await asyncio.gather(*workflow_tasks)
            
            # 验证结果
            assert len(results) == concurrent_users
            user_ids = [result[0] for result in results]
            task_ids = [result[1] for result in results]
            
            # 确保所有ID都是唯一的
            assert len(set(user_ids)) == concurrent_users
            assert len(set(task_ids)) == concurrent_users
            
        finally:
            await db_manager.drop_tables()
            await db_manager.close()


class TestFailureRecoveryScenarios:
    """故障恢复场景测试"""
    
    @pytest.fixture
    def db_manager(self):
        """创建数据库管理器"""
        manager = DatabaseManager()
        manager.initialize(test_mode=True)
        return manager
    
    @pytest.mark.asyncio
    async def test_agent_failure_recovery(self, db_manager):
        """测试代理故障恢复"""
        await db_manager.create_tables()
        
        try:
            async with db_manager.get_async_session() as session:
                # 创建用户和任务
                user = User(
                    username="failure_test_user",
                    email="failure@example.com",
                    password_hash=pwd_context.hash("testpassword"),
                    role=UserRole.ENTERPRISE,
                    credits=100.0
                )
                session.add(user)
                await session.commit()
                await session.refresh(user)
                
                task = Task(
                    user_id=user.id,
                    name="Failure Recovery Task",
                    protocol=ProtocolType.HTTP,
                    target="example.com",
                    port=80,
                    parameters={"method": "GET"},
                    frequency=60,
                    status=TaskStatus.ACTIVE
                )
                session.add(task)
                await session.commit()
                await session.refresh(task)
                
                # 创建多个代理
                agents = []
                for i in range(3):
                    agent = Agent(
                        name=f"failure-agent-{i}",
                        ip_address=f"192.168.1.{100+i}",
                        version="1.0.0",
                        status=AgentStatus.ONLINE
                    )
                    session.add(agent)
                    agents.append(agent)
                
                await session.commit()
                for agent in agents:
                    await session.refresh(agent)
                
                # 模拟第一个代理执行成功
                success_result = TaskResult(
                    task_id=task.id,
                    agent_id=agents[0].id,
                    execution_time=datetime.utcnow(),
                    duration=100.0,
                    status="success",
                    metrics={"response_time": 100, "status_code": 200},
                    raw_data={"response": "OK"}
                )
                session.add(success_result)
                
                # 模拟第二个代理执行失败
                failure_result = TaskResult(
                    task_id=task.id,
                    agent_id=agents[1].id,
                    execution_time=datetime.utcnow(),
                    duration=0.0,
                    status="error",
                    error_message="Connection timeout",
                    metrics={},
                    raw_data={}
                )
                session.add(failure_result)
                
                # 模拟第三个代理作为备用执行成功
                backup_result = TaskResult(
                    task_id=task.id,
                    agent_id=agents[2].id,
                    execution_time=datetime.utcnow(),
                    duration=120.0,
                    status="success",
                    metrics={"response_time": 120, "status_code": 200},
                    raw_data={"response": "OK"}
                )
                session.add(backup_result)
                
                # 更新失败代理状态
                agents[1].status = AgentStatus.OFFLINE
                
                await session.commit()
                
                # 验证故障恢复
                from sqlalchemy import select, func
                
                # 检查任务执行结果
                success_count_stmt = select(func.count(TaskResult.id)).where(
                    and_(TaskResult.task_id == task.id, TaskResult.status == "success")
                )
                result = await session.execute(success_count_stmt)
                success_count = result.scalar()
                
                failure_count_stmt = select(func.count(TaskResult.id)).where(
                    and_(TaskResult.task_id == task.id, TaskResult.status == "error")
                )
                result = await session.execute(failure_count_stmt)
                failure_count = result.scalar()
                
                # 验证结果
                assert success_count == 2  # 两个代理成功执行
                assert failure_count == 1   # 一个代理执行失败
                assert agents[1].status == AgentStatus.OFFLINE  # 失败代理被标记为离线
                
        finally:
            await db_manager.drop_tables()
            await db_manager.close()
    
    @pytest.mark.asyncio
    async def test_database_transaction_rollback(self, db_manager):
        """测试数据库事务回滚"""
        await db_manager.create_tables()
        
        try:
            async with db_manager.get_async_session() as session:
                # 创建用户
                user = User(
                    username="rollback_test_user",
                    email="rollback@example.com",
                    password_hash=pwd_context.hash("testpassword"),
                    role=UserRole.ENTERPRISE,
                    credits=100.0
                )
                session.add(user)
                await session.commit()
                await session.refresh(user)
                
                # 记录初始状态
                initial_credits = user.credits
                
                # 尝试一个会失败的事务
                try:
                    async with db_manager.get_async_session() as error_session:
                        # 扣除点数
                        user_in_error_session = await error_session.get(User, user.id)
                        user_in_error_session.credits -= 50.0
                        
                        # 创建交易记录
                        transaction = CreditTransaction(
                            user_id=user.id,
                            amount=-50.0,
                            type=TransactionType.CONSUMPTION,
                            description="测试交易"
                        )
                        error_session.add(transaction)
                        
                        # 故意引发错误（例如，违反某些业务规则）
                        if user_in_error_session.credits < 0:
                            raise ValueError("余额不足")
                        
                        await error_session.commit()
                        
                except Exception as e:
                    # 预期会有异常
                    assert "余额不足" in str(e) or isinstance(e, ValueError)
                
                # 验证回滚后的状态
                await session.refresh(user)
                assert user.credits == initial_credits  # 余额应该没有变化
                
                # 验证没有创建交易记录
                from sqlalchemy import select
                transaction_stmt = select(CreditTransaction).where(
                    CreditTransaction.user_id == user.id
                )
                result = await session.execute(transaction_stmt)
                transactions = result.scalars().all()
                
                # 应该没有交易记录（因为事务回滚了）
                assert len(transactions) == 0
                
        finally:
            await db_manager.drop_tables()
            await db_manager.close()


class TestDataConsistencyScenarios:
    """数据一致性场景测试"""
    
    @pytest.fixture
    def db_manager(self):
        """创建数据库管理器"""
        manager = DatabaseManager()
        manager.initialize(test_mode=True)
        return manager
    
    @pytest.mark.asyncio
    async def test_credit_consistency(self, db_manager):
        """测试点数一致性"""
        await db_manager.create_tables()
        
        try:
            async with db_manager.get_async_session() as session:
                # 创建用户
                user = User(
                    username="consistency_user",
                    email="consistency@example.com",
                    password_hash=pwd_context.hash("testpassword"),
                    role=UserRole.ENTERPRISE,
                    credits=1000.0
                )
                session.add(user)
                await session.commit()
                await session.refresh(user)
                
                # 记录所有交易
                transactions = []
                
                # 充值交易
                recharge = CreditTransaction(
                    user_id=user.id,
                    amount=500.0,
                    type=TransactionType.RECHARGE,
                    description="充值"
                )
                session.add(recharge)
                transactions.append(recharge)
                user.credits += 500.0
                
                # 多次消费交易
                for i in range(10):
                    consumption = CreditTransaction(
                        user_id=user.id,
                        amount=-10.0,
                        type=TransactionType.CONSUMPTION,
                        description=f"消费 {i+1}"
                    )
                    session.add(consumption)
                    transactions.append(consumption)
                    user.credits -= 10.0
                
                # 退款交易
                refund = CreditTransaction(
                    user_id=user.id,
                    amount=25.0,
                    type=TransactionType.REFUND,
                    description="退款"
                )
                session.add(refund)
                transactions.append(refund)
                user.credits += 25.0
                
                await session.commit()
                
                # 验证点数一致性
                expected_credits = 1000.0 + 500.0 - (10 * 10.0) + 25.0  # 1425.0
                assert user.credits == expected_credits
                
                # 验证交易记录总和
                from sqlalchemy import select, func
                sum_stmt = select(func.sum(CreditTransaction.amount)).where(
                    CreditTransaction.user_id == user.id
                )
                result = await session.execute(sum_stmt)
                transaction_sum = result.scalar() or 0.0
                
                # 交易记录总和应该等于点数变化
                credits_change = user.credits - 1000.0  # 减去初始点数
                assert abs(transaction_sum - credits_change) < 0.01  # 允许浮点数精度误差
                
        finally:
            await db_manager.drop_tables()
            await db_manager.close()
    
    @pytest.mark.asyncio
    async def test_task_result_consistency(self, db_manager):
        """测试任务结果一致性"""
        await db_manager.create_tables()
        
        try:
            async with db_manager.get_async_session() as session:
                # 创建用户、代理和任务
                user = User(
                    username="result_user",
                    email="result@example.com",
                    password_hash=pwd_context.hash("testpassword"),
                    role=UserRole.ENTERPRISE,
                    credits=100.0
                )
                session.add(user)
                
                agent = Agent(
                    name="result-agent",
                    ip_address="192.168.1.100",
                    version="1.0.0",
                    status=AgentStatus.ONLINE
                )
                session.add(agent)
                
                task = Task(
                    user_id=user.id,
                    name="Consistency Test Task",
                    protocol=ProtocolType.HTTP,
                    target="example.com",
                    port=80,
                    parameters={"method": "GET"},
                    frequency=60,
                    status=TaskStatus.ACTIVE
                )
                session.add(task)
                
                await session.commit()
                await session.refresh(user)
                await session.refresh(agent)
                await session.refresh(task)
                
                # 创建多个任务结果
                results = []
                for i in range(5):
                    result = TaskResult(
                        task_id=task.id,
                        agent_id=agent.id,
                        execution_time=datetime.utcnow() - timedelta(minutes=i),
                        duration=100.0 + i * 10,
                        status="success",
                        metrics={
                            "response_time": 100 + i * 5,
                            "status_code": 200
                        },
                        raw_data={"response": f"OK {i}"}
                    )
                    session.add(result)
                    results.append(result)
                
                await session.commit()
                
                # 验证结果一致性
                from sqlalchemy import select, func, desc
                
                # 检查结果数量
                count_stmt = select(func.count(TaskResult.id)).where(
                    TaskResult.task_id == task.id
                )
                result = await session.execute(count_stmt)
                result_count = result.scalar()
                assert result_count == 5
                
                # 检查平均响应时间
                avg_stmt = select(func.avg(TaskResult.duration)).where(
                    TaskResult.task_id == task.id
                )
                result = await session.execute(avg_stmt)
                avg_duration = result.scalar()
                expected_avg = sum(100.0 + i * 10 for i in range(5)) / 5
                assert abs(avg_duration - expected_avg) < 0.01
                
                # 检查最新结果
                latest_stmt = select(TaskResult).where(
                    TaskResult.task_id == task.id
                ).order_by(desc(TaskResult.execution_time)).limit(1)
                result = await session.execute(latest_stmt)
                latest_result = result.scalar_one()
                
                assert latest_result.duration == 100.0  # 最新的结果（i=0）
                
        finally:
            await db_manager.drop_tables()
            await db_manager.close()