"""任务模型单元测试"""

import pytest
import uuid
from datetime import datetime, timedelta
from sqlalchemy.exc import IntegrityError
from pydantic import ValidationError

from shared.models.task import (
    Task, TaskResult, ProtocolType, TaskStatus, TaskResultStatus,
    TaskCreate, TaskUpdate, TaskResponse, TaskResultCreate, TaskResultResponse,
    TaskBatch, TaskSummary, TaskStatistics, TaskResultSummary
)


class TestProtocolType:
    """协议类型枚举测试"""
    
    def test_protocol_values(self):
        """测试协议类型值"""
        assert ProtocolType.ICMP == "icmp"
        assert ProtocolType.TCP == "tcp"
        assert ProtocolType.UDP == "udp"
        assert ProtocolType.HTTP == "http"
        assert ProtocolType.HTTPS == "https"
    
    def test_protocol_enum_membership(self):
        """测试协议类型枚举成员"""
        protocols = [e.value for e in ProtocolType]
        assert "icmp" in protocols
        assert "tcp" in protocols
        assert "udp" in protocols
        assert "http" in protocols
        assert "https" in protocols


class TestTaskStatus:
    """任务状态枚举测试"""
    
    def test_status_values(self):
        """测试任务状态值"""
        assert TaskStatus.ACTIVE == "active"
        assert TaskStatus.PAUSED == "paused"
        assert TaskStatus.COMPLETED == "completed"
        assert TaskStatus.FAILED == "failed"


class TestTaskResultStatus:
    """任务结果状态枚举测试"""
    
    def test_result_status_values(self):
        """测试任务结果状态值"""
        assert TaskResultStatus.SUCCESS == "success"
        assert TaskResultStatus.TIMEOUT == "timeout"
        assert TaskResultStatus.ERROR == "error"


class TestTask:
    """任务模型测试"""
    
    def test_task_creation(self):
        """测试任务创建"""
        task = Task(
            user_id=uuid.uuid4(),
            name="测试任务",
            description="这是一个测试任务",
            protocol=ProtocolType.HTTP,
            target="example.com",
            port=80,
            frequency=60,
            timeout=30
        )
        
        assert task.name == "测试任务"
        assert task.description == "这是一个测试任务"
        assert task.protocol == ProtocolType.HTTP
        assert task.target == "example.com"
        assert task.port == 80
        assert task.frequency == 60
        assert task.timeout == 30
        assert task.status == TaskStatus.ACTIVE
        assert task.priority == 0
    
    def test_task_validation_frequency(self):
        """测试任务频率验证"""
        task = Task(
            user_id=uuid.uuid4(),
            name="测试任务",
            protocol=ProtocolType.ICMP,
            target="example.com"
        )
        
        # 测试有效频率
        task.frequency = 60
        assert task.frequency == 60
        
        # 测试无效频率 - 太小
        with pytest.raises(ValueError, match="执行频率不能小于10秒"):
            task.frequency = 5
        
        # 测试无效频率 - 太大
        with pytest.raises(ValueError, match="执行频率不能大于24小时"):
            task.frequency = 90000
    
    def test_task_validation_timeout(self):
        """测试任务超时验证"""
        task = Task(
            user_id=uuid.uuid4(),
            name="测试任务",
            protocol=ProtocolType.ICMP,
            target="example.com"
        )
        
        # 测试有效超时
        task.timeout = 30
        assert task.timeout == 30
        
        # 测试无效超时 - 太小
        with pytest.raises(ValueError, match="超时时间不能小于1秒"):
            task.timeout = 0
        
        # 测试无效超时 - 太大
        with pytest.raises(ValueError, match="超时时间不能大于5分钟"):
            task.timeout = 400
    
    def test_task_validation_target(self):
        """测试目标地址验证"""
        task = Task(
            user_id=uuid.uuid4(),
            name="测试任务",
            protocol=ProtocolType.ICMP,
            target="example.com"
        )
        
        # 测试有效目标
        task.target = "example.com"
        assert task.target == "example.com"
        
        # 测试去除空格
        task.target = "  example.com  "
        assert task.target == "example.com"
        
        # 测试空目标
        with pytest.raises(ValueError, match="目标地址不能为空"):
            task.target = ""
        
        with pytest.raises(ValueError, match="目标地址不能为空"):
            task.target = "   "
    
    def test_task_validation_port(self):
        """测试端口验证"""
        task = Task(
            user_id=uuid.uuid4(),
            name="测试任务",
            protocol=ProtocolType.TCP,
            target="example.com"
        )
        
        # 测试有效端口
        task.port = 80
        assert task.port == 80
        
        task.port = 65535
        assert task.port == 65535
        
        # 测试无效端口
        with pytest.raises(ValueError, match="端口号必须在1-65535之间"):
            task.port = 0
        
        with pytest.raises(ValueError, match="端口号必须在1-65535之间"):
            task.port = 70000
    
    def test_is_port_required(self):
        """测试端口是否必需"""
        # TCP需要端口
        task_tcp = Task(protocol=ProtocolType.TCP)
        assert task_tcp.is_port_required() is True
        
        # UDP需要端口
        task_udp = Task(protocol=ProtocolType.UDP)
        assert task_udp.is_port_required() is True
        
        # HTTP需要端口
        task_http = Task(protocol=ProtocolType.HTTP)
        assert task_http.is_port_required() is True
        
        # HTTPS需要端口
        task_https = Task(protocol=ProtocolType.HTTPS)
        assert task_https.is_port_required() is True
        
        # ICMP不需要端口
        task_icmp = Task(protocol=ProtocolType.ICMP)
        assert task_icmp.is_port_required() is False
    
    def test_get_default_port(self):
        """测试获取默认端口"""
        task_http = Task(protocol=ProtocolType.HTTP)
        assert task_http.get_default_port() == 80
        
        task_https = Task(protocol=ProtocolType.HTTPS)
        assert task_https.get_default_port() == 443
        
        task_tcp = Task(protocol=ProtocolType.TCP)
        assert task_tcp.get_default_port() is None
        
        task_icmp = Task(protocol=ProtocolType.ICMP)
        assert task_icmp.get_default_port() is None
    
    def test_validate_configuration(self):
        """测试配置验证"""
        # HTTP任务没有端口，应该自动设置默认端口
        task = Task(
            user_id=uuid.uuid4(),
            name="HTTP测试",
            protocol=ProtocolType.HTTP,
            target="example.com"
        )
        
        result = task.validate_configuration()
        assert result['valid'] is True
        assert task.port == 80
        assert task.parameters['method'] == 'GET'
        
        # TCP任务没有端口，应该报错
        task_tcp = Task(
            user_id=uuid.uuid4(),
            name="TCP测试",
            protocol=ProtocolType.TCP,
            target="example.com"
        )
        
        result = task_tcp.validate_configuration()
        assert result['valid'] is False
        assert "需要指定端口号" in result['errors'][0]
    
    def test_can_execute(self):
        """测试任务是否可执行"""
        task = Task(
            user_id=uuid.uuid4(),
            name="测试任务",
            protocol=ProtocolType.ICMP,
            target="example.com",
            status=TaskStatus.ACTIVE
        )
        
        # 活跃状态且没有下次执行时间
        assert task.can_execute() is True
        
        # 活跃状态且下次执行时间已到
        task.next_run = datetime.utcnow() - timedelta(minutes=1)
        assert task.can_execute() is True
        
        # 活跃状态但下次执行时间未到
        task.next_run = datetime.utcnow() + timedelta(minutes=1)
        assert task.can_execute() is False
        
        # 暂停状态
        task.status = TaskStatus.PAUSED
        task.next_run = None
        assert task.can_execute() is False
    
    def test_update_next_run(self):
        """测试更新下次执行时间"""
        task = Task(
            user_id=uuid.uuid4(),
            name="测试任务",
            protocol=ProtocolType.ICMP,
            target="example.com",
            frequency=60,
            status=TaskStatus.ACTIVE
        )
        
        before_update = datetime.utcnow().replace(microsecond=0)
        task.update_next_run()
        after_update = datetime.utcnow().replace(microsecond=0)
        
        assert task.next_run is not None
        # Allow for some timing tolerance
        expected_min = before_update + timedelta(seconds=60)
        expected_max = after_update + timedelta(seconds=60)
        assert task.next_run >= expected_min
        assert task.next_run <= expected_max
    
    def test_pause_resume(self):
        """测试暂停和恢复任务"""
        task = Task(
            user_id=uuid.uuid4(),
            name="测试任务",
            protocol=ProtocolType.ICMP,
            target="example.com",
            frequency=60,  # 添加频率
            status=TaskStatus.ACTIVE,
            next_run=datetime.utcnow() + timedelta(minutes=1)
        )
        
        # 暂停任务
        task.pause()
        assert task.status == TaskStatus.PAUSED
        assert task.next_run is None
        
        # 恢复任务
        task.resume()
        assert task.status == TaskStatus.ACTIVE
        assert task.next_run is not None
    
    def test_complete_fail(self):
        """测试完成和失败任务"""
        task = Task(
            user_id=uuid.uuid4(),
            name="测试任务",
            protocol=ProtocolType.ICMP,
            target="example.com",
            status=TaskStatus.ACTIVE,
            next_run=datetime.utcnow() + timedelta(minutes=1)
        )
        
        # 完成任务
        task.complete()
        assert task.status == TaskStatus.COMPLETED
        assert task.next_run is None
        
        # 重置状态
        task.status = TaskStatus.ACTIVE
        task.next_run = datetime.utcnow() + timedelta(minutes=1)
        
        # 失败任务
        task.fail()
        assert task.status == TaskStatus.FAILED
        assert task.next_run is None


class TestTaskResult:
    """任务结果模型测试"""
    
    def test_task_result_creation(self):
        """测试任务结果创建"""
        result = TaskResult(
            task_id=uuid.uuid4(),
            agent_id=uuid.uuid4(),
            execution_time=datetime.utcnow(),
            duration=150.5,
            status=TaskResultStatus.SUCCESS,
            metrics={"response_time": 150.5, "status_code": 200},
            raw_data={"headers": {"content-type": "text/html"}}
        )
        
        assert result.duration == 150.5
        assert result.status == TaskResultStatus.SUCCESS
        assert result.metrics["response_time"] == 150.5
        assert result.raw_data["headers"]["content-type"] == "text/html"
    
    def test_duration_validation(self):
        """测试执行时间验证"""
        result = TaskResult(
            task_id=uuid.uuid4(),
            agent_id=uuid.uuid4(),
            execution_time=datetime.utcnow(),
            status=TaskResultStatus.SUCCESS
        )
        
        # 测试有效时间
        result.duration = 100.0
        assert result.duration == 100.0
        
        # 测试负数时间
        with pytest.raises(ValueError, match="执行时间不能为负数"):
            result.duration = -10.0
    
    def test_is_successful(self):
        """测试结果是否成功"""
        result_success = TaskResult(status=TaskResultStatus.SUCCESS)
        assert result_success.is_successful() is True
        
        result_timeout = TaskResult(status=TaskResultStatus.TIMEOUT)
        assert result_timeout.is_successful() is False
        
        result_error = TaskResult(status=TaskResultStatus.ERROR)
        assert result_error.is_successful() is False
    
    def test_get_response_time(self):
        """测试获取响应时间"""
        # 从metrics获取
        result = TaskResult(
            duration=100.0,
            metrics={"response_time": 150.5}
        )
        assert result.get_response_time() == 150.5
        
        # 从duration获取
        result_no_metrics = TaskResult(duration=100.0)
        assert result_no_metrics.get_response_time() == 100.0
        
        # 都没有
        result_none = TaskResult()
        assert result_none.get_response_time() is None
    
    def test_get_error_summary(self):
        """测试获取错误摘要"""
        # 成功结果
        result_success = TaskResult(status=TaskResultStatus.SUCCESS)
        assert result_success.get_error_summary() == "成功"
        
        # 超时结果
        result_timeout = TaskResult(status=TaskResultStatus.TIMEOUT)
        assert result_timeout.get_error_summary() == "超时"
        
        # 有错误信息
        result_error = TaskResult(
            status=TaskResultStatus.ERROR,
            error_message="连接被拒绝"
        )
        assert result_error.get_error_summary() == "连接被拒绝"
        
        # 长错误信息截断
        long_error = "这是一个非常长的错误信息" * 10
        result_long_error = TaskResult(
            status=TaskResultStatus.ERROR,
            error_message=long_error
        )
        summary = result_long_error.get_error_summary()
        assert len(summary) <= 103  # 100 + "..."
        assert summary.endswith("...")
        
        # 无错误信息
        result_no_error = TaskResult(status=TaskResultStatus.ERROR)
        assert result_no_error.get_error_summary() == "未知错误"


class TestTaskCreate:
    """任务创建模式测试"""
    
    def test_valid_task_create(self):
        """测试有效的任务创建"""
        task_data = {
            "name": "测试任务",
            "description": "这是一个测试任务",
            "protocol": ProtocolType.HTTP,
            "target": "example.com",
            "port": 80,
            "frequency": 60,
            "timeout": 30
        }
        
        task_create = TaskCreate(**task_data)
        assert task_create.name == "测试任务"
        assert task_create.protocol == ProtocolType.HTTP
        assert task_create.target == "example.com"
        assert task_create.port == 80
    
    def test_invalid_task_create(self):
        """测试无效的任务创建"""
        # 空名称
        with pytest.raises(ValidationError):
            TaskCreate(
                name="",
                protocol=ProtocolType.HTTP,
                target="example.com"
            )
        
        # 无效端口
        with pytest.raises(ValidationError):
            TaskCreate(
                name="测试任务",
                protocol=ProtocolType.HTTP,
                target="example.com",
                port=70000
            )
        
        # 无效频率
        with pytest.raises(ValidationError):
            TaskCreate(
                name="测试任务",
                protocol=ProtocolType.HTTP,
                target="example.com",
                frequency=5
            )
    
    def test_target_validation(self):
        """测试目标地址验证"""
        # 空目标 - Pydantic会先检查字符串长度
        with pytest.raises(ValidationError):
            TaskCreate(
                name="测试任务",
                protocol=ProtocolType.HTTP,
                target=""
            )
        
        # 空格目标 - 这个会触发我们的自定义验证
        with pytest.raises(ValidationError, match="目标地址不能为空"):
            TaskCreate(
                name="测试任务",
                protocol=ProtocolType.HTTP,
                target="   "
            )


class TestTaskUpdate:
    """任务更新模式测试"""
    
    def test_valid_task_update(self):
        """测试有效的任务更新"""
        task_update = TaskUpdate(
            name="更新的任务名称",
            frequency=120
        )
        
        assert task_update.name == "更新的任务名称"
        assert task_update.frequency == 120
    
    def test_partial_update(self):
        """测试部分更新"""
        task_update = TaskUpdate(name="新名称")
        
        assert task_update.name == "新名称"
        assert task_update.frequency is None
        assert task_update.protocol is None


class TestTaskResultCreate:
    """任务结果创建模式测试"""
    
    def test_valid_result_create(self):
        """测试有效的结果创建"""
        result_data = {
            "task_id": uuid.uuid4(),
            "agent_id": uuid.uuid4(),
            "execution_time": datetime.utcnow(),
            "duration": 150.5,
            "status": TaskResultStatus.SUCCESS,
            "metrics": {"response_time": 150.5}
        }
        
        result_create = TaskResultCreate(**result_data)
        assert result_create.duration == 150.5
        assert result_create.status == TaskResultStatus.SUCCESS
    
    def test_invalid_result_create(self):
        """测试无效的结果创建"""
        # 负数执行时间
        with pytest.raises(ValidationError):
            TaskResultCreate(
                task_id=uuid.uuid4(),
                agent_id=uuid.uuid4(),
                execution_time=datetime.utcnow(),
                duration=-10.0,
                status=TaskResultStatus.SUCCESS
            )


class TestTaskEnhancements:
    """任务增强功能测试"""
    
    def test_get_execution_cost(self):
        """测试获取执行成本"""
        # ICMP任务，1分钟频率
        task_icmp = Task(protocol=ProtocolType.ICMP, frequency=60)
        assert task_icmp.get_execution_cost() == 0.1
        
        # HTTP任务，30秒频率（高频）
        task_http = Task(protocol=ProtocolType.HTTP, frequency=30)
        assert task_http.get_execution_cost() == 0.3
        
        # HTTPS任务，10分钟频率 (600秒 > 300秒，所以是0.6倍)
        task_https = Task(protocol=ProtocolType.HTTPS, frequency=600)
        assert abs(task_https.get_execution_cost() - (0.3 * 0.6)) < 0.001  # 频率调整
        
        # TCP任务，2小时频率
        task_tcp = Task(protocol=ProtocolType.TCP, frequency=7200)
        assert abs(task_tcp.get_execution_cost() - (0.2 * 0.4)) < 0.001  # 低频调整
    
    def test_get_estimated_daily_cost(self):
        """测试获取预估日成本"""
        # 每分钟执行一次的ICMP任务
        task = Task(protocol=ProtocolType.ICMP, frequency=60)
        daily_executions = 86400 / 60  # 1440次
        expected_cost = 0.1 * daily_executions
        assert task.get_estimated_daily_cost() == expected_cost
        
        # 没有频率的任务
        task_no_freq = Task(protocol=ProtocolType.ICMP)
        assert task_no_freq.get_estimated_daily_cost() == 0.0
    
    def test_is_high_frequency(self):
        """测试是否为高频任务"""
        task_high = Task(frequency=30)
        assert task_high.is_high_frequency() is True
        
        task_normal = Task(frequency=60)
        assert task_normal.is_high_frequency() is False
        
        task_low = Task(frequency=300)
        assert task_low.is_high_frequency() is False
        
        task_no_freq = Task()
        assert task_no_freq.is_high_frequency() is False
    
    def test_get_protocol_display_name(self):
        """测试获取协议显示名称"""
        task_icmp = Task(protocol=ProtocolType.ICMP)
        assert task_icmp.get_protocol_display_name() == "ICMP (Ping)"
        
        task_http = Task(protocol=ProtocolType.HTTP)
        assert task_http.get_protocol_display_name() == "HTTP网页测试"
        
        task_https = Task(protocol=ProtocolType.HTTPS)
        assert task_https.get_protocol_display_name() == "HTTPS安全网页测试"
        
        task_tcp = Task(protocol=ProtocolType.TCP)
        assert task_tcp.get_protocol_display_name() == "TCP连接测试"
        
        task_udp = Task(protocol=ProtocolType.UDP)
        assert task_udp.get_protocol_display_name() == "UDP数据包测试"
    
    def test_validate_protocol_parameters(self):
        """测试协议参数验证"""
        # HTTP任务参数验证
        task_http = Task(
            protocol=ProtocolType.HTTP,
            target="example.com",
            parameters={"method": "get", "headers": {"User-Agent": "test"}}
        )
        result = task_http.validate_protocol_parameters()
        assert result['valid'] is True
        assert task_http.parameters['method'] == 'GET'  # 应该被转换为大写
        
        # 无效HTTP方法
        task_invalid_method = Task(
            protocol=ProtocolType.HTTP,
            target="example.com",
            parameters={"method": "INVALID"}
        )
        result = task_invalid_method.validate_protocol_parameters()
        assert result['valid'] is False
        assert "无效的HTTP方法" in result['errors'][0]
        
        # ICMP任务有端口号警告
        task_icmp = Task(
            protocol=ProtocolType.ICMP,
            target="example.com",
            port=80
        )
        result = task_icmp.validate_protocol_parameters()
        assert result['valid'] is True
        assert len(result['warnings']) > 0
        assert "不需要端口号" in result['warnings'][0]
        
        # TCP任务没有端口号
        task_tcp = Task(
            protocol=ProtocolType.TCP,
            target="example.com"
        )
        result = task_tcp.validate_protocol_parameters()
        assert result['valid'] is False
        assert "必须指定端口号" in result['errors'][0]
    
    def test_get_target_info(self):
        """测试获取目标信息"""
        # IP地址目标
        task_ip = Task(
            protocol=ProtocolType.ICMP,
            target="192.168.1.1"
        )
        info = task_ip.get_target_info()
        assert info['is_ip_address'] is True
        assert info['is_domain'] is False
        assert info['target'] == "192.168.1.1"
        
        # 域名目标
        task_domain = Task(
            protocol=ProtocolType.HTTP,
            target="example.com",
            port=80
        )
        info = task_domain.get_target_info()
        assert info['is_ip_address'] is False
        assert info['is_domain'] is True
        assert info['full_url'] == "http://example.com"
        
        # HTTPS带自定义端口
        task_https = Task(
            protocol=ProtocolType.HTTPS,
            target="example.com",
            port=8443
        )
        info = task_https.get_target_info()
        assert info['full_url'] == "https://example.com:8443"
    
    def test_should_execute_now(self):
        """测试是否应该立即执行"""
        # 活跃状态，无下次执行时间
        task = Task(status=TaskStatus.ACTIVE)
        assert task.should_execute_now() is True
        
        # 活跃状态，下次执行时间已到
        task.next_run = datetime.utcnow() - timedelta(minutes=1)
        assert task.should_execute_now() is True
        
        # 活跃状态，下次执行时间未到
        task.next_run = datetime.utcnow() + timedelta(minutes=1)
        assert task.should_execute_now() is False
        
        # 非活跃状态
        task.status = TaskStatus.PAUSED
        assert task.should_execute_now() is False
    
    def test_get_next_execution_delay(self):
        """测试获取下次执行延迟"""
        task = Task(status=TaskStatus.ACTIVE)
        
        # 无下次执行时间
        assert task.get_next_execution_delay() is None
        
        # 下次执行时间已到
        task.next_run = datetime.utcnow() - timedelta(seconds=10)
        assert task.get_next_execution_delay() == 0
        
        # 下次执行时间未到
        task.next_run = datetime.utcnow() + timedelta(seconds=30)
        delay = task.get_next_execution_delay()
        assert delay is not None
        assert 25 <= delay <= 35  # 允许一些时间误差
        
        # 非活跃状态
        task.status = TaskStatus.PAUSED
        assert task.get_next_execution_delay() is None
    
    def test_reset_execution_schedule(self):
        """测试重置执行计划"""
        task = Task(
            status=TaskStatus.ACTIVE,
            next_run=datetime.utcnow() + timedelta(hours=1)
        )
        
        old_next_run = task.next_run
        task.reset_execution_schedule()
        
        assert task.next_run != old_next_run
        assert task.next_run <= datetime.utcnow()
    
    def test_get_comprehensive_validation(self):
        """测试全面验证"""
        # 有效的HTTP任务
        task = Task(
            protocol=ProtocolType.HTTP,
            target="example.com",
            port=80,
            frequency=60,
            timeout=30,
            parameters={"method": "GET"}
        )
        
        result = task.get_comprehensive_validation()
        assert result['valid'] is True
        assert result['config_valid'] is True
        assert result['protocol_valid'] is True
        
        # 无效的任务（缺少端口）
        task_invalid = Task(
            protocol=ProtocolType.TCP,
            target="example.com",
            frequency=60,
            timeout=30
        )
        
        result = task_invalid.get_comprehensive_validation()
        assert result['valid'] is False
        assert len(result['errors']) > 0


class TestTaskResultEnhancements:
    """任务结果增强功能测试"""
    
    def test_get_availability_score(self):
        """测试获取可用性评分"""
        result_success = TaskResult(status=TaskResultStatus.SUCCESS)
        assert result_success.get_availability_score() == 1.0
        
        result_timeout = TaskResult(status=TaskResultStatus.TIMEOUT)
        assert result_timeout.get_availability_score() == 0.5
        
        result_error = TaskResult(status=TaskResultStatus.ERROR)
        assert result_error.get_availability_score() == 0.0
    
    def test_get_performance_grade(self):
        """测试获取性能等级"""
        # 成功且快速响应
        result_excellent = TaskResult(
            status=TaskResultStatus.SUCCESS,
            duration=30.0
        )
        assert result_excellent.get_performance_grade() == "优秀"
        
        # 成功但响应较慢
        result_poor = TaskResult(
            status=TaskResultStatus.SUCCESS,
            duration=600.0
        )
        assert result_poor.get_performance_grade() == "很差"
        
        # 失败的结果
        result_failed = TaskResult(status=TaskResultStatus.ERROR)
        assert result_failed.get_performance_grade() == "N/A"
        
        # 从metrics获取响应时间
        result_with_metrics = TaskResult(
            status=TaskResultStatus.SUCCESS,
            metrics={"response_time": 80.0}
        )
        assert result_with_metrics.get_performance_grade() == "良好"
    
    def test_extract_key_metrics(self):
        """测试提取关键指标"""
        result = TaskResult(
            status=TaskResultStatus.SUCCESS,
            duration=120.0,
            execution_time=datetime.utcnow(),
            metrics={
                "response_time": 120.0,
                "status_code": 200,
                "packet_loss": 0.0,
                "jitter": 5.2
            }
        )
        
        metrics = result.extract_key_metrics()
        
        assert metrics["success"] is True
        assert metrics["response_time"] == 120.0
        assert metrics["availability_score"] == 1.0
        assert metrics["performance_grade"] == "一般"
        assert metrics["http_status"] == 200
        assert metrics["packet_loss"] == 0.0
        assert metrics["jitter"] == 5.2
        assert "execution_time" in metrics
    
    def test_is_timeout_error(self):
        """测试是否为超时错误"""
        result_timeout = TaskResult(status=TaskResultStatus.TIMEOUT)
        assert result_timeout.is_timeout_error() is True
        
        result_success = TaskResult(status=TaskResultStatus.SUCCESS)
        assert result_success.is_timeout_error() is False
        
        result_error = TaskResult(status=TaskResultStatus.ERROR)
        assert result_error.is_timeout_error() is False
    
    def test_is_network_error(self):
        """测试是否为网络错误"""
        # 网络连接被拒绝
        result_refused = TaskResult(
            status=TaskResultStatus.ERROR,
            error_message="Connection refused by target host"
        )
        assert result_refused.is_network_error() is True
        
        # DNS解析失败
        result_dns = TaskResult(
            status=TaskResultStatus.ERROR,
            error_message="DNS resolution failed for example.com"
        )
        assert result_dns.is_network_error() is True
        
        # 非网络错误
        result_other = TaskResult(
            status=TaskResultStatus.ERROR,
            error_message="Invalid response format"
        )
        assert result_other.is_network_error() is False
        
        # 成功结果
        result_success = TaskResult(status=TaskResultStatus.SUCCESS)
        assert result_success.is_network_error() is False
    
    def test_get_failure_category(self):
        """测试获取失败类别"""
        result_success = TaskResult(status=TaskResultStatus.SUCCESS)
        assert result_success.get_failure_category() == "success"
        
        result_timeout = TaskResult(status=TaskResultStatus.TIMEOUT)
        assert result_timeout.get_failure_category() == "timeout"
        
        result_network = TaskResult(
            status=TaskResultStatus.ERROR,
            error_message="Connection timeout"
        )
        assert result_network.get_failure_category() == "network_error"
        
        result_other = TaskResult(
            status=TaskResultStatus.ERROR,
            error_message="Invalid data format"
        )
        assert result_other.get_failure_category() == "other_error"
    
    def test_to_summary_dict(self):
        """测试转换为摘要字典"""
        result = TaskResult(
            task_id=uuid.uuid4(),
            agent_id=uuid.uuid4(),
            execution_time=datetime.utcnow(),
            status=TaskResultStatus.SUCCESS,
            duration=120.0,
            metrics={"response_time": 120.0}
        )
        
        summary = result.to_summary_dict()
        
        assert summary['status'] == 'success'
        assert summary['success'] is True
        assert summary['response_time'] == 120.0
        assert summary['performance_grade'] == "一般"
        assert summary['availability_score'] == 1.0
        assert summary['failure_category'] == "success"
        assert summary['error_summary'] == "成功"


class TestTaskBatch:
    """批量任务操作测试"""
    
    def test_valid_task_batch(self):
        """测试有效的批量操作"""
        task_ids = [uuid.uuid4(), uuid.uuid4(), uuid.uuid4()]
        batch = TaskBatch(task_ids=task_ids, action="pause")
        
        assert len(batch.task_ids) == 3
        assert batch.action == "pause"
    
    def test_invalid_task_batch_action(self):
        """测试无效的批量操作动作"""
        task_ids = [uuid.uuid4()]
        
        with pytest.raises(ValidationError, match="操作类型必须是"):
            TaskBatch(task_ids=task_ids, action="invalid_action")
    
    def test_empty_task_ids(self):
        """测试空任务ID列表"""
        with pytest.raises(ValidationError):
            TaskBatch(task_ids=[], action="pause")