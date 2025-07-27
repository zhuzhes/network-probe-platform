"""消息分发系统"""

import asyncio
import json
import uuid
from typing import Dict, Any, Optional, List, Set, Callable, Awaitable, Union
from datetime import datetime, timedelta
from dataclasses import dataclass, field
from enum import Enum
import logging

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', '..'))

from shared.models.task import Task, TaskStatus, TaskResult
from shared.models.agent import Agent, AgentStatus
from management_platform.database.repositories import TaskRepository, AgentRepository
from management_platform.database.connection import get_db_session
from .connection_manager import AdvancedConnectionManager


logger = logging.getLogger(__name__)


class MessageType(Enum):
    """消息类型枚举"""
    TASK_ASSIGNMENT = "task_assignment"
    TASK_CANCEL = "task_cancel"
    TASK_RESULT = "task_result"
    TASK_STATUS_UPDATE = "task_status_update"
    AGENT_COMMAND = "agent_command"
    SYSTEM_NOTIFICATION = "system_notification"
    HEARTBEAT = "heartbeat"
    HEARTBEAT_RESPONSE = "heartbeat_response"
    BROADCAST = "broadcast"
    ERROR = "error"


class MessagePriority(Enum):
    """消息优先级"""
    LOW = 1
    NORMAL = 2
    HIGH = 3
    URGENT = 4


@dataclass
class Message:
    """消息数据结构"""
    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    type: MessageType = MessageType.SYSTEM_NOTIFICATION
    priority: MessagePriority = MessagePriority.NORMAL
    sender: Optional[str] = None
    recipient: Optional[str] = None  # None表示广播
    data: Dict[str, Any] = field(default_factory=dict)
    created_at: datetime = field(default_factory=datetime.now)
    expires_at: Optional[datetime] = None
    retry_count: int = 0
    max_retries: int = 3
    callback: Optional[Callable[[bool, Optional[str]], Awaitable[None]]] = None
    
    def to_dict(self) -> Dict[str, Any]:
        """转换为字典格式"""
        return {
            "id": self.id,
            "type": self.type.value,
            "priority": self.priority.value,
            "sender": self.sender,
            "recipient": self.recipient,
            "data": self.data,
            "timestamp": self.created_at.isoformat(),
            "expires_at": self.expires_at.isoformat() if self.expires_at else None
        }
    
    def is_expired(self) -> bool:
        """检查消息是否过期"""
        if self.expires_at is None:
            return False
        return datetime.now() > self.expires_at
    
    def can_retry(self) -> bool:
        """检查是否可以重试"""
        return self.retry_count < self.max_retries


class MessageQueue:
    """消息队列"""
    
    def __init__(self, max_size: int = 10000):
        self.max_size = max_size
        self.queues: Dict[MessagePriority, asyncio.Queue] = {
            priority: asyncio.Queue(maxsize=max_size // 4)
            for priority in MessagePriority
        }
        self.stats = {
            "messages_queued": 0,
            "messages_sent": 0,
            "messages_failed": 0,
            "messages_expired": 0,
            "queue_full_errors": 0
        }
    
    async def put(self, message: Message) -> bool:
        """添加消息到队列"""
        try:
            # 检查消息是否过期
            if message.is_expired():
                self.stats["messages_expired"] += 1
                logger.warning(f"消息 {message.id} 已过期，丢弃")
                return False
            
            # 添加到对应优先级的队列
            queue = self.queues[message.priority]
            await queue.put(message)
            
            self.stats["messages_queued"] += 1
            logger.debug(f"消息 {message.id} 已加入 {message.priority.name} 优先级队列")
            return True
            
        except asyncio.QueueFull:
            self.stats["queue_full_errors"] += 1
            logger.error(f"队列已满，无法添加消息 {message.id}")
            return False
    
    async def get(self) -> Optional[Message]:
        """从队列获取消息（按优先级）"""
        # 按优先级顺序检查队列
        for priority in sorted(MessagePriority, key=lambda x: x.value, reverse=True):
            queue = self.queues[priority]
            try:
                message = queue.get_nowait()
                
                # 检查消息是否过期
                if message.is_expired():
                    self.stats["messages_expired"] += 1
                    logger.warning(f"消息 {message.id} 已过期，丢弃")
                    queue.task_done()
                    continue
                
                return message
                
            except asyncio.QueueEmpty:
                continue
        
        return None
    
    async def get_blocking(self, timeout: Optional[float] = None) -> Optional[Message]:
        """阻塞获取消息"""
        end_time = datetime.now() + timedelta(seconds=timeout) if timeout else None
        
        while True:
            message = await self.get()
            if message:
                return message
            
            # 检查超时
            if end_time and datetime.now() > end_time:
                return None
            
            # 等待一小段时间再检查
            await asyncio.sleep(0.1)
    
    def task_done(self, priority: MessagePriority):
        """标记任务完成"""
        self.queues[priority].task_done()
    
    def qsize(self, priority: Optional[MessagePriority] = None) -> Union[int, Dict[MessagePriority, int]]:
        """获取队列大小"""
        if priority:
            return self.queues[priority].qsize()
        return {p: q.qsize() for p, q in self.queues.items()}
    
    def get_stats(self) -> Dict[str, Any]:
        """获取队列统计信息"""
        return {
            **self.stats,
            "queue_sizes": self.qsize(),
            "total_queued": sum(self.qsize().values())
        }


class TaskDistributor:
    """任务分发器"""
    
    def __init__(self, connection_manager: AdvancedConnectionManager):
        self.connection_manager = connection_manager
        
        # 任务分发策略
        self.distribution_strategies = {
            "round_robin": self._round_robin_strategy,
            "load_based": self._load_based_strategy,
            "location_based": self._location_based_strategy,
            "capability_based": self._capability_based_strategy
        }
        
        # 当前策略
        self.current_strategy = "load_based"
        
        # 轮询状态（用于round_robin策略）
        self._round_robin_index = 0
        
        # 分发统计
        self.stats = {
            "tasks_distributed": 0,
            "distribution_failures": 0,
            "agent_selections": {},  # agent_id -> count
            "strategy_usage": {}     # strategy -> count
        }
    
    async def distribute_task(self, task: Task, strategy: Optional[str] = None) -> Optional[str]:
        """
        分发任务到代理
        
        Args:
            task: 任务对象
            strategy: 分发策略，None使用默认策略
            
        Returns:
            选中的代理ID，失败返回None
        """
        strategy = strategy or self.current_strategy
        
        if strategy not in self.distribution_strategies:
            logger.error(f"未知的分发策略: {strategy}")
            return None
        
        try:
            # 获取可用代理
            available_agents = self.connection_manager.get_available_agents()
            if not available_agents:
                logger.warning("没有可用的代理来执行任务")
                self.stats["distribution_failures"] += 1
                return None
            
            # 应用分发策略选择代理
            selected_agent = await self.distribution_strategies[strategy](task, available_agents)
            
            if not selected_agent:
                logger.warning(f"策略 {strategy} 未能选择合适的代理")
                self.stats["distribution_failures"] += 1
                return None
            
            # 创建任务分配消息
            task_message = Message(
                type=MessageType.TASK_ASSIGNMENT,
                priority=MessagePriority.HIGH,
                recipient=selected_agent,
                data={
                    "task_id": task.id,
                    "task_type": task.protocol,
                    "target": task.target,
                    "port": task.port,
                    "parameters": task.parameters,
                    "timeout": task.timeout,
                    "assigned_at": datetime.now().isoformat()
                },
                expires_at=datetime.now() + timedelta(minutes=5)  # 5分钟过期
            )
            
            # 发送任务到代理
            success = await self.connection_manager.send_message(selected_agent, task_message.to_dict())
            
            if success:
                # 更新统计
                self.stats["tasks_distributed"] += 1
                self.stats["agent_selections"][selected_agent] = \
                    self.stats["agent_selections"].get(selected_agent, 0) + 1
                self.stats["strategy_usage"][strategy] = \
                    self.stats["strategy_usage"].get(strategy, 0) + 1
                
                logger.info(f"任务 {task.id} 已分发给代理 {selected_agent} (策略: {strategy})")
                return selected_agent
            else:
                logger.error(f"向代理 {selected_agent} 发送任务失败")
                self.stats["distribution_failures"] += 1
                return None
                
        except Exception as e:
            logger.error(f"分发任务时发生异常: {e}")
            self.stats["distribution_failures"] += 1
            return None
    
    async def _round_robin_strategy(self, task: Task, available_agents: List[str]) -> Optional[str]:
        """轮询策略"""
        if not available_agents:
            return None
        
        # 选择下一个代理
        selected_agent = available_agents[self._round_robin_index % len(available_agents)]
        self._round_robin_index += 1
        
        return selected_agent
    
    async def _load_based_strategy(self, task: Task, available_agents: List[str]) -> Optional[str]:
        """基于负载的策略"""
        if not available_agents:
            return None
        
        # 获取所有代理的负载信息
        agent_loads = {}
        for agent_id in available_agents:
            load_info = self.connection_manager.load_monitor.get_agent_load(agent_id)
            if load_info:
                # 计算综合负载分数（CPU + 内存 + 磁盘）
                cpu_load = load_info.get("cpu_usage", 0)
                memory_load = load_info.get("memory_usage", 0)
                disk_load = load_info.get("disk_usage", 0)
                
                # 加权平均负载
                total_load = (cpu_load * 0.5 + memory_load * 0.3 + disk_load * 0.2)
                agent_loads[agent_id] = total_load
            else:
                # 没有负载信息的代理给予中等优先级
                agent_loads[agent_id] = 50.0
        
        # 选择负载最低的代理
        selected_agent = min(agent_loads.keys(), key=lambda x: agent_loads[x])
        return selected_agent
    
    async def _location_based_strategy(self, task: Task, available_agents: List[str]) -> Optional[str]:
        """基于位置的策略"""
        # 这里可以根据任务目标和代理位置选择最近的代理
        # 暂时使用简单的实现
        return available_agents[0] if available_agents else None
    
    async def _capability_based_strategy(self, task: Task, available_agents: List[str]) -> Optional[str]:
        """基于能力的策略"""
        # 筛选支持任务协议的代理
        capable_agents = []
        
        for agent_id in available_agents:
            connection = self.connection_manager.connection_pool.get_primary_connection(agent_id)
            if connection and task.protocol in connection.capabilities:
                capable_agents.append(agent_id)
        
        if not capable_agents:
            # 如果没有明确支持的代理，使用所有可用代理
            capable_agents = available_agents
        
        # 在支持的代理中使用负载策略
        return await self._load_based_strategy(task, capable_agents)
    
    async def cancel_task(self, task_id: str, agent_id: str) -> bool:
        """取消任务"""
        cancel_message = Message(
            type=MessageType.TASK_CANCEL,
            priority=MessagePriority.HIGH,
            recipient=agent_id,
            data={
                "task_id": task_id,
                "cancelled_at": datetime.now().isoformat()
            }
        )
        
        success = await self.connection_manager.send_message(agent_id, cancel_message.to_dict())
        if success:
            logger.info(f"任务 {task_id} 取消请求已发送给代理 {agent_id}")
        else:
            logger.error(f"向代理 {agent_id} 发送任务取消请求失败")
        
        return success
    
    def set_strategy(self, strategy: str):
        """设置分发策略"""
        if strategy in self.distribution_strategies:
            self.current_strategy = strategy
            logger.info(f"分发策略已设置为: {strategy}")
        else:
            logger.error(f"未知的分发策略: {strategy}")
    
    def get_stats(self) -> Dict[str, Any]:
        """获取分发统计信息"""
        return {
            **self.stats,
            "current_strategy": self.current_strategy,
            "available_strategies": list(self.distribution_strategies.keys())
        }


class ResultCollector:
    """结果收集器"""
    
    def __init__(self, connection_manager: AdvancedConnectionManager):
        self.connection_manager = connection_manager
        
        # 待处理的结果
        self.pending_results: Dict[str, Dict[str, Any]] = {}  # task_id -> result_data
        
        # 结果处理回调
        self.result_handlers: Dict[str, Callable[[str, Dict[str, Any]], Awaitable[None]]] = {}
        
        # 收集统计
        self.stats = {
            "results_received": 0,
            "results_processed": 0,
            "processing_failures": 0,
            "duplicate_results": 0
        }
    
    async def handle_task_result(self, agent_id: str, message: Dict[str, Any]):
        """
        处理任务结果
        
        Args:
            agent_id: 代理ID
            message: 结果消息
        """
        try:
            data = message.get("data", {})
            task_id = data.get("task_id")
            
            if not task_id:
                logger.error("任务结果消息缺少task_id")
                return
            
            # 检查是否是重复结果
            if task_id in self.pending_results:
                logger.warning(f"收到重复的任务结果: {task_id}")
                self.stats["duplicate_results"] += 1
                return
            
            # 记录结果
            result_data = {
                "task_id": task_id,
                "agent_id": agent_id,
                "result": data.get("result", {}),
                "status": data.get("status", "completed"),
                "error_message": data.get("error_message"),
                "execution_time": data.get("execution_time"),
                "metrics": data.get("metrics", {}),
                "received_at": datetime.now().isoformat()
            }
            
            self.pending_results[task_id] = result_data
            self.stats["results_received"] += 1
            
            logger.info(f"收到任务 {task_id} 的结果，来自代理 {agent_id}")
            
            # 发送确认响应
            ack_message = {
                "type": "task_result_ack",
                "data": {
                    "task_id": task_id,
                    "received": True,
                    "timestamp": datetime.now().isoformat()
                }
            }
            await self.connection_manager.send_message(agent_id, ack_message)
            
            # 处理结果
            await self._process_result(task_id, result_data)
            
        except Exception as e:
            logger.error(f"处理任务结果时发生异常: {e}")
            self.stats["processing_failures"] += 1
    
    async def _process_result(self, task_id: str, result_data: Dict[str, Any]):
        """处理任务结果"""
        try:
            # 保存结果到数据库
            async with get_db_session() as db:
                task_repo = TaskRepository(db)
                
                # 创建任务结果对象
                task_result = TaskResult(
                    task_id=task_id,
                    agent_id=result_data["agent_id"],
                    status=result_data["status"],
                    result_data=result_data["result"],
                    error_message=result_data.get("error_message"),
                    execution_time=result_data.get("execution_time"),
                    metrics=result_data.get("metrics", {}),
                    created_at=datetime.now()
                )
                
                # 保存结果
                await task_repo.create_task_result(task_result)
                
                # 更新任务状态
                if result_data["status"] == "completed":
                    await task_repo.update_task_status(task_id, TaskStatus.COMPLETED)
                elif result_data["status"] == "failed":
                    await task_repo.update_task_status(task_id, TaskStatus.FAILED)
            
            # 调用注册的结果处理器
            for handler_name, handler in self.result_handlers.items():
                try:
                    await handler(task_id, result_data)
                except Exception as e:
                    logger.error(f"结果处理器 {handler_name} 执行失败: {e}")
            
            # 从待处理列表中移除
            self.pending_results.pop(task_id, None)
            self.stats["results_processed"] += 1
            
            logger.info(f"任务 {task_id} 结果处理完成")
            
        except Exception as e:
            logger.error(f"处理任务 {task_id} 结果时发生异常: {e}")
            self.stats["processing_failures"] += 1
    
    def register_result_handler(self, name: str, handler: Callable[[str, Dict[str, Any]], Awaitable[None]]):
        """注册结果处理器"""
        self.result_handlers[name] = handler
        logger.info(f"已注册结果处理器: {name}")
    
    def unregister_result_handler(self, name: str):
        """注销结果处理器"""
        if name in self.result_handlers:
            del self.result_handlers[name]
            logger.info(f"已注销结果处理器: {name}")
    
    def get_pending_results(self) -> Dict[str, Dict[str, Any]]:
        """获取待处理的结果"""
        return self.pending_results.copy()
    
    def get_stats(self) -> Dict[str, Any]:
        """获取收集统计信息"""
        return {
            **self.stats,
            "pending_results_count": len(self.pending_results),
            "registered_handlers": list(self.result_handlers.keys())
        }


class StatusUpdater:
    """状态更新器"""
    
    def __init__(self, connection_manager: AdvancedConnectionManager):
        self.connection_manager = connection_manager
        
        # 状态更新统计
        self.stats = {
            "status_updates_sent": 0,
            "status_updates_failed": 0,
            "broadcast_updates": 0
        }
    
    async def update_task_status(self, task_id: str, status: TaskStatus, agent_id: Optional[str] = None):
        """
        更新任务状态
        
        Args:
            task_id: 任务ID
            status: 新状态
            agent_id: 目标代理ID，None表示广播
        """
        status_message = Message(
            type=MessageType.TASK_STATUS_UPDATE,
            priority=MessagePriority.NORMAL,
            recipient=agent_id,
            data={
                "task_id": task_id,
                "status": status.value,
                "updated_at": datetime.now().isoformat()
            }
        )
        
        if agent_id:
            # 发送给特定代理
            success = await self.connection_manager.send_message(agent_id, status_message.to_dict())
            if success:
                self.stats["status_updates_sent"] += 1
            else:
                self.stats["status_updates_failed"] += 1
        else:
            # 广播给所有代理
            success_count = await self.connection_manager.broadcast_message(status_message.to_dict())
            self.stats["broadcast_updates"] += 1
            self.stats["status_updates_sent"] += success_count
    
    async def send_system_notification(self, message: str, level: str = "info", agent_id: Optional[str] = None):
        """
        发送系统通知
        
        Args:
            message: 通知消息
            level: 通知级别 (info, warning, error)
            agent_id: 目标代理ID，None表示广播
        """
        notification = Message(
            type=MessageType.SYSTEM_NOTIFICATION,
            priority=MessagePriority.NORMAL if level == "info" else MessagePriority.HIGH,
            recipient=agent_id,
            data={
                "message": message,
                "level": level,
                "timestamp": datetime.now().isoformat()
            }
        )
        
        if agent_id:
            success = await self.connection_manager.send_message(agent_id, notification.to_dict())
            if success:
                self.stats["status_updates_sent"] += 1
            else:
                self.stats["status_updates_failed"] += 1
        else:
            success_count = await self.connection_manager.broadcast_message(notification.to_dict())
            self.stats["broadcast_updates"] += 1
            self.stats["status_updates_sent"] += success_count
    
    async def send_agent_command(self, agent_id: str, command: str, parameters: Optional[Dict[str, Any]] = None):
        """
        发送代理命令
        
        Args:
            agent_id: 代理ID
            command: 命令名称
            parameters: 命令参数
        """
        command_message = Message(
            type=MessageType.AGENT_COMMAND,
            priority=MessagePriority.HIGH,
            recipient=agent_id,
            data={
                "command": command,
                "parameters": parameters or {},
                "timestamp": datetime.now().isoformat()
            }
        )
        
        success = await self.connection_manager.send_message(agent_id, command_message.to_dict())
        if success:
            self.stats["status_updates_sent"] += 1
            logger.info(f"命令 {command} 已发送给代理 {agent_id}")
        else:
            self.stats["status_updates_failed"] += 1
            logger.error(f"向代理 {agent_id} 发送命令 {command} 失败")
        
        return success
    
    def get_stats(self) -> Dict[str, Any]:
        """获取状态更新统计"""
        return self.stats.copy()


class MessageDispatcher:
    """消息分发系统主类"""
    
    def __init__(self, connection_manager: AdvancedConnectionManager):
        self.connection_manager = connection_manager
        
        # 核心组件
        self.message_queue = MessageQueue()
        self.task_distributor = TaskDistributor(connection_manager)
        self.result_collector = ResultCollector(connection_manager)
        self.status_updater = StatusUpdater(connection_manager)
        
        # 消息处理器
        self.message_processors: Dict[MessageType, Callable[[str, Dict[str, Any]], Awaitable[None]]] = {
            MessageType.TASK_RESULT: self.result_collector.handle_task_result,
        }
        
        # 处理任务
        self._processor_task: Optional[asyncio.Task] = None
        self._running = False
        
        # 注册消息处理器到连接管理器
        self._register_message_handlers()
    
    def _register_message_handlers(self):
        """注册消息处理器到连接管理器"""
        self.connection_manager.register_message_handler("task_result", self._handle_task_result)
        self.connection_manager.register_message_handler("task_status_update", self._handle_task_status_update)
        self.connection_manager.register_message_handler("agent_status_update", self._handle_agent_status_update)
    
    async def start(self):
        """启动消息分发系统"""
        if self._running:
            return
        
        self._running = True
        self._processor_task = asyncio.create_task(self._message_processor_loop())
        logger.info("消息分发系统已启动")
    
    async def stop(self):
        """停止消息分发系统"""
        if not self._running:
            return
        
        self._running = False
        if self._processor_task:
            self._processor_task.cancel()
            try:
                await self._processor_task
            except asyncio.CancelledError:
                pass
        
        logger.info("消息分发系统已停止")
    
    async def _message_processor_loop(self):
        """消息处理循环"""
        while self._running:
            try:
                # 从队列获取消息
                message = await self.message_queue.get_blocking(timeout=1.0)
                if not message:
                    continue
                
                # 处理消息
                await self._process_message(message)
                
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"消息处理循环异常: {e}")
    
    async def _process_message(self, message: Message):
        """处理单个消息"""
        try:
            if message.type in self.message_processors:
                processor = self.message_processors[message.type]
                await processor(message.sender or "system", message.to_dict())
            else:
                logger.warning(f"未找到消息类型 {message.type} 的处理器")
            
            # 调用回调
            if message.callback:
                await message.callback(True, None)
                
        except Exception as e:
            logger.error(f"处理消息 {message.id} 时发生异常: {e}")
            
            # 重试逻辑
            if message.can_retry():
                message.retry_count += 1
                await self.message_queue.put(message)
                logger.info(f"消息 {message.id} 重试 {message.retry_count}/{message.max_retries}")
            else:
                logger.error(f"消息 {message.id} 重试次数已达上限，丢弃")
                if message.callback:
                    await message.callback(False, str(e))
    
    async def _handle_task_result(self, agent_id: str, message: Dict[str, Any]):
        """处理任务结果消息"""
        await self.result_collector.handle_task_result(agent_id, message)
    
    async def _handle_task_status_update(self, agent_id: str, message: Dict[str, Any]):
        """处理任务状态更新消息"""
        data = message.get("data", {})
        task_id = data.get("task_id")
        status = data.get("status")
        
        logger.info(f"收到任务 {task_id} 状态更新: {status} (来自代理 {agent_id})")
    
    async def _handle_agent_status_update(self, agent_id: str, message: Dict[str, Any]):
        """处理代理状态更新消息"""
        data = message.get("data", {})
        status = data.get("status")
        
        logger.info(f"收到代理 {agent_id} 状态更新: {status}")
    
    # 公共接口方法
    async def distribute_task(self, task: Task, strategy: Optional[str] = None) -> Optional[str]:
        """分发任务"""
        return await self.task_distributor.distribute_task(task, strategy)
    
    async def cancel_task(self, task_id: str, agent_id: str) -> bool:
        """取消任务"""
        return await self.task_distributor.cancel_task(task_id, agent_id)
    
    async def update_task_status(self, task_id: str, status: TaskStatus, agent_id: Optional[str] = None):
        """更新任务状态"""
        await self.status_updater.update_task_status(task_id, status, agent_id)
    
    async def send_system_notification(self, message: str, level: str = "info", agent_id: Optional[str] = None):
        """发送系统通知"""
        await self.status_updater.send_system_notification(message, level, agent_id)
    
    async def send_agent_command(self, agent_id: str, command: str, parameters: Optional[Dict[str, Any]] = None):
        """发送代理命令"""
        return await self.status_updater.send_agent_command(agent_id, command, parameters)
    
    async def broadcast_message(self, message_type: MessageType, data: Dict[str, Any], priority: MessagePriority = MessagePriority.NORMAL):
        """广播消息"""
        message = Message(
            type=message_type,
            priority=priority,
            data=data
        )
        
        success_count = await self.connection_manager.broadcast_message(message.to_dict())
        logger.info(f"广播消息 {message_type.value} 成功发送给 {success_count} 个代理")
        return success_count
    
    def register_result_handler(self, name: str, handler: Callable[[str, Dict[str, Any]], Awaitable[None]]):
        """注册结果处理器"""
        self.result_collector.register_result_handler(name, handler)
    
    def set_distribution_strategy(self, strategy: str):
        """设置任务分发策略"""
        self.task_distributor.set_strategy(strategy)
    
    def get_stats(self) -> Dict[str, Any]:
        """获取系统统计信息"""
        return {
            "message_queue": self.message_queue.get_stats(),
            "task_distributor": self.task_distributor.get_stats(),
            "result_collector": self.result_collector.get_stats(),
            "status_updater": self.status_updater.get_stats(),
            "system_status": {
                "running": self._running,
                "connected_agents": len(self.connection_manager.get_connected_agents()),
                "available_agents": len(self.connection_manager.get_available_agents())
            }
        }


# 全局消息分发器实例
message_dispatcher: Optional[MessageDispatcher] = None


def get_message_dispatcher(connection_manager: AdvancedConnectionManager) -> MessageDispatcher:
    """获取消息分发器实例"""
    global message_dispatcher
    if message_dispatcher is None:
        message_dispatcher = MessageDispatcher(connection_manager)
    return message_dispatcher