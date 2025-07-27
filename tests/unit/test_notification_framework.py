"""
通知框架单元测试
"""

import pytest
import asyncio
from datetime import datetime, timedelta
from unittest.mock import Mock, AsyncMock, patch

from management_platform.notifications.types import (
    NotificationType, NotificationChannel, NotificationStatus, 
    NotificationPriority, NotificationData
)
from management_platform.notifications.base import (
    NotificationBase, NotificationTemplate, NotificationConfig, TemplateManager
)
from management_platform.notifications.queue import NotificationQueue
from management_platform.notifications.manager import NotificationManager


class MockNotificationSender(NotificationBase):
    """模拟通知发送器"""
    
    def __init__(self, config: NotificationConfig, should_fail: bool = False):
        super().__init__(config)
        self.should_fail = should_fail
        self.sent_notifications = []
    
    async def send(self, notification: NotificationData) -> bool:
        if self.should_fail:
            raise Exception("模拟发送失败")
        
        self.sent_notifications.append(notification)
        return True
    
    def validate_recipient(self, recipient: str) -> bool:
        return "@" in recipient  # 简单的邮箱验证


class TestNotificationTypes:
    """测试通知类型定义"""
    
    def test_notification_data_creation(self):
        """测试通知数据创建"""
        notification = NotificationData(
            id="test-id",
            type=NotificationType.TASK_STATUS_CHANGE,
            channel=NotificationChannel.EMAIL,
            recipient="test@example.com",
            subject="Test Subject",
            content="Test Content",
            template_data={"key": "value"}
        )
        
        assert notification.id == "test-id"
        assert notification.type == NotificationType.TASK_STATUS_CHANGE
        assert notification.channel == NotificationChannel.EMAIL
        assert notification.priority == NotificationPriority.NORMAL
        assert notification.status == NotificationStatus.PENDING
        assert notification.retry_count == 0
        assert notification.max_retries == 3


class TestNotificationBase:
    """测试通知基类"""
    
    def test_template_rendering(self):
        """测试模板渲染"""
        config = NotificationConfig()
        sender = MockNotificationSender(config)
        
        template = "Hello {{name}}, your task {{task_id}} is {{status}}"
        data = {"name": "John", "task_id": "123", "status": "completed"}
        
        result = sender.render_template(template, data)
        assert result == "Hello John, your task 123 is completed"
    
    def test_template_rendering_error(self):
        """测试模板渲染错误处理"""
        config = NotificationConfig()
        sender = MockNotificationSender(config)
        
        template = "Hello {{name}}, your task {{undefined_var}} is {{status}}"
        data = {"name": "John", "status": "completed"}
        
        # 应该返回渲染后的内容，未定义变量被替换为空字符串
        result = sender.render_template(template, data)
        assert "Hello John, your task" in result
        assert "is completed" in result
    
    def test_prepare_notification(self):
        """测试通知准备"""
        config = NotificationConfig()
        sender = MockNotificationSender(config)
        
        notification = NotificationData(
            id="test-id",
            type=NotificationType.TASK_STATUS_CHANGE,
            channel=NotificationChannel.EMAIL,
            recipient="test@example.com",
            subject="Task {{task_id}} status changed",
            content="Your task {{task_id}} is now {{status}}",
            template_data={"task_id": "123", "status": "completed"}
        )
        
        prepared = sender.prepare_notification(notification)
        assert prepared.subject == "Task 123 status changed"
        assert prepared.content == "Your task 123 is now completed"
    
    @pytest.mark.asyncio
    async def test_send_with_retry_success(self):
        """测试重试发送成功"""
        config = NotificationConfig(max_retries=3)
        sender = MockNotificationSender(config)
        
        notification = NotificationData(
            id="test-id",
            type=NotificationType.TASK_STATUS_CHANGE,
            channel=NotificationChannel.EMAIL,
            recipient="test@example.com",
            subject="Test",
            content="Test",
            template_data={}
        )
        
        success = await sender.send_with_retry(notification)
        assert success is True
        assert notification.status == NotificationStatus.SENT
        assert notification.sent_at is not None
        assert len(sender.sent_notifications) == 1
    
    @pytest.mark.asyncio
    async def test_send_with_retry_failure(self):
        """测试重试发送失败"""
        config = NotificationConfig(max_retries=2, retry_delay=0.1)
        sender = MockNotificationSender(config, should_fail=True)
        
        notification = NotificationData(
            id="test-id",
            type=NotificationType.TASK_STATUS_CHANGE,
            channel=NotificationChannel.EMAIL,
            recipient="test@example.com",
            subject="Test",
            content="Test",
            template_data={}
        )
        
        success = await sender.send_with_retry(notification)
        assert success is False
        assert notification.status == NotificationStatus.FAILED
        assert notification.error_message is not None
        assert notification.retry_count == 2  # 最后一次尝试的计数


class TestTemplateManager:
    """测试模板管理器"""
    
    def test_default_templates_loaded(self):
        """测试默认模板加载"""
        manager = TemplateManager()
        
        # 检查默认模板是否加载
        assert manager.get_template("task_status_change") is not None
        assert manager.get_template("credit_low_balance") is not None
        assert manager.get_template("system_maintenance") is not None
    
    def test_add_template(self):
        """测试添加模板"""
        manager = TemplateManager()
        
        template = NotificationTemplate(
            id="custom_template",
            name="Custom Template",
            channel=NotificationChannel.EMAIL,
            subject_template="Custom Subject",
            content_template="Custom Content",
            variables=["var1", "var2"],
            created_at=datetime.utcnow(),
            updated_at=datetime.utcnow()
        )
        
        manager.add_template(template)
        retrieved = manager.get_template("custom_template")
        
        assert retrieved is not None
        assert retrieved.name == "Custom Template"
        assert retrieved.subject_template == "Custom Subject"
    
    def test_update_template(self):
        """测试更新模板"""
        manager = TemplateManager()
        
        # 获取现有模板
        original = manager.get_template("task_status_change")
        original_updated_at = original.updated_at
        
        # 更新模板
        updated_template = NotificationTemplate(
            id="task_status_change",
            name="Updated Template",
            channel=NotificationChannel.EMAIL,
            subject_template="Updated Subject",
            content_template="Updated Content",
            variables=["var1"],
            created_at=original.created_at,
            updated_at=original.updated_at
        )
        
        manager.update_template("task_status_change", updated_template)
        retrieved = manager.get_template("task_status_change")
        
        assert retrieved.name == "Updated Template"
        assert retrieved.updated_at > original_updated_at
    
    def test_delete_template(self):
        """测试删除模板"""
        manager = TemplateManager()
        
        # 确认模板存在
        assert manager.get_template("task_status_change") is not None
        
        # 删除模板
        manager.delete_template("task_status_change")
        
        # 确认模板已删除
        assert manager.get_template("task_status_change") is None
    
    def test_list_templates(self):
        """测试列出模板"""
        manager = TemplateManager()
        templates = manager.list_templates()
        
        assert len(templates) >= 3  # 至少有3个默认模板
        template_ids = [t.id for t in templates]
        assert "task_status_change" in template_ids
        assert "credit_low_balance" in template_ids
        assert "system_maintenance" in template_ids


class TestNotificationQueue:
    """测试通知队列"""
    
    @pytest.mark.asyncio
    async def test_enqueue_dequeue(self):
        """测试入队和出队"""
        queue = NotificationQueue()
        
        notification = NotificationData(
            id="test-id",
            type=NotificationType.TASK_STATUS_CHANGE,
            channel=NotificationChannel.EMAIL,
            recipient="test@example.com",
            subject="Test",
            content="Test",
            template_data={},
            priority=NotificationPriority.HIGH
        )
        
        # 入队
        success = await queue.enqueue(notification)
        assert success is True
        
        # 出队
        dequeued = await queue.dequeue()
        assert dequeued is not None
        assert dequeued.id == "test-id"
        assert dequeued.status == NotificationStatus.PROCESSING
        assert dequeued.priority == NotificationPriority.HIGH
    
    @pytest.mark.asyncio
    async def test_priority_ordering(self):
        """测试优先级排序"""
        queue = NotificationQueue()
        
        # 添加不同优先级的通知
        notifications = [
            NotificationData(
                id="low",
                type=NotificationType.TASK_STATUS_CHANGE,
                channel=NotificationChannel.EMAIL,
                recipient="test@example.com",
                subject="Test",
                content="Test",
                template_data={},
                priority=NotificationPriority.LOW
            ),
            NotificationData(
                id="urgent",
                type=NotificationType.TASK_STATUS_CHANGE,
                channel=NotificationChannel.EMAIL,
                recipient="test@example.com",
                subject="Test",
                content="Test",
                template_data={},
                priority=NotificationPriority.URGENT
            ),
            NotificationData(
                id="normal",
                type=NotificationType.TASK_STATUS_CHANGE,
                channel=NotificationChannel.EMAIL,
                recipient="test@example.com",
                subject="Test",
                content="Test",
                template_data={},
                priority=NotificationPriority.NORMAL
            )
        ]
        
        # 入队
        for notification in notifications:
            await queue.enqueue(notification)
        
        # 出队应该按优先级顺序
        first = await queue.dequeue()
        second = await queue.dequeue()
        third = await queue.dequeue()
        
        assert first.id == "urgent"
        assert second.id == "normal"
        assert third.id == "low"
    
    @pytest.mark.asyncio
    async def test_mark_completed(self):
        """测试标记完成"""
        queue = NotificationQueue()
        
        notification = NotificationData(
            id="test-id",
            type=NotificationType.TASK_STATUS_CHANGE,
            channel=NotificationChannel.EMAIL,
            recipient="test@example.com",
            subject="Test",
            content="Test",
            template_data={}
        )
        
        await queue.enqueue(notification)
        dequeued = await queue.dequeue()
        
        # 标记成功
        await queue.mark_completed("test-id", True)
        
        stats = await queue.get_stats()
        assert stats['total_processed'] == 1
        assert stats['processing_count'] == 0
    
    @pytest.mark.asyncio
    async def test_mark_failed(self):
        """测试标记失败"""
        queue = NotificationQueue()
        
        notification = NotificationData(
            id="test-id",
            type=NotificationType.TASK_STATUS_CHANGE,
            channel=NotificationChannel.EMAIL,
            recipient="test@example.com",
            subject="Test",
            content="Test",
            template_data={}
        )
        
        await queue.enqueue(notification)
        dequeued = await queue.dequeue()
        
        # 标记失败
        await queue.mark_completed("test-id", False, "Test error")
        
        stats = await queue.get_stats()
        assert stats['total_failed'] == 1
        assert stats['failed_count'] == 1
        
        failed_notifications = await queue.get_failed_notifications()
        assert len(failed_notifications) == 1
        assert failed_notifications[0].error_message == "Test error"
    
    @pytest.mark.asyncio
    async def test_requeue(self):
        """测试重新入队"""
        queue = NotificationQueue()
        
        notification = NotificationData(
            id="test-id",
            type=NotificationType.TASK_STATUS_CHANGE,
            channel=NotificationChannel.EMAIL,
            recipient="test@example.com",
            subject="Test",
            content="Test",
            template_data={}
        )
        
        await queue.enqueue(notification)
        dequeued = await queue.dequeue()
        
        # 重新入队
        success = await queue.requeue(dequeued)
        assert success is True
        
        # 应该能再次出队
        requeued = await queue.dequeue()
        assert requeued.id == "test-id"
        assert requeued.status == NotificationStatus.PROCESSING
    
    @pytest.mark.asyncio
    async def test_queue_full(self):
        """测试队列满的情况"""
        queue = NotificationQueue(max_size=2)
        
        # 添加两个通知
        for i in range(2):
            notification = NotificationData(
                id=f"test-{i}",
                type=NotificationType.TASK_STATUS_CHANGE,
                channel=NotificationChannel.EMAIL,
                recipient="test@example.com",
                subject="Test",
                content="Test",
                template_data={}
            )
            success = await queue.enqueue(notification)
            assert success is True
        
        # 第三个通知应该失败
        notification = NotificationData(
            id="test-overflow",
            type=NotificationType.TASK_STATUS_CHANGE,
            channel=NotificationChannel.EMAIL,
            recipient="test@example.com",
            subject="Test",
            content="Test",
            template_data={}
        )
        success = await queue.enqueue(notification)
        assert success is False


class TestNotificationManager:
    """测试通知管理器"""
    
    @pytest.mark.asyncio
    async def test_register_sender(self):
        """测试注册发送器"""
        manager = NotificationManager()
        config = NotificationConfig()
        sender = MockNotificationSender(config)
        
        manager.register_sender(NotificationChannel.EMAIL, sender)
        
        assert NotificationChannel.EMAIL in manager.senders
        assert manager.senders[NotificationChannel.EMAIL] == sender
    
    @pytest.mark.asyncio
    async def test_send_notification(self):
        """测试发送通知"""
        manager = NotificationManager()
        config = NotificationConfig()
        sender = MockNotificationSender(config)
        
        manager.register_sender(NotificationChannel.EMAIL, sender)
        
        notification_id = await manager.send_notification(
            notification_type=NotificationType.TASK_STATUS_CHANGE,
            channel=NotificationChannel.EMAIL,
            recipient="test@example.com",
            template_data={"task_name": "Test Task", "task_id": "123", "old_status": "running", "new_status": "completed", "change_time": "2023-01-01 12:00:00"}
        )
        
        assert notification_id is not None
        
        # 检查队列统计
        stats = await manager.get_statistics()
        assert stats['queue_stats']['total_enqueued'] == 1
    
    @pytest.mark.asyncio
    async def test_send_notification_unregistered_channel(self):
        """测试发送到未注册渠道的通知"""
        manager = NotificationManager()
        
        with pytest.raises(ValueError, match="未注册的通知渠道"):
            await manager.send_notification(
                notification_type=NotificationType.TASK_STATUS_CHANGE,
                channel=NotificationChannel.EMAIL,
                recipient="test@example.com",
                template_data={}
            )
    
    @pytest.mark.asyncio
    async def test_send_notification_invalid_template(self):
        """测试发送无效模板的通知"""
        manager = NotificationManager()
        config = NotificationConfig()
        sender = MockNotificationSender(config)
        
        manager.register_sender(NotificationChannel.EMAIL, sender)
        
        with pytest.raises(ValueError, match="未找到模板"):
            await manager.send_notification(
                notification_type=NotificationType.TASK_STATUS_CHANGE,
                channel=NotificationChannel.EMAIL,
                recipient="test@example.com",
                template_data={},
                template_id="nonexistent_template"
            )
    
    @pytest.mark.asyncio
    async def test_batch_send_notifications(self):
        """测试批量发送通知"""
        manager = NotificationManager()
        config = NotificationConfig()
        sender = MockNotificationSender(config)
        
        manager.register_sender(NotificationChannel.EMAIL, sender)
        
        notifications = [
            {
                'notification_type': NotificationType.TASK_STATUS_CHANGE,
                'channel': NotificationChannel.EMAIL,
                'recipient': 'test1@example.com',
                'template_data': {"task_name": "Task 1", "task_id": "123", "old_status": "running", "new_status": "completed", "change_time": "2023-01-01 12:00:00"}
            },
            {
                'notification_type': NotificationType.CREDIT_LOW_BALANCE,
                'channel': NotificationChannel.EMAIL,
                'recipient': 'test2@example.com',
                'template_data': {"current_balance": "10", "threshold": "50", "recharge_url": "http://example.com/recharge"}
            }
        ]
        
        notification_ids = await manager.send_batch_notifications(notifications)
        
        assert len(notification_ids) == 2
        assert all(nid is not None for nid in notification_ids)
    
    @pytest.mark.asyncio
    async def test_worker_lifecycle(self):
        """测试工作线程生命周期"""
        manager = NotificationManager()
        
        # 启动工作线程
        await manager.start_worker()
        assert manager._running is True
        assert manager._worker_task is not None
        
        # 停止工作线程
        await manager.stop_worker()
        assert manager._running is False
    
    @pytest.mark.asyncio
    async def test_process_notification_success(self):
        """测试处理通知成功"""
        manager = NotificationManager()
        config = NotificationConfig()
        sender = MockNotificationSender(config)
        
        manager.register_sender(NotificationChannel.EMAIL, sender)
        
        # 发送通知
        notification_id = await manager.send_notification(
            notification_type=NotificationType.TASK_STATUS_CHANGE,
            channel=NotificationChannel.EMAIL,
            recipient="test@example.com",
            template_data={"task_name": "Test Task", "task_id": "123", "old_status": "running", "new_status": "completed", "change_time": "2023-01-01 12:00:00"}
        )
        
        # 启动工作线程并等待处理
        await manager.start_worker()
        await asyncio.sleep(0.1)  # 等待处理
        await manager.stop_worker()
        
        # 检查发送结果
        assert len(sender.sent_notifications) == 1
        sent_notification = sender.sent_notifications[0]
        assert "Test Task" in sent_notification.subject
    
    @pytest.mark.asyncio
    async def test_rate_limiting(self):
        """测试速率限制"""
        config = NotificationConfig(rate_limit=2)  # 每分钟最多2条
        manager = NotificationManager(config)
        sender = MockNotificationSender(config)
        
        manager.register_sender(NotificationChannel.EMAIL, sender)
        
        # 发送3条通知
        for i in range(3):
            await manager.send_notification(
                notification_type=NotificationType.TASK_STATUS_CHANGE,
                channel=NotificationChannel.EMAIL,
                recipient=f"test{i}@example.com",
                template_data={"task_name": f"Task {i}", "task_id": str(i), "old_status": "running", "new_status": "completed", "change_time": "2023-01-01 12:00:00"}
            )
        
        # 启动工作线程并等待处理
        await manager.start_worker()
        await asyncio.sleep(0.2)  # 等待处理
        await manager.stop_worker()
        
        # 由于速率限制，应该只发送了2条
        assert len(sender.sent_notifications) <= 2
    
    @pytest.mark.asyncio
    async def test_get_statistics(self):
        """测试获取统计信息"""
        manager = NotificationManager()
        config = NotificationConfig()
        sender = MockNotificationSender(config)
        
        manager.register_sender(NotificationChannel.EMAIL, sender)
        
        stats = await manager.get_statistics()
        
        assert 'queue_stats' in stats
        assert 'registered_senders' in stats
        assert 'worker_running' in stats
        assert 'config' in stats
        assert NotificationChannel.EMAIL in stats['registered_senders']
    
    @pytest.mark.asyncio
    async def test_retry_failed_notifications(self):
        """测试重试失败的通知"""
        config = NotificationConfig(max_retries=1, retry_delay=0.01)  # 减少重试次数和延迟
        manager = NotificationManager(config)
        sender = MockNotificationSender(config, should_fail=True)
        
        manager.register_sender(NotificationChannel.EMAIL, sender)
        
        # 发送一个会失败的通知
        notification_id = await manager.send_notification(
            notification_type=NotificationType.TASK_STATUS_CHANGE,
            channel=NotificationChannel.EMAIL,
            recipient="test@example.com",
            template_data={"task_name": "Test Task", "task_id": "123", "old_status": "running", "new_status": "completed", "change_time": "2023-01-01 12:00:00"}
        )
        
        # 处理通知（会失败）
        await manager.start_worker()
        await asyncio.sleep(0.5)  # 增加等待时间确保处理完成
        await manager.stop_worker()
        
        # 检查失败统计
        stats = await manager.get_statistics()
        assert stats['queue_stats']['total_failed'] > 0
        
        # 修复发送器并重试
        sender.should_fail = False
        retry_count = await manager.retry_failed_notifications()
        
        assert retry_count > 0