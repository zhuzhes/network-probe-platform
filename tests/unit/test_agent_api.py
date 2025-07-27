"""代理API端点测试"""

import pytest
import uuid
from datetime import datetime, timedelta
from unittest.mock import Mock, AsyncMock, patch
from fastapi import HTTPException, status

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))

from shared.models.agent import (
    Agent, AgentResource, AgentCreate, AgentUpdate, AgentResponse,
    AgentResourceCreate, AgentResourceResponse, AgentSummary,
    AgentStatistics, AgentHealthCheck, AgentStatus, AgentLocationCreate,
    AgentCapabilities
)
from shared.models.user import User, UserRole, UserStatus
from management_platform.api.routes.agents import (
    create_agent, get_agents, get_agent_summary, get_available_agents,
    get_agent, update_agent, delete_agent, update_heartbeat,
    enable_agent, disable_agent, set_maintenance,
    create_agent_resource, get_agent_resources,
    get_agent_statistics, get_agent_health
)


class TestAgentAPI:
    """代理API测试类"""
    
    @pytest.fixture
    def mock_admin_user(self):
        """模拟管理员用户"""
        user = Mock(spec=User)
        user.id = uuid.uuid4()
        user.username = "admin"
        user.role = UserRole.ADMIN
        user.status = UserStatus.ACTIVE
        user.credits = 100.0
        return user
    
    @pytest.fixture
    def mock_regular_user(self):
        """模拟普通用户"""
        user = Mock(spec=User)
        user.id = uuid.uuid4()
        user.username = "user"
        user.role = UserRole.ENTERPRISE
        user.status = UserStatus.ACTIVE
        user.credits = 50.0
        return user
    
    @pytest.fixture
    def mock_agent(self):
        """模拟代理对象"""
        agent = Mock(spec=Agent)
        agent.id = uuid.uuid4()
        agent.name = "test-agent"
        agent.ip_address = "192.168.1.100"
        agent.country = "China"
        agent.city = "Beijing"
        agent.latitude = 39.9042
        agent.longitude = 116.4074
        agent.isp = "China Telecom"
        agent.version = "1.0.0"
        agent.capabilities = {"protocols": ["icmp", "tcp", "http"]}
        agent.status = AgentStatus.ONLINE
        agent.last_heartbeat = datetime.utcnow()
        agent.registered_at = datetime.utcnow() - timedelta(days=1)
        agent.availability = 0.95
        agent.avg_response_time = 50.0
        agent.success_rate = 0.98
        agent.current_cpu_usage = 25.0
        agent.current_memory_usage = 40.0
        agent.current_disk_usage = 60.0
        agent.current_load_average = 1.5
        agent.max_concurrent_tasks = 10
        agent.enabled = True
        agent.created_at = datetime.utcnow() - timedelta(days=1)
        agent.updated_at = datetime.utcnow()
        
        # 添加方法模拟
        agent.get_location_string.return_value = "Beijing, China"
        agent.get_uptime_hours.return_value = 24.0
        agent.get_resource_health_status.return_value = "healthy"
        agent.is_online.return_value = True
        agent.is_available.return_value = True
        
        return agent
    
    @pytest.fixture
    def mock_agent_resource(self):
        """模拟代理资源对象"""
        resource = Mock(spec=AgentResource)
        resource.id = uuid.uuid4()
        resource.agent_id = uuid.uuid4()
        resource.timestamp = datetime.utcnow()
        resource.cpu_usage = 25.0
        resource.memory_usage = 40.0
        resource.disk_usage = 60.0
        resource.network_in = 10.5
        resource.network_out = 8.2
        resource.load_average = 1.5
        resource.memory_total = 8192.0
        resource.memory_available = 4915.2
        resource.disk_total = 500.0
        resource.disk_available = 200.0
        resource.created_at = datetime.utcnow()
        resource.updated_at = datetime.utcnow()
        
        # 添加方法模拟
        resource.is_critical.return_value = False
        resource.is_warning.return_value = False
        
        return resource
    
    @pytest.fixture
    def mock_session(self):
        """模拟数据库会话"""
        return AsyncMock()
    
    @pytest.fixture
    def mock_agent_repo(self):
        """模拟代理仓库"""
        repo = AsyncMock()
        repo.commit = AsyncMock()
        return repo
    
    @pytest.fixture
    def mock_resource_repo(self):
        """模拟资源仓库"""
        repo = AsyncMock()
        repo.commit = AsyncMock()
        return repo
    
    @pytest.mark.asyncio
    async def test_create_agent_success(self, mock_admin_user, mock_agent, mock_session, mock_agent_repo):
        """测试成功创建代理"""
        # 准备测试数据
        agent_data = AgentCreate(
            name="test-agent",
            ip_address="192.168.1.100",
            version="1.0.0",
            location=AgentLocationCreate(
                country="China",
                city="Beijing",
                latitude=39.9042,
                longitude=116.4074,
                isp="China Telecom"
            ),
            capabilities=AgentCapabilities(
                protocols=["icmp", "tcp", "http"],
                max_concurrent_tasks=10
            )
        )
        
        # 设置模拟返回值
        mock_agent_repo.is_name_taken.return_value = False
        mock_agent_repo.get_by_ip_address.return_value = None
        mock_agent_repo.create.return_value = mock_agent
        
        # 执行测试
        with patch('management_platform.api.routes.agents.AgentRepository', return_value=mock_agent_repo):
            result = await create_agent(agent_data, mock_admin_user, mock_session)
        
        # 验证结果
        assert isinstance(result, AgentResponse)
        assert result.name == "test-agent"
        assert result.ip_address == "192.168.1.100"
        assert result.version == "1.0.0"
        
        # 验证调用
        mock_agent_repo.is_name_taken.assert_called_once_with("test-agent")
        mock_agent_repo.get_by_ip_address.assert_called_once_with("192.168.1.100")
        mock_agent_repo.create.assert_called_once()
        mock_agent_repo.commit.assert_called_once()
    
    @pytest.mark.asyncio
    async def test_create_agent_name_exists(self, mock_admin_user, mock_session, mock_agent_repo):
        """测试创建代理时名称已存在"""
        agent_data = AgentCreate(
            name="existing-agent",
            ip_address="192.168.1.100",
            version="1.0.0"
        )
        
        # 设置模拟返回值
        mock_agent_repo.is_name_taken.return_value = True
        
        # 执行测试并验证异常
        with patch('management_platform.api.routes.agents.AgentRepository', return_value=mock_agent_repo):
            with pytest.raises(HTTPException) as exc_info:
                await create_agent(agent_data, mock_admin_user, mock_session)
        
        assert exc_info.value.status_code == status.HTTP_400_BAD_REQUEST
        assert "代理名称已存在" in str(exc_info.value.detail)
    
    @pytest.mark.asyncio
    async def test_create_agent_ip_exists(self, mock_admin_user, mock_agent, mock_session, mock_agent_repo):
        """测试创建代理时IP地址已存在"""
        agent_data = AgentCreate(
            name="new-agent",
            ip_address="192.168.1.100",
            version="1.0.0"
        )
        
        # 设置模拟返回值
        mock_agent_repo.is_name_taken.return_value = False
        mock_agent_repo.get_by_ip_address.return_value = mock_agent
        
        # 执行测试并验证异常
        with patch('management_platform.api.routes.agents.AgentRepository', return_value=mock_agent_repo):
            with pytest.raises(HTTPException) as exc_info:
                await create_agent(agent_data, mock_admin_user, mock_session)
        
        assert exc_info.value.status_code == status.HTTP_400_BAD_REQUEST
        assert "IP地址已被其他代理使用" in str(exc_info.value.detail)
    
    @pytest.mark.asyncio
    async def test_get_agents_success(self, mock_regular_user, mock_agent, mock_session, mock_agent_repo):
        """测试成功获取代理列表"""
        # 设置模拟返回值
        mock_agent_repo.get_all.return_value = [mock_agent]
        mock_agent_repo.count.return_value = 1
        
        # 执行测试
        with patch('management_platform.api.routes.agents.AgentRepository', return_value=mock_agent_repo):
            result = await get_agents(1, 20, None, None, mock_regular_user, mock_session)
        
        # 验证结果
        assert result.total == 1
        assert result.page == 1
        assert result.size == 20
        assert len(result.agents) == 1
        assert result.agents[0].name == "test-agent"
        
        # 验证调用
        mock_agent_repo.get_all.assert_called_once_with(skip=0, limit=20)
        mock_agent_repo.count.assert_called_once()
    
    @pytest.mark.asyncio
    async def test_get_agents_with_status_filter(self, mock_regular_user, mock_agent, mock_session, mock_agent_repo):
        """测试按状态过滤获取代理列表"""
        # 设置模拟返回值
        mock_agent_repo.get_by_status.return_value = [mock_agent]
        mock_agent_repo.count.return_value = 1
        
        # 执行测试
        with patch('management_platform.api.routes.agents.AgentRepository', return_value=mock_agent_repo):
            result = await get_agents(1, 20, AgentStatus.ONLINE, None, mock_regular_user, mock_session)
        
        # 验证调用
        mock_agent_repo.get_by_status.assert_called_once_with(AgentStatus.ONLINE.value, skip=0, limit=20)
    
    @pytest.mark.asyncio
    async def test_get_agents_with_search(self, mock_regular_user, mock_agent, mock_session, mock_agent_repo):
        """测试搜索代理"""
        # 设置模拟返回值
        mock_agent_repo.search.return_value = [mock_agent]
        mock_agent_repo.count.return_value = 1
        
        # 执行测试
        with patch('management_platform.api.routes.agents.AgentRepository', return_value=mock_agent_repo):
            result = await get_agents(1, 20, None, "test", mock_regular_user, mock_session)
        
        # 验证调用
        mock_agent_repo.search.assert_called_once_with("test", skip=0, limit=20)
    
    @pytest.mark.asyncio
    async def test_get_agent_summary_success(self, mock_regular_user, mock_agent, mock_session, mock_agent_repo):
        """测试成功获取代理摘要"""
        # 设置模拟返回值
        mock_agent_repo.get_all.return_value = [mock_agent]
        mock_agent_repo.count.return_value = 1
        
        # 执行测试
        with patch('management_platform.api.routes.agents.AgentRepository', return_value=mock_agent_repo):
            result = await get_agent_summary(1, 20, mock_regular_user, mock_session)
        
        # 验证结果
        assert result.total == 1
        assert len(result.agents) == 1
        assert isinstance(result.agents[0], AgentSummary)
        assert result.agents[0].name == "test-agent"
    
    @pytest.mark.asyncio
    async def test_get_available_agents_success(self, mock_regular_user, mock_agent, mock_session, mock_agent_repo):
        """测试成功获取可用代理"""
        # 设置模拟返回值
        mock_agent_repo.get_available_agents.return_value = [mock_agent]
        
        # 执行测试
        with patch('management_platform.api.routes.agents.AgentRepository', return_value=mock_agent_repo):
            result = await get_available_agents(1, 20, mock_regular_user, mock_session)
        
        # 验证结果
        assert len(result.agents) == 1
        assert result.agents[0].name == "test-agent"
        
        # 验证调用 - 函数会调用两次，一次获取分页数据，一次获取总数
        assert mock_agent_repo.get_available_agents.call_count == 2
    
    @pytest.mark.asyncio
    async def test_get_agent_success(self, mock_regular_user, mock_agent, mock_session, mock_agent_repo):
        """测试成功获取代理详情"""
        agent_id = uuid.uuid4()
        
        # 设置模拟返回值
        mock_agent_repo.get_by_id.return_value = mock_agent
        
        # 执行测试
        with patch('management_platform.api.routes.agents.AgentRepository', return_value=mock_agent_repo):
            result = await get_agent(agent_id, mock_regular_user, mock_session)
        
        # 验证结果
        assert isinstance(result, AgentResponse)
        assert result.name == "test-agent"
        
        # 验证调用
        mock_agent_repo.get_by_id.assert_called_once_with(agent_id)
    
    @pytest.mark.asyncio
    async def test_get_agent_not_found(self, mock_regular_user, mock_session, mock_agent_repo):
        """测试获取不存在的代理"""
        agent_id = uuid.uuid4()
        
        # 设置模拟返回值
        mock_agent_repo.get_by_id.return_value = None
        
        # 执行测试并验证异常
        with patch('management_platform.api.routes.agents.AgentRepository', return_value=mock_agent_repo):
            with pytest.raises(HTTPException) as exc_info:
                await get_agent(agent_id, mock_regular_user, mock_session)
        
        assert exc_info.value.status_code == status.HTTP_404_NOT_FOUND
        assert "代理不存在" in str(exc_info.value.detail)
    
    @pytest.mark.asyncio
    async def test_update_agent_success(self, mock_admin_user, mock_agent, mock_session, mock_agent_repo):
        """测试成功更新代理"""
        agent_id = uuid.uuid4()
        agent_data = AgentUpdate(
            name="updated-agent",
            version="2.0.0",
            enabled=False
        )
        
        # 设置模拟返回值
        mock_agent_repo.get_by_id.return_value = mock_agent
        mock_agent_repo.is_name_taken.return_value = False
        mock_agent_repo.update.return_value = mock_agent
        
        # 执行测试
        with patch('management_platform.api.routes.agents.AgentRepository', return_value=mock_agent_repo):
            result = await update_agent(agent_id, agent_data, mock_admin_user, mock_session)
        
        # 验证结果
        assert isinstance(result, AgentResponse)
        
        # 验证调用
        mock_agent_repo.get_by_id.assert_called_once_with(agent_id)
        mock_agent_repo.is_name_taken.assert_called_once_with("updated-agent", exclude_agent_id=agent_id)
        mock_agent_repo.update.assert_called_once()
        mock_agent_repo.commit.assert_called_once()
    
    @pytest.mark.asyncio
    async def test_update_agent_not_found(self, mock_admin_user, mock_session, mock_agent_repo):
        """测试更新不存在的代理"""
        agent_id = uuid.uuid4()
        agent_data = AgentUpdate(name="updated-agent")
        
        # 设置模拟返回值
        mock_agent_repo.get_by_id.return_value = None
        
        # 执行测试并验证异常
        with patch('management_platform.api.routes.agents.AgentRepository', return_value=mock_agent_repo):
            with pytest.raises(HTTPException) as exc_info:
                await update_agent(agent_id, agent_data, mock_admin_user, mock_session)
        
        assert exc_info.value.status_code == status.HTTP_404_NOT_FOUND
        assert "代理不存在" in str(exc_info.value.detail)
    
    @pytest.mark.asyncio
    async def test_delete_agent_success(self, mock_admin_user, mock_agent, mock_session, mock_agent_repo):
        """测试成功删除代理"""
        agent_id = uuid.uuid4()
        
        # 设置模拟返回值
        mock_agent_repo.get_by_id.return_value = mock_agent
        mock_agent_repo.delete.return_value = True
        
        # 执行测试
        with patch('management_platform.api.routes.agents.AgentRepository', return_value=mock_agent_repo):
            result = await delete_agent(agent_id, mock_admin_user, mock_session)
        
        # 验证结果
        assert result["message"] == "代理删除成功"
        
        # 验证调用
        mock_agent_repo.get_by_id.assert_called_once_with(agent_id)
        mock_agent_repo.delete.assert_called_once_with(agent_id)
        mock_agent_repo.commit.assert_called_once()
    
    @pytest.mark.asyncio
    async def test_update_heartbeat_success(self, mock_regular_user, mock_session, mock_agent_repo):
        """测试成功更新心跳"""
        agent_id = uuid.uuid4()
        
        # 设置模拟返回值
        mock_agent_repo.update_heartbeat.return_value = True
        
        # 执行测试
        with patch('management_platform.api.routes.agents.AgentRepository', return_value=mock_agent_repo):
            result = await update_heartbeat(agent_id, mock_regular_user, mock_session)
        
        # 验证结果
        assert result["message"] == "心跳更新成功"
        
        # 验证调用
        mock_agent_repo.update_heartbeat.assert_called_once_with(agent_id)
        mock_agent_repo.commit.assert_called_once()
    
    @pytest.mark.asyncio
    async def test_update_heartbeat_not_found(self, mock_regular_user, mock_session, mock_agent_repo):
        """测试更新不存在代理的心跳"""
        agent_id = uuid.uuid4()
        
        # 设置模拟返回值
        mock_agent_repo.update_heartbeat.return_value = False
        
        # 执行测试并验证异常
        with patch('management_platform.api.routes.agents.AgentRepository', return_value=mock_agent_repo):
            with pytest.raises(HTTPException) as exc_info:
                await update_heartbeat(agent_id, mock_regular_user, mock_session)
        
        assert exc_info.value.status_code == status.HTTP_404_NOT_FOUND
        assert "代理不存在" in str(exc_info.value.detail)
    
    @pytest.mark.asyncio
    async def test_enable_agent_success(self, mock_admin_user, mock_agent, mock_session, mock_agent_repo):
        """测试成功启用代理"""
        agent_id = uuid.uuid4()
        
        # 设置模拟返回值
        mock_agent_repo.get_by_id.return_value = mock_agent
        mock_agent_repo.update.return_value = mock_agent
        
        # 执行测试
        with patch('management_platform.api.routes.agents.AgentRepository', return_value=mock_agent_repo):
            result = await enable_agent(agent_id, mock_admin_user, mock_session)
        
        # 验证结果
        assert isinstance(result, AgentResponse)
        
        # 验证调用
        mock_agent_repo.get_by_id.assert_called_once_with(agent_id)
        mock_agent_repo.update.assert_called_once_with(agent_id, {"enabled": True})
        mock_agent_repo.commit.assert_called_once()
    
    @pytest.mark.asyncio
    async def test_disable_agent_success(self, mock_admin_user, mock_agent, mock_session, mock_agent_repo):
        """测试成功禁用代理"""
        agent_id = uuid.uuid4()
        
        # 设置模拟返回值
        mock_agent_repo.get_by_id.return_value = mock_agent
        mock_agent_repo.update.return_value = mock_agent
        
        # 执行测试
        with patch('management_platform.api.routes.agents.AgentRepository', return_value=mock_agent_repo):
            result = await disable_agent(agent_id, mock_admin_user, mock_session)
        
        # 验证结果
        assert isinstance(result, AgentResponse)
        
        # 验证调用
        mock_agent_repo.update.assert_called_once_with(agent_id, {"enabled": False})
    
    @pytest.mark.asyncio
    async def test_set_maintenance_success(self, mock_admin_user, mock_agent, mock_session, mock_agent_repo):
        """测试成功设置维护状态"""
        agent_id = uuid.uuid4()
        
        # 设置模拟返回值
        mock_agent_repo.get_by_id.return_value = mock_agent
        mock_agent_repo.update.return_value = mock_agent
        
        # 执行测试
        with patch('management_platform.api.routes.agents.AgentRepository', return_value=mock_agent_repo):
            result = await set_maintenance(agent_id, mock_admin_user, mock_session)
        
        # 验证结果
        assert isinstance(result, AgentResponse)
        
        # 验证调用
        mock_agent_repo.update.assert_called_once_with(agent_id, {"status": AgentStatus.MAINTENANCE})
    
    @pytest.mark.asyncio
    async def test_create_agent_resource_success(self, mock_regular_user, mock_agent, mock_agent_resource, 
                                               mock_session, mock_agent_repo, mock_resource_repo):
        """测试成功创建代理资源记录"""
        agent_id = uuid.uuid4()
        resource_data = AgentResourceCreate(
            agent_id=agent_id,
            cpu_usage=25.0,
            memory_usage=40.0,
            disk_usage=60.0,
            network_in=10.5,
            network_out=8.2,
            load_average=1.5
        )
        
        # 设置模拟返回值
        mock_agent_repo.get_by_id.return_value = mock_agent
        mock_resource_repo.create.return_value = mock_agent_resource
        
        # 执行测试
        with patch('management_platform.api.routes.agents.AgentRepository', return_value=mock_agent_repo), \
             patch('management_platform.api.routes.agents.AgentResourceRepository', return_value=mock_resource_repo):
            result = await create_agent_resource(agent_id, resource_data, mock_regular_user, mock_session)
        
        # 验证结果
        assert isinstance(result, AgentResourceResponse)
        
        # 验证调用
        mock_agent_repo.get_by_id.assert_called_once_with(agent_id)
        mock_resource_repo.create.assert_called_once()
        mock_agent_repo.update.assert_called_once()  # 更新代理当前资源状态
        mock_resource_repo.commit.assert_called_once()
    
    @pytest.mark.asyncio
    async def test_create_agent_resource_agent_not_found(self, mock_regular_user, mock_session, 
                                                       mock_agent_repo, mock_resource_repo):
        """测试为不存在的代理创建资源记录"""
        agent_id = uuid.uuid4()
        resource_data = AgentResourceCreate(
            agent_id=agent_id,
            cpu_usage=25.0,
            memory_usage=40.0,
            disk_usage=60.0
        )
        
        # 设置模拟返回值
        mock_agent_repo.get_by_id.return_value = None
        
        # 执行测试并验证异常
        with patch('management_platform.api.routes.agents.AgentRepository', return_value=mock_agent_repo), \
             patch('management_platform.api.routes.agents.AgentResourceRepository', return_value=mock_resource_repo):
            with pytest.raises(HTTPException) as exc_info:
                await create_agent_resource(agent_id, resource_data, mock_regular_user, mock_session)
        
        assert exc_info.value.status_code == status.HTTP_404_NOT_FOUND
        assert "代理不存在" in str(exc_info.value.detail)
    
    @pytest.mark.asyncio
    async def test_create_agent_resource_id_mismatch(self, mock_regular_user, mock_agent, mock_session, 
                                                   mock_agent_repo, mock_resource_repo):
        """测试代理ID不匹配"""
        agent_id = uuid.uuid4()
        different_id = uuid.uuid4()
        resource_data = AgentResourceCreate(
            agent_id=different_id,  # 不同的ID
            cpu_usage=25.0,
            memory_usage=40.0,
            disk_usage=60.0
        )
        
        # 设置模拟返回值
        mock_agent_repo.get_by_id.return_value = mock_agent
        
        # 执行测试并验证异常
        with patch('management_platform.api.routes.agents.AgentRepository', return_value=mock_agent_repo), \
             patch('management_platform.api.routes.agents.AgentResourceRepository', return_value=mock_resource_repo):
            with pytest.raises(HTTPException) as exc_info:
                await create_agent_resource(agent_id, resource_data, mock_regular_user, mock_session)
        
        assert exc_info.value.status_code == status.HTTP_400_BAD_REQUEST
        assert "代理ID不匹配" in str(exc_info.value.detail)
    
    @pytest.mark.asyncio
    async def test_get_agent_resources_success(self, mock_regular_user, mock_agent, mock_agent_resource,
                                             mock_session, mock_agent_repo, mock_resource_repo):
        """测试成功获取代理资源记录"""
        agent_id = uuid.uuid4()
        
        # 设置模拟返回值
        mock_agent_repo.get_by_id.return_value = mock_agent
        mock_resource_repo.get_by_agent_id.return_value = [mock_agent_resource]
        mock_resource_repo.count.return_value = 1
        
        # 执行测试
        with patch('management_platform.api.routes.agents.AgentRepository', return_value=mock_agent_repo), \
             patch('management_platform.api.routes.agents.AgentResourceRepository', return_value=mock_resource_repo):
            result = await get_agent_resources(agent_id, 1, 20, mock_regular_user, mock_session)
        
        # 验证结果
        assert result.total == 1
        assert len(result.resources) == 1
        assert isinstance(result.resources[0], AgentResourceResponse)
        
        # 验证调用
        mock_agent_repo.get_by_id.assert_called_once_with(agent_id)
        mock_resource_repo.get_by_agent_id.assert_called_once_with(agent_id, skip=0, limit=20)
        mock_resource_repo.count.assert_called_once_with(agent_id=agent_id)
    
    @pytest.mark.asyncio
    async def test_get_agent_statistics_success(self, mock_regular_user, mock_agent, mock_session,
                                              mock_agent_repo, mock_resource_repo):
        """测试成功获取代理统计"""
        agent_id = uuid.uuid4()
        
        # 设置模拟返回值
        mock_agent_repo.get_by_id.return_value = mock_agent
        mock_resource_repo.get_by_agent_id.return_value = []
        
        # 创建模拟的TaskResultRepository
        mock_result_repo = AsyncMock()
        
        # 执行测试
        with patch('management_platform.api.routes.agents.AgentRepository', return_value=mock_agent_repo), \
             patch('management_platform.api.routes.agents.AgentResourceRepository', return_value=mock_resource_repo), \
             patch('management_platform.api.routes.agents.TaskResultRepository', return_value=mock_result_repo):
            result = await get_agent_statistics(agent_id, 30, mock_regular_user, mock_session)
        
        # 验证结果
        assert isinstance(result, AgentStatistics)
        assert result.agent_id == agent_id
        
        # 验证调用
        mock_agent_repo.get_by_id.assert_called_once_with(agent_id)
    
    @pytest.mark.asyncio
    async def test_get_agent_health_success(self, mock_regular_user, mock_agent, mock_session,
                                          mock_agent_repo, mock_resource_repo):
        """测试成功获取代理健康状态"""
        agent_id = uuid.uuid4()
        
        # 设置模拟返回值
        mock_agent_repo.get_by_id.return_value = mock_agent
        mock_resource_repo.get_by_agent_id.return_value = []
        
        # 执行测试
        with patch('management_platform.api.routes.agents.AgentRepository', return_value=mock_agent_repo), \
             patch('management_platform.api.routes.agents.AgentResourceRepository', return_value=mock_resource_repo):
            result = await get_agent_health(agent_id, mock_regular_user, mock_session)
        
        # 验证结果
        assert isinstance(result, AgentHealthCheck)
        assert result.agent_id == agent_id
        assert result.is_online == True
        assert result.is_available == True
        
        # 验证调用
        mock_agent_repo.get_by_id.assert_called_once_with(agent_id)


if __name__ == "__main__":
    pytest.main([__file__])