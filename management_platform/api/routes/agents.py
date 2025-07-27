"""代理管理API路由"""

from typing import List, Optional, Dict, Any
from fastapi import APIRouter, Depends, HTTPException, status, Query
from pydantic import BaseModel
import uuid
from datetime import datetime, timedelta

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', '..'))

from shared.models.agent import (
    Agent, AgentResource, AgentCreate, AgentUpdate, AgentResponse, 
    AgentResourceCreate, AgentResourceResponse, AgentSummary, 
    AgentStatistics, AgentHealthCheck, AgentStatus
)
from shared.models.user import User, UserRole
from management_platform.database.repositories import AgentRepository, AgentResourceRepository, TaskResultRepository
from ..dependencies import get_db_session, get_current_user, require_admin

router = APIRouter()


class AgentListResponse(BaseModel):
    """代理列表响应模型"""
    agents: List[AgentResponse]
    total: int
    page: int
    size: int


class AgentResourceListResponse(BaseModel):
    """代理资源列表响应模型"""
    resources: List[AgentResourceResponse]
    total: int
    page: int
    size: int


class AgentSummaryListResponse(BaseModel):
    """代理摘要列表响应模型"""
    agents: List[AgentSummary]
    total: int
    page: int
    size: int


@router.post("/", response_model=AgentResponse, summary="注册新代理")
async def create_agent(
    agent_data: AgentCreate,
    current_user: User = Depends(require_admin),
    session = Depends(get_db_session)
):
    """
    注册新代理（仅管理员）
    
    - **name**: 代理名称
    - **ip_address**: IP地址
    - **version**: 版本号
    - **location**: 位置信息（可选）
    - **capabilities**: 能力信息（可选）
    """
    agent_repo = AgentRepository(session)
    
    # 检查代理名称是否已存在
    if await agent_repo.is_name_taken(agent_data.name):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="代理名称已存在"
        )
    
    # 检查IP地址是否已存在
    existing_agent = await agent_repo.get_by_ip_address(agent_data.ip_address)
    if existing_agent:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="IP地址已被其他代理使用"
        )
    
    # 准备创建数据
    create_data = {
        "name": agent_data.name,
        "ip_address": agent_data.ip_address,
        "version": agent_data.version,
        "status": AgentStatus.OFFLINE,
        "availability": 0.0,
        "success_rate": 0.0,
        "enabled": True
    }
    
    # 添加位置信息
    if agent_data.location:
        create_data.update({
            "country": agent_data.location.country,
            "city": agent_data.location.city,
            "latitude": agent_data.location.latitude,
            "longitude": agent_data.location.longitude,
            "isp": agent_data.location.isp
        })
    
    # 添加能力信息
    if agent_data.capabilities:
        capabilities_dict = {
            "protocols": agent_data.capabilities.protocols,
            "features": agent_data.capabilities.features or {}
        }
        create_data["capabilities"] = capabilities_dict
        create_data["max_concurrent_tasks"] = agent_data.capabilities.max_concurrent_tasks
    
    # 创建代理
    created_agent = await agent_repo.create(create_data)
    await agent_repo.commit()
    
    return AgentResponse(
        id=created_agent.id,
        name=created_agent.name,
        ip_address=created_agent.ip_address,
        country=created_agent.country,
        city=created_agent.city,
        latitude=created_agent.latitude,
        longitude=created_agent.longitude,
        isp=created_agent.isp,
        version=created_agent.version,
        capabilities=created_agent.capabilities,
        status=created_agent.status,
        last_heartbeat=created_agent.last_heartbeat,
        registered_at=created_agent.registered_at,
        availability=created_agent.availability,
        avg_response_time=created_agent.avg_response_time,
        success_rate=created_agent.success_rate,
        current_cpu_usage=created_agent.current_cpu_usage,
        current_memory_usage=created_agent.current_memory_usage,
        current_disk_usage=created_agent.current_disk_usage,
        current_load_average=created_agent.current_load_average,
        max_concurrent_tasks=created_agent.max_concurrent_tasks,
        enabled=created_agent.enabled,
        created_at=created_agent.created_at,
        updated_at=created_agent.updated_at
    )


@router.get("/", response_model=AgentListResponse, summary="获取代理列表")
async def get_agents(
    page: int = Query(1, ge=1, description="页码"),
    size: int = Query(20, ge=1, le=100, description="每页数量"),
    status: Optional[AgentStatus] = Query(None, description="状态过滤"),
    search: Optional[str] = Query(None, description="搜索关键词"),
    current_user: User = Depends(get_current_user),
    session = Depends(get_db_session)
):
    """
    获取代理列表
    
    - 支持按状态过滤和关键词搜索
    - **page**: 页码（从1开始）
    - **size**: 每页数量（1-100）
    - **status**: 状态过滤（可选）
    - **search**: 搜索关键词（可选，搜索名称、IP、位置、运营商）
    """
    agent_repo = AgentRepository(session)
    
    skip = (page - 1) * size
    
    if search:
        agents = await agent_repo.search(search, skip=skip, limit=size)
    elif status:
        agents = await agent_repo.get_by_status(status.value, skip=skip, limit=size)
    else:
        agents = await agent_repo.get_all(skip=skip, limit=size)
    
    total = await agent_repo.count()
    
    agent_responses = [
        AgentResponse(
            id=agent.id,
            name=agent.name,
            ip_address=agent.ip_address,
            country=agent.country,
            city=agent.city,
            latitude=agent.latitude,
            longitude=agent.longitude,
            isp=agent.isp,
            version=agent.version,
            capabilities=agent.capabilities,
            status=agent.status,
            last_heartbeat=agent.last_heartbeat,
            registered_at=agent.registered_at,
            availability=agent.availability,
            avg_response_time=agent.avg_response_time,
            success_rate=agent.success_rate,
            current_cpu_usage=agent.current_cpu_usage,
            current_memory_usage=agent.current_memory_usage,
            current_disk_usage=agent.current_disk_usage,
            current_load_average=agent.current_load_average,
            max_concurrent_tasks=agent.max_concurrent_tasks,
            enabled=agent.enabled,
            created_at=agent.created_at,
            updated_at=agent.updated_at
        )
        for agent in agents
    ]
    
    return AgentListResponse(
        agents=agent_responses,
        total=total,
        page=page,
        size=size
    )


@router.get("/summary", response_model=AgentSummaryListResponse, summary="获取代理摘要")
async def get_agent_summary(
    page: int = Query(1, ge=1, description="页码"),
    size: int = Query(20, ge=1, le=100, description="每页数量"),
    current_user: User = Depends(get_current_user),
    session = Depends(get_db_session)
):
    """
    获取代理摘要信息
    """
    agent_repo = AgentRepository(session)
    
    skip = (page - 1) * size
    agents = await agent_repo.get_all(skip=skip, limit=size)
    total = await agent_repo.count()
    
    agent_summaries = []
    for agent in agents:
        location = agent.get_location_string()
        uptime_hours = agent.get_uptime_hours()
        resource_health = agent.get_resource_health_status()
        
        agent_summaries.append(AgentSummary(
            id=agent.id,
            name=agent.name,
            ip_address=agent.ip_address,
            location=location,
            status=agent.status,
            availability=agent.availability,
            success_rate=agent.success_rate,
            resource_health=resource_health,
            last_heartbeat=agent.last_heartbeat,
            uptime_hours=uptime_hours
        ))
    
    return AgentSummaryListResponse(
        agents=agent_summaries,
        total=total,
        page=page,
        size=size
    )


@router.get("/available", response_model=AgentListResponse, summary="获取可用代理")
async def get_available_agents(
    page: int = Query(1, ge=1, description="页码"),
    size: int = Query(20, ge=1, le=100, description="每页数量"),
    current_user: User = Depends(get_current_user),
    session = Depends(get_db_session)
):
    """
    获取当前可用的代理列表
    """
    agent_repo = AgentRepository(session)
    
    skip = (page - 1) * size
    agents = await agent_repo.get_available_agents(skip=skip, limit=size)
    
    # 获取总的可用代理数量
    all_available = await agent_repo.get_available_agents(skip=0, limit=10000)
    total = len(all_available)
    
    agent_responses = [
        AgentResponse(
            id=agent.id,
            name=agent.name,
            ip_address=agent.ip_address,
            country=agent.country,
            city=agent.city,
            latitude=agent.latitude,
            longitude=agent.longitude,
            isp=agent.isp,
            version=agent.version,
            capabilities=agent.capabilities,
            status=agent.status,
            last_heartbeat=agent.last_heartbeat,
            registered_at=agent.registered_at,
            availability=agent.availability,
            avg_response_time=agent.avg_response_time,
            success_rate=agent.success_rate,
            current_cpu_usage=agent.current_cpu_usage,
            current_memory_usage=agent.current_memory_usage,
            current_disk_usage=agent.current_disk_usage,
            current_load_average=agent.current_load_average,
            max_concurrent_tasks=agent.max_concurrent_tasks,
            enabled=agent.enabled,
            created_at=agent.created_at,
            updated_at=agent.updated_at
        )
        for agent in agents
    ]
    
    return AgentListResponse(
        agents=agent_responses,
        total=total,
        page=page,
        size=size
    )


@router.get("/{agent_id}", response_model=AgentResponse, summary="获取代理详情")
async def get_agent(
    agent_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    session = Depends(get_db_session)
):
    """
    获取代理详情
    """
    agent_repo = AgentRepository(session)
    
    agent = await agent_repo.get_by_id(agent_id)
    if not agent:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="代理不存在"
        )
    
    return AgentResponse(
        id=agent.id,
        name=agent.name,
        ip_address=agent.ip_address,
        country=agent.country,
        city=agent.city,
        latitude=agent.latitude,
        longitude=agent.longitude,
        isp=agent.isp,
        version=agent.version,
        capabilities=agent.capabilities,
        status=agent.status,
        last_heartbeat=agent.last_heartbeat,
        registered_at=agent.registered_at,
        availability=agent.availability,
        avg_response_time=agent.avg_response_time,
        success_rate=agent.success_rate,
        current_cpu_usage=agent.current_cpu_usage,
        current_memory_usage=agent.current_memory_usage,
        current_disk_usage=agent.current_disk_usage,
        current_load_average=agent.current_load_average,
        max_concurrent_tasks=agent.max_concurrent_tasks,
        enabled=agent.enabled,
        created_at=agent.created_at,
        updated_at=agent.updated_at
    )


@router.put("/{agent_id}", response_model=AgentResponse, summary="更新代理信息")
async def update_agent(
    agent_id: uuid.UUID,
    agent_data: AgentUpdate,
    current_user: User = Depends(require_admin),
    session = Depends(get_db_session)
):
    """
    更新代理信息（仅管理员）
    """
    agent_repo = AgentRepository(session)
    
    agent = await agent_repo.get_by_id(agent_id)
    if not agent:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="代理不存在"
        )
    
    # 准备更新数据
    update_data = {}
    
    if agent_data.name is not None:
        if await agent_repo.is_name_taken(agent_data.name, exclude_agent_id=agent_id):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="代理名称已存在"
            )
        update_data["name"] = agent_data.name
    
    if agent_data.version is not None:
        update_data["version"] = agent_data.version
    
    if agent_data.location is not None:
        update_data.update({
            "country": agent_data.location.country,
            "city": agent_data.location.city,
            "latitude": agent_data.location.latitude,
            "longitude": agent_data.location.longitude,
            "isp": agent_data.location.isp
        })
    
    if agent_data.capabilities is not None:
        capabilities_dict = {
            "protocols": agent_data.capabilities.protocols,
            "features": agent_data.capabilities.features or {}
        }
        update_data["capabilities"] = capabilities_dict
        update_data["max_concurrent_tasks"] = agent_data.capabilities.max_concurrent_tasks
    
    if agent_data.enabled is not None:
        update_data["enabled"] = agent_data.enabled
    
    if agent_data.max_concurrent_tasks is not None:
        update_data["max_concurrent_tasks"] = agent_data.max_concurrent_tasks
    
    if update_data:
        updated_agent = await agent_repo.update(agent_id, update_data)
        await agent_repo.commit()
        
        return AgentResponse(
            id=updated_agent.id,
            name=updated_agent.name,
            ip_address=updated_agent.ip_address,
            country=updated_agent.country,
            city=updated_agent.city,
            latitude=updated_agent.latitude,
            longitude=updated_agent.longitude,
            isp=updated_agent.isp,
            version=updated_agent.version,
            capabilities=updated_agent.capabilities,
            status=updated_agent.status,
            last_heartbeat=updated_agent.last_heartbeat,
            registered_at=updated_agent.registered_at,
            availability=updated_agent.availability,
            avg_response_time=updated_agent.avg_response_time,
            success_rate=updated_agent.success_rate,
            current_cpu_usage=updated_agent.current_cpu_usage,
            current_memory_usage=updated_agent.current_memory_usage,
            current_disk_usage=updated_agent.current_disk_usage,
            current_load_average=updated_agent.current_load_average,
            max_concurrent_tasks=updated_agent.max_concurrent_tasks,
            enabled=updated_agent.enabled,
            created_at=updated_agent.created_at,
            updated_at=updated_agent.updated_at
        )
    
    # 没有更新数据，返回原代理
    return AgentResponse(
        id=agent.id,
        name=agent.name,
        ip_address=agent.ip_address,
        country=agent.country,
        city=agent.city,
        latitude=agent.latitude,
        longitude=agent.longitude,
        isp=agent.isp,
        version=agent.version,
        capabilities=agent.capabilities,
        status=agent.status,
        last_heartbeat=agent.last_heartbeat,
        registered_at=agent.registered_at,
        availability=agent.availability,
        avg_response_time=agent.avg_response_time,
        success_rate=agent.success_rate,
        current_cpu_usage=agent.current_cpu_usage,
        current_memory_usage=agent.current_memory_usage,
        current_disk_usage=agent.current_disk_usage,
        current_load_average=agent.current_load_average,
        max_concurrent_tasks=agent.max_concurrent_tasks,
        enabled=agent.enabled,
        created_at=agent.created_at,
        updated_at=agent.updated_at
    )


@router.delete("/{agent_id}", summary="删除代理")
async def delete_agent(
    agent_id: uuid.UUID,
    current_user: User = Depends(require_admin),
    session = Depends(get_db_session)
):
    """
    删除代理（仅管理员）
    """
    agent_repo = AgentRepository(session)
    
    agent = await agent_repo.get_by_id(agent_id)
    if not agent:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="代理不存在"
        )
    
    await agent_repo.delete(agent_id)
    await agent_repo.commit()
    
    return {"message": "代理删除成功"}


@router.post("/{agent_id}/heartbeat", summary="更新代理心跳")
async def update_heartbeat(
    agent_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    session = Depends(get_db_session)
):
    """
    更新代理心跳时间
    """
    agent_repo = AgentRepository(session)
    
    success = await agent_repo.update_heartbeat(agent_id)
    if not success:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="代理不存在"
        )
    
    await agent_repo.commit()
    return {"message": "心跳更新成功"}


@router.post("/{agent_id}/enable", response_model=AgentResponse, summary="启用代理")
async def enable_agent(
    agent_id: uuid.UUID,
    current_user: User = Depends(require_admin),
    session = Depends(get_db_session)
):
    """
    启用代理（仅管理员）
    """
    agent_repo = AgentRepository(session)
    
    agent = await agent_repo.get_by_id(agent_id)
    if not agent:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="代理不存在"
        )
    
    updated_agent = await agent_repo.update(agent_id, {"enabled": True})
    await agent_repo.commit()
    
    return AgentResponse(
        id=updated_agent.id,
        name=updated_agent.name,
        ip_address=updated_agent.ip_address,
        country=updated_agent.country,
        city=updated_agent.city,
        latitude=updated_agent.latitude,
        longitude=updated_agent.longitude,
        isp=updated_agent.isp,
        version=updated_agent.version,
        capabilities=updated_agent.capabilities,
        status=updated_agent.status,
        last_heartbeat=updated_agent.last_heartbeat,
        registered_at=updated_agent.registered_at,
        availability=updated_agent.availability,
        avg_response_time=updated_agent.avg_response_time,
        success_rate=updated_agent.success_rate,
        current_cpu_usage=updated_agent.current_cpu_usage,
        current_memory_usage=updated_agent.current_memory_usage,
        current_disk_usage=updated_agent.current_disk_usage,
        current_load_average=updated_agent.current_load_average,
        max_concurrent_tasks=updated_agent.max_concurrent_tasks,
        enabled=updated_agent.enabled,
        created_at=updated_agent.created_at,
        updated_at=updated_agent.updated_at
    )


@router.post("/{agent_id}/disable", response_model=AgentResponse, summary="禁用代理")
async def disable_agent(
    agent_id: uuid.UUID,
    current_user: User = Depends(require_admin),
    session = Depends(get_db_session)
):
    """
    禁用代理（仅管理员）
    """
    agent_repo = AgentRepository(session)
    
    agent = await agent_repo.get_by_id(agent_id)
    if not agent:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="代理不存在"
        )
    
    updated_agent = await agent_repo.update(agent_id, {"enabled": False})
    await agent_repo.commit()
    
    return AgentResponse(
        id=updated_agent.id,
        name=updated_agent.name,
        ip_address=updated_agent.ip_address,
        country=updated_agent.country,
        city=updated_agent.city,
        latitude=updated_agent.latitude,
        longitude=updated_agent.longitude,
        isp=updated_agent.isp,
        version=updated_agent.version,
        capabilities=updated_agent.capabilities,
        status=updated_agent.status,
        last_heartbeat=updated_agent.last_heartbeat,
        registered_at=updated_agent.registered_at,
        availability=updated_agent.availability,
        avg_response_time=updated_agent.avg_response_time,
        success_rate=updated_agent.success_rate,
        current_cpu_usage=updated_agent.current_cpu_usage,
        current_memory_usage=updated_agent.current_memory_usage,
        current_disk_usage=updated_agent.current_disk_usage,
        current_load_average=updated_agent.current_load_average,
        max_concurrent_tasks=updated_agent.max_concurrent_tasks,
        enabled=updated_agent.enabled,
        created_at=updated_agent.created_at,
        updated_at=updated_agent.updated_at
    )


@router.post("/{agent_id}/maintenance", response_model=AgentResponse, summary="设置代理维护状态")
async def set_maintenance(
    agent_id: uuid.UUID,
    current_user: User = Depends(require_admin),
    session = Depends(get_db_session)
):
    """
    设置代理为维护状态（仅管理员）
    """
    agent_repo = AgentRepository(session)
    
    agent = await agent_repo.get_by_id(agent_id)
    if not agent:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="代理不存在"
        )
    
    updated_agent = await agent_repo.update(agent_id, {"status": AgentStatus.MAINTENANCE})
    await agent_repo.commit()
    
    return AgentResponse(
        id=updated_agent.id,
        name=updated_agent.name,
        ip_address=updated_agent.ip_address,
        country=updated_agent.country,
        city=updated_agent.city,
        latitude=updated_agent.latitude,
        longitude=updated_agent.longitude,
        isp=updated_agent.isp,
        version=updated_agent.version,
        capabilities=updated_agent.capabilities,
        status=updated_agent.status,
        last_heartbeat=updated_agent.last_heartbeat,
        registered_at=updated_agent.registered_at,
        availability=updated_agent.availability,
        avg_response_time=updated_agent.avg_response_time,
        success_rate=updated_agent.success_rate,
        current_cpu_usage=updated_agent.current_cpu_usage,
        current_memory_usage=updated_agent.current_memory_usage,
        current_disk_usage=updated_agent.current_disk_usage,
        current_load_average=updated_agent.current_load_average,
        max_concurrent_tasks=updated_agent.max_concurrent_tasks,
        enabled=updated_agent.enabled,
        created_at=updated_agent.created_at,
        updated_at=updated_agent.updated_at
    )


# 代理资源相关端点

@router.post("/{agent_id}/resources", response_model=AgentResourceResponse, summary="上报代理资源")
async def create_agent_resource(
    agent_id: uuid.UUID,
    resource_data: AgentResourceCreate,
    current_user: User = Depends(get_current_user),
    session = Depends(get_db_session)
):
    """
    上报代理资源使用情况
    """
    agent_repo = AgentRepository(session)
    resource_repo = AgentResourceRepository(session)
    
    # 验证代理存在
    agent = await agent_repo.get_by_id(agent_id)
    if not agent:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="代理不存在"
        )
    
    # 验证agent_id匹配
    if resource_data.agent_id != agent_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="代理ID不匹配"
        )
    
    # 创建资源记录
    created_resource = await resource_repo.create({
        "agent_id": resource_data.agent_id,
        "cpu_usage": resource_data.cpu_usage,
        "memory_usage": resource_data.memory_usage,
        "disk_usage": resource_data.disk_usage,
        "network_in": resource_data.network_in,
        "network_out": resource_data.network_out,
        "load_average": resource_data.load_average,
        "memory_total": resource_data.memory_total,
        "memory_available": resource_data.memory_available,
        "disk_total": resource_data.disk_total,
        "disk_available": resource_data.disk_available
    })
    
    # 更新代理的当前资源状态
    await agent_repo.update(agent_id, {
        "current_cpu_usage": resource_data.cpu_usage,
        "current_memory_usage": resource_data.memory_usage,
        "current_disk_usage": resource_data.disk_usage,
        "current_load_average": resource_data.load_average
    })
    
    await resource_repo.commit()
    
    return AgentResourceResponse(
        id=created_resource.id,
        agent_id=created_resource.agent_id,
        timestamp=created_resource.timestamp,
        cpu_usage=created_resource.cpu_usage,
        memory_usage=created_resource.memory_usage,
        disk_usage=created_resource.disk_usage,
        network_in=created_resource.network_in,
        network_out=created_resource.network_out,
        load_average=created_resource.load_average,
        memory_total=created_resource.memory_total,
        memory_available=created_resource.memory_available,
        disk_total=created_resource.disk_total,
        disk_available=created_resource.disk_available,
        created_at=created_resource.created_at,
        updated_at=created_resource.updated_at
    )


@router.get("/{agent_id}/resources", response_model=AgentResourceListResponse, summary="获取代理资源记录")
async def get_agent_resources(
    agent_id: uuid.UUID,
    page: int = Query(1, ge=1, description="页码"),
    size: int = Query(20, ge=1, le=100, description="每页数量"),
    current_user: User = Depends(get_current_user),
    session = Depends(get_db_session)
):
    """
    获取代理的资源使用记录
    """
    agent_repo = AgentRepository(session)
    resource_repo = AgentResourceRepository(session)
    
    # 验证代理存在
    agent = await agent_repo.get_by_id(agent_id)
    if not agent:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="代理不存在"
        )
    
    skip = (page - 1) * size
    resources = await resource_repo.get_by_agent_id(agent_id, skip=skip, limit=size)
    total = await resource_repo.count(agent_id=agent_id)
    
    resource_responses = [
        AgentResourceResponse(
            id=resource.id,
            agent_id=resource.agent_id,
            timestamp=resource.timestamp,
            cpu_usage=resource.cpu_usage,
            memory_usage=resource.memory_usage,
            disk_usage=resource.disk_usage,
            network_in=resource.network_in,
            network_out=resource.network_out,
            load_average=resource.load_average,
            memory_total=resource.memory_total,
            memory_available=resource.memory_available,
            disk_total=resource.disk_total,
            disk_available=resource.disk_available,
            created_at=resource.created_at,
            updated_at=resource.updated_at
        )
        for resource in resources
    ]
    
    return AgentResourceListResponse(
        resources=resource_responses,
        total=total,
        page=page,
        size=size
    )


@router.get("/{agent_id}/statistics", response_model=AgentStatistics, summary="获取代理统计")
async def get_agent_statistics(
    agent_id: uuid.UUID,
    days: int = Query(30, ge=1, le=365, description="统计天数"),
    current_user: User = Depends(get_current_user),
    session = Depends(get_db_session)
):
    """
    获取代理的统计信息
    """
    agent_repo = AgentRepository(session)
    result_repo = TaskResultRepository(session)
    resource_repo = AgentResourceRepository(session)
    
    # 验证代理存在
    agent = await agent_repo.get_by_id(agent_id)
    if not agent:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="代理不存在"
        )
    
    # 获取指定天数内的任务结果
    cutoff_date = datetime.utcnow() - timedelta(days=days)
    
    # 这里简化实现，实际应该在repository中添加按代理和时间过滤的方法
    # 获取所有结果然后过滤（生产环境应该优化）
    all_results = []
    # 由于没有直接的方法获取代理的所有任务结果，这里简化处理
    # 实际应该在TaskResultRepository中添加get_by_agent_id方法
    
    # 计算统计数据
    total_tasks_executed = len(all_results)
    successful_tasks = len([r for r in all_results if hasattr(r, 'status') and r.status == 'success'])
    failed_tasks = total_tasks_executed - successful_tasks
    
    # 计算平均执行时间
    execution_times = [r.duration for r in all_results if hasattr(r, 'duration') and r.duration]
    avg_execution_time = sum(execution_times) / len(execution_times) if execution_times else None
    
    # 计算运行时间百分比
    uptime_hours = agent.get_uptime_hours() or 0
    total_hours = days * 24
    uptime_percentage = min(1.0, uptime_hours / total_hours) if total_hours > 0 else 0.0
    
    # 最近24小时统计
    last_24h_cutoff = datetime.utcnow() - timedelta(hours=24)
    last_24h_results = [r for r in all_results if hasattr(r, 'execution_time') and r.execution_time >= last_24h_cutoff]
    last_24h_tasks = len(last_24h_results)
    last_24h_successful = len([r for r in last_24h_results if hasattr(r, 'status') and r.status == 'success'])
    last_24h_success_rate = (last_24h_successful / last_24h_tasks) if last_24h_tasks > 0 else 0.0
    
    # 获取资源警报数量
    recent_resources = await resource_repo.get_by_agent_id(agent_id, skip=0, limit=100)
    resource_alerts_count = len([r for r in recent_resources if r.is_critical() or r.is_warning()])
    
    return AgentStatistics(
        agent_id=agent_id,
        total_tasks_executed=total_tasks_executed,
        successful_tasks=successful_tasks,
        failed_tasks=failed_tasks,
        avg_execution_time=avg_execution_time,
        uptime_percentage=uptime_percentage,
        last_24h_tasks=last_24h_tasks,
        last_24h_success_rate=last_24h_success_rate,
        resource_alerts_count=resource_alerts_count
    )


@router.get("/{agent_id}/health", response_model=AgentHealthCheck, summary="获取代理健康状态")
async def get_agent_health(
    agent_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    session = Depends(get_db_session)
):
    """
    获取代理的健康检查信息
    """
    agent_repo = AgentRepository(session)
    resource_repo = AgentResourceRepository(session)
    
    # 验证代理存在
    agent = await agent_repo.get_by_id(agent_id)
    if not agent:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="代理不存在"
        )
    
    # 计算心跳时间差
    last_heartbeat_minutes_ago = None
    if agent.last_heartbeat:
        time_diff = datetime.utcnow() - agent.last_heartbeat
        last_heartbeat_minutes_ago = int(time_diff.total_seconds() / 60)
    
    # 检查各种状态
    is_online = agent.is_online()
    is_available = agent.is_available()
    resource_status = agent.get_resource_health_status()
    
    # 收集问题和建议
    issues = []
    recommendations = []
    
    if not is_online:
        issues.append("代理离线")
        recommendations.append("检查代理服务是否正常运行")
    
    if not agent.enabled:
        issues.append("代理已被禁用")
        recommendations.append("启用代理以恢复服务")
    
    if last_heartbeat_minutes_ago and last_heartbeat_minutes_ago > 5:
        issues.append(f"心跳超时 ({last_heartbeat_minutes_ago} 分钟前)")
        recommendations.append("检查网络连接和代理服务状态")
    
    if resource_status == "critical":
        issues.append("资源使用率过高")
        recommendations.append("检查系统资源使用情况，考虑升级硬件或减少负载")
    elif resource_status == "warning":
        issues.append("资源使用率较高")
        recommendations.append("监控资源使用情况，考虑优化或扩容")
    
    if agent.availability < 0.9:
        issues.append(f"可用率较低 ({agent.availability:.1%})")
        recommendations.append("检查代理稳定性和网络连接质量")
    
    if agent.success_rate < 0.9:
        issues.append(f"成功率较低 ({agent.success_rate:.1%})")
        recommendations.append("检查任务执行逻辑和目标服务可用性")
    
    return AgentHealthCheck(
        agent_id=agent_id,
        timestamp=datetime.utcnow(),
        is_online=is_online,
        is_available=is_available,
        resource_status=resource_status,
        last_heartbeat_minutes_ago=last_heartbeat_minutes_ago,
        issues=issues,
        recommendations=recommendations
    )