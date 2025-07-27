"""WebSocket客户端模块"""

import asyncio
import json
import ssl
import uuid
import hashlib
import hmac
from typing import Optional, Dict, Any, Callable, Awaitable
from datetime import datetime, timedelta
import websockets
try:
    from websockets.exceptions import ConnectionClosed, InvalidStatusCode, InvalidHandshake
except ImportError:
    # Fallback for newer websockets versions
    from websockets.exceptions import ConnectionClosed
    InvalidStatusCode = ConnectionClosed
    InvalidHandshake = ConnectionClosed

from .logger import AgentLogger
from shared.security.tls import tls_config


class WebSocketClient:
    """WebSocket客户端"""
    
    def __init__(
        self,
        server_url: str,
        api_key: str,
        agent_id: str,
        cert_file: Optional[str] = None,
        key_file: Optional[str] = None,
        logger: Optional[AgentLogger] = None
    ):
        """
        初始化WebSocket客户端
        
        Args:
            server_url: 服务器WebSocket URL
            api_key: API密钥
            agent_id: 代理ID
            cert_file: 客户端证书文件路径
            key_file: 客户端私钥文件路径
            logger: 日志器
        """
        self.server_url = server_url
        self.api_key = api_key
        self.agent_id = agent_id
        self.cert_file = cert_file
        self.key_file = key_file
        self.logger = logger or AgentLogger("websocket_client")
        
        # 连接状态
        self._websocket: Optional[websockets.WebSocketServerProtocol] = None
        self._connected = False
        self._reconnect_attempts = 0
        self._max_reconnect_attempts = 10
        self._reconnect_delay = 5  # 秒
        
        # 消息处理
        self._message_handlers: Dict[str, Callable[[Dict[str, Any]], Awaitable[None]]] = {}
        self._pending_responses: Dict[str, asyncio.Future] = {}
        
        # 心跳
        self._last_heartbeat = None
        self._last_heartbeat_sent = None
        self._heartbeat_task: Optional[asyncio.Task] = None
        self._heartbeat_interval = 30  # 秒
        self._heartbeat_timeout = 60  # 心跳超时时间
        self._missed_heartbeats = 0
        self._max_missed_heartbeats = 3
        
        # 任务管理
        self._tasks: Dict[str, asyncio.Task] = {}
        
        # 认证和安全
        self._authenticated = False
        self._auth_token: Optional[str] = None
        self._session_id: Optional[str] = None
    
    def register_handler(self, message_type: str, handler: Callable[[Dict[str, Any]], Awaitable[None]]):
        """
        注册消息处理器
        
        Args:
            message_type: 消息类型
            handler: 处理器函数
        """
        self._message_handlers[message_type] = handler
        self.logger.debug(f"已注册消息处理器: {message_type}")
    
    def _generate_auth_signature(self, timestamp: str, nonce: str) -> str:
        """
        生成认证签名
        
        Args:
            timestamp: 时间戳
            nonce: 随机数
            
        Returns:
            认证签名
        """
        message = f"{self.agent_id}:{timestamp}:{nonce}"
        signature = hmac.new(
            self.api_key.encode('utf-8'),
            message.encode('utf-8'),
            hashlib.sha256
        ).hexdigest()
        return signature
    
    async def _authenticate(self) -> bool:
        """
        执行认证流程
        
        Returns:
            认证是否成功
        """
        try:
            # 生成认证数据
            timestamp = datetime.now().isoformat()
            nonce = str(uuid.uuid4())
            signature = self._generate_auth_signature(timestamp, nonce)
            
            # 发送认证消息
            auth_message = {
                "type": "auth",
                "data": {
                    "agent_id": self.agent_id,
                    "timestamp": timestamp,
                    "nonce": nonce,
                    "signature": signature,
                    "version": "1.0.0"
                }
            }
            
            # 发送认证请求并等待响应
            response = await self.send_request(auth_message, timeout=30.0)
            
            if response and response.get("type") == "auth_response":
                auth_data = response.get("data", {})
                if auth_data.get("success"):
                    self._authenticated = True
                    self._auth_token = auth_data.get("token")
                    self._session_id = auth_data.get("session_id")
                    self.logger.info("认证成功")
                    return True
                else:
                    error_msg = auth_data.get("error", "Unknown error")
                    self.logger.error(f"认证失败: {error_msg}")
                    return False
            else:
                self.logger.error("认证响应格式错误")
                return False
                
        except Exception as e:
            self.logger.error(f"认证过程中发生异常: {e}")
            return False
    
    def _create_ssl_context(self) -> Optional[ssl.SSLContext]:
        """创建SSL上下文"""
        if not self.server_url.startswith('wss://'):
            return None
        
        try:
            # 使用TLS配置创建安全的SSL上下文
            context = tls_config.get_ssl_context(is_server=False)
            
            # 如果提供了客户端证书，配置双向认证
            if self.cert_file and self.key_file:
                try:
                    context.load_cert_chain(self.cert_file, self.key_file)
                    self.logger.info("已加载客户端证书进行双向认证")
                except Exception as e:
                    self.logger.error(f"加载客户端证书失败: {e}")
                    raise
            
            # 设置安全的TLS配置
            context.minimum_version = ssl.TLSVersion.TLSv1_2
            context.set_ciphers('ECDHE+AESGCM:ECDHE+CHACHA20:DHE+AESGCM:DHE+CHACHA20:!aNULL:!MD5:!DSS')
            
            return context
            
        except Exception as e:
            self.logger.error(f"创建SSL上下文失败: {e}")
            # 回退到默认SSL上下文
            context = ssl.create_default_context()
            if self.cert_file and self.key_file:
                try:
                    context.load_cert_chain(self.cert_file, self.key_file)
                except Exception as cert_e:
                    self.logger.error(f"加载客户端证书失败: {cert_e}")
                    raise
            return context
    
    async def connect(self) -> bool:
        """
        连接到服务器
        
        Returns:
            连接是否成功
        """
        if self._connected:
            self.logger.warning("WebSocket已经连接")
            return True
        
        try:
            self.logger.info(f"正在连接到服务器: {self.server_url}")
            
            # 创建SSL上下文
            ssl_context = self._create_ssl_context()
            
            # 准备连接头部，包含认证信息
            headers = {
                "Authorization": f"Bearer {self.api_key}",
                "X-Agent-ID": self.agent_id,
                "User-Agent": "NetworkProbeAgent/1.0"
            }
            
            # 建立WebSocket连接
            self._websocket = await websockets.connect(
                self.server_url,
                ssl=ssl_context,
                extra_headers=headers,
                ping_interval=20,
                ping_timeout=10,
                close_timeout=10
            )
            
            self._connected = True
            self._reconnect_attempts = 0
            self.logger.info("WebSocket连接建立成功")
            
            # 启动消息接收任务
            self._tasks["message_receiver"] = asyncio.create_task(
                self._message_receiver(),
                name="message_receiver"
            )
            
            # 执行认证
            if not await self._authenticate():
                self.logger.error("认证失败，关闭连接")
                await self.disconnect()
                return False
            
            # 启动心跳任务
            self._tasks["heartbeat"] = asyncio.create_task(
                self._heartbeat_sender(),
                name="heartbeat"
            )
            
            # 启动心跳监控任务
            self._tasks["heartbeat_monitor"] = asyncio.create_task(
                self._heartbeat_monitor(),
                name="heartbeat_monitor"
            )
            
            # 发送初始注册消息
            await self._send_registration()
            
            return True
            
        except (ConnectionClosed, InvalidStatusCode, InvalidHandshake) as e:
            self.logger.error(f"WebSocket连接失败: {e}")
            self._connected = False
            return False
        except Exception as e:
            self.logger.error(f"连接过程中发生异常: {e}")
            self._connected = False
            return False
    
    async def disconnect(self):
        """断开连接"""
        if not self._connected:
            return
        
        self.logger.info("正在断开WebSocket连接...")
        self._connected = False
        self._authenticated = False
        self._auth_token = None
        self._session_id = None
        
        # 取消所有任务
        for task_name, task in self._tasks.items():
            if not task.done():
                self.logger.debug(f"取消任务: {task_name}")
                task.cancel()
                try:
                    await task
                except asyncio.CancelledError:
                    pass
                except Exception as e:
                    self.logger.error(f"停止任务 {task_name} 时出错: {e}")
        
        self._tasks.clear()
        
        # 关闭WebSocket连接
        if self._websocket:
            try:
                await self._websocket.close()
            except Exception as e:
                self.logger.error(f"关闭WebSocket连接时出错: {e}")
            finally:
                self._websocket = None
        
        # 清理待处理的响应
        for future in self._pending_responses.values():
            if not future.done():
                future.cancel()
        self._pending_responses.clear()
        
        self.logger.info("WebSocket连接已断开")
    
    async def _send_registration(self):
        """发送代理注册消息"""
        registration_msg = {
            "type": "agent_register",
            "data": {
                "agent_id": self.agent_id,
                "timestamp": datetime.now().isoformat(),
                "capabilities": ["icmp", "tcp", "udp", "http", "https"],
                "version": "1.0.0"
            }
        }
        
        await self.send_message(registration_msg)
        self.logger.info("已发送代理注册消息")
    
    async def send_message(self, message: Dict[str, Any]) -> bool:
        """
        发送消息
        
        Args:
            message: 要发送的消息
            
        Returns:
            发送是否成功
        """
        if not self._connected or not self._websocket:
            self.logger.error("WebSocket未连接，无法发送消息")
            return False
        
        try:
            # 添加消息ID和时间戳
            if "id" not in message:
                message["id"] = str(uuid.uuid4())
            if "timestamp" not in message:
                message["timestamp"] = datetime.now().isoformat()
            
            message_json = json.dumps(message, ensure_ascii=False)
            await self._websocket.send(message_json)
            
            self.logger.debug(f"已发送消息: {message.get('type', 'unknown')}")
            return True
            
        except ConnectionClosed:
            self.logger.error("连接已关闭，无法发送消息")
            self._connected = False
            return False
        except Exception as e:
            self.logger.error(f"发送消息失败: {e}")
            return False
    
    async def send_request(self, message: Dict[str, Any], timeout: float = 30.0) -> Optional[Dict[str, Any]]:
        """
        发送请求并等待响应
        
        Args:
            message: 请求消息
            timeout: 超时时间（秒）
            
        Returns:
            响应消息，如果超时或失败则返回None
        """
        if not self._connected:
            self.logger.error("WebSocket未连接，无法发送请求")
            return None
        
        # 生成请求ID
        request_id = str(uuid.uuid4())
        message["id"] = request_id
        
        # 创建Future等待响应
        response_future = asyncio.Future()
        self._pending_responses[request_id] = response_future
        
        try:
            # 发送请求
            if not await self.send_message(message):
                return None
            
            # 等待响应
            response = await asyncio.wait_for(response_future, timeout=timeout)
            return response
            
        except asyncio.TimeoutError:
            self.logger.error(f"请求超时: {message.get('type', 'unknown')}")
            return None
        except Exception as e:
            self.logger.error(f"发送请求失败: {e}")
            return None
        finally:
            # 清理
            self._pending_responses.pop(request_id, None)
    
    async def _message_receiver(self):
        """消息接收循环"""
        self.logger.info("消息接收器已启动")
        
        try:
            while self._connected and self._websocket:
                try:
                    # 接收消息
                    message_json = await self._websocket.recv()
                    
                    # 解析消息
                    try:
                        message = json.loads(message_json)
                    except json.JSONDecodeError as e:
                        self.logger.error(f"消息JSON解析失败: {e}")
                        continue
                    
                    # 处理消息
                    await self._handle_message(message)
                    
                except ConnectionClosed:
                    self.logger.warning("WebSocket连接已关闭")
                    self._connected = False
                    break
                except Exception as e:
                    self.logger.error(f"接收消息时发生异常: {e}")
                    continue
                    
        except asyncio.CancelledError:
            self.logger.info("消息接收器被取消")
        except Exception as e:
            self.logger.error(f"消息接收器异常: {e}")
        finally:
            self.logger.info("消息接收器已停止")
    
    async def _handle_message(self, message: Dict[str, Any]):
        """
        处理接收到的消息
        
        Args:
            message: 接收到的消息
        """
        message_type = message.get("type")
        message_id = message.get("id")
        
        self.logger.debug(f"收到消息: {message_type}")
        
        # 检查是否是对之前请求的响应
        if message_id and message_id in self._pending_responses:
            future = self._pending_responses[message_id]
            if not future.done():
                future.set_result(message)
            return
        
        # 处理心跳响应
        if message_type == "heartbeat_response":
            self._last_heartbeat = datetime.now()
            self._missed_heartbeats = 0  # 重置丢失心跳计数
            self.logger.debug("收到心跳响应")
            return
        
        # 查找并调用消息处理器
        if message_type in self._message_handlers:
            try:
                await self._message_handlers[message_type](message)
            except Exception as e:
                self.logger.error(f"处理消息 {message_type} 时发生异常: {e}")
        else:
            self.logger.warning(f"未找到消息类型 {message_type} 的处理器")
    
    async def _heartbeat_sender(self):
        """心跳发送器"""
        self.logger.info("心跳发送器已启动")
        
        try:
            while self._connected and self._authenticated:
                # 发送心跳
                heartbeat_msg = {
                    "type": "heartbeat",
                    "data": {
                        "agent_id": self.agent_id,
                        "session_id": self._session_id,
                        "timestamp": datetime.now().isoformat()
                    }
                }
                
                if await self.send_message(heartbeat_msg):
                    self._last_heartbeat_sent = datetime.now()
                    self.logger.debug("已发送心跳")
                else:
                    self.logger.error("心跳发送失败")
                    self._missed_heartbeats += 1
                
                # 等待下次心跳
                await asyncio.sleep(self._heartbeat_interval)
                
        except asyncio.CancelledError:
            self.logger.info("心跳发送器被取消")
        except Exception as e:
            self.logger.error(f"心跳发送器异常: {e}")
        finally:
            self.logger.info("心跳发送器已停止")
    
    async def _heartbeat_monitor(self):
        """心跳监控器"""
        self.logger.info("心跳监控器已启动")
        
        try:
            while self._connected and self._authenticated:
                await asyncio.sleep(self._heartbeat_interval)
                
                # 检查心跳超时
                if self._last_heartbeat_sent:
                    time_since_last_sent = datetime.now() - self._last_heartbeat_sent
                    if time_since_last_sent.total_seconds() > self._heartbeat_timeout:
                        self._missed_heartbeats += 1
                        self.logger.warning(f"心跳超时，已丢失 {self._missed_heartbeats} 次心跳")
                
                # 检查是否需要重连
                if self._missed_heartbeats >= self._max_missed_heartbeats:
                    self.logger.error(f"连续丢失 {self._missed_heartbeats} 次心跳，连接可能已断开")
                    self._connected = False
                    break
                    
        except asyncio.CancelledError:
            self.logger.info("心跳监控器被取消")
        except Exception as e:
            self.logger.error(f"心跳监控器异常: {e}")
        finally:
            self.logger.info("心跳监控器已停止")
    
    async def reconnect(self) -> bool:
        """
        重新连接
        
        Returns:
            重连是否成功
        """
        if self._reconnect_attempts >= self._max_reconnect_attempts:
            self.logger.error(f"重连次数已达上限 ({self._max_reconnect_attempts})")
            return False
        
        self._reconnect_attempts += 1
        self.logger.info(f"尝试重新连接 (第 {self._reconnect_attempts} 次)")
        
        # 先断开现有连接
        await self.disconnect()
        
        # 等待一段时间后重连
        await asyncio.sleep(self._reconnect_delay)
        
        # 尝试连接
        return await self.connect()
    
    @property
    def is_connected(self) -> bool:
        """检查是否已连接"""
        return self._connected
    
    @property
    def is_authenticated(self) -> bool:
        """检查是否已认证"""
        return self._authenticated
    
    @property
    def last_heartbeat(self) -> Optional[datetime]:
        """获取最后一次心跳时间"""
        return self._last_heartbeat
    
    @property
    def last_heartbeat_sent(self) -> Optional[datetime]:
        """获取最后一次发送心跳时间"""
        return self._last_heartbeat_sent
    
    @property
    def missed_heartbeats(self) -> int:
        """获取丢失的心跳次数"""
        return self._missed_heartbeats
    
    @property
    def session_id(self) -> Optional[str]:
        """获取会话ID"""
        return self._session_id
    
    def set_heartbeat_interval(self, interval: int):
        """设置心跳间隔"""
        self._heartbeat_interval = interval
        self.logger.info(f"心跳间隔已设置为 {interval} 秒")
    
    def set_heartbeat_timeout(self, timeout: int):
        """设置心跳超时时间"""
        self._heartbeat_timeout = timeout
        self.logger.info(f"心跳超时时间已设置为 {timeout} 秒")
    
    def get_connection_stats(self) -> Dict[str, Any]:
        """获取连接统计信息"""
        return {
            "connected": self._connected,
            "authenticated": self._authenticated,
            "session_id": self._session_id,
            "last_heartbeat": self._last_heartbeat.isoformat() if self._last_heartbeat else None,
            "last_heartbeat_sent": self._last_heartbeat_sent.isoformat() if self._last_heartbeat_sent else None,
            "missed_heartbeats": self._missed_heartbeats,
            "reconnect_attempts": self._reconnect_attempts,
            "heartbeat_interval": self._heartbeat_interval,
            "heartbeat_timeout": self._heartbeat_timeout
        }