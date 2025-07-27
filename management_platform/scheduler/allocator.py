"""任务分配器模块"""

import logging
import math
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional, Tuple
import uuid

from sqlalchemy.orm import Session
from sqlalchemy import and_, func, desc

from shared.models.task import Task, TaskResult, TaskResultStatus
from shared.models.agent import Agent, AgentStatus, AgentResource
from management_platform.database.connection import get_db_session


logger = logging.getLogger(__name__)


class AgentSelector:
    """代理选择器"""
    
    def __init__(self):
        self.location_weight = 0.3
        self.performance_weight = 0.4
        self.load_weight = 0.3
    
    async def select_best_agent(self, task: Task, available_agents: List[Agent]) -> Optional[Agent]:
        """选择最佳代理"""
        if not available_agents:
            return None
        
        # 计算每个代理的评分
        agent_scores = []
        for agent in available_agents:
            score = await self._calculate_agent_score(task, agent)
            agent_scores.append((agent, score))
        
        # 按评分排序，选择最高分的代理
        agent_scores.sort(key=lambda x: x[1], reverse=True)
        
        best_agent, best_score = agent_scores[0]
        logger.debug(f"为任务 {task.id} 选择代理 {best_agent.id}，评分: {best_score:.3f}")
        
        return best_agent
    
    async def _calculate_agent_score(self, task: Task, agent: Agent) -> float:
        """计算代理评分"""
        # 地理位置评分
        location_score = self._calculate_location_score(task, agent)
        
        # 性能评分
        performance_score = await self._calculate_performance_score(task, agent)
        
        # 负载评分
        load_score = self._calculate_load_score(agent)
        
        # 综合评分
        total_score = (
            location_score * self.location_weight +
            performance_score * self.performance_weight +
            load_score * self.load_weight
        )
        
        return total_score
    
    def _calculate_location_score(self, task: Task, agent: Agent) -> float:
        """计算地理位置评分"""
        score = 0.5  # 基础分数
        
        # 检查首选位置匹配
        if task.preferred_location:
            if agent.country and task.preferred_location.lower() in agent.country.lower():
                score += 0.3
            elif agent.city and task.preferred_location.lower() in agent.city.lower():
                score += 0.2
        
        # 检查首选运营商匹配
        if task.preferred_isp:
            if agent.isp and task.preferred_isp.lower() in agent.isp.lower():
                score += 0.2
        
        return min(1.0, score)
    
    async def _calculate_performance_score(self, task: Task, agent: Agent) -> float:
        """计算性能评分"""
        try:
            async with get_db_session() as db:
                # 查询代理最近的任务执行记录
                recent_results = db.query(TaskResult).filter(
                    and_(
                        TaskResult.agent_id == agent.id,
                        TaskResult.execution_time >= datetime.utcnow() - timedelta(days=7)
                    )
                ).limit(100).all()
                
                if not recent_results:
                    return 0.5  # 没有历史数据时给中等分数
                
                # 计算成功率
                success_count = sum(1 for r in recent_results if r.status == TaskResultStatus.SUCCESS)
                success_rate = success_count / len(recent_results)
                
                # 计算平均响应时间评分
                successful_results = [r for r in recent_results if r.status == TaskResultStatus.SUCCESS and r.duration]
                if successful_results:
                    avg_response_time = sum(r.duration for r in successful_results) / len(successful_results)
                    # 响应时间越短评分越高（假设1000ms为基准）
                    response_score = max(0, 1 - (avg_response_time / 1000))
                else:
                    response_score = 0.5
                
                # 综合性能评分
                performance_score = (success_rate * 0.7) + (response_score * 0.3)
                
                return min(1.0, performance_score)
                
        except Exception as e:
            logger.error(f"计算代理 {agent.id} 性能评分时发生错误: {e}")
            return 0.5
    
    def _calculate_load_score(self, agent: Agent) -> float:
        """计算负载评分"""
        # 基于当前资源使用情况计算负载评分
        cpu_score = 1.0 - (agent.current_cpu_usage or 0) / 100
        memory_score = 1.0 - (agent.current_memory_usage or 0) / 100
        
        # 综合负载评分
        load_score = (cpu_score + memory_score) / 2
        
        return max(0.0, min(1.0, load_score))


class TaskAllocator:
    """任务分配器"""
    
    def __init__(self):
        self.agent_selector = AgentSelector()
        self.max_agent_load = 0.8  # 最大负载阈值
        self.min_agent_availability = 0.7  # 最小可用性阈值
    
    async def select_agent(self, task: Task) -> Optional[Agent]:
        """为任务选择合适的代理"""
        try:
            # 获取可用的代理列表
            available_agents = await self._get_available_agents(task)
            
            if not available_agents:
                logger.warning(f"没有可用的代理执行任务 {task.id}")
                return None
            
            # 过滤合适的代理
            suitable_agents = await self._filter_suitable_agents(task, available_agents)
            
            if not suitable_agents:
                logger.warning(f"没有合适的代理执行任务 {task.id}")
                return None
            
            # 选择最佳代理
            best_agent = await self.agent_selector.select_best_agent(task, suitable_agents)
            
            return best_agent
            
        except Exception as e:
            logger.error(f"为任务 {task.id} 选择代理时发生错误: {e}")
            return None
    
    async def _get_available_agents(self, task: Task) -> List[Agent]:
        """获取可用的代理列表"""
        try:
            async with get_db_session() as db:
                # 查询在线且启用的代理
                agents = db.query(Agent).filter(
                    and_(
                        Agent.status == AgentStatus.ONLINE,
                        Agent.enabled == True,
                        Agent.last_heartbeat >= datetime.utcnow() - timedelta(minutes=5)
                    )
                ).all()
                
                return agents
                
        except Exception as e:
            logger.error(f"获取可用代理列表时发生错误: {e}")
            return []
    
    async def _filter_suitable_agents(self, task: Task, agents: List[Agent]) -> List[Agent]:
        """过滤合适的代理"""
        suitable_agents = []
        
        for agent in agents:
            # 检查代理能力
            if not self._check_agent_capabilities(task, agent):
                continue
            
            # 检查代理负载
            if not self._check_agent_load(agent):
                continue
            
            # 检查代理可用性
            if not await self._check_agent_availability(agent):
                continue
            
            suitable_agents.append(agent)
        
        return suitable_agents
    
    def _check_agent_capabilities(self, task: Task, agent: Agent) -> bool:
        """检查代理是否支持任务协议"""
        if not agent.capabilities:
            return True  # 如果没有能力信息，假设支持所有协议
        
        supported_protocols = agent.capabilities.get('protocols', [])
        if not supported_protocols:
            return True  # 如果没有协议信息，假设支持所有协议
        
        return task.protocol.value in supported_protocols
    
    def _check_agent_load(self, agent: Agent) -> bool:
        """检查代理负载是否可接受"""
        # 检查CPU负载
        if agent.current_cpu_usage and agent.current_cpu_usage > self.max_agent_load * 100:
            return False
        
        # 检查内存负载
        if agent.current_memory_usage and agent.current_memory_usage > self.max_agent_load * 100:
            return False
        
        return True
    
    async def _check_agent_availability(self, agent: Agent) -> bool:
        """检查代理可用性"""
        if agent.availability and agent.availability < self.min_agent_availability:
            return False
        
        return True
    
    async def allocate_tasks_to_agents(self, tasks: List[Task]) -> Dict[uuid.UUID, Optional[uuid.UUID]]:
        """批量分配任务到代理"""
        allocation_result = {}
        
        # 获取所有可用代理
        all_available_agents = await self._get_available_agents(tasks[0] if tasks else None)
        
        # 跟踪代理负载
        agent_load_tracker = {agent.id: 0 for agent in all_available_agents}
        
        for task in tasks:
            # 过滤适合当前任务的代理
            suitable_agents = await self._filter_suitable_agents(task, all_available_agents)
            
            # 进一步过滤负载不高的代理
            available_agents = []
            for agent in suitable_agents:
                current_load = agent_load_tracker.get(agent.id, 0)
                if current_load < agent.max_concurrent_tasks:
                    available_agents.append(agent)
            
            if available_agents:
                # 选择最佳代理
                selected_agent = await self.agent_selector.select_best_agent(task, available_agents)
                if selected_agent:
                    allocation_result[task.id] = selected_agent.id
                    agent_load_tracker[selected_agent.id] += 1
                else:
                    allocation_result[task.id] = None
            else:
                allocation_result[task.id] = None
        
        return allocation_result
    
    async def rebalance_tasks(self) -> Dict[str, Any]:
        """重新平衡任务分配"""
        try:
            async with get_db_session() as db:
                # 获取所有在线代理的负载信息
                agents = db.query(Agent).filter(
                    Agent.status == AgentStatus.ONLINE
                ).all()
                
                if not agents:
                    return {'rebalanced': 0, 'message': '没有在线代理'}
                
                # 计算代理负载分布
                agent_loads = {}
                for agent in agents:
                    # 查询代理当前执行的任务数量
                    current_tasks = db.query(func.count(TaskResult.id)).filter(
                        and_(
                            TaskResult.agent_id == agent.id,
                            TaskResult.execution_time >= datetime.utcnow() - timedelta(minutes=10)
                        )
                    ).scalar() or 0
                    
                    agent_loads[agent.id] = {
                        'agent': agent,
                        'current_tasks': current_tasks,
                        'max_tasks': agent.max_concurrent_tasks,
                        'load_ratio': current_tasks / agent.max_concurrent_tasks if agent.max_concurrent_tasks > 0 else 0
                    }
                
                # 识别负载不均衡的情况
                load_ratios = [info['load_ratio'] for info in agent_loads.values()]
                avg_load = sum(load_ratios) / len(load_ratios)
                load_variance = sum((ratio - avg_load) ** 2 for ratio in load_ratios) / len(load_ratios)
                
                rebalance_info = {
                    'total_agents': len(agents),
                    'average_load': avg_load,
                    'load_variance': load_variance,
                    'rebalanced': 0,
                    'agent_loads': {str(agent_id): info['load_ratio'] for agent_id, info in agent_loads.items()}
                }
                
                # 如果负载方差较大，建议重新平衡
                if load_variance > 0.1:  # 阈值可调整
                    rebalance_info['recommendation'] = '建议重新平衡任务分配'
                    rebalance_info['high_load_agents'] = [
                        str(agent_id) for agent_id, info in agent_loads.items() 
                        if info['load_ratio'] > avg_load + 0.2
                    ]
                    rebalance_info['low_load_agents'] = [
                        str(agent_id) for agent_id, info in agent_loads.items() 
                        if info['load_ratio'] < avg_load - 0.2
                    ]
                
                return rebalance_info
                
        except Exception as e:
            logger.error(f"重新平衡任务时发生错误: {e}")
            return {'error': str(e)}
    
    async def get_allocation_statistics(self) -> Dict[str, Any]:
        """获取分配统计信息"""
        try:
            async with get_db_session() as db:
                # 获取最近24小时的任务分配统计
                since_time = datetime.utcnow() - timedelta(hours=24)
                
                # 总任务数
                total_tasks = db.query(func.count(TaskResult.id)).filter(
                    TaskResult.execution_time >= since_time
                ).scalar() or 0
                
                # 成功分配的任务数
                successful_tasks = db.query(func.count(TaskResult.id)).filter(
                    and_(
                        TaskResult.execution_time >= since_time,
                        TaskResult.status == TaskResultStatus.SUCCESS
                    )
                ).scalar() or 0
                
                # 按代理分组的任务分配统计
                agent_stats = db.query(
                    TaskResult.agent_id,
                    func.count(TaskResult.id).label('task_count'),
                    func.avg(TaskResult.duration).label('avg_duration'),
                    func.count(TaskResult.id).filter(TaskResult.status == TaskResultStatus.SUCCESS).label('success_count')
                ).filter(
                    TaskResult.execution_time >= since_time
                ).group_by(TaskResult.agent_id).all()
                
                agent_statistics = []
                for stat in agent_stats:
                    agent = db.query(Agent).filter(Agent.id == stat.agent_id).first()
                    agent_statistics.append({
                        'agent_id': str(stat.agent_id),
                        'agent_name': agent.name if agent else 'Unknown',
                        'task_count': stat.task_count,
                        'success_count': stat.success_count,
                        'success_rate': stat.success_count / stat.task_count if stat.task_count > 0 else 0,
                        'avg_duration': float(stat.avg_duration) if stat.avg_duration else 0
                    })
                
                return {
                    'period': '24小时',
                    'total_tasks': total_tasks,
                    'successful_tasks': successful_tasks,
                    'success_rate': successful_tasks / total_tasks if total_tasks > 0 else 0,
                    'agent_statistics': agent_statistics
                }
                
        except Exception as e:
            logger.error(f"获取分配统计信息时发生错误: {e}")
            return {'error': str(e)}
    
    async def predict_optimal_allocation(self, task: Task) -> Dict[str, Any]:
        """预测最优分配"""
        try:
            available_agents = await self._get_available_agents(task)
            suitable_agents = await self._filter_suitable_agents(task, available_agents)
            
            if not suitable_agents:
                return {
                    'prediction': 'no_suitable_agents',
                    'message': '没有合适的代理可用'
                }
            
            # 为每个合适的代理计算详细评分
            agent_predictions = []
            for agent in suitable_agents:
                location_score = self.agent_selector._calculate_location_score(task, agent)
                performance_score = await self.agent_selector._calculate_performance_score(task, agent)
                load_score = self.agent_selector._calculate_load_score(agent)
                
                total_score = (
                    location_score * self.agent_selector.location_weight +
                    performance_score * self.agent_selector.performance_weight +
                    load_score * self.agent_selector.load_weight
                )
                
                agent_predictions.append({
                    'agent_id': str(agent.id),
                    'agent_name': agent.name,
                    'total_score': total_score,
                    'location_score': location_score,
                    'performance_score': performance_score,
                    'load_score': load_score,
                    'current_load': {
                        'cpu': agent.current_cpu_usage,
                        'memory': agent.current_memory_usage
                    }
                })
            
            # 按评分排序
            agent_predictions.sort(key=lambda x: x['total_score'], reverse=True)
            
            return {
                'prediction': 'success',
                'recommended_agent': agent_predictions[0] if agent_predictions else None,
                'all_candidates': agent_predictions,
                'selection_criteria': {
                    'location_weight': self.agent_selector.location_weight,
                    'performance_weight': self.agent_selector.performance_weight,
                    'load_weight': self.agent_selector.load_weight
                }
            }
            
        except Exception as e:
            logger.error(f"预测最优分配时发生错误: {e}")
            return {'error': str(e)}


class TaskReassignmentManager:
    """任务重新分配管理器"""
    
    def __init__(self, task_allocator: TaskAllocator):
        self.task_allocator = task_allocator
        self.reassignment_history: Dict[uuid.UUID, List[Dict[str, Any]]] = {}
        self.max_reassignments = 3
        self.reassignment_delay = 60  # 重新分配延迟（秒）
    
    async def handle_agent_failure(self, failed_agent_id: uuid.UUID) -> Dict[str, Any]:
        """处理代理故障，重新分配其任务"""
        try:
            async with get_db_session() as db:
                # 查找失败代理正在执行的任务
                failed_agent = db.query(Agent).filter(Agent.id == failed_agent_id).first()
                if not failed_agent:
                    return {'error': '代理不存在'}
                
                # 查找该代理最近的任务结果（可能正在执行）
                recent_tasks = db.query(TaskResult).filter(
                    and_(
                        TaskResult.agent_id == failed_agent_id,
                        TaskResult.execution_time >= datetime.utcnow() - timedelta(minutes=30)
                    )
                ).all()
                
                # 获取可能需要重新分配的任务
                task_ids = [result.task_id for result in recent_tasks 
                           if result.status in [TaskResultStatus.TIMEOUT, TaskResultStatus.ERROR]]
                
                if not task_ids:
                    return {'reassigned_tasks': 0, 'message': '没有需要重新分配的任务'}
                
                # 获取任务详情
                tasks = db.query(Task).filter(
                    and_(
                        Task.id.in_(task_ids),
                        Task.status == TaskStatus.ACTIVE
                    )
                ).all()
                
                reassignment_results = []
                
                for task in tasks:
                    # 检查重新分配历史
                    if not self._can_reassign_task(task.id):
                        continue
                    
                    # 选择新的代理
                    new_agent = await self.task_allocator.select_agent(task)
                    if new_agent and new_agent.id != failed_agent_id:
                        # 记录重新分配
                        self._record_reassignment(task.id, failed_agent_id, new_agent.id)
                        
                        reassignment_results.append({
                            'task_id': str(task.id),
                            'task_name': task.name,
                            'old_agent_id': str(failed_agent_id),
                            'new_agent_id': str(new_agent.id),
                            'reassignment_time': datetime.utcnow().isoformat()
                        })
                
                return {
                    'failed_agent_id': str(failed_agent_id),
                    'reassigned_tasks': len(reassignment_results),
                    'reassignments': reassignment_results
                }
                
        except Exception as e:
            logger.error(f"处理代理故障时发生错误: {e}")
            return {'error': str(e)}
    
    def _can_reassign_task(self, task_id: uuid.UUID) -> bool:
        """检查任务是否可以重新分配"""
        history = self.reassignment_history.get(task_id, [])
        return len(history) < self.max_reassignments
    
    def _record_reassignment(self, task_id: uuid.UUID, old_agent_id: uuid.UUID, new_agent_id: uuid.UUID):
        """记录任务重新分配"""
        if task_id not in self.reassignment_history:
            self.reassignment_history[task_id] = []
        
        self.reassignment_history[task_id].append({
            'timestamp': datetime.utcnow(),
            'old_agent_id': old_agent_id,
            'new_agent_id': new_agent_id
        })
    
    async def handle_task_failure(self, task_id: uuid.UUID, failed_agent_id: uuid.UUID) -> Dict[str, Any]:
        """处理单个任务失败的重新分配"""
        try:
            if not self._can_reassign_task(task_id):
                return {
                    'reassigned': False,
                    'reason': '已达到最大重新分配次数'
                }
            
            async with get_db_session() as db:
                task = db.query(Task).filter(Task.id == task_id).first()
                if not task or task.status != TaskStatus.ACTIVE:
                    return {
                        'reassigned': False,
                        'reason': '任务不存在或不活跃'
                    }
                
                # 选择新的代理（排除失败的代理）
                available_agents = await self.task_allocator._get_available_agents(task)
                suitable_agents = await self.task_allocator._filter_suitable_agents(task, available_agents)
                
                # 过滤掉失败的代理
                suitable_agents = [agent for agent in suitable_agents if agent.id != failed_agent_id]
                
                if not suitable_agents:
                    return {
                        'reassigned': False,
                        'reason': '没有其他合适的代理可用'
                    }
                
                new_agent = await self.task_allocator.agent_selector.select_best_agent(task, suitable_agents)
                if new_agent:
                    self._record_reassignment(task_id, failed_agent_id, new_agent.id)
                    
                    return {
                        'reassigned': True,
                        'task_id': str(task_id),
                        'old_agent_id': str(failed_agent_id),
                        'new_agent_id': str(new_agent.id),
                        'reassignment_count': len(self.reassignment_history.get(task_id, []))
                    }
                else:
                    return {
                        'reassigned': False,
                        'reason': '无法选择合适的新代理'
                    }
                    
        except Exception as e:
            logger.error(f"处理任务失败重新分配时发生错误: {e}")
            return {'error': str(e)}
    
    async def get_reassignment_statistics(self) -> Dict[str, Any]:
        """获取重新分配统计信息"""
        total_reassignments = sum(len(history) for history in self.reassignment_history.values())
        tasks_with_reassignments = len(self.reassignment_history)
        
        # 计算重新分配频率
        if self.reassignment_history:
            all_reassignments = []
            for history in self.reassignment_history.values():
                all_reassignments.extend(history)
            
            # 按时间排序
            all_reassignments.sort(key=lambda x: x['timestamp'])
            
            # 计算最近24小时的重新分配
            recent_reassignments = [
                r for r in all_reassignments 
                if r['timestamp'] >= datetime.utcnow() - timedelta(hours=24)
            ]
            
            return {
                'total_reassignments': total_reassignments,
                'tasks_with_reassignments': tasks_with_reassignments,
                'recent_24h_reassignments': len(recent_reassignments),
                'avg_reassignments_per_task': total_reassignments / tasks_with_reassignments if tasks_with_reassignments > 0 else 0,
                'max_reassignments_per_task': max(len(history) for history in self.reassignment_history.values()) if self.reassignment_history else 0
            }
        else:
            return {
                'total_reassignments': 0,
                'tasks_with_reassignments': 0,
                'recent_24h_reassignments': 0,
                'avg_reassignments_per_task': 0,
                'max_reassignments_per_task': 0
            }
    
    def clear_old_reassignment_history(self, days: int = 7):
        """清理旧的重新分配历史"""
        cutoff_time = datetime.utcnow() - timedelta(days=days)
        
        for task_id in list(self.reassignment_history.keys()):
            history = self.reassignment_history[task_id]
            # 保留最近的记录
            recent_history = [r for r in history if r['timestamp'] >= cutoff_time]
            
            if recent_history:
                self.reassignment_history[task_id] = recent_history
            else:
                del self.reassignment_history[task_id]


class LoadBalancer:
    """负载均衡器"""
    
    def __init__(self, task_allocator: TaskAllocator):
        self.task_allocator = task_allocator
        self.load_threshold = 0.8  # 负载阈值
        self.rebalance_interval = 300  # 重新平衡间隔（秒）
        self.last_rebalance = datetime.utcnow()
    
    async def should_rebalance(self) -> bool:
        """检查是否需要重新平衡"""
        # 检查时间间隔
        if (datetime.utcnow() - self.last_rebalance).total_seconds() < self.rebalance_interval:
            return False
        
        # 检查负载分布
        rebalance_info = await self.task_allocator.rebalance_tasks()
        
        if 'load_variance' in rebalance_info:
            return rebalance_info['load_variance'] > 0.1
        
        return False
    
    async def perform_rebalance(self) -> Dict[str, Any]:
        """执行负载重新平衡"""
        try:
            async with get_db_session() as db:
                # 获取所有在线代理
                agents = db.query(Agent).filter(
                    Agent.status == AgentStatus.ONLINE
                ).all()
                
                if len(agents) < 2:
                    return {'rebalanced': False, 'reason': '代理数量不足'}
                
                # 计算每个代理的当前负载
                agent_loads = {}
                for agent in agents:
                    current_tasks = db.query(func.count(TaskResult.id)).filter(
                        and_(
                            TaskResult.agent_id == agent.id,
                            TaskResult.execution_time >= datetime.utcnow() - timedelta(minutes=10)
                        )
                    ).scalar() or 0
                    
                    load_ratio = current_tasks / agent.max_concurrent_tasks if agent.max_concurrent_tasks > 0 else 0
                    agent_loads[agent.id] = {
                        'agent': agent,
                        'current_tasks': current_tasks,
                        'load_ratio': load_ratio
                    }
                
                # 识别高负载和低负载代理
                avg_load = sum(info['load_ratio'] for info in agent_loads.values()) / len(agent_loads)
                
                high_load_agents = [
                    (agent_id, info) for agent_id, info in agent_loads.items()
                    if info['load_ratio'] > avg_load + 0.2
                ]
                
                low_load_agents = [
                    (agent_id, info) for agent_id, info in agent_loads.items()
                    if info['load_ratio'] < avg_load - 0.2
                ]
                
                if not high_load_agents or not low_load_agents:
                    return {'rebalanced': False, 'reason': '负载分布相对均衡'}
                
                # 执行重新平衡（这里只是记录建议，实际重新分配需要在调度器中实现）
                rebalance_suggestions = []
                
                for high_agent_id, high_info in high_load_agents:
                    for low_agent_id, low_info in low_load_agents:
                        if high_info['load_ratio'] - low_info['load_ratio'] > 0.3:
                            rebalance_suggestions.append({
                                'from_agent': str(high_agent_id),
                                'to_agent': str(low_agent_id),
                                'from_load': high_info['load_ratio'],
                                'to_load': low_info['load_ratio']
                            })
                
                self.last_rebalance = datetime.utcnow()
                
                return {
                    'rebalanced': True,
                    'rebalance_time': self.last_rebalance.isoformat(),
                    'suggestions': rebalance_suggestions,
                    'high_load_agents': len(high_load_agents),
                    'low_load_agents': len(low_load_agents)
                }
                
        except Exception as e:
            logger.error(f"执行负载重新平衡时发生错误: {e}")
            return {'error': str(e)}
    
    async def get_load_distribution(self) -> Dict[str, Any]:
        """获取当前负载分布"""
        try:
            async with get_db_session() as db:
                agents = db.query(Agent).filter(
                    Agent.status == AgentStatus.ONLINE
                ).all()
                
                load_distribution = []
                total_capacity = 0
                total_usage = 0
                
                for agent in agents:
                    current_tasks = db.query(func.count(TaskResult.id)).filter(
                        and_(
                            TaskResult.agent_id == agent.id,
                            TaskResult.execution_time >= datetime.utcnow() - timedelta(minutes=10)
                        )
                    ).scalar() or 0
                    
                    load_ratio = current_tasks / agent.max_concurrent_tasks if agent.max_concurrent_tasks > 0 else 0
                    
                    load_distribution.append({
                        'agent_id': str(agent.id),
                        'agent_name': agent.name,
                        'current_tasks': current_tasks,
                        'max_tasks': agent.max_concurrent_tasks,
                        'load_ratio': load_ratio,
                        'cpu_usage': agent.current_cpu_usage,
                        'memory_usage': agent.current_memory_usage
                    })
                    
                    total_capacity += agent.max_concurrent_tasks
                    total_usage += current_tasks
                
                overall_load = total_usage / total_capacity if total_capacity > 0 else 0
                
                return {
                    'agents': load_distribution,
                    'total_agents': len(agents),
                    'total_capacity': total_capacity,
                    'total_usage': total_usage,
                    'overall_load_ratio': overall_load,
                    'last_rebalance': self.last_rebalance.isoformat()
                }
                
        except Exception as e:
            logger.error(f"获取负载分布时发生错误: {e}")
            return {'error': str(e)}


class SmartTaskAllocator(TaskAllocator):
    """智能任务分配器（增强版）"""
    
    def __init__(self):
        super().__init__()
        self.reassignment_manager = TaskReassignmentManager(self)
        self.load_balancer = LoadBalancer(self)
        self.allocation_cache = {}  # 分配缓存
        self.cache_ttl = 60  # 缓存TTL（秒）
    
    async def select_agent_with_fallback(self, task: Task, exclude_agents: List[uuid.UUID] = None) -> Optional[Agent]:
        """带故障转移的代理选择"""
        exclude_agents = exclude_agents or []
        
        try:
            # 获取可用代理
            available_agents = await self._get_available_agents(task)
            
            # 排除指定的代理
            if exclude_agents:
                available_agents = [agent for agent in available_agents if agent.id not in exclude_agents]
            
            if not available_agents:
                logger.warning(f"没有可用的代理执行任务 {task.id}")
                return None
            
            # 过滤合适的代理
            suitable_agents = await self._filter_suitable_agents(task, available_agents)
            
            if not suitable_agents:
                # 如果没有完全合适的代理，尝试放宽条件
                logger.info(f"没有完全合适的代理，尝试放宽条件执行任务 {task.id}")
                suitable_agents = await self._filter_suitable_agents_relaxed(task, available_agents)
            
            if not suitable_agents:
                logger.warning(f"即使放宽条件也没有合适的代理执行任务 {task.id}")
                return None
            
            # 选择最佳代理
            best_agent = await self.agent_selector.select_best_agent(task, suitable_agents)
            
            # 缓存分配结果
            self._cache_allocation(task.id, best_agent.id if best_agent else None)
            
            return best_agent
            
        except Exception as e:
            logger.error(f"智能代理选择时发生错误: {e}")
            return None
    
    async def _filter_suitable_agents_relaxed(self, task: Task, agents: List[Agent]) -> List[Agent]:
        """放宽条件的代理过滤"""
        suitable_agents = []
        
        # 临时放宽负载阈值
        original_max_load = self.max_agent_load
        self.max_agent_load = 0.9  # 临时提高到90%
        
        # 临时放宽可用性阈值
        original_min_availability = self.min_agent_availability
        self.min_agent_availability = 0.5  # 临时降低到50%
        
        try:
            for agent in agents:
                # 检查基本能力（不放宽）
                if not self._check_agent_capabilities(task, agent):
                    continue
                
                # 放宽的负载检查
                if not self._check_agent_load(agent):
                    continue
                
                # 放宽的可用性检查
                if not await self._check_agent_availability(agent):
                    continue
                
                suitable_agents.append(agent)
        
        finally:
            # 恢复原始阈值
            self.max_agent_load = original_max_load
            self.min_agent_availability = original_min_availability
        
        return suitable_agents
    
    def _cache_allocation(self, task_id: uuid.UUID, agent_id: Optional[uuid.UUID]):
        """缓存分配结果"""
        self.allocation_cache[task_id] = {
            'agent_id': agent_id,
            'timestamp': datetime.utcnow()
        }
    
    def _get_cached_allocation(self, task_id: uuid.UUID) -> Optional[uuid.UUID]:
        """获取缓存的分配结果"""
        if task_id in self.allocation_cache:
            cache_entry = self.allocation_cache[task_id]
            if (datetime.utcnow() - cache_entry['timestamp']).total_seconds() < self.cache_ttl:
                return cache_entry['agent_id']
            else:
                # 缓存过期，删除
                del self.allocation_cache[task_id]
        
        return None
    
    async def handle_allocation_failure(self, task: Task, failed_agent_id: uuid.UUID) -> Optional[Agent]:
        """处理分配失败"""
        logger.info(f"处理任务 {task.id} 在代理 {failed_agent_id} 上的分配失败")
        
        # 尝试重新分配到其他代理
        return await self.reassignment_manager.handle_task_failure(task.id, failed_agent_id)
    
    async def optimize_allocation_strategy(self) -> Dict[str, Any]:
        """优化分配策略"""
        try:
            # 分析历史分配效果
            allocation_stats = await self.get_allocation_statistics()
            
            # 获取负载分布
            load_distribution = await self.load_balancer.get_load_distribution()
            
            # 获取重新分配统计
            reassignment_stats = await self.reassignment_manager.get_reassignment_statistics()
            
            # 基于统计数据调整权重
            optimization_suggestions = []
            
            # 如果重新分配频率过高，增加性能权重
            if reassignment_stats['total_reassignments'] > 10:
                optimization_suggestions.append({
                    'parameter': 'performance_weight',
                    'current_value': self.agent_selector.performance_weight,
                    'suggested_value': min(0.6, self.agent_selector.performance_weight + 0.1),
                    'reason': '重新分配频率过高，建议增加性能权重'
                })
            
            # 如果负载不均衡，增加负载权重
            if load_distribution.get('overall_load_ratio', 0) > 0.8:
                optimization_suggestions.append({
                    'parameter': 'load_weight',
                    'current_value': self.agent_selector.load_weight,
                    'suggested_value': min(0.5, self.agent_selector.load_weight + 0.1),
                    'reason': '整体负载较高，建议增加负载权重'
                })
            
            return {
                'current_strategy': {
                    'location_weight': self.agent_selector.location_weight,
                    'performance_weight': self.agent_selector.performance_weight,
                    'load_weight': self.agent_selector.load_weight
                },
                'optimization_suggestions': optimization_suggestions,
                'allocation_stats': allocation_stats,
                'load_distribution': load_distribution,
                'reassignment_stats': reassignment_stats
            }
            
        except Exception as e:
            logger.error(f"优化分配策略时发生错误: {e}")
            return {'error': str(e)}
    
    async def apply_optimization(self, optimizations: List[Dict[str, Any]]) -> bool:
        """应用优化建议"""
        try:
            for opt in optimizations:
                parameter = opt['parameter']
                new_value = opt['suggested_value']
                
                if parameter == 'location_weight':
                    self.agent_selector.location_weight = new_value
                elif parameter == 'performance_weight':
                    self.agent_selector.performance_weight = new_value
                elif parameter == 'load_weight':
                    self.agent_selector.load_weight = new_value
                
                logger.info(f"已应用优化: {parameter} = {new_value}")
            
            return True
            
        except Exception as e:
            logger.error(f"应用优化时发生错误: {e}")
            return False
    
    def cleanup_cache(self):
        """清理过期缓存"""
        current_time = datetime.utcnow()
        expired_keys = []
        
        for task_id, cache_entry in self.allocation_cache.items():
            if (current_time - cache_entry['timestamp']).total_seconds() > self.cache_ttl:
                expired_keys.append(task_id)
        
        for key in expired_keys:
            del self.allocation_cache[key]
        
        logger.debug(f"清理了 {len(expired_keys)} 个过期缓存条目")