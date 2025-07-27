"""任务相关数据模型"""

import uuid
from datetime import datetime, timedelta
from typing import Any, Dict, Optional
from enum import Enum

from sqlalchemy import (
    Column, String, Integer, Float, DateTime, Text, JSON,
    ForeignKey, Enum as SQLEnum
)
from sqlalchemy.orm import relationship, validates
from pydantic import BaseModel, Field, field_validator

from .base import BaseModel as DBBaseModel, BaseSchema, GUID


class ProtocolType(str, Enum):
    """协议类型枚举"""
    ICMP = "icmp"
    TCP = "tcp"
    UDP = "udp"
    HTTP = "http"
    HTTPS = "https"


class TaskStatus(str, Enum):
    """任务状态枚举"""
    ACTIVE = "active"
    PAUSED = "paused"
    COMPLETED = "completed"
    FAILED = "failed"


class TaskResultStatus(str, Enum):
    """任务结果状态枚举"""
    SUCCESS = "success"
    TIMEOUT = "timeout"
    ERROR = "error"


class Task(DBBaseModel):
    """拨测任务模型"""
    
    __tablename__ = "tasks"
    
    # 基本信息
    user_id = Column(GUID(), ForeignKey("users.id"), nullable=False, index=True)
    name = Column(String(255), nullable=False)
    description = Column(Text)
    
    # 协议配置
    protocol = Column(SQLEnum(ProtocolType), nullable=False)
    target = Column(String(255), nullable=False)  # 目标地址
    port = Column(Integer)  # 适用于TCP/UDP/HTTP
    parameters = Column(JSON)  # 协议特定参数
    
    # 执行配置
    frequency = Column(Integer, nullable=False, default=60)  # 执行频率(秒)
    timeout = Column(Integer, nullable=False, default=30)  # 超时时间(秒)
    priority = Column(Integer, default=0)  # 优先级
    
    # 状态管理
    status = Column(SQLEnum(TaskStatus), nullable=False, default=TaskStatus.ACTIVE)
    next_run = Column(DateTime(timezone=True))
    
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        if self.status is None:
            self.status = TaskStatus.ACTIVE
        if self.priority is None:
            self.priority = 0
    
    # 代理选择偏好
    preferred_location = Column(String(100))  # 首选地理位置
    preferred_isp = Column(String(100))  # 首选运营商
    
    # 关系
    results = relationship("TaskResult", back_populates="task", cascade="all, delete-orphan")
    
    @validates('frequency')
    def validate_frequency(self, key, frequency):
        """验证执行频率"""
        if frequency < 10:
            raise ValueError("执行频率不能小于10秒")
        if frequency > 86400:  # 24小时
            raise ValueError("执行频率不能大于24小时")
        return frequency
    
    @validates('timeout')
    def validate_timeout(self, key, timeout):
        """验证超时时间"""
        if timeout < 1:
            raise ValueError("超时时间不能小于1秒")
        if timeout > 300:  # 5分钟
            raise ValueError("超时时间不能大于5分钟")
        return timeout
    
    @validates('target')
    def validate_target(self, key, target):
        """验证目标地址"""
        if not target or not target.strip():
            raise ValueError("目标地址不能为空")
        return target.strip()
    
    @validates('port')
    def validate_port(self, key, port):
        """验证端口号"""
        if port is not None:
            if port < 1 or port > 65535:
                raise ValueError("端口号必须在1-65535之间")
        return port
    
    def is_port_required(self) -> bool:
        """检查当前协议是否需要端口号"""
        return self.protocol in [ProtocolType.TCP, ProtocolType.UDP, ProtocolType.HTTP, ProtocolType.HTTPS]
    
    def get_default_port(self) -> Optional[int]:
        """获取协议默认端口"""
        default_ports = {
            ProtocolType.HTTP: 80,
            ProtocolType.HTTPS: 443,
        }
        return default_ports.get(self.protocol)
    
    def validate_configuration(self) -> Dict[str, Any]:
        """验证任务配置的完整性"""
        errors = []
        
        # 检查端口配置
        if self.is_port_required() and not self.port:
            default_port = self.get_default_port()
            if default_port:
                self.port = default_port
            else:
                errors.append(f"协议 {self.protocol.value} 需要指定端口号")
        
        # 检查协议特定参数
        if self.protocol in [ProtocolType.HTTP, ProtocolType.HTTPS]:
            if not self.parameters:
                self.parameters = {}
            if 'method' not in self.parameters:
                self.parameters['method'] = 'GET'
        
        return {
            'valid': len(errors) == 0,
            'errors': errors
        }
    
    def can_execute(self) -> bool:
        """检查任务是否可以执行"""
        return (
            self.status == TaskStatus.ACTIVE and
            (self.next_run is None or self.next_run <= datetime.utcnow())
        )
    
    def update_next_run(self):
        """更新下次执行时间"""
        if self.status == TaskStatus.ACTIVE and self.frequency:
            self.next_run = datetime.utcnow().replace(microsecond=0) + \
                           timedelta(seconds=self.frequency)
    
    def pause(self):
        """暂停任务"""
        self.status = TaskStatus.PAUSED
        self.next_run = None
    
    def resume(self):
        """恢复任务"""
        if self.status == TaskStatus.PAUSED:
            self.status = TaskStatus.ACTIVE
            self.update_next_run()
    
    def complete(self):
        """完成任务"""
        self.status = TaskStatus.COMPLETED
        self.next_run = None
    
    def fail(self):
        """标记任务失败"""
        self.status = TaskStatus.FAILED
        self.next_run = None
    
    def get_execution_cost(self) -> float:
        """计算任务执行成本（点数）"""
        # 基础成本根据协议类型
        base_costs = {
            ProtocolType.ICMP: 0.1,
            ProtocolType.TCP: 0.2,
            ProtocolType.UDP: 0.2,
            ProtocolType.HTTP: 0.3,
            ProtocolType.HTTPS: 0.3,
        }
        
        base_cost = base_costs.get(self.protocol, 0.1)
        
        # 频率调整：频率越高，单次成本越低
        if self.frequency <= 60:  # 1分钟以内
            frequency_multiplier = 1.0
        elif self.frequency <= 300:  # 5分钟以内
            frequency_multiplier = 0.8
        elif self.frequency <= 3600:  # 1小时以内
            frequency_multiplier = 0.6
        else:  # 超过1小时
            frequency_multiplier = 0.4
        
        return base_cost * frequency_multiplier
    
    def get_estimated_daily_cost(self) -> float:
        """计算预估日成本"""
        if not self.frequency:
            return 0.0
        
        executions_per_day = 86400 / self.frequency  # 24小时 * 3600秒
        return self.get_execution_cost() * executions_per_day
    
    def is_high_frequency(self) -> bool:
        """检查是否为高频任务"""
        return bool(self.frequency and self.frequency < 60)
    
    def get_protocol_display_name(self) -> str:
        """获取协议显示名称"""
        display_names = {
            ProtocolType.ICMP: "ICMP (Ping)",
            ProtocolType.TCP: "TCP连接测试",
            ProtocolType.UDP: "UDP数据包测试",
            ProtocolType.HTTP: "HTTP网页测试",
            ProtocolType.HTTPS: "HTTPS安全网页测试",
        }
        return display_names.get(self.protocol, str(self.protocol.value).upper())
    
    def validate_protocol_parameters(self) -> Dict[str, Any]:
        """验证协议特定参数"""
        errors = []
        warnings = []
        
        if self.protocol in [ProtocolType.HTTP, ProtocolType.HTTPS]:
            # HTTP/HTTPS特定验证
            if not self.parameters:
                self.parameters = {}
            
            # 验证HTTP方法
            method = self.parameters.get('method', 'GET')
            valid_methods = ['GET', 'POST', 'PUT', 'DELETE', 'HEAD', 'OPTIONS']
            if method.upper() not in valid_methods:
                errors.append(f"无效的HTTP方法: {method}")
            else:
                self.parameters['method'] = method.upper()
            
            # 验证超时设置
            if self.timeout and self.timeout > 60:
                warnings.append("HTTP/HTTPS任务超时时间建议不超过60秒")
            
            # 验证请求头
            headers = self.parameters.get('headers', {})
            if not isinstance(headers, dict):
                errors.append("请求头必须是字典格式")
            
        elif self.protocol == ProtocolType.ICMP:
            # ICMP特定验证
            if self.port:
                warnings.append("ICMP协议不需要端口号，将被忽略")
            
            # 验证ICMP参数
            if self.parameters:
                packet_count = self.parameters.get('count', 4)
                if not isinstance(packet_count, int) or packet_count < 1 or packet_count > 100:
                    errors.append("ICMP包数量必须在1-100之间")
                
                packet_size = self.parameters.get('size', 64)
                if not isinstance(packet_size, int) or packet_size < 8 or packet_size > 65507:
                    errors.append("ICMP包大小必须在8-65507字节之间")
        
        elif self.protocol in [ProtocolType.TCP, ProtocolType.UDP]:
            # TCP/UDP特定验证
            if not self.port:
                errors.append(f"{self.protocol.value.upper()}协议必须指定端口号")
            
            if self.parameters:
                # 验证连接超时
                connect_timeout = self.parameters.get('connect_timeout')
                if connect_timeout and (not isinstance(connect_timeout, (int, float)) or connect_timeout <= 0):
                    errors.append("连接超时时间必须是正数")
        
        return {
            'valid': len(errors) == 0,
            'errors': errors,
            'warnings': warnings
        }
    
    def get_target_info(self) -> Dict[str, Any]:
        """获取目标信息"""
        import re
        
        # 检查是否为IP地址
        ip_pattern = r'^(\d{1,3}\.){3}\d{1,3}$'
        is_ip = bool(re.match(ip_pattern, self.target))
        
        # 检查是否为域名（不是IP地址且符合域名格式）
        domain_pattern = r'^[a-zA-Z0-9]([a-zA-Z0-9\-]{0,61}[a-zA-Z0-9])?(\.[a-zA-Z0-9]([a-zA-Z0-9\-]{0,61}[a-zA-Z0-9])?)*$'
        is_domain = bool(not is_ip and re.match(domain_pattern, self.target))
        
        # 构建完整URL（对于HTTP/HTTPS）
        full_url = None
        if self.protocol in [ProtocolType.HTTP, ProtocolType.HTTPS]:
            scheme = self.protocol.value
            port_part = f":{self.port}" if self.port and self.port != self.get_default_port() else ""
            full_url = f"{scheme}://{self.target}{port_part}"
        
        return {
            'target': self.target,
            'is_ip_address': is_ip,
            'is_domain': is_domain,
            'port': self.port,
            'full_url': full_url,
            'protocol': self.protocol.value
        }
    
    def should_execute_now(self) -> bool:
        """检查任务是否应该立即执行"""
        if self.status != TaskStatus.ACTIVE:
            return False
        
        if not self.next_run:
            return True
        
        return self.next_run <= datetime.utcnow()
    
    def get_next_execution_delay(self) -> Optional[int]:
        """获取距离下次执行的秒数"""
        if not self.next_run or self.status != TaskStatus.ACTIVE:
            return None
        
        now = datetime.utcnow()
        if self.next_run <= now:
            return 0
        
        return int((self.next_run - now).total_seconds())
    
    def reset_execution_schedule(self):
        """重置执行计划"""
        if self.status == TaskStatus.ACTIVE:
            self.next_run = datetime.utcnow().replace(microsecond=0)
    
    def get_comprehensive_validation(self) -> Dict[str, Any]:
        """获取全面的任务验证结果"""
        config_validation = self.validate_configuration()
        protocol_validation = self.validate_protocol_parameters()
        
        all_errors = config_validation.get('errors', []) + protocol_validation.get('errors', [])
        all_warnings = protocol_validation.get('warnings', [])
        
        return {
            'valid': len(all_errors) == 0,
            'errors': all_errors,
            'warnings': all_warnings,
            'config_valid': config_validation['valid'],
            'protocol_valid': protocol_validation['valid']
        }


class TaskResult(DBBaseModel):
    """任务结果模型"""
    
    __tablename__ = "task_results"
    
    # 关联信息
    task_id = Column(GUID(), ForeignKey("tasks.id"), nullable=False, index=True)
    agent_id = Column(GUID(), ForeignKey("agents.id"), nullable=False, index=True)
    
    # 执行信息
    execution_time = Column(DateTime(timezone=True), nullable=False, index=True)
    duration = Column(Float)  # 执行时间(毫秒)
    status = Column(SQLEnum(TaskResultStatus), nullable=False)
    error_message = Column(Text)
    
    # 结果数据
    metrics = Column(JSON)  # 协议特定指标
    raw_data = Column(JSON)  # 原始响应数据
    
    # 关系
    task = relationship("Task", back_populates="results")
    agent = relationship("Agent", back_populates="task_results")
    
    @validates('duration')
    def validate_duration(self, key, duration):
        """验证执行时间"""
        if duration is not None and duration < 0:
            raise ValueError("执行时间不能为负数")
        return duration
    
    def is_successful(self) -> bool:
        """检查结果是否成功"""
        return self.status == TaskResultStatus.SUCCESS
    
    def get_response_time(self) -> Optional[float]:
        """获取响应时间(毫秒)"""
        if self.metrics and 'response_time' in self.metrics:
            return self.metrics['response_time']
        return self.duration
    
    def get_error_summary(self) -> str:
        """获取错误摘要"""
        if self.status == TaskResultStatus.SUCCESS:
            return "成功"
        elif self.status == TaskResultStatus.TIMEOUT:
            return "超时"
        elif self.error_message:
            return self.error_message[:100] + "..." if len(self.error_message) > 100 else self.error_message
        else:
            return "未知错误"
    
    def get_availability_score(self) -> float:
        """获取可用性评分 (0-1)"""
        if self.status == TaskResultStatus.SUCCESS:
            return 1.0
        elif self.status == TaskResultStatus.TIMEOUT:
            return 0.5  # 部分可用
        else:
            return 0.0  # 不可用
    
    def get_performance_grade(self) -> str:
        """获取性能等级"""
        response_time = self.get_response_time()
        if not response_time or not self.is_successful():
            return "N/A"
        
        if response_time < 50:
            return "优秀"
        elif response_time < 100:
            return "良好"
        elif response_time < 200:
            return "一般"
        elif response_time < 500:
            return "较差"
        else:
            return "很差"
    
    def extract_key_metrics(self) -> Dict[str, Any]:
        """提取关键指标"""
        key_metrics = {
            "success": self.is_successful(),
            "response_time": self.get_response_time(),
            "availability_score": self.get_availability_score(),
            "performance_grade": self.get_performance_grade(),
            "execution_time": self.execution_time.isoformat() if self.execution_time else None,
        }
        
        # 添加协议特定指标
        if self.metrics:
            if "status_code" in self.metrics:
                key_metrics["http_status"] = self.metrics["status_code"]
            if "packet_loss" in self.metrics:
                key_metrics["packet_loss"] = self.metrics["packet_loss"]
            if "jitter" in self.metrics:
                key_metrics["jitter"] = self.metrics["jitter"]
        
        return key_metrics
    
    def is_timeout_error(self) -> bool:
        """检查是否为超时错误"""
        return self.status == TaskResultStatus.TIMEOUT
    
    def is_network_error(self) -> bool:
        """检查是否为网络错误"""
        if self.status != TaskResultStatus.ERROR:
            return False
        
        if not self.error_message:
            return False
        
        network_error_keywords = [
            'connection refused', 'connection timeout', 'network unreachable',
            'host unreachable', 'dns resolution failed', 'connection reset',
            'no route to host', 'network is down'
        ]
        
        error_lower = self.error_message.lower()
        return any(keyword in error_lower for keyword in network_error_keywords)
    
    def get_failure_category(self) -> str:
        """获取失败类别"""
        if self.is_successful():
            return "success"
        elif self.is_timeout_error():
            return "timeout"
        elif self.is_network_error():
            return "network_error"
        else:
            return "other_error"
    
    def to_summary_dict(self) -> Dict[str, Any]:
        """转换为摘要字典"""
        return {
            'id': str(self.id) if hasattr(self, 'id') else None,
            'task_id': str(self.task_id),
            'agent_id': str(self.agent_id),
            'execution_time': self.execution_time.isoformat() if self.execution_time else None,
            'status': self.status.value,
            'success': self.is_successful(),
            'response_time': self.get_response_time(),
            'performance_grade': self.get_performance_grade(),
            'availability_score': self.get_availability_score(),
            'failure_category': self.get_failure_category(),
            'error_summary': self.get_error_summary()
        }


# Pydantic 模式定义

class TaskCreate(BaseModel):
    """创建任务的请求模式"""
    name: str = Field(..., min_length=1, max_length=255, description="任务名称")
    description: Optional[str] = Field(None, description="任务描述")
    protocol: ProtocolType = Field(..., description="协议类型")
    target: str = Field(..., min_length=1, max_length=255, description="目标地址")
    port: Optional[int] = Field(None, ge=1, le=65535, description="端口号")
    parameters: Optional[Dict[str, Any]] = Field(None, description="协议特定参数")
    frequency: int = Field(60, ge=10, le=86400, description="执行频率(秒)")
    timeout: int = Field(30, ge=1, le=300, description="超时时间(秒)")
    priority: int = Field(0, description="优先级")
    preferred_location: Optional[str] = Field(None, max_length=100, description="首选地理位置")
    preferred_isp: Optional[str] = Field(None, max_length=100, description="首选运营商")
    
    @field_validator('target')
    @classmethod
    def validate_target(cls, v):
        if not v or not v.strip():
            raise ValueError('目标地址不能为空')
        return v.strip()


class TaskUpdate(BaseModel):
    """更新任务的请求模式"""
    name: Optional[str] = Field(None, min_length=1, max_length=255, description="任务名称")
    description: Optional[str] = Field(None, description="任务描述")
    protocol: Optional[ProtocolType] = Field(None, description="协议类型")
    target: Optional[str] = Field(None, min_length=1, max_length=255, description="目标地址")
    port: Optional[int] = Field(None, ge=1, le=65535, description="端口号")
    parameters: Optional[Dict[str, Any]] = Field(None, description="协议特定参数")
    frequency: Optional[int] = Field(None, ge=10, le=86400, description="执行频率(秒)")
    timeout: Optional[int] = Field(None, ge=1, le=300, description="超时时间(秒)")
    priority: Optional[int] = Field(None, description="优先级")
    preferred_location: Optional[str] = Field(None, max_length=100, description="首选地理位置")
    preferred_isp: Optional[str] = Field(None, max_length=100, description="首选运营商")
    
    @field_validator('target')
    @classmethod
    def validate_target(cls, v):
        if v is not None and (not v or not v.strip()):
            raise ValueError('目标地址不能为空')
        return v.strip() if v else v


class TaskResponse(BaseSchema):
    """任务响应模式"""
    user_id: uuid.UUID
    name: str
    description: Optional[str]
    protocol: ProtocolType
    target: str
    port: Optional[int]
    parameters: Optional[Dict[str, Any]]
    frequency: int
    timeout: int
    priority: int
    status: TaskStatus
    next_run: Optional[datetime]
    preferred_location: Optional[str]
    preferred_isp: Optional[str]


class TaskResultCreate(BaseModel):
    """创建任务结果的请求模式"""
    task_id: uuid.UUID = Field(..., description="任务ID")
    agent_id: uuid.UUID = Field(..., description="代理ID")
    execution_time: datetime = Field(..., description="执行时间")
    duration: Optional[float] = Field(None, ge=0, description="执行时间(毫秒)")
    status: TaskResultStatus = Field(..., description="执行状态")
    error_message: Optional[str] = Field(None, description="错误信息")
    metrics: Optional[Dict[str, Any]] = Field(None, description="协议特定指标")
    raw_data: Optional[Dict[str, Any]] = Field(None, description="原始响应数据")


class TaskResultResponse(BaseSchema):
    """任务结果响应模式"""
    task_id: uuid.UUID
    agent_id: uuid.UUID
    execution_time: datetime
    duration: Optional[float]
    status: TaskResultStatus
    error_message: Optional[str]
    metrics: Optional[Dict[str, Any]]
    raw_data: Optional[Dict[str, Any]]


class TaskSummary(BaseModel):
    """任务摘要模式"""
    id: uuid.UUID
    name: str
    protocol: ProtocolType
    target: str
    status: TaskStatus
    frequency: int
    last_execution: Optional[datetime] = None
    success_rate: Optional[float] = None
    avg_response_time: Optional[float] = None
    estimated_daily_cost: Optional[float] = None


class TaskStatistics(BaseModel):
    """任务统计模式"""
    task_id: uuid.UUID
    total_executions: int = 0
    successful_executions: int = 0
    failed_executions: int = 0
    timeout_executions: int = 0
    success_rate: float = 0.0
    avg_response_time: Optional[float] = None
    min_response_time: Optional[float] = None
    max_response_time: Optional[float] = None
    last_24h_executions: int = 0
    last_24h_success_rate: float = 0.0


class TaskBatch(BaseModel):
    """批量任务操作模式"""
    task_ids: list[uuid.UUID] = Field(..., min_length=1, description="任务ID列表")
    action: str = Field(..., description="操作类型: pause, resume, delete")
    
    @field_validator('action')
    @classmethod
    def validate_action(cls, v):
        allowed_actions = ['pause', 'resume', 'delete']
        if v not in allowed_actions:
            raise ValueError(f'操作类型必须是: {", ".join(allowed_actions)}')
        return v


class TaskResultSummary(BaseModel):
    """任务结果摘要模式"""
    id: uuid.UUID
    task_name: str
    agent_name: Optional[str] = None
    execution_time: datetime
    status: TaskResultStatus
    response_time: Optional[float] = None
    performance_grade: str
    error_summary: str