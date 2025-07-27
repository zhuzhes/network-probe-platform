"""
邮件通知发送器
"""

import smtplib
import ssl
import logging
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from email.mime.base import MIMEBase
from email import encoders
from typing import Dict, Any, Optional, List
import re
import asyncio
from dataclasses import dataclass

from .base import NotificationBase, NotificationConfig
from .types import NotificationData, NotificationStatus


logger = logging.getLogger(__name__)


@dataclass
class EmailConfig:
    """邮件配置"""
    smtp_server: str
    smtp_port: int = 587
    username: str = ""
    password: str = ""
    use_tls: bool = True
    use_ssl: bool = False
    from_email: str = ""
    from_name: str = "网络拨测平台"
    timeout: int = 30
    
    def __post_init__(self):
        if not self.from_email and self.username:
            self.from_email = self.username


class EmailSender(NotificationBase):
    """邮件发送器"""
    
    def __init__(self, config: NotificationConfig, email_config: EmailConfig):
        super().__init__(config)
        self.email_config = email_config
        self._validate_config()
    
    def _validate_config(self):
        """验证邮件配置"""
        if not self.email_config.smtp_server:
            raise ValueError("SMTP服务器地址不能为空")
        
        if not self.email_config.username:
            raise ValueError("SMTP用户名不能为空")
        
        if not self.email_config.password:
            raise ValueError("SMTP密码不能为空")
        
        if not self.email_config.from_email:
            raise ValueError("发件人邮箱不能为空")
    
    def validate_recipient(self, recipient: str) -> bool:
        """
        验证邮箱地址格式
        
        Args:
            recipient: 邮箱地址
            
        Returns:
            bool: 格式是否有效
        """
        email_pattern = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'
        return bool(re.match(email_pattern, recipient))
    
    async def send(self, notification: NotificationData) -> bool:
        """
        发送邮件通知
        
        Args:
            notification: 通知数据
            
        Returns:
            bool: 发送是否成功
        """
        try:
            # 创建邮件消息
            message = self._create_message(notification)
            
            # 发送邮件
            await self._send_email(message, notification.recipient)
            
            logger.info(f"邮件发送成功: {notification.id} -> {notification.recipient}")
            return True
            
        except Exception as e:
            logger.error(f"邮件发送失败: {notification.id}, 错误: {e}")
            notification.error_message = str(e)
            return False
    
    def _create_message(self, notification: NotificationData) -> MIMEMultipart:
        """
        创建邮件消息
        
        Args:
            notification: 通知数据
            
        Returns:
            MIMEMultipart: 邮件消息对象
        """
        message = MIMEMultipart("alternative")
        
        # 设置邮件头
        message["Subject"] = notification.subject
        message["From"] = f"{self.email_config.from_name} <{self.email_config.from_email}>"
        message["To"] = notification.recipient
        
        # 创建文本内容
        text_part = MIMEText(notification.content, "plain", "utf-8")
        message.attach(text_part)
        
        # 如果内容包含HTML标签，也创建HTML版本
        if self._contains_html(notification.content):
            html_content = self._text_to_html(notification.content)
            html_part = MIMEText(html_content, "html", "utf-8")
            message.attach(html_part)
        
        return message
    
    def _contains_html(self, content: str) -> bool:
        """检查内容是否包含HTML标签"""
        html_tags = ['<br>', '<p>', '<div>', '<span>', '<strong>', '<em>', '<ul>', '<li>']
        return any(tag in content.lower() for tag in html_tags)
    
    def _text_to_html(self, text: str) -> str:
        """将文本转换为HTML格式"""
        # 简单的文本到HTML转换
        html = text.replace('\n', '<br>\n')
        html = f"<html><body><pre style='font-family: Arial, sans-serif;'>{html}</pre></body></html>"
        return html
    
    async def _send_email(self, message: MIMEMultipart, recipient: str):
        """
        发送邮件
        
        Args:
            message: 邮件消息
            recipient: 收件人
        """
        # 在线程池中执行同步的SMTP操作
        loop = asyncio.get_event_loop()
        await loop.run_in_executor(None, self._send_email_sync, message, recipient)
    
    def _send_email_sync(self, message: MIMEMultipart, recipient: str):
        """
        同步发送邮件
        
        Args:
            message: 邮件消息
            recipient: 收件人
        """
        server = None
        try:
            # 创建SMTP连接
            if self.email_config.use_ssl:
                context = ssl.create_default_context()
                server = smtplib.SMTP_SSL(
                    self.email_config.smtp_server,
                    self.email_config.smtp_port,
                    timeout=self.email_config.timeout,
                    context=context
                )
            else:
                server = smtplib.SMTP(
                    self.email_config.smtp_server,
                    self.email_config.smtp_port,
                    timeout=self.email_config.timeout
                )
                
                if self.email_config.use_tls:
                    context = ssl.create_default_context()
                    server.starttls(context=context)
            
            # 登录
            server.login(self.email_config.username, self.email_config.password)
            
            # 发送邮件
            server.send_message(message, to_addrs=[recipient])
            
        finally:
            if server:
                server.quit()
    
    async def send_batch(self, notifications: List[NotificationData]) -> List[bool]:
        """
        批量发送邮件
        
        Args:
            notifications: 通知列表
            
        Returns:
            List[bool]: 发送结果列表
        """
        results = []
        
        # 使用连接池优化批量发送
        server = None
        try:
            # 建立连接
            server = await self._create_smtp_connection()
            
            for notification in notifications:
                try:
                    message = self._create_message(notification)
                    await self._send_with_connection(server, message, notification.recipient)
                    results.append(True)
                    logger.info(f"批量邮件发送成功: {notification.id} -> {notification.recipient}")
                    
                except Exception as e:
                    logger.error(f"批量邮件发送失败: {notification.id}, 错误: {e}")
                    notification.error_message = str(e)
                    results.append(False)
                    
        finally:
            if server:
                await self._close_smtp_connection(server)
        
        return results
    
    async def _create_smtp_connection(self):
        """创建SMTP连接"""
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(None, self._create_smtp_connection_sync)
    
    def _create_smtp_connection_sync(self):
        """同步创建SMTP连接"""
        if self.email_config.use_ssl:
            context = ssl.create_default_context()
            server = smtplib.SMTP_SSL(
                self.email_config.smtp_server,
                self.email_config.smtp_port,
                timeout=self.email_config.timeout,
                context=context
            )
        else:
            server = smtplib.SMTP(
                self.email_config.smtp_server,
                self.email_config.smtp_port,
                timeout=self.email_config.timeout
            )
            
            if self.email_config.use_tls:
                context = ssl.create_default_context()
                server.starttls(context=context)
        
        server.login(self.email_config.username, self.email_config.password)
        return server
    
    async def _send_with_connection(self, server, message: MIMEMultipart, recipient: str):
        """使用现有连接发送邮件"""
        loop = asyncio.get_event_loop()
        await loop.run_in_executor(
            None, 
            lambda: server.send_message(message, to_addrs=[recipient])
        )
    
    async def _close_smtp_connection(self, server):
        """关闭SMTP连接"""
        loop = asyncio.get_event_loop()
        await loop.run_in_executor(None, server.quit)
    
    async def test_connection(self) -> bool:
        """
        测试邮件服务器连接
        
        Returns:
            bool: 连接是否成功
        """
        try:
            server = await self._create_smtp_connection()
            await self._close_smtp_connection(server)
            logger.info("邮件服务器连接测试成功")
            return True
            
        except Exception as e:
            logger.error(f"邮件服务器连接测试失败: {e}")
            return False
    
    def get_config_info(self) -> Dict[str, Any]:
        """
        获取配置信息（隐藏敏感信息）
        
        Returns:
            Dict[str, Any]: 配置信息
        """
        return {
            "smtp_server": self.email_config.smtp_server,
            "smtp_port": self.email_config.smtp_port,
            "username": self.email_config.username,
            "from_email": self.email_config.from_email,
            "from_name": self.email_config.from_name,
            "use_tls": self.email_config.use_tls,
            "use_ssl": self.email_config.use_ssl,
            "timeout": self.email_config.timeout
        }


class EmailTemplateRenderer:
    """邮件模板渲染器"""
    
    @staticmethod
    def render_task_status_change(template_data: Dict[str, Any]) -> Dict[str, str]:
        """渲染任务状态变更邮件"""
        subject = f"任务状态变更通知 - {template_data.get('task_name', '未知任务')}"
        
        content = f"""
尊敬的用户，

您的拨测任务状态已发生变更：

任务名称: {template_data.get('task_name', '未知')}
任务ID: {template_data.get('task_id', '未知')}
原状态: {template_data.get('old_status', '未知')}
新状态: {template_data.get('new_status', '未知')}
变更时间: {template_data.get('change_time', '未知')}
"""
        
        if template_data.get('error_message'):
            content += f"\n错误信息: {template_data['error_message']}\n"
        
        content += """
请登录系统查看详细信息。

此致
网络拨测平台
"""
        
        return {"subject": subject, "content": content}
    
    @staticmethod
    def render_credit_low_balance(template_data: Dict[str, Any]) -> Dict[str, str]:
        """渲染余额不足邮件"""
        subject = "账户余额不足提醒"
        
        content = f"""
尊敬的用户，

您的账户余额已不足：

当前余额: {template_data.get('current_balance', '0')} 点数
阈值: {template_data.get('threshold', '50')} 点数

为避免影响您的拨测任务正常执行，请及时充值。

充值链接: {template_data.get('recharge_url', '#')}

此致
网络拨测平台
"""
        
        return {"subject": subject, "content": content}
    
    @staticmethod
    def render_system_maintenance(template_data: Dict[str, Any]) -> Dict[str, str]:
        """渲染系统维护邮件"""
        subject = "系统维护通知"
        
        content = f"""
尊敬的用户，

系统将进行维护：

维护时间: {template_data.get('maintenance_start', '未知')} 至 {template_data.get('maintenance_end', '未知')}
维护内容: {template_data.get('maintenance_description', '系统维护')}

维护期间系统可能无法正常使用，请您提前做好安排。

感谢您的理解与支持。

此致
网络拨测平台
"""
        
        return {"subject": subject, "content": content}