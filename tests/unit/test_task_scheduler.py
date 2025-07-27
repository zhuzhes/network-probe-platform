"""任务调度器单元测试"""

import pytest
import asyncio
import uuid
from datetime import datetime, timedelta
from unittest.mock import Mock, patch, AsyncMock

from management_platform.scheduler.scheduler import TaskScheduler
from management_platform.scheduler.queue import QueuedTask, TaskPriority
from shared.models.task import Task, TaskStatus, TaskResult, TaskResultStatus, ProtocolType
from shared.models.agent import Agent, AgentStatus


@pytest.fixture
def sample_task():
    """创建示例任务"""
    task = Mock(spec=Task)
    task.id = uuid.uuid4()
    task.name = "测试任务"
    task.protocol = ProtocolType.HTTP
    task.target = "example.com"
    task.frequency = 60
    task.status = TaskStatus.ACTIVE
    task.next_run = datetime.utcnow()
    task.priority = 1
    task.update_next_run = Mock()
    return task


@pytest.fixture
def sample_agent():
    """创建示例代理"""
    agent = Mock(spec=Agent)
    agent.id = uuid.uuid4()
    agent.name = "测试代理"
    agent.status = AgentStatus.ONLINE
    agent.current_cpu_usage = 50.0
    agent.current_memory_usage = 60.0
    agent.max_concurrent_tasks = 10
    return agent


@pytest.fixture
def scheduler():
    """创建调度器实例"""
    return TaskScheduler(
        max_concurrent_tasks=5,
        check_interval=1,
        task_timeout=30
    )


class TestTaskScheduler:
    """TaskScheduler测试类"""
    
    def test_scheduler_creation(self):
        """测试调度器创建"""
        scheduler = TaskScheduler(
            max_concurrent_tasks=10,
            check_interval=5,
            task_timeout=60
        )
        
        assert scheduler.max_concurrent_tasks == 10
        assert scheduler.check_interval == 5
        assert scheduler.task_timeout == 60
        assert scheduler._running is False
        assert len(scheduler._executing_tasks) == 0
    
    @pytest.mark.asyncio
    async def test_scheduler_lifecycle(self, scheduler):
        """测试调度器生命周期"""
        # 启动调度器
        await scheduler.start()
        assert scheduler._running is True
        assert scheduler._scheduler_task is not None
        assert scheduler._cleanup_task is not None
        
        # 停止调度器
        await scheduler.stop()
        assert scheduler._running is False
    
    @pytest.mark.asyncio
    async def test_calculate_task_priority(self, scheduler, sample_task):
        """测试任务优先级计算"""
        # 基础优先级
        sample_task.priority = 1
        sample_task.frequency = 300
        sample_task.next_run = datetime.utcnow()
        
        priority = scheduler._calculate_task_priority(sample_task)
        assert priority >= 0
        assert priority <= TaskPriority.URGENT.value
        
        # 高频任务应该有更高优先级
        sample_task.frequency = 30
        high_freq_priority = scheduler._calculate_task_priority(sample_task)
        assert high_freq_priority >= priority
        
        # 延迟任务应该有更高优先级
        sample_task.next_run = datetime.utcnow() - timedelta(minutes=10)
        delayed_priority = scheduler._calculate_task_priority(sample_task)
        assert delayed_priority >= priority
    
    @pytest.mark.asyncio
    @patch('management_platform.scheduler.scheduler.get_db_session')
    async def test_schedule_pending_tasks(self, mock_db_session, scheduler, sample_task):
        """测试调度待执行任务"""
        # 模拟数据库会话
        mock_db = Mock()
        mock_db_session.return_value.__aenter__.return_value = mock_db
        mock_db.query.return_value.filter.return_value.limit.return_value.all.return_value = [sample_task]
        
        # 模拟队列操作
        scheduler.queue_manager.main_queue.contains = AsyncMock(return_value=False)
        scheduler.queue_manager.enqueue_task = AsyncMock(return_value=True)
        
        await scheduler._schedule_pending_tasks()
        
        # 验证任务被加入队列
        scheduler.queue_manager.enqueue_task.assert_called_once()
        sample_task.update_next_run.assert_called_once()
    
    @pytest.mark.asyncio
    async def test_execute_task(self, scheduler, sample_task, sample_agent):
        """测试执行任务"""
        # 创建队列任务
        queued_task = QueuedTask(
            task=sample_task,
            priority=TaskPriority.NORMAL.value,
            scheduled_time=datetime.utcnow()
        )
        
        # 模拟代理选择
        scheduler.task_allocator.select_agent = AsyncMock(return_value=sample_agent)
        scheduler._send_task_to_agent = AsyncMock()
        
        success = await scheduler._execute_task(queued_task)
        
        assert success is True
        assert queued_task.assigned_agent_id == sample_agent.id
        assert sample_task.id in scheduler._executing_tasks
        assert sample_task.id in scheduler._task_start_times
        
        scheduler._send_task_to_agent.assert_called_once_with(sample_task, sample_agent)
    
    @pytest.mark.asyncio
    async def test_execute_task_no_agent(self, scheduler, sample_task):
        """测试无可用代理时的任务执行"""
        queued_task = QueuedTask(
            task=sample_task,
            priority=TaskPriority.NORMAL.value,
            scheduled_time=datetime.utcnow()
        )
        
        # 模拟无可用代理
        scheduler.task_allocator.select_agent = AsyncMock(return_value=None)
        
        success = await scheduler._execute_task(queued_task)
        
        assert success is False
        assert sample_task.id not in scheduler._executing_tasks
    
    @pytest.mark.asyncio
    @patch('management_platform.scheduler.scheduler.get_db_session')
    async def test_handle_task_result(self, mock_db_session, scheduler, sample_task, sample_agent):
        """测试处理任务结果"""
        # 模拟数据库会话
        mock_db = Mock()
        mock_db_session.return_value.__aenter__.return_value = mock_db
        
        # 添加执行中的任务
        queued_task = QueuedTask(
            task=sample_task,
            priority=TaskPriority.NORMAL.value,
            scheduled_time=datetime.utcnow()
        )
        scheduler._executing_tasks[sample_task.id] = queued_task
        scheduler._task_start_times[sample_task.id] = datetime.utcnow()
        
        await scheduler.handle_task_result(
            task_id=sample_task.id,
            agent_id=sample_agent.id,
            status=TaskResultStatus.SUCCESS,
            duration=1000.0,
            metrics={'response_time': 100.0}
        )
        
        # 验证任务从执行列表中移除
        assert sample_task.id not in scheduler._executing_tasks
        assert sample_task.id not in scheduler._task_start_times
        
        # 验证结果保存到数据库
        mock_db.add.assert_called_once()
        mock_db.commit.assert_called_once()
        
        # 验证统计信息更新
        assert scheduler._stats['total_executed'] == 1
    
    @pytest.mark.asyncio
    async def test_handle_task_timeout(self, scheduler, sample_task, sample_agent):
        """测试处理任务超时"""
        # 添加执行中的任务
        queued_task = QueuedTask(
            task=sample_task,
            priority=TaskPriority.NORMAL.value,
            scheduled_time=datetime.utcnow()
        )
        queued_task.assigned_agent_id = sample_agent.id
        scheduler._executing_tasks[sample_task.id] = queued_task
        scheduler._task_start_times[sample_task.id] = datetime.utcnow() - timedelta(seconds=100)
        
        # 模拟处理任务结果
        scheduler.handle_task_result = AsyncMock()
        
        await scheduler._handle_task_timeout(sample_task.id)
        
        # 验证超时结果被处理
        scheduler.handle_task_result.assert_called_once_with(
            task_id=sample_task.id,
            agent_id=sample_agent.id,
            status=TaskResultStatus.TIMEOUT,
            duration=scheduler.task_timeout * 1000,
            error_message="任务执行超时"
        )
    
    @pytest.mark.asyncio
    async def test_cleanup_timeout_tasks(self, scheduler, sample_task):
        """测试清理超时任务"""
        # 添加超时任务
        scheduler._task_start_times[sample_task.id] = datetime.utcnow() - timedelta(seconds=500)
        scheduler._handle_task_timeout = AsyncMock()
        
        await scheduler._cleanup_timeout_tasks()
        
        scheduler._handle_task_timeout.assert_called_once_with(sample_task.id)
    
    @pytest.mark.asyncio
    @patch('management_platform.scheduler.scheduler.get_db_session')
    async def test_pause_task(self, mock_db_session, scheduler, sample_task):
        """测试暂停任务"""
        # 模拟数据库会话
        mock_db = Mock()
        mock_db_session.return_value.__aenter__.return_value = mock_db
        mock_db.query.return_value.filter.return_value.first.return_value = sample_task
        
        # 模拟队列操作
        scheduler.queue_manager.remove_task = AsyncMock(return_value=True)
        
        success = await scheduler.pause_task(sample_task.id)
        
        assert success is True
        scheduler.queue_manager.remove_task.assert_called_once_with(sample_task.id)
        sample_task.pause.assert_called_once()
        mock_db.commit.assert_called_once()
    
    @pytest.mark.asyncio
    @patch('management_platform.scheduler.scheduler.get_db_session')
    async def test_resume_task(self, mock_db_session, scheduler, sample_task):
        """测试恢复任务"""
        # 模拟数据库会话
        mock_db = Mock()
        mock_db_session.return_value.__aenter__.return_value = mock_db
        mock_db.query.return_value.filter.return_value.first.return_value = sample_task
        sample_task.status = TaskStatus.PAUSED
        
        success = await scheduler.resume_task(sample_task.id)
        
        assert success is True
        sample_task.resume.assert_called_once()
        mock_db.commit.assert_called_once()
    
    @pytest.mark.asyncio
    async def test_cancel_task(self, scheduler, sample_task):
        """测试取消任务"""
        # 添加执行中的任务
        queued_task = QueuedTask(
            task=sample_task,
            priority=TaskPriority.NORMAL.value,
            scheduled_time=datetime.utcnow()
        )
        scheduler._executing_tasks[sample_task.id] = queued_task
        scheduler._task_start_times[sample_task.id] = datetime.utcnow()
        
        # 模拟队列操作
        scheduler.queue_manager.remove_task = AsyncMock(return_value=True)
        
        success = await scheduler.cancel_task(sample_task.id)
        
        assert success is True
        assert sample_task.id not in scheduler._executing_tasks
        assert sample_task.id not in scheduler._task_start_times
        scheduler.queue_manager.remove_task.assert_called_once_with(sample_task.id)
    
    @pytest.mark.asyncio
    async def test_get_scheduler_status(self, scheduler):
        """测试获取调度器状态"""
        # 模拟队列统计
        scheduler.queue_manager.get_queue_statistics = AsyncMock(return_value={
            'main_queue': {'total_tasks': 5},
            'retry_queue_size': 2,
            'delayed_queue_size': 1
        })
        
        status = await scheduler.get_scheduler_status()
        
        assert 'running' in status
        assert 'executing_tasks' in status
        assert 'max_concurrent_tasks' in status
        assert 'queue_statistics' in status
        assert 'execution_statistics' in status
        assert status['max_concurrent_tasks'] == scheduler.max_concurrent_tasks
    
    @pytest.mark.asyncio
    async def test_get_executing_tasks(self, scheduler, sample_task, sample_agent):
        """测试获取执行中任务列表"""
        # 添加执行中的任务
        queued_task = QueuedTask(
            task=sample_task,
            priority=TaskPriority.HIGH.value,
            scheduled_time=datetime.utcnow()
        )
        queued_task.assigned_agent_id = sample_agent.id
        scheduler._executing_tasks[sample_task.id] = queued_task
        scheduler._task_start_times[sample_task.id] = datetime.utcnow()
        
        executing_tasks = await scheduler.get_executing_tasks()
        
        assert len(executing_tasks) == 1
        task_info = executing_tasks[0]
        assert task_info['task_id'] == str(sample_task.id)
        assert task_info['task_name'] == sample_task.name
        assert task_info['agent_id'] == str(sample_agent.id)
        assert task_info['priority'] == TaskPriority.HIGH.value
        assert 'start_time' in task_info
        assert 'execution_duration' in task_info
    
    @pytest.mark.asyncio
    @patch('management_platform.scheduler.scheduler.get_db_session')
    async def test_update_task_priority(self, mock_db_session, scheduler, sample_task):
        """测试更新任务优先级"""
        # 模拟数据库会话
        mock_db = Mock()
        mock_db_session.return_value.__aenter__.return_value = mock_db
        mock_db.query.return_value.filter.return_value.first.return_value = sample_task
        
        # 模拟优先级队列
        scheduler.queue_manager.main_queue.update_priority = AsyncMock(return_value=True)
        
        new_priority = TaskPriority.HIGH.value
        success = await scheduler.update_task_priority(sample_task.id, new_priority)
        
        assert success is True
        assert sample_task.priority == new_priority
        mock_db.commit.assert_called_once()
    
    @pytest.mark.asyncio
    @patch('management_platform.scheduler.scheduler.get_db_session')
    async def test_force_execute_task(self, mock_db_session, scheduler, sample_task):
        """测试强制执行任务"""
        # 模拟数据库会话
        mock_db = Mock()
        mock_db_session.return_value.__aenter__.return_value = mock_db
        mock_db.query.return_value.filter.return_value.first.return_value = sample_task
        
        # 模拟任务执行
        scheduler._execute_task = AsyncMock(return_value=True)
        
        success = await scheduler.force_execute_task(sample_task.id)
        
        assert success is True
        scheduler._execute_task.assert_called_once()
        
        # 验证使用了紧急优先级
        call_args = scheduler._execute_task.call_args[0][0]
        assert call_args.priority == TaskPriority.URGENT.value
    
    @pytest.mark.asyncio
    async def test_process_queued_tasks(self, scheduler, sample_task):
        """测试处理队列任务"""
        # 创建队列任务
        queued_task = QueuedTask(
            task=sample_task,
            priority=TaskPriority.NORMAL.value,
            scheduled_time=datetime.utcnow()
        )
        
        # 模拟队列操作
        scheduler.queue_manager.dequeue_task = AsyncMock(side_effect=[queued_task, None])
        scheduler._execute_task = AsyncMock(return_value=True)
        
        await scheduler._process_queued_tasks()
        
        scheduler._execute_task.assert_called_once_with(queued_task)
    
    @pytest.mark.asyncio
    async def test_process_queued_tasks_max_concurrent(self, scheduler, sample_task):
        """测试达到最大并发数时的队列处理"""
        # 填满执行任务列表
        for i in range(scheduler.max_concurrent_tasks):
            task_id = uuid.uuid4()
            scheduler._executing_tasks[task_id] = Mock()
        
        # 模拟队列操作
        scheduler.queue_manager.dequeue_task = AsyncMock()
        
        await scheduler._process_queued_tasks()
        
        # 不应该尝试获取新任务
        scheduler.queue_manager.dequeue_task.assert_not_called()
    
    @pytest.mark.asyncio
    async def test_process_queued_tasks_execution_failure(self, scheduler, sample_task):
        """测试任务执行失败时的处理"""
        queued_task = QueuedTask(
            task=sample_task,
            priority=TaskPriority.NORMAL.value,
            scheduled_time=datetime.utcnow()
        )
        
        # 模拟执行失败
        scheduler.queue_manager.dequeue_task = AsyncMock(return_value=queued_task)
        scheduler._execute_task = AsyncMock(return_value=False)
        scheduler.queue_manager.retry_task = AsyncMock(return_value=True)
        
        await scheduler._process_queued_tasks()
        
        scheduler._execute_task.assert_called_once_with(queued_task)
        scheduler.queue_manager.retry_task.assert_called_once_with(queued_task, delay_seconds=60)


if __name__ == "__main__":
    pytest.main([__file__])