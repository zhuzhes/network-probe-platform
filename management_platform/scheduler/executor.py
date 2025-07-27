"""任务执行器模块"""

import asyncio
import logging
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any
from uuid import UUID

from shared.models.task import Task, TaskResult, TaskStatus
from shared.models.agent import Agent, AgentStatus
from management_platform.database.connection import db_manager
from management_platform.api.connection_manager import AdvancedConnectionManager

logger = logging.getLogger(__name__)


class TaskExecutor:
    """任务执行器"""
    
    def __init__(self, connection_manager: AdvancedConnectionManager):
        self.connection_manager = connection_manager
        self.executing_tasks: Dict[UUID, asyncio.Task] = {}
        self.task_timeouts: Dict[UUID, asyncio.Task] = {}
    
    async def execute_task(self, task: Task, agent: Agent) -> bool:
        """执行单个任务"""
        try:
            # 检查代理是否在线
            if not self.connection_manager.is_agent_connected(agent.id):
                logger.warning(f"代理 {agent.id} 不在线，无法执行任务 {task.id}")
                return False
            
            # 创建任务执行协程
            execution_task = asyncio.create_task(
                self._execute_task_on_agent(task, agent)
            )
            
            # 设置超时
            timeout_task = asyncio.create_task(
                self._handle_task_timeout(task.id, task.timeout or 30)
            )
            
            # 保存任务引用
            self.executing_tasks[task.id] = execution_task
            self.task_timeouts[task.id] = timeout_task
            
            # 等待任务完成或超时
            done, pending = await asyncio.wait(
                [execution_task, timeout_task],
                return_when=asyncio.FIRST_COMPLETED
            )
            
            # 取消未完成的任务
            for task_obj in pending:
                task_obj.cancel()
            
            # 清理任务引用
            self.executing_tasks.pop(task.id, None)
            self.task_timeouts.pop(task.id, None)
            
            # 检查执行结果
            if execution_task in done:
                result = await execution_task
                return result
            else:
                # 任务超时
                logger.warning(f"任务 {task.id} 执行超时")
                await self._handle_task_failure(task, agent, "任务执行超时")
                return False
                
        except Exception as e:
            logger.error(f"执行任务 {task.id} 时发生错误: {e}")
            await self._handle_task_failure(task, agent, str(e))
            return False
    
    async def _execute_task_on_agent(self, task: Task, agent: Agent) -> bool:
        """在指定代理上执行任务"""
        try:
            # 构建任务消息
            task_message = {
                "type": "execute_task",
                "task_id": str(task.id),
                "protocol": task.protocol,
                "target": task.target,
                "port": task.port,
                "parameters": task.parameters,
                "timeout": task.timeout or 30
            }
            
            # 发送任务到代理
            success = await self.connection_manager.send_message_to_agent(
                agent.id, task_message
            )
            
            if not success:
                logger.error(f"无法向代理 {agent.id} 发送任务 {task.id}")
                return False
            
            # 更新任务状态为执行中
            await self._update_task_status(task.id, TaskStatus.RUNNING)
            
            logger.info(f"任务 {task.id} 已发送到代理 {agent.id}")
            return True
            
        except Exception as e:
            logger.error(f"在代理 {agent.id} 上执行任务 {task.id} 失败: {e}")
            return False
    
    async def _handle_task_timeout(self, task_id: UUID, timeout_seconds: int):
        """处理任务超时"""
        await asyncio.sleep(timeout_seconds)
        logger.warning(f"任务 {task_id} 执行超时 ({timeout_seconds}秒)")
    
    async def _handle_task_failure(self, task: Task, agent: Agent, error_message: str):
        """处理任务失败"""
        try:
            # 创建失败结果记录
            async with db_manager.get_async_session() as session:
                result = TaskResult(
                    task_id=task.id,
                    agent_id=agent.id,
                    execution_time=datetime.utcnow(),
                    duration=0.0,
                    status="error",
                    error_message=error_message,
                    metrics={},
                    raw_data={}
                )
                session.add(result)
                await session.commit()
            
            # 更新任务状态
            await self._update_task_status(task.id, TaskStatus.FAILED)
            
        except Exception as e:
            logger.error(f"处理任务失败时发生错误: {e}")
    
    async def _update_task_status(self, task_id: UUID, status: TaskStatus):
        """更新任务状态"""
        try:
            async with db_manager.get_async_session() as session:
                task = await session.get(Task, task_id)
                if task:
                    task.status = status
                    task.updated_at = datetime.utcnow()
                    await session.commit()
        except Exception as e:
            logger.error(f"更新任务状态失败: {e}")
    
    async def handle_task_result(self, agent_id: UUID, result_data: Dict[str, Any]):
        """处理代理返回的任务结果"""
        try:
            task_id = UUID(result_data.get("task_id"))
            
            # 检查任务是否正在执行
            if task_id not in self.executing_tasks:
                logger.warning(f"收到未知任务 {task_id} 的结果")
                return
            
            # 保存任务结果
            async with db_manager.get_async_session() as session:
                result = TaskResult(
                    task_id=task_id,
                    agent_id=agent_id,
                    execution_time=datetime.fromisoformat(result_data.get("execution_time")),
                    duration=result_data.get("duration", 0.0),
                    status=result_data.get("status", "success"),
                    error_message=result_data.get("error_message"),
                    metrics=result_data.get("metrics", {}),
                    raw_data=result_data.get("raw_data", {})
                )
                session.add(result)
                await session.commit()
            
            # 更新任务状态
            if result_data.get("status") == "success":
                await self._update_task_status(task_id, TaskStatus.COMPLETED)
            else:
                await self._update_task_status(task_id, TaskStatus.FAILED)
            
            logger.info(f"任务 {task_id} 结果已保存")
            
        except Exception as e:
            logger.error(f"处理任务结果时发生错误: {e}")
    
    async def cancel_task(self, task_id: UUID) -> bool:
        """取消正在执行的任务"""
        try:
            # 取消执行任务
            if task_id in self.executing_tasks:
                self.executing_tasks[task_id].cancel()
                self.executing_tasks.pop(task_id, None)
            
            # 取消超时任务
            if task_id in self.task_timeouts:
                self.task_timeouts[task_id].cancel()
                self.task_timeouts.pop(task_id, None)
            
            # 更新任务状态
            await self._update_task_status(task_id, TaskStatus.CANCELLED)
            
            logger.info(f"任务 {task_id} 已取消")
            return True
            
        except Exception as e:
            logger.error(f"取消任务 {task_id} 失败: {e}")
            return False
    
    async def get_executing_tasks(self) -> List[UUID]:
        """获取正在执行的任务列表"""
        return list(self.executing_tasks.keys())
    
    async def cleanup(self):
        """清理资源"""
        # 取消所有正在执行的任务
        for task_id in list(self.executing_tasks.keys()):
            await self.cancel_task(task_id)
        
        logger.info("任务执行器已清理")