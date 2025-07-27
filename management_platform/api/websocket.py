"""WebSocket服务端模块"""

import asyncio
import json
import uuid
import hashlib
import hmac
from typing import Dict, Any, Optional, Set, Callable, Awaitable
from datetime import datetime, timedelta
from fastapi import WebSocket, WebSocketDisconnect, HTTPException, Depends
from fastapi.security import HTTPBearer
import logging

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', '..'))

from shared.models.agent import Agent, AgentStatus
from management_platform.database.repositories import AgentRepository
from management_platform.database.connection import get_db_session


logger = logging.getLogger(__name__)
security = HTTPBearer()


class ConnectionManager:
    """WebSocket连接管理器"""
    
    def __init__(self):
        # 活跃连接：agent_id -> WebSocket连接
        self.active_connections: Dict[str, WebSocket] = {}
        
        # 代理会话信息：agent_id -> session_info
        self.agent_sessions: Dict[str, Dict[str, Any]] = {}
        
        # 消息处理器：message_type -> handler
        self.message_handlers: Dict[str, Callable[[str, Dict[str, Any]], Awaitable[None]]] = {}
        
        # 心跳监控
        self.last_heartbeats: Dict[str, datetime] = {}
        self.heartbeat_timeout = 90  # 90秒心跳超时
        
        # 统计信息
        self.connection_stats = {
            "total_connections": 0,
            "active_connections": 0,
            "failed_authentications": 0,
            "messages_sent": 0,
            "messages_received": 0
        }
        
        # 心跳监控任务（延迟启动）
        self._heartbeat_monitor_task = None
        self._monitor_started = False
    
    def _start_heartbeat_monitor(self):
        """启动心跳监控任务"""
        if not self._monitor_started and (self._heartbeat_monitor_task is None or self._heartbeat_monitor_task.done()):
            try:
                self._heartbeat_monitor_task = asyncio.create_task(self._heartbeat_monitor())
                self._monitor_started = True
            except RuntimeError:
                # 没有运行的事件循环，稍后启动
                pass
    
    async def _heartbeat_monitor(self):
        """心跳监控循环"""
        while True:
            try:
                await asyncio.sleep(30)  # 每30秒检查一次
                
                current_time = datetime.now()
                expired_agents = []
                
                for agent_id, last_heartbeat in self.last_heartbeats.items():
                    if (current_time - last_heartbeat).total_seconds() > self.heartbeat_timeout:
                        expired_agents.append(agent_id)
                        logger.warning(f"代理 {agent_id} 心跳超时")
                
                # 断开超时的连接
                for agent_id in expired_agents:
                    await self.disconnect_agent(agent_id, reason="heartbeat_timeout")
                    
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"心跳监控异常: {e}")
    
    def register_handler(self, message_type: str, handler: Callable[[str, Dict[str, Any]], Awaitable[None]]):
        """
        注册消息处理器
        
        Args:
            message_type: 消息类型
            handler: 处理器函数，接收 (agent_id, message) 参数
        """
        self.message_handlers[message_type] = handler
        logger.info(f"已注册消息处理器: {message_type}")
    
    async def connect_agent(self, websocket: WebSocket, agent_id: str, session_info: Dict[str, Any]):
        """
        连接代理
        
        Args:
            websocket: WebSocket连接
            agent_id: 代理ID
            session_info: 会话信息
        """
        # 如果代理已连接，先断开旧连接
        if agent_id in self.active_connections:
            logger.warning(f"代理 {agent_id} 已存在连接，断开旧连接")
            await self.disconnect_agent(agent_id, reason="new_connection")
        
        # 建立新连接
        await websocket.accept()
        self.active_connections[agent_id] = websocket
        self.agent_sessions[agent_id] = session_info
        self.last_heartbeats[agent_id] = datetime.now()
        
        # 更新统计
        self.connection_stats["total_connections"] += 1
        self.connection_stats["active_connections"] = len(self.active_connections)
        
        logger.info(f"代理 {agent_id} 已连接，当前活跃连接数: {len(self.active_connections)}")
        
        # 启动心跳监控（如果还没启动）
        if not self._monitor_started:
            self._start_heartbeat_monitor()
        
        # 更新数据库中的代理状态
        try:
            async with get_db_session() as db:
                agent_repo = AgentRepository(db)
                await agent_repo.update_agent_status(agent_id, AgentStatus.ONLINE)
        except Exception as e:
            logger.error(f"更新代理状态失败: {e}")
    
    async def disconnect_agent(self, agent_id: str, reason: str = "unknown"):
        """
        断开代理连接
        
        Args:
            agent_id: 代理ID
            reason: 断开原因
        """
        if agent_id not in self.active_connections:
            return
        
        websocket = self.active_connections[agent_id]
        
        try:
            # 发送断开通知
            disconnect_message = {
                "type": "disconnect",
                "data": {
                    "reason": reason,
                    "timestamp": datetime.now().isoformat()
                }
            }
            await websocket.send_text(json.dumps(disconnect_message))
            
            # 关闭连接
            await websocket.close()
            
        except Exception as e:
            logger.error(f"关闭WebSocket连接时出错: {e}")
        finally:
            # 清理连接信息
            self.active_connections.pop(agent_id, None)
            self.agent_sessions.pop(agent_id, None)
            self.last_heartbeats.pop(agent_id, None)
            
            # 更新统计
            self.connection_stats["active_connections"] = len(self.active_connections)
            
            logger.info(f"代理 {agent_id} 已断开连接 (原因: {reason})，当前活跃连接数: {len(self.active_connections)}")
            
            # 更新数据库中的代理状态
            try:
                async with get_db_session() as db:
                    agent_repo = AgentRepository(db)
                    await agent_repo.update_agent_status(agent_id, AgentStatus.OFFLINE)
            except Exception as e:
                logger.error(f"更新代理状态失败: {e}")
    
    async def send_message_to_agent(self, agent_id: str, message: Dict[str, Any]) -> bool:
        """
        发送消息给指定代理
        
        Args:
            agent_id: 代理ID
            message: 消息内容
            
        Returns:
            发送是否成功
        """
        if agent_id not in self.active_connections:
            logger.warning(f"代理 {agent_id} 未连接，无法发送消息")
            return False
        
        websocket = self.active_connections[agent_id]
        
        try:
            # 添加消息ID和时间戳
            if "id" not in message:
                message["id"] = str(uuid.uuid4())
            if "timestamp" not in message:
                message["timestamp"] = datetime.now().isoformat()
            
            message_json = json.dumps(message, ensure_ascii=False)
            await websocket.send_text(message_json)
            
            # 更新统计
            self.connection_stats["messages_sent"] += 1
            
            logger.debug(f"已向代理 {agent_id} 发送消息: {message.get('type', 'unknown')}")
            return True
            
        except Exception as e:
            logger.error(f"向代理 {agent_id} 发送消息失败: {e}")
            # 连接可能已断开，清理连接
            await self.disconnect_agent(agent_id, reason="send_failed")
            return False
    
    async def broadcast_message(self, message: Dict[str, Any], exclude_agents: Optional[Set[str]] = None) -> int:
        """
        广播消息给所有连接的代理
        
        Args:
            message: 消息内容
            exclude_agents: 要排除的代理ID集合
            
        Returns:
            成功发送的代理数量
        """
        if exclude_agents is None:
            exclude_agents = set()
        
        success_count = 0
        failed_agents = []
        
        for agent_id in list(self.active_connections.keys()):
            if agent_id in exclude_agents:
                continue
            
            if await self.send_message_to_agent(agent_id, message.copy()):
                success_count += 1
            else:
                failed_agents.append(agent_id)
        
        if failed_agents:
            logger.warning(f"广播消息失败的代理: {failed_agents}")
        
        logger.info(f"广播消息成功发送给 {success_count} 个代理")
        return success_count
    
    async def handle_message(self, agent_id: str, message: Dict[str, Any]):
        """
        处理来自代理的消息
        
        Args:
            agent_id: 代理ID
            message: 消息内容
        """
        message_type = message.get("type")
        
        # 更新统计
        self.connection_stats["messages_received"] += 1
        
        logger.debug(f"收到来自代理 {agent_id} 的消息: {message_type}")
        
        # 处理心跳消息
        if message_type == "heartbeat":
            await self._handle_heartbeat(agent_id, message)
            return
        
        # 查找并调用消息处理器
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
                await self.send_message_to_agent(agent_id, error_response)
        else:
            logger.warning(f"未找到消息类型 {message_type} 的处理器")
            
            # 发送未知消息类型响应
            unknown_response = {
                "type": "unknown_message_type",
                "data": {
                    "message": f"Unknown message type: {message_type}",
                    "original_message_id": message.get("id"),
                    "timestamp": datetime.now().isoformat()
                }
            }
            await self.send_message_to_agent(agent_id, unknown_response)
    
    async def _handle_heartbeat(self, agent_id: str, message: Dict[str, Any]):
        """
        处理心跳消息
        
        Args:
            agent_id: 代理ID
            message: 心跳消息
        """
        # 更新心跳时间
        self.last_heartbeats[agent_id] = datetime.now()
        
        # 发送心跳响应
        heartbeat_response = {
            "type": "heartbeat_response",
            "data": {
                "agent_id": agent_id,
                "server_time": datetime.now().isoformat(),
                "original_message_id": message.get("id")
            }
        }
        
        await self.send_message_to_agent(agent_id, heartbeat_response)
        logger.debug(f"已响应代理 {agent_id} 的心跳")
    
    def get_connected_agents(self) -> Set[str]:
        """获取所有连接的代理ID"""
        return set(self.active_connections.keys())
    
    def get_agent_session(self, agent_id: str) -> Optional[Dict[str, Any]]:
        """获取代理会话信息"""
        return self.agent_sessions.get(agent_id)
    
    def is_agent_connected(self, agent_id: str) -> bool:
        """检查代理是否已连接"""
        return agent_id in self.active_connections
    
    def get_connection_stats(self) -> Dict[str, Any]:
        """获取连接统计信息"""
        return {
            **self.connection_stats,
            "connected_agents": list(self.active_connections.keys()),
            "heartbeat_status": {
                agent_id: {
                    "last_heartbeat": last_heartbeat.isoformat(),
                    "seconds_since_last": (datetime.now() - last_heartbeat).total_seconds()
                }
                for agent_id, last_heartbeat in self.last_heartbeats.items()
            }
        }


# 导入高级连接管理器和消息分发器
from .connection_manager import advanced_connection_manager
from .message_dispatcher import get_message_dispatcher

# 全局连接管理器实例（保持向后兼容）
connection_manager = ConnectionManager()

# 全局消息分发器实例
message_dispatcher = None


class WebSocketAuthenticator:
    """WebSocket认证器"""
    
    @staticmethod
    def _generate_auth_signature(agent_id: str, api_key: str, timestamp: str, nonce: str) -> str:
        """
        生成认证签名
        
        Args:
            agent_id: 代理ID
            api_key: API密钥
            timestamp: 时间戳
            nonce: 随机数
            
        Returns:
            认证签名
        """
        message = f"{agent_id}:{timestamp}:{nonce}"
        signature = hmac.new(
            api_key.encode('utf-8'),
            message.encode('utf-8'),
            hashlib.sha256
        ).hexdigest()
        return signature
    
    @staticmethod
    async def authenticate_agent(websocket: WebSocket) -> Optional[Dict[str, Any]]:
        """
        认证代理
        
        Args:
            websocket: WebSocket连接
            
        Returns:
            认证成功返回代理信息，失败返回None
        """
        try:
            # 等待认证消息
            auth_message_json = await asyncio.wait_for(websocket.receive_text(), timeout=30.0)
            auth_message = json.loads(auth_message_json)
            
            if auth_message.get("type") != "auth":
                await websocket.send_text(json.dumps({
                    "type": "auth_response",
                    "data": {
                        "success": False,
                        "error": "Invalid message type"
                    }
                }))
                return None
            
            auth_data = auth_message.get("data", {})
            agent_id = auth_data.get("agent_id")
            timestamp = auth_data.get("timestamp")
            nonce = auth_data.get("nonce")
            signature = auth_data.get("signature")
            version = auth_data.get("version", "unknown")
            
            if not all([agent_id, timestamp, nonce, signature]):
                await websocket.send_text(json.dumps({
                    "type": "auth_response",
                    "data": {
                        "success": False,
                        "error": "Missing authentication parameters"
                    }
                }))
                return None
            
            # 验证时间戳（防止重放攻击）
            try:
                auth_time = datetime.fromisoformat(timestamp.replace('Z', '+00:00'))
                time_diff = abs((datetime.now() - auth_time.replace(tzinfo=None)).total_seconds())
                if time_diff > 300:  # 5分钟时间窗口
                    await websocket.send_text(json.dumps({
                        "type": "auth_response",
                        "data": {
                            "success": False,
                            "error": "Authentication timestamp expired"
                        }
                    }))
                    return None
            except ValueError:
                await websocket.send_text(json.dumps({
                    "type": "auth_response",
                    "data": {
                        "success": False,
                        "error": "Invalid timestamp format"
                    }
                }))
                return None
            
            # 从数据库获取代理信息和API密钥
            async with get_db_session() as db:
                agent_repo = AgentRepository(db)
                agent = await agent_repo.get_agent_by_id(agent_id)
                
                if not agent:
                    await websocket.send_text(json.dumps({
                        "type": "auth_response",
                        "data": {
                            "success": False,
                            "error": "Agent not found"
                        }
                    }))
                    connection_manager.connection_stats["failed_authentications"] += 1
                    return None
                
                # 验证签名
                expected_signature = WebSocketAuthenticator._generate_auth_signature(
                    agent_id, agent.api_key, timestamp, nonce
                )
                
                if not hmac.compare_digest(signature, expected_signature):
                    await websocket.send_text(json.dumps({
                        "type": "auth_response",
                        "data": {
                            "success": False,
                            "error": "Invalid signature"
                        }
                    }))
                    connection_manager.connection_stats["failed_authentications"] += 1
                    return None
                
                # 生成会话信息
                session_id = str(uuid.uuid4())
                session_info = {
                    "session_id": session_id,
                    "agent_id": agent_id,
                    "authenticated_at": datetime.now(),
                    "version": version,
                    "agent": agent
                }
                
                # 发送认证成功响应
                await websocket.send_text(json.dumps({
                    "type": "auth_response",
                    "data": {
                        "success": True,
                        "session_id": session_id,
                        "server_time": datetime.now().isoformat(),
                        "heartbeat_interval": 30
                    }
                }))
                
                logger.info(f"代理 {agent_id} 认证成功")
                return session_info
                
        except asyncio.TimeoutError:
            logger.warning("代理认证超时")
            try:
                await websocket.send_text(json.dumps({
                    "type": "auth_response",
                    "data": {
                        "success": False,
                        "error": "Authentication timeout"
                    }
                }))
            except:
                pass
            connection_manager.connection_stats["failed_authentications"] += 1
            return None
        except json.JSONDecodeError:
            logger.error("认证消息JSON解析失败")
            try:
                await websocket.send_text(json.dumps({
                    "type": "auth_response",
                    "data": {
                        "success": False,
                        "error": "Invalid JSON format"
                    }
                }))
            except:
                pass
            connection_manager.connection_stats["failed_authentications"] += 1
            return None
        except Exception as e:
            logger.error(f"代理认证异常: {e}")
            try:
                await websocket.send_text(json.dumps({
                    "type": "auth_response",
                    "data": {
                        "success": False,
                        "error": "Authentication failed"
                    }
                }))
            except:
                pass
            connection_manager.connection_stats["failed_authentications"] += 1
            return None


async def websocket_endpoint(websocket: WebSocket):
    """
    WebSocket端点处理函数
    
    Args:
        websocket: WebSocket连接
    """
    global message_dispatcher
    session_id = None
    agent_id = None
    
    try:
        # 启动高级连接管理器（如果还没启动）
        if not advanced_connection_manager._started:
            await advanced_connection_manager.start()
        
        # 启动消息分发器（如果还没启动）
        if message_dispatcher is None:
            message_dispatcher = get_message_dispatcher(advanced_connection_manager)
            await message_dispatcher.start()
        
        # 认证代理
        session_info = await WebSocketAuthenticator.authenticate_agent(websocket)
        if not session_info:
            await websocket.close(code=1008, reason="Authentication failed")
            return
        
        agent_id = session_info["agent_id"]
        session_id = session_info["session_id"]
        
        # 添加连接到高级管理器
        if not await advanced_connection_manager.add_connection(websocket, agent_id, session_info):
            await websocket.close(code=1008, reason="Connection limit exceeded")
            return
        
        # 认证连接
        await advanced_connection_manager.authenticate_connection(session_id)
        
        # 消息处理循环
        while True:
            try:
                # 接收消息
                message_json = await websocket.receive_text()
                
                # 解析消息
                try:
                    message = json.loads(message_json)
                except json.JSONDecodeError as e:
                    logger.error(f"消息JSON解析失败: {e}")
                    continue
                
                # 处理消息
                await advanced_connection_manager.handle_message(session_id, message)
                
            except WebSocketDisconnect:
                logger.info(f"代理 {agent_id} 主动断开连接")
                break
            except Exception as e:
                logger.error(f"处理代理 {agent_id} 消息时发生异常: {e}")
                continue
                
    except Exception as e:
        logger.error(f"WebSocket连接处理异常: {e}")
    finally:
        # 清理连接
        if session_id:
            await advanced_connection_manager.remove_connection(session_id, reason="connection_closed")


# 消息处理器注册
async def handle_agent_register(agent_id: str, message: Dict[str, Any]):
    """处理代理注册消息"""
    data = message.get("data", {})
    capabilities = data.get("capabilities", [])
    version = data.get("version", "unknown")
    
    logger.info(f"代理 {agent_id} 注册，能力: {capabilities}, 版本: {version}")
    
    # 更新数据库中的代理信息
    try:
        async with get_db_session() as db:
            agent_repo = AgentRepository(db)
            await agent_repo.update_agent_capabilities(agent_id, capabilities)
            await agent_repo.update_agent_version(agent_id, version)
    except Exception as e:
        logger.error(f"更新代理信息失败: {e}")
    
    # 发送注册确认
    response = {
        "type": "agent_register_response",
        "data": {
            "success": True,
            "agent_id": agent_id,
            "timestamp": datetime.now().isoformat()
        }
    }
    
    await connection_manager.send_message_to_agent(agent_id, response)


async def handle_task_result(agent_id: str, message: Dict[str, Any]):
    """处理任务结果消息"""
    data = message.get("data", {})
    task_id = data.get("task_id")
    result = data.get("result")
    
    logger.info(f"收到代理 {agent_id} 的任务 {task_id} 结果")
    
    # 这里应该将结果保存到数据库
    # 实际实现时需要调用任务仓库的方法
    
    # 发送确认响应
    response = {
        "type": "task_result_ack",
        "data": {
            "task_id": task_id,
            "received": True,
            "timestamp": datetime.now().isoformat()
        }
    }
    
    await connection_manager.send_message_to_agent(agent_id, response)


async def handle_resource_report(agent_id: str, message: Dict[str, Any]):
    """处理资源报告消息"""
    data = message.get("data", {})
    resources = data.get("resources", {})
    
    logger.debug(f"收到代理 {agent_id} 的资源报告: {resources}")
    
    # 这里应该将资源信息保存到数据库
    # 实际实现时需要调用代理仓库的方法
    
    # 发送确认响应
    response = {
        "type": "resource_report_ack",
        "data": {
            "received": True,
            "timestamp": datetime.now().isoformat()
        }
    }
    
    await connection_manager.send_message_to_agent(agent_id, response)


# 注册消息处理器
connection_manager.register_handler("agent_register", handle_agent_register)
connection_manager.register_handler("task_result", handle_task_result)
connection_manager.register_handler("resource_report", handle_resource_report)


def get_connection_manager() -> ConnectionManager:
    """获取连接管理器实例（向后兼容）"""
    return connection_manager

def get_advanced_connection_manager():
    """获取高级连接管理器实例"""
    return advanced_connection_manager

def get_message_dispatcher_instance():
    """获取消息分发器实例"""
    global message_dispatcher
    if message_dispatcher is None:
        from .message_dispatcher import get_message_dispatcher
        message_dispatcher = get_message_dispatcher(advanced_connection_manager)
    return message_dispatcher