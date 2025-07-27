"""WebSocket安全通信模块"""

import json
import ssl
import asyncio
import logging
from typing import Optional, Dict, Any, Callable
from datetime import datetime, timedelta
import websockets
from websockets.server import WebSocketServerProtocol
from websockets.client import WebSocketClientProtocol
from cryptography.fernet import Fernet
import secrets
import hashlib

from .tls import tls_config
from .auth import verify_token, authenticate_api_key

logger = logging.getLogger(__name__)


class SecureWebSocketServer:
    """安全WebSocket服务器"""
    
    def __init__(self, host: str = "localhost", port: int = 8765):
        self.host = host
        self.port = port
        self.ssl_context = tls_config.get_ssl_context(is_server=True)
        self.connected_clients: Dict[str, WebSocketServerProtocol] = {}
        self.message_handlers: Dict[str, Callable] = {}
        self.encryption_key = Fernet.generate_key()
        self.cipher = Fernet(self.encryption_key)
        
    def register_handler(self, message_type: str, handler: Callable):
        """注册消息处理器"""
        self.message_handlers[message_type] = handler
    
    async def authenticate_client(self, websocket: WebSocketServerProtocol, path: str) -> Optional[str]:
        """认证客户端"""
        try:
            # 等待认证消息
            auth_message = await asyncio.wait_for(websocket.recv(), timeout=30.0)
            auth_data = json.loads(auth_message)
            
            if auth_data.get("type") != "auth":
                await websocket.send(json.dumps({
                    "type": "auth_response",
                    "success": False,
                    "error": "Invalid message type"
                }))
                return None
            
            # 验证API密钥或JWT令牌
            token = auth_data.get("token")
            if not token:
                await websocket.send(json.dumps({
                    "type": "auth_response",
                    "success": False,
                    "error": "Missing token"
                }))
                return None
            
            # 这里需要数据库会话，实际使用时需要依赖注入
            # 暂时返回模拟的客户端ID
            client_id = f"client_{secrets.token_hex(8)}"
            
            await websocket.send(json.dumps({
                "type": "auth_response",
                "success": True,
                "client_id": client_id,
                "encryption_key": self.encryption_key.decode('latin-1')
            }))
            
            return client_id
            
        except asyncio.TimeoutError:
            logger.warning("Client authentication timeout")
            return None
        except Exception as e:
            logger.error(f"Authentication error: {e}")
            return None
    
    async def handle_client(self, websocket: WebSocketServerProtocol, path: str):
        """处理客户端连接"""
        client_id = None
        try:
            # 认证客户端
            client_id = await self.authenticate_client(websocket, path)
            if not client_id:
                await websocket.close(code=1008, reason="Authentication failed")
                return
            
            # 添加到连接列表
            self.connected_clients[client_id] = websocket
            logger.info(f"Client {client_id} connected")
            
            # 处理消息
            async for message in websocket:
                try:
                    await self.handle_message(client_id, message)
                except Exception as e:
                    logger.error(f"Error handling message from {client_id}: {e}")
                    await websocket.send(json.dumps({
                        "type": "error",
                        "error": "Message processing failed"
                    }))
                    
        except websockets.exceptions.ConnectionClosed:
            logger.info(f"Client {client_id} disconnected")
        except Exception as e:
            logger.error(f"Error handling client {client_id}: {e}")
        finally:
            if client_id and client_id in self.connected_clients:
                del self.connected_clients[client_id]
    
    async def handle_message(self, client_id: str, message: str):
        """处理客户端消息"""
        try:
            # 解密消息
            decrypted_message = self.cipher.decrypt(message.encode('latin-1')).decode('utf-8')
            data = json.loads(decrypted_message)
            
            message_type = data.get("type")
            if message_type in self.message_handlers:
                await self.message_handlers[message_type](client_id, data)
            else:
                logger.warning(f"Unknown message type: {message_type}")
                
        except Exception as e:
            logger.error(f"Error processing message: {e}")
            raise
    
    async def send_message(self, client_id: str, message: Dict[str, Any]):
        """发送消息给客户端"""
        if client_id not in self.connected_clients:
            logger.warning(f"Client {client_id} not connected")
            return False
        
        try:
            websocket = self.connected_clients[client_id]
            
            # 加密消息
            message_json = json.dumps(message)
            encrypted_message = self.cipher.encrypt(message_json.encode('utf-8'))
            
            await websocket.send(encrypted_message.decode('latin-1'))
            return True
            
        except Exception as e:
            logger.error(f"Error sending message to {client_id}: {e}")
            return False
    
    async def broadcast_message(self, message: Dict[str, Any], exclude_client: Optional[str] = None):
        """广播消息给所有客户端"""
        for client_id in list(self.connected_clients.keys()):
            if exclude_client and client_id == exclude_client:
                continue
            await self.send_message(client_id, message)
    
    async def start_server(self):
        """启动WebSocket服务器"""
        logger.info(f"Starting secure WebSocket server on {self.host}:{self.port}")
        
        # 初始化TLS证书
        tls_config.initialize_certificates()
        
        server = await websockets.serve(
            self.handle_client,
            self.host,
            self.port,
            ssl=self.ssl_context,
            ping_interval=30,
            ping_timeout=10,
            close_timeout=10
        )
        
        logger.info("Secure WebSocket server started")
        return server


class SecureWebSocketClient:
    """安全WebSocket客户端"""
    
    def __init__(self, server_url: str, api_key: str, agent_id: str):
        self.server_url = server_url
        self.api_key = api_key
        self.agent_id = agent_id
        self.websocket: Optional[WebSocketClientProtocol] = None
        self.ssl_context = tls_config.get_ssl_context(is_server=False)
        self.encryption_key: Optional[bytes] = None
        self.cipher: Optional[Fernet] = None
        self.message_handlers: Dict[str, Callable] = {}
        self.heartbeat_task: Optional[asyncio.Task] = None
        self.reconnect_interval = 5
        self.max_reconnect_attempts = 10
        
    def register_handler(self, message_type: str, handler: Callable):
        """注册消息处理器"""
        self.message_handlers[message_type] = handler
    
    async def authenticate(self) -> bool:
        """认证到服务器"""
        try:
            # 发送认证消息
            auth_message = {
                "type": "auth",
                "token": self.api_key,
                "agent_id": self.agent_id,
                "timestamp": datetime.utcnow().isoformat()
            }
            
            await self.websocket.send(json.dumps(auth_message))
            
            # 等待认证响应
            response = await asyncio.wait_for(self.websocket.recv(), timeout=30.0)
            auth_response = json.loads(response)
            
            if auth_response.get("success"):
                # 设置加密密钥
                encryption_key = auth_response.get("encryption_key")
                if encryption_key:
                    self.encryption_key = encryption_key.encode('latin-1')
                    self.cipher = Fernet(self.encryption_key)
                
                logger.info("Authentication successful")
                return True
            else:
                logger.error(f"Authentication failed: {auth_response.get('error')}")
                return False
                
        except Exception as e:
            logger.error(f"Authentication error: {e}")
            return False
    
    async def connect(self) -> bool:
        """连接到服务器"""
        try:
            # 创建WebSocket连接
            self.websocket = await websockets.connect(
                self.server_url,
                ssl=self.ssl_context,
                ping_interval=30,
                ping_timeout=10,
                close_timeout=10
            )
            
            # 认证
            if await self.authenticate():
                # 启动心跳
                self.heartbeat_task = asyncio.create_task(self.heartbeat_loop())
                logger.info("Connected to server")
                return True
            else:
                await self.websocket.close()
                return False
                
        except Exception as e:
            logger.error(f"Connection error: {e}")
            return False
    
    async def disconnect(self):
        """断开连接"""
        if self.heartbeat_task:
            self.heartbeat_task.cancel()
            
        if self.websocket:
            await self.websocket.close()
            self.websocket = None
            
        logger.info("Disconnected from server")
    
    async def send_message(self, message: Dict[str, Any]) -> bool:
        """发送消息到服务器"""
        if not self.websocket or not self.cipher:
            logger.error("Not connected or not authenticated")
            return False
        
        try:
            # 加密消息
            message_json = json.dumps(message)
            encrypted_message = self.cipher.encrypt(message_json.encode('utf-8'))
            
            await self.websocket.send(encrypted_message.decode('latin-1'))
            return True
            
        except Exception as e:
            logger.error(f"Error sending message: {e}")
            return False
    
    async def handle_message(self, message: str):
        """处理服务器消息"""
        try:
            if not self.cipher:
                # 未加密的消息（认证阶段）
                data = json.loads(message)
            else:
                # 解密消息
                decrypted_message = self.cipher.decrypt(message.encode('latin-1')).decode('utf-8')
                data = json.loads(decrypted_message)
            
            message_type = data.get("type")
            if message_type in self.message_handlers:
                await self.message_handlers[message_type](data)
            else:
                logger.warning(f"Unknown message type: {message_type}")
                
        except Exception as e:
            logger.error(f"Error processing message: {e}")
    
    async def listen(self):
        """监听服务器消息"""
        try:
            async for message in self.websocket:
                await self.handle_message(message)
        except websockets.exceptions.ConnectionClosed:
            logger.info("Connection closed by server")
        except Exception as e:
            logger.error(f"Error listening for messages: {e}")
    
    async def heartbeat_loop(self):
        """心跳循环"""
        while True:
            try:
                await asyncio.sleep(30)  # 每30秒发送心跳
                
                heartbeat_message = {
                    "type": "heartbeat",
                    "agent_id": self.agent_id,
                    "timestamp": datetime.utcnow().isoformat()
                }
                
                await self.send_message(heartbeat_message)
                
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Heartbeat error: {e}")
                break
    
    async def connect_with_retry(self) -> bool:
        """带重试的连接"""
        for attempt in range(self.max_reconnect_attempts):
            try:
                if await self.connect():
                    return True
                    
                logger.warning(f"Connection attempt {attempt + 1} failed, retrying in {self.reconnect_interval}s")
                await asyncio.sleep(self.reconnect_interval)
                
            except Exception as e:
                logger.error(f"Connection attempt {attempt + 1} error: {e}")
                await asyncio.sleep(self.reconnect_interval)
        
        logger.error("Max reconnection attempts reached")
        return False


class MessageEncryption:
    """消息加密工具"""
    
    @staticmethod
    def generate_session_key() -> bytes:
        """生成会话密钥"""
        return Fernet.generate_key()
    
    @staticmethod
    def encrypt_message(message: str, key: bytes) -> str:
        """加密消息"""
        cipher = Fernet(key)
        encrypted = cipher.encrypt(message.encode('utf-8'))
        return encrypted.decode('latin-1')
    
    @staticmethod
    def decrypt_message(encrypted_message: str, key: bytes) -> str:
        """解密消息"""
        cipher = Fernet(key)
        decrypted = cipher.decrypt(encrypted_message.encode('latin-1'))
        return decrypted.decode('utf-8')
    
    @staticmethod
    def create_message_hash(message: str) -> str:
        """创建消息哈希"""
        return hashlib.sha256(message.encode('utf-8')).hexdigest()
    
    @staticmethod
    def verify_message_integrity(message: str, expected_hash: str) -> bool:
        """验证消息完整性"""
        actual_hash = MessageEncryption.create_message_hash(message)
        return actual_hash == expected_hash