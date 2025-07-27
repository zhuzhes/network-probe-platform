"""任务执行器单元测试"""

import pytest
import asyncio
import uuid
from datetime import datetime, timedelta
from unittest.mock import Mock, patch, AsyncMock

from agent.core.executor import TaskExecutor
from agent.protocols.base import ProtocolResult, ProtocolTestStatus
from shared.models.task import ProtocolType


@pytest.fixture
def sample_task_data():
    """创建示例任务数据"""
    return {
        'id': str(uuid.uuid4()),
        'protocol': 'http',
        'target': 'example.com',
        'port': 80,
        'timeout': 30,
        'parameters': {'method': 'GET'}
    }


@pytest.fixture
def sample_probe_result():
    """创建示例拨测结果"""
    return ProtocolResult(
        protocol='http',
        target='example.com',
        status=ProtocolTestStatus.SUCCESS,
        duration_ms=100.0,
        metrics={'status_code': 200},
        raw_data={'response': 'OK'}
    )


@pytest.fixture
def task_executor():
    """创建任务执行器实例"""
    return TaskExecutor(
        agent_id="test-agent",
        max_concurrent_tasks=5,
        default_timeout=30
    )


@pytest.fixture
def result_collector():
    """创建结果收集器实例"""
    return TaskResultCollector(
        agent_id="test-agent",
        batch_size=5,
        batch_timeout=10
    )


class TestTaskExecution:
    """TaskExecution测试类"""
    
    def test_task_execution_creation(self, sample_task_data):
        """测试任务执行实例创建"""
        task_id = uuid.uuid4()
        execution = TaskExecution(
            task_id=task_id,
            task_data=sample_task_data,
            start_time=datetime.utcnow()
        )
        
        assert execution.task_id == task_id
        assert execution.task_data == sample_task_data
        assert execution.status == ExecutionStatus.PENDING
        assert execution.retry_count == 0
        assert execution.max_retries == 3
    
    def test_duration_calculation(self, sample_task_data):
        """测试执行时长计算"""
        start_time = datetime.utcnow()
        execution = TaskExecution(
            task_id=uuid.uuid4(),
            task_data=sample_task_data,
            start_time=start_time
        )
        
        # 未结束时应该返回None
        assert execution.duration is None
        
        # 设置结束时间
        execution.end_time = start_time + timedelta(seconds=2)
        assert execution.duration == 2000.0  # 2秒 = 2000毫秒
    
    def test_is_completed(self, sample_task_data):
        """测试完成状态检查"""
        execution = TaskExecution(
            task_id=uuid.uuid4(),
            task_data=sample_task_data,
            start_time=datetime.utcnow()
        )
        
        # 初始状态不是完成
        assert execution.is_completed is False
        
        # 各种完成状态
        for status in [ExecutionStatus.COMPLETED, ExecutionStatus.FAILED, 
                      ExecutionStatus.TIMEOUT, ExecutionStatus.CANCELLED]:
            execution.status = status
            assert execution.is_completed is True
    
    def test_can_retry(self, sample_task_data):
        """测试重试检查"""
        execution = TaskExecution(
            task_id=uuid.uuid4(),
            task_data=sample_task_data,
            start_time=datetime.utcnow()
        )
        
        # 失败状态且未达到最大重试次数
        execution.status = ExecutionStatus.FAILED
        execution.retry_count = 1
        assert execution.can_retry is True
        
        # 达到最大重试次数
        execution.retry_count = 3
        assert execution.can_retry is False
        
        # 非失败状态
        execution.status = ExecutionStatus.COMPLETED
        execution.retry_count = 1
        assert execution.can_retry is False
    
    def test_mark_started(self, sample_task_data):
        """测试标记开始执行"""
        execution = TaskExecution(
            task_id=uuid.uuid4(),
            task_data=sample_task_data,
            start_time=datetime.utcnow()
        )
        
        execution.mark_started()
        assert execution.status == ExecutionStatus.RUNNING
    
    def test_mark_completed(self, sample_task_data, sample_probe_result):
        """测试标记执行完成"""
        execution = TaskExecution(
            task_id=uuid.uuid4(),
            task_data=sample_task_data,
            start_time=datetime.utcnow()
        )
        
        execution.mark_completed(sample_probe_result)
        assert execution.status == ExecutionStatus.COMPLETED
        assert execution.result == sample_probe_result
        assert execution.end_time is not None
    
    def test_mark_failed(self, sample_task_data):
        """测试标记执行失败"""
        execution = TaskExecution(
            task_id=uuid.uuid4(),
            task_data=sample_task_data,
            start_time=datetime.utcnow()
        )
        
        error_message = "测试错误"
        execution.mark_failed(error_message)
        assert execution.status == ExecutionStatus.FAILED
        assert execution.error_message == error_message
        assert execution.end_time is not None
    
    def test_mark_timeout(self, sample_task_data):
        """测试标记执行超时"""
        execution = TaskExecution(
            task_id=uuid.uuid4(),
            task_data=sample_task_data,
            start_time=datetime.utcnow()
        )
        
        execution.mark_timeout()
        assert execution.status == ExecutionStatus.TIMEOUT
        assert execution.error_message == "任务执行超时"
        assert execution.end_time is not None
    
    def test_mark_cancelled(self, sample_task_data):
        """测试标记执行取消"""
        execution = TaskExecution(
            task_id=uuid.uuid4(),
            task_data=sample_task_data,
            start_time=datetime.utcnow()
        )
        
        execution.mark_cancelled()
        assert execution.status == ExecutionStatus.CANCELLED
        assert execution.error_message == "任务被取消"
        assert execution.end_time is not None
    
    def test_increment_retry(self, sample_task_data):
        """测试增加重试次数"""
        execution = TaskExecution(
            task_id=uuid.uuid4(),
            task_data=sample_task_data,
            start_time=datetime.utcnow()
        )
        
        # 设置为失败状态
        execution.mark_failed("测试错误")
        initial_retry_count = execution.retry_count
        
        execution.increment_retry()
        assert execution.retry_count == initial_retry_count + 1
        assert execution.status == ExecutionStatus.PENDING
        assert execution.end_time is None
        assert execution.error_message is None


class TestTaskExecutor:
    """TaskExecutor测试类"""
    
    def test_executor_creation(self):
        """测试执行器创建"""
        executor = TaskExecutor(
            agent_id="test-agent",
            max_concurrent_tasks=10,
            default_timeout=60
        )
        
        assert executor.agent_id == "test-agent"
        assert executor.max_concurrent_tasks == 10
        assert executor.default_timeout == 60
        assert executor._running is False
        assert len(executor._executions) == 0
    
    @pytest.mark.asyncio
    async def test_executor_lifecycle(self, task_executor):
        """测试执行器生命周期"""
        # 启动执行器
        await task_executor.start()
        assert task_executor._running is True
        
        # 停止执行器
        await task_executor.stop()
        assert task_executor._running is False
        assert len(task_executor._executions) == 0
        assert len(task_executor._execution_tasks) == 0
    
    @pytest.mark.asyncio
    async def test_execute_task_success(self, task_executor, sample_task_data):
        """测试成功执行任务"""
        await task_executor.start()
        
        # 模拟协议处理器
        mock_handler = AsyncMock()
        mock_result = ProbeResult(
            status=ProbeStatus.SUCCESS,
            response_time=100.0,
            metrics={'status_code': 200}
        )
        mock_handler.probe.return_value = mock_result
        
        task_executor.protocol_registry.get_handler = Mock(return_value=mock_handler)
        
        # 执行任务
        success = await task_executor.execute_task(sample_task_data)
        assert success is True
        
        # 等待任务完成
        await asyncio.sleep(0.1)
        
        # 验证任务被执行
        mock_handler.probe.assert_called_once()
        
        await task_executor.stop()
    
    @pytest.mark.asyncio
    async def test_execute_task_not_running(self, task_executor, sample_task_data):
        """测试执行器未运行时执行任务"""
        success = await task_executor.execute_task(sample_task_data)
        assert success is False
    
    @pytest.mark.asyncio
    async def test_execute_task_duplicate(self, task_executor, sample_task_data):
        """测试重复执行同一任务"""
        await task_executor.start()
        
        # 第一次执行成功
        success1 = await task_executor.execute_task(sample_task_data)
        assert success1 is True
        
        # 第二次执行失败（重复）
        success2 = await task_executor.execute_task(sample_task_data)
        assert success2 is False
        
        await task_executor.stop()
    
    @pytest.mark.asyncio
    async def test_execute_task_max_concurrent(self, sample_task_data):
        """测试最大并发限制"""
        executor = TaskExecutor(
            agent_id="test-agent",
            max_concurrent_tasks=1  # 设置为1
        )
        await executor.start()
        
        # 第一个任务成功
        task1_data = sample_task_data.copy()
        task1_data['id'] = str(uuid.uuid4())
        success1 = await executor.execute_task(task1_data)
        assert success1 is True
        
        # 第二个任务失败（达到并发限制）
        task2_data = sample_task_data.copy()
        task2_data['id'] = str(uuid.uuid4())
        success2 = await executor.execute_task(task2_data)
        assert success2 is False
        
        await executor.stop()
    
    @pytest.mark.asyncio
    async def test_execute_task_timeout(self, task_executor, sample_task_data):
        """测试任务执行超时"""
        await task_executor.start()
        
        # 模拟超时的协议处理器
        mock_handler = AsyncMock()
        mock_handler.probe.side_effect = asyncio.TimeoutError()
        
        task_executor.protocol_registry.get_handler = Mock(return_value=mock_handler)
        
        # 设置短超时时间
        sample_task_data['timeout'] = 0.1
        
        success = await task_executor.execute_task(sample_task_data)
        assert success is True
        
        # 等待任务完成
        await asyncio.sleep(0.2)
        
        # 验证任务超时
        task_id = uuid.UUID(sample_task_data['id'])
        assert task_id not in task_executor._executions  # 应该被清理
        
        await task_executor.stop()
    
    @pytest.mark.asyncio
    async def test_execute_task_protocol_error(self, task_executor, sample_task_data):
        """测试协议执行错误"""
        await task_executor.start()
        
        # 模拟协议处理器抛出异常
        mock_handler = AsyncMock()
        mock_handler.probe.side_effect = Exception("协议错误")
        
        task_executor.protocol_registry.get_handler = Mock(return_value=mock_handler)
        
        success = await task_executor.execute_task(sample_task_data)
        assert success is True
        
        # 等待任务完成
        await asyncio.sleep(0.1)
        
        await task_executor.stop()
    
    @pytest.mark.asyncio
    async def test_execute_task_unsupported_protocol(self, task_executor, sample_task_data):
        """测试不支持的协议"""
        await task_executor.start()
        
        # 模拟不支持的协议
        task_executor.protocol_registry.get_handler = Mock(return_value=None)
        
        success = await task_executor.execute_task(sample_task_data)
        assert success is True
        
        # 等待任务完成
        await asyncio.sleep(0.1)
        
        await task_executor.stop()
    
    @pytest.mark.asyncio
    async def test_cancel_task(self, task_executor, sample_task_data):
        """测试取消任务"""
        await task_executor.start()
        
        # 模拟长时间运行的协议处理器
        mock_handler = AsyncMock()
        mock_handler.probe.side_effect = lambda *args: asyncio.sleep(10)
        
        task_executor.protocol_registry.get_handler = Mock(return_value=mock_handler)
        
        # 执行任务
        success = await task_executor.execute_task(sample_task_data)
        assert success is True
        
        task_id = uuid.UUID(sample_task_data['id'])
        
        # 取消任务
        cancel_success = await task_executor.cancel_task(task_id)
        assert cancel_success is True
        
        # 等待取消完成
        await asyncio.sleep(0.1)
        
        await task_executor.stop()
    
    @pytest.mark.asyncio
    async def test_cancel_nonexistent_task(self, task_executor):
        """测试取消不存在的任务"""
        await task_executor.start()
        
        task_id = uuid.uuid4()
        success = await task_executor.cancel_task(task_id)
        assert success is False
        
        await task_executor.stop()
    
    def test_get_execution_status(self, task_executor, sample_task_data):
        """测试获取执行状态"""
        task_id = uuid.UUID(sample_task_data['id'])
        
        # 不存在的任务
        status = task_executor.get_execution_status(task_id)
        assert status is None
        
        # 添加执行记录
        execution = TaskExecution(
            task_id=task_id,
            task_data=sample_task_data,
            start_time=datetime.utcnow()
        )
        task_executor._executions[task_id] = execution
        
        status = task_executor.get_execution_status(task_id)
        assert status is not None
        assert status['task_id'] == str(task_id)
        assert status['status'] == ExecutionStatus.PENDING.value
    
    def test_get_running_tasks(self, task_executor, sample_task_data):
        """测试获取运行中任务列表"""
        # 空列表
        running_tasks = task_executor.get_running_tasks()
        assert len(running_tasks) == 0
        
        # 添加运行中的任务
        task_id = uuid.UUID(sample_task_data['id'])
        execution = TaskExecution(
            task_id=task_id,
            task_data=sample_task_data,
            start_time=datetime.utcnow()
        )
        execution.status = ExecutionStatus.RUNNING
        task_executor._executions[task_id] = execution
        
        running_tasks = task_executor.get_running_tasks()
        assert len(running_tasks) == 1
        assert running_tasks[0]['task_id'] == str(task_id)
        assert running_tasks[0]['protocol'] == sample_task_data['protocol']
        assert running_tasks[0]['target'] == sample_task_data['target']
    
    def test_get_statistics(self, task_executor):
        """测试获取统计信息"""
        stats = task_executor.get_statistics()
        
        assert 'agent_id' in stats
        assert 'running' in stats
        assert 'current_executions' in stats
        assert 'max_concurrent_tasks' in stats
        assert 'statistics' in stats
        assert 'supported_protocols' in stats
        
        assert stats['agent_id'] == task_executor.agent_id
        assert stats['max_concurrent_tasks'] == task_executor.max_concurrent_tasks
    
    @pytest.mark.asyncio
    async def test_health_check(self, task_executor):
        """测试健康检查"""
        # 停止状态
        health = await task_executor.health_check()
        assert health['status'] == 'stopped'
        assert health['agent_id'] == task_executor.agent_id
        
        # 运行状态
        await task_executor.start()
        health = await task_executor.health_check()
        assert health['status'] == 'healthy'
        assert 'current_load' in health
        assert 'success_rate' in health
        
        await task_executor.stop()
    
    def test_set_max_concurrent_tasks(self, task_executor):
        """测试设置最大并发任务数"""
        original_max = task_executor.max_concurrent_tasks
        new_max = original_max + 5
        
        task_executor.set_max_concurrent_tasks(new_max)
        assert task_executor.max_concurrent_tasks == new_max
        
        # 测试无效值
        with pytest.raises(ValueError):
            task_executor.set_max_concurrent_tasks(0)
        
        with pytest.raises(ValueError):
            task_executor.set_max_concurrent_tasks(-1)
    
    def test_set_result_callback(self, task_executor):
        """测试设置结果回调函数"""
        callback = Mock()
        task_executor.set_result_callback(callback)
        assert task_executor.result_callback == callback


class TestTaskResultCollector:
    """TaskResultCollector测试类"""
    
    def test_collector_creation(self):
        """测试收集器创建"""
        collector = TaskResultCollector(
            agent_id="test-agent",
            batch_size=10,
            batch_timeout=60
        )
        
        assert collector.agent_id == "test-agent"
        assert collector.batch_size == 10
        assert collector.batch_timeout == 60
        assert collector._running is False
        assert len(collector._results_buffer) == 0
    
    @pytest.mark.asyncio
    async def test_collector_lifecycle(self, result_collector):
        """测试收集器生命周期"""
        # 启动收集器
        await result_collector.start()
        assert result_collector._running is True
        assert result_collector._batch_task is not None
        
        # 停止收集器
        await result_collector.stop()
        assert result_collector._running is False
    
    @pytest.mark.asyncio
    async def test_collect_result(self, result_collector):
        """测试收集结果"""
        await result_collector.start()
        
        result_data = {
            'task_id': str(uuid.uuid4()),
            'status': 'completed',
            'duration': 1000.0
        }
        
        await result_collector.collect_result(result_data)
        
        # 验证结果被添加到缓冲区
        assert len(result_collector._results_buffer) == 1
        assert result_collector._results_buffer[0] == result_data
        
        await result_collector.stop()
    
    @pytest.mark.asyncio
    async def test_batch_sending(self):
        """测试批量发送"""
        send_callback = AsyncMock()
        collector = TaskResultCollector(
            agent_id="test-agent",
            batch_size=2,  # 小批量大小
            batch_timeout=10,
            send_callback=send_callback
        )
        
        await collector.start()
        
        # 添加结果，达到批量大小
        result1 = {'task_id': str(uuid.uuid4()), 'status': 'completed'}
        result2 = {'task_id': str(uuid.uuid4()), 'status': 'failed'}
        
        await collector.collect_result(result1)
        await collector.collect_result(result2)
        
        # 等待批量发送
        await asyncio.sleep(0.1)
        
        # 验证回调被调用
        send_callback.assert_called_once()
        call_args = send_callback.call_args[0][0]
        assert call_args['agent_id'] == "test-agent"
        assert len(call_args['results']) == 2
        
        # 验证缓冲区被清空
        assert len(collector._results_buffer) == 0
        
        await collector.stop()
    
    @pytest.mark.asyncio
    async def test_timeout_sending(self):
        """测试超时发送"""
        send_callback = AsyncMock()
        collector = TaskResultCollector(
            agent_id="test-agent",
            batch_size=10,  # 大批量大小
            batch_timeout=0.1,  # 短超时时间
            send_callback=send_callback
        )
        
        await collector.start()
        
        # 添加一个结果（不足批量大小）
        result = {'task_id': str(uuid.uuid4()), 'status': 'completed'}
        await collector.collect_result(result)
        
        # 等待超时发送
        await asyncio.sleep(0.2)
        
        # 验证回调被调用
        send_callback.assert_called_once()
        
        await collector.stop()
    
    def test_get_buffer_status(self, result_collector):
        """测试获取缓冲区状态"""
        status = result_collector.get_buffer_status()
        
        assert 'buffer_size' in status
        assert 'batch_size' in status
        assert 'batch_timeout' in status
        assert 'running' in status
        
        assert status['buffer_size'] == 0
        assert status['batch_size'] == result_collector.batch_size
        assert status['batch_timeout'] == result_collector.batch_timeout
        assert status['running'] == result_collector._running


if __name__ == "__main__":
    pytest.main([__file__])