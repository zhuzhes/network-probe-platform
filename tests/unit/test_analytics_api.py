"""数据分析API测试"""

import pytest
import uuid
import json
from datetime import datetime, timedelta
from unittest.mock import Mock, patch, AsyncMock
import pytest
from unittest.mock import Mock, patch, AsyncMock
from fastapi import status

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))

from management_platform.api.main import create_app
from shared.models.user import User, UserRole, UserStatus
from shared.models.task import Task, TaskResult, ProtocolType, TaskStatus, TaskResultStatus
from shared.models.agent import Agent, AgentStatus


class TestAnalyticsAPI:
    """数据分析API测试类"""
    
    @pytest.fixture
    def app(self):
        """创建测试应用"""
        return create_app()
    
    @pytest.fixture
    def client(self):
        """创建模拟客户端"""
        return Mock()
    
    @pytest.fixture
    def mock_user(self):
        """模拟用户"""
        return User(
            id=uuid.uuid4(),
            username="testuser",
            email="test@example.com",
            role=UserRole.ENTERPRISE,
            status=UserStatus.ACTIVE,
            credits=100.0
        )
    
    @pytest.fixture
    def mock_admin_user(self):
        """模拟管理员用户"""
        return User(
            id=uuid.uuid4(),
            username="admin",
            email="admin@example.com",
            role=UserRole.ADMIN,
            status=UserStatus.ACTIVE,
            credits=1000.0
        )
    
    @pytest.fixture
    def mock_task(self, mock_user):
        """模拟任务"""
        return Task(
            id=uuid.uuid4(),
            user_id=mock_user.id,
            name="测试任务",
            description="测试描述",
            protocol=ProtocolType.HTTP,
            target="example.com",
            port=80,
            frequency=60,
            timeout=30,
            status=TaskStatus.ACTIVE
        )
    
    @pytest.fixture
    def mock_agent(self):
        """模拟代理"""
        return Agent(
            id=uuid.uuid4(),
            name="测试代理",
            ip_address="192.168.1.100",
            location={"country": "中国", "city": "北京"},
            isp="电信",
            status=AgentStatus.ONLINE
        )
    
    @pytest.fixture
    def mock_task_result(self, mock_task, mock_agent):
        """模拟任务结果"""
        return TaskResult(
            id=uuid.uuid4(),
            task_id=mock_task.id,
            agent_id=mock_agent.id,
            execution_time=datetime.utcnow(),
            duration=150.5,
            status=TaskResultStatus.SUCCESS,
            metrics={"response_time": 150.5, "status_code": 200}
        )
    
    @patch('management_platform.api.dependencies.get_db_session')
    @patch('management_platform.api.dependencies.get_current_user')
    def test_get_results_success(self, mock_get_user, mock_get_session, client, mock_user, mock_task_result):
        """测试获取拨测结果成功"""
        # 设置模拟
        mock_get_user.return_value = mock_user
        mock_session = Mock()
        mock_get_session.return_value = mock_session
        
        # 模拟仓库
        mock_task_repo = Mock()
        mock_result_repo = Mock()
        
        with patch('management_platform.api.routes.analytics.TaskRepository', return_value=mock_task_repo), \
             patch('management_platform.api.routes.analytics.TaskResultRepository', return_value=mock_result_repo):
            
            # 设置仓库方法返回值
            mock_task_repo.get_user_task_ids = AsyncMock(return_value=[mock_task_result.task_id])
            mock_result_repo.get_results_with_filters = AsyncMock(return_value=([mock_task_result], 1))
            
            # 发送请求
            response = client.get("/api/v1/analytics/results")
            
            # 验证响应
            assert response.status_code == status.HTTP_200_OK
            data = response.json()
            assert "results" in data
            assert "total" in data
            assert "page" in data
            assert "size" in data
            assert data["total"] == 1
            assert len(data["results"]) == 1
    
    @patch('management_platform.api.dependencies.get_db_session')
    @patch('management_platform.api.dependencies.get_current_user')
    def test_get_results_with_filters(self, mock_get_user, mock_get_session, client, mock_user):
        """测试带过滤条件获取拨测结果"""
        # 设置模拟
        mock_get_user.return_value = mock_user
        mock_session = Mock()
        mock_get_session.return_value = mock_session
        
        # 模拟仓库
        mock_task_repo = Mock()
        mock_result_repo = Mock()
        
        with patch('management_platform.api.routes.analytics.TaskRepository', return_value=mock_task_repo), \
             patch('management_platform.api.routes.analytics.TaskResultRepository', return_value=mock_result_repo):
            
            # 设置仓库方法返回值
            mock_task_repo.get_user_task_ids = AsyncMock(return_value=[uuid.uuid4()])
            mock_result_repo.get_results_with_filters = AsyncMock(return_value=([], 0))
            
            # 发送带过滤条件的请求
            response = client.get(
                "/api/v1/analytics/results",
                params={
                    "protocol": "http",
                    "status": "success",
                    "page": 1,
                    "size": 10
                }
            )
            
            # 验证响应
            assert response.status_code == status.HTTP_200_OK
            data = response.json()
            assert data["total"] == 0
            assert len(data["results"]) == 0
            assert data["filters"]["protocol"] == "http"
            assert data["filters"]["status"] == "success"
    
    @patch('management_platform.api.dependencies.get_db_session')
    @patch('management_platform.api.dependencies.get_current_user')
    def test_get_results_invalid_task_id(self, mock_get_user, mock_get_session, client, mock_user):
        """测试无效任务ID"""
        # 设置模拟
        mock_get_user.return_value = mock_user
        mock_session = Mock()
        mock_get_session.return_value = mock_session
        
        # 发送带无效任务ID的请求
        response = client.get(
            "/api/v1/analytics/results",
            params={"task_id": "invalid-uuid"}
        )
        
        # 验证响应
        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert "无效的任务ID格式" in response.json()["detail"]
    
    @patch('management_platform.api.dependencies.get_db_session')
    @patch('management_platform.api.dependencies.get_current_user')
    def test_get_statistics_success(self, mock_get_user, mock_get_session, client, mock_admin_user):
        """测试获取统计数据成功"""
        # 设置模拟
        mock_get_user.return_value = mock_admin_user
        mock_session = Mock()
        mock_get_session.return_value = mock_session
        
        # 模拟仓库
        mock_task_repo = Mock()
        mock_result_repo = Mock()
        mock_agent_repo = Mock()
        
        with patch('management_platform.api.routes.analytics.TaskRepository', return_value=mock_task_repo), \
             patch('management_platform.api.routes.analytics.TaskResultRepository', return_value=mock_result_repo), \
             patch('management_platform.api.routes.analytics.AgentRepository', return_value=mock_agent_repo):
            
            # 设置仓库方法返回值
            mock_result_repo.get_summary_statistics = AsyncMock(return_value={
                'total_executions': 100,
                'successful_executions': 95,
                'failed_executions': 5,
                'success_rate': 0.95,
                'avg_response_time': 150.5
            })
            
            mock_task_repo.get_task_statistics = AsyncMock(return_value={
                'total_tasks': 10,
                'status_distribution': {'active': 8, 'paused': 2},
                'protocol_distribution': {'http': 6, 'tcp': 4}
            })
            
            mock_agent_repo.get_agent_statistics = AsyncMock(return_value={
                'total_agents': 5,
                'online_agents': 4,
                'offline_agents': 1,
                'availability_rate': 0.8
            })
            
            mock_result_repo.get_protocol_statistics = AsyncMock(return_value={
                'http': {
                    'total_executions': 60,
                    'successful_executions': 58,
                    'success_rate': 0.967,
                    'avg_response_time': 120.0
                }
            })
            
            # 发送请求
            response = client.get("/api/v1/analytics/statistics")
            
            # 验证响应
            assert response.status_code == status.HTTP_200_OK
            data = response.json()
            assert "summary" in data
            assert "task_statistics" in data
            assert "agent_statistics" in data
            assert "protocol_statistics" in data
            assert "time_range" in data
            
            # 验证统计数据
            assert data["summary"]["total_executions"] == 100
            assert data["summary"]["success_rate"] == 0.95
            assert data["task_statistics"]["total_tasks"] == 10
            assert data["agent_statistics"]["total_agents"] == 5
    
    @patch('management_platform.api.dependencies.get_db_session')
    @patch('management_platform.api.dependencies.get_current_user')
    def test_get_statistics_enterprise_user(self, mock_get_user, mock_get_session, client, mock_user):
        """测试企业用户获取统计数据（不包含代理统计）"""
        # 设置模拟
        mock_get_user.return_value = mock_user
        mock_session = Mock()
        mock_get_session.return_value = mock_session
        
        # 模拟仓库
        mock_task_repo = Mock()
        mock_result_repo = Mock()
        mock_agent_repo = Mock()
        
        with patch('management_platform.api.routes.analytics.TaskRepository', return_value=mock_task_repo), \
             patch('management_platform.api.routes.analytics.TaskResultRepository', return_value=mock_result_repo), \
             patch('management_platform.api.routes.analytics.AgentRepository', return_value=mock_agent_repo):
            
            # 设置仓库方法返回值
            mock_result_repo.get_summary_statistics = AsyncMock(return_value={
                'total_executions': 50,
                'successful_executions': 48,
                'success_rate': 0.96
            })
            
            mock_task_repo.get_task_statistics = AsyncMock(return_value={
                'total_tasks': 5,
                'status_distribution': {'active': 5}
            })
            
            mock_result_repo.get_protocol_statistics = AsyncMock(return_value={})
            
            # 发送请求
            response = client.get("/api/v1/analytics/statistics")
            
            # 验证响应
            assert response.status_code == status.HTTP_200_OK
            data = response.json()
            
            # 企业用户不应该看到代理统计
            assert data["agent_statistics"] == {}
    
    @patch('management_platform.api.dependencies.get_db_session')
    @patch('management_platform.api.dependencies.get_current_user')
    def test_export_data_csv_success(self, mock_get_user, mock_get_session, client, mock_user, mock_task_result):
        """测试CSV格式数据导出成功"""
        # 设置模拟
        mock_get_user.return_value = mock_user
        mock_session = Mock()
        mock_get_session.return_value = mock_session
        
        # 模拟仓库
        mock_task_repo = Mock()
        mock_result_repo = Mock()
        
        with patch('management_platform.api.routes.analytics.TaskRepository', return_value=mock_task_repo), \
             patch('management_platform.api.routes.analytics.TaskResultRepository', return_value=mock_result_repo):
            
            # 设置仓库方法返回值
            mock_task_repo.get_user_task_ids = AsyncMock(return_value=[mock_task_result.task_id])
            mock_result_repo.get_results_with_filters = AsyncMock(return_value=([mock_task_result], 1))
            
            # 发送请求
            export_data = {
                "format": "csv",
                "task_ids": [str(mock_task_result.task_id)]
            }
            response = client.post("/api/v1/analytics/export", json=export_data)
            
            # 验证响应
            assert response.status_code == status.HTTP_200_OK
            assert response.headers["content-type"] == "text/csv; charset=utf-8"
            assert "attachment" in response.headers["content-disposition"]
            
            # 验证CSV内容
            csv_content = response.text
            assert "结果ID" in csv_content  # CSV头部
            assert str(mock_task_result.id) in csv_content  # 数据行
    
    @patch('management_platform.api.dependencies.get_db_session')
    @patch('management_platform.api.dependencies.get_current_user')
    def test_export_data_json_success(self, mock_get_user, mock_get_session, client, mock_user, mock_task_result):
        """测试JSON格式数据导出成功"""
        # 设置模拟
        mock_get_user.return_value = mock_user
        mock_session = Mock()
        mock_get_session.return_value = mock_session
        
        # 模拟仓库
        mock_task_repo = Mock()
        mock_result_repo = Mock()
        
        with patch('management_platform.api.routes.analytics.TaskRepository', return_value=mock_task_repo), \
             patch('management_platform.api.routes.analytics.TaskResultRepository', return_value=mock_result_repo):
            
            # 设置仓库方法返回值
            mock_task_repo.get_user_task_ids = AsyncMock(return_value=[mock_task_result.task_id])
            mock_result_repo.get_results_with_filters = AsyncMock(return_value=([mock_task_result], 1))
            
            # 发送请求
            export_data = {
                "format": "json",
                "start_time": "2024-01-01T00:00:00",
                "end_time": "2024-12-31T23:59:59"
            }
            response = client.post("/api/v1/analytics/export", json=export_data)
            
            # 验证响应
            assert response.status_code == status.HTTP_200_OK
            assert response.headers["content-type"] == "application/json"
            assert "attachment" in response.headers["content-disposition"]
            
            # 验证JSON内容
            json_data = response.json()
            assert "export_info" in json_data
            assert "data" in json_data
            assert json_data["export_info"]["total_records"] == 1
            assert len(json_data["data"]) == 1
    
    @patch('management_platform.api.dependencies.get_db_session')
    @patch('management_platform.api.dependencies.get_current_user')
    def test_export_data_invalid_format(self, mock_get_user, mock_get_session, client, mock_user):
        """测试无效导出格式"""
        # 设置模拟
        mock_get_user.return_value = mock_user
        mock_session = Mock()
        mock_get_session.return_value = mock_session
        
        # 发送请求
        export_data = {
            "format": "xml"  # 不支持的格式
        }
        response = client.post("/api/v1/analytics/export", json=export_data)
        
        # 验证响应
        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert "不支持的导出格式" in response.json()["detail"]
    
    @patch('management_platform.api.dependencies.get_db_session')
    @patch('management_platform.api.dependencies.get_current_user')
    def test_export_data_get_method(self, mock_get_user, mock_get_session, client, mock_user):
        """测试GET方式导出数据"""
        # 设置模拟
        mock_get_user.return_value = mock_user
        mock_session = Mock()
        mock_get_session.return_value = mock_session
        
        # 模拟仓库
        mock_task_repo = Mock()
        mock_result_repo = Mock()
        
        with patch('management_platform.api.routes.analytics.TaskRepository', return_value=mock_task_repo), \
             patch('management_platform.api.routes.analytics.TaskResultRepository', return_value=mock_result_repo):
            
            # 设置仓库方法返回值
            mock_task_repo.get_user_task_ids = AsyncMock(return_value=[])
            mock_result_repo.get_results_with_filters = AsyncMock(return_value=([], 0))
            
            # 发送GET请求
            response = client.get(
                "/api/v1/analytics/export",
                params={
                    "format": "csv",
                    "protocols": "http,tcp",
                    "status_filter": "success"
                }
            )
            
            # 验证响应
            assert response.status_code == status.HTTP_200_OK
            assert response.headers["content-type"] == "text/csv; charset=utf-8"
    
    @patch('management_platform.api.dependencies.get_db_session')
    @patch('management_platform.api.dependencies.get_current_user')
    def test_export_data_no_data(self, mock_get_user, mock_get_session, client, mock_user):
        """测试导出空数据"""
        # 设置模拟
        mock_get_user.return_value = mock_user
        mock_session = Mock()
        mock_get_session.return_value = mock_session
        
        # 模拟仓库
        mock_task_repo = Mock()
        mock_result_repo = Mock()
        
        with patch('management_platform.api.routes.analytics.TaskRepository', return_value=mock_task_repo), \
             patch('management_platform.api.routes.analytics.TaskResultRepository', return_value=mock_result_repo):
            
            # 设置仓库方法返回值（用户没有任务）
            mock_task_repo.get_user_task_ids = AsyncMock(return_value=[])
            
            # 发送请求
            export_data = {"format": "csv"}
            response = client.post("/api/v1/analytics/export", json=export_data)
            
            # 验证响应
            assert response.status_code == status.HTTP_200_OK
            assert "没有可导出的数据" in response.text
    
    def test_get_results_unauthorized(self, client):
        """测试未授权访问"""
        response = client.get("/api/v1/analytics/results")
        assert response.status_code == status.HTTP_401_UNAUTHORIZED
    
    def test_get_statistics_unauthorized(self, client):
        """测试未授权访问统计数据"""
        response = client.get("/api/v1/analytics/statistics")
        assert response.status_code == status.HTTP_401_UNAUTHORIZED
    
    def test_export_data_unauthorized(self, client):
        """测试未授权导出数据"""
        export_data = {"format": "csv"}
        response = client.post("/api/v1/analytics/export", json=export_data)
        assert response.status_code == status.HTTP_401_UNAUTHORIZED


if __name__ == "__main__":
    pytest.main([__file__, "-v"])