"""代理模型单元测试"""

import pytest
import uuid
from datetime import datetime, timedelta
from unittest.mock import patch

from shared.models.agent import (
    Agent, AgentResource, AgentStatus,
    AgentCreate, AgentUpdate, AgentResponse,
    AgentResourceCreate, AgentResourceResponse
)


class TestAgent:
    """Agent模型测试"""
    
    def test_agent_creation(self):
        """测试代理创建"""
        agent = Agent(
            name="test-agent",
            ip_address="192.168.1.100",
            version="1.0.0"
        )
        
        assert agent.name == "test-agent"
        assert agent.ip_address == "192.168.1.100"
        assert agent.version == "1.0.0"
        assert agent.status == AgentStatus.OFFLINE
        assert agent.availability == 0.0
        assert agent.success_rate == 0.0
        assert agent.max_concurrent_tasks == 10
        assert agent.enabled is True
        assert agent.registered_at is not None
    
    def test_agent_name_validation(self):
        """测试代理名称验证"""
        agent = Agent(name="  test-agent  ", ip_address="192.168.1.100", version="1.0.0")
        assert agent.name == "test-agent"
        
        with pytest.raises(ValueError, match="代理名称不能为空"):
            Agent(name="", ip_address="192.168.1.100", version="1.0.0")
        
        with pytest.raises(ValueError, match="代理名称不能为空"):
            Agent(name="   ", ip_address="192.168.1.100", version="1.0.0")
    
    def test_ip_address_validation(self):
        """测试IP地址验证"""
        # 有效的IPv4地址
        agent = Agent(name="test", ip_address="192.168.1.100", version="1.0.0")
        assert agent.ip_address == "192.168.1.100"
        
        # 有效的IPv6地址
        agent = Agent(name="test", ip_address="2001:db8::1", version="1.0.0")
        assert agent.ip_address == "2001:db8::1"
        
        # 无效的IP地址
        with pytest.raises(ValueError, match="无效的IP地址格式"):
            Agent(name="test", ip_address="invalid-ip", version="1.0.0")
        
        with pytest.raises(ValueError, match="无效的IP地址格式"):
            Agent(name="test", ip_address="999.999.999.999", version="1.0.0")
    
    def test_version_validation(self):
        """测试版本号验证"""
        agent = Agent(name="test", ip_address="192.168.1.100", version="  1.0.0  ")
        assert agent.version == "1.0.0"
        
        with pytest.raises(ValueError, match="版本号不能为空"):
            Agent(name="test", ip_address="192.168.1.100", version="")
        
        with pytest.raises(ValueError, match="版本号不能为空"):
            Agent(name="test", ip_address="192.168.1.100", version="   ")
    
    def test_rate_validation(self):
        """测试比率值验证"""
        agent = Agent(name="test", ip_address="192.168.1.100", version="1.0.0")
        
        # 有效值
        agent.availability = 0.5
        agent.success_rate = 0.8
        assert agent.availability == 0.5
        assert agent.success_rate == 0.8
        
        # 边界值
        agent.availability = 0.0
        agent.success_rate = 1.0
        assert agent.availability == 0.0
        assert agent.success_rate == 1.0
        
        # 无效值
        with pytest.raises(ValueError, match="availability 必须在0-1之间"):
            agent.availability = -0.1
        
        with pytest.raises(ValueError, match="availability 必须在0-1之间"):
            agent.availability = 1.1
        
        with pytest.raises(ValueError, match="success_rate 必须在0-1之间"):
            agent.success_rate = -0.1
        
        with pytest.raises(ValueError, match="success_rate 必须在0-1之间"):
            agent.success_rate = 1.1
    
    def test_coordinate_validation(self):
        """测试坐标验证"""
        agent = Agent(name="test", ip_address="192.168.1.100", version="1.0.0")
        
        # 有效坐标
        agent.latitude = 39.9042
        agent.longitude = 116.4074
        assert agent.latitude == 39.9042
        assert agent.longitude == 116.4074
        
        # 边界值
        agent.latitude = -90.0
        agent.longitude = -180.0
        assert agent.latitude == -90.0
        assert agent.longitude == -180.0
        
        agent.latitude = 90.0
        agent.longitude = 180.0
        assert agent.latitude == 90.0
        assert agent.longitude == 180.0
        
        # 无效纬度
        with pytest.raises(ValueError, match="纬度必须在-90到90之间"):
            agent.latitude = -91.0
        
        with pytest.raises(ValueError, match="纬度必须在-90到90之间"):
            agent.latitude = 91.0
        
        # 无效经度
        with pytest.raises(ValueError, match="经度必须在-180到180之间"):
            agent.longitude = -181.0
        
        with pytest.raises(ValueError, match="经度必须在-180到180之间"):
            agent.longitude = 181.0
    
    def test_max_concurrent_tasks_validation(self):
        """测试最大并发任务数验证"""
        agent = Agent(name="test", ip_address="192.168.1.100", version="1.0.0")
        
        # 有效值
        agent.max_concurrent_tasks = 5
        assert agent.max_concurrent_tasks == 5
        
        # 无效值
        with pytest.raises(ValueError, match="最大并发任务数必须大于0"):
            agent.max_concurrent_tasks = 0
        
        with pytest.raises(ValueError, match="最大并发任务数必须大于0"):
            agent.max_concurrent_tasks = -1
    
    def test_is_online(self):
        """测试在线状态检查"""
        agent = Agent(name="test", ip_address="192.168.1.100", version="1.0.0")
        
        agent.status = AgentStatus.ONLINE
        assert agent.is_online() is True
        
        agent.status = AgentStatus.OFFLINE
        assert agent.is_online() is False
        
        agent.status = AgentStatus.BUSY
        assert agent.is_online() is False
        
        agent.status = AgentStatus.MAINTENANCE
        assert agent.is_online() is False
    
    def test_is_heartbeat_recent(self):
        """测试心跳检查"""
        agent = Agent(name="test", ip_address="192.168.1.100", version="1.0.0")
        
        # 没有心跳记录
        assert agent.is_heartbeat_recent() is False
        
        # 最近的心跳
        agent.last_heartbeat = datetime.utcnow() - timedelta(minutes=2)
        assert agent.is_heartbeat_recent() is True
        
        # 过期的心跳
        agent.last_heartbeat = datetime.utcnow() - timedelta(minutes=10)
        assert agent.is_heartbeat_recent() is False
        
        # 自定义超时时间
        agent.last_heartbeat = datetime.utcnow() - timedelta(minutes=8)
        assert agent.is_heartbeat_recent(timeout_minutes=10) is True
        assert agent.is_heartbeat_recent(timeout_minutes=5) is False
    
    def test_is_available(self):
        """测试可用性检查"""
        agent = Agent(name="test", ip_address="192.168.1.100", version="1.0.0")
        
        # 默认状态：离线且未启用
        agent.enabled = False
        assert agent.is_available() is False
        
        # 启用但离线
        agent.enabled = True
        agent.status = AgentStatus.OFFLINE
        assert agent.is_available() is False
        
        # 在线但没有最近心跳
        agent.status = AgentStatus.ONLINE
        assert agent.is_available() is False
        
        # 在线且有最近心跳
        agent.last_heartbeat = datetime.utcnow() - timedelta(minutes=2)
        assert agent.is_available() is True
        
        # 忙碌状态也可用
        agent.status = AgentStatus.BUSY
        assert agent.is_available() is True
        
        # 维护状态不可用
        agent.status = AgentStatus.MAINTENANCE
        assert agent.is_available() is False
    
    def test_update_heartbeat(self):
        """测试心跳更新"""
        agent = Agent(name="test", ip_address="192.168.1.100", version="1.0.0")
        agent.status = AgentStatus.OFFLINE
        
        old_time = agent.last_heartbeat
        agent.update_heartbeat()
        
        assert agent.last_heartbeat != old_time
        assert agent.last_heartbeat is not None
        assert agent.status == AgentStatus.ONLINE
    
    def test_status_transitions(self):
        """测试状态转换"""
        agent = Agent(name="test", ip_address="192.168.1.100", version="1.0.0")
        
        # 设置离线
        agent.set_offline()
        assert agent.status == AgentStatus.OFFLINE
        
        # 设置维护
        agent.set_maintenance()
        assert agent.status == AgentStatus.MAINTENANCE
        
        # 设置在线
        agent.set_online()
        assert agent.status == AgentStatus.ONLINE
        
        # 设置忙碌
        agent.set_busy()
        assert agent.status == AgentStatus.BUSY
        
        # 从忙碌回到在线
        agent.set_online()
        assert agent.status == AgentStatus.ONLINE
        
        # 从离线状态不能设置忙碌
        agent.status = AgentStatus.OFFLINE
        agent.set_busy()
        assert agent.status == AgentStatus.OFFLINE
    
    def test_get_location_string(self):
        """测试位置字符串获取"""
        agent = Agent(name="test", ip_address="192.168.1.100", version="1.0.0")
        
        # 没有位置信息
        assert agent.get_location_string() == "未知位置"
        
        # 只有城市
        agent.city = "北京"
        assert agent.get_location_string() == "北京"
        
        # 只有国家
        agent.city = None
        agent.country = "中国"
        assert agent.get_location_string() == "中国"
        
        # 城市和国家都有
        agent.city = "北京"
        agent.country = "中国"
        assert agent.get_location_string() == "北京, 中国"
    
    def test_capabilities_handling(self):
        """测试能力处理"""
        agent = Agent(name="test", ip_address="192.168.1.100", version="1.0.0")
        
        # 没有能力信息
        assert agent.get_capabilities_list() == []
        assert agent.supports_protocol("http") is False
        
        # 设置能力信息
        agent.capabilities = {
            "protocols": ["http", "https", "tcp", "icmp"]
        }
        
        capabilities = agent.get_capabilities_list()
        assert "http" in capabilities
        assert "https" in capabilities
        assert "tcp" in capabilities
        assert "icmp" in capabilities
        
        assert agent.supports_protocol("http") is True
        assert agent.supports_protocol("HTTP") is True  # 大小写不敏感
        assert agent.supports_protocol("udp") is False
        
        # 无效的能力格式
        agent.capabilities = {"protocols": "invalid"}
        assert agent.get_capabilities_list() == []
        
        agent.capabilities = "invalid"
        assert agent.get_capabilities_list() == []
    
    def test_resource_status(self):
        """测试资源状态"""
        agent = Agent(name="test", ip_address="192.168.1.100", version="1.0.0")
        
        # 没有资源信息
        status = agent.get_resource_status()
        assert status['status'] == "unknown"
        
        # 健康状态
        agent.current_cpu_usage = 50.0
        agent.current_memory_usage = 60.0
        agent.current_disk_usage = 70.0
        
        status = agent.get_resource_status()
        assert status['status'] == "healthy"
        assert not agent.is_overloaded()
        
        # 警告状态
        agent.current_cpu_usage = 80.0
        status = agent.get_resource_status()
        assert status['status'] == "warning"
        assert agent.is_overloaded()
        
        # 临界状态
        agent.current_cpu_usage = 95.0
        status = agent.get_resource_status()
        assert status['status'] == "critical"
        assert agent.is_overloaded()
    
    def test_update_performance_metrics(self):
        """测试性能指标更新"""
        agent = Agent(name="test", ip_address="192.168.1.100", version="1.0.0")
        
        agent.update_performance_metrics(
            availability=0.95,
            avg_response_time=150.5,
            success_rate=0.98
        )
        
        assert agent.availability == 0.95
        assert agent.avg_response_time == 150.5
        assert agent.success_rate == 0.98
        
        # 测试边界值处理
        agent.update_performance_metrics(
            availability=1.5,  # 超过1.0
            avg_response_time=-10.0,  # 负数
            success_rate=-0.1  # 负数
        )
        
        assert agent.availability == 1.0  # 限制在1.0
        assert agent.avg_response_time == 0.0  # 限制在0.0
        assert agent.success_rate == 0.0  # 限制在0.0
    
    def test_update_resource_status(self):
        """测试资源状态更新"""
        agent = Agent(name="test", ip_address="192.168.1.100", version="1.0.0")
        
        agent.update_resource_status(
            cpu_usage=75.5,
            memory_usage=80.2,
            disk_usage=65.8,
            load_average=2.5
        )
        
        assert agent.current_cpu_usage == 75.5
        assert agent.current_memory_usage == 80.2
        assert agent.current_disk_usage == 65.8
        assert agent.current_load_average == 2.5
        
        # 测试边界值处理
        agent.update_resource_status(
            cpu_usage=150.0,  # 超过100
            memory_usage=-10.0,  # 负数
            disk_usage=200.0,  # 超过100
            load_average=-1.0  # 负数
        )
        
        assert agent.current_cpu_usage == 100.0
        assert agent.current_memory_usage == 0.0
        assert agent.current_disk_usage == 100.0
        assert agent.current_load_average == 0.0
    
    def test_get_selection_score(self):
        """测试代理选择评分"""
        agent = Agent(name="test", ip_address="192.168.1.100", version="1.0.0")
        
        # 不可用的代理
        agent.enabled = False
        assert agent.get_selection_score() == 0.0
        
        # 设置为可用状态
        agent.enabled = True
        agent.status = AgentStatus.ONLINE
        agent.last_heartbeat = datetime.utcnow()
        agent.availability = 0.9
        agent.success_rate = 0.95
        agent.current_cpu_usage = 50.0
        agent.current_memory_usage = 60.0
        agent.current_disk_usage = 70.0
        
        score = agent.get_selection_score()
        assert 0.0 < score <= 1.0
        
        # 测试地理位置匹配
        agent.city = "北京"
        agent.country = "中国"
        agent.isp = "中国电信"
        
        score_with_location = agent.get_selection_score(
            target_location="北京",
            target_isp="电信"
        )
        
        score_without_location = agent.get_selection_score()
        assert score_with_location > score_without_location
    
    def test_can_handle_task(self):
        """测试任务处理能力检查"""
        agent = Agent(name="test", ip_address="192.168.1.100", version="1.0.0")
        
        # 设置为可用状态
        agent.enabled = True
        agent.status = AgentStatus.ONLINE
        agent.last_heartbeat = datetime.utcnow()
        agent.capabilities = {"protocols": ["http", "https"]}
        agent.current_cpu_usage = 50.0
        agent.current_memory_usage = 60.0
        agent.current_disk_usage = 70.0
        
        assert agent.can_handle_task("http") is True
        assert agent.can_handle_task("udp") is False
        
        # 过载状态
        agent.current_cpu_usage = 95.0
        assert agent.can_handle_task("http") is False
    
    def test_get_uptime_hours(self):
        """测试运行时间计算"""
        agent = Agent(name="test", ip_address="192.168.1.100", version="1.0.0")
        
        # 没有注册时间
        agent.registered_at = None
        assert agent.get_uptime_hours() is None
        
        # 设置注册时间
        agent.registered_at = datetime.utcnow() - timedelta(hours=24)
        uptime = agent.get_uptime_hours()
        assert uptime is not None
        assert 23.5 < uptime < 24.5  # 允许一些时间误差
    
    def test_to_summary_dict(self):
        """测试摘要字典转换"""
        agent = Agent(name="test", ip_address="192.168.1.100", version="1.0.0")
        agent.city = "北京"
        agent.country = "中国"
        agent.isp = "中国电信"
        agent.status = AgentStatus.ONLINE
        agent.availability = 0.95
        agent.success_rate = 0.98
        agent.last_heartbeat = datetime.utcnow()
        
        summary = agent.to_summary_dict()
        
        assert summary['name'] == "test"
        assert summary['ip_address'] == "192.168.1.100"
        assert summary['location'] == "北京, 中国"
        assert summary['isp'] == "中国电信"
        assert summary['status'] == "online"
        assert summary['availability'] == 0.95
        assert summary['success_rate'] == 0.98
        assert summary['enabled'] is True


class TestAgentResource:
    """AgentResource模型测试"""
    
    def test_agent_resource_creation(self):
        """测试代理资源记录创建"""
        agent_id = uuid.uuid4()
        resource = AgentResource(
            agent_id=agent_id,
            cpu_usage=75.5,
            memory_usage=80.2,
            disk_usage=65.8,
            network_in=10.5,
            network_out=8.3,
            load_average=2.1
        )
        
        assert resource.agent_id == agent_id
        assert resource.cpu_usage == 75.5
        assert resource.memory_usage == 80.2
        assert resource.disk_usage == 65.8
        assert resource.network_in == 10.5
        assert resource.network_out == 8.3
        assert resource.load_average == 2.1
        assert resource.timestamp is not None
    
    def test_percentage_validation(self):
        """测试百分比值验证"""
        agent_id = uuid.uuid4()
        
        # 有效值
        resource = AgentResource(
            agent_id=agent_id,
            cpu_usage=0.0,
            memory_usage=50.0,
            disk_usage=100.0
        )
        assert resource.cpu_usage == 0.0
        assert resource.memory_usage == 50.0
        assert resource.disk_usage == 100.0
        
        # 无效值
        with pytest.raises(ValueError, match="cpu_usage 必须在0-100之间"):
            AgentResource(agent_id=agent_id, cpu_usage=-1.0, memory_usage=50.0, disk_usage=50.0)
        
        with pytest.raises(ValueError, match="cpu_usage 必须在0-100之间"):
            AgentResource(agent_id=agent_id, cpu_usage=101.0, memory_usage=50.0, disk_usage=50.0)
        
        with pytest.raises(ValueError, match="memory_usage 必须在0-100之间"):
            AgentResource(agent_id=agent_id, cpu_usage=50.0, memory_usage=-1.0, disk_usage=50.0)
        
        with pytest.raises(ValueError, match="disk_usage 必须在0-100之间"):
            AgentResource(agent_id=agent_id, cpu_usage=50.0, memory_usage=50.0, disk_usage=101.0)
    
    def test_positive_value_validation(self):
        """测试正数值验证"""
        agent_id = uuid.uuid4()
        
        # 有效值
        resource = AgentResource(
            agent_id=agent_id,
            cpu_usage=50.0,
            memory_usage=50.0,
            disk_usage=50.0,
            network_in=0.0,
            network_out=10.5,
            load_average=1.5
        )
        assert resource.network_in == 0.0
        assert resource.network_out == 10.5
        assert resource.load_average == 1.5
        
        # 无效值
        with pytest.raises(ValueError, match="network_in 不能为负数"):
            AgentResource(
                agent_id=agent_id,
                cpu_usage=50.0,
                memory_usage=50.0,
                disk_usage=50.0,
                network_in=-1.0
            )
        
        with pytest.raises(ValueError, match="load_average 不能为负数"):
            AgentResource(
                agent_id=agent_id,
                cpu_usage=50.0,
                memory_usage=50.0,
                disk_usage=50.0,
                load_average=-0.1
            )
    
    def test_size_validation(self):
        """测试大小值验证"""
        agent_id = uuid.uuid4()
        
        # 有效值
        resource = AgentResource(
            agent_id=agent_id,
            cpu_usage=50.0,
            memory_usage=50.0,
            disk_usage=50.0,
            memory_total=8192.0,
            memory_available=4096.0,
            disk_total=500.0,
            disk_available=200.0
        )
        assert resource.memory_total == 8192.0
        assert resource.disk_available == 200.0
        
        # 无效值
        with pytest.raises(ValueError, match="memory_total 不能为负数"):
            AgentResource(
                agent_id=agent_id,
                cpu_usage=50.0,
                memory_usage=50.0,
                disk_usage=50.0,
                memory_total=-100.0
            )
    
    def test_health_status_checks(self):
        """测试健康状态检查"""
        agent_id = uuid.uuid4()
        
        # 健康状态
        resource = AgentResource(
            agent_id=agent_id,
            cpu_usage=50.0,
            memory_usage=60.0,
            disk_usage=70.0
        )
        assert not resource.is_critical()
        assert not resource.is_warning()
        assert resource.get_health_status() == "healthy"
        
        # 警告状态
        resource.cpu_usage = 80.0
        assert not resource.is_critical()
        assert resource.is_warning()
        assert resource.get_health_status() == "warning"
        
        # 临界状态
        resource.cpu_usage = 95.0
        assert resource.is_critical()
        assert resource.get_health_status() == "critical"
        
        # 磁盘临界状态
        resource.cpu_usage = 50.0
        resource.disk_usage = 96.0
        assert resource.is_critical()
        assert resource.get_health_status() == "critical"
    
    def test_calculated_values(self):
        """测试计算值"""
        agent_id = uuid.uuid4()
        resource = AgentResource(
            agent_id=agent_id,
            cpu_usage=50.0,
            memory_usage=75.0,
            disk_usage=60.0,
            network_in=10.5,
            network_out=8.3,
            memory_total=8192.0,
            disk_total=500.0
        )
        
        # 内存使用量计算
        memory_usage_mb = resource.get_memory_usage_mb()
        assert memory_usage_mb == 8192.0 * 0.75
        
        # 磁盘使用量计算
        disk_usage_gb = resource.get_disk_usage_gb()
        assert disk_usage_gb == 500.0 * 0.60
        
        # 总网络流量计算
        network_total = resource.get_network_total_mbps()
        assert network_total == 10.5 + 8.3
        
        # 缺少数据时返回None
        resource.memory_total = None
        assert resource.get_memory_usage_mb() is None
        
        resource.network_in = None
        assert resource.get_network_total_mbps() is None
    
    def test_to_metrics_dict(self):
        """测试指标字典转换"""
        agent_id = uuid.uuid4()
        timestamp = datetime.utcnow()
        
        resource = AgentResource(
            agent_id=agent_id,
            timestamp=timestamp,
            cpu_usage=75.0,
            memory_usage=80.0,
            disk_usage=65.0,
            network_in=10.5,
            network_out=8.3,
            load_average=2.1,
            memory_total=8192.0,
            disk_total=500.0
        )
        
        metrics = resource.to_metrics_dict()
        
        assert metrics['timestamp'] == timestamp.isoformat()
        assert metrics['cpu_usage'] == 75.0
        assert metrics['memory_usage'] == 80.0
        assert metrics['disk_usage'] == 65.0
        assert metrics['network_in'] == 10.5
        assert metrics['network_out'] == 8.3
        assert metrics['load_average'] == 2.1
        assert metrics['health_status'] == "warning"  # CPU > 70%
        assert metrics['memory_usage_mb'] == 8192.0 * 0.8
        assert metrics['disk_usage_gb'] == 500.0 * 0.65
        assert metrics['network_total_mbps'] == 18.8
    
    def test_compare_with_previous(self):
        """测试与前一记录比较"""
        agent_id = uuid.uuid4()
        base_time = datetime.utcnow()
        
        previous = AgentResource(
            agent_id=agent_id,
            timestamp=base_time - timedelta(minutes=5),
            cpu_usage=60.0,
            memory_usage=70.0,
            disk_usage=50.0,
            load_average=1.5
        )
        
        current = AgentResource(
            agent_id=agent_id,
            timestamp=base_time,
            cpu_usage=75.0,
            memory_usage=65.0,
            disk_usage=52.0,
            load_average=2.0
        )
        
        comparison = current.compare_with_previous(previous)
        
        assert comparison['cpu_change'] == 15.0
        assert comparison['memory_change'] == -5.0
        assert comparison['disk_change'] == 2.0
        assert comparison['load_change'] == 0.5
        assert comparison['time_diff_seconds'] == 300.0
        
        # 没有前一记录
        comparison = current.compare_with_previous(None)
        assert comparison == {}


class TestAgentPydanticModels:
    """测试Agent相关的Pydantic模型"""
    
    def test_agent_create_validation(self):
        """测试AgentCreate验证"""
        # 有效数据
        agent_data = {
            "name": "test-agent",
            "ip_address": "192.168.1.100",
            "version": "1.0.0"
        }
        agent_create = AgentCreate(**agent_data)
        assert agent_create.name == "test-agent"
        assert agent_create.ip_address == "192.168.1.100"
        assert agent_create.version == "1.0.0"
        
        # 名称验证
        from pydantic import ValidationError
        with pytest.raises(ValidationError):
            AgentCreate(name="", ip_address="192.168.1.100", version="1.0.0")
        
        # IP地址验证
        with pytest.raises(ValueError, match="无效的IP地址格式"):
            AgentCreate(name="test", ip_address="invalid-ip", version="1.0.0")
        
        # 名称自动去空格
        agent_create = AgentCreate(name="  test-agent  ", ip_address="192.168.1.100", version="1.0.0")
        assert agent_create.name == "test-agent"
    
    def test_agent_resource_create_validation(self):
        """测试AgentResourceCreate验证"""
        agent_id = uuid.uuid4()
        
        # 有效数据
        resource_data = {
            "agent_id": agent_id,
            "cpu_usage": 75.5,
            "memory_usage": 80.2,
            "disk_usage": 65.8,
            "network_in": 10.5,
            "network_out": 8.3,
            "load_average": 2.1
        }
        resource_create = AgentResourceCreate(**resource_data)
        assert resource_create.agent_id == agent_id
        assert resource_create.cpu_usage == 75.5
        
        # 百分比范围验证
        with pytest.raises(ValueError):
            AgentResourceCreate(
                agent_id=agent_id,
                cpu_usage=-1.0,
                memory_usage=50.0,
                disk_usage=50.0
            )
        
        with pytest.raises(ValueError):
            AgentResourceCreate(
                agent_id=agent_id,
                cpu_usage=101.0,
                memory_usage=50.0,
                disk_usage=50.0
            )
        
        # 负数验证
        with pytest.raises(ValueError):
            AgentResourceCreate(
                agent_id=agent_id,
                cpu_usage=50.0,
                memory_usage=50.0,
                disk_usage=50.0,
                network_in=-1.0
            )


if __name__ == "__main__":
    pytest.main([__file__])