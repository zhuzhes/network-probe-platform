"""
事件驱动通知系统单元测试
"""

import pytest
import asyncio
from datetime import datetime
from unittest.mock import Mock, AsyncMock, MagicMock

from management_platform.notifications.events import (
    EventType, Event, EventBus, NotificationEventHandler, EventNotificationService
)
from management_platform.notifications.manager import NotificationManager
from management_platform.notifications.types import NotificationType, NotificationChannel, NotificationPriority
from management_platform.database.repositories import UserRepository, TaskRepository, AgentRepository


class MockUser:
    """模拟用户对象"""
    def __init__(self, id, email, role="enterprise"):
        self.id = id
        self.email = email
        self.role = role


class TestEvent:
    """测试事件数据结构"""
    
    def test_event_creation(self):
        """测试事件创建"""
        event = Event(
            type=EventType.TASK_STATUS_CHANGED,
            data={'task_id': '123', 'status': 'completed'},
            timestamp=datetime.utcnow(),
            user_id='user-123',
            task_id='task-123'
        )
        
        assert event.type == EventType.TASK_STATUS_CHANGED
        assert event.data['task_id'] == '123'
        assert event.user_id == 'user-123'
        assert event.task_id == 'task-123'
        assert isinstance(event.timestamp, datetime)


class TestEventBus:
    """测试事件总线"""
    
    @pytest.mark.asyncio
    async def test_subscribe_and_publish(self):
        """测试订阅和发布事件"""
        event_bus = EventBus()
        handler_called = False
        received_event = None
        
        async def test_handler(event):
            nonlocal handler_called, received_event
            handler_called = True
            received_event = event
        
        # 订阅事件
        event_bus.subscribe(EventType.TASK_STATUS_CHANGED, test_handler)
        
        # 启动事件总线
        await event_bus.start()
        
        # 发布事件
        test_event = Event(
            type=EventType.TASK_STATUS_CHANGED,
            data={'test': 'data'},
            timestamp=datetime.utcnow()
        )
        await event_bus.publish(test_event)
        
        # 等待处理
        await asyncio.sleep(0.1)
        
        # 停止事件总线
        await event_bus.stop()
        
        # 验证处理器被调用
        assert handler_called is True
        assert received_event == test_event
    
    @pytest.mark.asyncio
    async def test_multiple_handlers(self):
        """测试多个处理器"""
        event_bus = EventBus()
        handler1_called = False
        handler2_called = False
        
        async def handler1(event):
            nonlocal handler1_called
            handler1_called = True
        
        async def handler2(event):
            nonlocal handler2_called
            handler2_called = True
        
        # 订阅同一事件的多个处理器
        event_bus.subscribe(EventType.TASK_STATUS_CHANGED, handler1)
        event_bus.subscribe(EventType.TASK_STATUS_CHANGED, handler2)
        
        await event_bus.start()
        
        # 发布事件
        test_event = Event(
            type=EventType.TASK_STATUS_CHANGED,
            data={},
            timestamp=datetime.utcnow()
        )
        await event_bus.publish(test_event)
        
        # 等待处理
        await asyncio.sleep(0.1)
        
        await event_bus.stop()
        
        # 验证两个处理器都被调用
        assert handler1_called is True
        assert handler2_called is True
    
    @pytest.mark.asyncio
    async def test_unsubscribe(self):
        """测试取消订阅"""
        event_bus = EventBus()
        handler_called = False
        
        async def test_handler(event):
            nonlocal handler_called
            handler_called = True
        
        # 订阅然后取消订阅
        event_bus.subscribe(EventType.TASK_STATUS_CHANGED, test_handler)
        event_bus.unsubscribe(EventType.TASK_STATUS_CHANGED, test_handler)
        
        await event_bus.start()
        
        # 发布事件
        test_event = Event(
            type=EventType.TASK_STATUS_CHANGED,
            data={},
            timestamp=datetime.utcnow()
        )
        await event_bus.publish(test_event)
        
        # 等待处理
        await asyncio.sleep(0.1)
        
        await event_bus.stop()
        
        # 验证处理器没有被调用
        assert handler_called is False
    
    @pytest.mark.asyncio
    async def test_sync_handler(self):
        """测试同步处理器"""
        event_bus = EventBus()
        handler_called = False
        
        def sync_handler(event):
            nonlocal handler_called
            handler_called = True
        
        event_bus.subscribe(EventType.TASK_STATUS_CHANGED, sync_handler)
        
        await event_bus.start()
        
        test_event = Event(
            type=EventType.TASK_STATUS_CHANGED,
            data={},
            timestamp=datetime.utcnow()
        )
        await event_bus.publish(test_event)
        
        await asyncio.sleep(0.1)
        await event_bus.stop()
        
        assert handler_called is True
    
    @pytest.mark.asyncio
    async def test_handler_exception(self):
        """测试处理器异常"""
        event_bus = EventBus()
        
        async def failing_handler(event):
            raise Exception("Handler failed")
        
        async def working_handler(event):
            # 这个处理器应该仍然被调用
            pass
        
        event_bus.subscribe(EventType.TASK_STATUS_CHANGED, failing_handler)
        event_bus.subscribe(EventType.TASK_STATUS_CHANGED, working_handler)
        
        await event_bus.start()
        
        test_event = Event(
            type=EventType.TASK_STATUS_CHANGED,
            data={},
            timestamp=datetime.utcnow()
        )
        
        # 发布事件不应该抛出异常
        await event_bus.publish(test_event)
        await asyncio.sleep(0.1)
        
        await event_bus.stop()


class TestNotificationEventHandler:
    """测试通知事件处理器"""
    
    def setup_method(self):
        """设置测试"""
        self.notification_manager = Mock(spec=NotificationManager)
        self.notification_manager.send_notification = AsyncMock()
        self.notification_manager.send_batch_notifications = AsyncMock()
        
        self.user_repository = Mock(spec=UserRepository)
        self.user_repository.get_by_id = AsyncMock()
        self.user_repository.get_active_users = AsyncMock()
        self.user_repository.get_admin_users = AsyncMock()
        
        self.handler = NotificationEventHandler(
            self.notification_manager,
            self.user_repository
        )
    
    @pytest.mark.asyncio
    async def test_handle_task_status_changed(self):
        """测试处理任务状态变更事件"""
        # 设置模拟用户
        mock_user = MockUser("user-123", "user@example.com")
        self.user_repository.get_by_id.return_value = mock_user
        
        # 创建事件
        event = Event(
            type=EventType.TASK_STATUS_CHANGED,
            data={
                'task_id': 'task-123',
                'task_name': 'Test Task',
                'old_status': 'active',
                'new_status': 'completed'
            },
            timestamp=datetime.utcnow(),
            user_id='user-123'
        )
        
        # 处理事件
        await self.handler.handle_task_status_changed(event)
        
        # 验证通知发送
        self.notification_manager.send_notification.assert_called_once()
        call_args = self.notification_manager.send_notification.call_args
        
        assert call_args[1]['notification_type'] == NotificationType.TASK_STATUS_CHANGE
        assert call_args[1]['channel'] == NotificationChannel.EMAIL
        assert call_args[1]['recipient'] == 'user@example.com'
        assert 'Test Task' in call_args[1]['template_data']['task_name']
        assert call_args[1]['priority'] == NotificationPriority.NORMAL
    
    @pytest.mark.asyncio
    async def test_handle_task_failed(self):
        """测试处理任务失败事件"""
        mock_user = MockUser("user-123", "user@example.com")
        self.user_repository.get_by_id.return_value = mock_user
        
        event = Event(
            type=EventType.TASK_FAILED,
            data={
                'task_id': 'task-123',
                'task_name': 'Failed Task',
                'error_message': 'Connection timeout'
            },
            timestamp=datetime.utcnow(),
            user_id='user-123'
        )
        
        await self.handler.handle_task_failed(event)
        
        self.notification_manager.send_notification.assert_called_once()
        call_args = self.notification_manager.send_notification.call_args
        
        assert call_args[1]['notification_type'] == NotificationType.TASK_FAILED
        assert call_args[1]['priority'] == NotificationPriority.HIGH
        assert 'Connection timeout' in call_args[1]['template_data']['error_message']
    
    @pytest.mark.asyncio
    async def test_handle_task_completed(self):
        """测试处理任务完成事件"""
        mock_user = MockUser("user-123", "user@example.com")
        self.user_repository.get_by_id.return_value = mock_user
        
        event = Event(
            type=EventType.TASK_COMPLETED,
            data={
                'task_id': 'task-123',
                'task_name': 'Completed Task'
            },
            timestamp=datetime.utcnow(),
            user_id='user-123'
        )
        
        await self.handler.handle_task_completed(event)
        
        self.notification_manager.send_notification.assert_called_once()
        call_args = self.notification_manager.send_notification.call_args
        
        assert call_args[1]['notification_type'] == NotificationType.TASK_COMPLETED
        assert call_args[1]['priority'] == NotificationPriority.NORMAL
    
    @pytest.mark.asyncio
    async def test_handle_agent_offline(self):
        """测试处理代理离线事件"""
        # 设置管理员用户
        admin_user = MockUser("admin-123", "admin@example.com", "admin")
        self.user_repository.get_admin_users.return_value = [admin_user]
        
        event = Event(
            type=EventType.AGENT_OFFLINE,
            data={
                'agent_id': 'agent-123',
                'agent_name': 'Test Agent',
                'last_heartbeat': '2023-01-01 12:00:00'
            },
            timestamp=datetime.utcnow(),
            agent_id='agent-123'
        )
        
        await self.handler.handle_agent_offline(event)
        
        # 验证批量通知发送
        self.notification_manager.send_batch_notifications.assert_called_once()
        call_args = self.notification_manager.send_batch_notifications.call_args[0][0]
        
        assert len(call_args) == 1
        assert call_args[0]['recipient'] == 'admin@example.com'
        assert call_args[0]['priority'] == NotificationPriority.URGENT
    
    @pytest.mark.asyncio
    async def test_handle_credit_low_balance(self):
        """测试处理余额不足事件"""
        mock_user = MockUser("user-123", "user@example.com")
        self.user_repository.get_by_id.return_value = mock_user
        
        event = Event(
            type=EventType.CREDIT_LOW_BALANCE,
            data={
                'current_balance': 25.0,
                'threshold': 50.0,
                'recharge_url': 'https://example.com/recharge'
            },
            timestamp=datetime.utcnow(),
            user_id='user-123'
        )
        
        await self.handler.handle_credit_low_balance(event)
        
        self.notification_manager.send_notification.assert_called_once()
        call_args = self.notification_manager.send_notification.call_args
        
        assert call_args[1]['notification_type'] == NotificationType.CREDIT_LOW_BALANCE
        assert call_args[1]['priority'] == NotificationPriority.HIGH
        assert call_args[1]['template_data']['current_balance'] == '25.0'
    
    @pytest.mark.asyncio
    async def test_handle_credit_critical_balance(self):
        """测试处理余额严重不足事件"""
        mock_user = MockUser("user-123", "user@example.com")
        self.user_repository.get_by_id.return_value = mock_user
        
        event = Event(
            type=EventType.CREDIT_LOW_BALANCE,
            data={
                'current_balance': 5.0,  # 低于临界阈值
                'threshold': 50.0
            },
            timestamp=datetime.utcnow(),
            user_id='user-123'
        )
        
        await self.handler.handle_credit_low_balance(event)
        
        call_args = self.notification_manager.send_notification.call_args
        assert call_args[1]['priority'] == NotificationPriority.URGENT
    
    @pytest.mark.asyncio
    async def test_handle_system_maintenance(self):
        """测试处理系统维护事件"""
        # 设置活跃用户
        users = [
            MockUser("user-1", "user1@example.com"),
            MockUser("user-2", "user2@example.com")
        ]
        self.user_repository.get_active_users.return_value = users
        
        event = Event(
            type=EventType.SYSTEM_MAINTENANCE,
            data={
                'maintenance_start': '2023-01-01 02:00:00',
                'maintenance_end': '2023-01-01 04:00:00',
                'maintenance_description': '数据库升级'
            },
            timestamp=datetime.utcnow()
        )
        
        await self.handler.handle_system_maintenance(event)
        
        # 验证批量通知发送
        self.notification_manager.send_batch_notifications.assert_called_once()
        call_args = self.notification_manager.send_batch_notifications.call_args[0][0]
        
        assert len(call_args) == 2
        assert call_args[0]['recipient'] == 'user1@example.com'
        assert call_args[1]['recipient'] == 'user2@example.com'
        assert all(n['priority'] == NotificationPriority.HIGH for n in call_args)
    
    @pytest.mark.asyncio
    async def test_handle_missing_user(self):
        """测试处理用户不存在的情况"""
        self.user_repository.get_by_id.return_value = None
        
        event = Event(
            type=EventType.TASK_STATUS_CHANGED,
            data={
                'task_id': 'task-123',
                'task_name': 'Test Task',
                'old_status': 'active',
                'new_status': 'completed'
            },
            timestamp=datetime.utcnow(),
            user_id='nonexistent-user'
        )
        
        await self.handler.handle_task_status_changed(event)
        
        # 验证没有发送通知
        self.notification_manager.send_notification.assert_not_called()
    
    @pytest.mark.asyncio
    async def test_handle_incomplete_event_data(self):
        """测试处理不完整事件数据"""
        event = Event(
            type=EventType.TASK_STATUS_CHANGED,
            data={
                'task_id': 'task-123',
                # 缺少必要字段
            },
            timestamp=datetime.utcnow(),
            user_id='user-123'
        )
        
        await self.handler.handle_task_status_changed(event)
        
        # 验证没有发送通知
        self.notification_manager.send_notification.assert_not_called()


class TestEventNotificationService:
    """测试事件通知服务"""
    
    def setup_method(self):
        """设置测试"""
        self.notification_manager = Mock(spec=NotificationManager)
        self.user_repository = Mock(spec=UserRepository)
        
        self.service = EventNotificationService(
            self.notification_manager,
            self.user_repository
        )
    
    @pytest.mark.asyncio
    async def test_service_lifecycle(self):
        """测试服务生命周期"""
        # 启动服务
        await self.service.start()
        assert self.service.event_bus._running is True
        
        # 停止服务
        await self.service.stop()
        assert self.service.event_bus._running is False
    
    @pytest.mark.asyncio
    async def test_emit_task_status_changed(self):
        """测试发出任务状态变更事件"""
        await self.service.start()
        
        # 发出事件
        await self.service.emit_task_status_changed(
            user_id='user-123',
            task_id='task-123',
            task_name='Test Task',
            old_status='active',
            new_status='completed'
        )
        
        # 验证事件被加入队列
        assert self.service.event_bus._event_queue.qsize() == 1
        
        await self.service.stop()
    
    @pytest.mark.asyncio
    async def test_emit_task_failed(self):
        """测试发出任务失败事件"""
        await self.service.start()
        
        await self.service.emit_task_failed(
            user_id='user-123',
            task_id='task-123',
            task_name='Failed Task',
            error_message='Connection timeout'
        )
        
        assert self.service.event_bus._event_queue.qsize() == 1
        
        await self.service.stop()
    
    @pytest.mark.asyncio
    async def test_emit_agent_offline(self):
        """测试发出代理离线事件"""
        await self.service.start()
        
        await self.service.emit_agent_offline(
            agent_id='agent-123',
            agent_name='Test Agent',
            last_heartbeat='2023-01-01 12:00:00'
        )
        
        assert self.service.event_bus._event_queue.qsize() == 1
        
        await self.service.stop()
    
    @pytest.mark.asyncio
    async def test_emit_credit_low_balance(self):
        """测试发出余额不足事件"""
        await self.service.start()
        
        await self.service.emit_credit_low_balance(
            user_id='user-123',
            current_balance=25.0,
            threshold=50.0,
            recharge_url='https://example.com/recharge'
        )
        
        assert self.service.event_bus._event_queue.qsize() == 1
        
        await self.service.stop()
    
    @pytest.mark.asyncio
    async def test_emit_system_maintenance(self):
        """测试发出系统维护事件"""
        await self.service.start()
        
        await self.service.emit_system_maintenance(
            maintenance_start='2023-01-01 02:00:00',
            maintenance_end='2023-01-01 04:00:00',
            maintenance_description='数据库升级'
        )
        
        assert self.service.event_bus._event_queue.qsize() == 1
        
        await self.service.stop()
    
    def test_get_event_statistics(self):
        """测试获取事件统计信息"""
        stats = self.service.get_event_statistics()
        
        assert 'event_bus_running' in stats
        assert 'registered_handlers' in stats
        assert 'queue_size' in stats
        
        # 验证注册的处理器数量
        assert len(stats['registered_handlers']) > 0
        assert stats['registered_handlers']['task_status_changed'] == 1
        assert stats['registered_handlers']['task_failed'] == 1
        assert stats['registered_handlers']['agent_offline'] == 1
    
    @pytest.mark.asyncio
    async def test_multiple_events_processing(self):
        """测试多个事件处理"""
        await self.service.start()
        
        # 发出多个事件
        await self.service.emit_task_status_changed(
            'user-1', 'task-1', 'Task 1', 'active', 'completed'
        )
        await self.service.emit_task_failed(
            'user-2', 'task-2', 'Task 2', 'Connection failed'
        )
        await self.service.emit_agent_offline(
            'agent-1', 'Agent 1'
        )
        
        # 验证所有事件都被加入队列
        assert self.service.event_bus._event_queue.qsize() == 3
        
        await self.service.stop()
    
    @pytest.mark.asyncio
    async def test_event_handler_registration(self):
        """测试事件处理器注册"""
        # 验证所有必要的事件类型都有处理器
        expected_events = [
            EventType.TASK_STATUS_CHANGED,
            EventType.TASK_FAILED,
            EventType.TASK_COMPLETED,
            EventType.AGENT_STATUS_CHANGED,
            EventType.AGENT_OFFLINE,
            EventType.CREDIT_LOW_BALANCE,
            EventType.SYSTEM_MAINTENANCE
        ]
        
        for event_type in expected_events:
            assert event_type in self.service.event_bus._handlers
            assert len(self.service.event_bus._handlers[event_type]) > 0