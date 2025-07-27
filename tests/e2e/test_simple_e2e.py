"""简化的端到端测试"""

import pytest
import asyncio
import uuid
from datetime import datetime, timedelta
from typing import Dict, Any, List

# 导入需要测试的模块
from management_platform.database.connection import DatabaseManager
from shared.models.user import User, CreditTransaction, TransactionType, UserRole, UserStatus
from shared.models.task import Task, TaskResult, TaskStatus, ProtocolType
from shared.models.agent import Agent, AgentStatus, AgentResource
from shared.security.auth import pwd_context


class TestEndToEndUserScenarios:
    """端到端用户场景测试"""
    
    @pytest.fixture
    def db_manager(self):
        """创建数据库管理器"""
        manager = DatabaseManager()
        manager.initialize(test_mode=True)
        return manager
    
    @pytest.mark.asyncio
    async def test_complete_user_journey(self, db_manager):
        """测试完整的用户使用流程"""
        await db_manager.create_tables()
        
        try:
            # 阶段1：用户注册和充值
            async with db_manager.get_async_session() as session:
                # 创建企业用户
                user = User(
                    username="e2e_enterprise_user",
                    email="e2e@enterprise.com",
                    password_hash=pwd_context.hash("SecurePassword123!"),
                    company_name="E2E Test Enterprise",
                    role=UserRole.ENTERPRISE,
                    credits=0.0,
                    status=UserStatus.ACTIVE
                )
                session.add(user)
                await session.commit()
                await session.refresh(user)
                
                # 用户充值
                recharge = CreditTransaction(
                    user_id=user.id,
                    amount=1000.0,
                    type=TransactionType.RECHARGE,
                    description="初始充值",
                    reference_id="recharge_001"
                )
                session.add(recharge)
                user.credits += 1000.0
                await session.commit()
                
                assert user.credits == 1000.0
                
            # 阶段2：部署代理
            async with db_manager.get_async_session() as session:
                # 创建多个地理位置的代理
                agents = []
                locations = [
                    {"name": "beijing-agent", "country": "China", "city": "Beijing"},
                    {"name": "shanghai-agent", "country": "China", "city": "Shanghai"},
                    {"name": "newyork-agent", "country": "USA", "city": "New York"}
                ]
                
                for i, location in enumerate(locations):
                    agent = Agent(
                        name=location["name"],
                        ip_address=f"10.0.{i+1}.100",
                        country=location["country"],
                        city=location["city"],
                        version="1.0.0",
                        capabilities=["icmp", "tcp", "udp", "http", "https"],
                        status=AgentStatus.ONLINE
                    )
                    session.add(agent)
                    agents.append(agent)
                
                await session.commit()
                for agent in agents:
                    await session.refresh(agent)
                
                assert len(agents) == 3
                assert all(agent.status == AgentStatus.ONLINE for agent in agents)
                
            # 阶段3：创建拨测任务
            async with db_manager.get_async_session() as session:
                # 创建不同类型的任务
                tasks = []
                
                # HTTP监控任务
                http_task = Task(
                    user_id=user.id,
                    name="Website Monitoring",
                    protocol=ProtocolType.HTTP,
                    target="www.example.com",
                    port=80,
                    parameters={"method": "GET", "timeout": 30},
                    frequency=300,
                    status=TaskStatus.ACTIVE
                )
                session.add(http_task)
                tasks.append(http_task)
                
                # ICMP连通性检查
                icmp_task = Task(
                    user_id=user.id,
                    name="Connectivity Check",
                    protocol=ProtocolType.ICMP,
                    target="8.8.8.8",
                    parameters={"count": 4, "timeout": 5},
                    frequency=120,
                    status=TaskStatus.ACTIVE
                )
                session.add(icmp_task)
                tasks.append(icmp_task)
                
                await session.commit()
                for task in tasks:
                    await session.refresh(task)
                
                assert len(tasks) == 2
                
            # 阶段4：模拟任务执行
            async with db_manager.get_async_session() as session:
                execution_count = 0
                
                # 每个任务在每个代理上执行一次
                for task in tasks:
                    for agent in agents:
                        # 模拟成功执行
                        result = TaskResult(
                            task_id=task.id,
                            agent_id=agent.id,
                            execution_time=datetime.utcnow(),
                            duration=100.0 + execution_count * 10,
                            status="success",
                            metrics=self._generate_metrics(task.protocol),
                            raw_data={"response": "OK", "execution_id": execution_count}
                        )
                        session.add(result)
                        
                        # 扣除点数
                        consumption = CreditTransaction(
                            user_id=user.id,
                            amount=-1.0,
                            type=TransactionType.CONSUMPTION,
                            description=f"执行任务: {task.name}",
                            reference_id=str(task.id)
                        )
                        session.add(consumption)
                        user.credits -= 1.0
                        execution_count += 1
                
                await session.commit()
                
                # 验证执行结果
                expected_executions = len(tasks) * len(agents)  # 2任务 × 3代理 = 6次执行
                assert execution_count == expected_executions
                assert user.credits == 1000.0 - expected_executions
                
            # 阶段5：资源监控数据收集
            async with db_manager.get_async_session() as session:
                # 为每个代理生成资源监控数据
                for agent in agents:
                    for i in range(3):  # 3个时间点的数据
                        resource = AgentResource(
                            agent_id=agent.id,
                            timestamp=datetime.utcnow() - timedelta(minutes=i*5),
                            cpu_usage=30.0 + i * 10,
                            memory_usage=50.0 + i * 5,
                            disk_usage=25.0 + i * 2,
                            network_in=1000.0 + i * 100,
                            network_out=2000.0 + i * 200,
                            load_average=1.0 + i * 0.3
                        )
                        session.add(resource)
                
                await session.commit()
                
                # 验证资源数据
                from sqlalchemy import select, func
                count_stmt = select(func.count(AgentResource.id))
                result = await session.execute(count_stmt)
                resource_count = result.scalar()
                assert resource_count == 9  # 3代理 × 3时间点
                
            # 阶段6：数据分析和统计
            async with db_manager.get_async_session() as session:
                from sqlalchemy import select, func
                
                # 任务执行统计
                task_stats_stmt = select(
                    Task.name,
                    func.count(TaskResult.id).label('execution_count'),
                    func.avg(TaskResult.duration).label('avg_duration')
                ).select_from(
                    Task.join(TaskResult)
                ).where(
                    Task.user_id == user.id
                ).group_by(Task.id, Task.name)
                
                result = await session.execute(task_stats_stmt)
                task_stats = result.all()
                
                # 验证统计结果
                assert len(task_stats) == 2
                for stat in task_stats:
                    assert stat.execution_count == 3  # 每个任务被3个代理执行
                    assert stat.avg_duration > 0
                
                # 用户点数统计
                credit_stmt = select(
                    func.sum(CreditTransaction.amount).label('total_amount')
                ).where(CreditTransaction.user_id == user.id)
                
                result = await session.execute(credit_stmt)
                total_transactions = result.scalar()
                
                # 验证点数变化：1000充值 - 6消费 = 994
                expected_balance = 1000.0 - 6.0
                assert abs(total_transactions - expected_balance) < 0.01
                
        finally:
            await db_manager.drop_tables()
            await db_manager.close()
    
    @pytest.mark.asyncio
    async def test_failure_recovery_scenario(self, db_manager):
        """测试故障恢复场景"""
        await db_manager.create_tables()
        
        try:
            async with db_manager.get_async_session() as session:
                # 创建用户
                user = User(
                    username="failure_user",
                    email="failure@test.com",
                    password_hash=pwd_context.hash("testpass"),
                    role=UserRole.ENTERPRISE,
                    credits=100.0
                )
                session.add(user)
                
                # 创建任务
                task = Task(
                    user_id=user.id,
                    name="Failure Test Task",
                    protocol=ProtocolType.HTTP,
                    target="unreliable.example.com",
                    port=80,
                    parameters={"method": "GET"},
                    frequency=60,
                    status=TaskStatus.ACTIVE
                )
                session.add(task)
                
                # 创建代理
                primary_agent = Agent(
                    name="primary-agent",
                    ip_address="192.168.1.10",
                    version="1.0.0",
                    status=AgentStatus.ONLINE
                )
                session.add(primary_agent)
                
                backup_agent = Agent(
                    name="backup-agent",
                    ip_address="192.168.1.20",
                    version="1.0.0",
                    status=AgentStatus.ONLINE
                )
                session.add(backup_agent)
                
                await session.commit()
                await session.refresh(user)
                await session.refresh(task)
                await session.refresh(primary_agent)
                await session.refresh(backup_agent)
                
                # 模拟主代理执行失败
                failure_result = TaskResult(
                    task_id=task.id,
                    agent_id=primary_agent.id,
                    execution_time=datetime.utcnow(),
                    duration=0.0,
                    status="error",
                    error_message="Connection timeout",
                    metrics={},
                    raw_data={}
                )
                session.add(failure_result)
                
                # 主代理状态变为离线
                primary_agent.status = AgentStatus.OFFLINE
                
                # 备用代理执行成功
                success_result = TaskResult(
                    task_id=task.id,
                    agent_id=backup_agent.id,
                    execution_time=datetime.utcnow(),
                    duration=150.0,
                    status="success",
                    metrics={"response_time": 150, "status_code": 200},
                    raw_data={"response": "OK"}
                )
                session.add(success_result)
                
                await session.commit()
                
                # 验证故障恢复
                from sqlalchemy import select, func
                
                # 检查失败和成功的执行次数
                failure_count_stmt = select(func.count(TaskResult.id)).where(
                    (TaskResult.task_id == task.id) & (TaskResult.status == "error")
                )
                result = await session.execute(failure_count_stmt)
                failure_count = result.scalar()
                
                success_count_stmt = select(func.count(TaskResult.id)).where(
                    (TaskResult.task_id == task.id) & (TaskResult.status == "success")
                )
                result = await session.execute(success_count_stmt)
                success_count = result.scalar()
                
                assert failure_count == 1
                assert success_count == 1
                assert primary_agent.status == AgentStatus.OFFLINE
                assert backup_agent.status == AgentStatus.ONLINE
                
        finally:
            await db_manager.drop_tables()
            await db_manager.close()
    
    @pytest.mark.asyncio
    async def test_performance_under_load(self, db_manager):
        """测试负载下的性能"""
        await db_manager.create_tables()
        
        try:
            # 创建多个用户并发操作
            async def create_user_with_tasks(user_index):
                async with db_manager.get_async_session() as session:
                    # 创建用户
                    user = User(
                        username=f"perf_user_{user_index}",
                        email=f"perf{user_index}@test.com",
                        password_hash=pwd_context.hash("testpass"),
                        role=UserRole.ENTERPRISE,
                        credits=50.0
                    )
                    session.add(user)
                    await session.commit()
                    await session.refresh(user)
                    
                    # 创建任务
                    task = Task(
                        user_id=user.id,
                        name=f"Performance Task {user_index}",
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
            
            # 并发创建10个用户和任务
            user_count = 10
            tasks = [create_user_with_tasks(i) for i in range(user_count)]
            results = await asyncio.gather(*tasks)
            
            # 验证所有用户和任务都创建成功
            assert len(results) == user_count
            user_ids = [result[0] for result in results]
            task_ids = [result[1] for result in results]
            
            assert len(set(user_ids)) == user_count  # 所有用户ID唯一
            assert len(set(task_ids)) == user_count  # 所有任务ID唯一
            
            # 验证数据库中的记录数
            async with db_manager.get_async_session() as session:
                from sqlalchemy import select, func
                
                user_count_stmt = select(func.count(User.id))
                result = await session.execute(user_count_stmt)
                db_user_count = result.scalar()
                
                task_count_stmt = select(func.count(Task.id))
                result = await session.execute(task_count_stmt)
                db_task_count = result.scalar()
                
                assert db_user_count == user_count
                assert db_task_count == user_count
                
        finally:
            await db_manager.drop_tables()
            await db_manager.close()
    
    def _generate_metrics(self, protocol: ProtocolType) -> Dict[str, Any]:
        """根据协议生成相应的指标"""
        if protocol == ProtocolType.HTTP:
            return {
                "status_code": 200,
                "response_time": 150,
                "response_size": 1024,
                "dns_time": 10,
                "connect_time": 25
            }
        elif protocol == ProtocolType.ICMP:
            return {
                "packets_sent": 4,
                "packets_received": 4,
                "packet_loss": 0.0,
                "avg_rtt": 12.5,
                "min_rtt": 10.1,
                "max_rtt": 15.8
            }
        elif protocol == ProtocolType.TCP:
            return {
                "connect_time": 25,
                "response_time": 100,
                "port_open": True
            }
        else:
            return {"success": True}


class TestSystemIntegration:
    """系统集成测试"""
    
    @pytest.fixture
    def db_manager(self):
        """创建数据库管理器"""
        manager = DatabaseManager()
        manager.initialize(test_mode=True)
        return manager
    
    @pytest.mark.asyncio
    async def test_data_consistency_across_operations(self, db_manager):
        """测试跨操作的数据一致性"""
        await db_manager.create_tables()
        
        try:
            async with db_manager.get_async_session() as session:
                # 创建用户
                user = User(
                    username="consistency_user",
                    email="consistency@test.com",
                    password_hash=pwd_context.hash("testpass"),
                    role=UserRole.ENTERPRISE,
                    credits=500.0
                )
                session.add(user)
                await session.commit()
                await session.refresh(user)
                
                # 记录初始点数
                initial_credits = user.credits
                
                # 创建多个任务并执行
                total_consumption = 0.0
                for i in range(5):
                    # 创建任务
                    task = Task(
                        user_id=user.id,
                        name=f"Consistency Task {i}",
                        protocol=ProtocolType.HTTP,
                        target=f"test{i}.example.com",
                        port=80,
                        parameters={"method": "GET"},
                        frequency=300,
                        status=TaskStatus.ACTIVE
                    )
                    session.add(task)
                    await session.commit()
                    await session.refresh(task)
                    
                    # 模拟任务执行和点数消费
                    consumption_amount = 2.0  # 每个任务消费2点数
                    
                    # 创建消费记录
                    consumption = CreditTransaction(
                        user_id=user.id,
                        amount=-consumption_amount,
                        type=TransactionType.CONSUMPTION,
                        description=f"执行任务 {task.name}",
                        reference_id=str(task.id)
                    )
                    session.add(consumption)
                    
                    # 更新用户点数
                    user.credits -= consumption_amount
                    total_consumption += consumption_amount
                
                await session.commit()
                
                # 验证数据一致性
                from sqlalchemy import select, func
                
                # 验证用户点数
                expected_credits = initial_credits - total_consumption
                assert user.credits == expected_credits
                
                # 验证交易记录总和
                transaction_sum_stmt = select(
                    func.sum(CreditTransaction.amount)
                ).where(CreditTransaction.user_id == user.id)
                
                result = await session.execute(transaction_sum_stmt)
                transaction_sum = result.scalar() or 0.0
                
                assert abs(transaction_sum + total_consumption) < 0.01  # 消费记录为负数
                
                # 验证任务数量
                task_count_stmt = select(func.count(Task.id)).where(Task.user_id == user.id)
                result = await session.execute(task_count_stmt)
                task_count = result.scalar()
                
                assert task_count == 5
                
        finally:
            await db_manager.drop_tables()
            await db_manager.close()
    
    @pytest.mark.asyncio
    async def test_concurrent_operations_integrity(self, db_manager):
        """测试并发操作的完整性"""
        await db_manager.create_tables()
        
        try:
            # 创建共享用户
            async with db_manager.get_async_session() as session:
                user = User(
                    username="concurrent_user",
                    email="concurrent@test.com",
                    password_hash=pwd_context.hash("testpass"),
                    role=UserRole.ENTERPRISE,
                    credits=1000.0
                )
                session.add(user)
                await session.commit()
                await session.refresh(user)
                user_id = user.id
            
            # 并发执行多个操作
            async def concurrent_operation(operation_id):
                async with db_manager.get_async_session() as session:
                    # 创建任务
                    task = Task(
                        user_id=user_id,
                        name=f"Concurrent Task {operation_id}",
                        protocol=ProtocolType.HTTP,
                        target=f"concurrent{operation_id}.example.com",
                        port=80,
                        parameters={"method": "GET"},
                        frequency=300,
                        status=TaskStatus.ACTIVE
                    )
                    session.add(task)
                    await session.commit()
                    await session.refresh(task)
                    
                    # 创建任务结果
                    result = TaskResult(
                        task_id=task.id,
                        agent_id=uuid.uuid4(),  # 模拟代理ID
                        execution_time=datetime.utcnow(),
                        duration=100.0 + operation_id,
                        status="success",
                        metrics={"response_time": 100 + operation_id},
                        raw_data={"operation_id": operation_id}
                    )
                    session.add(result)
                    await session.commit()
                    
                    return task.id
            
            # 并发执行20个操作
            concurrent_count = 20
            operation_tasks = [concurrent_operation(i) for i in range(concurrent_count)]
            task_ids = await asyncio.gather(*operation_tasks)
            
            # 验证所有操作都成功
            assert len(task_ids) == concurrent_count
            assert len(set(task_ids)) == concurrent_count  # 所有任务ID唯一
            
            # 验证数据库状态
            async with db_manager.get_async_session() as session:
                from sqlalchemy import select, func
                
                # 验证任务数量
                task_count_stmt = select(func.count(Task.id)).where(Task.user_id == user_id)
                result = await session.execute(task_count_stmt)
                task_count = result.scalar()
                
                # 验证任务结果数量
                result_count_stmt = select(func.count(TaskResult.id))
                result = await session.execute(result_count_stmt)
                result_count = result.scalar()
                
                assert task_count == concurrent_count
                assert result_count == concurrent_count
                
        finally:
            await db_manager.drop_tables()
            await db_manager.close()