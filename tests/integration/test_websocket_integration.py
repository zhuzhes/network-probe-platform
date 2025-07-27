"""WebSocket通信集成测试"""

import pytest
import asyncio
import json
import uuid
from datetime import datetime
from typing import Dict, Any, List
from unittest.mock import Mock, patch, AsyncMock, MagicMock

import websockets
from fastapi import FastAPI, WebSocket
from fastapi.testclient import TestClient

# 导入需要测试的模块
from management_platform.api.websocket import ConnectionManager as WebSocketManager
from management_platform.api.connection_manager import AdvancedConnectionManager, ConnectionState
from management_platform.api.message_dispatcher import MessageDispatcher
from agent.core.websocket_client import WebSocketClient
from shared.models.agent import Agent, AgentStatus


class TestWebSocketIntegration:
    """WebSocket集成测试"""
    
    @pytest.fixture
    def mock_websocket(self):
        """模拟WebSocket连接"""
        websocket = Mock()
        websocket.accept = AsyncMock()
        websocket.send_text = AsyncMock()
        websocket.send_bytes = AsyncMock()
        websocket.receive_text = AsyncMock()
        websocket.receive_bytes = AsyncMock()
        websocket.close = AsyncMock()
        return websocket
    
    @pytest.fixture
    def connection_manager(self):
        """创建连接管理器"""
        return AdvancedConnectionManager()
    
    @pytest.fixture
    def message_dispatcher(self):
        """创建消息分发器"""
        return MessageDispatcher()
    
    @pytest.fixture
    def websocket_manager(self, connection_manager, message_dispatcher):
        """创建WebSocket管理器"""
        return WebSocketManager(connection_manager, message_dispatcher)
    
    @pytest.mark.asyncio
    async def test_agent_connection_flow(self, websocket_manager, mock_websocket, connection_manager):
        """测试代理连接流程"""
        agent_id = str(uuid.uuid4())
        
        # 模拟代理连接
        await connection_manager.connect_agent(agent_id, mock_websocket)
        
        # 验证连接状态
        assert connection_manager.is_agent_connected(agent_id)
        assert connection_manager.get_connection_state(agent_id) == ConnectionState.CONNECTED
        
        # 模拟认证消息
        auth_message = {
            "type": "authenticate",
            "agent_id": agent_id,
            "api_key": "test_api_key",
            "version": "1.0.0"
        }
        
        with patch.object(connection_manager, 'authenticate_agent', return_value=True):
            await websocket_manager.handle_message(agent_id, json.dumps(auth_message))
            
            # 验证认证后状态
            assert connection_manager.get_connection_state(agent_id) == ConnectionState.AUTHENTICATED
    
    @pytest.mark.asyncio
    async def test_heartbeat_mechanism(self, connection_manager, mock_websocket):
        """测试心跳机制"""
        agent_id = str(uuid.uuid4())
        
        # 连接代理
        await connection_manager.connect_agent(agent_id, mock_websocket)
        
        # 模拟心跳消息
        heartbeat_message = {
            "type": "heartbeat",
            "timestamp": datetime.utcnow().isoformat(),
            "agent_id": agent_id
        }
        
        # 发送心跳
        await connection_manager.handle_heartbeat(agent_id, heartbeat_message)
        
        # 验证心跳记录
        connection_info = connection_manager.get_connection_info(agent_id)
        assert connection_info is not None
        assert connection_info.last_heartbeat is not None
    
    @pytest.mark.asyncio
    async def test_task_distribution(self, websocket_manager, connection_manager, message_dispatcher, mock_websocket):
        """测试任务分发"""
        agent_id = str(uuid.uuid4())
        
        # 连接并认证代理
        await connection_manager.connect_agent(agent_id, mock_websocket)
        with patch.object(connection_manager, 'authenticate_agent', return_value=True):
            await connection_manager.set_connection_state(agent_id, ConnectionState.AUTHENTICATED)
        
        # 创建测试任务
        task_message = {
            "type": "execute_task",
            "task_id": str(uuid.uuid4()),
            "protocol": "http",
            "target": "example.com",
            "port": 80,
            "parameters": {"method": "GET", "timeout": 30}
        }
        
        # 分发任务
        success = await message_dispatcher.send_task_to_agent(agent_id, task_message)
        
        # 验证任务发送
        assert success
        mock_websocket.send_text.assert_called()
        
        # 验证发送的消息内容
        sent_message = json.loads(mock_websocket.send_text.call_args[0][0])
        assert sent_message["type"] == "execute_task"
        assert sent_message["protocol"] == "http"
        assert sent_message["target"] == "example.com"
    
    @pytest.mark.asyncio
    async def test_task_result_collection(self, websocket_manager, connection_manager, mock_websocket):
        """测试任务结果收集"""
        agent_id = str(uuid.uuid4())
        task_id = str(uuid.uuid4())
        
        # 连接代理
        await connection_manager.connect_agent(agent_id, mock_websocket)
        
        # 模拟任务结果消息
        result_message = {
            "type": "task_result",
            "task_id": task_id,
            "agent_id": agent_id,
            "execution_time": datetime.utcnow().isoformat(),
            "duration": 150.5,
            "status": "success",
            "metrics": {
                "response_time": 100,
                "status_code": 200,
                "response_size": 1024
            },
            "raw_data": {
                "headers": {"content-type": "text/html"},
                "response": "OK"
            }
        }
        
        # 处理结果消息
        with patch.object(websocket_manager, 'handle_task_result') as mock_handle:
            await websocket_manager.handle_message(agent_id, json.dumps(result_message))
            mock_handle.assert_called_once()
    
    @pytest.mark.asyncio
    async def test_resource_monitoring_data(self, websocket_manager, connection_manager, mock_websocket):
        """测试资源监控数据"""
        agent_id = str(uuid.uuid4())
        
        # 连接代理
        await connection_manager.connect_agent(agent_id, mock_websocket)
        
        # 模拟资源监控消息
        resource_message = {
            "type": "resource_report",
            "agent_id": agent_id,
            "timestamp": datetime.utcnow().isoformat(),
            "cpu_usage": 45.5,
            "memory_usage": 60.2,
            "disk_usage": 30.0,
            "network_in": 1024.0,
            "network_out": 2048.0,
            "load_average": 1.5
        }
        
        # 处理资源消息
        with patch.object(websocket_manager, 'handle_resource_report') as mock_handle:
            await websocket_manager.handle_message(agent_id, json.dumps(resource_message))
            mock_handle.assert_called_once()
    
    @pytest.mark.asyncio
    async def test_connection_error_handling(self, connection_manager, mock_websocket):
        """测试连接错误处理"""
        agent_id = str(uuid.uuid4())
        
        # 连接代理
        await connection_manager.connect_agent(agent_id, mock_websocket)
        assert connection_manager.is_agent_connected(agent_id)
        
        # 模拟连接错误
        await connection_manager.handle_connection_error(agent_id, "Connection lost")
        
        # 验证连接状态更新
        assert connection_manager.get_connection_state(agent_id) == ConnectionState.ERROR
    
    @pytest.mark.asyncio
    async def test_agent_disconnection(self, connection_manager, mock_websocket):
        """测试代理断开连接"""
        agent_id = str(uuid.uuid4())
        
        # 连接代理
        await connection_manager.connect_agent(agent_id, mock_websocket)
        assert connection_manager.is_agent_connected(agent_id)
        
        # 断开连接
        await connection_manager.disconnect_agent(agent_id)
        
        # 验证断开状态
        assert not connection_manager.is_agent_connected(agent_id)
        assert connection_manager.get_connection_state(agent_id) == ConnectionState.DISCONNECTED
    
    @pytest.mark.asyncio
    async def test_multiple_agents_connection(self, connection_manager):
        """测试多个代理连接"""
        agent_count = 10
        agent_ids = [str(uuid.uuid4()) for _ in range(agent_count)]
        mock_websockets = [Mock() for _ in range(agent_count)]
        
        # 为每个mock websocket设置异步方法
        for ws in mock_websockets:
            ws.accept = AsyncMock()
            ws.send_text = AsyncMock()
            ws.close = AsyncMock()
        
        # 连接所有代理
        for agent_id, websocket in zip(agent_ids, mock_websockets):
            await connection_manager.connect_agent(agent_id, websocket)
        
        # 验证所有代理都已连接
        for agent_id in agent_ids:
            assert connection_manager.is_agent_connected(agent_id)
        
        # 验证连接统计
        stats = connection_manager.get_connection_statistics()
        assert stats["total_connections"] == agent_count
        assert stats["active_connections"] == agent_count
    
    @pytest.mark.asyncio
    async def test_message_broadcasting(self, message_dispatcher, connection_manager):
        """测试消息广播"""
        agent_count = 5
        agent_ids = [str(uuid.uuid4()) for _ in range(agent_count)]
        mock_websockets = []
        
        # 连接多个代理
        for agent_id in agent_ids:
            mock_websocket = Mock()
            mock_websocket.send_text = AsyncMock()
            mock_websockets.append(mock_websocket)
            await connection_manager.connect_agent(agent_id, mock_websocket)
        
        # 广播消息
        broadcast_message = {
            "type": "system_announcement",
            "message": "System maintenance scheduled",
            "timestamp": datetime.utcnow().isoformat()
        }
        
        await message_dispatcher.broadcast_message(broadcast_message)
        
        # 验证所有代理都收到了消息
        for mock_websocket in mock_websockets:
            mock_websocket.send_text.assert_called()
    
    @pytest.mark.asyncio
    async def test_concurrent_message_handling(self, websocket_manager, connection_manager):
        """测试并发消息处理"""
        agent_id = str(uuid.uuid4())
        mock_websocket = Mock()
        mock_websocket.send_text = AsyncMock()
        
        # 连接代理
        await connection_manager.connect_agent(agent_id, mock_websocket)
        
        # 创建多个并发消息
        messages = []
        for i in range(20):
            message = {
                "type": "heartbeat",
                "agent_id": agent_id,
                "timestamp": datetime.utcnow().isoformat(),
                "sequence": i
            }
            messages.append(json.dumps(message))
        
        # 并发处理消息
        tasks = [
            websocket_manager.handle_message(agent_id, message)
            for message in messages
        ]
        
        # 等待所有消息处理完成
        results = await asyncio.gather(*tasks, return_exceptions=True)
        
        # 验证没有异常
        for result in results:
            assert not isinstance(result, Exception)


class TestWebSocketClientIntegration:
    """WebSocket客户端集成测试"""
    
    @pytest.fixture
    def mock_websocket_client(self):
        """模拟WebSocket客户端"""
        client = Mock(spec=WebSocketClient)
        client.connect = AsyncMock()
        client.disconnect = AsyncMock()
        client.send_message = AsyncMock()
        client.start_heartbeat = AsyncMock()
        client.stop_heartbeat = AsyncMock()
        return client
    
    @pytest.mark.asyncio
    async def test_client_connection_lifecycle(self, mock_websocket_client):
        """测试客户端连接生命周期"""
        # 测试连接
        await mock_websocket_client.connect()
        mock_websocket_client.connect.assert_called_once()
        
        # 测试心跳启动
        await mock_websocket_client.start_heartbeat()
        mock_websocket_client.start_heartbeat.assert_called_once()
        
        # 测试消息发送
        test_message = {"type": "test", "data": "test_data"}
        await mock_websocket_client.send_message(test_message)
        mock_websocket_client.send_message.assert_called_once_with(test_message)
        
        # 测试心跳停止
        await mock_websocket_client.stop_heartbeat()
        mock_websocket_client.stop_heartbeat.assert_called_once()
        
        # 测试断开连接
        await mock_websocket_client.disconnect()
        mock_websocket_client.disconnect.assert_called_once()
    
    @pytest.mark.asyncio
    async def test_client_authentication_flow(self, mock_websocket_client):
        """测试客户端认证流程"""
        agent_id = str(uuid.uuid4())
        api_key = "test_api_key"
        
        # 模拟认证消息
        auth_message = {
            "type": "authenticate",
            "agent_id": agent_id,
            "api_key": api_key,
            "version": "1.0.0",
            "capabilities": ["icmp", "tcp", "udp", "http", "https"]
        }
        
        # 发送认证消息
        await mock_websocket_client.send_message(auth_message)
        mock_websocket_client.send_message.assert_called_with(auth_message)
    
    @pytest.mark.asyncio
    async def test_client_task_execution_flow(self, mock_websocket_client):
        """测试客户端任务执行流程"""
        # 模拟接收任务消息
        task_message = {
            "type": "execute_task",
            "task_id": str(uuid.uuid4()),
            "protocol": "http",
            "target": "httpbin.org",
            "port": 80,
            "parameters": {"method": "GET", "timeout": 30}
        }
        
        # 模拟任务结果
        result_message = {
            "type": "task_result",
            "task_id": task_message["task_id"],
            "status": "success",
            "duration": 125.5,
            "metrics": {"response_time": 100, "status_code": 200},
            "raw_data": {"response": "OK"}
        }
        
        # 发送结果消息
        await mock_websocket_client.send_message(result_message)
        mock_websocket_client.send_message.assert_called_with(result_message)
    
    @pytest.mark.asyncio
    async def test_client_resource_reporting(self, mock_websocket_client):
        """测试客户端资源上报"""
        # 模拟资源数据
        resource_data = {
            "type": "resource_report",
            "timestamp": datetime.utcnow().isoformat(),
            "cpu_usage": 35.5,
            "memory_usage": 55.2,
            "disk_usage": 25.0,
            "network_in": 512.0,
            "network_out": 1024.0,
            "load_average": 0.8
        }
        
        # 发送资源数据
        await mock_websocket_client.send_message(resource_data)
        mock_websocket_client.send_message.assert_called_with(resource_data)
    
    @pytest.mark.asyncio
    async def test_client_error_handling(self, mock_websocket_client):
        """测试客户端错误处理"""
        # 模拟连接错误
        mock_websocket_client.connect.side_effect = ConnectionError("Connection failed")
        
        with pytest.raises(ConnectionError):
            await mock_websocket_client.connect()
        
        # 模拟发送消息错误
        mock_websocket_client.send_message.side_effect = Exception("Send failed")
        
        with pytest.raises(Exception):
            await mock_websocket_client.send_message({"type": "test"})


class TestEndToEndWebSocketFlow:
    """端到端WebSocket流程测试"""
    
    @pytest.mark.asyncio
    async def test_complete_agent_workflow(self):
        """测试完整的代理工作流程"""
        # 这是一个模拟的端到端测试
        # 在实际环境中，这会涉及真实的WebSocket连接
        
        # 1. 代理连接到管理平台
        connection_manager = AdvancedConnectionManager()
        message_dispatcher = MessageDispatcher()
        websocket_manager = WebSocketManager(connection_manager, message_dispatcher)
        
        agent_id = str(uuid.uuid4())
        mock_websocket = Mock()
        mock_websocket.send_text = AsyncMock()
        
        # 2. 建立连接
        await connection_manager.connect_agent(agent_id, mock_websocket)
        assert connection_manager.is_agent_connected(agent_id)
        
        # 3. 代理认证
        with patch.object(connection_manager, 'authenticate_agent', return_value=True):
            await connection_manager.set_connection_state(agent_id, ConnectionState.AUTHENTICATED)
        
        # 4. 发送任务给代理
        task_message = {
            "type": "execute_task",
            "task_id": str(uuid.uuid4()),
            "protocol": "http",
            "target": "example.com",
            "parameters": {"method": "GET"}
        }
        
        success = await message_dispatcher.send_task_to_agent(agent_id, task_message)
        assert success
        
        # 5. 模拟代理返回结果
        result_message = {
            "type": "task_result",
            "task_id": task_message["task_id"],
            "status": "success",
            "duration": 200.0,
            "metrics": {"response_time": 150, "status_code": 200}
        }
        
        with patch.object(websocket_manager, 'handle_task_result') as mock_handle:
            await websocket_manager.handle_message(agent_id, json.dumps(result_message))
            mock_handle.assert_called_once()
        
        # 6. 断开连接
        await connection_manager.disconnect_agent(agent_id)
        assert not connection_manager.is_agent_connected(agent_id)
    
    @pytest.mark.asyncio
    async def test_multiple_agents_concurrent_tasks(self):
        """测试多个代理并发执行任务"""
        connection_manager = AdvancedConnectionManager()
        message_dispatcher = MessageDispatcher()
        
        # 创建多个代理连接
        agent_count = 5
        agent_ids = []
        mock_websockets = []
        
        for i in range(agent_count):
            agent_id = str(uuid.uuid4())
            mock_websocket = Mock()
            mock_websocket.send_text = AsyncMock()
            
            await connection_manager.connect_agent(agent_id, mock_websocket)
            with patch.object(connection_manager, 'authenticate_agent', return_value=True):
                await connection_manager.set_connection_state(agent_id, ConnectionState.AUTHENTICATED)
            
            agent_ids.append(agent_id)
            mock_websockets.append(mock_websocket)
        
        # 并发发送任务给所有代理
        tasks = []
        for i, agent_id in enumerate(agent_ids):
            task_message = {
                "type": "execute_task",
                "task_id": str(uuid.uuid4()),
                "protocol": "http",
                "target": f"example{i}.com",
                "parameters": {"method": "GET"}
            }
            tasks.append(message_dispatcher.send_task_to_agent(agent_id, task_message))
        
        # 等待所有任务发送完成
        results = await asyncio.gather(*tasks)
        
        # 验证所有任务都成功发送
        assert all(results)
        
        # 验证所有代理都收到了任务
        for mock_websocket in mock_websockets:
            mock_websocket.send_text.assert_called()
    
    @pytest.mark.asyncio
    async def test_connection_recovery_scenario(self):
        """测试连接恢复场景"""
        connection_manager = AdvancedConnectionManager()
        agent_id = str(uuid.uuid4())
        
        # 初始连接
        mock_websocket1 = Mock()
        mock_websocket1.send_text = AsyncMock()
        await connection_manager.connect_agent(agent_id, mock_websocket1)
        assert connection_manager.is_agent_connected(agent_id)
        
        # 模拟连接丢失
        await connection_manager.handle_connection_error(agent_id, "Connection lost")
        assert connection_manager.get_connection_state(agent_id) == ConnectionState.ERROR
        
        # 模拟重新连接
        mock_websocket2 = Mock()
        mock_websocket2.send_text = AsyncMock()
        await connection_manager.connect_agent(agent_id, mock_websocket2)
        
        # 验证连接恢复
        assert connection_manager.is_agent_connected(agent_id)
        assert connection_manager.get_connection_state(agent_id) == ConnectionState.CONNECTED