"""任务API端点简单测试"""

import pytest
import uuid
from datetime import datetime, timedelta
from fastapi.testclient import TestClient
from unittest.mock import Mock, patch

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))

from management_platform.api.main import create_app
from shared.models.task import TaskStatus, TaskResultStatus, ProtocolType
from shared.models.user import UserRole, UserStatus


@pytest.fixture
def client():
    """创建测试客户端"""
    app = create_app()
    from fastapi.testclient import TestClient
    return TestClient(app)


@pytest.fixture
def mock_user():
    """模拟用户"""
    user = Mock()
    user.id = uuid.uuid4()
    user.username = "testuser"
    user.email = "test@example.com"
    user.role = UserRole.ENTERPRISE
    user.credits = 100.0
    user.status = UserStatus.ACTIVE
    return user


@pytest.fixture
def mock_admin():
    """模拟管理员用户"""
    admin = Mock()
    admin.id = uuid.uuid4()
    admin.username = "admin"
    admin.email = "admin@example.com"
    admin.role = UserRole.ADMIN
    admin.credits = 1000.0
    admin.status = UserStatus.ACTIVE
    return admin


@pytest.fixture
def mock_task():
    """模拟任务"""
    task = Mock()
    task.id = uuid.uuid4()
    task.user_id = uuid.uuid4()
    task.name = "测试任务"
    task.description = "这是一个测试任务"
    task.protocol = ProtocolType.HTTP
    task.target = "example.com"
    task.port = 80
    task.parameters = {"method": "GET"}
    task.frequency = 60
    task.timeout = 30
    task.priority = 0
    task.status = TaskStatus.ACTIVE
    task.next_run = datetime.utcnow() + timedelta(minutes=1)
    task.preferred_location = None
    task.preferred_isp = None
    task.created_at = datetime.utcnow()
    task.updated_at = datetime.utcnow()
    
    # 添加方法
    task.get_comprehensive_validation.return_value = {'valid': True, 'errors': []}
    task.get_estimated_daily_cost.return_value = 5.0
    task.update_next_run.return_value = None
    
    return task


@pytest.fixture
def mock_task_result():
    """模拟任务结果"""
    result = Mock()
    result.id = uuid.uuid4()
    result.task_id = uuid.uuid4()
    result.agent_id = uuid.uuid4()
    result.execution_time = datetime.utcnow()
    result.duration = 150.0
    result.status = TaskResultStatus.SUCCESS
    result.error_message = None
    result.metrics = {"response_time": 150.0, "status_code": 200}
    result.raw_data = {"headers": {}, "body": "OK"}
    result.created_at = datetime.utcnow()
    result.updated_at = datetime.utcnow()
    
    # 添加方法
    result.get_performance_grade.return_value = "一般"
    result.get_error_summary.return_value = "成功"
    
    return result


class TestTaskAPI:
    """任务API测试类"""
    
    @patch('management_platform.api.dependencies.get_current_user')
    @patch('management_platform.api.dependencies.get_db_session')
    def test_create_task_success(self, mock_db, mock_current_user, client, mock_user, mock_task):
        """测试成功创建任务"""
        mock_current_user.return_value = mock_user
        
        # 模拟仓库
        mock_task_repo = Mock()
        mock_task_repo.create.return_value = mock_task
        mock_task_repo.commit.return_value = None
        
        with patch('management_platform.api.routes.tasks.TaskRepository', return_value=mock_task_repo):
            response = client.post("/api/v1/tasks/", json={
                "name": "测试任务",
                "description": "这是一个测试任务",
                "protocol": "http",
                "target": "example.com",
                "port": 80,
                "parameters": {"method": "GET"},
                "frequency": 60,
                "timeout": 30,
                "priority": 0
            })
        
        assert response.status_code == 200
        data = response.json()
        assert data["name"] == "测试任务"
        assert data["protocol"] == "http"
        assert data["target"] == "example.com"
        assert data["port"] == 80
        assert data["frequency"] == 60
    
    @patch('management_platform.api.dependencies.get_current_user')
    @patch('management_platform.api.dependencies.get_db_session')
    def test_create_task_insufficient_credits(self, mock_db, mock_current_user, client, mock_user):
        """测试余额不足时创建任务失败"""
        # 设置用户余额为0
        mock_user.credits = 0.0
        mock_current_user.return_value = mock_user
        
        response = client.post("/api/v1/tasks/", json={
            "name": "测试任务",
            "protocol": "http",
            "target": "example.com",
            "frequency": 60,
            "timeout": 30
        })
        
        assert response.status_code == 400
        assert "余额不足" in response.json()["detail"]
    
    @patch('management_platform.api.dependencies.get_current_user')
    @patch('management_platform.api.dependencies.get_db_session')
    def test_get_tasks_list(self, mock_db, mock_current_user, client, mock_user, mock_task):
        """测试获取任务列表"""
        mock_current_user.return_value = mock_user
        
        # 模拟仓库
        mock_task_repo = Mock()
        mock_task_repo.get_by_user_id.return_value = [mock_task]
        mock_task_repo.count.return_value = 1
        
        with patch('management_platform.api.routes.tasks.TaskRepository', return_value=mock_task_repo):
            response = client.get("/api/v1/tasks/")
        
        assert response.status_code == 200
        data = response.json()
        assert data["total"] == 1
        assert len(data["tasks"]) == 1
        assert data["tasks"][0]["name"] == "测试任务"
    
    @patch('management_platform.api.dependencies.get_current_user')
    @patch('management_platform.api.dependencies.get_db_session')
    def test_get_task_detail(self, mock_db, mock_current_user, client, mock_user, mock_task):
        """测试获取任务详情"""
        mock_task.user_id = mock_user.id  # 确保任务属于当前用户
        mock_current_user.return_value = mock_user
        
        # 模拟仓库
        mock_task_repo = Mock()
        mock_task_repo.get_by_id.return_value = mock_task
        
        with patch('management_platform.api.routes.tasks.TaskRepository', return_value=mock_task_repo):
            response = client.get(f"/api/v1/tasks/{mock_task.id}")
        
        assert response.status_code == 200
        data = response.json()
        assert data["name"] == "测试任务"
        assert data["id"] == str(mock_task.id)
    
    @patch('management_platform.api.dependencies.get_current_user')
    @patch('management_platform.api.dependencies.get_db_session')
    def test_get_task_not_found(self, mock_db, mock_current_user, client, mock_user):
        """测试获取不存在的任务"""
        mock_current_user.return_value = mock_user
        
        # 模拟仓库
        mock_task_repo = Mock()
        mock_task_repo.get_by_id.return_value = None
        
        with patch('management_platform.api.routes.tasks.TaskRepository', return_value=mock_task_repo):
            response = client.get(f"/api/v1/tasks/{uuid.uuid4()}")
        
        assert response.status_code == 404
        assert "任务不存在" in response.json()["detail"]
    
    @patch('management_platform.api.dependencies.get_current_user')
    @patch('management_platform.api.dependencies.get_db_session')
    def test_get_task_permission_denied(self, mock_db, mock_current_user, client, mock_user, mock_task):
        """测试无权限访问其他用户任务"""
        mock_task.user_id = uuid.uuid4()  # 不同的用户ID
        mock_current_user.return_value = mock_user
        
        # 模拟仓库
        mock_task_repo = Mock()
        mock_task_repo.get_by_id.return_value = mock_task
        
        with patch('management_platform.api.routes.tasks.TaskRepository', return_value=mock_task_repo):
            response = client.get(f"/api/v1/tasks/{mock_task.id}")
        
        assert response.status_code == 403
        assert "无权访问" in response.json()["detail"]
    
    @patch('management_platform.api.dependencies.get_current_user')
    @patch('management_platform.api.dependencies.get_db_session')
    def test_update_task_success(self, mock_db, mock_current_user, client, mock_user, mock_task):
        """测试成功更新任务"""
        mock_task.user_id = mock_user.id  # 确保任务属于当前用户
        mock_current_user.return_value = mock_user
        
        # 更新后的任务
        updated_task = Mock()
        updated_task.id = mock_task.id
        updated_task.user_id = mock_user.id
        updated_task.name = "更新的任务"
        updated_task.description = mock_task.description
        updated_task.protocol = mock_task.protocol
        updated_task.target = mock_task.target
        updated_task.port = mock_task.port
        updated_task.parameters = mock_task.parameters
        updated_task.frequency = 120  # 更新频率
        updated_task.timeout = mock_task.timeout
        updated_task.priority = mock_task.priority
        updated_task.status = mock_task.status
        updated_task.next_run = datetime.utcnow() + timedelta(minutes=2)
        updated_task.preferred_location = mock_task.preferred_location
        updated_task.preferred_isp = mock_task.preferred_isp
        updated_task.created_at = mock_task.created_at
        updated_task.updated_at = datetime.utcnow()
        
        # 模拟仓库
        mock_task_repo = Mock()
        mock_task_repo.get_by_id.return_value = mock_task
        mock_task_repo.update.return_value = updated_task
        mock_task_repo.commit.return_value = None
        
        with patch('management_platform.api.routes.tasks.TaskRepository', return_value=mock_task_repo):
            response = client.put(f"/api/v1/tasks/{mock_task.id}", json={
                "name": "更新的任务",
                "frequency": 120
            })
        
        assert response.status_code == 200
        data = response.json()
        assert data["name"] == "更新的任务"
        assert data["frequency"] == 120
    
    @patch('management_platform.api.dependencies.get_current_user')
    @patch('management_platform.api.dependencies.get_db_session')
    def test_delete_task_success(self, mock_db, mock_current_user, client, mock_user, mock_task):
        """测试成功删除任务"""
        mock_task.user_id = mock_user.id  # 确保任务属于当前用户
        mock_current_user.return_value = mock_user
        
        # 模拟仓库
        mock_task_repo = Mock()
        mock_task_repo.get_by_id.return_value = mock_task
        mock_task_repo.delete.return_value = True
        mock_task_repo.commit.return_value = None
        
        with patch('management_platform.api.routes.tasks.TaskRepository', return_value=mock_task_repo):
            response = client.delete(f"/api/v1/tasks/{mock_task.id}")
        
        assert response.status_code == 200
        assert "删除成功" in response.json()["message"]
    
    @patch('management_platform.api.dependencies.get_current_user')
    @patch('management_platform.api.dependencies.get_db_session')
    def test_pause_task_success(self, mock_db, mock_current_user, client, mock_user, mock_task):
        """测试成功暂停任务"""
        mock_task.user_id = mock_user.id  # 确保任务属于当前用户
        mock_current_user.return_value = mock_user
        
        # 暂停后的任务
        paused_task = Mock()
        paused_task.id = mock_task.id
        paused_task.user_id = mock_user.id
        paused_task.name = mock_task.name
        paused_task.description = mock_task.description
        paused_task.protocol = mock_task.protocol
        paused_task.target = mock_task.target
        paused_task.port = mock_task.port
        paused_task.parameters = mock_task.parameters
        paused_task.frequency = mock_task.frequency
        paused_task.timeout = mock_task.timeout
        paused_task.priority = mock_task.priority
        paused_task.status = TaskStatus.PAUSED
        paused_task.next_run = None
        paused_task.preferred_location = mock_task.preferred_location
        paused_task.preferred_isp = mock_task.preferred_isp
        paused_task.created_at = mock_task.created_at
        paused_task.updated_at = datetime.utcnow()
        
        # 模拟仓库
        mock_task_repo = Mock()
        mock_task_repo.get_by_id.return_value = mock_task
        mock_task_repo.update.return_value = paused_task
        mock_task_repo.commit.return_value = None
        
        with patch('management_platform.api.routes.tasks.TaskRepository', return_value=mock_task_repo):
            response = client.post(f"/api/v1/tasks/{mock_task.id}/pause")
        
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "paused"
        assert data["next_run"] is None
    
    @patch('management_platform.api.dependencies.get_current_user')
    @patch('management_platform.api.dependencies.get_db_session')
    def test_get_task_results(self, mock_db, mock_current_user, client, mock_user, mock_task, mock_task_result):
        """测试获取任务结果"""
        mock_task.user_id = mock_user.id  # 确保任务属于当前用户
        mock_current_user.return_value = mock_user
        
        # 模拟仓库
        mock_task_repo = Mock()
        mock_task_repo.get_by_id.return_value = mock_task
        
        mock_result_repo = Mock()
        mock_result_repo.get_by_task_id.return_value = [mock_task_result]
        
        with patch('management_platform.api.routes.tasks.TaskRepository', return_value=mock_task_repo), \
             patch('management_platform.api.routes.tasks.TaskResultRepository', return_value=mock_result_repo):
            response = client.get(f"/api/v1/tasks/{mock_task.id}/results")
        
        assert response.status_code == 200
        data = response.json()
        assert data["total"] == 1
        assert len(data["results"]) == 1
        result = data["results"][0]
        assert result["status"] == "success"
        assert result["duration"] == 150.0
    
    @patch('management_platform.api.dependencies.get_current_user')
    @patch('management_platform.api.dependencies.get_db_session')
    def test_admin_can_access_all_tasks(self, mock_db, mock_current_user, client, mock_admin, mock_task):
        """测试管理员可以访问所有任务"""
        mock_current_user.return_value = mock_admin
        
        # 模拟仓库
        mock_task_repo = Mock()
        mock_task_repo.get_all.return_value = [mock_task]
        mock_task_repo.count.return_value = 1
        
        with patch('management_platform.api.routes.tasks.TaskRepository', return_value=mock_task_repo):
            response = client.get("/api/v1/tasks/")
        
        assert response.status_code == 200
        data = response.json()
        assert data["total"] == 1
        # 验证调用了get_all而不是get_by_user_id
        mock_task_repo.get_all.assert_called_once()
    
    def test_task_validation_errors(self, client):
        """测试任务验证错误"""
        # 测试缺少必需字段
        response = client.post("/api/v1/tasks/", json={
            "name": "测试任务"
            # 缺少protocol和target
        })
        assert response.status_code == 422  # Validation error
        
        # 测试无效的协议类型
        response = client.post("/api/v1/tasks/", json={
            "name": "测试任务",
            "protocol": "invalid_protocol",
            "target": "example.com"
        })
        assert response.status_code == 422
        
        # 测试无效的频率
        response = client.post("/api/v1/tasks/", json={
            "name": "测试任务",
            "protocol": "http",
            "target": "example.com",
            "frequency": 5  # 小于最小值10
        })
        assert response.status_code == 422


if __name__ == "__main__":
    pytest.main([__file__])