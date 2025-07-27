"""代理模型集成测试"""

import pytest
import uuid
from datetime import datetime, timedelta
from unittest.mock import Mock

from shared.models.agent import Agent, AgentResource, AgentStatus
from shared.models.task import Task, TaskResult, ProtocolType, TaskStatus, TaskResultStatus
from shared.models.user import User, UserRole


class TestAgentTaskIntegration:
    """代理与任务集成测试"""
    
    def test_agent_task_result_relationship(self):
        """测试代理与任务结果的关系"""
        # 创建用户
        user = User(
            username="testuser",
            email="test@example.com",
            password_hash="hashed_password",
            role=UserRole.ENTERPRISE
        )
        
        # 创建代理
        agent = Agent(
            name="test-agent",
            ip_address="192.168.1.100",
            version="1.0.0",
            status=AgentStatus.ONLINE
        )
        
        # 创建任务
        task = Task(
            user_id=user.id,
            name="HTTP测试",
            protocol=ProtocolType.HTTP,
            target="example.com",
            port=80,
            frequency=60
        )
        
        # 创建任务结果
        task_result = TaskResult(
            task_id=task.id,
            agent_id=agent.id,
            execution_time=datetime.utcnow(),
            duration=150.5,
            status=TaskResultStatus.SUCCESS,
            metrics={"response_time": 150.5, "status_code": 200}
        )
        
        # 验证关系
        assert task_result.task_id == task.id
        assert task_result.agent_id == agent.id
        assert task_result.is_successful()
        assert task_result.get_response_time() == 150.5
    
    def test_agent_selection_for_task(self):
        """测试为任务选择代理"""
        # 创建多个代理
        agent1 = Agent(
            name="agent-beijing",
            ip_address="192.168.1.100",
            version="1.0.0",
            status=AgentStatus.ONLINE,
            city="北京",
            country="中国",
            isp="中国电信",
            availability=0.95,
            success_rate=0.98,
            capabilities={"protocols": ["http", "https", "tcp", "icmp"]},
            current_cpu_usage=50.0,
            current_memory_usage=60.0,
            current_disk_usage=70.0
        )
        agent1.last_heartbeat = datetime.utcnow()
        agent1.enabled = True
        
        agent2 = Agent(
            name="agent-shanghai",
            ip_address="192.168.1.101",
            version="1.0.0",
            status=AgentStatus.ONLINE,
            city="上海",
            country="中国",
            isp="中国联通",
            availability=0.90,
            success_rate=0.95,
            capabilities={"protocols": ["http", "https", "tcp"]},
            current_cpu_usage=80.0,
            current_memory_usage=85.0,
            current_disk_usage=75.0
        )
        agent2.last_heartbeat = datetime.utcnow()
        agent2.enabled = True
        
        agent3 = Agent(
            name="agent-offline",
            ip_address="192.168.1.102",
            version="1.0.0",
            status=AgentStatus.OFFLINE,
            availability=0.99,
            success_rate=0.99
        )
        
        agents = [agent1, agent2, agent3]
        
        # 创建HTTP任务，首选北京
        task = Task(
            user_id=uuid.uuid4(),
            name="HTTP测试",
            protocol=ProtocolType.HTTP,
            target="example.com",
            port=80,
            frequency=60,
            preferred_location="北京",
            preferred_isp="电信"
        )
        
        # 筛选可用代理
        available_agents = [agent for agent in agents if agent.is_available()]
        assert len(available_agents) == 2  # agent1 和 agent2
        
        # 筛选支持协议的代理
        protocol_agents = [
            agent for agent in available_agents 
            if agent.can_handle_task(task.protocol.value)
        ]
        assert len(protocol_agents) == 1  # 只有agent1可以处理（agent2过载）
        
        # 计算选择评分
        scores = []
        for agent in available_agents:  # 使用所有可用代理来比较评分
            score = agent.get_selection_score(
                target_location=task.preferred_location,
                target_isp=task.preferred_isp
            )
            scores.append((agent, score))
        
        # 按评分排序
        scores.sort(key=lambda x: x[1], reverse=True)
        
        # agent1应该得分更高（位置匹配 + 资源状态更好）
        assert scores[0][0] == agent1
        assert scores[0][1] > scores[1][1]
    
    def test_agent_resource_monitoring(self):
        """测试代理资源监控"""
        agent = Agent(
            name="test-agent",
            ip_address="192.168.1.100",
            version="1.0.0"
        )
        
        # 创建资源监控记录
        timestamps = []
        resources = []
        
        for i in range(5):
            timestamp = datetime.utcnow() - timedelta(minutes=i*5)
            timestamps.append(timestamp)
            
            resource = AgentResource(
                agent_id=agent.id,
                timestamp=timestamp,
                cpu_usage=50.0 + i*10,  # 递增的CPU使用率
                memory_usage=60.0 + i*5,
                disk_usage=70.0 + i*2,
                network_in=10.0 + i,
                network_out=8.0 + i,
                load_average=1.0 + i*0.5
            )
            resources.append(resource)
        
        # 验证资源记录
        assert len(resources) == 5
        
        # 检查健康状态变化
        assert resources[0].get_health_status() == "healthy"  # CPU 50%
        assert resources[2].get_health_status() == "healthy"  # CPU 70% (still healthy)
        assert resources[4].get_health_status() == "warning"  # CPU 90% (warning, not critical yet)
        
        # 更新代理的当前资源状态
        latest_resource = resources[0]  # 最新的记录
        agent.update_resource_status(
            cpu_usage=latest_resource.cpu_usage,
            memory_usage=latest_resource.memory_usage,
            disk_usage=latest_resource.disk_usage,
            load_average=latest_resource.load_average
        )
        
        # 验证代理状态
        assert agent.current_cpu_usage == 50.0
        assert agent.get_resource_health_status() == "healthy"
        assert not agent.is_overloaded()
        
        # 比较相邻记录
        comparison = resources[0].compare_with_previous(resources[1])
        assert comparison['cpu_change'] == -10.0  # CPU使用率下降
        assert comparison['memory_change'] == -5.0
        assert abs(comparison['time_diff_seconds'] - 300.0) < 1.0  # 5分钟，允许1秒误差
    
    def test_agent_performance_tracking(self):
        """测试代理性能跟踪"""
        agent = Agent(
            name="test-agent",
            ip_address="192.168.1.100",
            version="1.0.0",
            status=AgentStatus.ONLINE
        )
        agent.last_heartbeat = datetime.utcnow()
        agent.enabled = True
        
        # 模拟任务执行结果
        task_results = []
        
        # 创建10个成功的任务结果
        for i in range(10):
            result = TaskResult(
                task_id=uuid.uuid4(),
                agent_id=agent.id,
                execution_time=datetime.utcnow() - timedelta(minutes=i),
                duration=100.0 + i*10,  # 响应时间递增
                status=TaskResultStatus.SUCCESS,
                metrics={"response_time": 100.0 + i*10}
            )
            task_results.append(result)
        
        # 创建2个失败的任务结果
        for i in range(2):
            result = TaskResult(
                task_id=uuid.uuid4(),
                agent_id=agent.id,
                execution_time=datetime.utcnow() - timedelta(minutes=10+i),
                status=TaskResultStatus.ERROR,
                error_message="Connection failed"
            )
            task_results.append(result)
        
        # 计算性能指标
        total_tasks = len(task_results)
        successful_tasks = len([r for r in task_results if r.is_successful()])
        success_rate = successful_tasks / total_tasks
        
        successful_results = [r for r in task_results if r.is_successful()]
        avg_response_time = sum(r.duration for r in successful_results) / len(successful_results)
        
        # 更新代理性能指标
        agent.update_performance_metrics(
            availability=0.95,  # 95%可用性
            avg_response_time=avg_response_time,
            success_rate=success_rate
        )
        
        # 验证性能指标
        assert agent.availability == 0.95
        assert abs(agent.success_rate - (10/12)) < 0.0001  # 10/12 with floating point tolerance
        assert agent.avg_response_time == 145.0  # (100+110+...+190)/10
        
        # 测试选择评分
        score = agent.get_selection_score()
        assert 0.0 < score <= 1.0
    
    def test_agent_capability_matching(self):
        """测试代理能力匹配"""
        # 创建具有不同能力的代理
        http_agent = Agent(
            name="http-agent",
            ip_address="192.168.1.100",
            version="1.0.0",
            status=AgentStatus.ONLINE,
            capabilities={"protocols": ["http", "https"]}
        )
        http_agent.last_heartbeat = datetime.utcnow()
        http_agent.enabled = True
        
        full_agent = Agent(
            name="full-agent",
            ip_address="192.168.1.101",
            version="1.0.0",
            status=AgentStatus.ONLINE,
            capabilities={"protocols": ["http", "https", "tcp", "udp", "icmp"]}
        )
        full_agent.last_heartbeat = datetime.utcnow()
        full_agent.enabled = True
        
        # 测试不同协议的任务
        protocols_to_test = [
            (ProtocolType.HTTP, [http_agent, full_agent]),
            (ProtocolType.HTTPS, [http_agent, full_agent]),
            (ProtocolType.TCP, [full_agent]),
            (ProtocolType.UDP, [full_agent]),
            (ProtocolType.ICMP, [full_agent])
        ]
        
        agents = [http_agent, full_agent]
        
        for protocol, expected_agents in protocols_to_test:
            capable_agents = [
                agent for agent in agents 
                if agent.can_handle_task(protocol.value)
            ]
            
            assert len(capable_agents) == len(expected_agents)
            for expected_agent in expected_agents:
                assert expected_agent in capable_agents
    
    def test_agent_load_balancing(self):
        """测试代理负载均衡"""
        # 创建多个代理，模拟不同的负载状态
        agents = []
        
        # 低负载代理
        low_load_agent = Agent(
            name="low-load-agent",
            ip_address="192.168.1.100",
            version="1.0.0",
            status=AgentStatus.ONLINE,
            current_cpu_usage=30.0,
            current_memory_usage=40.0,
            current_disk_usage=50.0,
            availability=0.98,
            success_rate=0.99
        )
        low_load_agent.last_heartbeat = datetime.utcnow()
        low_load_agent.enabled = True
        agents.append(low_load_agent)
        
        # 中等负载代理
        medium_load_agent = Agent(
            name="medium-load-agent",
            ip_address="192.168.1.101",
            version="1.0.0",
            status=AgentStatus.BUSY,
            current_cpu_usage=60.0,
            current_memory_usage=65.0,
            current_disk_usage=70.0,
            availability=0.95,
            success_rate=0.97
        )
        medium_load_agent.last_heartbeat = datetime.utcnow()
        medium_load_agent.enabled = True
        agents.append(medium_load_agent)
        
        # 高负载代理
        high_load_agent = Agent(
            name="high-load-agent",
            ip_address="192.168.1.102",
            version="1.0.0",
            status=AgentStatus.ONLINE,
            current_cpu_usage=85.0,
            current_memory_usage=90.0,
            current_disk_usage=80.0,
            availability=0.90,
            success_rate=0.92
        )
        high_load_agent.last_heartbeat = datetime.utcnow()
        high_load_agent.enabled = True
        agents.append(high_load_agent)
        
        # 过载代理
        overloaded_agent = Agent(
            name="overloaded-agent",
            ip_address="192.168.1.103",
            version="1.0.0",
            status=AgentStatus.ONLINE,
            current_cpu_usage=95.0,
            current_memory_usage=95.0,
            current_disk_usage=98.0,
            availability=0.85,
            success_rate=0.88
        )
        overloaded_agent.last_heartbeat = datetime.utcnow()
        overloaded_agent.enabled = True
        agents.append(overloaded_agent)
        
        # 检查负载状态
        assert not low_load_agent.is_overloaded()
        assert not medium_load_agent.is_overloaded()
        assert high_load_agent.is_overloaded()
        assert overloaded_agent.is_overloaded()
        
        # 计算选择评分并排序
        scores = [(agent, agent.get_selection_score()) for agent in agents]
        scores.sort(key=lambda x: x[1], reverse=True)
        
        # 验证排序结果：低负载代理应该得分最高
        assert scores[0][0] == low_load_agent
        assert scores[1][0] == medium_load_agent
        # 高负载和过载代理的评分应该较低
        assert scores[0][1] > scores[2][1]
        assert scores[0][1] > scores[3][1]
    
    def test_agent_heartbeat_and_availability(self):
        """测试代理心跳和可用性"""
        agent = Agent(
            name="test-agent",
            ip_address="192.168.1.100",
            version="1.0.0",
            status=AgentStatus.OFFLINE
        )
        agent.enabled = True
        
        # 初始状态：离线且无心跳
        assert not agent.is_available()
        assert not agent.is_heartbeat_recent()
        
        # 更新心跳，状态应该变为在线
        agent.update_heartbeat()
        assert agent.status == AgentStatus.ONLINE
        assert agent.is_heartbeat_recent()
        assert agent.is_available()
        
        # 模拟心跳超时
        agent.last_heartbeat = datetime.utcnow() - timedelta(minutes=10)
        assert not agent.is_heartbeat_recent()
        assert not agent.is_available()
        
        # 设置维护状态
        agent.set_maintenance()
        agent.last_heartbeat = datetime.utcnow()  # 恢复心跳
        assert agent.is_heartbeat_recent()
        assert not agent.is_available()  # 维护状态不可用
        
        # 恢复在线状态
        agent.set_online()
        assert agent.is_available()
    
    def test_agent_summary_and_statistics(self):
        """测试代理摘要和统计信息"""
        agent = Agent(
            name="test-agent",
            ip_address="192.168.1.100",
            version="1.0.0",
            city="北京",
            country="中国",
            isp="中国电信",
            status=AgentStatus.ONLINE,
            availability=0.95,
            success_rate=0.98,
            avg_response_time=120.5,
            registered_at=datetime.utcnow() - timedelta(hours=48)
        )
        agent.last_heartbeat = datetime.utcnow() - timedelta(minutes=2)
        
        # 获取摘要信息
        summary = agent.to_summary_dict()
        
        assert summary['name'] == "test-agent"
        assert summary['ip_address'] == "192.168.1.100"
        assert summary['location'] == "北京, 中国"
        assert summary['isp'] == "中国电信"
        assert summary['status'] == "online"
        assert summary['status_display'] == "在线"
        assert summary['availability'] == 0.95
        assert summary['success_rate'] == 0.98
        assert summary['enabled'] is True
        
        # 检查运行时间
        uptime = agent.get_uptime_hours()
        assert uptime is not None
        assert 47.5 < uptime < 48.5  # 大约48小时
        
        # 检查状态显示
        status_displays = {
            AgentStatus.ONLINE: "在线",
            AgentStatus.OFFLINE: "离线",
            AgentStatus.BUSY: "忙碌",
            AgentStatus.MAINTENANCE: "维护中"
        }
        
        for status, display in status_displays.items():
            agent.status = status
            assert agent.get_status_display() == display


if __name__ == "__main__":
    pytest.main([__file__])