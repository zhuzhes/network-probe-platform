"""消息分发系统测试"""

import pytest
import asyncio
import uuid
from datetime import datetime, timedelta
from unittest.mock import Mock, AsyncMock, patch, MagicMock

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))

from management_platform.api.message_dispatcher import (
    Message,
    MessageType,
    MessagePriority,
    MessageQueue,
    TaskDistributor,
    ResultCollector,
    StatusUpdater,
    MessageDispatcher
)
from management_platform.api.connection_manager import AdvancedConnectionManager
from shared.models.task import Task, TaskStatus


class TestMessage:
    """消息测试"""
    
    def test_message_creation(self):
        """测试消息创建"""
        message = Message(
            type=MessageType.TASK_ASSIGNMENT,
            priority=MessagePriority.HIGH,
            recipient="test_agent",
            data={"key": "value"}
        )
        
        assert message.type == MessageType.TASK_ASSIGNMENT
        assert message.priority == MessagePriority.HIGH
        assert message.recipient == "test_agent"
        assert message.data == {"key": "value"}
        assert message.retry_count == 0
        assert message.max_retries == 3
    
    def test_message_to_dict(self):
        """测试消息转换为字典"""
        message = Message(
            type=MessageType.TASK_RESULT,
            priority=MessagePriority.NORMAL,
            sender="test_agent",
            data={"result": "success"}
        )
        
        message_dict = message.to_dict()
        
        assert message_dict["type"] == "task_result"
        assert message_dict["priority"] == 2
        assert message_dict["sender"] == "test_agent"
        assert message_dict["data"] == {"result": "success"}
        assert "timestamp" in message_dict
    
    def test_message_expiration(self):
        """测试消息过期"""
        # 未过期的消息
        message = Message(expires_at=datetime.now() + timedelta(minutes=5))
        assert not message.is_expired()
        
        # 过期的消息
        expired_message = Message(expires_at=datetime.now() - timedelta(minutes=5))
        assert expired_message.is_expired()
        
        # 没有过期时间的消息
        no_expiry_message = Message()
        assert not no_expiry_message.is_expired()
    
    def test_message_retry(self):
        """测试消息重试"""
        message = Message(max_retries=2)
        
        assert message.can_retry()
        
        message.retry_count = 1
        assert message.can_retry()
        
        message.retry_count = 2
        assert not message.can_retry()


class TestMessageQueue:
    """消息队列测试"""
    
    @pytest.fixture
    def queue(self):
        """创建消息队列"""
        return MessageQueue(max_size=100)
    
    @pytest.mark.asyncio
    async def test_put_and_get_message(self, queue):
        """测试添加和获取消息"""
        message = Message(
            type=MessageType.TASK_ASSIGNMENT,
            priority=MessagePriority.HIGH,
            data={"test": "data"}
        )
        
        # 添加消息
        result = await queue.put(message)
        assert result is True
        assert queue.stats["messages_queued"] == 1
        
        # 获取消息
        retrieved = await queue.get()
        assert retrieved == message
    
    @pytest.mark.asyncio
    async def test_priority_ordering(self, queue):
        """测试优先级排序"""
        # 添加不同优先级的消息
        low_msg = Message(priority=MessagePriority.LOW, data={"priority": "low"})
        high_msg = Message(priority=MessagePriority.HIGH, data={"priority": "high"})
        urgent_msg = Message(priority=MessagePriority.URGENT, data={"priority": "urgent"})
        normal_msg = Message(priority=MessagePriority.NORMAL, data={"priority": "normal"})
        
        # 按非优先级顺序添加
        await queue.put(low_msg)
        await queue.put(normal_msg)
        await queue.put(urgent_msg)
        await queue.put(high_msg)
        
        # 获取消息应该按优先级顺序
        first = await queue.get()
        assert first.data["priority"] == "urgent"
        
        second = await queue.get()
        assert second.data["priority"] == "high"
        
        third = await queue.get()
        assert third.data["priority"] == "normal"
        
        fourth = await queue.get()
        assert fourth.data["priority"] == "low"
    
    @pytest.mark.asyncio
    async def test_expired_message_handling(self, queue):
        """测试过期消息处理"""
        expired_message = Message(
            expires_at=datetime.now() - timedelta(minutes=1),
            data={"expired": True}
        )
        
        # 添加过期消息应该失败
        result = await queue.put(expired_message)
        assert result is False
        assert queue.stats["messages_expired"] == 1
    
    @pytest.mark.asyncio
    async def test_get_blocking(self, queue):
        """测试阻塞获取消息"""
        message = Message(data={"test": "blocking"})
        
        # 在另一个任务中延迟添加消息
        async def delayed_put():
            await asyncio.sleep(0.1)
            await queue.put(message)
        
        # 启动延迟添加任务
        asyncio.create_task(delayed_put())
        
        # 阻塞获取应该等待并获取到消息
        retrieved = await queue.get_blocking(timeout=1.0)
        assert retrieved == message
    
    @pytest.mark.asyncio
    async def test_get_blocking_timeout(self, queue):
        """测试阻塞获取超时"""
        # 空队列阻塞获取应该超时
        result = await queue.get_blocking(timeout=0.1)
        assert result is None
    
    def test_queue_size(self, queue):
        """测试队列大小"""
        # 初始大小应该为0
        sizes = queue.qsize()
        assert all(size == 0 for size in sizes.values())
        
        # 添加消息后大小应该增加
        message = Message(priority=MessagePriority.HIGH)
        asyncio.run(queue.put(message))
        
        high_size = queue.qsize(MessagePriority.HIGH)
        assert high_size == 1
    
    def test_get_stats(self, queue):
        """测试获取统计信息"""
        stats = queue.get_stats()
        
        assert "messages_queued" in stats
        assert "messages_sent" in stats
        assert "messages_failed" in stats
        assert "queue_sizes" in stats
        assert "total_queued" in stats


class TestTaskDistributor:
    """任务分发器测试"""
    
    @pytest.fixture
    def mock_connection_manager(self):
        """创建模拟连接管理器"""
        manager = Mock(spec=AdvancedConnectionManager)
        manager.get_available_agents.return_value = ["agent1", "agent2", "agent3"]
        manager.send_message = AsyncMock(return_value=True)
        
        # 模拟负载监控器
        load_monitor = Mock()
        load_monitor.get_agent_load.return_value = {"cpu_usage": 50.0, "memory_usage": 60.0, "disk_usage": 30.0}
        manager.load_monitor = load_monitor
        
        # 模拟连接池
        connection_pool = Mock()
        connection = Mock()
        connection.capabilities = ["icmp", "tcp", "udp", "http"]
        connection_pool.get_primary_connection.return_value = connection
        manager.connection_pool = connection_pool
        
        return manager
    
    @pytest.fixture
    def distributor(self, mock_connection_manager):
        """创建任务分发器"""
        return TaskDistributor(mock_connection_manager)
    
    @pytest.fixture
    def mock_task(self):
        """创建模拟任务"""
        task = Mock(spec=Task)
        task.id = str(uuid.uuid4())
        task.protocol = "icmp"
        task.target = "example.com"
        task.port = None
        task.parameters = {}
        task.timeout = 30
        return task
    
    @pytest.mark.asyncio
    async def test_distribute_task_success(self, distributor, mock_task, mock_connection_manager):
        """测试成功分发任务"""
        result = await distributor.distribute_task(mock_task)
        
        assert result is not None
        assert result in ["agent1", "agent2", "agent3"]
        assert distributor.stats["tasks_distributed"] == 1
        
        # 验证发送消息被调用
        mock_connection_manager.send_message.assert_called_once()
    
    @pytest.mark.asyncio
    async def test_distribute_task_no_agents(self, distributor, mock_task, mock_connection_manager):
        """测试没有可用代理时分发任务"""
        mock_connection_manager.get_available_agents.return_value = []
        
        result = await distributor.distribute_task(mock_task)
        
        assert result is None
        assert distributor.stats["distribution_failures"] == 1
    
    @pytest.mark.asyncio
    async def test_distribute_task_send_failure(self, distributor, mock_task, mock_connection_manager):
        """测试发送消息失败"""
        mock_connection_manager.send_message.return_value = False
        
        result = await distributor.distribute_task(mock_task)
        
        assert result is None
        assert distributor.stats["distribution_failures"] == 1
    
    @pytest.mark.asyncio
    async def test_round_robin_strategy(self, distributor, mock_task):
        """测试轮询策略"""
        available_agents = ["agent1", "agent2", "agent3"]
        
        # 连续分发应该轮询选择代理
        agent1 = await distributor._round_robin_strategy(mock_task, available_agents)
        agent2 = await distributor._round_robin_strategy(mock_task, available_agents)
        agent3 = await distributor._round_robin_strategy(mock_task, available_agents)
        agent4 = await distributor._round_robin_strategy(mock_task, available_agents)
        
        assert agent1 == "agent1"
        assert agent2 == "agent2"
        assert agent3 == "agent3"
        assert agent4 == "agent1"  # 应该回到第一个
    
    @pytest.mark.asyncio
    async def test_load_based_strategy(self, distributor, mock_task, mock_connection_manager):
        """测试基于负载的策略"""
        available_agents = ["agent1", "agent2", "agent3"]
        
        # 设置不同的负载
        def mock_get_load(agent_id):
            loads = {
                "agent1": {"cpu_usage": 80.0, "memory_usage": 70.0, "disk_usage": 60.0},
                "agent2": {"cpu_usage": 30.0, "memory_usage": 40.0, "disk_usage": 20.0},
                "agent3": {"cpu_usage": 60.0, "memory_usage": 50.0, "disk_usage": 40.0}
            }
            return loads.get(agent_id, {})
        
        mock_connection_manager.load_monitor.get_agent_load.side_effect = mock_get_load
        
        selected_agent = await distributor._load_based_strategy(mock_task, available_agents)
        
        # 应该选择负载最低的agent2
        assert selected_agent == "agent2"
    
    @pytest.mark.asyncio
    async def test_capability_based_strategy(self, distributor, mock_task, mock_connection_manager):
        """测试基于能力的策略"""
        available_agents = ["agent1", "agent2", "agent3"]
        
        # 设置不同的能力
        def mock_get_connection(agent_id):
            connections = {
                "agent1": Mock(capabilities=["tcp", "udp"]),
                "agent2": Mock(capabilities=["icmp", "http"]),
                "agent3": Mock(capabilities=["http", "https"])
            }
            return connections.get(agent_id)
        
        mock_connection_manager.connection_pool.get_primary_connection.side_effect = mock_get_connection
        
        # 任务需要icmp协议
        mock_task.protocol = "icmp"
        
        selected_agent = await distributor._capability_based_strategy(mock_task, available_agents)
        
        # 应该选择支持icmp的agent2
        assert selected_agent == "agent2"
    
    @pytest.mark.asyncio
    async def test_cancel_task(self, distributor, mock_connection_manager):
        """测试取消任务"""
        task_id = str(uuid.uuid4())
        agent_id = "test_agent"
        
        result = await distributor.cancel_task(task_id, agent_id)
        
        assert result is True
        mock_connection_manager.send_message.assert_called_once()
        
        # 验证消息内容
        call_args = mock_connection_manager.send_message.call_args
        assert call_args[0][0] == agent_id
        message = call_args[0][1]
        assert message["type"] == "task_cancel"
        assert message["data"]["task_id"] == task_id
    
    def test_set_strategy(self, distributor):
        """测试设置分发策略"""
        distributor.set_strategy("round_robin")
        assert distributor.current_strategy == "round_robin"
        
        # 设置无效策略应该不改变当前策略
        old_strategy = distributor.current_strategy
        distributor.set_strategy("invalid_strategy")
        assert distributor.current_strategy == old_strategy
    
    def test_get_stats(self, distributor):
        """测试获取统计信息"""
        stats = distributor.get_stats()
        
        assert "tasks_distributed" in stats
        assert "distribution_failures" in stats
        assert "current_strategy" in stats
        assert "available_strategies" in stats


class TestResultCollector:
    """结果收集器测试"""
    
    @pytest.fixture
    def mock_connection_manager(self):
        """创建模拟连接管理器"""
        manager = Mock(spec=AdvancedConnectionManager)
        manager.send_message = AsyncMock(return_value=True)
        return manager
    
    @pytest.fixture
    def collector(self, mock_connection_manager):
        """创建结果收集器"""
        return ResultCollector(mock_connection_manager)
    
    @pytest.mark.asyncio
    async def test_handle_task_result(self, collector, mock_connection_manager):
        """测试处理任务结果"""
        agent_id = "test_agent"
        task_id = str(uuid.uuid4())
        
        message = {
            "type": "task_result",
            "data": {
                "task_id": task_id,
                "result": {"status": "success", "latency": 10.5},
                "status": "completed",
                "execution_time": 1.5,
                "metrics": {"packets_sent": 4, "packets_received": 4}
            }
        }
        
        with patch('management_platform.api.message_dispatcher.get_db_session'), \
             patch('management_platform.api.message_dispatcher.TaskRepository'):
            
            await collector.handle_task_result(agent_id, message)
            
            # 验证结果被记录
            assert task_id in collector.pending_results
            assert collector.stats["results_received"] == 1
            
            # 验证发送了确认消息
            mock_connection_manager.send_message.assert_called_once()
    
    @pytest.mark.asyncio
    async def test_handle_duplicate_result(self, collector):
        """测试处理重复结果"""
        agent_id = "test_agent"
        task_id = str(uuid.uuid4())
        
        # 先添加一个结果
        collector.pending_results[task_id] = {"existing": "result"}
        
        message = {
            "type": "task_result",
            "data": {
                "task_id": task_id,
                "result": {"status": "success"}
            }
        }
        
        await collector.handle_task_result(agent_id, message)
        
        # 应该检测到重复并增加统计
        assert collector.stats["duplicate_results"] == 1
    
    @pytest.mark.asyncio
    async def test_handle_result_missing_task_id(self, collector):
        """测试处理缺少task_id的结果"""
        agent_id = "test_agent"
        
        message = {
            "type": "task_result",
            "data": {
                "result": {"status": "success"}
                # 缺少task_id
            }
        }
        
        await collector.handle_task_result(agent_id, message)
        
        # 应该没有记录结果
        assert len(collector.pending_results) == 0
    
    def test_register_result_handler(self, collector):
        """测试注册结果处理器"""
        handler = AsyncMock()
        collector.register_result_handler("test_handler", handler)
        
        assert "test_handler" in collector.result_handlers
        assert collector.result_handlers["test_handler"] == handler
    
    def test_unregister_result_handler(self, collector):
        """测试注销结果处理器"""
        handler = AsyncMock()
        collector.register_result_handler("test_handler", handler)
        
        collector.unregister_result_handler("test_handler")
        
        assert "test_handler" not in collector.result_handlers
    
    def test_get_pending_results(self, collector):
        """测试获取待处理结果"""
        test_result = {"task_id": "test", "result": "data"}
        collector.pending_results["test"] = test_result
        
        pending = collector.get_pending_results()
        
        assert pending == {"test": test_result}
        # 应该返回副本，不是原始字典
        assert pending is not collector.pending_results
    
    def test_get_stats(self, collector):
        """测试获取统计信息"""
        stats = collector.get_stats()
        
        assert "results_received" in stats
        assert "results_processed" in stats
        assert "pending_results_count" in stats
        assert "registered_handlers" in stats


class TestStatusUpdater:
    """状态更新器测试"""
    
    @pytest.fixture
    def mock_connection_manager(self):
        """创建模拟连接管理器"""
        manager = Mock(spec=AdvancedConnectionManager)
        manager.send_message = AsyncMock(return_value=True)
        manager.broadcast_message = AsyncMock(return_value=3)
        return manager
    
    @pytest.fixture
    def updater(self, mock_connection_manager):
        """创建状态更新器"""
        return StatusUpdater(mock_connection_manager)
    
    @pytest.mark.asyncio
    async def test_update_task_status_specific_agent(self, updater, mock_connection_manager):
        """测试向特定代理更新任务状态"""
        task_id = str(uuid.uuid4())
        agent_id = "test_agent"
        
        await updater.update_task_status(task_id, TaskStatus.ACTIVE, agent_id)
        
        # 验证发送了消息
        mock_connection_manager.send_message.assert_called_once()
        call_args = mock_connection_manager.send_message.call_args
        assert call_args[0][0] == agent_id
        
        message = call_args[0][1]
        assert message["type"] == "task_status_update"
        assert message["data"]["task_id"] == task_id
        assert message["data"]["status"] == "active"
        
        assert updater.stats["status_updates_sent"] == 1
    
    @pytest.mark.asyncio
    async def test_update_task_status_broadcast(self, updater, mock_connection_manager):
        """测试广播任务状态更新"""
        task_id = str(uuid.uuid4())
        
        await updater.update_task_status(task_id, TaskStatus.COMPLETED)
        
        # 验证广播了消息
        mock_connection_manager.broadcast_message.assert_called_once()
        
        assert updater.stats["broadcast_updates"] == 1
        assert updater.stats["status_updates_sent"] == 3  # 广播成功数
    
    @pytest.mark.asyncio
    async def test_send_system_notification(self, updater, mock_connection_manager):
        """测试发送系统通知"""
        message = "System maintenance scheduled"
        level = "warning"
        agent_id = "test_agent"
        
        await updater.send_system_notification(message, level, agent_id)
        
        # 验证发送了通知
        mock_connection_manager.send_message.assert_called_once()
        call_args = mock_connection_manager.send_message.call_args
        
        notification = call_args[0][1]
        assert notification["type"] == "system_notification"
        assert notification["data"]["message"] == message
        assert notification["data"]["level"] == level
    
    @pytest.mark.asyncio
    async def test_send_agent_command(self, updater, mock_connection_manager):
        """测试发送代理命令"""
        agent_id = "test_agent"
        command = "restart"
        parameters = {"delay": 30}
        
        result = await updater.send_agent_command(agent_id, command, parameters)
        
        assert result is True
        
        # 验证发送了命令
        mock_connection_manager.send_message.assert_called_once()
        call_args = mock_connection_manager.send_message.call_args
        
        command_message = call_args[0][1]
        assert command_message["type"] == "agent_command"
        assert command_message["data"]["command"] == command
        assert command_message["data"]["parameters"] == parameters
    
    def test_get_stats(self, updater):
        """测试获取统计信息"""
        stats = updater.get_stats()
        
        assert "status_updates_sent" in stats
        assert "status_updates_failed" in stats
        assert "broadcast_updates" in stats


class TestMessageDispatcher:
    """消息分发系统测试"""
    
    @pytest.fixture
    def mock_connection_manager(self):
        """创建模拟连接管理器"""
        manager = Mock(spec=AdvancedConnectionManager)
        manager.register_message_handler = Mock()
        manager.get_connected_agents.return_value = {"agent1", "agent2"}
        manager.get_available_agents.return_value = ["agent1", "agent2"]
        return manager
    
    @pytest.fixture
    def dispatcher(self, mock_connection_manager):
        """创建消息分发器"""
        return MessageDispatcher(mock_connection_manager)
    
    @pytest.mark.asyncio
    async def test_start_stop(self, dispatcher):
        """测试启动和停止"""
        assert not dispatcher._running
        
        await dispatcher.start()
        assert dispatcher._running
        assert dispatcher._processor_task is not None
        
        await dispatcher.stop()
        assert not dispatcher._running
    
    @pytest.mark.asyncio
    async def test_distribute_task(self, dispatcher):
        """测试分发任务"""
        mock_task = Mock(spec=Task)
        mock_task.id = str(uuid.uuid4())
        
        with patch.object(dispatcher.task_distributor, 'distribute_task', new_callable=AsyncMock) as mock_distribute:
            mock_distribute.return_value = "agent1"
            
            result = await dispatcher.distribute_task(mock_task)
            
            assert result == "agent1"
            mock_distribute.assert_called_once_with(mock_task, None)
    
    @pytest.mark.asyncio
    async def test_cancel_task(self, dispatcher):
        """测试取消任务"""
        task_id = str(uuid.uuid4())
        agent_id = "test_agent"
        
        with patch.object(dispatcher.task_distributor, 'cancel_task', new_callable=AsyncMock) as mock_cancel:
            mock_cancel.return_value = True
            
            result = await dispatcher.cancel_task(task_id, agent_id)
            
            assert result is True
            mock_cancel.assert_called_once_with(task_id, agent_id)
    
    @pytest.mark.asyncio
    async def test_broadcast_message(self, dispatcher, mock_connection_manager):
        """测试广播消息"""
        mock_connection_manager.broadcast_message = AsyncMock(return_value=2)
        
        result = await dispatcher.broadcast_message(
            MessageType.SYSTEM_NOTIFICATION,
            {"message": "test broadcast"},
            MessagePriority.HIGH
        )
        
        assert result == 2
        mock_connection_manager.broadcast_message.assert_called_once()
    
    def test_register_result_handler(self, dispatcher):
        """测试注册结果处理器"""
        handler = AsyncMock()
        dispatcher.register_result_handler("test_handler", handler)
        
        # 验证处理器被注册到结果收集器
        assert "test_handler" in dispatcher.result_collector.result_handlers
    
    def test_set_distribution_strategy(self, dispatcher):
        """测试设置分发策略"""
        dispatcher.set_distribution_strategy("round_robin")
        
        assert dispatcher.task_distributor.current_strategy == "round_robin"
    
    def test_get_stats(self, dispatcher):
        """测试获取统计信息"""
        stats = dispatcher.get_stats()
        
        assert "message_queue" in stats
        assert "task_distributor" in stats
        assert "result_collector" in stats
        assert "status_updater" in stats
        assert "system_status" in stats


if __name__ == "__main__":
    pytest.main([__file__])