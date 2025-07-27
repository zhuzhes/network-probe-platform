"""
通知系统基础类和接口定义
"""

from abc import ABC, abstractmethod
from typing import Dict, Any, Optional, List
from dataclasses import dataclass
from datetime import datetime
import json
import logging
from jinja2 import Template, Environment, BaseLoader

from .types import NotificationData, NotificationChannel, NotificationStatus


logger = logging.getLogger(__name__)


@dataclass
class NotificationTemplate:
    """通知模板"""
    id: str
    name: str
    channel: NotificationChannel
    subject_template: str
    content_template: str
    variables: List[str]
    created_at: datetime
    updated_at: datetime


@dataclass
class NotificationConfig:
    """通知配置"""
    enabled: bool = True
    max_retries: int = 3
    retry_delay: int = 60  # 秒
    batch_size: int = 10
    rate_limit: int = 100  # 每分钟最大发送数量
    templates: Dict[str, NotificationTemplate] = None
    
    def __post_init__(self):
        if self.templates is None:
            self.templates = {}


class NotificationBase(ABC):
    """通知发送器基类"""
    
    def __init__(self, config: NotificationConfig):
        self.config = config
        self.env = Environment(loader=BaseLoader())
    
    @abstractmethod
    async def send(self, notification: NotificationData) -> bool:
        """
        发送通知
        
        Args:
            notification: 通知数据
            
        Returns:
            bool: 发送是否成功
        """
        pass
    
    @abstractmethod
    def validate_recipient(self, recipient: str) -> bool:
        """
        验证接收者格式
        
        Args:
            recipient: 接收者
            
        Returns:
            bool: 格式是否有效
        """
        pass
    
    def render_template(self, template_str: str, data: Dict[str, Any]) -> str:
        """
        渲染模板
        
        Args:
            template_str: 模板字符串
            data: 模板数据
            
        Returns:
            str: 渲染后的内容
        """
        try:
            # 使用undefined='strict'来处理未定义变量
            env = Environment(loader=BaseLoader(), undefined='strict')
            template = env.from_string(template_str)
            return template.render(**data)
        except Exception as e:
            logger.error(f"模板渲染失败: {e}")
            # 如果渲染失败，尝试使用默认的undefined处理
            try:
                template = self.env.from_string(template_str)
                return template.render(**data)
            except Exception:
                return template_str
    
    def prepare_notification(self, notification: NotificationData) -> NotificationData:
        """
        准备通知数据，渲染模板
        
        Args:
            notification: 原始通知数据
            
        Returns:
            NotificationData: 处理后的通知数据
        """
        # 渲染主题和内容模板
        if notification.template_data:
            notification.subject = self.render_template(
                notification.subject, 
                notification.template_data
            )
            notification.content = self.render_template(
                notification.content, 
                notification.template_data
            )
        
        return notification
    
    async def send_with_retry(self, notification: NotificationData) -> bool:
        """
        带重试的发送通知
        
        Args:
            notification: 通知数据
            
        Returns:
            bool: 最终发送是否成功
        """
        max_retries = min(notification.max_retries, self.config.max_retries)
        
        for attempt in range(max_retries + 1):
            try:
                notification.retry_count = attempt
                success = await self.send(notification)
                
                if success:
                    notification.status = NotificationStatus.SENT
                    notification.sent_at = datetime.utcnow()
                    return True
                    
            except Exception as e:
                logger.error(f"通知发送失败 (尝试 {attempt + 1}/{max_retries + 1}): {e}")
                notification.error_message = str(e)
                
                if attempt < max_retries:
                    # 等待重试
                    import asyncio
                    await asyncio.sleep(self.config.retry_delay * (attempt + 1))
        
        notification.status = NotificationStatus.FAILED
        return False


class TemplateManager:
    """模板管理器"""
    
    def __init__(self):
        self.templates: Dict[str, NotificationTemplate] = {}
        self._load_default_templates()
    
    def _load_default_templates(self):
        """加载默认模板"""
        default_templates = [
            NotificationTemplate(
                id="task_status_change",
                name="任务状态变更通知",
                channel=NotificationChannel.EMAIL,
                subject_template="任务状态变更通知 - {{task_name}}",
                content_template="""
                尊敬的用户，
                
                您的拨测任务状态已发生变更：
                
                任务名称: {{task_name}}
                任务ID: {{task_id}}
                原状态: {{old_status}}
                新状态: {{new_status}}
                变更时间: {{change_time}}
                
                {% if error_message %}
                错误信息: {{error_message}}
                {% endif %}
                
                请登录系统查看详细信息。
                
                此致
                网络拨测平台
                """,
                variables=["task_name", "task_id", "old_status", "new_status", "change_time", "error_message"],
                created_at=datetime.utcnow(),
                updated_at=datetime.utcnow()
            ),
            NotificationTemplate(
                id="credit_low_balance",
                name="余额不足提醒",
                channel=NotificationChannel.EMAIL,
                subject_template="账户余额不足提醒",
                content_template="""
                尊敬的用户，
                
                您的账户余额已不足：
                
                当前余额: {{current_balance}} 点数
                阈值: {{threshold}} 点数
                
                为避免影响您的拨测任务正常执行，请及时充值。
                
                充值链接: {{recharge_url}}
                
                此致
                网络拨测平台
                """,
                variables=["current_balance", "threshold", "recharge_url"],
                created_at=datetime.utcnow(),
                updated_at=datetime.utcnow()
            ),
            NotificationTemplate(
                id="system_maintenance",
                name="系统维护通知",
                channel=NotificationChannel.EMAIL,
                subject_template="系统维护通知",
                content_template="""
                尊敬的用户，
                
                系统将进行维护：
                
                维护时间: {{maintenance_start}} 至 {{maintenance_end}}
                维护内容: {{maintenance_description}}
                
                维护期间系统可能无法正常使用，请您提前做好安排。
                
                感谢您的理解与支持。
                
                此致
                网络拨测平台
                """,
                variables=["maintenance_start", "maintenance_end", "maintenance_description"],
                created_at=datetime.utcnow(),
                updated_at=datetime.utcnow()
            )
        ]
        
        for template in default_templates:
            self.templates[template.id] = template
    
    def get_template(self, template_id: str) -> Optional[NotificationTemplate]:
        """获取模板"""
        return self.templates.get(template_id)
    
    def add_template(self, template: NotificationTemplate):
        """添加模板"""
        self.templates[template.id] = template
    
    def update_template(self, template_id: str, template: NotificationTemplate):
        """更新模板"""
        if template_id in self.templates:
            template.updated_at = datetime.utcnow()
            self.templates[template_id] = template
    
    def delete_template(self, template_id: str):
        """删除模板"""
        if template_id in self.templates:
            del self.templates[template_id]
    
    def list_templates(self) -> List[NotificationTemplate]:
        """列出所有模板"""
        return list(self.templates.values())