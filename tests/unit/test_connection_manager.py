"""连接管理器测试"""

import pytest
import asyncio
import uuid
from datetime import datetime, timedelta
from unittest.mock import Mock, AsyncMock, patch, MagicMock
from fastapi import WebSocket

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))

from management_platform.api.connection_manager import (
    ConnectionInfo,
    ConnectionState,
    ConnectionPool,
    HeartbeatManager,
    LoadMonitor,
    ConnectionRecovery,
    AdvancedConnectionManager
)


class TestConnectionInfo:
    """连接信息测试"""
    
    def test_connection_info_creation(self):
        """测试连接信息创建"""
        websocket = Mock(spec=WebSocket)
        agent_id = "test_agent"
        session_id = str(uuid.uuid4())
        
        conn_info = ConnectionInfo(
            agent_id=agent_id,
            websocket=websocket,
            state=ConnectionState.CONNECTED,
            session_id=session_id
        )
        
        assert conn_info.agent_id == agent_id
        assert conn_info.websocket == websocket
        assert conn_info.state == ConnectionState.CONNECTED
        assert conn_info.session_id == session_id
        assert conn_info.missed_heartbeats == 0
        assert conn_info.message_count_sent == 0
        assert conn_info.message_count_received == 0
    
    def test_connection_info_to_dict(self):
        """测试连接信息转换为字典"""
        websocket = Mock(spec=WebSocket)
        agent_id = "test_agent"
        session_id = str(uuid.uuid4())
        
        conn_info = ConnectionInfo(
            agent_id=agent_id,
            websocket=websocket,
            state=ConnectionState.AUTHENTICATED,
            session_id=session_id,
            capabilities=["icmp", "tcp"],
            version="1.0.0"
        )
        
        conn_dict = conn_info.to_dict()
        
        assert conn_dict["agent_id"] == agent_id
        assert conn_dict["state"] == "authenticated"
        assert conn_dict["session_id"] == session_id
        assert conn_dict["capabilities"] == ["icmp", "tcp"]
        assert conn_dict["version"] == "1.0.0"
        assert "connection_duration" in conn_dict


class TestConnectionPool:
    """连接池测试"""
    
    @pytest.fixture
    def pool(self):
        """创建连接池实例"""
        return ConnectionPool(max_connections_per_agent=2)
    
    @pytest.fixture
    def mock_connection(self):
        """创建模拟连接信息"""
        websocket = Mock(spec=WebSocket)
        return ConnectionInfo(
            agent_id="test_agent",
            websocket=websocket,
            state=ConnectionState.CONNECTED,
            session_id=str(uuid.uuid4())
        )
    
    def test_add_connection_success(self, pool, mock_connection):
        """测试成功添加连接"""
        result = pool.add_connection(mock_connection)
        
        assert result is True
        assert mock_connection.agent_id in pool.connections
        assert mock_connection.session_id in pool.active_connections
        assert pool.stats["total_connections"] == 1
        assert pool.stats["active_connections"] == 1
    
    def test_add_connection_limit_exceeded(self, pool):
        """测试连接数限制"""
        agent_id = "test_agent"
        
        # 添加最大数量的连接
        for i in range(pool.max_connections_per_agent):
            websocket = Mock(spec=WebSocket)
            conn_info = ConnectionInfo(
                agent_id=agent_id,
                websocket=websocket,
                state=ConnectionState.CONNECTED,
                session_id=str(uuid.uuid4())
            )
            assert pool.add_connection(conn_info) is True
        
        # 尝试添加超出限制的连接
        websocket = Mock(spec=WebSocket)
        extra_conn = ConnectionInfo(
            agent_id=agent_id,
            websocket=websocket,
            state=ConnectionState.CONNECTED,
            session_id=str(uuid.uuid4())
        )
        assert pool.add_connection(extra_conn) is False
    
    def test_remove_connection(self, pool, mock_connection):
        """测试移除连接"""
        # 先添加连接
        pool.add_connection(mock_connection)
        
        # 移除连接
        removed = pool.remove_connection(mock_connection.session_id, "test")
        
        assert removed == mock_connection
        assert mock_connection.session_id not in pool.active_connections
        assert pool.stats["active_connections"] == 0
        assert pool.stats["disconnections"] == 1
    
    def test_remove_nonexistent_connection(self, pool):
        """测试移除不存在的连接"""
        result = pool.remove_connection("nonexistent_session", "test")
        assert result is None
    
    def test_get_connection(self, pool, mock_connection):
        """测试获取连接"""
        pool.add_connection(mock_connection)
        
        retrieved = pool.get_connection(mock_connection.session_id)
        assert retrieved == mock_connection
        
        # 测试获取不存在的连接
        assert pool.get_connection("nonexistent") is None
    
    def test_get_agent_connections(self, pool):
        """测试获取代理的所有连接"""
        agent_id = "test_agent"
        
        # 添加多个连接
        connections = []
        for i in range(2):
            websocket = Mock(spec=WebSocket)
            conn_info = ConnectionInfo(
                agent_id=agent_id,
                websocket=websocket,
                state=ConnectionState.CONNECTED,
                session_id=str(uuid.uuid4())
            )
            connections.append(conn_info)
            pool.add_connection(conn_info)
        
        agent_connections = pool.get_agent_connections(agent_id)
        assert len(agent_connections) == 2
        assert all(conn.agent_id == agent_id for conn in agent_connections)
    
    def test_get_primary_connection(self, pool):
        """测试获取主连接"""
        agent_id = "test_agent"
        
        # 添加未认证的连接
        websocket1 = Mock(spec=WebSocket)
        conn1 = ConnectionInfo(
            agent_id=agent_id,
            websocket=websocket1,
            state=ConnectionState.CONNECTED,
            session_id=str(uuid.uuid4())
        )
        pool.add_connection(conn1)
        
        # 添加已认证的连接
        websocket2 = Mock(spec=WebSocket)
        conn2 = ConnectionInfo(
            agent_id=agent_id,
            websocket=websocket2,
            state=ConnectionState.AUTHENTICATED,
            session_id=str(uuid.uuid4())
        )
        pool.add_connection(conn2)
        
        # 应该返回已认证的连接
        primary = pool.get_primary_connection(agent_id)
        assert primary == conn2
    
    def test_is_agent_connected(self, pool, mock_connection):
        """测试检查代理是否连接"""
        assert pool.is_agent_connected(mock_connection.agent_id) is False
        
        pool.add_connection(mock_connection)
        assert pool.is_agent_connected(mock_connection.agent_id) is True
        
        pool.remove_connection(mock_connection.session_id)
        assert pool.is_agent_connected(mock_connection.agent_id) is False
    
    def test_get_stats(self, pool, mock_connection):
        """测试获取统计信息"""
        pool.add_connection(mock_connection)
        
        stats = pool.get_stats()
        assert stats["total_connections"] == 1
        assert stats["active_connections"] == 1
        assert stats["agents_connected"] == 1
        assert mock_connection.agent_id in stats["connections_by_agent"]


class TestHeartbeatManager:
    """心跳管理器测试"""
    
    @pytest.fixture
    def pool(self):
        """创建连接池"""
        return ConnectionPool()
    
    @pytest.fixture
    def heartbeat_manager(self, pool):
        """创建心跳管理器"""
        return HeartbeatManager(pool)
    
    @pytest.fixture
    def mock_connection(self, pool):
        """创建模拟连接"""
        websocket = Mock(spec=WebSocket)
        conn_info = ConnectionInfo(
            agent_id="test_agent",
            websocket=websocket,
            state=ConnectionState.AUTHENTICATED,
            session_id=str(uuid.uuid4())
        )
        pool.add_connection(conn_info)
        return conn_info
    
    @pytest.mark.asyncio
    async def test_start_stop_monitoring(self, heartbeat_manager):
        """测试启动和停止监控"""
        assert not heartbeat_manager._running
        
        await heartbeat_manager.start_monitoring()
        assert heartbeat_manager._running
        assert heartbeat_manager._monitor_task is not None
        
        await heartbeat_manager.stop_monitoring()
        assert not heartbeat_manager._running
    
    def test_record_heartbeat_sent(self, heartbeat_manager, mock_connection):
        """测试记录心跳发送"""
        heartbeat_manager.record_heartbeat_sent(mock_connection.session_id)
        
        assert mock_connection.last_heartbeat_sent is not None
        assert heartbeat_manager.stats["heartbeats_sent"] == 1
    
    def test_record_heartbeat_received(self, heartbeat_manager, mock_connection):
        """测试记录心跳接收"""
        # 先设置一些丢失的心跳
        mock_connection.missed_heartbeats = 2
        
        heartbeat_manager.record_heartbeat_received(mock_connection.session_id)
        
        assert mock_connection.last_heartbeat is not None
        assert mock_connection.missed_heartbeats == 0  # 应该重置
        assert heartbeat_manager.stats["heartbeats_received"] == 1
    
    def test_record_heartbeat_nonexistent_connection(self, heartbeat_manager):
        """测试记录不存在连接的心跳"""
        # 不应该抛出异常
        heartbeat_manager.record_heartbeat_sent("nonexistent")
        heartbeat_manager.record_heartbeat_received("nonexistent")
    
    def test_set_timeout_callback(self, heartbeat_manager):
        """测试设置超时回调"""
        callback = AsyncMock()
        heartbeat_manager.set_timeout_callback(callback)
        
        assert heartbeat_manager._timeout_callback == callback
    
    def test_get_stats(self, heartbeat_manager):
        """测试获取统计信息"""
        stats = heartbeat_manager.get_stats()
        
        assert "heartbeats_sent" in stats
        assert "heartbeats_received" in stats
        assert "heartbeat_timeouts" in stats
        assert "connections_recovered" in stats


class TestLoadMonitor:
    """负载监控器测试"""
    
    @pytest.fixture
    def pool(self):
        """创建连接池"""
        return ConnectionPool()
    
    @pytest.fixture
    def load_monitor(self, pool):
        """创建负载监控器"""
        return LoadMonitor(pool)
    
    @pytest.fixture
    def mock_connection(self, pool):
        """创建模拟连接"""
        websocket = Mock(spec=WebSocket)
        conn_info = ConnectionInfo(
            agent_id="test_agent",
            websocket=websocket,
            state=ConnectionState.AUTHENTICATED,
            session_id=str(uuid.uuid4())
        )
        pool.add_connection(conn_info)
        return conn_info
    
    def test_update_agent_load(self, load_monitor, mock_connection):
        """测试更新代理负载"""
        load_metrics = {
            "cpu_usage": 45.5,
            "memory_usage": 60.2,
            "disk_usage": 30.1
        }
        
        load_monitor.update_agent_load(mock_connection.agent_id, load_metrics)
        
        # 检查连接中的负载信息是否更新
        assert mock_connection.load_metrics == load_metrics
        
        # 检查负载历史是否记录
        assert mock_connection.agent_id in load_monitor.load_history
        assert len(load_monitor.load_history[mock_connection.agent_id]) == 1
    
    def test_get_agent_load(self, load_monitor, mock_connection):
        """测试获取代理负载"""
        load_metrics = {"cpu_usage": 50.0}
        load_monitor.update_agent_load(mock_connection.agent_id, load_metrics)
        
        retrieved_load = load_monitor.get_agent_load(mock_connection.agent_id)
        assert retrieved_load == load_metrics
        
        # 测试不存在的代理
        assert load_monitor.get_agent_load("nonexistent") is None
    
    def test_get_agent_load_history(self, load_monitor, mock_connection):
        """测试获取代理负载历史"""
        # 添加多个负载记录
        for i in range(5):
            load_metrics = {"cpu_usage": 10.0 * i}
            load_monitor.update_agent_load(mock_connection.agent_id, load_metrics)
        
        history = load_monitor.get_agent_load_history(mock_connection.agent_id, limit=3)
        assert len(history) == 3
        
        # 检查是否是最新的记录
        assert history[-1]["metrics"]["cpu_usage"] == 40.0
    
    def test_is_agent_overloaded(self, load_monitor, mock_connection):
        """测试检查代理是否过载"""
        # 正常负载
        normal_load = {
            "cpu_usage": 50.0,
            "memory_usage": 60.0,
            "disk_usage": 70.0
        }
        load_monitor.update_agent_load(mock_connection.agent_id, normal_load)
        assert not load_monitor.is_agent_overloaded(mock_connection.agent_id)
        
        # 过载情况
        high_load = {
            "cpu_usage": 90.0,  # 超过80%阈值
            "memory_usage": 60.0,
            "disk_usage": 70.0
        }
        load_monitor.update_agent_load(mock_connection.agent_id, high_load)
        assert load_monitor.is_agent_overloaded(mock_connection.agent_id)
    
    def test_get_available_agents(self, load_monitor, pool):
        """测试获取可用代理列表"""
        # 创建两个代理连接
        agents = []
        for i, agent_id in enumerate(["agent1", "agent2"]):
            websocket = Mock(spec=WebSocket)
            conn_info = ConnectionInfo(
                agent_id=agent_id,
                websocket=websocket,
                state=ConnectionState.AUTHENTICATED,
                session_id=str(uuid.uuid4())
            )
            pool.add_connection(conn_info)
            agents.append(conn_info)
        
        # 设置不同的负载
        load_monitor.update_agent_load("agent1", {"cpu_usage": 50.0})  # 正常
        load_monitor.update_agent_load("agent2", {"cpu_usage": 90.0})  # 过载
        
        available = load_monitor.get_available_agents()
        assert "agent1" in available
        assert "agent2" not in available
    
    def test_get_load_summary(self, load_monitor, mock_connection):
        """测试获取负载摘要"""
        load_metrics = {
            "cpu_usage": 75.0,
            "memory_usage": 80.0,
            "disk_usage": 60.0
        }
        load_monitor.update_agent_load(mock_connection.agent_id, load_metrics)
        
        summary = load_monitor.get_load_summary()
        
        assert summary["total_agents"] == 1
        assert "average_loads" in summary
        assert "peak_loads" in summary
        assert summary["average_loads"]["cpu"] == 75.0


class TestConnectionRecovery:
    """连接恢复测试"""
    
    @pytest.fixture
    def pool(self):
        """创建连接池"""
        return ConnectionPool()
    
    @pytest.fixture
    def recovery_manager(self, pool):
        """创建恢复管理器"""
        return ConnectionRecovery(pool)
    
    @pytest.mark.asyncio
    async def test_attempt_recovery(self, recovery_manager):
        """测试尝试恢复"""
        agent_id = "test_agent"
        
        # 模拟恢复过程
        with patch.object(recovery_manager, '_recovery_loop', new_callable=AsyncMock) as mock_loop:
            await recovery_manager.attempt_recovery(agent_id, "test_reason")
            
            # 检查恢复任务是否创建
            assert agent_id in recovery_manager.recovery_tasks
            mock_loop.assert_called_once_with(agent_id, "test_reason")
    
    @pytest.mark.asyncio
    async def test_attempt_recovery_already_recovering(self, recovery_manager):
        """测试重复恢复尝试"""
        agent_id = "test_agent"
        
        # 创建一个模拟任务
        mock_task = AsyncMock()
        recovery_manager.recovery_tasks[agent_id] = mock_task
        
        with patch.object(recovery_manager, '_recovery_loop', new_callable=AsyncMock) as mock_loop:
            await recovery_manager.attempt_recovery(agent_id, "test_reason")
            
            # 不应该创建新的恢复任务
            mock_loop.assert_not_called()
    
    def test_cancel_recovery(self, recovery_manager):
        """测试取消恢复"""
        agent_id = "test_agent"
        
        # 创建模拟任务
        mock_task = Mock()
        mock_task.done.return_value = False
        mock_task.cancel = Mock()
        recovery_manager.recovery_tasks[agent_id] = mock_task
        recovery_manager.recovery_attempts[agent_id] = 2
        
        recovery_manager.cancel_recovery(agent_id)
        
        # 检查清理是否完成
        assert agent_id not in recovery_manager.recovery_tasks
        assert agent_id not in recovery_manager.recovery_attempts
        mock_task.cancel.assert_called_once()
    
    def test_is_recovering(self, recovery_manager):
        """测试检查是否在恢复中"""
        agent_id = "test_agent"
        
        assert not recovery_manager.is_recovering(agent_id)
        
        # 添加恢复任务
        recovery_manager.recovery_tasks[agent_id] = Mock()
        assert recovery_manager.is_recovering(agent_id)
    
    def test_get_recovery_status(self, recovery_manager):
        """测试获取恢复状态"""
        agent_id = "test_agent"
        
        # 没有恢复任务
        assert recovery_manager.get_recovery_status(agent_id) is None
        
        # 有恢复任务
        recovery_manager.recovery_tasks[agent_id] = Mock()
        recovery_manager.recovery_attempts[agent_id] = 2
        
        status = recovery_manager.get_recovery_status(agent_id)
        assert status["agent_id"] == agent_id
        assert status["current_attempt"] == 2
        assert status["is_recovering"] is True
    
    def test_get_stats(self, recovery_manager):
        """测试获取恢复统计"""
        recovery_manager.stats["recovery_attempts"] = 10
        recovery_manager.stats["successful_recoveries"] = 8
        recovery_manager.recovery_tasks["agent1"] = Mock()
        recovery_manager.recovery_tasks["agent2"] = Mock()
        
        stats = recovery_manager.get_stats()
        
        assert stats["recovery_attempts"] == 10
        assert stats["successful_recoveries"] == 8
        assert stats["agents_recovering"] == 2
        assert stats["recovery_success_rate"] == 80.0


class TestAdvancedConnectionManager:
    """高级连接管理器测试"""
    
    @pytest.fixture
    def manager(self):
        """创建高级连接管理器"""
        return AdvancedConnectionManager()
    
    @pytest.fixture
    def mock_websocket(self):
        """创建模拟WebSocket"""
        websocket = Mock(spec=WebSocket)
        websocket.accept = AsyncMock()
        websocket.send_text = AsyncMock()
        websocket.close = AsyncMock()
        return websocket
    
    @pytest.mark.asyncio
    async def test_start_stop(self, manager):
        """测试启动和停止"""
        assert not manager._started
        
        await manager.start()
        assert manager._started
        
        await manager.stop()
        assert not manager._started
    
    @pytest.mark.asyncio
    async def test_add_connection(self, manager, mock_websocket):
        """测试添加连接"""
        agent_id = "test_agent"
        session_info = {
            "session_id": str(uuid.uuid4()),
            "agent": {"id": agent_id},
            "version": "1.0.0"
        }
        
        result = await manager.add_connection(mock_websocket, agent_id, session_info)
        
        assert result is True
        assert manager.is_agent_connected(agent_id)
        mock_websocket.accept.assert_called_once()
    
    @pytest.mark.asyncio
    async def test_authenticate_connection(self, manager, mock_websocket):
        """测试认证连接"""
        agent_id = "test_agent"
        session_info = {
            "session_id": str(uuid.uuid4()),
            "agent": {"id": agent_id}
        }
        
        # 先添加连接
        await manager.add_connection(mock_websocket, agent_id, session_info)
        
        # 认证连接
        with patch('management_platform.api.connection_manager.get_db_session'), \
             patch('management_platform.api.connection_manager.AgentRepository'):
            
            result = await manager.authenticate_connection(session_info["session_id"])
            assert result is True
    
    @pytest.mark.asyncio
    async def test_send_message(self, manager, mock_websocket):
        """测试发送消息"""
        agent_id = "test_agent"
        session_info = {
            "session_id": str(uuid.uuid4()),
            "agent": {"id": agent_id}
        }
        
        # 添加并认证连接
        await manager.add_connection(mock_websocket, agent_id, session_info)
        
        with patch('management_platform.api.connection_manager.get_db_session'), \
             patch('management_platform.api.connection_manager.AgentRepository'):
            
            await manager.authenticate_connection(session_info["session_id"])
            
            # 发送消息
            message = {"type": "test_message", "data": {"key": "value"}}
            result = await manager.send_message(agent_id, message)
            
            assert result is True
            mock_websocket.send_text.assert_called_once()
    
    @pytest.mark.asyncio
    async def test_send_message_not_connected(self, manager):
        """测试向未连接的代理发送消息"""
        result = await manager.send_message("nonexistent_agent", {"type": "test"})
        assert result is False
    
    @pytest.mark.asyncio
    async def test_broadcast_message(self, manager):
        """测试广播消息"""
        # 创建多个连接
        agents = ["agent1", "agent2", "agent3"]
        websockets = []
        
        for agent_id in agents:
            websocket = Mock(spec=WebSocket)
            websocket.accept = AsyncMock()
            websocket.send_text = AsyncMock()
            websockets.append(websocket)
            
            session_info = {
                "session_id": str(uuid.uuid4()),
                "agent": {"id": agent_id}
            }
            
            await manager.add_connection(websocket, agent_id, session_info)
            
            with patch('management_platform.api.connection_manager.get_db_session'), \
                 patch('management_platform.api.connection_manager.AgentRepository'):
                
                await manager.authenticate_connection(session_info["session_id"])
        
        # 广播消息，排除一个代理
        message = {"type": "broadcast_test"}
        exclude_agents = {"agent2"}
        
        result = await manager.broadcast_message(message, exclude_agents)
        
        assert result == 2  # 应该成功发送给2个代理
        websockets[0].send_text.assert_called_once()  # agent1
        websockets[1].send_text.assert_not_called()   # agent2 (excluded)
        websockets[2].send_text.assert_called_once()  # agent3
    
    def test_register_message_handler(self, manager):
        """测试注册消息处理器"""
        handler = AsyncMock()
        manager.register_message_handler("test_message", handler)
        
        assert "test_message" in manager.message_handlers
        assert manager.message_handlers["test_message"] == handler
    
    def test_get_connection_stats(self, manager):
        """测试获取连接统计"""
        stats = manager.get_connection_stats()
        
        assert "connection_pool" in stats
        assert "heartbeat" in stats
        assert "load_monitor" in stats
        assert "recovery" in stats
        assert "connected_agents" in stats
    
    def test_is_agent_connected(self, manager):
        """测试检查代理是否连接"""
        assert not manager.is_agent_connected("test_agent")
    
    def test_get_connected_agents(self, manager):
        """测试获取已连接的代理"""
        agents = manager.get_connected_agents()
        assert isinstance(agents, set)
        assert len(agents) == 0
    
    def test_get_available_agents(self, manager):
        """测试获取可用代理"""
        agents = manager.get_available_agents()
        assert isinstance(agents, list)
        assert len(agents) == 0


if __name__ == "__main__":
    pytest.