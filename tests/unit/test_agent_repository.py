"""代理仓库测试"""

import pytest
import uuid
from datetime import datetime, timedelta

from management_platform.database.repositories import AgentRepository, AgentResourceRepository
from shared.models.agent import Agent, AgentResource, AgentStatus


def generate_unique_agent_name():
    """生成唯一的代理名称"""
    return f"test_agent_{uuid.uuid4().hex[:8]}"


class TestAgentRepository:
    """代理仓库测试类"""
    
    @pytest.mark.asyncio
    async def test_create_agent(self, db_session):
        """测试创建代理"""
        repo = AgentRepository(db_session)
        
        agent_name = generate_unique_agent_name()
        agent_data = {
            "name": agent_name,
            "ip_address": "192.168.1.100",
            "version": "1.0.0",
            "country": "China",
            "city": "Beijing",
            "isp": "China Telecom"
        }
        
        agent = await repo.create(agent_data)
        
        assert agent.id is not None
        assert agent.name == agent_name
        assert agent.ip_address == "192.168.1.100"
        assert agent.version == "1.0.0"
        assert agent.country == "China"
        assert agent.city == "Beijing"
        assert agent.isp == "China Telecom"
        assert agent.status == AgentStatus.OFFLINE
        assert agent.enabled is True
    
    @pytest.mark.asyncio
    async def test_get_agent_by_id(self, db_session):
        """测试根据ID获取代理"""
        repo = AgentRepository(db_session)
        
        # 创建代理
        agent_data = {
            "name": "Test Agent",
            "ip_address": "192.168.1.101",
            "version": "1.0.0"
        }
        created_agent = await repo.create(agent_data)
        
        # 获取代理
        found_agent = await repo.get_by_id(created_agent.id)
        
        assert found_agent is not None
        assert found_agent.id == created_agent.id
        assert found_agent.name == "Test Agent"
        assert found_agent.ip_address == "192.168.1.101"
    
    @pytest.mark.asyncio
    async def test_get_agent_by_name(self, db_session):
        """测试根据名称获取代理"""
        repo = AgentRepository(db_session)
        
        agent_name = generate_unique_agent_name()
        agent_data = {
            "name": agent_name,
            "ip_address": "192.168.1.102",
            "version": "1.0.0"
        }
        created_agent = await repo.create(agent_data)
        
        found_agent = await repo.get_by_name(agent_name)
        
        assert found_agent is not None
        assert found_agent.id == created_agent.id
        assert found_agent.name == agent_name
    
    @pytest.mark.asyncio
    async def test_get_agent_by_ip_address(self, db_session):
        """测试根据IP地址获取代理"""
        repo = AgentRepository(db_session)
        
        agent_data = {
            "name": generate_unique_agent_name(),
            "ip_address": "192.168.1.103",
            "version": "1.0.0"
        }
        created_agent = await repo.create(agent_data)
        
        found_agent = await repo.get_by_ip_address("192.168.1.103")
        
        assert found_agent is not None
        assert found_agent.id == created_agent.id
        assert found_agent.ip_address == "192.168.1.103"
    
    @pytest.mark.asyncio
    async def test_update_agent(self, db_session):
        """测试更新代理"""
        repo = AgentRepository(db_session)
        
        # 创建代理
        agent_data = {
            "name": "Original Agent",
            "ip_address": "192.168.1.104",
            "version": "1.0.0",
            "country": "China"
        }
        created_agent = await repo.create(agent_data)
        original_updated_at = created_agent.updated_at
        
        # 更新代理
        update_data = {
            "name": "Updated Agent",
            "version": "1.1.0",
            "city": "Shanghai"
        }
        updated_agent = await repo.update(created_agent.id, update_data)
        
        assert updated_agent is not None
        assert updated_agent.name == "Updated Agent"
        assert updated_agent.version == "1.1.0"
        assert updated_agent.city == "Shanghai"
        assert updated_agent.country == "China"  # 保持不变
        assert updated_agent.updated_at > original_updated_at
    
    @pytest.mark.asyncio
    async def test_delete_agent(self, db_session):
        """测试删除代理"""
        repo = AgentRepository(db_session)
        
        # 创建代理
        agent_data = {
            "name": "Agent to Delete",
            "ip_address": "192.168.1.105",
            "version": "1.0.0"
        }
        created_agent = await repo.create(agent_data)
        
        # 删除代理
        result = await repo.delete(created_agent.id)
        assert result is True
        
        # 验证代理已删除
        found_agent = await repo.get_by_id(created_agent.id)
        assert found_agent is None
    
    @pytest.mark.asyncio
    async def test_get_agents_by_status(self, db_session):
        """测试根据状态获取代理"""
        repo = AgentRepository(db_session)
        
        # 创建不同状态的代理
        agents_data = [
            {
                "name": generate_unique_agent_name(),
                "ip_address": "192.168.1.106",
                "version": "1.0.0",
                "status": AgentStatus.ONLINE
            },
            {
                "name": generate_unique_agent_name(),
                "ip_address": "192.168.1.107",
                "version": "1.0.0",
                "status": AgentStatus.OFFLINE
            }
        ]
        
        for agent_data in agents_data:
            await repo.create(agent_data)
        
        # 获取在线代理
        online_agents = await repo.get_by_status(AgentStatus.ONLINE)
        assert len(online_agents) >= 1
        assert all(agent.status == AgentStatus.ONLINE for agent in online_agents)
        
        # 获取离线代理
        offline_agents = await repo.get_by_status(AgentStatus.OFFLINE)
        assert len(offline_agents) >= 1
        assert all(agent.status == AgentStatus.OFFLINE for agent in offline_agents)
    
    @pytest.mark.asyncio
    async def test_get_available_agents(self, db_session):
        """测试获取可用代理"""
        repo = AgentRepository(db_session)
        
        current_time = datetime.utcnow()
        
        # 创建不同可用性的代理
        agents_data = [
            {
                "name": generate_unique_agent_name(),
                "ip_address": "192.168.1.108",
                "version": "1.0.0",
                "status": AgentStatus.ONLINE,
                "enabled": True,
                "last_heartbeat": current_time - timedelta(minutes=1),  # 最近心跳
                "availability": 0.95
            },
            {
                "name": generate_unique_agent_name(),
                "ip_address": "192.168.1.109",
                "version": "1.0.0",
                "status": AgentStatus.ONLINE,
                "enabled": False,  # 未启用
                "last_heartbeat": current_time - timedelta(minutes=1)
            },
            {
                "name": generate_unique_agent_name(),
                "ip_address": "192.168.1.110",
                "version": "1.0.0",
                "status": AgentStatus.ONLINE,
                "enabled": True,
                "last_heartbeat": current_time - timedelta(minutes=10),  # 心跳过期
                "availability": 0.90
            }
        ]
        
        for agent_data in agents_data:
            await repo.create(agent_data)
        
        # 获取可用代理
        available_agents = await repo.get_available_agents()
        
        # 应该只包含启用且心跳最近的代理
        for agent in available_agents:
            assert agent.enabled is True
            assert agent.status in [AgentStatus.ONLINE, AgentStatus.BUSY]
            assert agent.last_heartbeat > current_time - timedelta(minutes=5)
    
    @pytest.mark.asyncio
    async def test_search_agents(self, db_session):
        """测试搜索代理"""
        repo = AgentRepository(db_session)
        
        # 创建代理
        agents_data = [
            {
                "name": "Beijing Agent",
                "ip_address": "192.168.1.111",
                "version": "1.0.0",
                "country": "China",
                "city": "Beijing",
                "isp": "China Telecom"
            },
            {
                "name": "Shanghai Agent",
                "ip_address": "192.168.1.112",
                "version": "1.0.0",
                "country": "China",
                "city": "Shanghai",
                "isp": "China Unicom"
            }
        ]
        
        for agent_data in agents_data:
            await repo.create(agent_data)
        
        # 搜索代理
        beijing_results = await repo.search("Beijing")
        assert len(beijing_results) >= 1
        assert any("Beijing" in agent.name or "Beijing" in (agent.city or "") for agent in beijing_results)
        
        telecom_results = await repo.search("Telecom")
        assert len(telecom_results) >= 1
        assert any("Telecom" in (agent.isp or "") for agent in telecom_results)
        
        ip_results = await repo.search("192.168.1.111")
        assert len(ip_results) >= 1
        assert any("192.168.1.111" in agent.ip_address for agent in ip_results)
    
    @pytest.mark.asyncio
    async def test_count_agents(self, db_session):
        """测试代理计数"""
        repo = AgentRepository(db_session)
        
        initial_count = await repo.count()
        
        # 创建代理
        agent_data = {
            "name": "Count Test Agent",
            "ip_address": "192.168.1.113",
            "version": "1.0.0"
        }
        await repo.create(agent_data)
        
        new_count = await repo.count()
        assert new_count == initial_count + 1
    
    @pytest.mark.asyncio
    async def test_update_heartbeat(self, db_session):
        """测试更新心跳"""
        repo = AgentRepository(db_session)
        
        # 创建离线代理
        agent_data = {
            "name": "Heartbeat Test Agent",
            "ip_address": "192.168.1.114",
            "version": "1.0.0",
            "status": AgentStatus.OFFLINE
        }
        created_agent = await repo.create(agent_data)
        
        # 更新心跳
        result = await repo.update_heartbeat(created_agent.id)
        assert result is True
        
        # 验证心跳已更新且状态变为在线
        updated_agent = await repo.get_by_id(created_agent.id)
        assert updated_agent.last_heartbeat is not None
        assert updated_agent.status == AgentStatus.ONLINE
    
    @pytest.mark.asyncio
    async def test_is_name_taken(self, db_session):
        """测试检查名称是否已被使用"""
        repo = AgentRepository(db_session)
        
        agent_name = generate_unique_agent_name()
        agent_data = {
            "name": agent_name,
            "ip_address": "192.168.1.115",
            "version": "1.0.0"
        }
        created_agent = await repo.create(agent_data)
        
        # 检查已存在的名称
        assert await repo.is_name_taken(agent_name) is True
        
        # 检查不存在的名称
        assert await repo.is_name_taken("nonexistent_agent") is False
        
        # 检查排除特定代理ID的情况
        assert await repo.is_name_taken(agent_name, exclude_agent_id=created_agent.id) is False


class TestAgentResourceRepository:
    """代理资源仓库测试类"""
    
    @pytest.mark.asyncio
    async def test_create_agent_resource(self, db_session):
        """测试创建代理资源记录"""
        agent_repo = AgentRepository(db_session)
        resource_repo = AgentResourceRepository(db_session)
        
        # 创建代理
        agent_data = {
            "name": "Resource Test Agent",
            "ip_address": "192.168.1.116",
            "version": "1.0.0"
        }
        agent = await agent_repo.create(agent_data)
        
        # 创建资源记录
        resource_data = {
            "agent_id": agent.id,
            "timestamp": datetime.utcnow(),
            "cpu_usage": 75.5,
            "memory_usage": 80.2,
            "disk_usage": 65.8,
            "network_in": 10.5,
            "network_out": 8.3,
            "load_average": 2.1
        }
        
        resource = await resource_repo.create(resource_data)
        
        assert resource.id is not None
        assert resource.agent_id == agent.id
        assert resource.cpu_usage == 75.5
        assert resource.memory_usage == 80.2
        assert resource.disk_usage == 65.8
        assert resource.network_in == 10.5
        assert resource.network_out == 8.3
        assert resource.load_average == 2.1
    
    @pytest.mark.asyncio
    async def test_get_resources_by_agent_id(self, db_session):
        """测试获取代理的资源记录"""
        agent_repo = AgentRepository(db_session)
        resource_repo = AgentResourceRepository(db_session)
        
        # 创建代理
        agent_data = {
            "name": "Resource History Agent",
            "ip_address": "192.168.1.117",
            "version": "1.0.0"
        }
        agent = await agent_repo.create(agent_data)
        
        # 创建多个资源记录
        resources_data = [
            {
                "agent_id": agent.id,
                "timestamp": datetime.utcnow() - timedelta(minutes=2),
                "cpu_usage": 70.0,
                "memory_usage": 75.0,
                "disk_usage": 60.0
            },
            {
                "agent_id": agent.id,
                "timestamp": datetime.utcnow() - timedelta(minutes=1),
                "cpu_usage": 80.0,
                "memory_usage": 85.0,
                "disk_usage": 65.0
            }
        ]
        
        for resource_data in resources_data:
            await resource_repo.create(resource_data)
        
        # 获取代理资源记录
        agent_resources = await resource_repo.get_by_agent_id(agent.id)
        
        assert len(agent_resources) == 2
        # 应该按时间戳倒序排列
        assert agent_resources[0].cpu_usage == 80.0  # 最新的记录
        assert agent_resources[1].cpu_usage == 70.0  # 较早的记录
    
    @pytest.mark.asyncio
    async def test_get_latest_resource_by_agent_id(self, db_session):
        """测试获取代理的最新资源记录"""
        agent_repo = AgentRepository(db_session)
        resource_repo = AgentResourceRepository(db_session)
        
        # 创建代理
        agent_data = {
            "name": "Latest Resource Agent",
            "ip_address": "192.168.1.118",
            "version": "1.0.0"
        }
        agent = await agent_repo.create(agent_data)
        
        # 创建多个资源记录
        resources_data = [
            {
                "agent_id": agent.id,
                "timestamp": datetime.utcnow() - timedelta(minutes=5),
                "cpu_usage": 60.0,
                "memory_usage": 65.0,
                "disk_usage": 55.0
            },
            {
                "agent_id": agent.id,
                "timestamp": datetime.utcnow() - timedelta(minutes=1),
                "cpu_usage": 85.0,
                "memory_usage": 90.0,
                "disk_usage": 70.0
            }
        ]
        
        for resource_data in resources_data:
            await resource_repo.create(resource_data)
        
        # 获取最新资源记录
        latest_resource = await resource_repo.get_latest_by_agent_id(agent.id)
        
        assert latest_resource is not None
        assert latest_resource.cpu_usage == 85.0  # 最新的记录
        assert latest_resource.memory_usage == 90.0
        assert latest_resource.disk_usage == 70.0
    
    @pytest.mark.asyncio
    async def test_count_resources(self, db_session):
        """测试资源记录计数"""
        agent_repo = AgentRepository(db_session)
        resource_repo = AgentResourceRepository(db_session)
        
        # 创建代理
        agent_data = {
            "name": "Count Resource Agent",
            "ip_address": "192.168.1.119",
            "version": "1.0.0"
        }
        agent = await agent_repo.create(agent_data)
        
        initial_count = await resource_repo.count(agent_id=agent.id)
        
        # 创建资源记录
        resource_data = {
            "agent_id": agent.id,
            "timestamp": datetime.utcnow(),
            "cpu_usage": 50.0,
            "memory_usage": 55.0,
            "disk_usage": 45.0
        }
        await resource_repo.create(resource_data)
        
        new_count = await resource_repo.count(agent_id=agent.id)
        assert new_count == initial_count + 1