"""
通知队列管理
"""

import asyncio
import logging
from typing import List, Optional, Dict, Any
from datetime import datetime, timedelta
from collections import deque
import json

from .types import NotificationData, NotificationStatus, NotificationPriority


logger = logging.getLogger(__name__)


class NotificationQueue:
    """通知队列"""
    
    def __init__(self, max_size: int = 10000):
        self.max_size = max_size
        self.queues: Dict[NotificationPriority, deque] = {
            priority: deque() for priority in NotificationPriority
        }
        self.processing: Dict[str, NotificationData] = {}
        self.failed: deque = deque(maxlen=1000)  # 保留最近1000个失败记录
        self._lock = asyncio.Lock()
        self._stats = {
            'total_enqueued': 0,
            'total_processed': 0,
            'total_failed': 0,
            'current_size': 0
        }
    
    async def enqueue(self, notification: NotificationData) -> bool:
        """
        将通知加入队列
        
        Args:
            notification: 通知数据
            
        Returns:
            bool: 是否成功加入队列
        """
        async with self._lock:
            current_size = sum(len(queue) for queue in self.queues.values())
            
            if current_size >= self.max_size:
                logger.warning(f"通知队列已满，丢弃通知: {notification.id}")
                return False
            
            # 设置创建时间
            if notification.created_at is None:
                notification.created_at = datetime.utcnow()
            
            # 根据优先级加入对应队列
            self.queues[notification.priority].append(notification)
            self._stats['total_enqueued'] += 1
            self._stats['current_size'] = current_size + 1
            
            logger.debug(f"通知已加入队列: {notification.id}, 优先级: {notification.priority}")
            return True
    
    async def dequeue(self) -> Optional[NotificationData]:
        """
        从队列中取出通知（按优先级）
        
        Returns:
            Optional[NotificationData]: 通知数据，如果队列为空则返回None
        """
        async with self._lock:
            # 按优先级顺序检查队列
            for priority in sorted(NotificationPriority, key=lambda x: x.value, reverse=True):
                queue = self.queues[priority]
                if queue:
                    notification = queue.popleft()
                    notification.status = NotificationStatus.PROCESSING
                    self.processing[notification.id] = notification
                    self._stats['current_size'] -= 1
                    
                    logger.debug(f"从队列取出通知: {notification.id}, 优先级: {priority}")
                    return notification
            
            return None
    
    async def mark_completed(self, notification_id: str, success: bool, error_message: str = None):
        """
        标记通知处理完成
        
        Args:
            notification_id: 通知ID
            success: 是否成功
            error_message: 错误消息（如果失败）
        """
        async with self._lock:
            if notification_id in self.processing:
                notification = self.processing.pop(notification_id)
                
                if success:
                    notification.status = NotificationStatus.SENT
                    notification.sent_at = datetime.utcnow()
                    self._stats['total_processed'] += 1
                    logger.debug(f"通知发送成功: {notification_id}")
                else:
                    notification.status = NotificationStatus.FAILED
                    notification.error_message = error_message
                    self.failed.append(notification)
                    self._stats['total_failed'] += 1
                    logger.warning(f"通知发送失败: {notification_id}, 错误: {error_message}")
    
    async def requeue(self, notification: NotificationData) -> bool:
        """
        重新加入队列（用于重试）
        
        Args:
            notification: 通知数据
            
        Returns:
            bool: 是否成功重新加入队列
        """
        # 从处理中移除
        async with self._lock:
            if notification.id in self.processing:
                del self.processing[notification.id]
        
        # 重新加入队列
        notification.status = NotificationStatus.PENDING
        return await self.enqueue(notification)
    
    async def get_stats(self) -> Dict[str, Any]:
        """
        获取队列统计信息
        
        Returns:
            Dict[str, Any]: 统计信息
        """
        async with self._lock:
            queue_sizes = {
                priority.name: len(queue) 
                for priority, queue in self.queues.items()
            }
            
            return {
                **self._stats,
                'processing_count': len(self.processing),
                'failed_count': len(self.failed),
                'queue_sizes': queue_sizes
            }
    
    async def get_pending_notifications(self, limit: int = 100) -> List[NotificationData]:
        """
        获取待处理通知列表
        
        Args:
            limit: 最大返回数量
            
        Returns:
            List[NotificationData]: 待处理通知列表
        """
        async with self._lock:
            notifications = []
            count = 0
            
            # 按优先级顺序收集通知
            for priority in sorted(NotificationPriority, key=lambda x: x.value, reverse=True):
                queue = self.queues[priority]
                for notification in queue:
                    if count >= limit:
                        break
                    notifications.append(notification)
                    count += 1
                
                if count >= limit:
                    break
            
            return notifications
    
    async def get_failed_notifications(self, limit: int = 100) -> List[NotificationData]:
        """
        获取失败通知列表
        
        Args:
            limit: 最大返回数量
            
        Returns:
            List[NotificationData]: 失败通知列表
        """
        async with self._lock:
            return list(self.failed)[-limit:]
    
    async def clear_old_failed(self, older_than_hours: int = 24):
        """
        清理旧的失败记录
        
        Args:
            older_than_hours: 清理多少小时前的记录
        """
        cutoff_time = datetime.utcnow() - timedelta(hours=older_than_hours)
        
        async with self._lock:
            # 过滤掉旧的失败记录
            self.failed = deque(
                [n for n in self.failed if n.created_at and n.created_at > cutoff_time],
                maxlen=self.failed.maxlen
            )
    
    async def clear_all(self):
        """清空所有队列"""
        async with self._lock:
            for queue in self.queues.values():
                queue.clear()
            self.processing.clear()
            self.failed.clear()
            self._stats = {
                'total_enqueued': 0,
                'total_processed': 0,
                'total_failed': 0,
                'current_size': 0
            }