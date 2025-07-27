"""任务API端点测试"""

import pytest
import uuid
from datetime import datetime, timedelta
from httpx import AsyncClient
from unittest.mock import Mock, patch, AsyncMock

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))

from management_platform.api.main import create_app
from shared.models.task import TaskStatus, TaskResultStatus, ProtocolType
from shared.models.user import UserRole, UserStatus


@pytest.fixture
async def client():
    """创建测试客户端"""
    app = create_app()
    async with AsyncClient(app=app, base_url="http://test") as ac:
        yield ac


class TestTaskAPI:
    """任务API测试类"""
    
    def setup_method(self):
        """测试前设置"""
        self.test_user_id = uuid.uuid4()
        self.test_task_id = uuid.uuid4()
        self.test_agent_id = uuid.uuid4()
        
        # 模拟用户
        self.mock_user = Mock()
        self.mock_user.id = self.test_user_id
        self.mock_user.username = "testuser"
        self.mock_user.email = "test@example.com"
        self.mock_user.role = UserRole.ENTERPRISE
        self.mock_user.credits = 100.0
        self.mock_user.status = UserStatus.ACTIVE
        
        # 模拟管理员用户
        self.mock_admin = Mock()
        self.mock_admin.id = uuid.uuid4()
        self.mock_admin.username = "admin"
        self.mock_admin.email = "admin@example.com"
        self.mock_admin.role = UserRole.ADMIN
        self.mock_admin.credits = 1000.0
        self.mock_admin.status = UserStatus.ACTIVE
        
        # 模拟任务
        self.mock_task = Mock()
        self.mock_task.id = self.test_task_id
        self.mock_task.user_id = self.test_user_id
        self.mock_task.name = "测试任务"
        self.mock_task.description = "这是一个测试任务"
        self.mock_task.protocol = ProtocolType.HTTP
        self.mock_task.target = "example.com"
        self.mock_task.port = 80
        self.mock_task.parameters = {"method": "GET"}
        self.mock_task.frequency = 60
        self.mock_task.timeout = 30
        self.mock_task.priority = 0
        self.mock_task.status = TaskStatus.ACTIVE
        self.mock_task.next_run = datetime.utcnow() + timedelta(minutes=1)
        self.mock_task.preferred_location = None
        self.mock_task.preferred_isp = None
        self.mock_task.created_at = datetime.utcnow()
        self.mock_task.updated_at = datetime.utcnow()
        
        # 模拟任务结果
        self.mock_result = Mock()
        self.mock_result.id = uuid.uuid4()
        self.mock_result.task_id = self.test_task_id
        self.mock_result.agent_id = self.test_agent_id
        self.mock_result.execution_time = datetime.utcnow()
        self.mock_result.duration = 150.0
        self.mock_result.status = TaskResultStatus.SUCCESS
        self.mock_result.error_message = None
        self.mock_result.metrics = {"response_time": 150.0, "status_code": 200}
        self.mock_result.raw_data = {"headers": {}, "body": "OK"}
        self.mock_result.created_at = datetime.utcnow()
        self.mock_result.updated_at = datetime.utcnow()
        
        # 为结果添加方法
        self.mock_result.get_performance_grade.return_value = "一般"
        self.mock_result.get_error_summary.return_value = "成功"
    
    @patch('management_platform.api.dependencies.get_current_user')
    @patch('management_platform.api.dependencies.get_db_session')
    def test_create_task_success(self, mock_db, mock_user, client):
        """测试成功创建任务"""
        mock_user.return_value = self.mock_user
        
        # 模拟仓库
        mock_task_repo = Mock()
        mock_task_repo.create.return_value = self.mock_task
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
    def test_create_task_insufficient_credits(self, mock_db, mock_user):
        """测试余额不足时创建任务失败"""
        # 设置用户余额为0
        self.mock_user.credits = 0.0
        mock_user.return_value = self.mock_user
        
        response = self.client.post("/api/v1/tasks/", json={
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
    def test_create_task_invalid_config(self, mock_db, mock_user):
        """测试无效配置创建任务失败"""
        mock_user.return_value = self.mock_user
        
        response = self.client.post("/api/v1/tasks/", json={
            "name": "测试任务",
            "protocol": "tcp",
            "target": "example.com",
            # TCP协议缺少端口号
            "frequency": 60,
            "timeout": 30
        })
        
        assert response.status_code == 400
        assert "配置无效" in response.json()["detail"]
    
    @patch('management_platform.api.dependencies.get_current_user')
    @patch('management_platform.api.dependencies.get_db_session')
    def test_get_tasks_list(self, mock_db, mock_user):
        """测试获取任务列表"""
        mock_user.return_value = self.mock_user
        
        # 模拟仓库
        mock_task_repo = Mock()
        mock_task_repo.get_by_user_id.return_value = [self.mock_task]
        mock_task_repo.count.return_value = 1
        
        with patch('management_platform.api.routes.tasks.TaskRepository', return_value=mock_task_repo):
            response = self.client.get("/api/v1/tasks/")
        
        assert response.status_code == 200
        data = response.json()
        assert data["total"] == 1
        assert len(data["tasks"]) == 1
        assert data["tasks"][0]["name"] == "测试任务"
    
    @patch('management_platform.api.dependencies.get_current_user')
    @patch('management_platform.api.dependencies.get_db_session')
    def test_get_tasks_with_filters(self, mock_db, mock_user):
        """测试带过滤器的任务列表"""
        mock_user.return_value = self.mock_user
        
        # 模拟仓库
        mock_task_repo = Mock()
        mock_task_repo.search.return_value = [self.mock_task]
        mock_task_repo.count.return_value = 1
        
        with patch('management_platform.api.routes.tasks.TaskRepository', return_value=mock_task_repo):
            response = self.client.get("/api/v1/tasks/?search=测试&status=active&protocol=http")
        
        assert response.status_code == 200
        data = response.json()
        assert data["total"] == 1
        mock_task_repo.search.assert_called_once()
    
    @patch('management_platform.api.dependencies.get_current_user')
    @patch('management_platform.api.dependencies.get_db_session')
    def test_get_task_summary(self, mock_db, mock_user):
        """测试获取任务摘要"""
        mock_user.return_value = self.mock_user
        
        # 模拟仓库
        mock_task_repo = Mock()
        mock_task_repo.get_by_user_id.return_value = [self.mock_task]
        mock_task_repo.count.return_value = 1
        
        mock_result_repo = Mock()
        mock_result_repo.get_by_task_id.return_value = [self.mock_result]
        
        with patch('management_platform.api.routes.tasks.TaskRepository', return_value=mock_task_repo), \
             patch('management_platform.api.routes.tasks.TaskResultRepository', return_value=mock_result_repo):
            response = self.client.get("/api/v1/tasks/summary")
        
        assert response.status_code == 200
        data = response.json()
        assert data["total"] == 1
        assert len(data["tasks"]) == 1
        task_summary = data["tasks"][0]
        assert task_summary["name"] == "测试任务"
        assert task_summary["success_rate"] == 1.0  # 1个成功结果
        assert task_summary["avg_response_time"] == 150.0
    
    @patch('management_platform.api.dependencies.get_current_user')
    @patch('management_platform.api.dependencies.get_db_session')
    def test_get_task_detail(self, mock_db, mock_user):
        """测试获取任务详情"""
        mock_user.return_value = self.mock_user
        
        # 模拟仓库
        mock_task_repo = Mock()
        mock_task_repo.get_by_id.return_value = self.mock_task
        
        with patch('management_platform.api.routes.tasks.TaskRepository', return_value=mock_task_repo):
            response = self.client.get(f"/api/v1/tasks/{self.test_task_id}")
        
        assert response.status_code == 200
        data = response.json()
        assert data["name"] == "测试任务"
        assert data["id"] == str(self.test_task_id)
    
    @patch('management_platform.api.dependencies.get_current_user')
    @patch('management_platform.api.dependencies.get_db_session')
    def test_get_task_not_found(self, mock_db, mock_user):
        """测试获取不存在的任务"""
        mock_user.return_value = self.mock_user
        
        # 模拟仓库
        mock_task_repo = Mock()
        mock_task_repo.get_by_id.return_value = None
        
        with patch('management_platform.api.routes.tasks.TaskRepository', return_value=mock_task_repo):
            response = self.client.get(f"/api/v1/tasks/{uuid.uuid4()}")
        
        assert response.status_code == 404
        assert "任务不存在" in response.json()["detail"]
    
    @patch('management_platform.api.dependencies.get_current_user')
    @patch('management_platform.api.dependencies.get_db_session')
    def test_get_task_permission_denied(self, mock_db, mock_user):
        """测试无权限访问其他用户任务"""
        mock_user.return_value = self.mock_user
        
        # 创建其他用户的任务
        other_task = Mock()
        other_task.id = self.test_task_id
        other_task.user_id = uuid.uuid4()  # 不同的用户ID
        
        # 模拟仓库
        mock_task_repo = Mock()
        mock_task_repo.get_by_id.return_value = other_task
        
        with patch('management_platform.api.routes.tasks.TaskRepository', return_value=mock_task_repo):
            response = self.client.get(f"/api/v1/tasks/{self.test_task_id}")
        
        assert response.status_code == 403
        assert "无权访问" in response.json()["detail"]
    
    @patch('management_platform.api.dependencies.get_current_user')
    @patch('management_platform.api.dependencies.get_db_session')
    def test_update_task_success(self, mock_db, mock_user):
        """测试成功更新任务"""
        mock_user.return_value = self.mock_user
        
        # 更新后的任务
        updated_task = Mock()
        updated_task.id = self.test_task_id
        updated_task.user_id = self.test_user_id
        updated_task.name = "更新的任务"
        updated_task.description = self.mock_task.description
        updated_task.protocol = self.mock_task.protocol
        updated_task.target = self.mock_task.target
        updated_task.port = self.mock_task.port
        updated_task.parameters = self.mock_task.parameters
        updated_task.frequency = 120  # 更新频率
        updated_task.timeout = self.mock_task.timeout
        updated_task.priority = self.mock_task.priority
        updated_task.status = self.mock_task.status
        updated_task.next_run = datetime.utcnow() + timedelta(minutes=2)
        updated_task.preferred_location = self.mock_task.preferred_location
        updated_task.preferred_isp = self.mock_task.preferred_isp
        updated_task.created_at = self.mock_task.created_at
        updated_task.updated_at = datetime.utcnow()
        
        # 模拟仓库
        mock_task_repo = Mock()
        mock_task_repo.get_by_id.return_value = self.mock_task
        mock_task_repo.update.return_value = updated_task
        mock_task_repo.commit.return_value = None
        
        with patch('management_platform.api.routes.tasks.TaskRepository', return_value=mock_task_repo):
            response = self.client.put(f"/api/v1/tasks/{self.test_task_id}", json={
                "name": "更新的任务",
                "frequency": 120
            })
        
        assert response.status_code == 200
        data = response.json()
        assert data["name"] == "更新的任务"
        assert data["frequency"] == 120
    
    @patch('management_platform.api.dependencies.get_current_user')
    @patch('management_platform.api.dependencies.get_db_session')
    def test_delete_task_success(self, mock_db, mock_user):
        """测试成功删除任务"""
        mock_user.return_value = self.mock_user
        
        # 模拟仓库
        mock_task_repo = Mock()
        mock_task_repo.get_by_id.return_value = self.mock_task
        mock_task_repo.delete.return_value = True
        mock_task_repo.commit.return_value = None
        
        with patch('management_platform.api.routes.tasks.TaskRepository', return_value=mock_task_repo):
            response = self.client.delete(f"/api/v1/tasks/{self.test_task_id}")
        
        assert response.status_code == 200
        assert "删除成功" in response.json()["message"]
    
    @patch('management_platform.api.dependencies.get_current_user')
    @patch('management_platform.api.dependencies.get_db_session')
    def test_pause_task_success(self, mock_db, mock_user):
        """测试成功暂停任务"""
        mock_user.return_value = self.mock_user
        
        # 暂停后的任务
        paused_task = Mock()
        paused_task.id = self.test_task_id
        paused_task.user_id = self.test_user_id
        paused_task.name = self.mock_task.name
        paused_task.description = self.mock_task.description
        paused_task.protocol = self.mock_task.protocol
        paused_task.target = self.mock_task.target
        paused_task.port = self.mock_task.port
        paused_task.parameters = self.mock_task.parameters
        paused_task.frequency = self.mock_task.frequency
        paused_task.timeout = self.mock_task.timeout
        paused_task.priority = self.mock_task.priority
        paused_task.status = TaskStatus.PAUSED
        paused_task.next_run = None
        paused_task.preferred_location = self.mock_task.preferred_location
        paused_task.preferred_isp = self.mock_task.preferred_isp
        paused_task.created_at = self.mock_task.created_at
        paused_task.updated_at = datetime.utcnow()
        
        # 模拟仓库
        mock_task_repo = Mock()
        mock_task_repo.get_by_id.return_value = self.mock_task
        mock_task_repo.update.return_value = paused_task
        mock_task_repo.commit.return_value = None
        
        with patch('management_platform.api.routes.tasks.TaskRepository', return_value=mock_task_repo):
            response = self.client.post(f"/api/v1/tasks/{self.test_task_id}/pause")
        
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "paused"
        assert data["next_run"] is None
    
    @patch('management_platform.api.dependencies.get_current_user')
    @patch('management_platform.api.dependencies.get_db_session')
    def test_resume_task_success(self, mock_db, mock_user):
        """测试成功恢复任务"""
        mock_user.return_value = self.mock_user
        
        # 暂停状态的任务
        paused_task = Mock()
        paused_task.id = self.test_task_id
        paused_task.user_id = self.test_user_id
        paused_task.status = TaskStatus.PAUSED
        paused_task.frequency = 60
        
        # 恢复后的任务
        resumed_task = Mock()
        resumed_task.id = self.test_task_id
        resumed_task.user_id = self.test_user_id
        resumed_task.name = self.mock_task.name
        resumed_task.description = self.mock_task.description
        resumed_task.protocol = self.mock_task.protocol
        resumed_task.target = self.mock_task.target
        resumed_task.port = self.mock_task.port
        resumed_task.parameters = self.mock_task.parameters
        resumed_task.frequency = self.mock_task.frequency
        resumed_task.timeout = self.mock_task.timeout
        resumed_task.priority = self.mock_task.priority
        resumed_task.status = TaskStatus.ACTIVE
        resumed_task.next_run = datetime.utcnow() + timedelta(minutes=1)
        resumed_task.preferred_location = self.mock_task.preferred_location
        resumed_task.preferred_isp = self.mock_task.preferred_isp
        resumed_task.created_at = self.mock_task.created_at
        resumed_task.updated_at = datetime.utcnow()
        
        # 模拟仓库
        mock_task_repo = Mock()
        mock_task_repo.get_by_id.return_value = paused_task
        mock_task_repo.update.return_value = resumed_task
        mock_task_repo.commit.return_value = None
        
        with patch('management_platform.api.routes.tasks.TaskRepository', return_value=mock_task_repo):
            response = self.client.post(f"/api/v1/tasks/{self.test_task_id}/resume")
        
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "active"
        assert data["next_run"] is not None
    
    @patch('management_platform.api.dependencies.get_current_user')
    @patch('management_platform.api.dependencies.get_db_session')
    def test_batch_operation_pause(self, mock_db, mock_user):
        """测试批量暂停任务"""
        mock_user.return_value = self.mock_user
        
        task_ids = [self.test_task_id, uuid.uuid4()]
        
        # 模拟仓库
        mock_task_repo = Mock()
        mock_task_repo.get_by_id.side_effect = [self.mock_task, self.mock_task]
        mock_task_repo.pause_tasks_batch.return_value = 2
        mock_task_repo.commit.return_value = None
        
        with patch('management_platform.api.routes.tasks.TaskRepository', return_value=mock_task_repo):
            response = self.client.post("/api/v1/tasks/batch", json={
                "task_ids": [str(tid) for tid in task_ids],
                "action": "pause"
            })
        
        assert response.status_code == 200
        data = response.json()
        assert data["success_count"] == 2
        assert data["failed_count"] == 0
        assert "暂停" in data["message"]
    
    @patch('management_platform.api.dependencies.get_current_user')
    @patch('management_platform.api.dependencies.get_db_session')
    def test_get_task_results(self, mock_db, mock_user):
        """测试获取任务结果"""
        mock_user.return_value = self.mock_user
        
        # 模拟仓库
        mock_task_repo = Mock()
        mock_task_repo.get_by_id.return_value = self.mock_task
        
        mock_result_repo = Mock()
        mock_result_repo.get_by_task_id.return_value = [self.mock_result]
        
        with patch('management_platform.api.routes.tasks.TaskRepository', return_value=mock_task_repo), \
             patch('management_platform.api.routes.tasks.TaskResultRepository', return_value=mock_result_repo):
            response = self.client.get(f"/api/v1/tasks/{self.test_task_id}/results")
        
        assert response.status_code == 200
        data = response.json()
        assert data["total"] == 1
        assert len(data["results"]) == 1
        result = data["results"][0]
        assert result["status"] == "success"
        assert result["duration"] == 150.0
    
    @patch('management_platform.api.dependencies.get_current_user')
    @patch('management_platform.api.dependencies.get_db_session')
    def test_get_task_statistics(self, mock_db, mock_user):
        """测试获取任务统计"""
        mock_user.return_value = self.mock_user
        
        # 模拟仓库
        mock_task_repo = Mock()
        mock_task_repo.get_by_id.return_value = self.mock_task
        
        mock_result_repo = Mock()
        mock_result_repo.get_by_task_id.return_value = [self.mock_result, self.mock_result]
        
        with patch('management_platform.api.routes.tasks.TaskRepository', return_value=mock_task_repo), \
             patch('management_platform.api.routes.tasks.TaskResultRepository', return_value=mock_result_repo):
            response = self.client.get(f"/api/v1/tasks/{self.test_task_id}/statistics")
        
        assert response.status_code == 200
        data = response.json()
        assert data["task_id"] == str(self.test_task_id)
        assert data["total_executions"] == 2
        assert data["successful_executions"] == 2
        assert data["success_rate"] == 1.0
        assert data["avg_response_time"] == 150.0
    
    @patch('management_platform.api.dependencies.get_current_user')
    @patch('management_platform.api.dependencies.get_db_session')
    def test_get_all_task_results(self, mock_db, mock_user):
        """测试获取所有任务结果摘要"""
        mock_user.return_value = self.mock_user
        
        # 模拟仓库
        mock_task_repo = Mock()
        mock_task_repo.get_by_user_id.return_value = [self.mock_task]
        
        mock_result_repo = Mock()
        mock_result_repo.get_by_task_id.return_value = [self.mock_result]
        
        with patch('management_platform.api.routes.tasks.TaskRepository', return_value=mock_task_repo), \
             patch('management_platform.api.routes.tasks.TaskResultRepository', return_value=mock_result_repo):
            response = self.client.get("/api/v1/tasks/results")
        
        assert response.status_code == 200
        data = response.json()
        assert len(data) == 1
        result_summary = data[0]
        assert result_summary["task_name"] == "测试任务"
        assert result_summary["status"] == "success"
        assert result_summary["response_time"] == 150.0
    
    @patch('management_platform.api.dependencies.get_current_user')
    @patch('management_platform.api.dependencies.get_db_session')
    def test_admin_can_access_all_tasks(self, mock_db, mock_user):
        """测试管理员可以访问所有任务"""
        mock_user.return_value = self.mock_admin
        
        # 模拟仓库
        mock_task_repo = Mock()
        mock_task_repo.get_all.return_value = [self.mock_task]
        mock_task_repo.count.return_value = 1
        
        with patch('management_platform.api.routes.tasks.TaskRepository', return_value=mock_task_repo):
            response = self.client.get("/api/v1/tasks/")
        
        assert response.status_code == 200
        data = response.json()
        assert data["total"] == 1
        # 验证调用了get_all而不是get_by_user_id
        mock_task_repo.get_all.assert_called_once()
    
    def test_task_validation_errors(self):
        """测试任务验证错误"""
        # 测试缺少必需字段
        response = self.client.post("/api/v1/tasks/", json={
            "name": "测试任务"
            # 缺少protocol和target
        })
        assert response.status_code == 422  # Validation error
        
        # 测试无效的协议类型
        response = self.client.post("/api/v1/tasks/", json={
            "name": "测试任务",
            "protocol": "invalid_protocol",
            "target": "example.com"
        })
        assert response.status_code == 422
        
        # 测试无效的频率
        response = self.client.post("/api/v1/tasks/", json={
            "name": "测试任务",
            "protocol": "http",
            "target": "example.com",
            "frequency": 5  # 小于最小值10
        })
        assert response.status_code == 422
    
    @patch('management_platform.api.dependencies.get_current_user')
    @patch('management_platform.api.dependencies.get_db_session')
    def test_pause_non_active_task_fails(self, mock_db, mock_user):
        """测试暂停非活跃任务失败"""
        mock_user.return_value = self.mock_user
        
        # 已暂停的任务
        paused_task = Mock()
        paused_task.id = self.test_task_id
        paused_task.user_id = self.test_user_id
        paused_task.status = TaskStatus.PAUSED
        
        # 模拟仓库
        mock_task_repo = Mock()
        mock_task_repo.get_by_id.return_value = paused_task
        
        with patch('management_platform.api.routes.tasks.TaskRepository', return_value=mock_task_repo):
            response = self.client.post(f"/api/v1/tasks/{self.test_task_id}/pause")
        
        assert response.status_code == 400
        assert "只能暂停活跃状态" in response.json()["detail"]
    
    @patch('management_platform.api.dependencies.get_current_user')
    @patch('management_platform.api.dependencies.get_db_session')
    def test_resume_insufficient_credits(self, mock_db, mock_user):
        """测试余额不足时恢复任务失败"""
        # 设置用户余额为0
        self.mock_user.credits = 0.0
        mock_user.return_value = self.mock_user
        
        # 暂停状态的任务
        paused_task = Mock()
        paused_task.id = self.test_task_id
        paused_task.user_id = self.test_user_id
        paused_task.status = TaskStatus.PAUSED
        
        # 模拟仓库
        mock_task_repo = Mock()
        mock_task_repo.get_by_id.return_value = paused_task
        
        with patch('management_platform.api.routes.tasks.TaskRepository', return_value=mock_task_repo):
            response = self.client.post(f"/api/v1/tasks/{self.test_task_id}/resume")
        
        assert response.status_code == 400
        assert "余额不足" in response.json()["detail"]


if __name__ == "__main__":
    pytest.main([__file__])