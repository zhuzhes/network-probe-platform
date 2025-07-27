"""
事件驱动通知系统
"""

import asyncio
import logging
from typing import Dict, Any, Optional, List, Callable
from datetime import datetime
from enum import Enum
from dataclasses import dataclass

from .manager import NotificationManager
from .types import NotificationType, NotificationChannel, NotificationPriority
from ..database.repositories import UserRepository, TaskRepository, AgentRepository


logger = logging.getLogger(__name__)


class EventType(Enum):
    """事件类型枚举"""
    TASK_STATUS_CHANGED = "task_status_changed"
    TASK_FAILED = "task_failed"
    TASK_COMPLETED = "task_completed"
    AGENT_STATUS_CHANGED = "agent_status_changed"
    AGENT_OFFLINE = "agent_offline"
    AGENT_ONLINE = "agent_online"
    CREDIT_LOW_BALANCE = "credit_low_balance"
    SYSTEM_MAINTENANCE = "system_maintenance"
    USER_REGISTERED = "user_registered"
    TASK_CREATED = "task_created"


@dataclass
class Event:
    """事件数据结构"""
    type: EventType
    data: Dict[str, Any]
    timestamp: datetime
    user_id: Optional[str] = None
    task_id: Optional[str] = None
    agent_id: Optional[str] = None


class EventBus:
    """事件总线"""
    
    def __init__(self):
        self._handlers: Dict[EventType, List[Callable]] = {}
        self._running = False
        self._event_queue = asyncio.Queue()
        self._worker_task: Optional[asyncio.Task] = None
    
    def subscribe(self, event_type: EventType, handler: Callable):
        """订阅事件"""
        if event_type not in self._handlers:
            self._handlers[event_type] = []
        self._handlers[event_type].append(handler)
        logger.debug(f"订阅事件处理器: {event_type.value}")
    
    def unsubscribe(self, event_type: EventType, handler: Callable):
        """取消订阅事件"""
        if event_type in self._handlers:
            try:
                self._handlers[event_type].remove(handler)
                logger.debug(f"取消订阅事件处理器: {event_type.value}")
            except ValueError:
                pass
    
    async def publish(self, event: Event):
        """发布事件"""
        await self._event_queue.put(event)
        logger.debug(f"发布事件: {event.type.value}")
    
    async def start(self):
        """启动事件处理器"""
        if self._running:
            return
        
        self._running = True
        self._worker_task = asyncio.create_task(self._process_events())
        logger.info("事件总线已启动")
    
    async def stop(self):
        """停止事件处理器"""
        if not self._running:
            return
        
        self._running = False
        if self._worker_task:
            self._worker_task.cancel()
            try:
                await self._worker_task
            except asyncio.CancelledError:
                pass
        
        logger.info("事件总线已停止")
    
    async def _process_events(self):
        """处理事件的主循环"""
        while self._running:
            try:
                # 等待事件
                event = await asyncio.wait_for(self._event_queue.get(), timeout=1.0)
                
                # 处理事件
                await self._handle_event(event)
                
            except asyncio.TimeoutError:
                continue
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"处理事件时发生错误: {e}")
    
    async def _handle_event(self, event: Event):
        """处理单个事件"""
        handlers = self._handlers.get(event.type, [])
        
        if not handlers:
            logger.debug(f"没有找到事件处理器: {event.type.value}")
            return
        
        # 并发执行所有处理器
        tasks = []
        for handler in handlers:
            try:
                if asyncio.iscoroutinefunction(handler):
                    tasks.append(handler(event))
                else:
                    # 同步处理器在线程池中执行
                    loop = asyncio.get_event_loop()
                    tasks.append(loop.run_in_executor(None, handler, event))
            except Exception as e:
                logger.error(f"创建事件处理任务失败: {e}")
        
        if tasks:
            # 等待所有处理器完成
            results = await asyncio.gather(*tasks, return_exceptions=True)
            
            # 记录处理结果
            for i, result in enumerate(results):
                if isinstance(result, Exception):
                    logger.error(f"事件处理器 {i} 执行失败: {result}")


class NotificationEventHandler:
    """通知事件处理器"""
    
    def __init__(self, notification_manager: NotificationManager, 
                 user_repository: UserRepository,
                 task_repository: TaskRepository = None,
                 agent_repository: AgentRepository = None):
        self.notification_manager = notification_manager
        self.user_repository = user_repository
        self.task_repository = task_repository
        self.agent_repository = agent_repository
        
        # 配置阈值
        self.credit_low_threshold = 50.0  # 余额不足阈值
        self.credit_critical_threshold = 10.0  # 余额严重不足阈值
    
    async def handle_task_status_changed(self, event: Event):
        """处理任务状态变更事件"""
        try:
            data = event.data
            task_id = data.get('task_id')
            old_status = data.get('old_status')
            new_status = data.get('new_status')
            task_name = data.get('task_name', '未知任务')
            user_id = event.user_id
            
            if not all([task_id, old_status, new_status, user_id]):
                logger.warning("任务状态变更事件数据不完整")
                return
            
            # 获取用户信息
            user = await self.user_repository.get_by_id(user_id)
            if not user:
                logger.warning(f"未找到用户: {user_id}")
                return
            
            # 准备模板数据
            template_data = {
                'task_name': task_name,
                'task_id': task_id,
                'old_status': self._get_status_display(old_status),
                'new_status': self._get_status_display(new_status),
                'change_time': datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S'),
                'error_message': data.get('error_message', '')
            }
            
            # 发送通知
            await self.notification_manager.send_notification(
                notification_type=NotificationType.TASK_STATUS_CHANGE,
                channel=NotificationChannel.EMAIL,
                recipient=user.email,
                template_data=template_data,
                priority=NotificationPriority.NORMAL
            )
            
            logger.info(f"发送任务状态变更通知: {task_id} -> {user.email}")
            
        except Exception as e:
            logger.error(f"处理任务状态变更事件失败: {e}")
    
    async def handle_task_failed(self, event: Event):
        """处理任务失败事件"""
        try:
            data = event.data
            task_id = data.get('task_id')
            task_name = data.get('task_name', '未知任务')
            error_message = data.get('error_message', '未知错误')
            user_id = event.user_id
            
            if not all([task_id, user_id]):
                logger.warning("任务失败事件数据不完整")
                return
            
            # 获取用户信息
            user = await self.user_repository.get_by_id(user_id)
            if not user:
                logger.warning(f"未找到用户: {user_id}")
                return
            
            # 准备模板数据
            template_data = {
                'task_name': task_name,
                'task_id': task_id,
                'old_status': '运行中',
                'new_status': '失败',
                'change_time': datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S'),
                'error_message': error_message
            }
            
            # 发送高优先级通知
            await self.notification_manager.send_notification(
                notification_type=NotificationType.TASK_FAILED,
                channel=NotificationChannel.EMAIL,
                recipient=user.email,
                template_data=template_data,
                priority=NotificationPriority.HIGH
            )
            
            logger.info(f"发送任务失败通知: {task_id} -> {user.email}")
            
        except Exception as e:
            logger.error(f"处理任务失败事件失败: {e}")
    
    async def handle_task_completed(self, event: Event):
        """处理任务完成事件"""
        try:
            data = event.data
            task_id = data.get('task_id')
            task_name = data.get('task_name', '未知任务')
            user_id = event.user_id
            
            if not all([task_id, user_id]):
                logger.warning("任务完成事件数据不完整")
                return
            
            # 获取用户信息
            user = await self.user_repository.get_by_id(user_id)
            if not user:
                logger.warning(f"未找到用户: {user_id}")
                return
            
            # 准备模板数据
            template_data = {
                'task_name': task_name,
                'task_id': task_id,
                'old_status': '运行中',
                'new_status': '已完成',
                'change_time': datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S'),
                'error_message': ''
            }
            
            # 发送通知
            await self.notification_manager.send_notification(
                notification_type=NotificationType.TASK_COMPLETED,
                channel=NotificationChannel.EMAIL,
                recipient=user.email,
                template_data=template_data,
                priority=NotificationPriority.NORMAL
            )
            
            logger.info(f"发送任务完成通知: {task_id} -> {user.email}")
            
        except Exception as e:
            logger.error(f"处理任务完成事件失败: {e}")
    
    async def handle_agent_status_changed(self, event: Event):
        """处理代理状态变更事件"""
        try:
            data = event.data
            agent_id = data.get('agent_id')
            agent_name = data.get('agent_name', '未知代理')
            old_status = data.get('old_status')
            new_status = data.get('new_status')
            
            if not all([agent_id, old_status, new_status]):
                logger.warning("代理状态变更事件数据不完整")
                return
            
            # 只有状态变为离线时才发送通知给管理员
            if new_status == 'offline' and old_status != 'offline':
                await self._send_admin_notification(
                    subject=f"代理离线通知 - {agent_name}",
                    content=f"""
管理员您好，

代理状态发生变更：

代理名称: {agent_name}
代理ID: {agent_id}
原状态: {self._get_agent_status_display(old_status)}
新状态: {self._get_agent_status_display(new_status)}
变更时间: {datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S')}

请及时检查代理状态。

此致
网络拨测平台
                    """,
                    priority=NotificationPriority.HIGH
                )
            
            logger.info(f"处理代理状态变更事件: {agent_id} {old_status} -> {new_status}")
            
        except Exception as e:
            logger.error(f"处理代理状态变更事件失败: {e}")
    
    async def handle_agent_offline(self, event: Event):
        """处理代理离线事件"""
        try:
            data = event.data
            agent_id = data.get('agent_id')
            agent_name = data.get('agent_name', '未知代理')
            last_heartbeat = data.get('last_heartbeat')
            
            if not agent_id:
                logger.warning("代理离线事件数据不完整")
                return
            
            # 发送管理员通知
            await self._send_admin_notification(
                subject=f"代理离线警报 - {agent_name}",
                content=f"""
管理员您好，

代理已离线：

代理名称: {agent_name}
代理ID: {agent_id}
最后心跳: {last_heartbeat or '未知'}
离线时间: {datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S')}

请及时检查代理状态并采取必要措施。

此致
网络拨测平台
                """,
                priority=NotificationPriority.URGENT
            )
            
            logger.info(f"发送代理离线通知: {agent_id}")
            
        except Exception as e:
            logger.error(f"处理代理离线事件失败: {e}")
    
    async def handle_credit_low_balance(self, event: Event):
        """处理余额不足事件"""
        try:
            data = event.data
            user_id = event.user_id
            current_balance = data.get('current_balance', 0)
            threshold = data.get('threshold', self.credit_low_threshold)
            
            if not user_id:
                logger.warning("余额不足事件数据不完整")
                return
            
            # 获取用户信息
            user = await self.user_repository.get_by_id(user_id)
            if not user:
                logger.warning(f"未找到用户: {user_id}")
                return
            
            # 确定优先级
            priority = NotificationPriority.URGENT if current_balance <= self.credit_critical_threshold else NotificationPriority.HIGH
            
            # 准备模板数据
            template_data = {
                'current_balance': str(current_balance),
                'threshold': str(threshold),
                'recharge_url': data.get('recharge_url', '#')
            }
            
            # 发送通知
            await self.notification_manager.send_notification(
                notification_type=NotificationType.CREDIT_LOW_BALANCE,
                channel=NotificationChannel.EMAIL,
                recipient=user.email,
                template_data=template_data,
                priority=priority
            )
            
            logger.info(f"发送余额不足通知: {user_id} -> {user.email}, 余额: {current_balance}")
            
        except Exception as e:
            logger.error(f"处理余额不足事件失败: {e}")
    
    async def handle_system_maintenance(self, event: Event):
        """处理系统维护事件"""
        try:
            data = event.data
            maintenance_start = data.get('maintenance_start')
            maintenance_end = data.get('maintenance_end')
            maintenance_description = data.get('maintenance_description', '系统维护')
            
            if not all([maintenance_start, maintenance_end]):
                logger.warning("系统维护事件数据不完整")
                return
            
            # 准备模板数据
            template_data = {
                'maintenance_start': maintenance_start,
                'maintenance_end': maintenance_end,
                'maintenance_description': maintenance_description
            }
            
            # 获取所有活跃用户
            users = await self.user_repository.get_active_users()
            
            # 批量发送通知
            notifications = []
            for user in users:
                notifications.append({
                    'notification_type': NotificationType.SYSTEM_MAINTENANCE,
                    'channel': NotificationChannel.EMAIL,
                    'recipient': user.email,
                    'template_data': template_data,
                    'priority': NotificationPriority.HIGH
                })
            
            if notifications:
                await self.notification_manager.send_batch_notifications(notifications)
                logger.info(f"发送系统维护通知给 {len(notifications)} 个用户")
            
        except Exception as e:
            logger.error(f"处理系统维护事件失败: {e}")
    
    def _get_status_display(self, status: str) -> str:
        """获取状态显示文本"""
        status_map = {
            'active': '活跃',
            'paused': '暂停',
            'completed': '已完成',
            'failed': '失败',
            'running': '运行中'
        }
        return status_map.get(status, status)
    
    def _get_agent_status_display(self, status: str) -> str:
        """获取代理状态显示文本"""
        status_map = {
            'online': '在线',
            'offline': '离线',
            'busy': '忙碌',
            'maintenance': '维护中'
        }
        return status_map.get(status, status)
    
    async def _send_admin_notification(self, subject: str, content: str, 
                                     priority: NotificationPriority = NotificationPriority.NORMAL):
        """发送管理员通知"""
        try:
            # 获取管理员用户
            admin_users = await self.user_repository.get_admin_users()
            
            if not admin_users:
                logger.warning("没有找到管理员用户")
                return
            
            # 批量发送通知
            notifications = []
            for admin in admin_users:
                notifications.append({
                    'notification_type': NotificationType.SYSTEM_MAINTENANCE,  # 使用通用类型
                    'channel': NotificationChannel.EMAIL,
                    'recipient': admin.email,
                    'template_data': {'subject': subject, 'content': content},
                    'priority': priority
                })
            
            if notifications:
                await self.notification_manager.send_batch_notifications(notifications)
                logger.info(f"发送管理员通知给 {len(notifications)} 个管理员")
                
        except Exception as e:
            logger.error(f"发送管理员通知失败: {e}")


class EventNotificationService:
    """事件通知服务"""
    
    def __init__(self, notification_manager: NotificationManager,
                 user_repository: UserRepository,
                 task_repository: TaskRepository = None,
                 agent_repository: AgentRepository = None):
        self.event_bus = EventBus()
        self.notification_handler = NotificationEventHandler(
            notification_manager, user_repository, task_repository, agent_repository
        )
        self._setup_event_handlers()
    
    def _setup_event_handlers(self):
        """设置事件处理器"""
        # 任务相关事件
        self.event_bus.subscribe(
            EventType.TASK_STATUS_CHANGED,
            self.notification_handler.handle_task_status_changed
        )
        self.event_bus.subscribe(
            EventType.TASK_FAILED,
            self.notification_handler.handle_task_failed
        )
        self.event_bus.subscribe(
            EventType.TASK_COMPLETED,
            self.notification_handler.handle_task_completed
        )
        
        # 代理相关事件
        self.event_bus.subscribe(
            EventType.AGENT_STATUS_CHANGED,
            self.notification_handler.handle_agent_status_changed
        )
        self.event_bus.subscribe(
            EventType.AGENT_OFFLINE,
            self.notification_handler.handle_agent_offline
        )
        
        # 用户相关事件
        self.event_bus.subscribe(
            EventType.CREDIT_LOW_BALANCE,
            self.notification_handler.handle_credit_low_balance
        )
        
        # 系统相关事件
        self.event_bus.subscribe(
            EventType.SYSTEM_MAINTENANCE,
            self.notification_handler.handle_system_maintenance
        )
    
    async def start(self):
        """启动事件通知服务"""
        await self.event_bus.start()
        logger.info("事件通知服务已启动")
    
    async def stop(self):
        """停止事件通知服务"""
        await self.event_bus.stop()
        logger.info("事件通知服务已停止")
    
    async def emit_task_status_changed(self, user_id: str, task_id: str, 
                                     task_name: str, old_status: str, 
                                     new_status: str, error_message: str = None):
        """发出任务状态变更事件"""
        event = Event(
            type=EventType.TASK_STATUS_CHANGED,
            data={
                'task_id': task_id,
                'task_name': task_name,
                'old_status': old_status,
                'new_status': new_status,
                'error_message': error_message
            },
            timestamp=datetime.utcnow(),
            user_id=user_id,
            task_id=task_id
        )
        await self.event_bus.publish(event)
    
    async def emit_task_failed(self, user_id: str, task_id: str, 
                             task_name: str, error_message: str):
        """发出任务失败事件"""
        event = Event(
            type=EventType.TASK_FAILED,
            data={
                'task_id': task_id,
                'task_name': task_name,
                'error_message': error_message
            },
            timestamp=datetime.utcnow(),
            user_id=user_id,
            task_id=task_id
        )
        await self.event_bus.publish(event)
    
    async def emit_task_completed(self, user_id: str, task_id: str, task_name: str):
        """发出任务完成事件"""
        event = Event(
            type=EventType.TASK_COMPLETED,
            data={
                'task_id': task_id,
                'task_name': task_name
            },
            timestamp=datetime.utcnow(),
            user_id=user_id,
            task_id=task_id
        )
        await self.event_bus.publish(event)
    
    async def emit_agent_status_changed(self, agent_id: str, agent_name: str,
                                      old_status: str, new_status: str):
        """发出代理状态变更事件"""
        event = Event(
            type=EventType.AGENT_STATUS_CHANGED,
            data={
                'agent_id': agent_id,
                'agent_name': agent_name,
                'old_status': old_status,
                'new_status': new_status
            },
            timestamp=datetime.utcnow(),
            agent_id=agent_id
        )
        await self.event_bus.publish(event)
    
    async def emit_agent_offline(self, agent_id: str, agent_name: str, 
                               last_heartbeat: str = None):
        """发出代理离线事件"""
        event = Event(
            type=EventType.AGENT_OFFLINE,
            data={
                'agent_id': agent_id,
                'agent_name': agent_name,
                'last_heartbeat': last_heartbeat
            },
            timestamp=datetime.utcnow(),
            agent_id=agent_id
        )
        await self.event_bus.publish(event)
    
    async def emit_credit_low_balance(self, user_id: str, current_balance: float,
                                    threshold: float = 50.0, recharge_url: str = None):
        """发出余额不足事件"""
        event = Event(
            type=EventType.CREDIT_LOW_BALANCE,
            data={
                'current_balance': current_balance,
                'threshold': threshold,
                'recharge_url': recharge_url or '#'
            },
            timestamp=datetime.utcnow(),
            user_id=user_id
        )
        await self.event_bus.publish(event)
    
    async def emit_system_maintenance(self, maintenance_start: str, 
                                    maintenance_end: str,
                                    maintenance_description: str = "系统维护"):
        """发出系统维护事件"""
        event = Event(
            type=EventType.SYSTEM_MAINTENANCE,
            data={
                'maintenance_start': maintenance_start,
                'maintenance_end': maintenance_end,
                'maintenance_description': maintenance_description
            },
            timestamp=datetime.utcnow()
        )
        await self.event_bus.publish(event)
    
    def get_event_statistics(self) -> Dict[str, Any]:
        """获取事件统计信息"""
        return {
            'event_bus_running': self.event_bus._running,
            'registered_handlers': {
                event_type.value: len(handlers)
                for event_type, handlers in self.event_bus._handlers.items()
            },
            'queue_size': self.event_bus._event_queue.qsize() if self.event_bus._event_queue else 0
        }