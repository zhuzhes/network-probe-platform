"""任务管理API路由"""

from typing import List, Optional, Dict, Any
from fastapi import APIRouter, Depends, HTTPException, status, Query
from pydantic import BaseModel
import uuid
from datetime import datetime, timedelta

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', '..'))

from shared.models.task import (
    Task, TaskResult, TaskCreate, TaskUpdate, TaskResponse, TaskResultResponse,
    TaskSummary, TaskStatistics, TaskBatch, TaskResultSummary,
    ProtocolType, TaskStatus, TaskResultStatus
)
from shared.models.user import User, UserRole
from management_platform.database.repositories import TaskRepository, TaskResultRepository, UserRepository
from ..dependencies import get_db_session, get_current_user, require_admin

router = APIRouter()


class TaskListResponse(BaseModel):
    """任务列表响应模型"""
    tasks: List[TaskResponse]
    total: int
    page: int
    size: int


class TaskResultListResponse(BaseModel):
    """任务结果列表响应模型"""
    results: List[TaskResultResponse]
    total: int
    page: int
    size: int


class TaskSummaryListResponse(BaseModel):
    """任务摘要列表响应模型"""
    tasks: List[TaskSummary]
    total: int
    page: int
    size: int


class TaskBatchResponse(BaseModel):
    """批量操作响应模型"""
    success_count: int
    failed_count: int
    message: str


@router.post("/", response_model=TaskResponse, summary="创建拨测任务")
async def create_task(
    task_data: TaskCreate,
    current_user: User = Depends(get_current_user),
    session = Depends(get_db_session)
):
    """
    创建新的拨测任务
    
    - **name**: 任务名称
    - **description**: 任务描述（可选）
    - **protocol**: 协议类型（icmp, tcp, udp, http, https）
    - **target**: 目标地址
    - **port**: 端口号（TCP/UDP/HTTP协议需要）
    - **parameters**: 协议特定参数（可选）
    - **frequency**: 执行频率（秒，10-86400）
    - **timeout**: 超时时间（秒，1-300）
    - **priority**: 优先级（默认0）
    - **preferred_location**: 首选地理位置（可选）
    - **preferred_isp**: 首选运营商（可选）
    """
    task_repo = TaskRepository(session)
    user_repo = UserRepository(session)
    
    # 检查用户余额
    if current_user.credits <= 0:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="账户余额不足，请先充值"
        )
    
    # 创建任务对象进行验证
    task = Task(
        user_id=current_user.id,
        name=task_data.name,
        description=task_data.description,
        protocol=task_data.protocol,
        target=task_data.target,
        port=task_data.port,
        parameters=task_data.parameters,
        frequency=task_data.frequency,
        timeout=task_data.timeout,
        priority=task_data.priority,
        preferred_location=task_data.preferred_location,
        preferred_isp=task_data.preferred_isp
    )
    
    # 验证任务配置
    validation_result = task.get_comprehensive_validation()
    if not validation_result['valid']:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"任务配置无效: {'; '.join(validation_result['errors'])}"
        )
    
    # 计算预估成本
    estimated_daily_cost = task.get_estimated_daily_cost()
    if estimated_daily_cost > current_user.credits:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"预估日成本({estimated_daily_cost:.2f}点)超过账户余额({current_user.credits:.2f}点)"
        )
    
    # 设置下次执行时间
    task.update_next_run()
    
    # 创建任务
    created_task = await task_repo.create({
        "user_id": task.user_id,
        "name": task.name,
        "description": task.description,
        "protocol": task.protocol,
        "target": task.target,
        "port": task.port,
        "parameters": task.parameters,
        "frequency": task.frequency,
        "timeout": task.timeout,
        "priority": task.priority,
        "status": task.status,
        "next_run": task.next_run,
        "preferred_location": task.preferred_location,
        "preferred_isp": task.preferred_isp
    })
    
    await task_repo.commit()
    
    return TaskResponse(
        id=created_task.id,
        user_id=created_task.user_id,
        name=created_task.name,
        description=created_task.description,
        protocol=created_task.protocol,
        target=created_task.target,
        port=created_task.port,
        parameters=created_task.parameters,
        frequency=created_task.frequency,
        timeout=created_task.timeout,
        priority=created_task.priority,
        status=created_task.status,
        next_run=created_task.next_run,
        preferred_location=created_task.preferred_location,
        preferred_isp=created_task.preferred_isp,
        created_at=created_task.created_at,
        updated_at=created_task.updated_at
    )


@router.get("/", response_model=TaskListResponse, summary="获取任务列表")
async def get_tasks(
    page: int = Query(1, ge=1, description="页码"),
    size: int = Query(20, ge=1, le=100, description="每页数量"),
    status: Optional[TaskStatus] = Query(None, description="任务状态过滤"),
    protocol: Optional[ProtocolType] = Query(None, description="协议类型过滤"),
    search: Optional[str] = Query(None, description="搜索关键词"),
    current_user: User = Depends(get_current_user),
    session = Depends(get_db_session)
):
    """
    获取任务列表
    
    - 普通用户只能查看自己的任务
    - 管理员可以查看所有任务
    - 支持按状态、协议类型过滤和关键词搜索
    """
    task_repo = TaskRepository(session)
    
    skip = (page - 1) * size
    user_id = None if current_user.role == UserRole.ADMIN else current_user.id
    
    if search:
        tasks = await task_repo.search(search, user_id=user_id, skip=skip, limit=size)
    elif status:
        if user_id:
            # 对于普通用户，需要同时过滤用户ID和状态
            all_tasks = await task_repo.get_by_user_id(user_id, skip=0, limit=10000)
            tasks = [t for t in all_tasks if t.status == status][skip:skip+size]
        else:
            tasks = await task_repo.get_by_status(status.value, skip=skip, limit=size)
    elif protocol:
        if user_id:
            # 对于普通用户，需要同时过滤用户ID和协议
            all_tasks = await task_repo.get_by_user_id(user_id, skip=0, limit=10000)
            tasks = [t for t in all_tasks if t.protocol == protocol][skip:skip+size]
        else:
            tasks = await task_repo.get_tasks_by_protocol(protocol.value, skip=skip, limit=size)
    else:
        if user_id:
            tasks = await task_repo.get_by_user_id(user_id, skip=skip, limit=size)
        else:
            tasks = await task_repo.get_all(skip=skip, limit=size)
    
    total = await task_repo.count(user_id=user_id)
    
    task_responses = [
        TaskResponse(
            id=task.id,
            user_id=task.user_id,
            name=task.name,
            description=task.description,
            protocol=task.protocol,
            target=task.target,
            port=task.port,
            parameters=task.parameters,
            frequency=task.frequency,
            timeout=task.timeout,
            priority=task.priority,
            status=task.status,
            next_run=task.next_run,
            preferred_location=task.preferred_location,
            preferred_isp=task.preferred_isp,
            created_at=task.created_at,
            updated_at=task.updated_at
        )
        for task in tasks
    ]
    
    return TaskListResponse(
        tasks=task_responses,
        total=total,
        page=page,
        size=size
    )


@router.get("/summary", response_model=TaskSummaryListResponse, summary="获取任务摘要")
async def get_task_summary(
    page: int = Query(1, ge=1, description="页码"),
    size: int = Query(20, ge=1, le=100, description="每页数量"),
    current_user: User = Depends(get_current_user),
    session = Depends(get_db_session)
):
    """
    获取任务摘要信息，包含统计数据
    """
    task_repo = TaskRepository(session)
    result_repo = TaskResultRepository(session)
    
    skip = (page - 1) * size
    user_id = None if current_user.role == UserRole.ADMIN else current_user.id
    
    if user_id:
        tasks = await task_repo.get_by_user_id(user_id, skip=skip, limit=size)
    else:
        tasks = await task_repo.get_all(skip=skip, limit=size)
    
    total = await task_repo.count(user_id=user_id)
    
    # 为每个任务计算摘要信息
    task_summaries = []
    for task in tasks:
        # 获取最近的执行结果
        recent_results = await result_repo.get_by_task_id(task.id, skip=0, limit=10)
        
        last_execution = None
        success_count = 0
        total_response_time = 0.0
        response_time_count = 0
        
        if recent_results:
            last_execution = recent_results[0].execution_time
            for result in recent_results:
                if result.status == TaskResultStatus.SUCCESS:
                    success_count += 1
                    if result.duration:
                        total_response_time += result.duration
                        response_time_count += 1
        
        success_rate = (success_count / len(recent_results)) if recent_results else None
        avg_response_time = (total_response_time / response_time_count) if response_time_count > 0 else None
        estimated_daily_cost = task.get_estimated_daily_cost()
        
        task_summaries.append(TaskSummary(
            id=task.id,
            name=task.name,
            protocol=task.protocol,
            target=task.target,
            status=task.status,
            frequency=task.frequency,
            last_execution=last_execution,
            success_rate=success_rate,
            avg_response_time=avg_response_time,
            estimated_daily_cost=estimated_daily_cost
        ))
    
    return TaskSummaryListResponse(
        tasks=task_summaries,
        total=total,
        page=page,
        size=size
    )


@router.get("/{task_id}", response_model=TaskResponse, summary="获取任务详情")
async def get_task(
    task_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    session = Depends(get_db_session)
):
    """
    获取任务详情
    
    - 普通用户只能查看自己的任务
    - 管理员可以查看任何任务
    """
    task_repo = TaskRepository(session)
    
    task = await task_repo.get_by_id(task_id)
    if not task:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="任务不存在"
        )
    
    # 检查权限
    if current_user.role != UserRole.ADMIN and task.user_id != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="无权访问此任务"
        )
    
    return TaskResponse(
        id=task.id,
        user_id=task.user_id,
        name=task.name,
        description=task.description,
        protocol=task.protocol,
        target=task.target,
        port=task.port,
        parameters=task.parameters,
        frequency=task.frequency,
        timeout=task.timeout,
        priority=task.priority,
        status=task.status,
        next_run=task.next_run,
        preferred_location=task.preferred_location,
        preferred_isp=task.preferred_isp,
        created_at=task.created_at,
        updated_at=task.updated_at
    )


@router.put("/{task_id}", response_model=TaskResponse, summary="更新任务")
async def update_task(
    task_id: uuid.UUID,
    task_data: TaskUpdate,
    current_user: User = Depends(get_current_user),
    session = Depends(get_db_session)
):
    """
    更新任务信息
    
    - 普通用户只能更新自己的任务
    - 管理员可以更新任何任务
    """
    task_repo = TaskRepository(session)
    
    task = await task_repo.get_by_id(task_id)
    if not task:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="任务不存在"
        )
    
    # 检查权限
    if current_user.role != UserRole.ADMIN and task.user_id != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="无权修改此任务"
        )
    
    # 准备更新数据
    update_data = {}
    
    if task_data.name is not None:
        update_data["name"] = task_data.name
    if task_data.description is not None:
        update_data["description"] = task_data.description
    if task_data.protocol is not None:
        update_data["protocol"] = task_data.protocol
    if task_data.target is not None:
        update_data["target"] = task_data.target
    if task_data.port is not None:
        update_data["port"] = task_data.port
    if task_data.parameters is not None:
        update_data["parameters"] = task_data.parameters
    if task_data.frequency is not None:
        update_data["frequency"] = task_data.frequency
        # 频率变化时重新计算下次执行时间
        if task.status == TaskStatus.ACTIVE:
            update_data["next_run"] = datetime.utcnow() + timedelta(seconds=task_data.frequency)
    if task_data.timeout is not None:
        update_data["timeout"] = task_data.timeout
    if task_data.priority is not None:
        update_data["priority"] = task_data.priority
    if task_data.preferred_location is not None:
        update_data["preferred_location"] = task_data.preferred_location
    if task_data.preferred_isp is not None:
        update_data["preferred_isp"] = task_data.preferred_isp
    
    if update_data:
        # 创建临时任务对象进行验证
        temp_task = Task(
            user_id=task.user_id,
            name=update_data.get("name", task.name),
            description=update_data.get("description", task.description),
            protocol=update_data.get("protocol", task.protocol),
            target=update_data.get("target", task.target),
            port=update_data.get("port", task.port),
            parameters=update_data.get("parameters", task.parameters),
            frequency=update_data.get("frequency", task.frequency),
            timeout=update_data.get("timeout", task.timeout),
            priority=update_data.get("priority", task.priority),
            preferred_location=update_data.get("preferred_location", task.preferred_location),
            preferred_isp=update_data.get("preferred_isp", task.preferred_isp)
        )
        
        # 验证更新后的配置
        validation_result = temp_task.get_comprehensive_validation()
        if not validation_result['valid']:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"任务配置无效: {'; '.join(validation_result['errors'])}"
            )
        
        updated_task = await task_repo.update(task_id, update_data)
        await task_repo.commit()
        
        return TaskResponse(
            id=updated_task.id,
            user_id=updated_task.user_id,
            name=updated_task.name,
            description=updated_task.description,
            protocol=updated_task.protocol,
            target=updated_task.target,
            port=updated_task.port,
            parameters=updated_task.parameters,
            frequency=updated_task.frequency,
            timeout=updated_task.timeout,
            priority=updated_task.priority,
            status=updated_task.status,
            next_run=updated_task.next_run,
            preferred_location=updated_task.preferred_location,
            preferred_isp=updated_task.preferred_isp,
            created_at=updated_task.created_at,
            updated_at=updated_task.updated_at
        )
    
    # 没有更新数据，返回原任务
    return TaskResponse(
        id=task.id,
        user_id=task.user_id,
        name=task.name,
        description=task.description,
        protocol=task.protocol,
        target=task.target,
        port=task.port,
        parameters=task.parameters,
        frequency=task.frequency,
        timeout=task.timeout,
        priority=task.priority,
        status=task.status,
        next_run=task.next_run,
        preferred_location=task.preferred_location,
        preferred_isp=task.preferred_isp,
        created_at=task.created_at,
        updated_at=task.updated_at
    )


@router.delete("/{task_id}", summary="删除任务")
async def delete_task(
    task_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    session = Depends(get_db_session)
):
    """
    删除任务
    
    - 普通用户只能删除自己的任务
    - 管理员可以删除任何任务
    """
    task_repo = TaskRepository(session)
    
    task = await task_repo.get_by_id(task_id)
    if not task:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="任务不存在"
        )
    
    # 检查权限
    if current_user.role != UserRole.ADMIN and task.user_id != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="无权删除此任务"
        )
    
    await task_repo.delete(task_id)
    await task_repo.commit()
    
    return {"message": "任务删除成功"}


@router.post("/{task_id}/pause", response_model=TaskResponse, summary="暂停任务")
async def pause_task(
    task_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    session = Depends(get_db_session)
):
    """
    暂停任务执行
    """
    task_repo = TaskRepository(session)
    
    task = await task_repo.get_by_id(task_id)
    if not task:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="任务不存在"
        )
    
    # 检查权限
    if current_user.role != UserRole.ADMIN and task.user_id != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="无权操作此任务"
        )
    
    if task.status != TaskStatus.ACTIVE:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="只能暂停活跃状态的任务"
        )
    
    updated_task = await task_repo.update(task_id, {
        "status": TaskStatus.PAUSED,
        "next_run": None
    })
    await task_repo.commit()
    
    return TaskResponse(
        id=updated_task.id,
        user_id=updated_task.user_id,
        name=updated_task.name,
        description=updated_task.description,
        protocol=updated_task.protocol,
        target=updated_task.target,
        port=updated_task.port,
        parameters=updated_task.parameters,
        frequency=updated_task.frequency,
        timeout=updated_task.timeout,
        priority=updated_task.priority,
        status=updated_task.status,
        next_run=updated_task.next_run,
        preferred_location=updated_task.preferred_location,
        preferred_isp=updated_task.preferred_isp,
        created_at=updated_task.created_at,
        updated_at=updated_task.updated_at
    )


@router.post("/{task_id}/resume", response_model=TaskResponse, summary="恢复任务")
async def resume_task(
    task_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    session = Depends(get_db_session)
):
    """
    恢复任务执行
    """
    task_repo = TaskRepository(session)
    
    task = await task_repo.get_by_id(task_id)
    if not task:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="任务不存在"
        )
    
    # 检查权限
    if current_user.role != UserRole.ADMIN and task.user_id != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="无权操作此任务"
        )
    
    if task.status != TaskStatus.PAUSED:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="只能恢复暂停状态的任务"
        )
    
    # 检查用户余额
    if current_user.credits <= 0:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="账户余额不足，请先充值"
        )
    
    next_run = datetime.utcnow() + timedelta(seconds=task.frequency)
    updated_task = await task_repo.update(task_id, {
        "status": TaskStatus.ACTIVE,
        "next_run": next_run
    })
    await task_repo.commit()
    
    return TaskResponse(
        id=updated_task.id,
        user_id=updated_task.user_id,
        name=updated_task.name,
        description=updated_task.description,
        protocol=updated_task.protocol,
        target=updated_task.target,
        port=updated_task.port,
        parameters=updated_task.parameters,
        frequency=updated_task.frequency,
        timeout=updated_task.timeout,
        priority=updated_task.priority,
        status=updated_task.status,
        next_run=updated_task.next_run,
        preferred_location=updated_task.preferred_location,
        preferred_isp=updated_task.preferred_isp,
        created_at=updated_task.created_at,
        updated_at=updated_task.updated_at
    )


@router.post("/batch", response_model=TaskBatchResponse, summary="批量操作任务")
async def batch_operation(
    batch_data: TaskBatch,
    current_user: User = Depends(get_current_user),
    session = Depends(get_db_session)
):
    """
    批量操作任务（暂停、恢复、删除）
    """
    task_repo = TaskRepository(session)
    
    # 验证所有任务的权限
    tasks = []
    for task_id in batch_data.task_ids:
        task = await task_repo.get_by_id(task_id)
        if not task:
            continue
        
        # 检查权限
        if current_user.role != UserRole.ADMIN and task.user_id != current_user.id:
            continue
        
        tasks.append(task)
    
    if not tasks:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="没有找到可操作的任务"
        )
    
    success_count = 0
    failed_count = 0
    
    if batch_data.action == "pause":
        success_count = await task_repo.pause_tasks_batch([task.id for task in tasks])
        failed_count = len(tasks) - success_count
        message = f"成功暂停 {success_count} 个任务"
    
    elif batch_data.action == "resume":
        # 检查用户余额
        if current_user.credits <= 0:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="账户余额不足，请先充值"
            )
        
        success_count = await task_repo.resume_tasks_batch([task.id for task in tasks])
        failed_count = len(tasks) - success_count
        message = f"成功恢复 {success_count} 个任务"
    
    elif batch_data.action == "delete":
        for task in tasks:
            try:
                await task_repo.delete(task.id)
                success_count += 1
            except Exception:
                failed_count += 1
        message = f"成功删除 {success_count} 个任务"
    
    else:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="不支持的操作类型"
        )
    
    await task_repo.commit()
    
    return TaskBatchResponse(
        success_count=success_count,
        failed_count=failed_count,
        message=message
    )


# 任务结果相关端点

@router.get("/{task_id}/results", response_model=TaskResultListResponse, summary="获取任务结果")
async def get_task_results(
    task_id: uuid.UUID,
    page: int = Query(1, ge=1, description="页码"),
    size: int = Query(20, ge=1, le=100, description="每页数量"),
    status: Optional[TaskResultStatus] = Query(None, description="结果状态过滤"),
    start_time: Optional[datetime] = Query(None, description="开始时间"),
    end_time: Optional[datetime] = Query(None, description="结束时间"),
    current_user: User = Depends(get_current_user),
    session = Depends(get_db_session)
):
    """
    获取任务的执行结果列表
    
    - 支持按状态和时间范围过滤
    """
    task_repo = TaskRepository(session)
    result_repo = TaskResultRepository(session)
    
    # 验证任务存在和权限
    task = await task_repo.get_by_id(task_id)
    if not task:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="任务不存在"
        )
    
    if current_user.role != UserRole.ADMIN and task.user_id != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="无权访问此任务的结果"
        )
    
    skip = (page - 1) * size
    
    # 获取结果（这里简化实现，实际应该在repository中支持更复杂的过滤）
    results = await result_repo.get_by_task_id(task_id, skip=skip, limit=size)
    
    # 应用过滤器
    if status:
        results = [r for r in results if r.status == status]
    
    if start_time:
        results = [r for r in results if r.execution_time >= start_time]
    
    if end_time:
        results = [r for r in results if r.execution_time <= end_time]
    
    # 重新分页
    results = results[skip:skip+size] if skip > 0 else results[:size]
    
    # 获取总数（简化实现）
    all_results = await result_repo.get_by_task_id(task_id, skip=0, limit=10000)
    total = len(all_results)
    
    result_responses = [
        TaskResultResponse(
            id=result.id,
            task_id=result.task_id,
            agent_id=result.agent_id,
            execution_time=result.execution_time,
            duration=result.duration,
            status=result.status,
            error_message=result.error_message,
            metrics=result.metrics,
            raw_data=result.raw_data,
            created_at=result.created_at,
            updated_at=result.updated_at
        )
        for result in results
    ]
    
    return TaskResultListResponse(
        results=result_responses,
        total=total,
        page=page,
        size=size
    )


@router.get("/{task_id}/statistics", response_model=TaskStatistics, summary="获取任务统计")
async def get_task_statistics(
    task_id: uuid.UUID,
    days: int = Query(30, ge=1, le=365, description="统计天数"),
    current_user: User = Depends(get_current_user),
    session = Depends(get_db_session)
):
    """
    获取任务的统计信息
    """
    task_repo = TaskRepository(session)
    result_repo = TaskResultRepository(session)
    
    # 验证任务存在和权限
    task = await task_repo.get_by_id(task_id)
    if not task:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="任务不存在"
        )
    
    if current_user.role != UserRole.ADMIN and task.user_id != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="无权访问此任务的统计信息"
        )
    
    # 获取指定天数内的结果
    cutoff_date = datetime.utcnow() - timedelta(days=days)
    all_results = await result_repo.get_by_task_id(task_id, skip=0, limit=10000)
    
    # 过滤时间范围
    recent_results = [r for r in all_results if r.execution_time >= cutoff_date]
    last_24h_results = [r for r in all_results if r.execution_time >= datetime.utcnow() - timedelta(hours=24)]
    
    # 计算统计数据
    total_executions = len(recent_results)
    successful_executions = len([r for r in recent_results if r.status == TaskResultStatus.SUCCESS])
    failed_executions = len([r for r in recent_results if r.status == TaskResultStatus.ERROR])
    timeout_executions = len([r for r in recent_results if r.status == TaskResultStatus.TIMEOUT])
    
    success_rate = (successful_executions / total_executions) if total_executions > 0 else 0.0
    
    # 计算响应时间统计
    response_times = [r.duration for r in recent_results if r.duration and r.status == TaskResultStatus.SUCCESS]
    avg_response_time = sum(response_times) / len(response_times) if response_times else None
    min_response_time = min(response_times) if response_times else None
    max_response_time = max(response_times) if response_times else None
    
    # 最近24小时统计
    last_24h_executions = len(last_24h_results)
    last_24h_successful = len([r for r in last_24h_results if r.status == TaskResultStatus.SUCCESS])
    last_24h_success_rate = (last_24h_successful / last_24h_executions) if last_24h_executions > 0 else 0.0
    
    return TaskStatistics(
        task_id=task_id,
        total_executions=total_executions,
        successful_executions=successful_executions,
        failed_executions=failed_executions,
        timeout_executions=timeout_executions,
        success_rate=success_rate,
        avg_response_time=avg_response_time,
        min_response_time=min_response_time,
        max_response_time=max_response_time,
        last_24h_executions=last_24h_executions,
        last_24h_success_rate=last_24h_success_rate
    )


@router.get("/results", response_model=List[TaskResultSummary], summary="获取所有任务结果摘要")
async def get_all_task_results(
    page: int = Query(1, ge=1, description="页码"),
    size: int = Query(50, ge=1, le=200, description="每页数量"),
    status: Optional[TaskResultStatus] = Query(None, description="结果状态过滤"),
    start_time: Optional[datetime] = Query(None, description="开始时间"),
    end_time: Optional[datetime] = Query(None, description="结束时间"),
    current_user: User = Depends(get_current_user),
    session = Depends(get_db_session)
):
    """
    获取所有任务结果的摘要信息
    
    - 普通用户只能查看自己任务的结果
    - 管理员可以查看所有结果
    """
    task_repo = TaskRepository(session)
    result_repo = TaskResultRepository(session)
    
    skip = (page - 1) * size
    
    # 获取用户的任务列表
    if current_user.role == UserRole.ADMIN:
        user_tasks = await task_repo.get_all(skip=0, limit=10000)
    else:
        user_tasks = await task_repo.get_by_user_id(current_user.id, skip=0, limit=10000)
    
    task_dict = {task.id: task for task in user_tasks}
    
    # 获取所有结果并过滤
    all_results = []
    for task in user_tasks:
        task_results = await result_repo.get_by_task_id(task.id, skip=0, limit=1000)
        all_results.extend(task_results)
    
    # 应用过滤器
    if status:
        all_results = [r for r in all_results if r.status == status]
    
    if start_time:
        all_results = [r for r in all_results if r.execution_time >= start_time]
    
    if end_time:
        all_results = [r for r in all_results if r.execution_time <= end_time]
    
    # 按时间排序
    all_results.sort(key=lambda x: x.execution_time, reverse=True)
    
    # 分页
    results = all_results[skip:skip+size]
    
    # 构建摘要响应
    result_summaries = []
    for result in results:
        task = task_dict.get(result.task_id)
        task_name = task.name if task else "未知任务"
        
        # 这里简化了agent_name的获取，实际应该查询agent表
        agent_name = f"Agent-{str(result.agent_id)[:8]}" if result.agent_id else None
        
        result_summaries.append(TaskResultSummary(
            id=result.id,
            task_name=task_name,
            agent_name=agent_name,
            execution_time=result.execution_time,
            status=result.status,
            response_time=result.duration,
            performance_grade=result.get_performance_grade(),
            error_summary=result.get_error_summary()
        ))
    
    return result_summaries