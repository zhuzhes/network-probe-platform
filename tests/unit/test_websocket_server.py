"""WebSocket服务端测试"""

import pytest
import asyncio
import json
import uuid
from datetime import datetime, timedelta
from unittest.mock import Mock, AsyncMock, patch, MagicMock
from fastapi import WebSocket
from fastapi.testclient import TestClient

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))

from management_platform.api.websocket import (
    ConnectionManager,
    WebSocketAuthenticator,
    connection_manager,
    websocket_endpoint,
    handle_agent_register,
    handle_task_result,
    handle_resource_report
)
from shared.models.agent import Agent, AgentStatus


class TestConnectionManager:
    """连接管理器测试"""
    
    @pytest.fixture
    def manager(self):
        """创建连接管理器实例"""
        manager = ConnectionManager()
        # 停止心跳监控任务以避免测试干扰
        if manager._heartbeat_monitor_task:
            manager._heartbeat_monitor_task.cancel()
        return manager
    
    @pytest.fixture
    def mock_websocket(self):
        """创建模拟WebSocket连接"""
        websocket = Mock(spec=WebSocket)
        websocket.accept = AsyncMock()
        websocket.send_text = AsyncMock()
        websocket.close = AsyncMock()
        return websocket
    
    @pytest.mark.asyncio
    async def test_connect_agent(self, manager, mock_websocket):
        """测试代理连接"""
        agent_id = "test_agent_1"
        session_info = {
            "session_id": str(uuid.uuid4()),
            "agent_id": agent_id,
            "authenticated_at": datetime.now()
        }
        
        with patch('management_platform.api.websocket.get_db_session'), \
             patch('management_platform.api.websocket.AgentRepository'):
            
            await manager.connect_agent(mock_websocket, agent_id, session_info)
            
            # 验证连接已建立
            assert agent_id in manager.active_connections
            assert manager.active_connections[agent_id] == mock_websocket
            assert agent_id in manager.agent_sessions
            assert agent_id in manager.last_heartbeats
            
            # 验证WebSocket已接受连接
            mock_websocket.accept.assert_called_once()
            
            # 验证统计信息更新
            assert manager.connection_stats["total_connections"] == 1
            assert manager.connection_stats["active_connections"] == 1
    
    @pytest.mark.asyncio
    async def test_connect_agent_replace_existing(self, manager, mock_websocket):
        """测试替换现有代理连接"""
        agent_id = "test_agent_1"
        session_info = {
            "session_id": str(uuid.uuid4()),
            "agent_id": agent_id,
            "authenticated_at": datetime.now()
        }
        
        # 创建旧连接
        old_websocket = Mock(spec=WebSocket)
        old_websocket.send_text = AsyncMock()
        old_websocket.close = AsyncMock()
        
        with patch('management_platform.api.websocket.get_db_session'), \
             patch('management_platform.api.websocket.AgentRepository'):
            
            # 先建立旧连接
            manager.active_connections[agent_id] = old_websocket
            manager.agent_sessions[agent_id] = {"old": "session"}
            
            # 建立新连接
            await manager.connect_agent(mock_websocket, agent_id, session_info)
            
            # 验证旧连接被断开
            old_websocket.send_text.assert_called_once()
            old_websocket.close.assert_called_once()
            
            # 验证新连接已建立
            assert manager.active_connections[agent_id] == mock_websocket
            assert manager.agent_sessions[agent_id] == session_info
    
    @pytest.mark.asyncio
    async def test_disconnect_agent(self, manager, mock_websocket):
        """测试代理断开连接"""
        agent_id = "test_agent_1"
        session_info = {"session_id": str(uuid.uuid4())}
        
        with patch('management_platform.api.websocket.get_db_session'), \
             patch('management_platform.api.websocket.AgentRepository'):
            
            # 先建立连接
            manager.active_connections[agent_id] = mock_websocket
            manager.agent_sessions[agent_id] = session_info
            manager.last_heartbeats[agent_id] = datetime.now()
            
            # 断开连接
            await manager.disconnect_agent(agent_id, reason="test")
            
            # 验证连接已清理
            assert agent_id not in manager.active_connections
            assert agent_id not in manager.agent_sessions
            assert agent_id not in manager.last_heartbeats
            
            # 验证WebSocket发送了断开消息并关闭
            mock_websocket.send_text.assert_called_once()
            mock_websocket.close.assert_called_once()
            
            # 验证统计信息更新
            assert manager.connection_stats["active_connections"] == 0
    
    @pytest.mark.asyncio
    async def test_send_message_to_agent_success(self, manager, mock_websocket):
        """测试成功发送消息给代理"""
        agent_id = "test_agent_1"
        manager.active_connections[agent_id] = mock_websocket
        
        message = {
            "type": "test_message",
            "data": {"key": "value"}
        }
        
        result = await manager.send_message_to_agent(agent_id, message)
        
        # 验证发送成功
        assert result is True
        mock_websocket.send_text.assert_called_once()
        
        # 验证消息格式
        sent_message = json.loads(mock_websocket.send_text.call_args[0][0])
        assert sent_message["type"] == "test_message"
        assert sent_message["data"] == {"key": "value"}
        assert "id" in sent_message
        assert "timestamp" in sent_message
        
        # 验证统计信息更新
        assert manager.connection_stats["messages_sent"] == 1
    
    @pytest.mark.asyncio
    async def test_send_message_to_agent_not_connected(self, manager):
        """测试向未连接的代理发送消息"""
        agent_id = "not_connected_agent"
        message = {"type": "test_message"}
        
        result = await manager.send_message_to_agent(agent_id, message)
        
        # 验证发送失败
        assert result is False
    
    @pytest.mark.asyncio
    async def test_send_message_to_agent_send_failed(self, manager, mock_websocket):
        """测试发送消息失败的情况"""
        agent_id = "test_agent_1"
        manager.active_connections[agent_id] = mock_websocket
        
        # 模拟发送失败
        mock_websocket.send_text.side_effect = Exception("Send failed")
        
        with patch.object(manager, 'disconnect_agent', new_callable=AsyncMock) as mock_disconnect:
            message = {"type": "test_message"}
            result = await manager.send_message_to_agent(agent_id, message)
            
            # 验证发送失败
            assert result is False
            
            # 验证调用了断开连接
            mock_disconnect.assert_called_once_with(agent_id, reason="send_failed")
    
    @pytest.mark.asyncio
    async def test_broadcast_message(self, manager):
        """测试广播消息"""
        # 创建多个模拟连接
        agents = ["agent_1", "agent_2", "agent_3"]
        websockets = []
        
        for agent_id in agents:
            websocket = Mock(spec=WebSocket)
            websocket.send_text = AsyncMock()
            manager.active_connections[agent_id] = websocket
            websockets.append(websocket)
        
        message = {"type": "broadcast_test"}
        exclude_agents = {"agent_2"}
        
        result = await manager.broadcast_message(message, exclude_agents)
        
        # 验证返回成功发送的数量
        assert result == 2
        
        # 验证只有未排除的代理收到消息
        websockets[0].send_text.assert_called_once()  # agent_1
        websockets[1].send_text.assert_not_called()   # agent_2 (excluded)
        websockets[2].send_text.assert_called_once()  # agent_3
    
    @pytest.mark.asyncio
    async def test_handle_message_heartbeat(self, manager):
        """测试处理心跳消息"""
        agent_id = "test_agent_1"
        websocket = Mock(spec=WebSocket)
        websocket.send_text = AsyncMock()
        manager.active_connections[agent_id] = websocket
        
        message = {
            "type": "heartbeat",
            "id": str(uuid.uuid4()),
            "data": {"agent_id": agent_id}
        }
        
        await manager.handle_message(agent_id, message)
        
        # 验证心跳时间已更新
        assert agent_id in manager.last_heartbeats
        
        # 验证发送了心跳响应
        websocket.send_text.assert_called_once()
        response = json.loads(websocket.send_text.call_args[0][0])
        assert response["type"] == "heartbeat_response"
        assert response["data"]["agent_id"] == agent_id
    
    @pytest.mark.asyncio
    async def test_handle_message_with_handler(self, manager):
        """测试处理有处理器的消息"""
        agent_id = "test_agent_1"
        
        # 注册消息处理器
        handler = AsyncMock()
        manager.register_handler("test_message", handler)
        
        message = {
            "type": "test_message",
            "data": {"key": "value"}
        }
        
        await manager.handle_message(agent_id, message)
        
        # 验证处理器被调用
        handler.assert_called_once_with(agent_id, message)
    
    @pytest.mark.asyncio
    async def test_handle_message_unknown_type(self, manager):
        """测试处理未知类型消息"""
        agent_id = "test_agent_1"
        websocket = Mock(spec=WebSocket)
        websocket.send_text = AsyncMock()
        manager.active_connections[agent_id] = websocket
        
        message = {
            "type": "unknown_message_type",
            "id": str(uuid.uuid4())
        }
        
        await manager.handle_message(agent_id, message)
        
        # 验证发送了未知消息类型响应
        websocket.send_text.assert_called_once()
        response = json.loads(websocket.send_text.call_args[0][0])
        assert response["type"] == "unknown_message_type"
    
    @pytest.mark.asyncio
    async def test_handle_message_handler_exception(self, manager):
        """测试消息处理器异常"""
        agent_id = "test_agent_1"
        websocket = Mock(spec=WebSocket)
        websocket.send_text = AsyncMock()
        manager.active_connections[agent_id] = websocket
        
        # 注册会抛出异常的处理器
        handler = AsyncMock(side_effect=Exception("Handler error"))
        manager.register_handler("error_message", handler)
        
        message = {
            "type": "error_message",
            "id": str(uuid.uuid4())
        }
        
        await manager.handle_message(agent_id, message)
        
        # 验证发送了错误响应
        websocket.send_text.assert_called_once()
        response = json.loads(websocket.send_text.call_args[0][0])
        assert response["type"] == "error"
    
    def test_get_connected_agents(self, manager):
        """测试获取连接的代理"""
        agents = ["agent_1", "agent_2", "agent_3"]
        for agent_id in agents:
            manager.active_connections[agent_id] = Mock()
        
        connected_agents = manager.get_connected_agents()
        
        assert connected_agents == set(agents)
    
    def test_get_agent_session(self, manager):
        """测试获取代理会话信息"""
        agent_id = "test_agent_1"
        session_info = {"session_id": str(uuid.uuid4())}
        manager.agent_sessions[agent_id] = session_info
        
        result = manager.get_agent_session(agent_id)
        
        assert result == session_info
    
    def test_is_agent_connected(self, manager):
        """测试检查代理是否连接"""
        agent_id = "test_agent_1"
        manager.active_connections[agent_id] = Mock()
        
        assert manager.is_agent_connected(agent_id) is True
        assert manager.is_agent_connected("not_connected") is False
    
    def test_get_connection_stats(self, manager):
        """测试获取连接统计信息"""
        # 添加一些测试数据
        agent_id = "test_agent_1"
        manager.active_connections[agent_id] = Mock()
        manager.last_heartbeats[agent_id] = datetime.now()
        manager.connection_stats["messages_sent"] = 10
        
        stats = manager.get_connection_stats()
        
        assert "connected_agents" in stats
        assert "heartbeat_status" in stats
        assert stats["messages_sent"] == 10
        assert agent_id in stats["connected_agents"]
        assert agent_id in stats["heartbeat_status"]


class TestWebSocketAuthenticator:
    """WebSocket认证器测试"""
    
    def test_generate_auth_signature(self):
        """测试生成认证签名"""
        agent_id = "test_agent"
        api_key = "test_api_key"
        timestamp = "2023-01-01T00:00:00"
        nonce = "test_nonce"
        
        signature = WebSocketAuthenticator._generate_auth_signature(
            agent_id, api_key, timestamp, nonce
        )
        
        # 验证签名是64字符的十六进制字符串（SHA256）
        assert len(signature) == 64
        assert all(c in '0123456789abcdef' for c in signature)
        
        # 验证相同输入产生相同签名
        signature2 = WebSocketAuthenticator._generate_auth_signature(
            agent_id, api_key, timestamp, nonce
        )
        assert signature == signature2
    
    @pytest.mark.asyncio
    async def test_authenticate_agent_success(self):
        """测试代理认证成功"""
        websocket = Mock(spec=WebSocket)
        websocket.receive_text = AsyncMock()
        websocket.send_text = AsyncMock()
        
        agent_id = "test_agent"
        api_key = "test_api_key"
        timestamp = datetime.now().isoformat()
        nonce = str(uuid.uuid4())
        
        # 生成正确的签名
        signature = WebSocketAuthenticator._generate_auth_signature(
            agent_id, api_key, timestamp, nonce
        )
        
        auth_message = {
            "type": "auth",
            "data": {
                "agent_id": agent_id,
                "timestamp": timestamp,
                "nonce": nonce,
                "signature": signature,
                "version": "1.0.0"
            }
        }
        
        websocket.receive_text.return_value = json.dumps(auth_message)
        
        # 模拟数据库查询
        mock_agent = Mock()
        mock_agent.api_key = api_key
        
        with patch('management_platform.api.websocket.get_db_session'), \
             patch('management_platform.api.websocket.AgentRepository') as mock_repo_class:
            
            mock_repo = Mock()
            mock_repo.get_agent_by_id = AsyncMock(return_value=mock_agent)
            mock_repo_class.return_value = mock_repo
            
            result = await WebSocketAuthenticator.authenticate_agent(websocket)
            
            # 验证认证成功
            assert result is not None
            assert result["agent_id"] == agent_id
            assert "session_id" in result
            assert "authenticated_at" in result
            
            # 验证发送了成功响应
            websocket.send_text.assert_called_once()
            response = json.loads(websocket.send_text.call_args[0][0])
            assert response["type"] == "auth_response"
            assert response["data"]["success"] is True
    
    @pytest.mark.asyncio
    async def test_authenticate_agent_invalid_message_type(self):
        """测试无效消息类型"""
        websocket = Mock(spec=WebSocket)
        websocket.receive_text = AsyncMock()
        websocket.send_text = AsyncMock()
        
        invalid_message = {
            "type": "invalid_type",
            "data": {}
        }
        
        websocket.receive_text.return_value = json.dumps(invalid_message)
        
        result = await WebSocketAuthenticator.authenticate_agent(websocket)
        
        # 验证认证失败
        assert result is None
        
        # 验证发送了错误响应
        websocket.send_text.assert_called_once()
        response = json.loads(websocket.send_text.call_args[0][0])
        assert response["type"] == "auth_response"
        assert response["data"]["success"] is False
        assert "Invalid message type" in response["data"]["error"]
    
    @pytest.mark.asyncio
    async def test_authenticate_agent_missing_parameters(self):
        """测试缺少认证参数"""
        websocket = Mock(spec=WebSocket)
        websocket.receive_text = AsyncMock()
        websocket.send_text = AsyncMock()
        
        incomplete_message = {
            "type": "auth",
            "data": {
                "agent_id": "test_agent"
                # 缺少其他必需参数
            }
        }
        
        websocket.receive_text.return_value = json.dumps(incomplete_message)
        
        result = await WebSocketAuthenticator.authenticate_agent(websocket)
        
        # 验证认证失败
        assert result is None
        
        # 验证发送了错误响应
        websocket.send_text.assert_called_once()
        response = json.loads(websocket.send_text.call_args[0][0])
        assert response["data"]["success"] is False
        assert "Missing authentication parameters" in response["data"]["error"]
    
    @pytest.mark.asyncio
    async def test_authenticate_agent_expired_timestamp(self):
        """测试过期的时间戳"""
        websocket = Mock(spec=WebSocket)
        websocket.receive_text = AsyncMock()
        websocket.send_text = AsyncMock()
        
        # 使用过期的时间戳（10分钟前）
        expired_timestamp = (datetime.now() - timedelta(minutes=10)).isoformat()
        
        auth_message = {
            "type": "auth",
            "data": {
                "agent_id": "test_agent",
                "timestamp": expired_timestamp,
                "nonce": str(uuid.uuid4()),
                "signature": "dummy_signature"
            }
        }
        
        websocket.receive_text.return_value = json.dumps(auth_message)
        
        result = await WebSocketAuthenticator.authenticate_agent(websocket)
        
        # 验证认证失败
        assert result is None
        
        # 验证发送了错误响应
        websocket.send_text.assert_called_once()
        response = json.loads(websocket.send_text.call_args[0][0])
        assert response["data"]["success"] is False
        assert "timestamp expired" in response["data"]["error"]
    
    @pytest.mark.asyncio
    async def test_authenticate_agent_not_found(self):
        """测试代理不存在"""
        websocket = Mock(spec=WebSocket)
        websocket.receive_text = AsyncMock()
        websocket.send_text = AsyncMock()
        
        auth_message = {
            "type": "auth",
            "data": {
                "agent_id": "nonexistent_agent",
                "timestamp": datetime.now().isoformat(),
                "nonce": str(uuid.uuid4()),
                "signature": "dummy_signature"
            }
        }
        
        websocket.receive_text.return_value = json.dumps(auth_message)
        
        # 模拟代理不存在
        with patch('management_platform.api.websocket.get_db_session'), \
             patch('management_platform.api.websocket.AgentRepository') as mock_repo_class:
            
            mock_repo = Mock()
            mock_repo.get_agent_by_id = AsyncMock(return_value=None)
            mock_repo_class.return_value = mock_repo
            
            result = await WebSocketAuthenticator.authenticate_agent(websocket)
            
            # 验证认证失败
            assert result is None
            
            # 验证发送了错误响应
            websocket.send_text.assert_called_once()
            response = json.loads(websocket.send_text.call_args[0][0])
            assert response["data"]["success"] is False
            assert "Agent not found" in response["data"]["error"]
    
    @pytest.mark.asyncio
    async def test_authenticate_agent_invalid_signature(self):
        """测试无效签名"""
        websocket = Mock(spec=WebSocket)
        websocket.receive_text = AsyncMock()
        websocket.send_text = AsyncMock()
        
        auth_message = {
            "type": "auth",
            "data": {
                "agent_id": "test_agent",
                "timestamp": datetime.now().isoformat(),
                "nonce": str(uuid.uuid4()),
                "signature": "invalid_signature"
            }
        }
        
        websocket.receive_text.return_value = json.dumps(auth_message)
        
        # 模拟数据库查询
        mock_agent = Mock()
        mock_agent.api_key = "test_api_key"
        
        with patch('management_platform.api.websocket.get_db_session'), \
             patch('management_platform.api.websocket.AgentRepository') as mock_repo_class:
            
            mock_repo = Mock()
            mock_repo.get_agent_by_id = AsyncMock(return_value=mock_agent)
            mock_repo_class.return_value = mock_repo
            
            result = await WebSocketAuthenticator.authenticate_agent(websocket)
            
            # 验证认证失败
            assert result is None
            
            # 验证发送了错误响应
            websocket.send_text.assert_called_once()
            response = json.loads(websocket.send_text.call_args[0][0])
            assert response["data"]["success"] is False
            assert "Invalid signature" in response["data"]["error"]
    
    @pytest.mark.asyncio
    async def test_authenticate_agent_timeout(self):
        """测试认证超时"""
        websocket = Mock(spec=WebSocket)
        websocket.receive_text = AsyncMock(side_effect=asyncio.TimeoutError())
        websocket.send_text = AsyncMock()
        
        result = await WebSocketAuthenticator.authenticate_agent(websocket)
        
        # 验证认证失败
        assert result is None
        
        # 验证发送了超时响应
        websocket.send_text.assert_called_once()
        response = json.loads(websocket.send_text.call_args[0][0])
        assert response["data"]["success"] is False
        assert "timeout" in response["data"]["error"]


class TestMessageHandlers:
    """消息处理器测试"""
    
    @pytest.mark.asyncio
    async def test_handle_agent_register(self):
        """测试处理代理注册消息"""
        agent_id = "test_agent"
        message = {
            "type": "agent_register",
            "data": {
                "capabilities": ["icmp", "tcp", "udp"],
                "version": "1.0.0"
            }
        }
        
        with patch('management_platform.api.websocket.get_db_session'), \
             patch('management_platform.api.websocket.AgentRepository') as mock_repo_class, \
             patch('management_platform.api.websocket.connection_manager') as mock_manager:
            
            mock_repo = Mock()
            mock_repo.update_agent_capabilities = AsyncMock()
            mock_repo.update_agent_version = AsyncMock()
            mock_repo_class.return_value = mock_repo
            
            mock_manager.send_message_to_agent = AsyncMock()
            
            await handle_agent_register(agent_id, message)
            
            # 验证数据库更新被调用
            mock_repo.update_agent_capabilities.assert_called_once_with(
                agent_id, ["icmp", "tcp", "udp"]
            )
            mock_repo.update_agent_version.assert_called_once_with(
                agent_id, "1.0.0"
            )
            
            # 验证发送了确认响应
            mock_manager.send_message_to_agent.assert_called_once()
            call_args = mock_manager.send_message_to_agent.call_args
            assert call_args[0][0] == agent_id
            response = call_args[0][1]
            assert response["type"] == "agent_register_response"
            assert response["data"]["success"] is True
    
    @pytest.mark.asyncio
    async def test_handle_task_result(self):
        """测试处理任务结果消息"""
        agent_id = "test_agent"
        task_id = str(uuid.uuid4())
        message = {
            "type": "task_result",
            "data": {
                "task_id": task_id,
                "result": {
                    "status": "success",
                    "metrics": {"latency": 10.5}
                }
            }
        }
        
        with patch('management_platform.api.websocket.connection_manager') as mock_manager:
            mock_manager.send_message_to_agent = AsyncMock()
            
            await handle_task_result(agent_id, message)
            
            # 验证发送了确认响应
            mock_manager.send_message_to_agent.assert_called_once()
            call_args = mock_manager.send_message_to_agent.call_args
            assert call_args[0][0] == agent_id
            response = call_args[0][1]
            assert response["type"] == "task_result_ack"
            assert response["data"]["task_id"] == task_id
            assert response["data"]["received"] is True
    
    @pytest.mark.asyncio
    async def test_handle_resource_report(self):
        """测试处理资源报告消息"""
        agent_id = "test_agent"
        message = {
            "type": "resource_report",
            "data": {
                "resources": {
                    "cpu_usage": 45.2,
                    "memory_usage": 60.1,
                    "disk_usage": 30.5
                }
            }
        }
        
        with patch('management_platform.api.websocket.connection_manager') as mock_manager:
            mock_manager.send_message_to_agent = AsyncMock()
            
            await handle_resource_report(agent_id, message)
            
            # 验证发送了确认响应
            mock_manager.send_message_to_agent.assert_called_once()
            call_args = mock_manager.send_message_to_agent.call_args
            assert call_args[0][0] == agent_id
            response = call_args[0][1]
            assert response["type"] == "resource_report_ack"
            assert response["data"]["received"] is True


if __name__ == "__main__":
    pytest.main([__file__])