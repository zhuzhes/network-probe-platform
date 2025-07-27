"""代理核心功能单元测试"""

import pytest
import asyncio
import tempfile
import json
import os
from unittest.mock import patch, MagicMock
from pathlib import Path

from agent.core.agent import Agent
from agent.core.config import AgentConfigManager
from agent.core.logger import AgentLogger, setup_logger


class TestAgentConfigManager:
    """代理配置管理器测试"""
    
    def test_init_with_default_config(self):
        """测试使用默认配置初始化"""
        # 使用不存在的配置文件路径来测试默认配置
        with tempfile.NamedTemporaryFile(delete=True) as f:
            non_existent_path = f.name + "_non_existent"
        
        config = AgentConfigManager(config_file=non_existent_path)
        assert config.agent_name == "probe-agent"
        assert config.heartbeat_interval == 30
        assert config.resource_report_interval == 60
    
    def test_init_with_custom_config_file(self):
        """测试使用自定义配置文件初始化"""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
            test_config = {
                "agent_name": "test-agent",
                "heartbeat_interval": 15,
                "custom_setting": "test_value"
            }
            json.dump(test_config, f)
            config_file = f.name
        
        try:
            config = AgentConfigManager(config_file)
            assert config.agent_name == "test-agent"
            assert config.heartbeat_interval == 15
            assert config.get("custom_setting") == "test_value"
        finally:
            os.unlink(config_file)
    
    def test_get_and_set_config(self):
        """测试配置的获取和设置"""
        config = AgentConfigManager()
        
        # 测试设置和获取
        config.set("test_key", "test_value")
        assert config.get("test_key") == "test_value"
        
        # 测试默认值
        assert config.get("non_existent_key", "default") == "default"
    
    def test_update_config(self):
        """测试批量更新配置"""
        config = AgentConfigManager()
        
        update_dict = {
            "key1": "value1",
            "key2": "value2"
        }
        config.update(update_dict)
        
        assert config.get("key1") == "value1"
        assert config.get("key2") == "value2"
    
    def test_save_and_load_config(self):
        """测试配置的保存和加载"""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
            config_file = f.name
        
        try:
            # 创建配置并设置值
            config1 = AgentConfigManager(config_file)
            config1.set("test_key", "test_value")
            config1.agent_name = "saved-agent"
            config1.save_local_config()
            
            # 重新加载配置
            config2 = AgentConfigManager(config_file)
            assert config2.get("test_key") == "test_value"
            assert config2.agent_name == "saved-agent"
        finally:
            if os.path.exists(config_file):
                os.unlink(config_file)
    
    def test_property_access(self):
        """测试属性访问"""
        config = AgentConfigManager()
        
        # 测试读取属性
        assert isinstance(config.agent_name, str)
        assert isinstance(config.heartbeat_interval, int)
        assert isinstance(config.max_concurrent_tasks, int)
        
        # 测试设置属性
        config.agent_name = "new-agent"
        assert config.agent_name == "new-agent"
        
        config.server_url = "ws://new-server:8000"
        assert config.server_url == "ws://new-server:8000"


class TestAgentLogger:
    """代理日志系统测试"""
    
    def test_setup_logger_default(self):
        """测试默认日志设置"""
        logger = setup_logger("test_logger")
        assert logger.name == "test_logger"
        assert logger.level == 20  # INFO level
        assert len(logger.handlers) >= 1  # 至少有控制台处理器
    
    def test_setup_logger_with_file(self):
        """测试文件日志设置"""
        with tempfile.NamedTemporaryFile(suffix='.log', delete=False) as f:
            log_file = f.name
        
        try:
            logger = setup_logger("test_logger_file", log_file=log_file)
            
            # 验证日志器创建成功
            assert logger.name == "test_logger_file"
            
            # 验证有文件处理器
            file_handlers = [h for h in logger.handlers if hasattr(h, 'baseFilename')]
            assert len(file_handlers) > 0
            
            # 验证文件处理器指向正确的文件
            assert file_handlers[0].baseFilename == log_file
            
            # 检查日志文件是否创建
            assert os.path.exists(log_file)
            
        finally:
            if os.path.exists(log_file):
                os.unlink(log_file)
    
    def test_agent_logger_methods(self):
        """测试代理日志器方法"""
        logger = AgentLogger("test_agent")
        
        # 测试各种日志方法（不会抛出异常即可）
        logger.debug("Debug message")
        logger.info("Info message")
        logger.warning("Warning message")
        logger.error("Error message")
        logger.critical("Critical message")
    
    def test_agent_logger_set_level(self):
        """测试设置日志级别"""
        logger = AgentLogger("test_agent")
        
        logger.set_level("DEBUG")
        assert logger.logger.level == 10  # DEBUG level
        
        logger.set_level("ERROR")
        assert logger.logger.level == 40  # ERROR level
    
    def test_agent_logger_add_context(self):
        """测试添加上下文"""
        logger = AgentLogger("test_agent")
        
        context_logger = logger.add_context(agent_id="test-123", task_id="task-456")
        assert hasattr(context_logger, 'extra')
        assert context_logger.extra['agent_id'] == "test-123"
        assert context_logger.extra['task_id'] == "task-456"


class TestAgent:
    """代理主类测试"""
    
    @pytest.fixture
    def agent(self):
        """创建测试用代理实例"""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
            config_file = f.name
        
        agent = Agent(config_file)
        yield agent
        
        # 清理
        if os.path.exists(config_file):
            os.unlink(config_file)
    
    def test_agent_init(self, agent):
        """测试代理初始化"""
        assert agent.agent_id is not None
        assert len(agent.agent_id) > 0
        assert not agent.is_running
        assert not agent.is_connected
        assert isinstance(agent.config, AgentConfigManager)
        assert isinstance(agent.logger, AgentLogger)
    
    def test_agent_properties(self, agent):
        """测试代理属性"""
        assert isinstance(agent.agent_id, str)
        assert isinstance(agent.is_running, bool)
        assert isinstance(agent.is_connected, bool)
    
    def test_get_status(self, agent):
        """测试获取代理状态"""
        status = agent.get_status()
        
        required_keys = [
            "agent_id", "agent_name", "running", "connected",
            "server_url", "heartbeat_interval", "resource_report_interval",
            "max_concurrent_tasks", "active_tasks", "timestamp"
        ]
        
        for key in required_keys:
            assert key in status
        
        assert status["agent_id"] == agent.agent_id
        assert status["running"] == agent.is_running
        assert status["connected"] == agent.is_connected
        assert isinstance(status["active_tasks"], list)
    
    @pytest.mark.asyncio
    async def test_agent_start_stop(self, agent):
        """测试代理启动和停止"""
        # 测试启动
        start_task = asyncio.create_task(agent.start())
        
        # 等待一小段时间让代理启动
        await asyncio.sleep(0.1)
        
        assert agent.is_running
        
        # 测试停止
        await agent.stop()
        
        assert not agent.is_running
        
        # 等待启动任务完成
        try:
            await start_task
        except:
            pass  # 启动任务可能因为停止而被取消
    
    @pytest.mark.asyncio
    async def test_agent_reload_config(self, agent):
        """测试重新加载配置"""
        original_name = agent.config.agent_name
        
        # 修改配置
        agent.config.agent_name = "reloaded-agent"
        agent.config.save_local_config()
        
        # 重新加载配置
        await agent.reload_config()
        
        # 验证配置已重新加载
        assert agent.config.agent_name == "reloaded-agent"
    
    @pytest.mark.asyncio
    async def test_agent_signal_handling(self, agent):
        """测试信号处理"""
        # 这个测试主要验证信号处理器设置不会抛出异常
        # 实际的信号处理在集成测试中验证
        assert hasattr(agent, '_signal_handler')
        
        # 模拟信号处理
        with patch.object(agent, 'stop') as mock_stop:
            agent._signal_handler(2, None)  # SIGINT
            # 由于信号处理器使用asyncio.create_task，我们需要等待一下
            await asyncio.sleep(0.01)


class TestAgentIntegration:
    """代理集成测试"""
    
    @pytest.mark.asyncio
    async def test_agent_lifecycle(self):
        """测试代理完整生命周期"""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
            config_file = f.name
        
        try:
            agent = Agent(config_file)
            
            # 验证初始状态
            assert not agent.is_running
            assert not agent.is_connected
            
            # 启动代理（在后台运行）
            start_task = asyncio.create_task(agent.start())
            
            # 等待代理启动
            await asyncio.sleep(0.1)
            assert agent.is_running
            
            # 检查状态
            status = agent.get_status()
            assert status["running"]
            assert len(status["active_tasks"]) > 0
            
            # 停止代理
            await agent.stop()
            assert not agent.is_running
            
            # 等待启动任务完成
            try:
                await start_task
            except:
                pass
                
        finally:
            if os.path.exists(config_file):
                os.unlink(config_file)
    
    @pytest.mark.asyncio
    async def test_agent_config_persistence(self):
        """测试代理配置持久化"""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
            config_file = f.name
        
        try:
            # 创建第一个代理实例
            agent1 = Agent(config_file)
            original_id = agent1.agent_id
            
            # 启动并立即停止以保存配置
            start_task = asyncio.create_task(agent1.start())
            await asyncio.sleep(0.1)
            await agent1.stop()
            
            try:
                await start_task
            except:
                pass
            
            # 创建第二个代理实例，应该使用相同的ID
            agent2 = Agent(config_file)
            assert agent2.agent_id == original_id
            
        finally:
            if os.path.exists(config_file):
                os.unlink(config_file)