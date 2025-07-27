"""任务分配器单元测试"""

import pytest
import uuid
from datetime import datetime, timedelta
from unittest.mock import Mock, patch, AsyncMock

from management_platform.scheduler.allocator import AgentSelector, TaskAllocator
from shared.models.task import Task, TaskResult, TaskResultStatus, ProtocolType
from shared.models.agent import Agent, AgentStatus


@pytest.fixture
def sample_task():
    """创建示例任务"""
    task = Mock(spec=Task)
    task.id = uuid.uuid4()
    task.name = "测试任务"
    task.protocol = ProtocolType.HTTP
    task.target = "example.com"
    task.preferred_location = "Beijing"
    task.preferred_isp = "China Telecom"
    return task


@pytest.fixture
def sample_agent():
    """创建示例代理"""
    agent = Mock(spec=Agent)
    agent.id = uuid.uuid4()
    agent.name = "测试代理"
    agent.status = AgentStatus.ONLINE
    agent.country = "China"
    agent.city = "Beijing"
    agent.isp = "China Telecom"
    agent.current_cpu_usage = 30.0
    agent.current_memory_usage = 40.0
    agent.availability = 0.95
    agent.success_rate = 0.90
    agent.avg_response_time = 150.0
    agent.capabilities = {"protocols": ["http", "https", "tcp", "udp", "icmp"]}
    agent.enabled = True
    agent.max_concurrent_tasks = 10
    agent.last_heartbeat = datetime.utcnow()
    return agent


@pytest.fixture
def agent_selector():
    """创建代理选择器实例"""
    return AgentSelector()


@pytest.fixture
def task_allocator():
    """创建任务分配器实例"""
    return TaskAllocator()


class TestAgentSelector:
    """AgentSelector测试类"""
    
    @pytest.mark.asyncio
    async def test_select_best_agent_empty_list(self, agent_selector, sample_task):
        """测试空代理列表的选择"""
        result = await agent_selector.select_best_agent(sample_task, [])
        assert result is None
    
    @pytest.mark.asyncio
    async def test_select_best_agent_single_agent(self, agent_selector, sample_task, sample_agent):
        """测试单个代理的选择"""
        with patch.object(agent_selector, '_calculate_agent_score', return_value=0.8):
            result = await agent_selector.select_best_agent(sample_task, [sample_agent])
            assert result == sample_agent
    
    @pytest.mark.asyncio
    async def test_select_best_agent_multiple_agents(self, agent_selector, sample_task):
        """测试多个代理的选择"""
        agent1 = Mock(spec=Agent)
        agent1.id = uuid.uuid4()
        agent2 = Mock(spec=Agent)
        agent2.id = uuid.uuid4()
        
        # 模拟不同的评分
        async def mock_calculate_score(task, agent):
            if agent == agent1:
                return 0.9
            else:
                return 0.7
        
        with patch.object(agent_selector, '_calculate_agent_score', side_effect=mock_calculate_score):
            result = await agent_selector.select_best_agent(sample_task, [agent1, agent2])
            assert result == agent1  # 应该选择评分更高的代理
    
    def test_calculate_location_score_perfect_match(self, agent_selector, sample_task, sample_agent):
        """测试完美位置匹配的评分"""
        sample_task.preferred_location = "Beijing"
        sample_task.preferred_isp = "China Telecom"
        sample_agent.country = "China"
        sample_agent.city = "Beijing"
        sample_agent.isp = "China Telecom"
        
        score = agent_selector._calculate_location_score(sample_task, sample_agent)
        assert score > 0.5  # 应该高于基础分数
    
    def test_calculate_location_score_no_preference(self, agent_selector, sample_task, sample_agent):
        """测试无偏好设置的评分"""
        sample_task.preferred_location = None
        sample_task.preferred_isp = None
        
        score = agent_selector._calculate_location_score(sample_task, sample_agent)
        assert score == 0.5  # 应该等于基础分数
    
    def test_calculate_location_score_partial_match(self, agent_selector, sample_task, sample_agent):
        """测试部分匹配的评分"""
        sample_task.preferred_location = "Beijing"
        sample_task.preferred_isp = "China Mobile"  # 不匹配
        sample_agent.country = "China"
        sample_agent.city = "Beijing"
        sample_agent.isp = "China Telecom"
        
        score = agent_selector._calculate_location_score(sample_task, sample_agent)
        assert 0.5 < score < 1.0  # 应该在基础分数和满分之间
    
    @pytest.mark.asyncio
    @patch('management_platform.scheduler.allocator.get_db_session')
    async def test_calculate_performance_score_no_history(self, mock_db_session, agent_selector, sample_task, sample_agent):
        """测试无历史数据时的性能评分"""
        # 模拟数据库会话
        mock_db = Mock()
        mock_db_session.return_value.__aenter__.return_value = mock_db
        mock_db.query.return_value.filter.return_value.limit.return_value.all.return_value = []
        
        score = await agent_selector._calculate_performance_score(sample_task, sample_agent)
        assert score == 0.5  # 无历史数据时应该返回中等分数
    
    @pytest.mark.asyncio
    @patch('management_platform.scheduler.allocator.get_db_session')
    async def test_calculate_performance_score_with_history(self, mock_db_session, agent_selector, sample_task, sample_agent):
        """测试有历史数据时的性能评分"""
        # 创建模拟的任务结果
        successful_result = Mock(spec=TaskResult)
        successful_result.status = TaskResultStatus.SUCCESS
        successful_result.duration = 100.0
        
        failed_result = Mock(spec=TaskResult)
        failed_result.status = TaskResultStatus.ERROR
        failed_result.duration = None
        
        # 模拟数据库会话
        mock_db = Mock()
        mock_db_session.return_value.__aenter__.return_value = mock_db
        mock_db.query.return_value.filter.return_value.limit.return_value.all.return_value = [
            successful_result, successful_result, failed_result
        ]
        
        score = await agent_selector._calculate_performance_score(sample_task, sample_agent)
        assert 0 <= score <= 1.0
        assert score > 0.5  # 有成功记录应该高于基础分数
    
    def test_calculate_load_score_low_load(self, agent_selector, sample_agent):
        """测试低负载的评分"""
        sample_agent.current_cpu_usage = 20.0
        sample_agent.current_memory_usage = 30.0
        
        score = agent_selector._calculate_load_score(sample_agent)
        assert score > 0.5  # 低负载应该有较高评分
    
    def test_calculate_load_score_high_load(self, agent_selector, sample_agent):
        """测试高负载的评分"""
        sample_agent.current_cpu_usage = 90.0
        sample_agent.current_memory_usage = 85.0
        
        score = agent_selector._calculate_load_score(sample_agent)
        assert score < 0.5  # 高负载应该有较低评分
    
    def test_calculate_load_score_no_data(self, agent_selector, sample_agent):
        """测试无负载数据的评分"""
        sample_agent.current_cpu_usage = None
        sample_agent.current_memory_usage = None
        
        score = agent_selector._calculate_load_score(sample_agent)
        assert score == 1.0  # 无数据时应该给满分


class TestTaskAllocator:
    """TaskAllocator测试类"""
    
    @pytest.mark.asyncio
    @patch('management_platform.scheduler.allocator.get_db_session')
    async def test_get_available_agents(self, mock_db_session, task_allocator, sample_task):
        """测试获取可用代理列表"""
        # 创建模拟代理
        online_agent = Mock(spec=Agent)
        online_agent.status = AgentStatus.ONLINE
        online_agent.enabled = True
        online_agent.last_heartbeat = datetime.utcnow()
        
        offline_agent = Mock(spec=Agent)
        offline_agent.status = AgentStatus.OFFLINE
        offline_agent.enabled = True
        offline_agent.last_heartbeat = datetime.utcnow()
        
        # 模拟数据库会话
        mock_db = Mock()
        mock_db_session.return_value.__aenter__.return_value = mock_db
        mock_db.query.return_value.filter.return_value.all.return_value = [online_agent]
        
        agents = await task_allocator._get_available_agents(sample_task)
        assert len(agents) == 1
        assert agents[0] == online_agent
    
    def test_check_agent_capabilities_supported(self, task_allocator, sample_task, sample_agent):
        """测试代理能力检查 - 支持的协议"""
        sample_task.protocol = ProtocolType.HTTP
        sample_agent.capabilities = {"protocols": ["http", "https", "tcp"]}
        
        result = task_allocator._check_agent_capabilities(sample_task, sample_agent)
        assert result is True
    
    def test_check_agent_capabilities_not_supported(self, task_allocator, sample_task, sample_agent):
        """测试代理能力检查 - 不支持的协议"""
        sample_task.protocol = ProtocolType.UDP
        sample_agent.capabilities = {"protocols": ["http", "https", "tcp"]}
        
        result = task_allocator._check_agent_capabilities(sample_task, sample_agent)
        assert result is False
    
    def test_check_agent_capabilities_no_info(self, task_allocator, sample_task, sample_agent):
        """测试代理能力检查 - 无能力信息"""
        sample_agent.capabilities = None
        
        result = task_allocator._check_agent_capabilities(sample_task, sample_agent)
        assert result is True  # 无信息时假设支持所有协议
    
    def test_check_agent_load_acceptable(self, task_allocator, sample_agent):
        """测试代理负载检查 - 可接受的负载"""
        sample_agent.current_cpu_usage = 50.0
        sample_agent.current_memory_usage = 60.0
        task_allocator.max_agent_load = 0.8
        
        result = task_allocator._check_agent_load(sample_agent)
        assert result is True
    
    def test_check_agent_load_too_high(self, task_allocator, sample_agent):
        """测试代理负载检查 - 负载过高"""
        sample_agent.current_cpu_usage = 90.0
        sample_agent.current_memory_usage = 60.0
        task_allocator.max_agent_load = 0.8
        
        result = task_allocator._check_agent_load(sample_agent)
        assert result is False
    
    @pytest.mark.asyncio
    async def test_check_agent_availability_good(self, task_allocator, sample_agent):
        """测试代理可用性检查 - 良好的可用性"""
        sample_agent.availability = 0.95
        task_allocator.min_agent_availability = 0.7
        
        result = await task_allocator._check_agent_availability(sample_agent)
        assert result is True
    
    @pytest.mark.asyncio
    async def test_check_agent_availability_poor(self, task_allocator, sample_agent):
        """测试代理可用性检查 - 较差的可用性"""
        sample_agent.availability = 0.5
        task_allocator.min_agent_availability = 0.7
        
        result = await task_allocator._check_agent_availability(sample_agent)
        assert result is False
    
    @pytest.mark.asyncio
    async def test_filter_suitable_agents(self, task_allocator, sample_task):
        """测试过滤合适的代理"""
        # 创建不同类型的代理
        good_agent = Mock(spec=Agent)
        good_agent.capabilities = {"protocols": ["http"]}
        good_agent.current_cpu_usage = 50.0
        good_agent.current_memory_usage = 50.0
        good_agent.availability = 0.9
        
        overloaded_agent = Mock(spec=Agent)
        overloaded_agent.capabilities = {"protocols": ["http"]}
        overloaded_agent.current_cpu_usage = 95.0
        overloaded_agent.current_memory_usage = 50.0
        overloaded_agent.availability = 0.9
        
        low_availability_agent = Mock(spec=Agent)
        low_availability_agent.capabilities = {"protocols": ["http"]}
        low_availability_agent.current_cpu_usage = 50.0
        low_availability_agent.current_memory_usage = 50.0
        low_availability_agent.availability = 0.5
        
        sample_task.protocol = ProtocolType.HTTP
        agents = [good_agent, overloaded_agent, low_availability_agent]
        
        suitable_agents = await task_allocator._filter_suitable_agents(sample_task, agents)
        
        assert len(suitable_agents) == 1
        assert suitable_agents[0] == good_agent
    
    @pytest.mark.asyncio
    async def test_select_agent_success(self, task_allocator, sample_task, sample_agent):
        """测试成功选择代理"""
        # 模拟方法
        task_allocator._get_available_agents = AsyncMock(return_value=[sample_agent])
        task_allocator._filter_suitable_agents = AsyncMock(return_value=[sample_agent])
        task_allocator.agent_selector.select_best_agent = AsyncMock(return_value=sample_agent)
        
        result = await task_allocator.select_agent(sample_task)
        
        assert result == sample_agent
        task_allocator._get_available_agents.assert_called_once_with(sample_task)
        task_allocator._filter_suitable_agents.assert_called_once_with(sample_task, [sample_agent])
        task_allocator.agent_selector.select_best_agent.assert_called_once_with(sample_task, [sample_agent])
    
    @pytest.mark.asyncio
    async def test_select_agent_no_available(self, task_allocator, sample_task):
        """测试无可用代理时的选择"""
        task_allocator._get_available_agents = AsyncMock(return_value=[])
        
        result = await task_allocator.select_agent(sample_task)
        
        assert result is None
    
    @pytest.mark.asyncio
    async def test_select_agent_no_suitable(self, task_allocator, sample_task, sample_agent):
        """测试无合适代理时的选择"""
        task_allocator._get_available_agents = AsyncMock(return_value=[sample_agent])
        task_allocator._filter_suitable_agents = AsyncMock(return_value=[])
        
        result = await task_allocator.select_agent(sample_task)
        
        assert result is None
    
    @pytest.mark.asyncio
    async def test_allocate_tasks_to_agents(self, task_allocator, sample_task, sample_agent):
        """测试批量分配任务到代理"""
        # 创建多个任务
        task1 = Mock(spec=Task)
        task1.id = uuid.uuid4()
        task2 = Mock(spec=Task)
        task2.id = uuid.uuid4()
        
        tasks = [task1, task2]
        
        # 模拟方法
        task_allocator._get_available_agents = AsyncMock(return_value=[sample_agent])
        task_allocator._filter_suitable_agents = AsyncMock(return_value=[sample_agent])
        task_allocator.agent_selector.select_best_agent = AsyncMock(return_value=sample_agent)
        
        result = await task_allocator.allocate_tasks_to_agents(tasks)
        
        assert len(result) == 2
        assert result[task1.id] == sample_agent.id
        assert result[task2.id] == sample_agent.id
    
    @pytest.mark.asyncio
    @patch('management_platform.scheduler.allocator.get_db_session')
    async def test_rebalance_tasks(self, mock_db_session, task_allocator):
        """测试重新平衡任务"""
        # 创建模拟代理
        agent1 = Mock(spec=Agent)
        agent1.id = uuid.uuid4()
        agent1.max_concurrent_tasks = 10
        
        agent2 = Mock(spec=Agent)
        agent2.id = uuid.uuid4()
        agent2.max_concurrent_tasks = 10
        
        # 模拟数据库会话
        mock_db = Mock()
        mock_db_session.return_value.__aenter__.return_value = mock_db
        mock_db.query.return_value.filter.return_value.all.return_value = [agent1, agent2]
        
        # 模拟任务计数查询
        mock_db.query.return_value.filter.return_value.scalar.side_effect = [5, 2]  # agent1有5个任务，agent2有2个任务
        
        result = await task_allocator.rebalance_tasks()
        
        assert 'total_agents' in result
        assert 'average_load' in result
        assert 'load_variance' in result
        assert 'agent_loads' in result
        assert result['total_agents'] == 2
    
    @pytest.mark.asyncio
    @patch('management_platform.scheduler.allocator.get_db_session')
    async def test_get_allocation_statistics(self, mock_db_session, task_allocator):
        """测试获取分配统计信息"""
        # 模拟数据库会话
        mock_db = Mock()
        mock_db_session.return_value.__aenter__.return_value = mock_db
        
        # 模拟统计查询结果
        mock_db.query.return_value.filter.return_value.scalar.side_effect = [100, 80]  # 总任务100，成功80
        
        # 模拟代理统计
        agent_stat = Mock()
        agent_stat.agent_id = uuid.uuid4()
        agent_stat.task_count = 50
        agent_stat.success_count = 40
        agent_stat.avg_duration = 150.0
        
        mock_db.query.return_value.filter.return_value.group_by.return_value.all.return_value = [agent_stat]
        
        # 模拟代理查询
        agent = Mock(spec=Agent)
        agent.name = "测试代理"
        mock_db.query.return_value.filter.return_value.first.return_value = agent
        
        result = await task_allocator.get_allocation_statistics()
        
        assert 'total_tasks' in result
        assert 'successful_tasks' in result
        assert 'success_rate' in result
        assert 'agent_statistics' in result
        assert result['total_tasks'] == 100
        assert result['successful_tasks'] == 80
        assert result['success_rate'] == 0.8
        assert len(result['agent_statistics']) == 1
    
    @pytest.mark.asyncio
    async def test_predict_optimal_allocation(self, task_allocator, sample_task, sample_agent):
        """测试预测最优分配"""
        # 模拟方法
        task_allocator._get_available_agents = AsyncMock(return_value=[sample_agent])
        task_allocator._filter_suitable_agents = AsyncMock(return_value=[sample_agent])
        
        # 模拟评分计算
        task_allocator.agent_selector._calculate_location_score = Mock(return_value=0.8)
        task_allocator.agent_selector._calculate_performance_score = AsyncMock(return_value=0.9)
        task_allocator.agent_selector._calculate_load_score = Mock(return_value=0.7)
        
        result = await task_allocator.predict_optimal_allocation(sample_task)
        
        assert result['prediction'] == 'success'
        assert 'recommended_agent' in result
        assert 'all_candidates' in result
        assert 'selection_criteria' in result
        
        recommended = result['recommended_agent']
        assert recommended['agent_id'] == str(sample_agent.id)
        assert 'total_score' in recommended
        assert 'location_score' in recommended
        assert 'performance_score' in recommended
        assert 'load_score' in recommended
    
    @pytest.mark.asyncio
    async def test_predict_optimal_allocation_no_agents(self, task_allocator, sample_task):
        """测试无合适代理时的预测"""
        task_allocator._get_available_agents = AsyncMock(return_value=[])
        task_allocator._filter_suitable_agents = AsyncMock(return_value=[])
        
        result = await task_allocator.predict_optimal_allocation(sample_task)
        
        assert result['prediction'] == 'no_suitable_agents'
        assert 'message' in result


if __name__ == "__main__":
    pytest.main([__file__])


class TestTaskReassignmentManager:
    """TaskReassignmentManager测试类"""
    
    @pytest.fixture
    def task_allocator(self):
        return TaskAllocator()
    
    @pytest.fixture
    def reassignment_manager(self, task_allocator):
        from management_platform.scheduler.allocator import TaskReassignmentManager
        return TaskReassignmentManager(task_allocator)
    
    def test_can_reassign_task_new_task(self, reassignment_manager):
        """测试新任务的重新分配检查"""
        task_id = uuid.uuid4()
        assert reassignment_manager._can_reassign_task(task_id) is True
    
    def test_can_reassign_task_max_reached(self, reassignment_manager):
        """测试达到最大重新分配次数的检查"""
        task_id = uuid.uuid4()
        
        # 模拟达到最大重新分配次数
        reassignment_manager.reassignment_history[task_id] = [
            {'timestamp': datetime.utcnow(), 'old_agent_id': uuid.uuid4(), 'new_agent_id': uuid.uuid4()}
            for _ in range(reassignment_manager.max_reassignments)
        ]
        
        assert reassignment_manager._can_reassign_task(task_id) is False
    
    def test_record_reassignment(self, reassignment_manager):
        """测试记录重新分配"""
        task_id = uuid.uuid4()
        old_agent_id = uuid.uuid4()
        new_agent_id = uuid.uuid4()
        
        reassignment_manager._record_reassignment(task_id, old_agent_id, new_agent_id)
        
        assert task_id in reassignment_manager.reassignment_history
        assert len(reassignment_manager.reassignment_history[task_id]) == 1
        
        record = reassignment_manager.reassignment_history[task_id][0]
        assert record['old_agent_id'] == old_agent_id
        assert record['new_agent_id'] == new_agent_id
    
    @pytest.mark.asyncio
    @patch('management_platform.scheduler.allocator.get_db_session')
    async def test_handle_agent_failure(self, mock_db_session, reassignment_manager):
        """测试处理代理故障"""
        failed_agent_id = uuid.uuid4()
        
        # 模拟数据库会话
        mock_db = Mock()
        mock_db_session.return_value.__aenter__.return_value = mock_db
        
        # 模拟失败的代理
        failed_agent = Mock(spec=Agent)
        failed_agent.id = failed_agent_id
        mock_db.query.return_value.filter.return_value.first.return_value = failed_agent
        
        # 模拟任务结果
        task_result = Mock(spec=TaskResult)
        task_result.task_id = uuid.uuid4()
        task_result.status = TaskResultStatus.ERROR
        mock_db.query.return_value.filter.return_value.all.return_value = [task_result]
        
        # 模拟任务
        task = Mock(spec=Task)
        task.id = task_result.task_id
        task.name = "测试任务"
        task.status = TaskStatus.ACTIVE
        mock_db.query.return_value.filter.return_value.all.return_value = [task]
        
        # 模拟新代理选择
        new_agent = Mock(spec=Agent)
        new_agent.id = uuid.uuid4()
        reassignment_manager.task_allocator.select_agent = AsyncMock(return_value=new_agent)
        
        result = await reassignment_manager.handle_agent_failure(failed_agent_id)
        
        assert 'reassigned_tasks' in result
        assert result['reassigned_tasks'] >= 0
    
    @pytest.mark.asyncio
    async def test_get_reassignment_statistics_empty(self, reassignment_manager):
        """测试空重新分配历史的统计"""
        stats = await reassignment_manager.get_reassignment_statistics()
        
        assert stats['total_reassignments'] == 0
        assert stats['tasks_with_reassignments'] == 0
        assert stats['recent_24h_reassignments'] == 0
        assert stats['avg_reassignments_per_task'] == 0
        assert stats['max_reassignments_per_task'] == 0
    
    @pytest.mark.asyncio
    async def test_get_reassignment_statistics_with_data(self, reassignment_manager):
        """测试有数据的重新分配统计"""
        # 添加一些重新分配历史
        task_id1 = uuid.uuid4()
        task_id2 = uuid.uuid4()
        
        reassignment_manager.reassignment_history[task_id1] = [
            {'timestamp': datetime.utcnow(), 'old_agent_id': uuid.uuid4(), 'new_agent_id': uuid.uuid4()},
            {'timestamp': datetime.utcnow(), 'old_agent_id': uuid.uuid4(), 'new_agent_id': uuid.uuid4()}
        ]
        
        reassignment_manager.reassignment_history[task_id2] = [
            {'timestamp': datetime.utcnow(), 'old_agent_id': uuid.uuid4(), 'new_agent_id': uuid.uuid4()}
        ]
        
        stats = await reassignment_manager.get_reassignment_statistics()
        
        assert stats['total_reassignments'] == 3
        assert stats['tasks_with_reassignments'] == 2
        assert stats['avg_reassignments_per_task'] == 1.5
        assert stats['max_reassignments_per_task'] == 2
    
    def test_clear_old_reassignment_history(self, reassignment_manager):
        """测试清理旧的重新分配历史"""
        task_id = uuid.uuid4()
        
        # 添加新旧记录
        old_record = {
            'timestamp': datetime.utcnow() - timedelta(days=10),
            'old_agent_id': uuid.uuid4(),
            'new_agent_id': uuid.uuid4()
        }
        
        new_record = {
            'timestamp': datetime.utcnow(),
            'old_agent_id': uuid.uuid4(),
            'new_agent_id': uuid.uuid4()
        }
        
        reassignment_manager.reassignment_history[task_id] = [old_record, new_record]
        
        # 清理7天前的记录
        reassignment_manager.clear_old_reassignment_history(days=7)
        
        # 应该只保留新记录
        assert len(reassignment_manager.reassignment_history[task_id]) == 1
        assert reassignment_manager.reassignment_history[task_id][0] == new_record


class TestLoadBalancer:
    """LoadBalancer测试类"""
    
    @pytest.fixture
    def task_allocator(self):
        return TaskAllocator()
    
    @pytest.fixture
    def load_balancer(self, task_allocator):
        from management_platform.scheduler.allocator import LoadBalancer
        return LoadBalancer(task_allocator)
    
    @pytest.mark.asyncio
    async def test_should_rebalance_time_interval(self, load_balancer):
        """测试时间间隔的重新平衡检查"""
        # 刚刚重新平衡过
        load_balancer.last_rebalance = datetime.utcnow()
        
        result = await load_balancer.should_rebalance()
        assert result is False
    
    @pytest.mark.asyncio
    async def test_should_rebalance_high_variance(self, load_balancer):
        """测试高方差时的重新平衡检查"""
        # 设置足够的时间间隔
        load_balancer.last_rebalance = datetime.utcnow() - timedelta(seconds=400)
        
        # 模拟高方差的重新平衡信息
        load_balancer.task_allocator.rebalance_tasks = AsyncMock(return_value={
            'load_variance': 0.2  # 高于阈值0.1
        })
        
        result = await load_balancer.should_rebalance()
        assert result is True
    
    @pytest.mark.asyncio
    @patch('management_platform.scheduler.allocator.get_db_session')
    async def test_get_load_distribution(self, mock_db_session, load_balancer):
        """测试获取负载分布"""
        # 模拟数据库会话
        mock_db = Mock()
        mock_db_session.return_value.__aenter__.return_value = mock_db
        
        # 模拟代理
        agent = Mock(spec=Agent)
        agent.id = uuid.uuid4()
        agent.name = "测试代理"
        agent.max_concurrent_tasks = 10
        agent.current_cpu_usage = 50.0
        agent.current_memory_usage = 60.0
        
        mock_db.query.return_value.filter.return_value.all.return_value = [agent]
        
        # 模拟任务计数
        mock_db.query.return_value.filter.return_value.scalar.return_value = 5
        
        result = await load_balancer.get_load_distribution()
        
        assert 'agents' in result
        assert 'total_agents' in result
        assert 'total_capacity' in result
        assert 'total_usage' in result
        assert 'overall_load_ratio' in result
        
        assert result['total_agents'] == 1
        assert result['total_capacity'] == 10
        assert result['total_usage'] == 5
        assert result['overall_load_ratio'] == 0.5


class TestSmartTaskAllocator:
    """SmartTaskAllocator测试类"""
    
    @pytest.fixture
    def smart_allocator(self):
        from management_platform.scheduler.allocator import SmartTaskAllocator
        return SmartTaskAllocator()
    
    @pytest.mark.asyncio
    async def test_select_agent_with_fallback_success(self, smart_allocator, sample_task, sample_agent):
        """测试成功的故障转移代理选择"""
        # 模拟方法
        smart_allocator._get_available_agents = AsyncMock(return_value=[sample_agent])
        smart_allocator._filter_suitable_agents = AsyncMock(return_value=[sample_agent])
        smart_allocator.agent_selector.select_best_agent = AsyncMock(return_value=sample_agent)
        
        result = await smart_allocator.select_agent_with_fallback(sample_task)
        
        assert result == sample_agent
        smart_allocator._get_available_agents.assert_called_once_with(sample_task)
        smart_allocator._filter_suitable_agents.assert_called_once_with(sample_task, [sample_agent])
    
    @pytest.mark.asyncio
    async def test_select_agent_with_fallback_exclude_agents(self, smart_allocator, sample_task, sample_agent):
        """测试排除指定代理的选择"""
        excluded_agent = Mock(spec=Agent)
        excluded_agent.id = uuid.uuid4()
        
        # 模拟方法
        smart_allocator._get_available_agents = AsyncMock(return_value=[sample_agent, excluded_agent])
        smart_allocator._filter_suitable_agents = AsyncMock(return_value=[sample_agent])
        smart_allocator.agent_selector.select_best_agent = AsyncMock(return_value=sample_agent)
        
        result = await smart_allocator.select_agent_with_fallback(
            sample_task, 
            exclude_agents=[excluded_agent.id]
        )
        
        assert result == sample_agent
        # 验证排除了指定代理
        call_args = smart_allocator._filter_suitable_agents.call_args[0][1]
        assert excluded_agent not in call_args
        assert sample_agent in call_args
    
    @pytest.mark.asyncio
    async def test_select_agent_with_fallback_relaxed_conditions(self, smart_allocator, sample_task, sample_agent):
        """测试放宽条件的代理选择"""
        # 模拟严格条件下无合适代理，放宽条件后有代理
        smart_allocator._get_available_agents = AsyncMock(return_value=[sample_agent])
        smart_allocator._filter_suitable_agents = AsyncMock(return_value=[])  # 严格条件下无代理
        smart_allocator._filter_suitable_agents_relaxed = AsyncMock(return_value=[sample_agent])  # 放宽条件后有代理
        smart_allocator.agent_selector.select_best_agent = AsyncMock(return_value=sample_agent)
        
        result = await smart_allocator.select_agent_with_fallback(sample_task)
        
        assert result == sample_agent
        smart_allocator._filter_suitable_agents_relaxed.assert_called_once()
    
    def test_cache_allocation(self, smart_allocator, sample_task, sample_agent):
        """测试缓存分配结果"""
        smart_allocator._cache_allocation(sample_task.id, sample_agent.id)
        
        assert sample_task.id in smart_allocator.allocation_cache
        cache_entry = smart_allocator.allocation_cache[sample_task.id]
        assert cache_entry['agent_id'] == sample_agent.id
        assert 'timestamp' in cache_entry
    
    def test_get_cached_allocation_valid(self, smart_allocator, sample_task, sample_agent):
        """测试获取有效的缓存分配"""
        smart_allocator._cache_allocation(sample_task.id, sample_agent.id)
        
        cached_agent_id = smart_allocator._get_cached_allocation(sample_task.id)
        assert cached_agent_id == sample_agent.id
    
    def test_get_cached_allocation_expired(self, smart_allocator, sample_task, sample_agent):
        """测试获取过期的缓存分配"""
        # 手动设置过期的缓存
        smart_allocator.allocation_cache[sample_task.id] = {
            'agent_id': sample_agent.id,
            'timestamp': datetime.utcnow() - timedelta(seconds=120)  # 超过TTL
        }
        
        cached_agent_id = smart_allocator._get_cached_allocation(sample_task.id)
        assert cached_agent_id is None
        assert sample_task.id not in smart_allocator.allocation_cache  # 应该被删除
    
    def test_cleanup_cache(self, smart_allocator, sample_task, sample_agent):
        """测试清理过期缓存"""
        # 添加有效和过期的缓存条目
        valid_task_id = uuid.uuid4()
        expired_task_id = uuid.uuid4()
        
        smart_allocator.allocation_cache[valid_task_id] = {
            'agent_id': sample_agent.id,
            'timestamp': datetime.utcnow()
        }
        
        smart_allocator.allocation_cache[expired_task_id] = {
            'agent_id': sample_agent.id,
            'timestamp': datetime.utcnow() - timedelta(seconds=120)
        }
        
        smart_allocator.cleanup_cache()
        
        assert valid_task_id in smart_allocator.allocation_cache
        assert expired_task_id not in smart_allocator.allocation_cache
    
    @pytest.mark.asyncio
    async def test_optimize_allocation_strategy(self, smart_allocator):
        """测试优化分配策略"""
        # 模拟各种统计信息
        smart_allocator.get_allocation_statistics = AsyncMock(return_value={
            'total_tasks': 100,
            'success_rate': 0.8
        })
        
        smart_allocator.load_balancer.get_load_distribution = AsyncMock(return_value={
            'overall_load_ratio': 0.9
        })
        
        smart_allocator.reassignment_manager.get_reassignment_statistics = AsyncMock(return_value={
            'total_reassignments': 15
        })
        
        result = await smart_allocator.optimize_allocation_strategy()
        
        assert 'current_strategy' in result
        assert 'optimization_suggestions' in result
        assert 'allocation_stats' in result
        assert 'load_distribution' in result
        assert 'reassignment_stats' in result
        
        # 检查是否有优化建议
        suggestions = result['optimization_suggestions']
        assert len(suggestions) > 0  # 应该有建议因为重新分配次数>10且负载>0.8
    
    @pytest.mark.asyncio
    async def test_apply_optimization(self, smart_allocator):
        """测试应用优化建议"""
        optimizations = [
            {
                'parameter': 'performance_weight',
                'suggested_value': 0.5
            },
            {
                'parameter': 'load_weight',
                'suggested_value': 0.4
            }
        ]
        
        result = await smart_allocator.apply_optimization(optimizations)
        
        assert result is True
        assert smart_allocator.agent_selector.performance_weight == 0.5
        assert smart_allocator.agent_selector.load_weight == 0.4