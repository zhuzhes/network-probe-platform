"""任务调度器核心模块"""

import asyncio
import logging
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional, Set
import uuid

from sqlalchemy.orm import Session
from sqlalchemy import and_, or_

from shared.models.task import Task, TaskStatus, TaskResult, TaskResultStatus
from shared.models.agent import Agent, AgentStatus
from management_platform.database.connection import get_db_session
from .queue import TaskQueueManager, QueuedTask, TaskPriority
from .allocator import TaskAllocator


logger = logging.getLogger(__name__)


class TaskScheduler:
    """任务调度器"""
    
    def __init__(self, 
                 max_concurrent_tasks: int = 100,
                 check_interval: int = 10,
                 task_timeout: int = 300):
        self.max_concurrent_tasks = max_concurrent_tasks
        self.check_interval = check_interval
        self.task_timeout = task_timeout
        
        # 核心组件
        self.queue_manager = TaskQueueManager()
        self.task_allocator = TaskAllocator()
        
        # 运行状态
        self._running = False
        self._scheduler_task: Optional[asyncio.Task] = None
        self._cleanup_task: Optional[asyncio.Task] = None
        
        # 执行中的任务跟踪
        self._executing_tasks: Dict[uuid.UUID, QueuedTask] = {}
        self._task_start_times: Dict[uuid.UUID, datetime] = {}
        
        # 统计信息
        self._stats = {
            'total_scheduled': 0,
            'total_executed': 0,
            'total_failed': 0,
            'total_timeout': 0,
            'avg_execution_time': 0.0
        }
    
    async def start(self):
        """启动调度器"""
        if self._running:
            logger.warning("调度器已在运行")
            return
        
        self._running = True
        
        # 启动队列管理器
        await self.queue_manager.start()
        
        # 启动调度器主循环
        self._scheduler_task = asyncio.create_task(self._scheduler_loop())
        
        # 启动清理任务
        self._cleanup_task = asyncio.create_task(self._cleanup_loop())
        
        logger.info("任务调度器已启动")
    
    async def stop(self):
        """停止调度器"""
        if not self._running:
            return
        
        self._running = False
        
        # 停止后台任务
        if self._scheduler_task:
            self._scheduler_task.cancel()
            try:
                await self._scheduler_task
            except asyncio.CancelledError:
                pass
        
        if self._cleanup_task:
            self._cleanup_task.cancel()
            try:
                await self._cleanup_task
            except asyncio.CancelledError:
                pass
        
        # 停止队列管理器
        await self.queue_manager.stop()
        
        logger.info("任务调度器已停止")
    
    async def _scheduler_loop(self):
        """调度器主循环"""
        while self._running:
            try:
                # 检查并调度新任务
                await self._schedule_pending_tasks()
                
                # 处理队列中的任务
                await self._process_queued_tasks()
                
                # 等待下一次检查
                await asyncio.sleep(self.check_interval)
                
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"调度器主循环发生错误: {e}")
                await asyncio.sleep(self.check_interval)
    
    async def _cleanup_loop(self):
        """清理循环，处理超时任务"""
        while self._running:
            try:
                await self._cleanup_timeout_tasks()
                await asyncio.sleep(30)  # 每30秒检查一次超时任务
                
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"清理循环发生错误: {e}")
                await asyncio.sleep(30)
    
    async def _schedule_pending_tasks(self):
        """调度待执行的任务"""
        try:
            async with get_db_session() as db:
                # 查询需要执行的任务
                current_time = datetime.utcnow()
                pending_tasks = db.query(Task).filter(
                    and_(
                        Task.status == TaskStatus.ACTIVE,
                        or_(
                            Task.next_run.is_(None),
                            Task.next_run <= current_time
                        )
                    )
                ).limit(100).all()
                
                for task in pending_tasks:
                    # 检查任务是否已在队列中
                    if await self.queue_manager.main_queue.contains(task.id):
                        continue
                    
                    # 检查任务是否正在执行
                    if task.id in self._executing_tasks:
                        continue
                    
                    # 计算任务优先级
                    priority = self._calculate_task_priority(task)
                    
                    # 将任务加入队列
                    success = await self.queue_manager.enqueue_task(task, priority)
                    if success:
                        self._stats['total_scheduled'] += 1
                        logger.debug(f"任务 {task.id} 已加入调度队列，优先级: {priority}")
                        
                        # 更新任务的下次执行时间
                        task.update_next_run()
                        db.commit()
                
        except Exception as e:
            logger.error(f"调度待执行任务时发生错误: {e}")
    
    async def _process_queued_tasks(self):
        """处理队列中的任务"""
        try:
            # 检查当前执行任务数量
            if len(self._executing_tasks) >= self.max_concurrent_tasks:
                return
            
            # 从队列获取任务
            available_slots = self.max_concurrent_tasks - len(self._executing_tasks)
            
            for _ in range(available_slots):
                queued_task = await self.queue_manager.dequeue_task()
                if not queued_task:
                    break
                
                # 分配代理执行任务
                success = await self._execute_task(queued_task)
                if not success:
                    # 执行失败，尝试重试
                    await self.queue_manager.retry_task(queued_task, delay_seconds=60)
                
        except Exception as e:
            logger.error(f"处理队列任务时发生错误: {e}")
    
    async def _execute_task(self, queued_task: QueuedTask) -> bool:
        """执行任务"""
        try:
            # 选择合适的代理
            agent = await self.task_allocator.select_agent(queued_task.task)
            if not agent:
                logger.warning(f"无法为任务 {queued_task.task.id} 找到合适的代理")
                return False
            
            # 记录任务开始执行
            queued_task.assigned_agent_id = agent.id
            self._executing_tasks[queued_task.task.id] = queued_task
            self._task_start_times[queued_task.task.id] = datetime.utcnow()
            
            # 发送任务到代理（这里应该通过WebSocket发送）
            await self._send_task_to_agent(queued_task.task, agent)
            
            logger.info(f"任务 {queued_task.task.id} 已分配给代理 {agent.id}")
            return True
            
        except Exception as e:
            logger.error(f"执行任务 {queued_task.task.id} 时发生错误: {e}")
            return False
    
    async def _send_task_to_agent(self, task: Task, agent: Agent):
        """发送任务到代理（占位符实现）"""
        # TODO: 实现通过WebSocket发送任务到代理的逻辑
        # 这里应该调用WebSocket服务端的消息发送功能
        logger.debug(f"发送任务 {task.id} 到代理 {agent.id}")
        
        # 模拟任务执行（实际实现中应该通过WebSocket通信）
        asyncio.create_task(self._simulate_task_execution(task, agent))
    
    async def _simulate_task_execution(self, task: Task, agent: Agent):
        """模拟任务执行（用于测试）"""
        # 这是一个临时的模拟实现，实际应该通过WebSocket通信
        await asyncio.sleep(5)  # 模拟执行时间
        
        # 模拟任务结果
        result_status = TaskResultStatus.SUCCESS if hash(str(task.id)) % 10 < 8 else TaskResultStatus.ERROR
        
        await self.handle_task_result(
            task_id=task.id,
            agent_id=agent.id,
            status=result_status,
            duration=5000.0,  # 5秒
            metrics={'response_time': 100.0} if result_status == TaskResultStatus.SUCCESS else None,
            error_message="模拟错误" if result_status == TaskResultStatus.ERROR else None
        )
    
    async def _cleanup_timeout_tasks(self):
        """清理超时任务"""
        current_time = datetime.utcnow()
        timeout_tasks = []
        
        for task_id, start_time in self._task_start_times.items():
            if (current_time - start_time).total_seconds() > self.task_timeout:
                timeout_tasks.append(task_id)
        
        for task_id in timeout_tasks:
            await self._handle_task_timeout(task_id)
    
    async def _handle_task_timeout(self, task_id: uuid.UUID):
        """处理任务超时"""
        if task_id not in self._executing_tasks:
            return
        
        queued_task = self._executing_tasks[task_id]
        
        # 记录超时结果
        await self.handle_task_result(
            task_id=task_id,
            agent_id=queued_task.assigned_agent_id,
            status=TaskResultStatus.TIMEOUT,
            duration=self.task_timeout * 1000,  # 转换为毫秒
            error_message="任务执行超时"
        )
        
        logger.warning(f"任务 {task_id} 执行超时")
    
    def _calculate_task_priority(self, task: Task) -> int:
        """计算任务优先级"""
        # 基础优先级
        base_priority = task.priority or 0
        
        # 根据任务频率调整优先级
        if task.frequency:
            if task.frequency <= 60:  # 高频任务
                base_priority += 2
            elif task.frequency <= 300:  # 中频任务
                base_priority += 1
        
        # 根据任务延迟调整优先级
        if task.next_run:
            delay = (datetime.utcnow() - task.next_run).total_seconds()
            if delay > 300:  # 延迟超过5分钟
                base_priority += 3
            elif delay > 60:  # 延迟超过1分钟
                base_priority += 1
        
        return max(0, min(base_priority, TaskPriority.URGENT.value))
    
    async def handle_task_result(self, 
                               task_id: uuid.UUID,
                               agent_id: Optional[uuid.UUID],
                               status: TaskResultStatus,
                               duration: Optional[float] = None,
                               metrics: Optional[Dict[str, Any]] = None,
                               raw_data: Optional[Dict[str, Any]] = None,
                               error_message: Optional[str] = None):
        """处理任务执行结果"""
        try:
            # 从执行列表中移除任务
            if task_id in self._executing_tasks:
                del self._executing_tasks[task_id]
            
            if task_id in self._task_start_times:
                del self._task_start_times[task_id]
            
            # 保存任务结果到数据库
            async with get_db_session() as db:
                task_result = TaskResult(
                    task_id=task_id,
                    agent_id=agent_id,
                    execution_time=datetime.utcnow(),
                    duration=duration,
                    status=status,
                    error_message=error_message,
                    metrics=metrics,
                    raw_data=raw_data
                )
                
                db.add(task_result)
                db.commit()
                
                # 更新统计信息
                self._stats['total_executed'] += 1
                if status == TaskResultStatus.SUCCESS:
                    pass  # 成功任务
                elif status == TaskResultStatus.TIMEOUT:
                    self._stats['total_timeout'] += 1
                else:
                    self._stats['total_failed'] += 1
                
                logger.info(f"任务 {task_id} 执行完成，状态: {status.value}")
                
        except Exception as e:
            logger.error(f"处理任务结果时发生错误: {e}")
    
    async def pause_task(self, task_id: uuid.UUID) -> bool:
        """暂停任务"""
        try:
            # 从队列中移除任务
            await self.queue_manager.remove_task(task_id)
            
            # 更新数据库中的任务状态
            async with get_db_session() as db:
                task = db.query(Task).filter(Task.id == task_id).first()
                if task:
                    task.pause()
                    db.commit()
                    logger.info(f"任务 {task_id} 已暂停")
                    return True
                
        except Exception as e:
            logger.error(f"暂停任务 {task_id} 时发生错误: {e}")
        
        return False
    
    async def resume_task(self, task_id: uuid.UUID) -> bool:
        """恢复任务"""
        try:
            async with get_db_session() as db:
                task = db.query(Task).filter(Task.id == task_id).first()
                if task and task.status == TaskStatus.PAUSED:
                    task.resume()
                    db.commit()
                    logger.info(f"任务 {task_id} 已恢复")
                    return True
                
        except Exception as e:
            logger.error(f"恢复任务 {task_id} 时发生错误: {e}")
        
        return False
    
    async def cancel_task(self, task_id: uuid.UUID) -> bool:
        """取消正在执行的任务"""
        try:
            # 从执行列表中移除
            if task_id in self._executing_tasks:
                del self._executing_tasks[task_id]
            
            if task_id in self._task_start_times:
                del self._task_start_times[task_id]
            
            # 从队列中移除
            await self.queue_manager.remove_task(task_id)
            
            logger.info(f"任务 {task_id} 已取消")
            return True
            
        except Exception as e:
            logger.error(f"取消任务 {task_id} 时发生错误: {e}")
            return False
    
    async def get_scheduler_status(self) -> Dict[str, Any]:
        """获取调度器状态"""
        queue_stats = await self.queue_manager.get_queue_statistics()
        
        return {
            'running': self._running,
            'executing_tasks': len(self._executing_tasks),
            'max_concurrent_tasks': self.max_concurrent_tasks,
            'queue_statistics': queue_stats,
            'execution_statistics': self._stats.copy(),
            'check_interval': self.check_interval,
            'task_timeout': self.task_timeout
        }
    
    async def get_executing_tasks(self) -> List[Dict[str, Any]]:
        """获取正在执行的任务列表"""
        executing_tasks = []
        current_time = datetime.utcnow()
        
        for task_id, queued_task in self._executing_tasks.items():
            start_time = self._task_start_times.get(task_id)
            execution_duration = (current_time - start_time).total_seconds() if start_time else 0
            
            executing_tasks.append({
                'task_id': str(task_id),
                'task_name': queued_task.task.name,
                'agent_id': str(queued_task.assigned_agent_id) if queued_task.assigned_agent_id else None,
                'start_time': start_time.isoformat() if start_time else None,
                'execution_duration': execution_duration,
                'priority': queued_task.priority,
                'retry_count': queued_task.retry_count
            })
        
        return executing_tasks
    
    async def update_task_priority(self, task_id: uuid.UUID, new_priority: int) -> bool:
        """更新任务优先级"""
        try:
            # 更新队列中的任务优先级
            if isinstance(self.queue_manager.main_queue, type(self.queue_manager.main_queue)) and \
               hasattr(self.queue_manager.main_queue, 'update_priority'):
                await self.queue_manager.main_queue.update_priority(task_id, new_priority)
            
            # 更新数据库中的任务优先级
            async with get_db_session() as db:
                task = db.query(Task).filter(Task.id == task_id).first()
                if task:
                    task.priority = new_priority
                    db.commit()
                    logger.info(f"任务 {task_id} 优先级已更新为 {new_priority}")
                    return True
                
        except Exception as e:
            logger.error(f"更新任务优先级时发生错误: {e}")
        
        return False
    
    async def force_execute_task(self, task_id: uuid.UUID) -> bool:
        """强制执行任务"""
        try:
            async with get_db_session() as db:
                task = db.query(Task).filter(Task.id == task_id).first()
                if not task:
                    return False
                
                # 创建高优先级的队列任务
                queued_task = QueuedTask(
                    task=task,
                    priority=TaskPriority.URGENT.value,
                    scheduled_time=datetime.utcnow()
                )
                
                # 直接执行任务
                success = await self._execute_task(queued_task)
                if success:
                    logger.info(f"任务 {task_id} 已强制执行")
                
                return success
                
        except Exception as e:
            logger.error(f"强制执行任务 {task_id} 时发生错误: {e}")
            return False