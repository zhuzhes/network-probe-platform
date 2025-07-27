"""
邮件通知功能单元测试
"""

import pytest
import asyncio
from unittest.mock import Mock, AsyncMock, patch, MagicMock
from email.mime.multipart import MIMEMultipart
import smtplib

from management_platform.notifications.email import EmailSender, EmailConfig, EmailTemplateRenderer
from management_platform.notifications.base import NotificationConfig
from management_platform.notifications.types import (
    NotificationData, NotificationChannel, NotificationType, NotificationStatus
)


class TestEmailConfig:
    """测试邮件配置"""
    
    def test_email_config_creation(self):
        """测试邮件配置创建"""
        config = EmailConfig(
            smtp_server="smtp.example.com",
            smtp_port=587,
            username="test@example.com",
            password="password123",
            from_name="Test Platform"
        )
        
        assert config.smtp_server == "smtp.example.com"
        assert config.smtp_port == 587
        assert config.username == "test@example.com"
        assert config.from_email == "test@example.com"  # 自动设置
        assert config.from_name == "Test Platform"
        assert config.use_tls is True
        assert config.use_ssl is False
    
    def test_email_config_custom_from_email(self):
        """测试自定义发件人邮箱"""
        config = EmailConfig(
            smtp_server="smtp.example.com",
            username="login@example.com",
            password="password123",
            from_email="noreply@example.com"
        )
        
        assert config.username == "login@example.com"
        assert config.from_email == "noreply@example.com"


class TestEmailSender:
    """测试邮件发送器"""
    
    def test_email_sender_creation(self):
        """测试邮件发送器创建"""
        notification_config = NotificationConfig()
        email_config = EmailConfig(
            smtp_server="smtp.example.com",
            username="test@example.com",
            password="password123"
        )
        
        sender = EmailSender(notification_config, email_config)
        assert sender.email_config == email_config
    
    def test_email_sender_invalid_config(self):
        """测试无效配置"""
        notification_config = NotificationConfig()
        
        # 缺少SMTP服务器
        with pytest.raises(ValueError, match="SMTP服务器地址不能为空"):
            email_config = EmailConfig(
                smtp_server="",
                username="test@example.com",
                password="password123"
            )
            EmailSender(notification_config, email_config)
            
        # 缺少用户名
        with pytest.raises(ValueError, match="SMTP用户名不能为空"):
            email_config = EmailConfig(
                smtp_server="smtp.example.com",
                username="",
                password="password123"
            )
            EmailSender(notification_config, email_config)
            
        # 缺少密码
        with pytest.raises(ValueError, match="SMTP密码不能为空"):
            email_config = EmailConfig(
                smtp_server="smtp.example.com",
                username="test@example.com",
                password=""
            )
            EmailSender(notification_config, email_config)
    
    def test_validate_recipient(self):
        """测试收件人验证"""
        notification_config = NotificationConfig()
        email_config = EmailConfig(
            smtp_server="smtp.example.com",
            username="test@example.com",
            password="password123"
        )
        sender = EmailSender(notification_config, email_config)
        
        # 有效邮箱
        assert sender.validate_recipient("user@example.com") is True
        assert sender.validate_recipient("test.user+tag@domain.co.uk") is True
        
        # 无效邮箱
        assert sender.validate_recipient("invalid-email") is False
        assert sender.validate_recipient("@example.com") is False
        assert sender.validate_recipient("user@") is False
        assert sender.validate_recipient("") is False
    
    def test_create_message(self):
        """测试创建邮件消息"""
        notification_config = NotificationConfig()
        email_config = EmailConfig(
            smtp_server="smtp.example.com",
            username="test@example.com",
            password="password123",
            from_name="Test Platform"
        )
        sender = EmailSender(notification_config, email_config)
        
        notification = NotificationData(
            id="test-id",
            type=NotificationType.TASK_STATUS_CHANGE,
            channel=NotificationChannel.EMAIL,
            recipient="user@example.com",
            subject="Test Subject",
            content="Test Content",
            template_data={}
        )
        
        message = sender._create_message(notification)
        
        assert isinstance(message, MIMEMultipart)
        assert message["Subject"] == "Test Subject"
        assert message["From"] == "Test Platform <test@example.com>"
        assert message["To"] == "user@example.com"
    
    def test_contains_html(self):
        """测试HTML内容检测"""
        notification_config = NotificationConfig()
        email_config = EmailConfig(
            smtp_server="smtp.example.com",
            username="test@example.com",
            password="password123"
        )
        sender = EmailSender(notification_config, email_config)
        
        # 包含HTML标签
        assert sender._contains_html("Hello <br> World") is True
        assert sender._contains_html("This is <strong>bold</strong>") is True
        
        # 不包含HTML标签
        assert sender._contains_html("Plain text content") is False
        assert sender._contains_html("No HTML here") is False
    
    def test_text_to_html(self):
        """测试文本转HTML"""
        notification_config = NotificationConfig()
        email_config = EmailConfig(
            smtp_server="smtp.example.com",
            username="test@example.com",
            password="password123"
        )
        sender = EmailSender(notification_config, email_config)
        
        text = "Line 1\nLine 2\nLine 3"
        html = sender._text_to_html(text)
        
        assert "<html>" in html
        assert "<body>" in html
        assert "<br>" in html
        assert "Line 1<br>" in html
    
    @pytest.mark.asyncio
    async def test_send_success(self):
        """测试发送成功"""
        notification_config = NotificationConfig()
        email_config = EmailConfig(
            smtp_server="smtp.example.com",
            username="test@example.com",
            password="password123"
        )
        sender = EmailSender(notification_config, email_config)
        
        notification = NotificationData(
            id="test-id",
            type=NotificationType.TASK_STATUS_CHANGE,
            channel=NotificationChannel.EMAIL,
            recipient="user@example.com",
            subject="Test Subject",
            content="Test Content",
            template_data={}
        )
        
        # Mock SMTP发送
        with patch.object(sender, '_send_email', new_callable=AsyncMock) as mock_send:
            mock_send.return_value = None
            
            result = await sender.send(notification)
            
            assert result is True
            mock_send.assert_called_once()
    
    @pytest.mark.asyncio
    async def test_send_failure(self):
        """测试发送失败"""
        notification_config = NotificationConfig()
        email_config = EmailConfig(
            smtp_server="smtp.example.com",
            username="test@example.com",
            password="password123"
        )
        sender = EmailSender(notification_config, email_config)
        
        notification = NotificationData(
            id="test-id",
            type=NotificationType.TASK_STATUS_CHANGE,
            channel=NotificationChannel.EMAIL,
            recipient="user@example.com",
            subject="Test Subject",
            content="Test Content",
            template_data={}
        )
        
        # Mock SMTP发送失败
        with patch.object(sender, '_send_email', new_callable=AsyncMock) as mock_send:
            mock_send.side_effect = Exception("SMTP Error")
            
            result = await sender.send(notification)
            
            assert result is False
            assert notification.error_message == "SMTP Error"
    
    @pytest.mark.asyncio
    async def test_send_email_sync(self):
        """测试同步邮件发送"""
        notification_config = NotificationConfig()
        email_config = EmailConfig(
            smtp_server="smtp.example.com",
            smtp_port=587,
            username="test@example.com",
            password="password123",
            use_tls=True
        )
        sender = EmailSender(notification_config, email_config)
        
        # 创建模拟消息
        message = MIMEMultipart()
        message["Subject"] = "Test"
        message["From"] = "test@example.com"
        message["To"] = "user@example.com"
        
        # Mock SMTP服务器
        mock_server = MagicMock()
        
        with patch('smtplib.SMTP') as mock_smtp:
            mock_smtp.return_value = mock_server
            
            sender._send_email_sync(message, "user@example.com")
            
            # 验证SMTP调用
            mock_smtp.assert_called_once_with("smtp.example.com", 587, timeout=30)
            mock_server.starttls.assert_called_once()
            mock_server.login.assert_called_once_with("test@example.com", "password123")
            mock_server.send_message.assert_called_once_with(message, to_addrs=["user@example.com"])
            mock_server.quit.assert_called_once()
    
    @pytest.mark.asyncio
    async def test_send_email_sync_ssl(self):
        """测试SSL邮件发送"""
        notification_config = NotificationConfig()
        email_config = EmailConfig(
            smtp_server="smtp.example.com",
            smtp_port=465,
            username="test@example.com",
            password="password123",
            use_ssl=True,
            use_tls=False
        )
        sender = EmailSender(notification_config, email_config)
        
        message = MIMEMultipart()
        mock_server = MagicMock()
        
        with patch('smtplib.SMTP_SSL') as mock_smtp_ssl:
            mock_smtp_ssl.return_value = mock_server
            
            sender._send_email_sync(message, "user@example.com")
            
            # 验证SSL SMTP调用
            mock_smtp_ssl.assert_called_once()
            mock_server.login.assert_called_once_with("test@example.com", "password123")
            mock_server.send_message.assert_called_once()
            mock_server.quit.assert_called_once()
    
    @pytest.mark.asyncio
    async def test_batch_send(self):
        """测试批量发送"""
        notification_config = NotificationConfig()
        email_config = EmailConfig(
            smtp_server="smtp.example.com",
            username="test@example.com",
            password="password123"
        )
        sender = EmailSender(notification_config, email_config)
        
        notifications = [
            NotificationData(
                id="test-1",
                type=NotificationType.TASK_STATUS_CHANGE,
                channel=NotificationChannel.EMAIL,
                recipient="user1@example.com",
                subject="Test 1",
                content="Content 1",
                template_data={}
            ),
            NotificationData(
                id="test-2",
                type=NotificationType.TASK_STATUS_CHANGE,
                channel=NotificationChannel.EMAIL,
                recipient="user2@example.com",
                subject="Test 2",
                content="Content 2",
                template_data={}
            )
        ]
        
        # Mock SMTP连接方法
        mock_server = MagicMock()
        with patch.object(sender, '_create_smtp_connection', new_callable=AsyncMock) as mock_create:
            with patch.object(sender, '_send_with_connection', new_callable=AsyncMock) as mock_send:
                with patch.object(sender, '_close_smtp_connection', new_callable=AsyncMock) as mock_close:
                    mock_create.return_value = mock_server
                    
                    results = await sender.send_batch(notifications)
                    
                    assert len(results) == 2
                    assert all(results)
                    assert mock_send.call_count == 2
                    mock_close.assert_called_once_with(mock_server)
    
    @pytest.mark.asyncio
    async def test_test_connection_success(self):
        """测试连接测试成功"""
        notification_config = NotificationConfig()
        email_config = EmailConfig(
            smtp_server="smtp.example.com",
            username="test@example.com",
            password="password123"
        )
        sender = EmailSender(notification_config, email_config)
        
        mock_server = MagicMock()
        with patch.object(sender, '_create_smtp_connection', new_callable=AsyncMock) as mock_create:
            with patch.object(sender, '_close_smtp_connection', new_callable=AsyncMock) as mock_close:
                mock_create.return_value = mock_server
                
                result = await sender.test_connection()
                
                assert result is True
                mock_create.assert_called_once()
                mock_close.assert_called_once_with(mock_server)
    
    @pytest.mark.asyncio
    async def test_test_connection_failure(self):
        """测试连接测试失败"""
        notification_config = NotificationConfig()
        email_config = EmailConfig(
            smtp_server="smtp.example.com",
            username="test@example.com",
            password="password123"
        )
        sender = EmailSender(notification_config, email_config)
        
        with patch.object(sender, '_create_smtp_connection', new_callable=AsyncMock) as mock_create:
            mock_create.side_effect = Exception("Connection failed")
            
            result = await sender.test_connection()
            
            assert result is False
    
    def test_get_config_info(self):
        """测试获取配置信息"""
        notification_config = NotificationConfig()
        email_config = EmailConfig(
            smtp_server="smtp.example.com",
            smtp_port=587,
            username="test@example.com",
            password="secret123",
            from_name="Test Platform"
        )
        sender = EmailSender(notification_config, email_config)
        
        config_info = sender.get_config_info()
        
        # 验证配置信息包含非敏感数据
        assert config_info["smtp_server"] == "smtp.example.com"
        assert config_info["smtp_port"] == 587
        assert config_info["username"] == "test@example.com"
        assert config_info["from_name"] == "Test Platform"
        
        # 验证不包含密码
        assert "password" not in config_info


class TestEmailTemplateRenderer:
    """测试邮件模板渲染器"""
    
    def test_render_task_status_change(self):
        """测试任务状态变更模板渲染"""
        template_data = {
            "task_name": "Test Task",
            "task_id": "123",
            "old_status": "running",
            "new_status": "completed",
            "change_time": "2023-01-01 12:00:00"
        }
        
        result = EmailTemplateRenderer.render_task_status_change(template_data)
        
        assert "subject" in result
        assert "content" in result
        assert "Test Task" in result["subject"]
        assert "Test Task" in result["content"]
        assert "123" in result["content"]
        assert "running" in result["content"]
        assert "completed" in result["content"]
    
    def test_render_task_status_change_with_error(self):
        """测试带错误信息的任务状态变更模板"""
        template_data = {
            "task_name": "Failed Task",
            "task_id": "456",
            "old_status": "running",
            "new_status": "failed",
            "change_time": "2023-01-01 12:00:00",
            "error_message": "Connection timeout"
        }
        
        result = EmailTemplateRenderer.render_task_status_change(template_data)
        
        assert "Connection timeout" in result["content"]
        assert "错误信息" in result["content"]
    
    def test_render_credit_low_balance(self):
        """测试余额不足模板渲染"""
        template_data = {
            "current_balance": "10.5",
            "threshold": "50",
            "recharge_url": "https://example.com/recharge"
        }
        
        result = EmailTemplateRenderer.render_credit_low_balance(template_data)
        
        assert "余额不足" in result["subject"]
        assert "10.5" in result["content"]
        assert "50" in result["content"]
        assert "https://example.com/recharge" in result["content"]
    
    def test_render_system_maintenance(self):
        """测试系统维护模板渲染"""
        template_data = {
            "maintenance_start": "2023-01-01 02:00:00",
            "maintenance_end": "2023-01-01 04:00:00",
            "maintenance_description": "数据库升级"
        }
        
        result = EmailTemplateRenderer.render_system_maintenance(template_data)
        
        assert "维护通知" in result["subject"]
        assert "2023-01-01 02:00:00" in result["content"]
        assert "2023-01-01 04:00:00" in result["content"]
        assert "数据库升级" in result["content"]
    
    def test_render_with_missing_data(self):
        """测试缺少数据的模板渲染"""
        # 空数据
        result = EmailTemplateRenderer.render_task_status_change({})
        
        assert "未知任务" in result["subject"]
        assert "未知" in result["content"]
        
        # 部分数据
        result = EmailTemplateRenderer.render_credit_low_balance({"current_balance": "5"})
        
        assert "5" in result["content"]
        assert "50" in result["content"]  # 默认阈值
        assert "#" in result["content"]  # 默认链接