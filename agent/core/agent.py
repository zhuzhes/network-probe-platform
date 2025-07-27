"""代理主程序"""

import asyncio
import signal
import sys
import uuid
from typing import Optional, Dict, Any
from datetime import datetime

from .config import AgentConfigManager
from .logger import AgentLogger
from .websocket_client import WebSocketClient
from .executor import TaskExecutor, TaskResultCollector
from ..monitoring import ResourceMonitor


class Agent:
    """网络拨测代理主类"""
    
    def __init__(self, config_file: Optional[str] = None):
        """
        初始化代理
        
        Args:
            config_file: 配置文件路径
        """
        self.config = AgentConfigManager(config_file)
        self.logger = AgentLogger("agent")
        
        # 代理状态
        self._running = False
        self._connected = False
        self._agent_id = self.config.agent_id or str(uuid.uuid4())
        
        # WebSocket客户端
        self._websocket_client: Optional[WebSocketClient] = None
        
        # 资源监控器
        self._resource_monitor = ResourceMonitor(self.logger)
        
        # 任务执行器
        self._task_executor: Optional[TaskExecutor] = None
        self._result_collector: Optional[TaskResultCollector] = None
        
        # 异步任务
        self._tasks: Dict[str, asyncio.Task] = {}
        
        # 信号处理
        self._setup_signal_handlers()
        
        self.logger.info(f"代理初始化完成，ID: {self._agent_id}")
    
    def _setup_signal_handlers(self):
        """设置信号处理器"""
        if sys.platform != 'win32':
            signal.signal(signal.SIGINT, self._signal_handler)
            signal.signal(signal.SIGTERM, self._signal_handler)
    
    def _signal_handler(self, signum, frame):
        """信号处理函数"""
        self.logger.info(f"接收到信号 {signum}，准备关闭代理...")
        asyncio.create_task(self.stop())
    
    @property
    def agent_id(self) -> str:
        """获取代理ID"""
        return self._agent_id
    
    @property
    def is_running(self) -> bool:
        """检查代理是否正在运行"""
        return self._running
    
    @property
    def is_connected(self) -> bool:
        """检查代理是否已连接到管理平台"""
        return self._websocket_client is not None and self._websocket_client.is_connected
    
    async def start(self):
        """启动代理"""
        if self._running:
            self.logger.warning("代理已经在运行中")
            return
        
        self.logger.info("正在启动代理...")
        self._running = True
        
        try:
            # 保存代理ID到配置
            if not self.config.agent_id:
                self.config.agent_id = self._agent_id
                self.config.save_local_config()
            
            # 启动核心服务
            await self._start_core_services()
            
            self.logger.info("代理启动成功")
            
            # 保持运行
            await self._run_forever()
            
        except Exception as e:
            self.logger.error(f"代理启动失败: {e}")
            await self.stop()
            raise
    
    async def stop(self):
        """停止代理"""
        if not self._running:
            return
        
        self.logger.info("正在停止代理...")
        self._running = False
        self._connected = False
        
        # 断开WebSocket连接
        if self._websocket_client:
            await self._websocket_client.disconnect()
            self._websocket_client = None
        
        # 停止任务执行器
        await self._stop_task_executor()
        
        # 停止所有异步任务
        for task_name, task in self._tasks.items():
            if not task.done():
                self.logger.info(f"正在取消任务: {task_name}")
                task.cancel()
                try:
                    await task
                except asyncio.CancelledError:
                    pass
                except Exception as e:
                    self.logger.error(f"停止任务 {task_name} 时出错: {e}")
        
        self._tasks.clear()
        self.logger.info("代理已停止")
    
    async def _start_core_services(self):
        """启动核心服务"""
        # 创建WebSocket客户端
        self._websocket_client = WebSocketClient(
            server_url=self.config.server_url,
            api_key=self.config.api_key,
            agent_id=self._agent_id,
            cert_file=self.config.cert_file,
            key_file=self.config.key_file,
            logger=self.logger
        )
        
        # 注册消息处理器
        self._register_message_handlers()
        
        # 连接到管理平台
        if await self._websocket_client.connect():
            self._connected = True
            self.logger.info("已连接到管理平台")
        else:
            self.logger.error("连接到管理平台失败")
            raise RuntimeError("无法连接到管理平台")
        
        # 启动连接监控服务
        self._tasks["connection_monitor"] = asyncio.create_task(
            self._connection_monitor_service(),
            name="connection_monitor"
        )
        
        # 启动资源监控服务
        self._tasks["resource_monitor"] = asyncio.create_task(
            self._resource_monitor_service(),
            name="resource_monitor"
        )
        
        # 启动任务执行器
        await self._start_task_executor()
        
        self.logger.info("核心服务已启动")
    
    async def _run_forever(self):
        """保持代理运行"""
        try:
            while self._running:
                await asyncio.sleep(1)
                
                # 检查关键任务状态
                for task_name, task in list(self._tasks.items()):
                    if task.done():
                        if task.exception():
                            self.logger.error(f"任务 {task_name} 异常退出: {task.exception()}")
                            # 重启关键任务
                            if task_name in ["connection_monitor", "resource_monitor"]:
                                self.logger.info(f"重启任务: {task_name}")
                                if task_name == "connection_monitor":
                                    self._tasks[task_name] = asyncio.create_task(
                                        self._connection_monitor_service(),
                                        name=task_name
                                    )
                                elif task_name == "resource_monitor":
                                    self._tasks[task_name] = asyncio.create_task(
                                        self._resource_monitor_service(),
                                        name=task_name
                                    )
                        else:
                            self.logger.info(f"任务 {task_name} 正常结束")
                            del self._tasks[task_name]
                            
        except asyncio.CancelledError:
            self.logger.info("代理主循环被取消")
        except Exception as e:
            self.logger.error(f"代理主循环异常: {e}")
            raise
    
    def _register_message_handlers(self):
        """注册消息处理器"""
        if not self._websocket_client:
            return
        
        # 注册任务相关消息处理器
        self._websocket_client.register_handler("task_assign", self._handle_task_assign)
        self._websocket_client.register_handler("task_cancel", self._handle_task_cancel)
        self._websocket_client.register_handler("config_update", self._handle_config_update)
        self._websocket_client.register_handler("agent_command", self._handle_agent_command)
        
        self.logger.info("消息处理器已注册")
    
    async def _handle_task_assign(self, message: Dict[str, Any]):
        """处理任务分配消息"""
        task_data = message.get("data", {})
        task_id = task_data.get("task_id")
        
        self.logger.info(f"收到任务分配: {task_id}")
        
        try:
            # 使用任务执行器执行任务
            if self._task_executor:
                success = await self._task_executor.execute_task(task_data)
                status = "accepted" if success else "rejected"
                error_message = None if success else "任务执行器繁忙或任务无效"
            else:
                status = "rejected"
                error_message = "任务执行器未初始化"
            
            # 发送响应消息
            response = {
                "type": "task_assign_response",
                "data": {
                    "task_id": task_id,
                    "status": status,
                    "agent_id": self._agent_id,
                    "error_message": error_message
                }
            }
            
            if self._websocket_client:
                await self._websocket_client.send_message(response)
                
        except Exception as e:
            self.logger.error(f"处理任务分配失败: {e}")
            
            # 发送错误响应
            error_response = {
                "type": "task_assign_response",
                "data": {
                    "task_id": task_id,
                    "status": "error",
                    "agent_id": self._agent_id,
                    "error_message": str(e)
                }
            }
            
            if self._websocket_client:
                await self._websocket_client.send_message(error_response)
    
    async def _handle_task_cancel(self, message: Dict[str, Any]):
        """处理任务取消消息"""
        task_data = message.get("data", {})
        task_id = task_data.get("task_id")
        
        self.logger.info(f"收到任务取消: {task_id}")
        
        try:
            # 使用任务执行器取消任务
            if self._task_executor:
                success = await self._task_executor.cancel_task(uuid.UUID(task_id))
                status = "cancelled" if success else "not_found"
                error_message = None if success else "任务不存在或已完成"
            else:
                status = "error"
                error_message = "任务执行器未初始化"
            
            # 发送响应消息
            response = {
                "type": "task_cancel_response",
                "data": {
                    "task_id": task_id,
                    "status": status,
                    "agent_id": self._agent_id,
                    "error_message": error_message
                }
            }
            
            if self._websocket_client:
                await self._websocket_client.send_message(response)
                
        except Exception as e:
            self.logger.error(f"处理任务取消失败: {e}")
            
            # 发送错误响应
            error_response = {
                "type": "task_cancel_response",
                "data": {
                    "task_id": task_id,
                    "status": "error",
                    "agent_id": self._agent_id,
                    "error_message": str(e)
                }
            }
            
            if self._websocket_client:
                await self._websocket_client.send_message(error_response)
    
    async def _handle_config_update(self, message: Dict[str, Any]):
        """处理配置更新消息"""
        config_data = message.get("data", {})
        
        self.logger.info("收到配置更新消息")
        
        # 更新配置
        self.config.update(config_data)
        self.config.save_local_config()
        
        # 重新加载配置
        await self.reload_config()
        
        # 发送确认消息
        response = {
            "type": "config_update_response",
            "data": {
                "status": "updated",
                "agent_id": self._agent_id
            }
        }
        
        if self._websocket_client:
            await self._websocket_client.send_message(response)
    
    async def _handle_agent_command(self, message: Dict[str, Any]):
        """处理代理命令消息"""
        command_data = message.get("data", {})
        command = command_data.get("command")
        
        self.logger.info(f"收到代理命令: {command}")
        
        response_data = {
            "command": command,
            "agent_id": self._agent_id,
            "status": "unknown"
        }
        
        try:
            if command == "status":
                response_data["status"] = "success"
                response_data["result"] = self.get_status()
            elif command == "reload_config":
                await self.reload_config()
                response_data["status"] = "success"
            elif command == "restart":
                # 这里可以实现重启逻辑
                response_data["status"] = "success"
                response_data["message"] = "restart command received"
            else:
                response_data["status"] = "error"
                response_data["message"] = f"unknown command: {command}"
        
        except Exception as e:
            response_data["status"] = "error"
            response_data["message"] = str(e)
        
        response = {
            "type": "agent_command_response",
            "data": response_data
        }
        
        if self._websocket_client:
            await self._websocket_client.send_message(response)
    
    async def _connection_monitor_service(self):
        """连接监控服务"""
        self.logger.info("连接监控服务已启动")
        
        try:
            while self._running:
                if self._websocket_client and not self._websocket_client.is_connected:
                    self.logger.warning("检测到连接断开，尝试重新连接...")
                    
                    if await self._websocket_client.reconnect():
                        self.logger.info("重新连接成功")
                        self._connected = True
                    else:
                        self.logger.error("重新连接失败")
                        self._connected = False
                
                await asyncio.sleep(10)  # 每10秒检查一次连接状态
                
        except asyncio.CancelledError:
            self.logger.info("连接监控服务已停止")
        except Exception as e:
            self.logger.error(f"连接监控服务异常: {e}")
            raise
    
    async def _resource_monitor_service(self):
        """资源监控服务"""
        self.logger.info("资源监控服务已启动")
        try:
            while self._running:
                try:
                    # 收集资源指标
                    metrics = await self._resource_monitor.collect_metrics_async()
                    
                    # 添加代理信息
                    resource_data = {
                        "agent_id": self._agent_id,
                        "timestamp": metrics["timestamp"],
                        "metrics": metrics
                    }
                    
                    # 发送资源数据到管理平台
                    if self._websocket_client and self._websocket_client.is_connected:
                        message = {
                            "type": "resource_report",
                            "data": resource_data
                        }
                        await self._websocket_client.send_message(message)
                        self.logger.debug("资源数据已上报")
                    else:
                        self.logger.warning("WebSocket未连接，跳过资源数据上报")
                    
                except Exception as e:
                    self.logger.error(f"收集或上报资源数据失败: {e}")
                
                # 等待下次收集
                await asyncio.sleep(self.config.resource_report_interval)
                
        except asyncio.CancelledError:
            self.logger.info("资源监控服务已停止")
        except Exception as e:
            self.logger.error(f"资源监控服务异常: {e}")
            raise
    
    def get_status(self) -> Dict[str, Any]:
        """获取代理状态信息"""
        status = {
            "agent_id": self._agent_id,
            "agent_name": self.config.agent_name,
            "running": self._running,
            "connected": self._connected,
            "server_url": self.config.server_url,
            "heartbeat_interval": self.config.heartbeat_interval,
            "resource_report_interval": self.config.resource_report_interval,
            "max_concurrent_tasks": self.config.max_concurrent_tasks,
            "active_tasks": list(self._tasks.keys()),
            "timestamp": datetime.now().isoformat()
        }
        
        # 添加当前资源使用情况
        try:
            current_resources = self._resource_monitor.collect_all_metrics()
            status["resources"] = current_resources
        except Exception as e:
            self.logger.error(f"获取资源状态失败: {e}")
            status["resources"] = {"error": str(e)}
        
        # 添加任务执行器状态
        try:
            status["task_executor"] = self.get_task_executor_status()
        except Exception as e:
            self.logger.error(f"获取任务执行器状态失败: {e}")
            status["task_executor"] = {"error": str(e)}
        
        return status
    
    async def reload_config(self):
        """重新加载配置"""
        self.logger.info("重新加载配置...")
        old_config = self.config.get_all()
        
        # 重新创建配置管理器
        self.config = AgentConfigManager(self.config.config_file)
        
        new_config = self.config.get_all()
        
        # 检查关键配置是否变更
        if old_config.get('server_url') != new_config.get('server_url'):
            self.logger.info("服务器URL已变更，需要重新连接")
            # 这里将在子任务6.2中实现重新连接逻辑
        
        if old_config.get('heartbeat_interval') != new_config.get('heartbeat_interval'):
            self.logger.info("心跳间隔已变更")
            # 更新WebSocket客户端的心跳间隔
            if self._websocket_client:
                self._websocket_client.set_heartbeat_interval(new_config.get('heartbeat_interval', 30))
        
        if old_config.get('resource_report_interval') != new_config.get('resource_report_interval'):
            self.logger.info("资源报告间隔已变更")
            # 重启资源监控服务
            if "resource_monitor" in self._tasks:
                self._tasks["resource_monitor"].cancel()
        
        self.logger.info("配置重新加载完成")
    
    async def _start_task_executor(self):
        """启动任务执行器"""
        try:
            # 创建结果收集器
            self._result_collector = TaskResultCollector(
                agent_id=self._agent_id,
                batch_size=self.config.result_batch_size or 10,
                batch_timeout=self.config.result_batch_timeout or 30,
                send_callback=self._send_task_results
            )
            
            # 创建任务执行器
            self._task_executor = TaskExecutor(
                agent_id=self._agent_id,
                max_concurrent_tasks=self.config.max_concurrent_tasks or 10,
                default_timeout=self.config.default_task_timeout or 30,
                result_callback=self._result_collector.collect_result
            )
            
            # 启动组件
            await self._result_collector.start()
            await self._task_executor.start()
            
            self.logger.info("任务执行器已启动")
            
        except Exception as e:
            self.logger.error(f"启动任务执行器失败: {e}")
            raise
    
    async def _stop_task_executor(self):
        """停止任务执行器"""
        try:
            if self._task_executor:
                await self._task_executor.stop()
                self._task_executor = None
                self.logger.info("任务执行器已停止")
            
            if self._result_collector:
                await self._result_collector.stop()
                self._result_collector = None
                self.logger.info("结果收集器已停止")
                
        except Exception as e:
            self.logger.error(f"停止任务执行器失败: {e}")
    
    async def _send_task_results(self, batch_data: Dict[str, Any]):
        """发送任务结果批次"""
        try:
            if self._websocket_client and self._websocket_client.is_connected:
                message = {
                    "type": "task_results_batch",
                    "data": batch_data
                }
                await self._websocket_client.send_message(message)
                self.logger.debug(f"已发送 {len(batch_data['results'])} 个任务结果")
            else:
                self.logger.warning("WebSocket未连接，无法发送任务结果")
                
        except Exception as e:
            self.logger.error(f"发送任务结果失败: {e}")
    
    def get_task_executor_status(self) -> Dict[str, Any]:
        """获取任务执行器状态"""
        if not self._task_executor:
            return {"status": "not_initialized"}
        
        return self._task_executor.get_statistics()
    
    async def get_task_executor_health(self) -> Dict[str, Any]:
        """获取任务执行器健康状态"""
        if not self._task_executor:
            return {"status": "not_initialized"}
        
        return await self._task_executor.health_check()


async def main():
    """代理主入口函数"""
    agent = Agent()
    
    try:
        await agent.start()
    except KeyboardInterrupt:
        print("\n接收到中断信号，正在关闭代理...")
    except Exception as e:
        print(f"代理运行异常: {e}")
        sys.exit(1)
    finally:
        await agent.stop()


if __name__ == "__main__":
    asyncio.run(main())