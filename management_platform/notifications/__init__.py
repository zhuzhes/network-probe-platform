"""
通知系统模块

提供统一的通知发送和管理功能，支持多种通知类型和渠道。
"""

from .base import NotificationBase, NotificationTemplate, NotificationConfig
from .manager import NotificationManager
from .queue import NotificationQueue
from .types import NotificationType, NotificationStatus, NotificationChannel
from .email import EmailSender, EmailConfig, EmailTemplateRenderer
from .events import (
    EventType, Event, EventBus, NotificationEventHandler, EventNotificationService
)

__all__ = [
    'NotificationBase',
    'NotificationTemplate', 
    'NotificationConfig',
    'NotificationManager',
    'NotificationQueue',
    'NotificationType',
    'NotificationStatus',
    'NotificationChannel',
    'EmailSender',
    'EmailConfig',
    'EmailTemplateRenderer',
    'EventType',
    'Event',
    'EventBus',
    'NotificationEventHandler',
    'EventNotificationService'
]