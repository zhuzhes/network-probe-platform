"""任务执行集成测试"""

import pytest
import asyncio
import uuid
from unittest.mock import Mock, patch, AsyncMock

from agent.core.agent import Agent
from agent.core.executor import TaskExecutor, TaskResultCollector
from agent.protocols.base import ProtocolResult, ProtocolTestStatus
from shared.models.task import ProtocolType


@pytest.fixture
def mock_config():
    """模拟配置"""
    config = Mock()
    config.agent_id = "test-agent-123"
    config.agent_name = "测试代理"
    config.server_url = "wss://test.example.com/ws"
    config.api_key = "test-api-key"
    config.heartbeat_interval = 30
    config.resource_report_interval = 60
    config.max_concurrent_tasks = 5
    config.default_task_timeout = 30
    config.result_batch_size = 10
    config.result_batch_timeout = 30
    config.cert_file = None
    config.key_file = None
    config.get_all.return_value = {
        'agent_id': config.agent_id,
        'agent_name': config.agent_name,
        'server_url': config.server_url,
        'max_concurrent_tasks': config.max_concurrent_tasks
    }
    config.save_local_config = Mock()
    return config


@pytest.fixture
def sample_task_data():
    """示例任务数据"""
    return {
        'id': str(uuid.uuid4()),
        'protocol': 'http',
        'target': 'example.com',
        'port': 80,
        'timeout': 30,
        'parameters': {'method': 'GET'}
    }


class TestTaskExecutorIntegration:
    """任务执行器集成测试"""
    
    @pytest.mark.asyncio
    async def test_task_executor_lifecycle(self):
        """测试任务执行器生命周期"""
        executor = TaskExecutor(
            agent_id="test-agent",
            max_concurrent_tasks=3,
            default_timeout=30
        )
        
        # 启动执行器
        await executor.start()
        assert executor._running is True
        
        # 获取状态
        stats = executor.get_statistics()
        assert stats['agent_id'] == "test-agent"
        assert stats['running'] is True
        assert stats['current_executions'] == 0
        
        # 健康检查
        health = await executor.health_check()
        assert health['status'] == 'healthy'
        assert health['current_load'] == 0.0
        
        # 停止执行器
        await executor.stop()
        assert executor._running is False
    
    @pytest.mark.asyncio
    async def test_task_execution_with_mock_protocol(self, sample_task_data):
        """测试使用模拟协议的任务执行"""
        # 创建结果收集器
        results = []
        
        async def collect_result(result_data):
            results.append(result_data)
        
        collector = TaskResultCollector(
            agent_id="test-agent",
            batch_size=1,  # 立即发送
            batch_timeout=1,
            send_callback=collect_result
        )
        
        # 创建任务执行器
        executor = TaskExecutor(
            agent_id="test-agent",
            max_concurrent_tasks=5,
            default_timeout=30,
            result_callback=collector.collect_result
        )
        
        # 模拟协议处理器
        mock_handler = AsyncMock()
        mock_result = ProbeResult(
            status=ProbeStatus.SUCCESS,
            response_time=150.0,
            metrics={'status_code': 200, 'response_time': 150.0},
            raw_data={'headers': {'content-type': 'text/html'}}
        )
        mock_handler.probe.return_value = mock_result
        
        executor.protocol_registry.get_handler = Mock(return_value=mock_handler)
        
        # 启动组件
        await collector.start()
        await executor.start()
        
        try:
            # 执行任务
            success = await executor.execute_task(sample_task_data)
            assert success is True
            
            # 等待任务完成
            await asyncio.sleep(0.2)
            
            # 验证协议处理器被调用
            mock_handler.probe.assert_called_once_with(
                'example.com', 80, {'method': 'GET'}
            )
            
            # 等待结果收集
            await asyncio.sleep(0.2)
            
            # 验证结果被收集
            assert len(results) == 1
            batch_data = results[0]
            assert batch_data['agent_id'] == "test-agent"
            assert len(batch_data['results']) == 1
            
            result = batch_data['results'][0]
            assert result['task_id'] == sample_task_data['id']
            assert result['agent_id'] == "test-agent"
            assert result['status'] == 'completed'
            assert result['probe_status'] == 'success'
            assert result['metrics']['status_code'] == 200
            
        finally:
            await executor.stop()
            await collector.stop()
    
    @pytest.mark.asyncio
    async def test_task_execution_failure_and_retry(self, sample_task_data):
        """测试任务执行失败和重试"""
        results = []
        
        async def collect_result(result_data):
            results.append(result_data)
        
        collector = TaskResultCollector(
            agent_id="test-agent",
            batch_size=1,
            batch_timeout=1,
            send_callback=collect_result
        )
        
        executor = TaskExecutor(
            agent_id="test-agent",
            max_concurrent_tasks=5,
            default_timeout=30,
            result_callback=collector.collect_result
        )
        
        # 模拟失败的协议处理器
        mock_handler = AsyncMock()
        mock_handler.probe.side_effect = Exception("网络连接失败")
        
        executor.protocol_registry.get_handler = Mock(return_value=mock_handler)
        
        await collector.start()
        await executor.start()
        
        try:
            # 执行任务
            success = await executor.execute_task(sample_task_data)
            assert success is True
            
            # 等待任务完成（包括重试）
            await asyncio.sleep(2.0)  # 等待足够长的时间让重试完成
            
            # 验证多次调用（原始执行 + 重试）
            assert mock_handler.probe.call_count > 1
            
            # 等待结果收集
            await asyncio.sleep(0.2)
            
            # 验证最终失败结果
            assert len(results) > 0
            final_result = results[-1]['results'][0]
            assert final_result['status'] == 'failed'
            assert 'error_message' in final_result
            
        finally:
            await executor.stop()
            await collector.stop()
    
    @pytest.mark.asyncio
    async def test_concurrent_task_execution(self):
        """测试并发任务执行"""
        results = []
        
        async def collect_result(result_data):
            results.append(result_data)
        
        collector = TaskResultCollector(
            agent_id="test-agent",
            batch_size=5,
            batch_timeout=1,
            send_callback=collect_result
        )
        
        executor = TaskExecutor(
            agent_id="test-agent",
            max_concurrent_tasks=3,
            default_timeout=30,
            result_callback=collector.collect_result
        )
        
        # 模拟慢速协议处理器
        mock_handler = AsyncMock()
        
        async def slow_probe(*args):
            await asyncio.sleep(0.1)  # 模拟网络延迟
            return ProbeResult(
                status=ProbeStatus.SUCCESS,
                response_time=100.0,
                metrics={'response_time': 100.0}
            )
        
        mock_handler.probe.side_effect = slow_probe
        executor.protocol_registry.get_handler = Mock(return_value=mock_handler)
        
        await collector.start()
        await executor.start()
        
        try:
            # 创建多个任务
            tasks = []
            for i in range(5):
                task_data = {
                    'id': str(uuid.uuid4()),
                    'protocol': 'http',
                    'target': f'example{i}.com',
                    'port': 80,
                    'timeout': 30,
                    'parameters': {'method': 'GET'}
                }
                tasks.append(task_data)
            
            # 并发执行任务
            execution_results = []
            for task_data in tasks:
                result = await executor.execute_task(task_data)
                execution_results.append(result)
            
            # 前3个任务应该成功，后2个可能因为并发限制而失败
            successful_executions = sum(execution_results)
            assert successful_executions == 3  # 最大并发数
            
            # 等待任务完成
            await asyncio.sleep(0.5)
            
            # 验证统计信息
            stats = executor.get_statistics()
            assert stats['statistics']['total_executed'] >= 3
            
        finally:
            await executor.stop()
            await collector.stop()
    
    @pytest.mark.asyncio
    async def test_task_cancellation(self, sample_task_data):
        """测试任务取消"""
        executor = TaskExecutor(
            agent_id="test-agent",
            max_concurrent_tasks=5,
            default_timeout=30
        )
        
        # 模拟长时间运行的协议处理器
        mock_handler = AsyncMock()
        
        async def long_running_probe(*args):
            await asyncio.sleep(10)  # 长时间运行
            return ProbeResult(status=ProbeStatus.SUCCESS, response_time=10000.0)
        
        mock_handler.probe.side_effect = long_running_probe
        executor.protocol_registry.get_handler = Mock(return_value=mock_handler)
        
        await executor.start()
        
        try:
            # 执行任务
            success = await executor.execute_task(sample_task_data)
            assert success is True
            
            task_id = uuid.UUID(sample_task_data['id'])
            
            # 等待任务开始执行
            await asyncio.sleep(0.1)
            
            # 验证任务正在运行
            running_tasks = executor.get_running_tasks()
            assert len(running_tasks) == 1
            assert running_tasks[0]['task_id'] == str(task_id)
            
            # 取消任务
            cancel_success = await executor.cancel_task(task_id)
            assert cancel_success is True
            
            # 等待取消完成
            await asyncio.sleep(0.1)
            
            # 验证任务不再运行
            running_tasks = executor.get_running_tasks()
            assert len(running_tasks) == 0
            
            # 验证统计信息
            stats = executor.get_statistics()
            assert stats['statistics']['total_cancelled'] >= 1
            
        finally:
            await executor.stop()


class TestAgentTaskIntegration:
    """代理任务集成测试"""
    
    @pytest.mark.asyncio
    @patch('agent.core.agent.WebSocketClient')
    @patch('agent.core.agent.ResourceMonitor')
    @patch('agent.core.agent.AgentConfigManager')
    async def test_agent_task_handling(self, mock_config_manager, mock_resource_monitor, mock_websocket_client, mock_config, sample_task_data):
        """测试代理任务处理"""
        # 设置模拟
        mock_config_manager.return_value = mock_config
        mock_resource_monitor.return_value = Mock()
        
        mock_ws_instance = Mock()
        mock_ws_instance.connect = AsyncMock(return_value=True)
        mock_ws_instance.disconnect = AsyncMock()
        mock_ws_instance.send_message = AsyncMock()
        mock_ws_instance.is_connected = True
        mock_ws_instance.register_handler = Mock()
        mock_websocket_client.return_value = mock_ws_instance
        
        # 创建代理
        agent = Agent()
        
        # 模拟协议处理器
        mock_handler = AsyncMock()
        mock_result = ProbeResult(
            status=ProbeStatus.SUCCESS,
            response_time=100.0,
            metrics={'status_code': 200}
        )
        mock_handler.probe.return_value = mock_result
        
        try:
            # 启动代理
            await agent.start()
            
            # 设置协议处理器
            if agent._task_executor:
                agent._task_executor.protocol_registry.get_handler = Mock(return_value=mock_handler)
            
            # 模拟接收任务分配消息
            message = {
                "type": "task_assign",
                "data": sample_task_data
            }
            
            await agent._handle_task_assign(message)
            
            # 等待任务执行
            await asyncio.sleep(0.2)
            
            # 验证响应消息被发送
            mock_ws_instance.send_message.assert_called()
            
            # 验证任务被执行
            mock_handler.probe.assert_called_once()
            
            # 获取代理状态
            status = agent.get_status()
            assert 'task_executor' in status
            assert status['task_executor']['agent_id'] == mock_config.agent_id
            
        finally:
            await agent.stop()
    
    @pytest.mark.asyncio
    @patch('agent.core.agent.WebSocketClient')
    @patch('agent.core.agent.ResourceMonitor')
    @patch('agent.core.agent.AgentConfigManager')
    async def test_agent_task_cancellation(self, mock_config_manager, mock_resource_monitor, mock_websocket_client, mock_config, sample_task_data):
        """测试代理任务取消"""
        # 设置模拟
        mock_config_manager.return_value = mock_config
        mock_resource_monitor.return_value = Mock()
        
        mock_ws_instance = Mock()
        mock_ws_instance.connect = AsyncMock(return_value=True)
        mock_ws_instance.disconnect = AsyncMock()
        mock_ws_instance.send_message = AsyncMock()
        mock_ws_instance.is_connected = True
        mock_ws_instance.register_handler = Mock()
        mock_websocket_client.return_value = mock_ws_instance
        
        # 创建代理
        agent = Agent()
        
        try:
            # 启动代理
            await agent.start()
            
            # 模拟任务取消消息
            cancel_message = {
                "type": "task_cancel",
                "data": {
                    "task_id": sample_task_data['id']
                }
            }
            
            await agent._handle_task_cancel(cancel_message)
            
            # 验证响应消息被发送
            mock_ws_instance.send_message.assert_called()
            
            # 获取发送的消息
            call_args = mock_ws_instance.send_message.call_args[0][0]
            assert call_args['type'] == 'task_cancel_response'
            assert call_args['data']['task_id'] == sample_task_data['id']
            
        finally:
            await agent.stop()


if __name__ == "__main__":
    pytest.main([__file__])