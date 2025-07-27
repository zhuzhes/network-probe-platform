"""
通知系统类型定义
"""

from enum import Enum
from typing import Dict, Any, Optional
from dataclasses import dataclass
from datetime import datetime


class NotificationType(Enum):
    """通知类型枚举"""
    TASK_STATUS_CHANGE = "task_status_change"
    AGENT_STATUS_CHANGE = "agent_status_change"
    CREDIT_LOW_BALANCE = "credit_low_balance"
    SYSTEM_MAINTENANCE = "system_maintenance"
    TASK_FAILED = "task_failed"
    TASK_COMPLETED = "task_completed"
    AGENT_OFFLINE = "agent_offline"
    AGENT_ONLINE = "agent_online"


class NotificationChannel(Enum):
    """通知渠道枚举"""
    EMAIL = "email"
    SMS = "sms"
    WEBHOOK = "webhook"
    IN_APP = "in_app"


class NotificationStatus(Enum):
    """通知状态枚举"""
    PENDING = "pending"
    PROCESSING = "processing"
    SENT = "sent"
    FAILED = "failed"
    CANCELLED = "cancelled"


class NotificationPriority(Enum):
    """通知优先级枚举"""
    LOW = 1
    NORMAL = 2
    HIGH = 3
    URGENT = 4


@dataclass
class NotificationData:
    """通知数据结构"""
    id: str
    type: NotificationType
    channel: NotificationChannel
    recipient: str
    subject: str
    content: str
    template_data: Dict[str, Any]
    priority: NotificationPriority = NotificationPriority.NORMAL
    status: NotificationStatus = NotificationStatus.PENDING
    created_at: Optional[datetime] = None
    sent_at: Optional[datetime] = None
    error_message: Optional[str] = None
    retry_count: int = 0
    max_retries: int = 3