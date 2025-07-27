"""代理连接管理模块"""

import asyncio
import json
import uuid
from typing import Dict, Any, Optional, Set, List, Callable, Awaitable
from datetime import datetime, timedelta
from dataclasses import dataclass, field
from enum import Enum
from fastapi import WebSocket
import logging

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', '..'))

from shared.models.agent import Agent, AgentStatus
from management_platform.database.repositories import AgentRepository
from management_platform.database.connection import get_db_session


logger = logging.getLogger(__name__)


class ConnectionState(Enum):
    """连接状态枚举"""
    CONNECTING = "connecting"
    CONNECTED = "connected"
    AUTHENTICATED = "authenticated"
    DISCONNECTING = "disconnecting"
    DISCONNECTED = "disconnected"
    ERROR = "error"


@dataclass
class ConnectionInfo:
    """连接信息"""
    agent_id: str
    websocket: WebSocket
    state: ConnectionState
    session_id: str
    authenticated_at: Optional[datetime] = None
    connected_at: datetime = field(default_factory=datetime.now)
    last_heartbeat: Optional[datetime] = None
    last_heartbeat_sent: Optional[datetime] = None
    missed_heartbeats: int = 0
    message_count_sent: int = 0
    message_count_received: int = 0
    bytes_sent: int = 0
    bytes_received: int = 0
    agent_info: Optional[Dict[str, Any]] = None
    capabilities: List[str] = field(default_factory=list)
    version: str = "unknown"
    load_metrics: Dict[str, float] = field(default_factory=dict)
    
    def to_dict(self) -> Dict[str, Any]:
        """转换为字典"""
        return {
            "agent_id": self.agent_id,
            "state": self.state.value,
            "session_id": self.session_id,
            "authenticated_at": self.authenticated_at.isoformat() if self.authenticated_at else None,
            "connected_at": self.connected_at.isoformat(),
            "last_heartbeat": self.last_heartbeat.isoformat() if self.last_heartbeat else None,
            "last_heartbeat_sent": self.last_heartbeat_sent.isoformat() if self.last_heartbeat_sent else None,
            "missed_heartbeats": self.missed_heartbeats,
            "message_count_sent": self.message_count_sent,
            "message_count_received": self.message_count_received,
            "bytes_sent": self.bytes_sent,
            "bytes_received": self.bytes_received,
            "capabilities": self.capabilities,
            "version": self.version,
            "load_metrics": self.load_metrics,
            "connection_duration": (datetime.now() - self.connected_at).total_seconds()
        }


class ConnectionPool:
    """连接池管理器"""
    
    def __init__(self, max_connections_per_agent: int = 1):
        """
        初始化连接池
        
        Args:
            max_connections_per_agent: 每个代理的最大连接数
        """
        self.max_connections_per_agent = max_connections_per_agent
        
        # 连接池：agent_id -> List[ConnectionInfo]
        self.connections: Dict[str, List[ConnectionInfo]] = {}
        
        # 活跃连接索引：session_id -> ConnectionInfo
        self.active_connections: Dict[str, ConnectionInfo] = {}
        
        # 连接统计
        self.stats = {
            "total_connections": 0,
            "active_connections": 0,
            "peak_connections": 0,
            "connection_attempts": 0,
            "failed_connections": 0,
            "disconnections": 0,
            "heartbeat_timeouts": 0,
            "authentication_failures": 0
        }
        
        # 连接历史（最近1000条）
        self.connection_history: List[Dict[str, Any]] = []
        self.max_history_size = 1000
    
    def add_connection(self, connection_info: ConnectionInfo) -> bool:
        """
        添加连接到池中
        
        Args:
            connection_info: 连接信息
            
        Returns:
            是否成功添加
        """
        agent_id = connection_info.agent_id
        
        # 检查连接数限制
        if agent_id in self.connections:
            if len(self.connections[agent_id]) >= self.max_connections_per_agent:
                logger.warning(f"代理 {agent_id} 连接数已达上限 {self.max_connections_per_agent}")
                return False
        else:
            self.connections[agent_id] = []
        
        # 添加连接
        self.connections[agent_id].append(connection_info)
        self.active_connections[connection_info.session_id] = connection_info
        
        # 更新统计
        self.stats["total_connections"] += 1
        self.stats["active_connections"] = len(self.active_connections)
        self.stats["peak_connections"] = max(
            self.stats["peak_connections"],
            self.stats["active_connections"]
        )
        
        # 记录连接历史
        self._add_to_history({
            "event": "connection_added",
            "agent_id": agent_id,
            "session_id": connection_info.session_id,
            "timestamp": datetime.now().isoformat()
        })
        
        logger.info(f"连接已添加到池中: {agent_id} (会话: {connection_info.session_id})")
        return True
    
    def remove_connection(self, session_id: str, reason: str = "unknown") -> Optional[ConnectionInfo]:
        """
        从池中移除连接
        
        Args:
            session_id: 会话ID
            reason: 移除原因
            
        Returns:
            被移除的连接信息
        """
        if session_id not in self.active_connections:
            return None
        
        connection_info = self.active_connections[session_id]
        agent_id = connection_info.agent_id
        
        # 从活跃连接中移除
        del self.active_connections[session_id]
        
        # 从代理连接列表中移除
        if agent_id in self.connections:
            self.connections[agent_id] = [
                conn for conn in self.connections[agent_id]
                if conn.session_id != session_id
            ]
            
            # 如果代理没有连接了，移除代理条目
            if not self.connections[agent_id]:
                del self.connections[agent_id]
        
        # 更新统计
        self.stats["active_connections"] = len(self.active_connections)
        self.stats["disconnections"] += 1
        
        # 记录连接历史
        self._add_to_history({
            "event": "connection_removed",
            "agent_id": agent_id,
            "session_id": session_id,
            "reason": reason,
            "timestamp": datetime.now().isoformat(),
            "duration": (datetime.now() - connection_info.connected_at).total_seconds()
        })
        
        logger.info(f"连接已从池中移除: {agent_id} (会话: {session_id}, 原因: {reason})")
        return connection_info
    
    def get_connection(self, session_id: str) -> Optional[ConnectionInfo]:
        """获取连接信息"""
        return self.active_connections.get(session_id)
    
    def get_agent_connections(self, agent_id: str) -> List[ConnectionInfo]:
        """获取代理的所有连接"""
        return self.connections.get(agent_id, [])
    
    def get_primary_connection(self, agent_id: str) -> Optional[ConnectionInfo]:
        """获取代理的主连接（第一个认证的连接）"""
        connections = self.get_agent_connections(agent_id)
        for conn in connections:
            if conn.state == ConnectionState.AUTHENTICATED:
                return conn
        return connections[0] if connections else None
    
    def get_all_connections(self) -> List[ConnectionInfo]:
        """获取所有连接"""
        return list(self.active_connections.values())
    
    def get_connected_agents(self) -> Set[str]:
        """获取所有已连接的代理ID"""
        return set(self.connections.keys())
    
    def is_agent_connected(self, agent_id: str) -> bool:
        """检查代理是否已连接"""
        return agent_id in self.connections and len(self.connections[agent_id]) > 0
    
    def get_connection_count(self, agent_id: str = None) -> int:
        """获取连接数"""
        if agent_id:
            return len(self.connections.get(agent_id, []))
        return len(self.active_connections)
    
    def get_stats(self) -> Dict[str, Any]:
        """获取连接池统计信息"""
        return {
            **self.stats,
            "agents_connected": len(self.connections),
            "connections_by_agent": {
                agent_id: len(connections)
                for agent_id, connections in self.connections.items()
            }
        }
    
    def get_connection_history(self, limit: int = 100) -> List[Dict[str, Any]]:
        """获取连接历史"""
        return self.connection_history[-limit:]
    
    def _add_to_history(self, event: Dict[str, Any]):
        """添加事件到历史记录"""
        self.connection_history.append(event)
        if len(self.connection_history) > self.max_history_size:
            self.connection_history = self.connection_history[-self.max_history_size:]


class HeartbeatManager:
    """心跳管理器"""
    
    def __init__(self, connection_pool: ConnectionPool):
        self.connection_pool = connection_pool
        self.heartbeat_interval = 30  # 心跳间隔（秒）
        self.heartbeat_timeout = 90   # 心跳超时（秒）
        self.max_missed_heartbeats = 3  # 最大丢失心跳次数
        
        # 心跳监控任务
        self._monitor_task: Optional[asyncio.Task] = None
        self._running = False
        
        # 心跳统计
        self.stats = {
            "heartbeats_sent": 0,
            "heartbeats_received": 0,
            "heartbeat_timeouts": 0,
            "connections_recovered": 0
        }
    
    async def start_monitoring(self):
        """启动心跳监控"""
        if self._running:
            return
        
        self._running = True
        self._monitor_task = asyncio.create_task(self._monitor_loop())
        logger.info("心跳监控已启动")
    
    async def stop_monitoring(self):
        """停止心跳监控"""
        self._running = False
        if self._monitor_task:
            self._monitor_task.cancel()
            try:
                await self._monitor_task
            except asyncio.CancelledError:
                pass
        logger.info("心跳监控已停止")
    
    async def _monitor_loop(self):
        """心跳监控循环"""
        while self._running:
            try:
                await asyncio.sleep(self.heartbeat_interval)
                await self._check_heartbeats()
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"心跳监控异常: {e}")
    
    async def _check_heartbeats(self):
        """检查心跳状态"""
        current_time = datetime.now()
        expired_connections = []
        
        for connection in self.connection_pool.get_all_connections():
            if connection.state != ConnectionState.AUTHENTICATED:
                continue
            
            # 检查心跳超时
            if connection.last_heartbeat:
                time_since_heartbeat = (current_time - connection.last_heartbeat).total_seconds()
                if time_since_heartbeat > self.heartbeat_timeout:
                    connection.missed_heartbeats += 1
                    logger.warning(
                        f"代理 {connection.agent_id} 心跳超时 "
                        f"({time_since_heartbeat:.1f}s)，丢失心跳次数: {connection.missed_heartbeats}"
                    )
                    
                    if connection.missed_heartbeats >= self.max_missed_heartbeats:
                        expired_connections.append(connection)
            
            # 检查发送心跳的时间
            elif connection.last_heartbeat_sent:
                time_since_sent = (current_time - connection.last_heartbeat_sent).total_seconds()
                if time_since_sent > self.heartbeat_timeout:
                    connection.missed_heartbeats += 1
                    if connection.missed_heartbeats >= self.max_missed_heartbeats:
                        expired_connections.append(connection)
        
        # 处理过期连接
        for connection in expired_connections:
            logger.error(f"代理 {connection.agent_id} 心跳超时，断开连接")
            self.stats["heartbeat_timeouts"] += 1
            self.connection_pool.stats["heartbeat_timeouts"] += 1
            
            # 这里需要调用连接管理器的断开方法
            # 由于循环依赖，我们通过回调来处理
            if hasattr(self, '_timeout_callback'):
                await self._timeout_callback(connection.session_id, "heartbeat_timeout")
    
    def record_heartbeat_sent(self, session_id: str):
        """记录心跳发送"""
        connection = self.connection_pool.get_connection(session_id)
        if connection:
            connection.last_heartbeat_sent = datetime.now()
            self.stats["heartbeats_sent"] += 1
    
    def record_heartbeat_received(self, session_id: str):
        """记录心跳接收"""
        connection = self.connection_pool.get_connection(session_id)
        if connection:
            connection.last_heartbeat = datetime.now()
            connection.missed_heartbeats = 0  # 重置丢失计数
            self.stats["heartbeats_received"] += 1
    
    def set_timeout_callback(self, callback: Callable[[str, str], Awaitable[None]]):
        """设置超时回调"""
        self._timeout_callback = callback
    
    def get_stats(self) -> Dict[str, Any]:
        """获取心跳统计"""
        return self.stats.copy()


class LoadMonitor:
    """负载监控器"""
    
    def __init__(self, connection_pool: ConnectionPool):
        self.connection_pool = connection_pool
        
        # 负载阈值
        self.cpu_threshold = 80.0      # CPU使用率阈值
        self.memory_threshold = 85.0   # 内存使用率阈值
        self.disk_threshold = 90.0     # 磁盘使用率阈值
        
        # 负载统计
        self.load_history: Dict[str, List[Dict[str, Any]]] = {}  # agent_id -> load_records
        self.max_history_size = 100
        
        # 告警状态
        self.alert_states: Dict[str, Dict[str, bool]] = {}  # agent_id -> {metric: is_alerting}
    
    def update_agent_load(self, agent_id: str, load_metrics: Dict[str, float]):
        """
        更新代理负载信息
        
        Args:
            agent_id: 代理ID
            load_metrics: 负载指标
        """
        # 更新连接池中的负载信息
        connections = self.connection_pool.get_agent_connections(agent_id)
        for connection in connections:
            connection.load_metrics = load_metrics.copy()
        
        # 记录负载历史
        if agent_id not in self.load_history:
            self.load_history[agent_id] = []
        
        load_record = {
            "timestamp": datetime.now().isoformat(),
            "metrics": load_metrics.copy()
        }
        
        self.load_history[agent_id].append(load_record)
        
        # 限制历史记录大小
        if len(self.load_history[agent_id]) > self.max_history_size:
            self.load_history[agent_id] = self.load_history[agent_id][-self.max_history_size:]
        
        # 检查告警条件
        self._check_load_alerts(agent_id, load_metrics)
    
    def _check_load_alerts(self, agent_id: str, load_metrics: Dict[str, float]):
        """检查负载告警"""
        if agent_id not in self.alert_states:
            self.alert_states[agent_id] = {}
        
        alerts = []
        
        # 检查CPU使用率
        cpu_usage = load_metrics.get("cpu_usage", 0)
        if cpu_usage > self.cpu_threshold:
            if not self.alert_states[agent_id].get("cpu", False):
                alerts.append(f"CPU使用率过高: {cpu_usage:.1f}%")
                self.alert_states[agent_id]["cpu"] = True
        else:
            if self.alert_states[agent_id].get("cpu", False):
                alerts.append(f"CPU使用率恢复正常: {cpu_usage:.1f}%")
                self.alert_states[agent_id]["cpu"] = False
        
        # 检查内存使用率
        memory_usage = load_metrics.get("memory_usage", 0)
        if memory_usage > self.memory_threshold:
            if not self.alert_states[agent_id].get("memory", False):
                alerts.append(f"内存使用率过高: {memory_usage:.1f}%")
                self.alert_states[agent_id]["memory"] = True
        else:
            if self.alert_states[agent_id].get("memory", False):
                alerts.append(f"内存使用率恢复正常: {memory_usage:.1f}%")
                self.alert_states[agent_id]["memory"] = False
        
        # 检查磁盘使用率
        disk_usage = load_metrics.get("disk_usage", 0)
        if disk_usage > self.disk_threshold:
            if not self.alert_states[agent_id].get("disk", False):
                alerts.append(f"磁盘使用率过高: {disk_usage:.1f}%")
                self.alert_states[agent_id]["disk"] = True
        else:
            if self.alert_states[agent_id].get("disk", False):
                alerts.append(f"磁盘使用率恢复正常: {disk_usage:.1f}%")
                self.alert_states[agent_id]["disk"] = False
        
        # 记录告警
        for alert in alerts:
            logger.warning(f"代理 {agent_id} 负载告警: {alert}")
    
    def get_agent_load(self, agent_id: str) -> Optional[Dict[str, float]]:
        """获取代理当前负载"""
        connection = self.connection_pool.get_primary_connection(agent_id)
        return connection.load_metrics if connection else None
    
    def get_agent_load_history(self, agent_id: str, limit: int = 50) -> List[Dict[str, Any]]:
        """获取代理负载历史"""
        history = self.load_history.get(agent_id, [])
        return history[-limit:]
    
    def get_load_summary(self) -> Dict[str, Any]:
        """获取负载摘要"""
        summary = {
            "total_agents": len(self.load_history),
            "agents_with_alerts": 0,
            "average_loads": {},
            "peak_loads": {},
            "alert_counts": {"cpu": 0, "memory": 0, "disk": 0}
        }
        
        if not self.load_history:
            return summary
        
        # 计算平均负载和峰值负载
        all_cpu = []
        all_memory = []
        all_disk = []
        
        for agent_id, history in self.load_history.items():
            if not history:
                continue
            
            # 获取最新的负载数据
            latest = history[-1]["metrics"]
            all_cpu.append(latest.get("cpu_usage", 0))
            all_memory.append(latest.get("memory_usage", 0))
            all_disk.append(latest.get("disk_usage", 0))
            
            # 统计告警
            alerts = self.alert_states.get(agent_id, {})
            if any(alerts.values()):
                summary["agents_with_alerts"] += 1
            
            for metric, is_alerting in alerts.items():
                if is_alerting:
                    summary["alert_counts"][metric] += 1
        
        if all_cpu:
            summary["average_loads"]["cpu"] = sum(all_cpu) / len(all_cpu)
            summary["peak_loads"]["cpu"] = max(all_cpu)
        
        if all_memory:
            summary["average_loads"]["memory"] = sum(all_memory) / len(all_memory)
            summary["peak_loads"]["memory"] = max(all_memory)
        
        if all_disk:
            summary["average_loads"]["disk"] = sum(all_disk) / len(all_disk)
            summary["peak_loads"]["disk"] = max(all_disk)
        
        return summary
    
    def is_agent_overloaded(self, agent_id: str) -> bool:
        """检查代理是否过载"""
        load_metrics = self.get_agent_load(agent_id)
        if not load_metrics:
            return False
        
        return (
            load_metrics.get("cpu_usage", 0) > self.cpu_threshold or
            load_metrics.get("memory_usage", 0) > self.memory_threshold or
            load_metrics.get("disk_usage", 0) > self.disk_threshold
        )
    
    def get_available_agents(self) -> List[str]:
        """获取可用的代理列表（未过载）"""
        available = []
        for agent_id in self.connection_pool.get_connected_agents():
            if not self.is_agent_overloaded(agent_id):
                available.append(agent_id)
        return available


class ConnectionRecovery:
    """连接恢复管理器"""
    
    def __init__(self, connection_pool: ConnectionPool):
        self.connection_pool = connection_pool
        
        # 恢复配置
        self.max_recovery_attempts = 3
        self.recovery_delay = 5  # 秒
        self.recovery_backoff = 2  # 退避倍数
        
        # 恢复状态跟踪
        self.recovery_attempts: Dict[str, int] = {}  # agent_id -> attempt_count
        self.recovery_tasks: Dict[str, asyncio.Task] = {}  # agent_id -> recovery_task
        
        # 恢复统计
        self.stats = {
            "recovery_attempts": 0,
            "successful_recoveries": 0,
            "failed_recoveries": 0
        }
    
    async def attempt_recovery(self, agent_id: str, reason: str = "connection_lost"):
        """
        尝试恢复代理连接
        
        Args:
            agent_id: 代理ID
            reason: 恢复原因
        """
        if agent_id in self.recovery_tasks:
            logger.info(f"代理 {agent_id} 已在恢复中，跳过")
            return
        
        logger.info(f"开始恢复代理 {agent_id} 的连接 (原因: {reason})")
        
        # 创建恢复任务
        self.recovery_tasks[agent_id] = asyncio.create_task(
            self._recovery_loop(agent_id, reason)
        )
    
    async def _recovery_loop(self, agent_id: str, reason: str):
        """恢复循环"""
        attempt = self.recovery_attempts.get(agent_id, 0)
        
        while attempt < self.max_recovery_attempts:
            attempt += 1
            self.recovery_attempts[agent_id] = attempt
            self.stats["recovery_attempts"] += 1
            
            logger.info(f"代理 {agent_id} 恢复尝试 {attempt}/{self.max_recovery_attempts}")
            
            try:
                # 等待恢复延迟
                delay = self.recovery_delay * (self.recovery_backoff ** (attempt - 1))
                await asyncio.sleep(delay)
                
                # 检查代理是否已重新连接
                if self.connection_pool.is_agent_connected(agent_id):
                    logger.info(f"代理 {agent_id} 已重新连接，恢复成功")
                    self.stats["successful_recoveries"] += 1
                    self._cleanup_recovery(agent_id)
                    return
                
                # 尝试通知代理重新连接（如果有其他通信渠道）
                await self._notify_agent_reconnect(agent_id)
                
            except Exception as e:
                logger.error(f"代理 {agent_id} 恢复尝试 {attempt} 失败: {e}")
        
        # 所有恢复尝试都失败了
        logger.error(f"代理 {agent_id} 恢复失败，已达最大尝试次数")
        self.stats["failed_recoveries"] += 1
        
        # 更新数据库中的代理状态
        try:
            async with get_db_session() as db:
                agent_repo = AgentRepository(db)
                await agent_repo.update_agent_status(agent_id, AgentStatus.OFFLINE)
        except Exception as e:
            logger.error(f"更新代理状态失败: {e}")
        
        self._cleanup_recovery(agent_id)
    
    async def _notify_agent_reconnect(self, agent_id: str):
        """通知代理重新连接"""
        # 这里可以实现其他通信方式来通知代理重新连接
        # 例如：通过数据库标记、消息队列等
        logger.debug(f"通知代理 {agent_id} 重新连接")
    
    def _cleanup_recovery(self, agent_id: str):
        """清理恢复状态"""
        self.recovery_attempts.pop(agent_id, None)
        task = self.recovery_tasks.pop(agent_id, None)
        if task and not task.done():
            task.cancel()
    
    def cancel_recovery(self, agent_id: str):
        """取消代理的恢复尝试"""
        if agent_id in self.recovery_tasks:
            logger.info(f"取消代理 {agent_id} 的恢复尝试")
            self._cleanup_recovery(agent_id)
    
    def is_recovering(self, agent_id: str) -> bool:
        """检查代理是否在恢复中"""
        return agent_id in self.recovery_tasks
    
    def get_recovery_status(self, agent_id: str) -> Optional[Dict[str, Any]]:
        """获取代理的恢复状态"""
        if not self.is_recovering(agent_id):
            return None
        
        return {
            "agent_id": agent_id,
            "current_attempt": self.recovery_attempts.get(agent_id, 0),
            "max_attempts": self.max_recovery_attempts,
            "is_recovering": True
        }
    
    def get_stats(self) -> Dict[str, Any]:
        """获取恢复统计"""
        return {
            **self.stats,
            "agents_recovering": len(self.recovery_tasks),
            "recovery_success_rate": (
                self.stats["successful_recoveries"] / max(1, self.stats["recovery_attempts"])
            ) * 100
        }


class AdvancedConnectionManager:
    """高级连接管理器"""
    
    def __init__(self, max_connections_per_agent: int = 1):
        """
        初始化高级连接管理器
        
        Args:
            max_connections_per_agent: 每个代理的最大连接数
        """
        # 核心组件
        self.connection_pool = ConnectionPool(max_connections_per_agent)
        self.heartbeat_manager = HeartbeatManager(self.connection_pool)
        self.load_monitor = LoadMonitor(self.connection_pool)
        self.recovery_manager = ConnectionRecovery(self.connection_pool)
        
        # 设置心跳超时回调
        self.heartbeat_manager.set_timeout_callback(self._handle_heartbeat_timeout)
        
        # 消息处理器
        self.message_handlers: Dict[str, Callable[[str, Dict[str, Any]], Awaitable[None]]] = {}
        
        # 启动状态
        self._started = False
    
    async def start(self):
        """启动连接管理器"""
        if self._started:
            return
        
        await self.heartbeat_manager.start_monitoring()
        self._started = True
        logger.info("高级连接管理器已启动")
    
    async def stop(self):
        """停止连接管理器"""
        if not self._started:
            return
        
        await self.heartbeat_manager.stop_monitoring()
        
        # 取消所有恢复任务
        for agent_id in list(self.recovery_manager.recovery_tasks.keys()):
            self.recovery_manager.cancel_recovery(agent_id)
        
        self._started = False
        logger.info("高级连接管理器已停止")
    
    async def add_connection(self, websocket: WebSocket, agent_id: str, session_info: Dict[str, Any]) -> bool:
        """添加新连接"""
        # 创建连接信息
        connection_info = ConnectionInfo(
            agent_id=agent_id,
            websocket=websocket,
            state=ConnectionState.CONNECTING,
            session_id=session_info["session_id"],
            agent_info=session_info.get("agent"),
            version=session_info.get("version", "unknown")
        )
        
        # 添加到连接池
        if not self.connection_pool.add_connection(connection_info):
            return False
        
        # 接受WebSocket连接
        await websocket.accept()
        connection_info.state = ConnectionState.CONNECTED
        
        # 取消该代理的恢复尝试（如果有）
        self.recovery_manager.cancel_recovery(agent_id)
        
        logger.info(f"代理 {agent_id} 连接已建立")
        return True
    
    async def authenticate_connection(self, session_id: str) -> bool:
        """认证连接"""
        connection = self.connection_pool.get_connection(session_id)
        if not connection:
            return False
        
        connection.state = ConnectionState.AUTHENTICATED
        connection.authenticated_at = datetime.now()
        
        # 更新数据库中的代理状态
        try:
            async with get_db_session() as db:
                agent_repo = AgentRepository(db)
                await agent_repo.update_agent_status(connection.agent_id, AgentStatus.ONLINE)
        except Exception as e:
            logger.error(f"更新代理状态失败: {e}")
        
        logger.info(f"代理 {connection.agent_id} 认证成功")
        return True
    
    async def remove_connection(self, session_id: str, reason: str = "unknown") -> bool:
        """移除连接"""
        connection = self.connection_pool.get_connection(session_id)
        if not connection:
            return False
        
        agent_id = connection.agent_id
        connection.state = ConnectionState.DISCONNECTING
        
        try:
            # 发送断开通知
            disconnect_message = {
                "type": "disconnect",
                "data": {
                    "reason": reason,
                    "timestamp": datetime.now().isoformat()
                }
            }
            await connection.websocket.send_text(json.dumps(disconnect_message))
            
            # 关闭WebSocket连接
            await connection.websocket.close()
            
        except Exception as e:
            logger.error(f"关闭WebSocket连接时出错: {e}")
        finally:
            # 从连接池中移除
            self.connection_pool.remove_connection(session_id, reason)
            
            # 更新数据库中的代理状态
            try:
                async with get_db_session() as db:
                    agent_repo = AgentRepository(db)
                    await agent_repo.update_agent_status(agent_id, AgentStatus.OFFLINE)
            except Exception as e:
                logger.error(f"更新代理状态失败: {e}")
            
            # 如果是意外断开，尝试恢复连接
            if reason in ["heartbeat_timeout", "connection_error", "network_error"]:
                await self.recovery_manager.attempt_recovery(agent_id, reason)
        
        logger.info(f"代理 {agent_id} 连接已断开 (原因: {reason})")
        return True
    
    async def send_message(self, agent_id: str, message: Dict[str, Any]) -> bool:
        """发送消息给代理"""
        connection = self.connection_pool.get_primary_connection(agent_id)
        if not connection or connection.state != ConnectionState.AUTHENTICATED:
            logger.warning(f"代理 {agent_id} 未连接或未认证，无法发送消息")
            return False
        
        try:
            # 添加消息ID和时间戳
            if "id" not in message:
                message["id"] = str(uuid.uuid4())
            if "timestamp" not in message:
                message["timestamp"] = datetime.now().isoformat()
            
            message_json = json.dumps(message, ensure_ascii=False)
            await connection.websocket.send_text(message_json)
            
            # 更新统计
            connection.message_count_sent += 1
            connection.bytes_sent += len(message_json.encode('utf-8'))
            
            logger.debug(f"已向代理 {agent_id} 发送消息: {message.get('type', 'unknown')}")
            return True
            
        except Exception as e:
            logger.error(f"向代理 {agent_id} 发送消息失败: {e}")
            # 连接可能已断开，尝试移除连接
            await self.remove_connection(connection.session_id, "send_failed")
            return False
    
    async def broadcast_message(self, message: Dict[str, Any], exclude_agents: Optional[Set[str]] = None) -> int:
        """广播消息"""
        if exclude_agents is None:
            exclude_agents = set()
        
        success_count = 0
        for agent_id in self.connection_pool.get_connected_agents():
            if agent_id in exclude_agents:
                continue
            
            if await self.send_message(agent_id, message.copy()):
                success_count += 1
        
        logger.info(f"广播消息成功发送给 {success_count} 个代理")
        return success_count
    
    async def handle_message(self, session_id: str, message: Dict[str, Any]):
        """处理来自代理的消息"""
        connection = self.connection_pool.get_connection(session_id)
        if not connection:
            logger.warning(f"收到来自未知会话 {session_id} 的消息")
            return
        
        agent_id = connection.agent_id
        message_type = message.get("type")
        
        # 更新统计
        connection.message_count_received += 1
        message_json = json.dumps(message, ensure_ascii=False)
        connection.bytes_received += len(message_json.encode('utf-8'))
        
        logger.debug(f"收到来自代理 {agent_id} 的消息: {message_type}")
        
        # 处理心跳消息
        if message_type == "heartbeat":
            await self._handle_heartbeat(session_id, message)
            return
        
        # 处理资源报告
        if message_type == "resource_report":
            await self._handle_resource_report(agent_id, message)
        
        # 处理代理注册
        if message_type == "agent_register":
            await self._handle_agent_register(session_id, message)
        
        # 调用注册的消息处理器
        if message_type in self.message_handlers:
            try:
                await self.message_handlers[message_type](agent_id, message)
            except Exception as e:
                logger.error(f"处理消息 {message_type} 时发生异常: {e}")
                
                # 发送错误响应
                error_response = {
                    "type": "error",
                    "data": {
                        "error": "Message processing failed",
                        "original_message_id": message.get("id"),
                        "timestamp": datetime.now().isoformat()
                    }
                }
                await self.send_message(agent_id, error_response)
        else:
            logger.warning(f"未找到消息类型 {message_type} 的处理器")
    
    async def _handle_heartbeat(self, session_id: str, message: Dict[str, Any]):
        """处理心跳消息"""
        connection = self.connection_pool.get_connection(session_id)
        if not connection:
            return
        
        # 记录心跳
        self.heartbeat_manager.record_heartbeat_received(session_id)
        
        # 发送心跳响应
        heartbeat_response = {
            "type": "heartbeat_response",
            "data": {
                "agent_id": connection.agent_id,
                "server_time": datetime.now().isoformat(),
                "original_message_id": message.get("id")
            }
        }
        
        await self.send_message(connection.agent_id, heartbeat_response)
        self.heartbeat_manager.record_heartbeat_sent(session_id)
    
    async def _handle_resource_report(self, agent_id: str, message: Dict[str, Any]):
        """处理资源报告"""
        data = message.get("data", {})
        resources = data.get("resources", {})
        
        # 更新负载监控
        self.load_monitor.update_agent_load(agent_id, resources)
        
        logger.debug(f"已更新代理 {agent_id} 的负载信息: {resources}")
    
    async def _handle_agent_register(self, session_id: str, message: Dict[str, Any]):
        """处理代理注册"""
        connection = self.connection_pool.get_connection(session_id)
        if not connection:
            return
        
        data = message.get("data", {})
        capabilities = data.get("capabilities", [])
        version = data.get("version", "unknown")
        
        # 更新连接信息
        connection.capabilities = capabilities
        connection.version = version
        
        logger.info(f"代理 {connection.agent_id} 注册，能力: {capabilities}, 版本: {version}")
    
    async def _handle_heartbeat_timeout(self, session_id: str, reason: str):
        """处理心跳超时"""
        await self.remove_connection(session_id, reason)
    
    def register_message_handler(self, message_type: str, handler: Callable[[str, Dict[str, Any]], Awaitable[None]]):
        """注册消息处理器"""
        self.message_handlers[message_type] = handler
        logger.info(f"已注册消息处理器: {message_type}")
    
    def get_connection_stats(self) -> Dict[str, Any]:
        """获取连接统计信息"""
        return {
            "connection_pool": self.connection_pool.get_stats(),
            "heartbeat": self.heartbeat_manager.get_stats(),
            "load_monitor": self.load_monitor.get_load_summary(),
            "recovery": self.recovery_manager.get_stats(),
            "connected_agents": [
                conn.to_dict() for conn in self.connection_pool.get_all_connections()
            ]
        }
    
    def get_agent_info(self, agent_id: str) -> Optional[Dict[str, Any]]:
        """获取代理详细信息"""
        connection = self.connection_pool.get_primary_connection(agent_id)
        if not connection:
            return None
        
        return {
            "connection": connection.to_dict(),
            "load_history": self.load_monitor.get_agent_load_history(agent_id),
            "recovery_status": self.recovery_manager.get_recovery_status(agent_id),
            "is_overloaded": self.load_monitor.is_agent_overloaded(agent_id)
        }
    
    def is_agent_connected(self, agent_id: str) -> bool:
        """检查代理是否已连接"""
        return self.connection_pool.is_agent_connected(agent_id)
    
    def get_connected_agents(self) -> Set[str]:
        """获取所有已连接的代理"""
        return self.connection_pool.get_connected_agents()
    
    def get_available_agents(self) -> List[str]:
        """获取可用的代理列表（未过载）"""
        return self.load_monitor.get_available_agents()


# 全局高级连接管理器实例
advanced_connection_manager = AdvancedConnectionManager()