"""任务仓库测试"""

import pytest
import uuid
from datetime import datetime, timedelta

from management_platform.database.repositories import TaskRepository, TaskResultRepository
from shared.models.task import Task, TaskResult, ProtocolType, TaskStatus, TaskResultStatus
from shared.models.user import User


def generate_unique_task_name():
    """生成唯一的任务名称"""
    return f"test_task_{uuid.uuid4().hex[:8]}"


class TestTaskRepository:
    """任务仓库测试类"""
    
    @pytest.mark.asyncio
    async def test_create_task(self, db_session):
        """测试创建任务"""
        repo = TaskRepository(db_session)
        
        # 先创建用户
        user = User(
            username=f"testuser_{uuid.uuid4().hex[:8]}",
            email=f"test_{uuid.uuid4().hex[:8]}@example.com",
            password_hash="hashed_password"
        )
        db_session.add(user)
        if hasattr(db_session, 'execute'):
            await db_session.flush()
        else:
            db_session.flush()
        
        task_name = generate_unique_task_name()
        task_data = {
            "user_id": user.id,
            "name": task_name,
            "description": "Test task description",
            "protocol": ProtocolType.HTTP,
            "target": "example.com",
            "port": 80,
            "frequency": 60,
            "timeout": 30
        }
        
        task = await repo.create(task_data)
        
        assert task.id is not None
        assert task.name == task_name
        assert task.protocol == ProtocolType.HTTP
        assert task.target == "example.com"
        assert task.port == 80
        assert task.frequency == 60
        assert task.timeout == 30
        assert task.status == TaskStatus.ACTIVE
    
    @pytest.mark.asyncio
    async def test_get_task_by_id(self, db_session):
        """测试根据ID获取任务"""
        repo = TaskRepository(db_session)
        
        # 先创建用户
        user = User(
            username=f"testuser_{uuid.uuid4().hex[:8]}",
            email=f"test_{uuid.uuid4().hex[:8]}@example.com",
            password_hash="hashed_password"
        )
        db_session.add(user)
        if hasattr(db_session, 'execute'):
            await db_session.flush()
        else:
            db_session.flush()
        
        # 创建任务
        task_data = {
            "user_id": user.id,
            "name": "Test Task",
            "protocol": ProtocolType.ICMP,
            "target": "8.8.8.8",
            "frequency": 30,
            "timeout": 10
        }
        created_task = await repo.create(task_data)
        
        # 获取任务
        found_task = await repo.get_by_id(created_task.id)
        
        assert found_task is not None
        assert found_task.id == created_task.id
        assert found_task.name == "Test Task"
        assert found_task.protocol == ProtocolType.ICMP
        assert found_task.target == "8.8.8.8"
    
    @pytest.mark.asyncio
    async def test_get_tasks_by_user_id(self, db_session):
        """测试获取用户的任务列表"""
        repo = TaskRepository(db_session)
        
        # 创建用户
        user = User(
            username=f"testuser_{uuid.uuid4().hex[:8]}",
            email=f"test_{uuid.uuid4().hex[:8]}@example.com",
            password_hash="hashed_password"
        )
        db_session.add(user)
        if hasattr(db_session, 'execute'):
            await db_session.flush()
        else:
            db_session.flush()
        
        # 创建多个任务
        tasks_data = [
            {
                "user_id": user.id,
                "name": "Task 1",
                "protocol": ProtocolType.HTTP,
                "target": "example1.com",
                "frequency": 60,
                "timeout": 30
            },
            {
                "user_id": user.id,
                "name": "Task 2",
                "protocol": ProtocolType.HTTPS,
                "target": "example2.com",
                "frequency": 120,
                "timeout": 30
            }
        ]
        
        for task_data in tasks_data:
            await repo.create(task_data)
        
        # 获取用户的任务
        user_tasks = await repo.get_by_user_id(user.id)
        
        assert len(user_tasks) == 2
        task_names = [task.name for task in user_tasks]
        assert "Task 1" in task_names
        assert "Task 2" in task_names
    
    @pytest.mark.asyncio
    async def test_update_task(self, db_session):
        """测试更新任务"""
        repo = TaskRepository(db_session)
        
        # 创建用户
        user = User(
            username=f"testuser_{uuid.uuid4().hex[:8]}",
            email=f"test_{uuid.uuid4().hex[:8]}@example.com",
            password_hash="hashed_password"
        )
        db_session.add(user)
        if hasattr(db_session, 'execute'):
            await db_session.flush()
        else:
            db_session.flush()
        
        # 创建任务
        task_data = {
            "user_id": user.id,
            "name": "Original Task",
            "protocol": ProtocolType.HTTP,
            "target": "example.com",
            "frequency": 60,
            "timeout": 30
        }
        created_task = await repo.create(task_data)
        original_updated_at = created_task.updated_at
        
        # 更新任务
        update_data = {
            "name": "Updated Task",
            "frequency": 120,
            "description": "Updated description"
        }
        updated_task = await repo.update(created_task.id, update_data)
        
        assert updated_task is not None
        assert updated_task.name == "Updated Task"
        assert updated_task.frequency == 120
        assert updated_task.description == "Updated description"
        assert updated_task.updated_at > original_updated_at
    
    @pytest.mark.asyncio
    async def test_delete_task(self, db_session):
        """测试删除任务"""
        repo = TaskRepository(db_session)
        
        # 创建用户
        user = User(
            username=f"testuser_{uuid.uuid4().hex[:8]}",
            email=f"test_{uuid.uuid4().hex[:8]}@example.com",
            password_hash="hashed_password"
        )
        db_session.add(user)
        if hasattr(db_session, 'execute'):
            await db_session.flush()
        else:
            db_session.flush()
        
        # 创建任务
        task_data = {
            "user_id": user.id,
            "name": "Task to Delete",
            "protocol": ProtocolType.TCP,
            "target": "example.com",
            "port": 22,
            "frequency": 60,
            "timeout": 30
        }
        created_task = await repo.create(task_data)
        
        # 删除任务
        result = await repo.delete(created_task.id)
        assert result is True
        
        # 验证任务已删除
        found_task = await repo.get_by_id(created_task.id)
        assert found_task is None
    
    @pytest.mark.asyncio
    async def test_get_tasks_by_status(self, db_session):
        """测试根据状态获取任务"""
        repo = TaskRepository(db_session)
        
        # 创建用户
        user = User(
            username=f"testuser_{uuid.uuid4().hex[:8]}",
            email=f"test_{uuid.uuid4().hex[:8]}@example.com",
            password_hash="hashed_password"
        )
        db_session.add(user)
        if hasattr(db_session, 'execute'):
            await db_session.flush()
        else:
            db_session.flush()
        
        # 创建不同状态的任务
        tasks_data = [
            {
                "user_id": user.id,
                "name": "Active Task",
                "protocol": ProtocolType.HTTP,
                "target": "example.com",
                "frequency": 60,
                "timeout": 30,
                "status": TaskStatus.ACTIVE
            },
            {
                "user_id": user.id,
                "name": "Paused Task",
                "protocol": ProtocolType.HTTPS,
                "target": "example.com",
                "frequency": 60,
                "timeout": 30,
                "status": TaskStatus.PAUSED
            }
        ]
        
        for task_data in tasks_data:
            await repo.create(task_data)
        
        # 获取活跃任务
        active_tasks = await repo.get_by_status(TaskStatus.ACTIVE)
        assert len(active_tasks) >= 1
        assert all(task.status == TaskStatus.ACTIVE for task in active_tasks)
        
        # 获取暂停任务
        paused_tasks = await repo.get_by_status(TaskStatus.PAUSED)
        assert len(paused_tasks) >= 1
        assert all(task.status == TaskStatus.PAUSED for task in paused_tasks)
    
    @pytest.mark.asyncio
    async def test_get_executable_tasks(self, db_session):
        """测试获取可执行任务"""
        repo = TaskRepository(db_session)
        
        # 创建用户
        user = User(
            username=f"testuser_{uuid.uuid4().hex[:8]}",
            email=f"test_{uuid.uuid4().hex[:8]}@example.com",
            password_hash="hashed_password"
        )
        db_session.add(user)
        if hasattr(db_session, 'execute'):
            await db_session.flush()
        else:
            db_session.flush()
        
        current_time = datetime.utcnow()
        
        # 创建不同执行时间的任务
        tasks_data = [
            {
                "user_id": user.id,
                "name": "Ready Task",
                "protocol": ProtocolType.HTTP,
                "target": "example.com",
                "frequency": 60,
                "timeout": 30,
                "status": TaskStatus.ACTIVE,
                "next_run": current_time - timedelta(minutes=1)  # 应该执行
            },
            {
                "user_id": user.id,
                "name": "Future Task",
                "protocol": ProtocolType.HTTPS,
                "target": "example.com",
                "frequency": 60,
                "timeout": 30,
                "status": TaskStatus.ACTIVE,
                "next_run": current_time + timedelta(minutes=1)  # 不应该执行
            },
            {
                "user_id": user.id,
                "name": "No Schedule Task",
                "protocol": ProtocolType.ICMP,
                "target": "8.8.8.8",
                "frequency": 60,
                "timeout": 30,
                "status": TaskStatus.ACTIVE,
                "next_run": None  # 应该执行
            }
        ]
        
        for task_data in tasks_data:
            await repo.create(task_data)
        
        # 获取可执行任务
        executable_tasks = await repo.get_executable_tasks()
        
        # 应该包含Ready Task和No Schedule Task
        executable_names = [task.name for task in executable_tasks]
        assert "Ready Task" in executable_names
        assert "No Schedule Task" in executable_names
        assert "Future Task" not in executable_names
    
    @pytest.mark.asyncio
    async def test_search_tasks(self, db_session):
        """测试搜索任务"""
        repo = TaskRepository(db_session)
        
        # 创建用户
        user = User(
            username=f"testuser_{uuid.uuid4().hex[:8]}",
            email=f"test_{uuid.uuid4().hex[:8]}@example.com",
            password_hash="hashed_password"
        )
        db_session.add(user)
        if hasattr(db_session, 'execute'):
            await db_session.flush()
        else:
            db_session.flush()
        
        # 创建任务
        tasks_data = [
            {
                "user_id": user.id,
                "name": "HTTP Monitor",
                "description": "Monitor HTTP service",
                "protocol": ProtocolType.HTTP,
                "target": "api.example.com",
                "frequency": 60,
                "timeout": 30
            },
            {
                "user_id": user.id,
                "name": "Database Check",
                "description": "Check database connectivity",
                "protocol": ProtocolType.TCP,
                "target": "db.example.com",
                "port": 5432,
                "frequency": 120,
                "timeout": 30
            }
        ]
        
        for task_data in tasks_data:
            await repo.create(task_data)
        
        # 搜索任务
        http_results = await repo.search("HTTP")
        assert len(http_results) >= 1
        assert any("HTTP" in task.name for task in http_results)
        
        database_results = await repo.search("database")
        assert len(database_results) >= 1
        assert any("Database" in task.name for task in database_results)
        
        example_results = await repo.search("example.com")
        assert len(example_results) >= 2
    
    @pytest.mark.asyncio
    async def test_count_tasks(self, db_session):
        """测试任务计数"""
        repo = TaskRepository(db_session)
        
        # 创建用户
        user = User(
            username=f"testuser_{uuid.uuid4().hex[:8]}",
            email=f"test_{uuid.uuid4().hex[:8]}@example.com",
            password_hash="hashed_password"
        )
        db_session.add(user)
        if hasattr(db_session, 'execute'):
            await db_session.flush()
        else:
            db_session.flush()
        
        initial_count = await repo.count(user_id=user.id)
        
        # 创建任务
        task_data = {
            "user_id": user.id,
            "name": "Count Test Task",
            "protocol": ProtocolType.HTTP,
            "target": "example.com",
            "frequency": 60,
            "timeout": 30
        }
        await repo.create(task_data)
        
        new_count = await repo.count(user_id=user.id)
        assert new_count == initial_count + 1
    
    @pytest.mark.asyncio
    async def test_batch_operations(self, db_session):
        """测试批量操作"""
        repo = TaskRepository(db_session)
        
        # 创建用户
        user = User(
            username=f"testuser_{uuid.uuid4().hex[:8]}",
            email=f"test_{uuid.uuid4().hex[:8]}@example.com",
            password_hash="hashed_password"
        )
        db_session.add(user)
        if hasattr(db_session, 'execute'):
            await db_session.flush()
        else:
            db_session.flush()
        
        # 创建多个任务
        task_ids = []
        for i in range(3):
            task_data = {
                "user_id": user.id,
                "name": f"Batch Task {i}",
                "protocol": ProtocolType.HTTP,
                "target": f"example{i}.com",
                "frequency": 60,
                "timeout": 30
            }
            task = await repo.create(task_data)
            task_ids.append(task.id)
        
        # 批量暂停任务
        paused_count = await repo.pause_tasks_batch(task_ids)
        assert paused_count == 3
        
        # 验证任务已暂停
        for task_id in task_ids:
            task = await repo.get_by_id(task_id)
            assert task.status == TaskStatus.PAUSED
            assert task.next_run is None
        
        # 批量恢复任务
        resumed_count = await repo.resume_tasks_batch(task_ids)
        assert resumed_count == 3
        
        # 验证任务已恢复
        for task_id in task_ids:
            task = await repo.get_by_id(task_id)
            assert task.status == TaskStatus.ACTIVE
            assert task.next_run is not None


class TestTaskResultRepository:
    """任务结果仓库测试类"""
    
    @pytest.mark.asyncio
    async def test_create_task_result(self, db_session):
        """测试创建任务结果"""
        task_repo = TaskRepository(db_session)
        result_repo = TaskResultRepository(db_session)
        
        # 创建用户
        user = User(
            username=f"testuser_{uuid.uuid4().hex[:8]}",
            email=f"test_{uuid.uuid4().hex[:8]}@example.com",
            password_hash="hashed_password"
        )
        db_session.add(user)
        if hasattr(db_session, 'execute'):
            await db_session.flush()
        else:
            db_session.flush()
        
        # 创建任务
        task_data = {
            "user_id": user.id,
            "name": "Test Task",
            "protocol": ProtocolType.HTTP,
            "target": "example.com",
            "frequency": 60,
            "timeout": 30
        }
        task = await task_repo.create(task_data)
        
        # 创建代理（简化，直接使用UUID）
        agent_id = uuid.uuid4()
        
        # 创建任务结果
        result_data = {
            "task_id": task.id,
            "agent_id": agent_id,
            "execution_time": datetime.utcnow(),
            "duration": 150.5,
            "status": TaskResultStatus.SUCCESS,
            "metrics": {"response_time": 150.5, "status_code": 200},
            "raw_data": {"headers": {"content-type": "text/html"}}
        }
        
        result = await result_repo.create(result_data)
        
        assert result.id is not None
        assert result.task_id == task.id
        assert result.agent_id == agent_id
        assert result.duration == 150.5
        assert result.status == TaskResultStatus.SUCCESS
        assert result.metrics["response_time"] == 150.5
    
    @pytest.mark.asyncio
    async def test_get_results_by_task_id(self, db_session):
        """测试获取任务的结果列表"""
        task_repo = TaskRepository(db_session)
        result_repo = TaskResultRepository(db_session)
        
        # 创建用户
        user = User(
            username=f"testuser_{uuid.uuid4().hex[:8]}",
            email=f"test_{uuid.uuid4().hex[:8]}@example.com",
            password_hash="hashed_password"
        )
        db_session.add(user)
        if hasattr(db_session, 'execute'):
            await db_session.flush()
        else:
            db_session.flush()
        
        # 创建任务
        task_data = {
            "user_id": user.id,
            "name": "Test Task",
            "protocol": ProtocolType.HTTP,
            "target": "example.com",
            "frequency": 60,
            "timeout": 30
        }
        task = await task_repo.create(task_data)
        
        agent_id = uuid.uuid4()
        
        # 创建多个结果
        results_data = [
            {
                "task_id": task.id,
                "agent_id": agent_id,
                "execution_time": datetime.utcnow() - timedelta(minutes=2),
                "duration": 100.0,
                "status": TaskResultStatus.SUCCESS
            },
            {
                "task_id": task.id,
                "agent_id": agent_id,
                "execution_time": datetime.utcnow() - timedelta(minutes=1),
                "duration": 200.0,
                "status": TaskResultStatus.TIMEOUT
            }
        ]
        
        for result_data in results_data:
            await result_repo.create(result_data)
        
        # 获取任务结果
        task_results = await result_repo.get_by_task_id(task.id)
        
        assert len(task_results) == 2
        # 应该按执行时间倒序排列
        assert task_results[0].duration == 200.0  # 最新的结果
        assert task_results[1].duration == 100.0  # 较早的结果
    
    @pytest.mark.asyncio
    async def test_get_task_statistics(self, db_session):
        """测试获取任务统计信息"""
        task_repo = TaskRepository(db_session)
        result_repo = TaskResultRepository(db_session)
        
        # 创建用户
        user = User(
            username=f"testuser_{uuid.uuid4().hex[:8]}",
            email=f"test_{uuid.uuid4().hex[:8]}@example.com",
            password_hash="hashed_password"
        )
        db_session.add(user)
        if hasattr(db_session, 'execute'):
            await db_session.flush()
        else:
            db_session.flush()
        
        # 创建任务
        task_data = {
            "user_id": user.id,
            "name": "Statistics Test Task",
            "protocol": ProtocolType.HTTP,
            "target": "example.com",
            "frequency": 60,
            "timeout": 30
        }
        task = await task_repo.create(task_data)
        
        agent_id = uuid.uuid4()
        
        # 创建多个结果（成功和失败）
        results_data = [
            {
                "task_id": task.id,
                "agent_id": agent_id,
                "execution_time": datetime.utcnow() - timedelta(hours=1),
                "duration": 100.0,
                "status": TaskResultStatus.SUCCESS
            },
            {
                "task_id": task.id,
                "agent_id": agent_id,
                "execution_time": datetime.utcnow() - timedelta(minutes=30),
                "duration": 150.0,
                "status": TaskResultStatus.SUCCESS
            },
            {
                "task_id": task.id,
                "agent_id": agent_id,
                "execution_time": datetime.utcnow() - timedelta(minutes=15),
                "status": TaskResultStatus.ERROR,
                "error_message": "Connection failed"
            }
        ]
        
        for result_data in results_data:
            await result_repo.create(result_data)
        
        # 获取统计信息
        stats = await result_repo.get_task_statistics(task.id)
        
        assert stats['task_id'] == task.id
        assert stats['total_executions'] == 3
        assert stats['successful_executions'] == 2
        assert stats['failed_executions'] == 1
        assert stats['success_rate'] == 2/3
        assert stats['avg_response_time'] == 125.0  # (100 + 150) / 2
    
    @pytest.mark.asyncio
    async def test_get_recent_results(self, db_session):
        """测试获取最近的结果"""
        task_repo = TaskRepository(db_session)
        result_repo = TaskResultRepository(db_session)
        
        # 创建用户
        user = User(
            username=f"testuser_{uuid.uuid4().hex[:8]}",
            email=f"test_{uuid.uuid4().hex[:8]}@example.com",
            password_hash="hashed_password"
        )
        db_session.add(user)
        if hasattr(db_session, 'execute'):
            await db_session.flush()
        else:
            db_session.flush()
        
        # 创建任务
        task_data = {
            "user_id": user.id,
            "name": "Recent Test Task",
            "protocol": ProtocolType.HTTP,
            "target": "example.com",
            "frequency": 60,
            "timeout": 30
        }
        task = await task_repo.create(task_data)
        
        agent_id = uuid.uuid4()
        
        # 创建不同时间的结果
        results_data = [
            {
                "task_id": task.id,
                "agent_id": agent_id,
                "execution_time": datetime.utcnow() - timedelta(hours=25),  # 超过24小时
                "duration": 100.0,
                "status": TaskResultStatus.SUCCESS
            },
            {
                "task_id": task.id,
                "agent_id": agent_id,
                "execution_time": datetime.utcnow() - timedelta(hours=1),   # 最近24小时内
                "duration": 150.0,
                "status": TaskResultStatus.SUCCESS
            }
        ]
        
        for result_data in results_data:
            await result_repo.create(result_data)
        
        # 获取最近24小时的结果
        recent_results = await result_repo.get_recent_results(hours=24)
        
        # 应该只包含最近24小时内的结果
        assert len(recent_results) >= 1
        for result in recent_results:
            assert result.execution_time > datetime.utcnow() - timedelta(hours=24)
    
    @pytest.mark.asyncio
    async def test_get_latest_result_by_task(self, db_session):
        """测试获取任务的最新结果"""
        task_repo = TaskRepository(db_session)
        result_repo = TaskResultRepository(db_session)
        
        # 创建用户
        user = User(
            username=f"testuser_{uuid.uuid4().hex[:8]}",
            email=f"test_{uuid.uuid4().hex[:8]}@example.com",
            password_hash="hashed_password"
        )
        db_session.add(user)
        if hasattr(db_session, 'execute'):
            await db_session.flush()
        else:
            db_session.flush()
        
        # 创建任务
        task_data = {
            "user_id": user.id,
            "name": "Latest Result Test Task",
            "protocol": ProtocolType.HTTP,
            "target": "example.com",
            "frequency": 60,
            "timeout": 30
        }
        task = await task_repo.create(task_data)
        
        agent_id = uuid.uuid4()
        
        # 创建多个结果
        results_data = [
            {
                "task_id": task.id,
                "agent_id": agent_id,
                "execution_time": datetime.utcnow() - timedelta(minutes=5),
                "duration": 100.0,
                "status": TaskResultStatus.SUCCESS
            },
            {
                "task_id": task.id,
                "agent_id": agent_id,
                "execution_time": datetime.utcnow() - timedelta(minutes=1),
                "duration": 200.0,
                "status": TaskResultStatus.TIMEOUT
            }
        ]
        
        for result_data in results_data:
            await result_repo.create(result_data)
        
        # 获取最新结果
        latest_result = await result_repo.get_latest_result_by_task(task.id)
        
        assert latest_result is not None
        assert latest_result.duration == 200.0  # 最新的结果
        assert latest_result.status == TaskResultStatus.TIMEOUT