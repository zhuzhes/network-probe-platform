"""
通知管理器 - 统一的通知发送和管理接口
"""

import asyncio
import logging
from typing import Dict, List, Optional, Any
from datetime import datetime
import uuid

from .base import NotificationBase, TemplateManager, NotificationConfig
from .queue import NotificationQueue
from .types import (
    NotificationData, NotificationChannel, NotificationStatus, 
    NotificationPriority, NotificationType
)


logger = logging.getLogger(__name__)


class NotificationManager:
    """通知管理器"""
    
    def __init__(self, config: NotificationConfig = None):
        self.config = config or NotificationConfig()
        self.template_manager = TemplateManager()
        self.queue = NotificationQueue()
        self.senders: Dict[NotificationChannel, NotificationBase] = {}
        self._worker_task: Optional[asyncio.Task] = None
        self._running = False
        self._rate_limiter = {}  # 简单的速率限制器
    
    def register_sender(self, channel: NotificationChannel, sender: NotificationBase):
        """
        注册通知发送器
        
        Args:
            channel: 通知渠道
            sender: 发送器实例
        """
        self.senders[channel] = sender
        logger.info(f"注册通知发送器: {channel.value}")
    
    def unregister_sender(self, channel: NotificationChannel):
        """
        注销通知发送器
        
        Args:
            channel: 通知渠道
        """
        if channel in self.senders:
            del self.senders[channel]
            logger.info(f"注销通知发送器: {channel.value}")
    
    async def send_notification(
        self,
        notification_type: NotificationType,
        channel: NotificationChannel,
        recipient: str,
        template_data: Dict[str, Any],
        priority: NotificationPriority = NotificationPriority.NORMAL,
        template_id: str = None
    ) -> str:
        """
        发送通知
        
        Args:
            notification_type: 通知类型
            channel: 通知渠道
            recipient: 接收者
            template_data: 模板数据
            priority: 优先级
            template_id: 自定义模板ID
            
        Returns:
            str: 通知ID
        """
        # 检查发送器是否已注册
        if channel not in self.senders:
            raise ValueError(f"未注册的通知渠道: {channel.value}")
        
        # 获取模板
        template_id = template_id or notification_type.value
        template = self.template_manager.get_template(template_id)
        if not template:
            raise ValueError(f"未找到模板: {template_id}")
        
        # 创建通知数据
        notification_id = str(uuid.uuid4())
        notification = NotificationData(
            id=notification_id,
            type=notification_type,
            channel=channel,
            recipient=recipient,
            subject=template.subject_template,
            content=template.content_template,
            template_data=template_data,
            priority=priority,
            created_at=datetime.utcnow()
        )
        
        # 加入队列
        success = await self.queue.enqueue(notification)
        if not success:
            raise RuntimeError("通知队列已满，无法发送通知")
        
        logger.info(f"通知已加入队列: {notification_id}, 类型: {notification_type.value}")
        return notification_id
    
    async def send_batch_notifications(
        self,
        notifications: List[Dict[str, Any]]
    ) -> List[str]:
        """
        批量发送通知
        
        Args:
            notifications: 通知列表，每个元素包含send_notification的参数
            
        Returns:
            List[str]: 通知ID列表
        """
        notification_ids = []
        
        for notification_data in notifications:
            try:
                notification_id = await self.send_notification(**notification_data)
                notification_ids.append(notification_id)
            except Exception as e:
                logger.error(f"批量发送通知失败: {e}")
                notification_ids.append(None)
        
        return notification_ids
    
    async def start_worker(self):
        """启动通知处理工作线程"""
        if self._running:
            logger.warning("通知处理器已在运行")
            return
        
        self._running = True
        self._worker_task = asyncio.create_task(self._process_notifications())
        logger.info("通知处理器已启动")
    
    async def stop_worker(self):
        """停止通知处理工作线程"""
        if not self._running:
            return
        
        self._running = False
        if self._worker_task:
            self._worker_task.cancel()
            try:
                await self._worker_task
            except asyncio.CancelledError:
                pass
        
        logger.info("通知处理器已停止")
    
    async def _process_notifications(self):
        """处理通知的主循环"""
        logger.info("开始处理通知队列")
        
        while self._running:
            try:
                # 从队列获取通知
                notification = await self.queue.dequeue()
                if not notification:
                    # 队列为空，等待一段时间
                    await asyncio.sleep(1)
                    continue
                
                # 检查速率限制
                if not await self._check_rate_limit(notification.channel):
                    # 重新加入队列
                    await self.queue.requeue(notification)
                    await asyncio.sleep(1)
                    continue
                
                # 发送通知
                await self._send_single_notification(notification)
                
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"处理通知时发生错误: {e}")
                await asyncio.sleep(1)
    
    async def _send_single_notification(self, notification: NotificationData):
        """
        发送单个通知
        
        Args:
            notification: 通知数据
        """
        sender = self.senders.get(notification.channel)
        if not sender:
            await self.queue.mark_completed(
                notification.id, 
                False, 
                f"未找到发送器: {notification.channel.value}"
            )
            return
        
        try:
            # 验证接收者格式
            if not sender.validate_recipient(notification.recipient):
                await self.queue.mark_completed(
                    notification.id,
                    False,
                    f"无效的接收者格式: {notification.recipient}"
                )
                return
            
            # 准备通知数据（渲染模板）
            prepared_notification = sender.prepare_notification(notification)
            
            # 发送通知
            success = await sender.send_with_retry(prepared_notification)
            
            # 标记完成
            await self.queue.mark_completed(
                notification.id,
                success,
                prepared_notification.error_message if not success else None
            )
            
        except Exception as e:
            logger.error(f"发送通知失败: {notification.id}, 错误: {e}")
            await self.queue.mark_completed(notification.id, False, str(e))
    
    async def _check_rate_limit(self, channel: NotificationChannel) -> bool:
        """
        检查速率限制
        
        Args:
            channel: 通知渠道
            
        Returns:
            bool: 是否允许发送
        """
        # 简单的速率限制实现
        now = datetime.utcnow()
        minute_key = now.strftime("%Y%m%d%H%M")
        
        if channel not in self._rate_limiter:
            self._rate_limiter[channel] = {}
        
        channel_limiter = self._rate_limiter[channel]
        
        # 清理旧的计数
        keys_to_remove = [k for k in channel_limiter.keys() if k < minute_key]
        for key in keys_to_remove:
            del channel_limiter[key]
        
        # 检查当前分钟的发送量
        current_count = channel_limiter.get(minute_key, 0)
        if current_count >= self.config.rate_limit:
            return False
        
        # 增加计数
        channel_limiter[minute_key] = current_count + 1
        return True
    
    async def get_notification_status(self, notification_id: str) -> Optional[Dict[str, Any]]:
        """
        获取通知状态
        
        Args:
            notification_id: 通知ID
            
        Returns:
            Optional[Dict[str, Any]]: 通知状态信息
        """
        # 检查处理中的通知
        async with self.queue._lock:
            if notification_id in self.queue.processing:
                notification = self.queue.processing[notification_id]
                return {
                    'id': notification.id,
                    'status': notification.status.value,
                    'created_at': notification.created_at,
                    'sent_at': notification.sent_at,
                    'error_message': notification.error_message,
                    'retry_count': notification.retry_count
                }
        
        # 检查失败的通知
        for notification in self.queue.failed:
            if notification.id == notification_id:
                return {
                    'id': notification.id,
                    'status': notification.status.value,
                    'created_at': notification.created_at,
                    'sent_at': notification.sent_at,
                    'error_message': notification.error_message,
                    'retry_count': notification.retry_count
                }
        
        return None
    
    async def get_statistics(self) -> Dict[str, Any]:
        """
        获取通知系统统计信息
        
        Returns:
            Dict[str, Any]: 统计信息
        """
        queue_stats = await self.queue.get_stats()
        
        return {
            'queue_stats': queue_stats,
            'registered_senders': list(self.senders.keys()),
            'worker_running': self._running,
            'config': {
                'enabled': self.config.enabled,
                'max_retries': self.config.max_retries,
                'rate_limit': self.config.rate_limit,
                'batch_size': self.config.batch_size
            }
        }
    
    async def retry_failed_notifications(self, notification_ids: List[str] = None) -> int:
        """
        重试失败的通知
        
        Args:
            notification_ids: 要重试的通知ID列表，如果为None则重试所有失败的通知
            
        Returns:
            int: 重试的通知数量
        """
        failed_notifications = await self.queue.get_failed_notifications()
        retry_count = 0
        
        for notification in failed_notifications:
            if notification_ids is None or notification.id in notification_ids:
                # 重置状态并重新加入队列
                notification.status = NotificationStatus.PENDING
                notification.error_message = None
                notification.retry_count = 0
                
                success = await self.queue.enqueue(notification)
                if success:
                    retry_count += 1
        
        logger.info(f"重试了 {retry_count} 个失败的通知")
        return retry_count