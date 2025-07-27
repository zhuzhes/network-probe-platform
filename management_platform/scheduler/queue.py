"""任务队列管理模块"""

import asyncio
import heapq
import logging
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional, Set, Tuple
from dataclasses import dataclass, field
from enum import Enum
import uuid

from shared.models.task import Task, TaskStatus
from shared.models.agent import Agent, AgentStatus


logger = logging.getLogger(__name__)


class TaskPriority(Enum):
    """任务优先级枚举"""
    LOW = 0
    NORMAL = 1
    HIGH = 2
    URGENT = 3


@dataclass
class QueuedTask:
    """队列中的任务项"""
    task: Task
    priority: int
    scheduled_time: datetime
    retry_count: int = 0
    max_retries: int = 3
    assigned_agent_id: Optional[uuid.UUID] = None
    created_at: datetime = field(default_factory=datetime.utcnow)
    
    def __lt__(self, other):
        """用于优先级队列排序"""
        # 首先按优先级排序（数值越大优先级越高）
        if self.priority != other.priority:
            return self.priority > other.priority
        
        # 相同优先级按计划时间排序
        if self.scheduled_time != other.scheduled_time:
            return self.scheduled_time < other.scheduled_time
        
        # 最后按创建时间排序
        return self.created_at < other.created_at
    
    def can_retry(self) -> bool:
        """检查是否可以重试"""
        return self.retry_count < self.max_retries
    
    def increment_retry(self):
        """增加重试次数"""
        self.retry_count += 1
    
    def is_ready_to_execute(self) -> bool:
        """检查是否准备执行"""
        return self.scheduled_time <= datetime.utcnow()
    
    def get_delay_seconds(self) -> int:
        """获取延迟执行的秒数"""
        if self.scheduled_time <= datetime.utcnow():
            return 0
        return int((self.scheduled_time - datetime.utcnow()).total_seconds())


class TaskQueue:
    """基础任务队列"""
    
    def __init__(self, max_size: int = 10000):
        self.max_size = max_size
        self._queue: List[QueuedTask] = []
        self._task_ids: Set[uuid.UUID] = set()
        self._lock = asyncio.Lock()
        
    async def put(self, queued_task: QueuedTask) -> bool:
        """添加任务到队列"""
        async with self._lock:
            if len(self._queue) >= self.max_size:
                logger.warning(f"任务队列已满，无法添加任务 {queued_task.task.id}")
                return False
            
            if queued_task.task.id in self._task_ids:
                logger.warning(f"任务 {queued_task.task.id} 已在队列中")
                return False
            
            self._queue.append(queued_task)
            self._task_ids.add(queued_task.task.id)
            logger.debug(f"任务 {queued_task.task.id} 已添加到队列")
            return True
    
    async def get(self) -> Optional[QueuedTask]:
        """从队列获取任务"""
        async with self._lock:
            if not self._queue:
                return None
            
            # 找到第一个准备执行的任务
            for i, queued_task in enumerate(self._queue):
                if queued_task.is_ready_to_execute():
                    self._queue.pop(i)
                    self._task_ids.remove(queued_task.task.id)
                    return queued_task
            
            return None
    
    async def remove(self, task_id: uuid.UUID) -> bool:
        """从队列移除任务"""
        async with self._lock:
            for i, queued_task in enumerate(self._queue):
                if queued_task.task.id == task_id:
                    self._queue.pop(i)
                    self._task_ids.remove(task_id)
                    logger.debug(f"任务 {task_id} 已从队列移除")
                    return True
            return False
    
    async def size(self) -> int:
        """获取队列大小"""
        async with self._lock:
            return len(self._queue)
    
    async def is_empty(self) -> bool:
        """检查队列是否为空"""
        async with self._lock:
            return len(self._queue) == 0
    
    async def contains(self, task_id: uuid.UUID) -> bool:
        """检查队列是否包含指定任务"""
        async with self._lock:
            return task_id in self._task_ids
    
    async def get_ready_tasks(self, limit: int = 10) -> List[QueuedTask]:
        """获取准备执行的任务列表"""
        async with self._lock:
            ready_tasks = []
            current_time = datetime.utcnow()
            
            for queued_task in self._queue:
                if len(ready_tasks) >= limit:
                    break
                if queued_task.scheduled_time <= current_time:
                    ready_tasks.append(queued_task)
            
            return ready_tasks
    
    async def get_statistics(self) -> Dict[str, Any]:
        """获取队列统计信息"""
        async with self._lock:
            if not self._queue:
                return {
                    'total_tasks': 0,
                    'ready_tasks': 0,
                    'waiting_tasks': 0,
                    'avg_wait_time': 0,
                    'priority_distribution': {}
                }
            
            current_time = datetime.utcnow()
            ready_count = 0
            wait_times = []
            priority_counts = {}
            
            for queued_task in self._queue:
                if queued_task.scheduled_time <= current_time:
                    ready_count += 1
                
                wait_time = (current_time - queued_task.created_at).total_seconds()
                wait_times.append(wait_time)
                
                priority = queued_task.priority
                priority_counts[priority] = priority_counts.get(priority, 0) + 1
            
            avg_wait_time = sum(wait_times) / len(wait_times) if wait_times else 0
            
            return {
                'total_tasks': len(self._queue),
                'ready_tasks': ready_count,
                'waiting_tasks': len(self._queue) - ready_count,
                'avg_wait_time': avg_wait_time,
                'priority_distribution': priority_counts
            }


class PriorityTaskQueue(TaskQueue):
    """优先级任务队列"""
    
    def __init__(self, max_size: int = 10000):
        super().__init__(max_size)
        self._heap: List[QueuedTask] = []
        
    async def put(self, queued_task: QueuedTask) -> bool:
        """添加任务到优先级队列"""
        async with self._lock:
            if len(self._heap) >= self.max_size:
                logger.warning(f"优先级队列已满，无法添加任务 {queued_task.task.id}")
                return False
            
            if queued_task.task.id in self._task_ids:
                logger.warning(f"任务 {queued_task.task.id} 已在队列中")
                return False
            
            heapq.heappush(self._heap, queued_task)
            self._task_ids.add(queued_task.task.id)
            logger.debug(f"任务 {queued_task.task.id} 已添加到优先级队列，优先级: {queued_task.priority}")
            return True
    
    async def get(self) -> Optional[QueuedTask]:
        """从优先级队列获取最高优先级的准备执行任务"""
        async with self._lock:
            # 临时存储不能执行的任务
            temp_tasks = []
            
            try:
                while self._heap:
                    queued_task = heapq.heappop(self._heap)
                    
                    if queued_task.is_ready_to_execute():
                        # 将临时任务放回队列
                        for temp_task in temp_tasks:
                            heapq.heappush(self._heap, temp_task)
                        
                        self._task_ids.remove(queued_task.task.id)
                        return queued_task
                    else:
                        temp_tasks.append(queued_task)
                
                # 没有找到准备执行的任务，将所有任务放回队列
                for temp_task in temp_tasks:
                    heapq.heappush(self._heap, temp_task)
                
                return None
                
            except Exception as e:
                # 发生异常时，确保临时任务被放回队列
                for temp_task in temp_tasks:
                    heapq.heappush(self._heap, temp_task)
                logger.error(f"从优先级队列获取任务时发生错误: {e}")
                return None
    
    async def remove(self, task_id: uuid.UUID) -> bool:
        """从优先级队列移除任务"""
        async with self._lock:
            if task_id not in self._task_ids:
                return False
            
            # 重建堆，排除指定任务
            new_heap = []
            for queued_task in self._heap:
                if queued_task.task.id != task_id:
                    new_heap.append(queued_task)
            
            self._heap = new_heap
            heapq.heapify(self._heap)
            self._task_ids.remove(task_id)
            
            logger.debug(f"任务 {task_id} 已从优先级队列移除")
            return True
    
    async def size(self) -> int:
        """获取队列大小"""
        async with self._lock:
            return len(self._heap)
    
    async def is_empty(self) -> bool:
        """检查队列是否为空"""
        async with self._lock:
            return len(self._heap) == 0
    
    async def peek(self) -> Optional[QueuedTask]:
        """查看队列顶部任务但不移除"""
        async with self._lock:
            if not self._heap:
                return None
            return self._heap[0]
    
    async def get_ready_tasks(self, limit: int = 10) -> List[QueuedTask]:
        """获取准备执行的任务列表（按优先级排序）"""
        async with self._lock:
            ready_tasks = []
            current_time = datetime.utcnow()
            
            # 创建堆的副本进行遍历
            heap_copy = self._heap.copy()
            
            while heap_copy and len(ready_tasks) < limit:
                queued_task = heapq.heappop(heap_copy)
                if queued_task.scheduled_time <= current_time:
                    ready_tasks.append(queued_task)
            
            return ready_tasks
    
    async def update_priority(self, task_id: uuid.UUID, new_priority: int) -> bool:
        """更新任务优先级"""
        async with self._lock:
            if task_id not in self._task_ids:
                return False
            
            # 找到任务并更新优先级
            updated = False
            for queued_task in self._heap:
                if queued_task.task.id == task_id:
                    queued_task.priority = new_priority
                    updated = True
                    break
            
            if updated:
                # 重新构建堆以保持堆属性
                heapq.heapify(self._heap)
                logger.debug(f"任务 {task_id} 优先级已更新为 {new_priority}")
            
            return updated
    
    async def get_priority_statistics(self) -> Dict[int, Dict[str, Any]]:
        """获取按优先级分组的统计信息"""
        async with self._lock:
            priority_stats = {}
            current_time = datetime.utcnow()
            
            for queued_task in self._heap:
                priority = queued_task.priority
                if priority not in priority_stats:
                    priority_stats[priority] = {
                        'total': 0,
                        'ready': 0,
                        'waiting': 0,
                        'avg_wait_time': 0,
                        'wait_times': []
                    }
                
                stats = priority_stats[priority]
                stats['total'] += 1
                
                if queued_task.scheduled_time <= current_time:
                    stats['ready'] += 1
                else:
                    stats['waiting'] += 1
                
                wait_time = (current_time - queued_task.created_at).total_seconds()
                stats['wait_times'].append(wait_time)
            
            # 计算平均等待时间
            for priority, stats in priority_stats.items():
                if stats['wait_times']:
                    stats['avg_wait_time'] = sum(stats['wait_times']) / len(stats['wait_times'])
                del stats['wait_times']  # 删除临时数据
            
            return priority_stats


class DelayedTaskQueue:
    """延迟任务队列"""
    
    def __init__(self):
        self._delayed_tasks: List[Tuple[datetime, QueuedTask]] = []
        self._lock = asyncio.Lock()
    
    async def schedule_task(self, queued_task: QueuedTask, delay_seconds: int):
        """调度延迟任务"""
        execute_time = datetime.utcnow() + timedelta(seconds=delay_seconds)
        queued_task.scheduled_time = execute_time
        
        async with self._lock:
            heapq.heappush(self._delayed_tasks, (execute_time, queued_task))
            logger.debug(f"任务 {queued_task.task.id} 已调度，将在 {execute_time} 执行")
    
    async def get_ready_tasks(self) -> List[QueuedTask]:
        """获取准备执行的延迟任务"""
        ready_tasks = []
        current_time = datetime.utcnow()
        
        async with self._lock:
            while self._delayed_tasks:
                execute_time, queued_task = self._delayed_tasks[0]
                if execute_time <= current_time:
                    heapq.heappop(self._delayed_tasks)
                    ready_tasks.append(queued_task)
                else:
                    break
        
        return ready_tasks
    
    async def size(self) -> int:
        """获取延迟队列大小"""
        async with self._lock:
            return len(self._delayed_tasks)
    
    async def get_next_execution_time(self) -> Optional[datetime]:
        """获取下一个任务的执行时间"""
        async with self._lock:
            if not self._delayed_tasks:
                return None
            return self._delayed_tasks[0][0]


class TaskQueueManager:
    """任务队列管理器"""
    
    def __init__(self, use_priority_queue: bool = True, max_queue_size: int = 10000):
        self.use_priority_queue = use_priority_queue
        
        if use_priority_queue:
            self.main_queue = PriorityTaskQueue(max_queue_size)
        else:
            self.main_queue = TaskQueue(max_queue_size)
        
        self.delayed_queue = DelayedTaskQueue()
        self.retry_queue = TaskQueue(max_queue_size // 10)  # 重试队列较小
        
        self._running = False
        self._background_task: Optional[asyncio.Task] = None
    
    async def start(self):
        """启动队列管理器"""
        if self._running:
            return
        
        self._running = True
        self._background_task = asyncio.create_task(self._process_delayed_tasks())
        logger.info("任务队列管理器已启动")
    
    async def stop(self):
        """停止队列管理器"""
        self._running = False
        if self._background_task:
            self._background_task.cancel()
            try:
                await self._background_task
            except asyncio.CancelledError:
                pass
        logger.info("任务队列管理器已停止")
    
    async def _process_delayed_tasks(self):
        """处理延迟任务的后台任务"""
        while self._running:
            try:
                # 检查延迟队列中的准备任务
                ready_tasks = await self.delayed_queue.get_ready_tasks()
                
                for queued_task in ready_tasks:
                    await self.main_queue.put(queued_task)
                    logger.debug(f"延迟任务 {queued_task.task.id} 已移至主队列")
                
                # 等待一段时间再检查
                await asyncio.sleep(1)
                
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"处理延迟任务时发生错误: {e}")
                await asyncio.sleep(5)  # 错误时等待更长时间
    
    async def enqueue_task(self, task: Task, priority: int = TaskPriority.NORMAL.value, 
                          delay_seconds: int = 0) -> bool:
        """将任务加入队列"""
        queued_task = QueuedTask(
            task=task,
            priority=priority,
            scheduled_time=datetime.utcnow() + timedelta(seconds=delay_seconds)
        )
        
        if delay_seconds > 0:
            await self.delayed_queue.schedule_task(queued_task, delay_seconds)
            return True
        else:
            return await self.main_queue.put(queued_task)
    
    async def dequeue_task(self) -> Optional[QueuedTask]:
        """从队列获取任务"""
        # 首先尝试从重试队列获取
        retry_task = await self.retry_queue.get()
        if retry_task:
            return retry_task
        
        # 然后从主队列获取
        return await self.main_queue.get()
    
    async def retry_task(self, queued_task: QueuedTask, delay_seconds: int = 60) -> bool:
        """重试失败的任务"""
        if not queued_task.can_retry():
            logger.warning(f"任务 {queued_task.task.id} 已达到最大重试次数")
            return False
        
        queued_task.increment_retry()
        queued_task.scheduled_time = datetime.utcnow() + timedelta(seconds=delay_seconds)
        
        success = await self.retry_queue.put(queued_task)
        if success:
            logger.info(f"任务 {queued_task.task.id} 已加入重试队列，重试次数: {queued_task.retry_count}")
        
        return success
    
    async def remove_task(self, task_id: uuid.UUID) -> bool:
        """从所有队列中移除任务"""
        removed_main = await self.main_queue.remove(task_id)
        removed_retry = await self.retry_queue.remove(task_id)
        
        return removed_main or removed_retry
    
    async def get_queue_statistics(self) -> Dict[str, Any]:
        """获取队列统计信息"""
        main_stats = await self.main_queue.get_statistics()
        retry_size = await self.retry_queue.size()
        delayed_size = await self.delayed_queue.size()
        
        return {
            'main_queue': main_stats,
            'retry_queue_size': retry_size,
            'delayed_queue_size': delayed_size,
            'total_queued_tasks': main_stats['total_tasks'] + retry_size + delayed_size
        }