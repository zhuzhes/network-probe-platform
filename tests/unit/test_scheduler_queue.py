"""任务队列模块单元测试"""

import pytest
import asyncio
import uuid
from datetime import datetime, timedelta
from unittest.mock import Mock, patch

from management_platform.scheduler.queue import (
    QueuedTask, TaskQueue, PriorityTaskQueue, DelayedTaskQueue, 
    TaskQueueManager, TaskPriority
)
from shared.models.task import Task, TaskStatus, ProtocolType


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
    return task


@pytest.fixture
def queued_task(sample_task):
    """创建队列任务"""
    return QueuedTask(
        task=sample_task,
        priority=TaskPriority.NORMAL.value,
        scheduled_time=datetime.utcnow()
    )


class TestQueuedTask:
    """QueuedTask测试类"""
    
    def test_queued_task_creation(self, sample_task):
        """测试队列任务创建"""
        queued_task = QueuedTask(
            task=sample_task,
            priority=TaskPriority.HIGH.value,
            scheduled_time=datetime.utcnow()
        )
        
        assert queued_task.task == sample_task
        assert queued_task.priority == TaskPriority.HIGH.value
        assert queued_task.retry_count == 0
        assert queued_task.max_retries == 3
    
    def test_queued_task_comparison(self, sample_task):
        """测试队列任务比较"""
        now = datetime.utcnow()
        
        task1 = QueuedTask(
            task=sample_task,
            priority=TaskPriority.HIGH.value,
            scheduled_time=now
        )
        
        task2 = QueuedTask(
            task=sample_task,
            priority=TaskPriority.NORMAL.value,
            scheduled_time=now
        )
        
        # 高优先级任务应该排在前面
        assert task1 < task2
    
    def test_can_retry(self, queued_task):
        """测试重试检查"""
        assert queued_task.can_retry() is True
        
        queued_task.retry_count = 3
        assert queued_task.can_retry() is False
    
    def test_increment_retry(self, queued_task):
        """测试增加重试次数"""
        initial_count = queued_task.retry_count
        queued_task.increment_retry()
        assert queued_task.retry_count == initial_count + 1
    
    def test_is_ready_to_execute(self, queued_task):
        """测试执行就绪检查"""
        # 当前时间的任务应该准备执行
        queued_task.scheduled_time = datetime.utcnow()
        assert queued_task.is_ready_to_execute() is True
        
        # 未来时间的任务不应该执行
        queued_task.scheduled_time = datetime.utcnow() + timedelta(minutes=5)
        assert queued_task.is_ready_to_execute() is False
    
    def test_get_delay_seconds(self, queued_task):
        """测试获取延迟秒数"""
        # 当前时间任务
        queued_task.scheduled_time = datetime.utcnow()
        assert queued_task.get_delay_seconds() == 0
        
        # 未来任务
        queued_task.scheduled_time = datetime.utcnow() + timedelta(seconds=30)
        delay = queued_task.get_delay_seconds()
        assert 25 <= delay <= 35  # 允许一些时间误差


class TestTaskQueue:
    """TaskQueue测试类"""
    
    @pytest.mark.asyncio
    async def test_queue_creation(self):
        """测试队列创建"""
        queue = TaskQueue(max_size=100)
        assert await queue.size() == 0
        assert await queue.is_empty() is True
    
    @pytest.mark.asyncio
    async def test_put_and_get(self, queued_task):
        """测试添加和获取任务"""
        queue = TaskQueue()
        
        # 添加任务
        success = await queue.put(queued_task)
        assert success is True
        assert await queue.size() == 1
        assert await queue.is_empty() is False
        
        # 获取任务
        retrieved_task = await queue.get()
        assert retrieved_task == queued_task
        assert await queue.size() == 0
        assert await queue.is_empty() is True
    
    @pytest.mark.asyncio
    async def test_put_duplicate_task(self, queued_task):
        """测试添加重复任务"""
        queue = TaskQueue()
        
        # 第一次添加成功
        success1 = await queue.put(queued_task)
        assert success1 is True
        
        # 第二次添加失败
        success2 = await queue.put(queued_task)
        assert success2 is False
        assert await queue.size() == 1
    
    @pytest.mark.asyncio
    async def test_queue_max_size(self, sample_task):
        """测试队列最大容量"""
        queue = TaskQueue(max_size=2)
        
        # 添加两个任务成功
        task1 = QueuedTask(task=sample_task, priority=1, scheduled_time=datetime.utcnow())
        task2 = QueuedTask(task=sample_task, priority=1, scheduled_time=datetime.utcnow())
        task2.task.id = uuid.uuid4()  # 不同的ID
        
        assert await queue.put(task1) is True
        assert await queue.put(task2) is True
        
        # 第三个任务添加失败
        task3 = QueuedTask(task=sample_task, priority=1, scheduled_time=datetime.utcnow())
        task3.task.id = uuid.uuid4()
        assert await queue.put(task3) is False
    
    @pytest.mark.asyncio
    async def test_remove_task(self, queued_task):
        """测试移除任务"""
        queue = TaskQueue()
        
        await queue.put(queued_task)
        assert await queue.size() == 1
        
        # 移除任务
        success = await queue.remove(queued_task.task.id)
        assert success is True
        assert await queue.size() == 0
        
        # 移除不存在的任务
        success = await queue.remove(uuid.uuid4())
        assert success is False
    
    @pytest.mark.asyncio
    async def test_contains(self, queued_task):
        """测试包含检查"""
        queue = TaskQueue()
        
        assert await queue.contains(queued_task.task.id) is False
        
        await queue.put(queued_task)
        assert await queue.contains(queued_task.task.id) is True
    
    @pytest.mark.asyncio
    async def test_get_ready_tasks(self, sample_task):
        """测试获取准备执行的任务"""
        queue = TaskQueue()
        
        # 添加一个准备执行的任务
        ready_task = QueuedTask(
            task=sample_task,
            priority=1,
            scheduled_time=datetime.utcnow() - timedelta(seconds=1)
        )
        
        # 添加一个未来执行的任务
        future_task = QueuedTask(
            task=sample_task,
            priority=1,
            scheduled_time=datetime.utcnow() + timedelta(minutes=5)
        )
        future_task.task.id = uuid.uuid4()
        
        await queue.put(ready_task)
        await queue.put(future_task)
        
        ready_tasks = await queue.get_ready_tasks(limit=10)
        assert len(ready_tasks) == 1
        assert ready_tasks[0] == ready_task
    
    @pytest.mark.asyncio
    async def test_get_statistics(self, sample_task):
        """测试获取统计信息"""
        queue = TaskQueue()
        
        # 空队列统计
        stats = await queue.get_statistics()
        assert stats['total_tasks'] == 0
        assert stats['ready_tasks'] == 0
        assert stats['waiting_tasks'] == 0
        
        # 添加任务后的统计
        ready_task = QueuedTask(
            task=sample_task,
            priority=TaskPriority.HIGH.value,
            scheduled_time=datetime.utcnow()
        )
        
        future_task = QueuedTask(
            task=sample_task,
            priority=TaskPriority.NORMAL.value,
            scheduled_time=datetime.utcnow() + timedelta(minutes=5)
        )
        future_task.task.id = uuid.uuid4()
        
        await queue.put(ready_task)
        await queue.put(future_task)
        
        stats = await queue.get_statistics()
        assert stats['total_tasks'] == 2
        assert stats['ready_tasks'] == 1
        assert stats['waiting_tasks'] == 1
        assert TaskPriority.HIGH.value in stats['priority_distribution']
        assert TaskPriority.NORMAL.value in stats['priority_distribution']


class TestPriorityTaskQueue:
    """PriorityTaskQueue测试类"""
    
    @pytest.mark.asyncio
    async def test_priority_ordering(self, sample_task):
        """测试优先级排序"""
        queue = PriorityTaskQueue()
        
        # 添加不同优先级的任务
        low_task = QueuedTask(
            task=sample_task,
            priority=TaskPriority.LOW.value,
            scheduled_time=datetime.utcnow()
        )
        
        high_task = QueuedTask(
            task=sample_task,
            priority=TaskPriority.HIGH.value,
            scheduled_time=datetime.utcnow()
        )
        high_task.task.id = uuid.uuid4()
        
        normal_task = QueuedTask(
            task=sample_task,
            priority=TaskPriority.NORMAL.value,
            scheduled_time=datetime.utcnow()
        )
        normal_task.task.id = uuid.uuid4()
        
        # 按低、高、普通的顺序添加
        await queue.put(low_task)
        await queue.put(high_task)
        await queue.put(normal_task)
        
        # 应该按高、普通、低的顺序获取
        task1 = await queue.get()
        task2 = await queue.get()
        task3 = await queue.get()
        
        assert task1 == high_task
        assert task2 == normal_task
        assert task3 == low_task
    
    @pytest.mark.asyncio
    async def test_peek(self, queued_task):
        """测试查看队列顶部"""
        queue = PriorityTaskQueue()
        
        # 空队列
        assert await queue.peek() is None
        
        # 添加任务后查看
        await queue.put(queued_task)
        peeked_task = await queue.peek()
        assert peeked_task == queued_task
        
        # 查看不会移除任务
        assert await queue.size() == 1
    
    @pytest.mark.asyncio
    async def test_update_priority(self, queued_task):
        """测试更新优先级"""
        queue = PriorityTaskQueue()
        
        await queue.put(queued_task)
        
        # 更新优先级
        success = await queue.update_priority(queued_task.task.id, TaskPriority.HIGH.value)
        assert success is True
        
        # 更新不存在任务的优先级
        success = await queue.update_priority(uuid.uuid4(), TaskPriority.HIGH.value)
        assert success is False
    
    @pytest.mark.asyncio
    async def test_get_priority_statistics(self, sample_task):
        """测试获取优先级统计"""
        queue = PriorityTaskQueue()
        
        # 添加不同优先级的任务
        for priority in [TaskPriority.LOW.value, TaskPriority.HIGH.value, TaskPriority.HIGH.value]:
            task = QueuedTask(
                task=sample_task,
                priority=priority,
                scheduled_time=datetime.utcnow()
            )
            task.task.id = uuid.uuid4()
            await queue.put(task)
        
        stats = await queue.get_priority_statistics()
        
        assert TaskPriority.LOW.value in stats
        assert TaskPriority.HIGH.value in stats
        assert stats[TaskPriority.LOW.value]['total'] == 1
        assert stats[TaskPriority.HIGH.value]['total'] == 2


class TestDelayedTaskQueue:
    """DelayedTaskQueue测试类"""
    
    @pytest.mark.asyncio
    async def test_schedule_task(self, queued_task):
        """测试调度延迟任务"""
        queue = DelayedTaskQueue()
        
        # 调度延迟任务
        await queue.schedule_task(queued_task, delay_seconds=30)
        
        assert await queue.size() == 1
        
        # 检查执行时间
        next_time = await queue.get_next_execution_time()
        assert next_time is not None
        assert next_time > datetime.utcnow()
    
    @pytest.mark.asyncio
    async def test_get_ready_tasks(self, queued_task):
        """测试获取准备执行的延迟任务"""
        queue = DelayedTaskQueue()
        
        # 调度一个立即执行的任务
        await queue.schedule_task(queued_task, delay_seconds=0)
        
        # 稍等一下确保时间过去
        await asyncio.sleep(0.1)
        
        ready_tasks = await queue.get_ready_tasks()
        assert len(ready_tasks) == 1
        assert ready_tasks[0] == queued_task
        
        # 任务应该被移除
        assert await queue.size() == 0


class TestTaskQueueManager:
    """TaskQueueManager测试类"""
    
    @pytest.mark.asyncio
    async def test_manager_lifecycle(self):
        """测试管理器生命周期"""
        manager = TaskQueueManager()
        
        # 启动管理器
        await manager.start()
        assert manager._running is True
        
        # 停止管理器
        await manager.stop()
        assert manager._running is False
    
    @pytest.mark.asyncio
    async def test_enqueue_and_dequeue(self, sample_task):
        """测试入队和出队"""
        manager = TaskQueueManager()
        await manager.start()
        
        try:
            # 入队任务
            success = await manager.enqueue_task(sample_task, TaskPriority.NORMAL.value)
            assert success is True
            
            # 出队任务
            queued_task = await manager.dequeue_task()
            assert queued_task is not None
            assert queued_task.task == sample_task
            
        finally:
            await manager.stop()
    
    @pytest.mark.asyncio
    async def test_enqueue_with_delay(self, sample_task):
        """测试延迟入队"""
        manager = TaskQueueManager()
        await manager.start()
        
        try:
            # 延迟入队
            success = await manager.enqueue_task(
                sample_task, 
                TaskPriority.NORMAL.value, 
                delay_seconds=1
            )
            assert success is True
            
            # 立即出队应该为空
            queued_task = await manager.dequeue_task()
            assert queued_task is None
            
            # 等待延迟时间后应该能获取到任务
            await asyncio.sleep(1.5)
            queued_task = await manager.dequeue_task()
            assert queued_task is not None
            
        finally:
            await manager.stop()
    
    @pytest.mark.asyncio
    async def test_retry_task(self, sample_task):
        """测试重试任务"""
        manager = TaskQueueManager()
        await manager.start()
        
        try:
            # 创建队列任务
            queued_task = QueuedTask(
                task=sample_task,
                priority=TaskPriority.NORMAL.value,
                scheduled_time=datetime.utcnow()
            )
            
            # 重试任务
            success = await manager.retry_task(queued_task, delay_seconds=0)
            assert success is True
            assert queued_task.retry_count == 1
            
            # 从重试队列获取任务
            retry_task = await manager.dequeue_task()
            assert retry_task == queued_task
            
        finally:
            await manager.stop()
    
    @pytest.mark.asyncio
    async def test_remove_task(self, sample_task):
        """测试移除任务"""
        manager = TaskQueueManager()
        await manager.start()
        
        try:
            # 入队任务
            await manager.enqueue_task(sample_task, TaskPriority.NORMAL.value)
            
            # 移除任务
            success = await manager.remove_task(sample_task.id)
            assert success is True
            
            # 应该无法获取到任务
            queued_task = await manager.dequeue_task()
            assert queued_task is None
            
        finally:
            await manager.stop()
    
    @pytest.mark.asyncio
    async def test_get_queue_statistics(self, sample_task):
        """测试获取队列统计"""
        manager = TaskQueueManager()
        await manager.start()
        
        try:
            # 添加一些任务
            await manager.enqueue_task(sample_task, TaskPriority.NORMAL.value)
            
            # 获取统计信息
            stats = await manager.get_queue_statistics()
            
            assert 'main_queue' in stats
            assert 'retry_queue_size' in stats
            assert 'delayed_queue_size' in stats
            assert 'total_queued_tasks' in stats
            
        finally:
            await manager.stop()


if __name__ == "__main__":
    pytest.main([__file__])