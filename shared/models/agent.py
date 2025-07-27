"""代理相关数据模型"""

import uuid
from datetime import datetime, timedelta
from typing import Any, Dict, Optional, List
from enum import Enum

from sqlalchemy import (
    Column, String, Float, DateTime, Text, JSON,
    ForeignKey, Enum as SQLEnum, Boolean, Integer
)
from sqlalchemy.orm import relationship, validates
from pydantic import BaseModel, Field, field_validator

from .base import BaseModel as DBBaseModel, BaseSchema, GUID


class AgentStatus(str, Enum):
    """代理状态枚举"""
    ONLINE = "online"
    OFFLINE = "offline"
    BUSY = "busy"
    MAINTENANCE = "maintenance"


class Agent(DBBaseModel):
    """代理模型"""
    
    __tablename__ = "agents"
    
    # 基本信息
    name = Column(String(255), nullable=False, index=True)
    ip_address = Column(String(45), nullable=False)  # 支持IPv6
    
    # 地理位置信息
    country = Column(String(100))
    city = Column(String(100))
    latitude = Column(Float)
    longitude = Column(Float)
    isp = Column(String(100))  # 运营商
    
    # 版本和能力
    version = Column(String(50), nullable=False)
    capabilities = Column(JSON)  # 支持的协议和功能
    
    # 状态管理
    status = Column(SQLEnum(AgentStatus), nullable=False, default=AgentStatus.OFFLINE)
    last_heartbeat = Column(DateTime(timezone=True))
    registered_at = Column(DateTime(timezone=True), nullable=False, default=datetime.utcnow)
    
    # 性能指标
    availability = Column(Float, default=0.0)  # 可用率 (0-1)
    avg_response_time = Column(Float)  # 平均响应时间(毫秒)
    success_rate = Column(Float, default=0.0)  # 成功率 (0-1)
    
    # 当前资源状态
    current_cpu_usage = Column(Float)
    current_memory_usage = Column(Float)
    current_disk_usage = Column(Float)
    current_load_average = Column(Float)
    
    # 配置信息
    max_concurrent_tasks = Column(Integer, default=10)
    enabled = Column(Boolean, default=True)
    
    # 关系
    resources = relationship("AgentResource", back_populates="agent", cascade="all, delete-orphan")
    task_results = relationship("TaskResult", back_populates="agent")
    
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        if self.status is None:
            self.status = AgentStatus.OFFLINE
        if self.registered_at is None:
            self.registered_at = datetime.utcnow()
        if self.availability is None:
            self.availability = 0.0
        if self.success_rate is None:
            self.success_rate = 0.0
        if self.max_concurrent_tasks is None:
            self.max_concurrent_tasks = 10
        if self.enabled is None:
            self.enabled = True
    
    @validates('name')
    def validate_name(self, key, name):
        """验证代理名称"""
        if not name or not name.strip():
            raise ValueError("代理名称不能为空")
        return name.strip()
    
    @validates('ip_address')
    def validate_ip_address(self, key, ip_address):
        """验证IP地址格式"""
        import ipaddress
        try:
            ipaddress.ip_address(ip_address)
            return ip_address
        except ValueError:
            raise ValueError(f"无效的IP地址格式: {ip_address}")
    
    @validates('version')
    def validate_version(self, key, version):
        """验证版本号格式"""
        if not version or not version.strip():
            raise ValueError("版本号不能为空")
        return version.strip()
    
    @validates('availability', 'success_rate')
    def validate_rate(self, key, value):
        """验证比率值 (0-1)"""
        if value is not None:
            if value < 0 or value > 1:
                raise ValueError(f"{key} 必须在0-1之间")
        return value
    
    @validates('latitude')
    def validate_latitude(self, key, latitude):
        """验证纬度"""
        if latitude is not None:
            if latitude < -90 or latitude > 90:
                raise ValueError("纬度必须在-90到90之间")
        return latitude
    
    @validates('longitude')
    def validate_longitude(self, key, longitude):
        """验证经度"""
        if longitude is not None:
            if longitude < -180 or longitude > 180:
                raise ValueError("经度必须在-180到180之间")
        return longitude
    
    @validates('max_concurrent_tasks')
    def validate_max_concurrent_tasks(self, key, value):
        """验证最大并发任务数"""
        if value is not None and value < 1:
            raise ValueError("最大并发任务数必须大于0")
        return value
    
    def is_online(self) -> bool:
        """检查代理是否在线"""
        return self.status == AgentStatus.ONLINE
    
    def is_available(self) -> bool:
        """检查代理是否可用于执行任务"""
        return (
            self.enabled and
            self.status in [AgentStatus.ONLINE, AgentStatus.BUSY] and
            self.is_heartbeat_recent()
        )
    
    def is_heartbeat_recent(self, timeout_minutes: int = 5) -> bool:
        """检查心跳是否最近"""
        if not self.last_heartbeat:
            return False
        
        timeout = datetime.utcnow() - timedelta(minutes=timeout_minutes)
        return self.last_heartbeat > timeout
    
    def update_heartbeat(self):
        """更新心跳时间"""
        self.last_heartbeat = datetime.utcnow()
        if self.status == AgentStatus.OFFLINE:
            self.status = AgentStatus.ONLINE
    
    def set_offline(self):
        """设置代理离线"""
        self.status = AgentStatus.OFFLINE
    
    def set_maintenance(self):
        """设置代理维护状态"""
        self.status = AgentStatus.MAINTENANCE
    
    def set_busy(self):
        """设置代理忙碌状态"""
        if self.status == AgentStatus.ONLINE:
            self.status = AgentStatus.BUSY
    
    def set_online(self):
        """设置代理在线状态"""
        if self.status in [AgentStatus.BUSY, AgentStatus.OFFLINE, AgentStatus.MAINTENANCE]:
            self.status = AgentStatus.ONLINE
    
    def get_location_string(self) -> str:
        """获取位置字符串"""
        parts = []
        if self.city:
            parts.append(self.city)
        if self.country:
            parts.append(self.country)
        return ", ".join(parts) if parts else "未知位置"
    
    def get_capabilities_list(self) -> List[str]:
        """获取能力列表"""
        if not self.capabilities:
            return []
        
        if isinstance(self.capabilities, dict):
            protocols = self.capabilities.get('protocols', [])
            return protocols if isinstance(protocols, list) else []
        
        return []
    
    def supports_protocol(self, protocol: str) -> bool:
        """检查是否支持指定协议"""
        return protocol.lower() in [p.lower() for p in self.get_capabilities_list()]
    
    def get_resource_status(self) -> Dict[str, Any]:
        """获取资源状态"""
        return {
            'cpu_usage': self.current_cpu_usage,
            'memory_usage': self.current_memory_usage,
            'disk_usage': self.current_disk_usage,
            'load_average': self.current_load_average,
            'status': self.get_resource_health_status()
        }
    
    def get_resource_health_status(self) -> str:
        """获取资源健康状态"""
        if not all([
            self.current_cpu_usage is not None,
            self.current_memory_usage is not None,
            self.current_disk_usage is not None
        ]):
            return "unknown"
        
        # 检查资源使用率
        if (self.current_cpu_usage > 90 or 
            self.current_memory_usage > 90 or 
            self.current_disk_usage > 95):
            return "critical"
        elif (self.current_cpu_usage > 70 or 
              self.current_memory_usage > 70 or 
              self.current_disk_usage > 80):
            return "warning"
        else:
            return "healthy"
    
    def is_overloaded(self) -> bool:
        """检查代理是否过载"""
        health_status = self.get_resource_health_status()
        return health_status in ["critical", "warning"]
    
    def update_performance_metrics(self, availability: float = None, 
                                 avg_response_time: float = None, 
                                 success_rate: float = None):
        """更新性能指标"""
        if availability is not None:
            self.availability = max(0.0, min(1.0, availability))
        if avg_response_time is not None:
            self.avg_response_time = max(0.0, avg_response_time)
        if success_rate is not None:
            self.success_rate = max(0.0, min(1.0, success_rate))
    
    def update_resource_status(self, cpu_usage: float = None, 
                             memory_usage: float = None,
                             disk_usage: float = None, 
                             load_average: float = None):
        """更新资源状态"""
        if cpu_usage is not None:
            self.current_cpu_usage = max(0.0, min(100.0, cpu_usage))
        if memory_usage is not None:
            self.current_memory_usage = max(0.0, min(100.0, memory_usage))
        if disk_usage is not None:
            self.current_disk_usage = max(0.0, min(100.0, disk_usage))
        if load_average is not None:
            self.current_load_average = max(0.0, load_average)
    
    def get_selection_score(self, target_location: str = None, 
                          target_isp: str = None) -> float:
        """计算代理选择评分 (0-1)"""
        if not self.is_available():
            return 0.0
        
        score = 0.0
        
        # 基础可用性评分 (40%)
        score += self.availability * 0.4
        
        # 性能评分 (30%)
        if self.success_rate is not None:
            score += self.success_rate * 0.3
        
        # 资源状态评分 (20%)
        resource_score = 1.0
        if self.is_overloaded():
            resource_score = 0.3
        elif self.get_resource_health_status() == "warning":
            resource_score = 0.7
        score += resource_score * 0.2
        
        # 地理位置匹配评分 (10%)
        location_score = 0.5  # 默认评分
        if target_location and self.city:
            if target_location.lower() in self.city.lower():
                location_score = 1.0
            elif target_location.lower() in self.country.lower():
                location_score = 0.8
        
        if target_isp and self.isp:
            if target_isp.lower() in self.isp.lower():
                location_score = min(1.0, location_score + 0.3)
        
        score += location_score * 0.1
        
        return min(1.0, max(0.0, score))
    
    def can_handle_task(self, protocol: str) -> bool:
        """检查是否能处理指定协议的任务"""
        return (
            self.is_available() and
            self.supports_protocol(protocol) and
            not self.is_overloaded()
        )
    
    def get_uptime_hours(self) -> Optional[float]:
        """获取运行时间(小时)"""
        if not self.registered_at:
            return None
        
        uptime = datetime.utcnow() - self.registered_at
        return uptime.total_seconds() / 3600
    
    def get_status_display(self) -> str:
        """获取状态显示文本"""
        status_map = {
            AgentStatus.ONLINE: "在线",
            AgentStatus.OFFLINE: "离线",
            AgentStatus.BUSY: "忙碌",
            AgentStatus.MAINTENANCE: "维护中"
        }
        return status_map.get(self.status, "未知")
    
    def to_summary_dict(self) -> Dict[str, Any]:
        """转换为摘要字典"""
        return {
            'id': str(self.id) if hasattr(self, 'id') else None,
            'name': self.name,
            'ip_address': self.ip_address,
            'location': self.get_location_string(),
            'isp': self.isp,
            'version': self.version,
            'status': self.status.value,
            'status_display': self.get_status_display(),
            'availability': self.availability,
            'success_rate': self.success_rate,
            'avg_response_time': self.avg_response_time,
            'resource_health': self.get_resource_health_status(),
            'last_heartbeat': self.last_heartbeat.isoformat() if self.last_heartbeat else None,
            'uptime_hours': self.get_uptime_hours(),
            'enabled': self.enabled
        }


class AgentResource(DBBaseModel):
    """代理资源监控记录模型"""
    
    __tablename__ = "agent_resources"
    
    # 关联信息
    agent_id = Column(GUID(), ForeignKey("agents.id"), nullable=False, index=True)
    
    # 时间戳
    timestamp = Column(DateTime(timezone=True), nullable=False, default=datetime.utcnow, index=True)
    
    # 资源指标
    cpu_usage = Column(Float, nullable=False)  # CPU使用率 (0-100)
    memory_usage = Column(Float, nullable=False)  # 内存使用率 (0-100)
    disk_usage = Column(Float, nullable=False)  # 磁盘使用率 (0-100)
    network_in = Column(Float)  # 网络入流量 (MB/s)
    network_out = Column(Float)  # 网络出流量 (MB/s)
    load_average = Column(Float)  # 系统负载平均值
    
    # 扩展指标
    memory_total = Column(Float)  # 总内存 (MB)
    memory_available = Column(Float)  # 可用内存 (MB)
    disk_total = Column(Float)  # 总磁盘空间 (GB)
    disk_available = Column(Float)  # 可用磁盘空间 (GB)
    
    # 关系
    agent = relationship("Agent", back_populates="resources")
    
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        if self.timestamp is None:
            self.timestamp = datetime.utcnow()
    
    @validates('cpu_usage', 'memory_usage', 'disk_usage')
    def validate_percentage(self, key, value):
        """验证百分比值"""
        if value < 0 or value > 100:
            raise ValueError(f"{key} 必须在0-100之间")
        return value
    
    @validates('network_in', 'network_out', 'load_average')
    def validate_positive(self, key, value):
        """验证正数值"""
        if value is not None and value < 0:
            raise ValueError(f"{key} 不能为负数")
        return value
    
    @validates('memory_total', 'memory_available', 'disk_total', 'disk_available')
    def validate_size(self, key, value):
        """验证大小值"""
        if value is not None and value < 0:
            raise ValueError(f"{key} 不能为负数")
        return value
    
    def is_critical(self) -> bool:
        """检查资源是否处于临界状态"""
        return (
            self.cpu_usage > 90 or
            self.memory_usage > 90 or
            self.disk_usage > 95
        )
    
    def is_warning(self) -> bool:
        """检查资源是否处于警告状态"""
        return (
            self.cpu_usage > 70 or
            self.memory_usage > 70 or
            self.disk_usage > 80
        )
    
    def get_health_status(self) -> str:
        """获取健康状态"""
        if self.is_critical():
            return "critical"
        elif self.is_warning():
            return "warning"
        else:
            return "healthy"
    
    def get_memory_usage_mb(self) -> Optional[float]:
        """获取内存使用量(MB)"""
        if self.memory_total and self.memory_usage:
            return (self.memory_usage / 100) * self.memory_total
        return None
    
    def get_disk_usage_gb(self) -> Optional[float]:
        """获取磁盘使用量(GB)"""
        if self.disk_total and self.disk_usage:
            return (self.disk_usage / 100) * self.disk_total
        return None
    
    def get_network_total_mbps(self) -> Optional[float]:
        """获取总网络流量(MB/s)"""
        if self.network_in is not None and self.network_out is not None:
            return self.network_in + self.network_out
        return None
    
    def to_metrics_dict(self) -> Dict[str, Any]:
        """转换为指标字典"""
        return {
            'timestamp': self.timestamp.isoformat() if self.timestamp else None,
            'cpu_usage': self.cpu_usage,
            'memory_usage': self.memory_usage,
            'disk_usage': self.disk_usage,
            'network_in': self.network_in,
            'network_out': self.network_out,
            'load_average': self.load_average,
            'memory_total': self.memory_total,
            'memory_available': self.memory_available,
            'disk_total': self.disk_total,
            'disk_available': self.disk_available,
            'health_status': self.get_health_status(),
            'memory_usage_mb': self.get_memory_usage_mb(),
            'disk_usage_gb': self.get_disk_usage_gb(),
            'network_total_mbps': self.get_network_total_mbps()
        }
    
    def compare_with_previous(self, previous: 'AgentResource') -> Dict[str, Any]:
        """与前一个记录比较"""
        if not previous:
            return {}
        
        return {
            'cpu_change': self.cpu_usage - previous.cpu_usage,
            'memory_change': self.memory_usage - previous.memory_usage,
            'disk_change': self.disk_usage - previous.disk_usage,
            'load_change': (self.load_average - previous.load_average) if 
                          (self.load_average and previous.load_average) else None,
            'time_diff_seconds': (self.timestamp - previous.timestamp).total_seconds()
        }


# Pydantic 模式定义

class AgentLocationCreate(BaseModel):
    """代理位置信息"""
    country: Optional[str] = Field(None, max_length=100, description="国家")
    city: Optional[str] = Field(None, max_length=100, description="城市")
    latitude: Optional[float] = Field(None, ge=-90, le=90, description="纬度")
    longitude: Optional[float] = Field(None, ge=-180, le=180, description="经度")
    isp: Optional[str] = Field(None, max_length=100, description="运营商")


class AgentCapabilities(BaseModel):
    """代理能力信息"""
    protocols: List[str] = Field(default_factory=list, description="支持的协议")
    max_concurrent_tasks: int = Field(10, ge=1, description="最大并发任务数")
    features: Optional[Dict[str, Any]] = Field(None, description="其他功能特性")


class AgentCreate(BaseModel):
    """创建代理的请求模式"""
    name: str = Field(..., min_length=1, max_length=255, description="代理名称")
    ip_address: str = Field(..., description="IP地址")
    version: str = Field(..., min_length=1, max_length=50, description="版本号")
    location: Optional[AgentLocationCreate] = Field(None, description="位置信息")
    capabilities: Optional[AgentCapabilities] = Field(None, description="能力信息")
    
    @field_validator('name')
    @classmethod
    def validate_name(cls, v):
        if not v or not v.strip():
            raise ValueError('代理名称不能为空')
        return v.strip()
    
    @field_validator('ip_address')
    @classmethod
    def validate_ip_address(cls, v):
        import ipaddress
        try:
            ipaddress.ip_address(v)
            return v
        except ValueError:
            raise ValueError(f'无效的IP地址格式: {v}')


class AgentUpdate(BaseModel):
    """更新代理的请求模式"""
    name: Optional[str] = Field(None, min_length=1, max_length=255, description="代理名称")
    version: Optional[str] = Field(None, min_length=1, max_length=50, description="版本号")
    location: Optional[AgentLocationCreate] = Field(None, description="位置信息")
    capabilities: Optional[AgentCapabilities] = Field(None, description="能力信息")
    enabled: Optional[bool] = Field(None, description="是否启用")
    max_concurrent_tasks: Optional[int] = Field(None, ge=1, description="最大并发任务数")


class AgentResponse(BaseSchema):
    """代理响应模式"""
    name: str
    ip_address: str
    country: Optional[str]
    city: Optional[str]
    latitude: Optional[float]
    longitude: Optional[float]
    isp: Optional[str]
    version: str
    capabilities: Optional[Dict[str, Any]]
    status: AgentStatus
    last_heartbeat: Optional[datetime]
    registered_at: datetime
    availability: float
    avg_response_time: Optional[float]
    success_rate: float
    current_cpu_usage: Optional[float]
    current_memory_usage: Optional[float]
    current_disk_usage: Optional[float]
    current_load_average: Optional[float]
    max_concurrent_tasks: int
    enabled: bool


class AgentResourceCreate(BaseModel):
    """创建代理资源记录的请求模式"""
    agent_id: uuid.UUID = Field(..., description="代理ID")
    cpu_usage: float = Field(..., ge=0, le=100, description="CPU使用率")
    memory_usage: float = Field(..., ge=0, le=100, description="内存使用率")
    disk_usage: float = Field(..., ge=0, le=100, description="磁盘使用率")
    network_in: Optional[float] = Field(None, ge=0, description="网络入流量(MB/s)")
    network_out: Optional[float] = Field(None, ge=0, description="网络出流量(MB/s)")
    load_average: Optional[float] = Field(None, ge=0, description="系统负载平均值")
    memory_total: Optional[float] = Field(None, ge=0, description="总内存(MB)")
    memory_available: Optional[float] = Field(None, ge=0, description="可用内存(MB)")
    disk_total: Optional[float] = Field(None, ge=0, description="总磁盘空间(GB)")
    disk_available: Optional[float] = Field(None, ge=0, description="可用磁盘空间(GB)")


class AgentResourceResponse(BaseSchema):
    """代理资源响应模式"""
    agent_id: uuid.UUID
    timestamp: datetime
    cpu_usage: float
    memory_usage: float
    disk_usage: float
    network_in: Optional[float]
    network_out: Optional[float]
    load_average: Optional[float]
    memory_total: Optional[float]
    memory_available: Optional[float]
    disk_total: Optional[float]
    disk_available: Optional[float]


class AgentSummary(BaseModel):
    """代理摘要模式"""
    id: uuid.UUID
    name: str
    ip_address: str
    location: str
    status: AgentStatus
    availability: float
    success_rate: float
    resource_health: str
    last_heartbeat: Optional[datetime]
    uptime_hours: Optional[float]


class AgentStatistics(BaseModel):
    """代理统计模式"""
    agent_id: uuid.UUID
    total_tasks_executed: int = 0
    successful_tasks: int = 0
    failed_tasks: int = 0
    avg_execution_time: Optional[float] = None
    uptime_percentage: float = 0.0
    last_24h_tasks: int = 0
    last_24h_success_rate: float = 0.0
    resource_alerts_count: int = 0


class AgentHealthCheck(BaseModel):
    """代理健康检查模式"""
    agent_id: uuid.UUID
    timestamp: datetime
    is_online: bool
    is_available: bool
    resource_status: str
    last_heartbeat_minutes_ago: Optional[int]
    issues: List[str] = Field(default_factory=list)
    recommendations: List[str] = Field(default_factory=list)