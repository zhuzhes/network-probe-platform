"""任务执行器模块"""

import asyncio
import logging
import uuid
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional, Callable
from dataclasses import dataclass
from enum import Enum
import json

from shared.models.task import Task, TaskStatus, ProtocolType
from shared.models.agent import Agent
from ..protocols.registry import ProtocolRegistry
from ..protocols.base import ProtocolResult, ProtocolTestStatus


logger = logging.getLogger(__name__)


class ExecutionStatus(str, Enum):
    """执行状态枚举"""
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    TIMEOUT = "timeout"
    CANCELLED = "cancelled"


@dataclass
class TaskExecution:
    """任务执行实例"""
    task_id: uuid.UUID
    task_data: Dict[str, Any]
    start_time: datetime
    status: ExecutionStatus = ExecutionStatus.PENDING
    end_time: Optional[datetime] = None
    result: Optional[ProtocolResult] = None
    error_message: Optional[str] = None
    retry_count: int = 0
    max_retries: int = 3
    
    @property
    def duration(self) -> Optional[float]:
        """获取执行时长（毫秒）"""
        if self.start_time and self.end_time:
            return (self.end_time - self.start_time).total_seconds() * 1000
        return None
    
    @property
    def is_completed(self) -> bool:
        """检查是否已完成"""
        return self.status in [ExecutionStatus.COMPLETED, ExecutionStatus.FAILED, 
                              ExecutionStatus.TIMEOUT, ExecutionStatus.CANCELLED]
    
    @property
    def can_retry(self) -> bool:
        """检查是否可以重试"""
        return (self.status == ExecutionStatus.FAILED and 
                self.retry_count < self.max_retries)
    
    def mark_started(self):
        """标记开始执行"""
        self.status = ExecutionStatus.RUNNING
        self.start_time = datetime.utcnow()
    
    def mark_completed(self, result: ProtocolResult):
        """标记执行完成"""
        self.status = ExecutionStatus.COMPLETED
        self.end_time = datetime.utcnow()
        self.result = result
    
    def mark_failed(self, error_message: str):
        """标记执行失败"""
        self.status = ExecutionStatus.FAILED
        self.end_time = datetime.utcnow()
        self.error_message = error_message
    
    def mark_timeout(self):
        """标记执行超时"""
        self.status = ExecutionStatus.TIMEOUT
        self.end_time = datetime.utcnow()
        self.error_message = "任务执行超时"
    
    def mark_cancelled(self):
        """标记执行取消"""
        self.status = ExecutionStatus.CANCELLED
        self.end_time = datetime.utcnow()
        self.error_message = "任务被取消"
    
    def increment_retry(self):
        """增加重试次数"""
        self.retry_count += 1
        self.status = ExecutionStatus.PENDING
        self.end_time = None
        self.error_message = None


class TaskExecutor:
    """任务执行器"""
    
    def __init__(self, 
                 agent_id: str,
                 max_concurrent_tasks: int = 10,
                 default_timeout: int = 30,
                 result_callback: Optional[Callable] = None):
        """
        初始化任务执行器
        
        Args:
            agent_id: 代理ID
            max_concurrent_tasks: 最大并发任务数
            default_timeout: 默认超时时间（秒）
            result_callback: 结果回调函数
        """
        self.agent_id = agent_id
        self.max_concurrent_tasks = max_concurrent_tasks
        self.default_timeout = default_timeout
        self.result_callback = result_callback
        
        # 协议注册表
        self.protocol_registry = ProtocolRegistry()
        
        # 执行状态
        self._running = False
        self._executions: Dict[uuid.UUID, TaskExecution] = {}
        self._execution_tasks: Dict[uuid.UUID, asyncio.Task] = {}
        self._execution_semaphore = asyncio.Semaphore(max_concurrent_tasks)
        
        # 统计信息
        self._stats = {
            'total_executed': 0,
            'total_successful': 0,
            'total_failed': 0,
            'total_timeout': 0,
            'total_cancelled': 0,
            'avg_execution_time': 0.0
        }
        
        logger.info(f"任务执行器初始化完成，代理ID: {agent_id}")
    
    async def start(self):
        """启动执行器"""
        if self._running:
            logger.warning("任务执行器已在运行")
            return
        
        self._running = True
        logger.info("任务执行器已启动")
    
    async def stop(self):
        """停止执行器"""
        if not self._running:
            return
        
        self._running = False
        
        # 取消所有正在执行的任务
        for task_id, task in self._execution_tasks.items():
            if not task.done():
                task.cancel()
                execution = self._executions.get(task_id)
                if execution:
                    execution.mark_cancelled()
        
        # 等待所有任务完成
        if self._execution_tasks:
            await asyncio.gather(*self._execution_tasks.values(), return_exceptions=True)
        
        self._execution_tasks.clear()
        self._executions.clear()
        
        logger.info("任务执行器已停止")
    
    async def execute_task(self, task_data: Dict[str, Any]) -> bool:
        """
        执行任务
        
        Args:
            task_data: 任务数据
            
        Returns:
            bool: 是否成功开始执行
        """
        if not self._running:
            logger.error("任务执行器未运行")
            return False
        
        try:
            task_id = uuid.UUID(task_data['id'])
            
            # 检查任务是否已在执行
            if task_id in self._executions:
                logger.warning(f"任务 {task_id} 已在执行中")
                return False
            
            # 检查并发限制
            if len(self._executions) >= self.max_concurrent_tasks:
                logger.warning(f"已达到最大并发任务数 {self.max_concurrent_tasks}")
                return False
            
            # 创建任务执行实例
            execution = TaskExecution(
                task_id=task_id,
                task_data=task_data,
                start_time=datetime.utcnow()
            )
            
            self._executions[task_id] = execution
            
            # 创建执行任务
            execution_task = asyncio.create_task(
                self._execute_task_internal(execution)
            )
            self._execution_tasks[task_id] = execution_task
            
            logger.info(f"任务 {task_id} 开始执行")
            return True
            
        except Exception as e:
            logger.error(f"启动任务执行失败: {e}")
            return False
    
    async def _execute_task_internal(self, execution: TaskExecution):
        """内部任务执行逻辑"""
        task_id = execution.task_id
        
        try:
            async with self._execution_semaphore:
                await self._perform_task_execution(execution)
                
        except asyncio.CancelledError:
            execution.mark_cancelled()
            logger.info(f"任务 {task_id} 被取消")
            
        except Exception as e:
            execution.mark_failed(str(e))
            logger.error(f"任务 {task_id} 执行异常: {e}")
            
        finally:
            # 清理执行任务
            if task_id in self._execution_tasks:
                del self._execution_tasks[task_id]
            
            # 更新统计信息
            self._update_statistics(execution)
            
            # 发送结果
            await self._send_result(execution)
            
            # 处理重试
            if execution.can_retry():
                logger.info(f"任务 {task_id} 准备重试，当前重试次数: {execution.retry_count}")
                execution.increment_retry()
                
                # 延迟重试
                await asyncio.sleep(min(2 ** execution.retry_count, 60))  # 指数退避
                
                # 重新执行
                retry_task = asyncio.create_task(self._execute_task_internal(execution))
                self._execution_tasks[task_id] = retry_task
            else:
                # 移除执行记录
                if task_id in self._executions:
                    del self._executions[task_id]
    
    async def _perform_task_execution(self, execution: TaskExecution):
        """执行具体的任务"""
        task_data = execution.task_data
        task_id = execution.task_id
        
        try:
            # 解析任务参数
            protocol = ProtocolType(task_data['protocol'])
            target = task_data['target']
            port = task_data.get('port')
            timeout = task_data.get('timeout', self.default_timeout)
            parameters = task_data.get('parameters', {})
            
            # 获取协议处理器
            protocol_handler = self.protocol_registry.get_handler(protocol)
            if not protocol_handler:
                raise ValueError(f"不支持的协议: {protocol}")
            
            # 标记开始执行
            execution.mark_started()
            
            logger.debug(f"开始执行任务 {task_id}: {protocol} -> {target}")
            
            # 执行拨测
            result = await asyncio.wait_for(
                protocol_handler.probe(target, port, parameters),
                timeout=timeout
            )
            
            # 标记完成
            execution.mark_completed(result)
            
            logger.debug(f"任务 {task_id} 执行完成: {result.status}")
            
        except asyncio.TimeoutError:
            execution.mark_timeout()
            logger.warning(f"任务 {task_id} 执行超时")
            
        except Exception as e:
            execution.mark_failed(str(e))
            logger.error(f"任务 {task_id} 执行失败: {e}")
    
    async def _send_result(self, execution: TaskExecution):
        """发送执行结果"""
        if not self.result_callback:
            return
        
        try:
            # 构建结果数据
            result_data = {
                'task_id': str(execution.task_id),
                'agent_id': self.agent_id,
                'execution_time': execution.start_time.isoformat(),
                'duration': execution.duration,
                'status': execution.status.value,
                'error_message': execution.error_message,
                'retry_count': execution.retry_count
            }
            
            # 添加拨测结果
            if execution.result:
                result_data.update({
                    'probe_status': execution.result.status.value,
                    'metrics': execution.result.metrics,
                    'raw_data': execution.result.raw_data
                })
            
            # 调用回调函数
            await self.result_callback(result_data)
            
        except Exception as e:
            logger.error(f"发送任务结果失败: {e}")
    
    def _update_statistics(self, execution: TaskExecution):
        """更新统计信息"""
        self._stats['total_executed'] += 1
        
        if execution.status == ExecutionStatus.COMPLETED:
            self._stats['total_successful'] += 1
        elif execution.status == ExecutionStatus.FAILED:
            self._stats['total_failed'] += 1
        elif execution.status == ExecutionStatus.TIMEOUT:
            self._stats['total_timeout'] += 1
        elif execution.status == ExecutionStatus.CANCELLED:
            self._stats['total_cancelled'] += 1
        
        # 更新平均执行时间
        if execution.duration:
            total_time = self._stats['avg_execution_time'] * (self._stats['total_executed'] - 1)
            self._stats['avg_execution_time'] = (total_time + execution.duration) / self._stats['total_executed']
    
    async def cancel_task(self, task_id: uuid.UUID) -> bool:
        """
        取消任务执行
        
        Args:
            task_id: 任务ID
            
        Returns:
            bool: 是否成功取消
        """
        if task_id not in self._execution_tasks:
            logger.warning(f"任务 {task_id} 不在执行中")
            return False
        
        try:
            # 取消执行任务
            execution_task = self._execution_tasks[task_id]
            execution_task.cancel()
            
            # 标记执行状态
            execution = self._executions.get(task_id)
            if execution:
                execution.mark_cancelled()
            
            logger.info(f"任务 {task_id} 已取消")
            return True
            
        except Exception as e:
            logger.error(f"取消任务 {task_id} 失败: {e}")
            return False
    
    def get_execution_status(self, task_id: uuid.UUID) -> Optional[Dict[str, Any]]:
        """
        获取任务执行状态
        
        Args:
            task_id: 任务ID
            
        Returns:
            Optional[Dict]: 执行状态信息
        """
        execution = self._executions.get(task_id)
        if not execution:
            return None
        
        return {
            'task_id': str(task_id),
            'status': execution.status.value,
            'start_time': execution.start_time.isoformat(),
            'end_time': execution.end_time.isoformat() if execution.end_time else None,
            'duration': execution.duration,
            'retry_count': execution.retry_count,
            'error_message': execution.error_message
        }
    
    def get_running_tasks(self) -> List[Dict[str, Any]]:
        """获取正在运行的任务列表"""
        running_tasks = []
        
        for task_id, execution in self._executions.items():
            if execution.status == ExecutionStatus.RUNNING:
                running_tasks.append({
                    'task_id': str(task_id),
                    'start_time': execution.start_time.isoformat(),
                    'duration': (datetime.utcnow() - execution.start_time).total_seconds() * 1000,
                    'protocol': execution.task_data.get('protocol'),
                    'target': execution.task_data.get('target')
                })
        
        return running_tasks
    
    def get_statistics(self) -> Dict[str, Any]:
        """获取执行统计信息"""
        return {
            'agent_id': self.agent_id,
            'running': self._running,
            'current_executions': len(self._executions),
            'max_concurrent_tasks': self.max_concurrent_tasks,
            'statistics': self._stats.copy(),
            'supported_protocols': list(self.protocol_registry.get_supported_protocols())
        }
    
    async def health_check(self) -> Dict[str, Any]:
        """健康检查"""
        return {
            'status': 'healthy' if self._running else 'stopped',
            'agent_id': self.agent_id,
            'current_load': len(self._executions) / self.max_concurrent_tasks,
            'total_executed': self._stats['total_executed'],
            'success_rate': (self._stats['total_successful'] / self._stats['total_executed'] 
                           if self._stats['total_executed'] > 0 else 0),
            'avg_execution_time': self._stats['avg_execution_time'],
            'supported_protocols': list(self.protocol_registry.get_supported_protocols())
        }
    
    def set_max_concurrent_tasks(self, max_tasks: int):
        """设置最大并发任务数"""
        if max_tasks <= 0:
            raise ValueError("最大并发任务数必须大于0")
        
        old_max = self.max_concurrent_tasks
        self.max_concurrent_tasks = max_tasks
        
        # 更新信号量
        self._execution_semaphore = asyncio.Semaphore(max_tasks)
        
        logger.info(f"最大并发任务数已从 {old_max} 更新为 {max_tasks}")
    
    def set_result_callback(self, callback: Callable):
        """设置结果回调函数"""
        self.result_callback = callback
        logger.info("结果回调函数已更新")


class TaskResultCollector:
    """任务结果收集器"""
    
    def __init__(self, 
                 agent_id: str,
                 batch_size: int = 10,
                 batch_timeout: int = 30,
                 send_callback: Optional[Callable] = None):
        """
        初始化结果收集器
        
        Args:
            agent_id: 代理ID
            batch_size: 批量大小
            batch_timeout: 批量超时时间（秒）
            send_callback: 发送回调函数
        """
        self.agent_id = agent_id
        self.batch_size = batch_size
        self.batch_timeout = batch_timeout
        self.send_callback = send_callback
        
        self._results_buffer: List[Dict[str, Any]] = []
        self._buffer_lock = asyncio.Lock()
        self._batch_task: Optional[asyncio.Task] = None
        self._running = False
        
        logger.info(f"任务结果收集器初始化完成，代理ID: {agent_id}")
    
    async def start(self):
        """启动收集器"""
        if self._running:
            return
        
        self._running = True
        self._batch_task = asyncio.create_task(self._batch_sender_loop())
        logger.info("任务结果收集器已启动")
    
    async def stop(self):
        """停止收集器"""
        if not self._running:
            return
        
        self._running = False
        
        if self._batch_task:
            self._batch_task.cancel()
            try:
                await self._batch_task
            except asyncio.CancelledError:
                pass
        
        # 发送剩余结果
        await self._flush_buffer()
        
        logger.info("任务结果收集器已停止")
    
    async def collect_result(self, result_data: Dict[str, Any]):
        """收集任务结果"""
        async with self._buffer_lock:
            self._results_buffer.append(result_data)
            
            # 如果达到批量大小，立即发送
            if len(self._results_buffer) >= self.batch_size:
                await self._send_batch()
    
    async def _batch_sender_loop(self):
        """批量发送循环"""
        while self._running:
            try:
                await asyncio.sleep(self.batch_timeout)
                
                async with self._buffer_lock:
                    if self._results_buffer:
                        await self._send_batch()
                        
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"批量发送循环异常: {e}")
    
    async def _send_batch(self):
        """发送批量结果"""
        if not self._results_buffer or not self.send_callback:
            return
        
        try:
            batch_data = {
                'agent_id': self.agent_id,
                'timestamp': datetime.utcnow().isoformat(),
                'results': self._results_buffer.copy()
            }
            
            await self.send_callback(batch_data)
            
            logger.debug(f"已发送 {len(self._results_buffer)} 个任务结果")
            self._results_buffer.clear()
            
        except Exception as e:
            logger.error(f"发送批量结果失败: {e}")
    
    async def _flush_buffer(self):
        """刷新缓冲区"""
        async with self._buffer_lock:
            if self._results_buffer:
                await self._send_batch()
    
    def get_buffer_status(self) -> Dict[str, Any]:
        """获取缓冲区状态"""
        return {
            'buffer_size': len(self._results_buffer),
            'batch_size': self.batch_size,
            'batch_timeout': self.batch_timeout,
            'running': self._running
        }