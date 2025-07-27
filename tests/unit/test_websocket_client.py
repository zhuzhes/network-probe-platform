"""WebSocket客户端单元测试"""

import pytest
import asyncio
import json
import ssl
from unittest.mock import AsyncMock, MagicMock, patch
from datetime import datetime

from agent.core.websocket_client import WebSocketClient
from agent.core.logger import AgentLogger


class MockWebSocket:
    """模拟WebSocket连接"""
    
    def __init__(self):
        self.sent_messages = []
        self.received_messages = []
        self.closed = False
        self.close_called = False
        self._recv_event = asyncio.Event()
    
    async def send(self, message):
        """模拟发送消息"""
        if self.closed:
            from websockets.exceptions import ConnectionClosed
            raise ConnectionClosed(None, None)
        self.sent_messages.append(message)
    
    async def recv(self):
        """模拟接收消息"""
        if self.closed:
            from websockets.exceptions import ConnectionClosed
            raise ConnectionClosed(None, None)
        
        # 等待消息或超时
        try:
            await asyncio.wait_for(self._recv_event.wait(), timeout=0.5)
            self._recv_event.clear()
        except asyncio.TimeoutError:
            pass
        
        if self.received_messages:
            return self.received_messages.pop(0)
        
        # 如果没有消息，模拟连接关闭
        self.closed = True
        from websockets.exceptions import ConnectionClosed
        raise ConnectionClosed(None, None)
    
    async def close(self):
        """模拟关闭连接"""
        self.closed = True
        self.close_called = True
        self._recv_event.set()
    
    def add_received_message(self, message):
        """添加要接收的消息"""
        if isinstance(message, dict):
            message = json.dumps(message)
        self.received_messages.append(message)
        self._recv_event.set()
    
    def __await__(self):
        """Make MockWebSocket awaitable for websockets.connect"""
        async def _await():
            return self
        return _await().__await__()
    
    async def __aenter__(self):
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        await self.close()


class TestWebSocketClient:
    """WebSocket客户端测试"""
    
    @pytest.fixture
    def client(self):
        """创建测试用WebSocket客户端"""
        return WebSocketClient(
            server_url="ws://localhost:8000/ws",
            api_key="test-api-key",
            agent_id="test-agent-123"
        )
    
    @pytest.fixture
    def ssl_client(self):
        """创建使用SSL的WebSocket客户端"""
        return WebSocketClient(
            server_url="wss://localhost:8000/ws",
            api_key="test-api-key",
            agent_id="test-agent-123",
            cert_file="/path/to/cert.pem",
            key_file="/path/to/key.pem"
        )
    
    def test_client_init(self, client):
        """测试客户端初始化"""
        assert client.server_url == "ws://localhost:8000/ws"
        assert client.api_key == "test-api-key"
        assert client.agent_id == "test-agent-123"
        assert not client.is_connected
        assert not client.is_authenticated
        assert client.last_heartbeat is None
        assert client.session_id is None
        assert client.missed_heartbeats == 0
    
    def test_register_handler(self, client):
        """测试注册消息处理器"""
        async def test_handler(message):
            pass
        
        client.register_handler("test_message", test_handler)
        assert "test_message" in client._message_handlers
        assert client._message_handlers["test_message"] == test_handler
    
    def test_create_ssl_context_no_ssl(self, client):
        """测试非SSL连接不创建SSL上下文"""
        context = client._create_ssl_context()
        assert context is None
    
    def test_create_ssl_context_with_ssl(self, ssl_client):
        """测试SSL连接创建SSL上下文"""
        with patch('ssl.create_default_context') as mock_create_context:
            mock_context = MagicMock()
            mock_create_context.return_value = mock_context
            
            context = ssl_client._create_ssl_context()
            
            assert context == mock_context
            mock_create_context.assert_called_once()
    
    @pytest.mark.asyncio
    async def test_connect_success(self, client):
        """测试成功连接"""
        mock_websocket = MockWebSocket()
        
        with patch('websockets.connect', return_value=mock_websocket) as mock_connect:
            # 模拟认证响应
            async def add_auth_response():
                await asyncio.sleep(0.1)
                # 找到认证请求并添加响应
                if mock_websocket.sent_messages:
                    for msg_json in mock_websocket.sent_messages:
                        try:
                            msg = json.loads(msg_json)
                            if msg.get("type") == "auth":
                                auth_response = {
                                    "id": msg.get("id"),
                                    "type": "auth_response",
                                    "data": {
                                        "success": True,
                                        "token": "test-token",
                                        "session_id": "test-session-123"
                                    }
                                }
                                mock_websocket.add_received_message(auth_response)
                                break
                        except json.JSONDecodeError:
                            continue
                
                # 模拟注册消息的响应
                mock_websocket.add_received_message({
                    "type": "agent_register_response",
                    "data": {"status": "success"}
                })
            
            # 启动响应任务
            response_task = asyncio.create_task(add_auth_response())
            
            result = await client.connect()
            
            await response_task
            
            assert result is True
            assert client.is_connected
            assert client.is_authenticated
            assert client.session_id == "test-session-123"
            mock_connect.assert_called_once()
            
            # 检查连接参数
            call_args = mock_connect.call_args
            assert call_args[0][0] == "ws://localhost:8000/ws"
            assert "Authorization" in call_args[1]["extra_headers"]
            assert "X-Agent-ID" in call_args[1]["extra_headers"]
            
            # 清理
            await client.disconnect()
    
    @pytest.mark.asyncio
    async def test_connect_failure(self, client):
        """测试连接失败"""
        with patch('websockets.connect', side_effect=Exception("Connection failed")):
            result = await client.connect()
            
            assert result is False
            assert not client.is_connected
    
    @pytest.mark.asyncio
    async def test_disconnect(self, client):
        """测试断开连接"""
        mock_websocket = MockWebSocket()
        
        with patch('websockets.connect', return_value=mock_websocket):
            # 模拟认证成功
            async def mock_auth():
                await asyncio.sleep(0.1)
                if mock_websocket.sent_messages:
                    for msg_json in mock_websocket.sent_messages:
                        try:
                            msg = json.loads(msg_json)
                            if msg.get("type") == "auth":
                                auth_response = {
                                    "id": msg.get("id"),
                                    "type": "auth_response",
                                    "data": {
                                        "success": True,
                                        "token": "test-token",
                                        "session_id": "test-session-123"
                                    }
                                }
                                mock_websocket.add_received_message(auth_response)
                                break
                        except json.JSONDecodeError:
                            continue
            
            auth_task = asyncio.create_task(mock_auth())
            await client.connect()
            await auth_task
            
            assert client.is_connected
            assert client.is_authenticated
            
            await client.disconnect()
            assert not client.is_connected
            assert not client.is_authenticated
            assert client.session_id is None
            assert mock_websocket.close_called
    
    @pytest.mark.asyncio
    async def test_send_message_success(self, client):
        """测试成功发送消息"""
        mock_websocket = MockWebSocket()
        
        with patch('websockets.connect', return_value=mock_websocket):
            # 模拟认证成功
            async def mock_auth():
                await asyncio.sleep(0.1)
                if mock_websocket.sent_messages:
                    for msg_json in mock_websocket.sent_messages:
                        try:
                            msg = json.loads(msg_json)
                            if msg.get("type") == "auth":
                                auth_response = {
                                    "id": msg.get("id"),
                                    "type": "auth_response",
                                    "data": {
                                        "success": True,
                                        "token": "test-token",
                                        "session_id": "test-session"
                                    }
                                }
                                mock_websocket.add_received_message(auth_response)
                                break
                        except json.JSONDecodeError:
                            continue
            
            auth_task = asyncio.create_task(mock_auth())
            await client.connect()
            await auth_task
            
            message = {"type": "test", "data": {"key": "value"}}
            result = await client.send_message(message)
            
            assert result is True
            assert len(mock_websocket.sent_messages) >= 1  # 包括认证和注册消息
            
            # 检查发送的消息
            sent_message = json.loads(mock_websocket.sent_messages[-1])
            assert sent_message["type"] == "test"
            assert sent_message["data"] == {"key": "value"}
            assert "id" in sent_message
            assert "timestamp" in sent_message
            
            await client.disconnect()
    
    @pytest.mark.asyncio
    async def test_send_message_not_connected(self, client):
        """测试未连接时发送消息"""
        message = {"type": "test", "data": {"key": "value"}}
        result = await client.send_message(message)
        
        assert result is False
    
    @pytest.mark.asyncio
    async def test_send_request_success(self, client):
        """测试成功发送请求并接收响应"""
        mock_websocket = MockWebSocket()
        
        with patch('websockets.connect', return_value=mock_websocket):
            await client.connect()
            
            # 准备响应消息
            request_message = {"type": "test_request", "data": {"key": "value"}}
            
            # 在发送请求后添加响应消息
            async def send_and_respond():
                result = await client.send_request(request_message, timeout=1.0)
                return result
            
            # 启动请求任务
            request_task = asyncio.create_task(send_and_respond())
            
            # 等待一小段时间让请求发送
            await asyncio.sleep(0.1)
            
            # 找到请求ID并添加响应
            if mock_websocket.sent_messages:
                sent_message = json.loads(mock_websocket.sent_messages[-1])
                request_id = sent_message.get("id")
                
                response_message = {
                    "id": request_id,
                    "type": "test_response",
                    "data": {"result": "success"}
                }
                mock_websocket.add_received_message(response_message)
            
            # 等待请求完成
            response = await request_task
            
            assert response is not None
            assert response["type"] == "test_response"
            assert response["data"]["result"] == "success"
            
            await client.disconnect()
    
    @pytest.mark.asyncio
    async def test_send_request_timeout(self, client):
        """测试请求超时"""
        mock_websocket = MockWebSocket()
        
        with patch('websockets.connect', return_value=mock_websocket):
            await client.connect()
            
            request_message = {"type": "test_request", "data": {"key": "value"}}
            response = await client.send_request(request_message, timeout=0.1)
            
            assert response is None
            
            await client.disconnect()
    
    @pytest.mark.asyncio
    async def test_message_handling(self, client):
        """测试消息处理"""
        mock_websocket = MockWebSocket()
        handler_called = False
        received_message = None
        
        async def test_handler(message):
            nonlocal handler_called, received_message
            handler_called = True
            received_message = message
        
        client.register_handler("test_message", test_handler)
        
        with patch('websockets.connect', return_value=mock_websocket):
            await client.connect()
            
            # 添加测试消息
            test_message = {
                "type": "test_message",
                "data": {"key": "value"}
            }
            mock_websocket.add_received_message(test_message)
            
            # 等待消息处理
            await asyncio.sleep(0.2)
            
            assert handler_called
            assert received_message["type"] == "test_message"
            assert received_message["data"]["key"] == "value"
            
            await client.disconnect()
    
    @pytest.mark.asyncio
    async def test_heartbeat_handling(self, client):
        """测试心跳处理"""
        mock_websocket = MockWebSocket()
        
        with patch('websockets.connect', return_value=mock_websocket):
            await client.connect()
            
            # 添加心跳响应消息
            heartbeat_response = {
                "type": "heartbeat_response",
                "data": {"status": "ok"}
            }
            mock_websocket.add_received_message(heartbeat_response)
            
            # 等待心跳处理
            await asyncio.sleep(0.2)
            
            assert client.last_heartbeat is not None
            
            await client.disconnect()
    
    @pytest.mark.asyncio
    async def test_reconnect_success(self, client):
        """测试成功重连"""
        mock_websocket = MockWebSocket()
        
        with patch('websockets.connect', return_value=mock_websocket):
            # 首次连接
            await client.connect()
            assert client.is_connected
            
            # 模拟连接断开
            await client.disconnect()
            assert not client.is_connected
            
            # 重连
            result = await client.reconnect()
            assert result is True
            assert client.is_connected
            
            await client.disconnect()
    
    @pytest.mark.asyncio
    async def test_reconnect_max_attempts(self, client):
        """测试重连达到最大次数"""
        # 设置较小的最大重连次数
        client._max_reconnect_attempts = 2
        
        with patch('websockets.connect', side_effect=Exception("Connection failed")):
            # 第一次重连
            result = await client.reconnect()
            assert result is False
            assert client._reconnect_attempts == 1
            
            # 第二次重连
            result = await client.reconnect()
            assert result is False
            assert client._reconnect_attempts == 2
            
            # 第三次重连应该失败（达到最大次数）
            result = await client.reconnect()
            assert result is False
    
    def test_set_heartbeat_interval(self, client):
        """测试设置心跳间隔"""
        client.set_heartbeat_interval(60)
        assert client._heartbeat_interval == 60
    
    def test_set_heartbeat_timeout(self, client):
        """测试设置心跳超时时间"""
        client.set_heartbeat_timeout(120)
        assert client._heartbeat_timeout == 120
    
    def test_generate_auth_signature(self, client):
        """测试生成认证签名"""
        timestamp = "2023-01-01T00:00:00"
        nonce = "test-nonce"
        signature = client._generate_auth_signature(timestamp, nonce)
        
        # 验证签名格式
        assert isinstance(signature, str)
        assert len(signature) == 64  # SHA256 hex digest length
        
        # 验证签名一致性
        signature2 = client._generate_auth_signature(timestamp, nonce)
        assert signature == signature2
    
    def test_get_connection_stats(self, client):
        """测试获取连接统计信息"""
        stats = client.get_connection_stats()
        
        assert "connected" in stats
        assert "authenticated" in stats
        assert "session_id" in stats
        assert "last_heartbeat" in stats
        assert "last_heartbeat_sent" in stats
        assert "missed_heartbeats" in stats
        assert "reconnect_attempts" in stats
        assert "heartbeat_interval" in stats
        assert "heartbeat_timeout" in stats
        
        assert stats["connected"] is False
        assert stats["authenticated"] is False
        assert stats["missed_heartbeats"] == 0
    
    @pytest.mark.asyncio
    async def test_authentication_success(self, client):
        """测试认证成功"""
        mock_websocket = MockWebSocket()
        
        with patch('websockets.connect', return_value=mock_websocket):
            # 启动连接任务
            connect_task = asyncio.create_task(client.connect())
            
            # 等待认证请求
            await asyncio.sleep(0.1)
            
            # 找到认证请求并添加成功响应
            if mock_websocket.sent_messages:
                for msg_json in mock_websocket.sent_messages:
                    try:
                        msg = json.loads(msg_json)
                        if msg.get("type") == "auth":
                            auth_response = {
                                "id": msg.get("id"),
                                "type": "auth_response",
                                "data": {
                                    "success": True,
                                    "token": "test-auth-token",
                                    "session_id": "session-123"
                                }
                            }
                            mock_websocket.add_received_message(auth_response)
                            break
                    except json.JSONDecodeError:
                        continue
            
            # 等待连接完成
            result = await connect_task
            
            assert result is True
            assert client.is_authenticated
            assert client.session_id == "session-123"
            
            await client.disconnect()
    
    @pytest.mark.asyncio
    async def test_authentication_failure(self, client):
        """测试认证失败"""
        mock_websocket = MockWebSocket()
        
        with patch('websockets.connect', return_value=mock_websocket):
            # 启动连接任务
            connect_task = asyncio.create_task(client.connect())
            
            # 等待认证请求
            await asyncio.sleep(0.1)
            
            # 找到认证请求并添加失败响应
            if mock_websocket.sent_messages:
                for msg_json in mock_websocket.sent_messages:
                    try:
                        msg = json.loads(msg_json)
                        if msg.get("type") == "auth":
                            auth_response = {
                                "id": msg.get("id"),
                                "type": "auth_response",
                                "data": {
                                    "success": False,
                                    "error": "Invalid credentials"
                                }
                            }
                            mock_websocket.add_received_message(auth_response)
                            break
                    except json.JSONDecodeError:
                        continue
            
            # 等待连接完成
            result = await connect_task
            
            assert result is False
            assert not client.is_authenticated
            assert client.session_id is None
    
    @pytest.mark.asyncio
    async def test_enhanced_heartbeat(self, client):
        """测试增强的心跳机制"""
        mock_websocket = MockWebSocket()
        
        with patch('websockets.connect', return_value=mock_websocket):
            # 模拟认证成功
            async def mock_auth_and_heartbeat():
                await asyncio.sleep(0.1)
                
                # 处理认证
                if mock_websocket.sent_messages:
                    for msg_json in mock_websocket.sent_messages:
                        try:
                            msg = json.loads(msg_json)
                            if msg.get("type") == "auth":
                                auth_response = {
                                    "id": msg.get("id"),
                                    "type": "auth_response",
                                    "data": {
                                        "success": True,
                                        "token": "test-token",
                                        "session_id": "test-session"
                                    }
                                }
                                mock_websocket.add_received_message(auth_response)
                                break
                        except json.JSONDecodeError:
                            continue
                
                # 等待心跳消息
                await asyncio.sleep(0.2)
                
                # 处理心跳响应
                for msg_json in mock_websocket.sent_messages:
                    try:
                        msg = json.loads(msg_json)
                        if msg.get("type") == "heartbeat":
                            heartbeat_response = {
                                "type": "heartbeat_response",
                                "data": {"status": "ok"}
                            }
                            mock_websocket.add_received_message(heartbeat_response)
                            break
                    except json.JSONDecodeError:
                        continue
            
            # 设置较短的心跳间隔用于测试
            client.set_heartbeat_interval(1)
            
            response_task = asyncio.create_task(mock_auth_and_heartbeat())
            
            await client.connect()
            await response_task
            
            # 等待心跳处理
            await asyncio.sleep(0.5)
            
            assert client.is_connected
            assert client.is_authenticated
            assert client.last_heartbeat is not None
            assert client.missed_heartbeats == 0
            
            await client.disconnect()


class TestWebSocketClientIntegration:
    """WebSocket客户端集成测试"""
    
    @pytest.mark.asyncio
    async def test_full_lifecycle(self):
        """测试完整生命周期"""
        client = WebSocketClient(
            server_url="ws://localhost:8000/ws",
            api_key="test-api-key",
            agent_id="test-agent-123"
        )
        
        mock_websocket = MockWebSocket()
        
        # 注册消息处理器
        messages_received = []
        
        async def message_handler(message):
            messages_received.append(message)
        
        client.register_handler("test_message", message_handler)
        
        with patch('websockets.connect', return_value=mock_websocket):
            # 连接
            result = await client.connect()
            assert result is True
            assert client.is_connected
            
            # 发送消息
            test_message = {"type": "test", "data": {"key": "value"}}
            result = await client.send_message(test_message)
            assert result is True
            
            # 接收消息
            received_message = {
                "type": "test_message",
                "data": {"response": "ok"}
            }
            mock_websocket.add_received_message(received_message)
            
            # 等待消息处理
            await asyncio.sleep(0.2)
            
            assert len(messages_received) == 1
            assert messages_received[0]["type"] == "test_message"
            
            # 断开连接
            await client.disconnect()
            assert not client.is_connected
    
    @pytest.mark.asyncio
    async def test_error_handling(self):
        """测试错误处理"""
        client = WebSocketClient(
            server_url="ws://localhost:8000/ws",
            api_key="test-api-key",
            agent_id="test-agent-123"
        )
        
        # 测试连接失败
        with patch('websockets.connect', side_effect=Exception("Connection failed")):
            result = await client.connect()
            assert result is False
            assert not client.is_connected
        
        # 测试消息处理异常
        mock_websocket = MockWebSocket()
        
        async def failing_handler(message):
            raise Exception("Handler failed")
        
        client.register_handler("test_message", failing_handler)
        
        with patch('websockets.connect', return_value=mock_websocket):
            await client.connect()
            
            # 发送会导致处理器失败的消息
            failing_message = {
                "type": "test_message",
                "data": {"key": "value"}
            }
            mock_websocket.add_received_message(failing_message)
            
            # 等待消息处理（应该不会崩溃）
            await asyncio.sleep(0.2)
            
            # 客户端应该仍然连接
            assert client.is_connected
            
            await client.disconnect()