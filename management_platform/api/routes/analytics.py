"""数据分析API路由"""

from typing import List, Optional, Dict, Any
from fastapi import APIRouter, Depends, HTTPException, status, Query, Response
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
import uuid
import csv
import json
import io
from datetime import datetime, timedelta
from sqlalchemy import func, and_, or_

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', '..'))

from shared.models.task import Task, TaskResult, ProtocolType, TaskStatus, TaskResultStatus
from shared.models.agent import Agent
from shared.models.user import User, UserRole
from management_platform.database.repositories import TaskRepository, TaskResultRepository, AgentRepository
from ..dependencies import get_db_session, get_current_user, require_admin

router = APIRouter()


class TaskResultsResponse(BaseModel):
    """拨测结果响应模型"""
    results: List[Dict[str, Any]]
    total: int
    page: int
    size: int
    filters: Dict[str, Any]


class StatisticsResponse(BaseModel):
    """统计数据响应模型"""
    summary: Dict[str, Any]
    task_statistics: Dict[str, Any]
    agent_statistics: Dict[str, Any]
    protocol_statistics: Dict[str, Any]
    time_range: Dict[str, str]


class ExportRequest(BaseModel):
    """数据导出请求模型"""
    format: str = Field(..., description="导出格式: csv, json")
    task_ids: Optional[List[str]] = Field(None, description="任务ID列表，为空则导出所有")
    start_time: Optional[datetime] = Field(None, description="开始时间")
    end_time: Optional[datetime] = Field(None, description="结束时间")
    protocols: Optional[List[ProtocolType]] = Field(None, description="协议类型过滤")
    status_filter: Optional[List[TaskResultStatus]] = Field(None, description="结果状态过滤")


@router.get("/results", response_model=TaskResultsResponse, summary="获取拨测结果")
async def get_results(
    page: int = Query(1, ge=1, description="页码"),
    size: int = Query(20, ge=1, le=100, description="每页数量"),
    task_id: Optional[str] = Query(None, description="任务ID过滤"),
    agent_id: Optional[str] = Query(None, description="代理ID过滤"),
    protocol: Optional[ProtocolType] = Query(None, description="协议类型过滤"),
    status: Optional[TaskResultStatus] = Query(None, description="结果状态过滤"),
    start_time: Optional[datetime] = Query(None, description="开始时间"),
    end_time: Optional[datetime] = Query(None, description="结束时间"),
    current_user: User = Depends(get_current_user),
    session = Depends(get_db_session)
):
    """
    获取拨测结果数据
    
    支持多种过滤条件：
    - 任务ID
    - 代理ID
    - 协议类型
    - 结果状态
    - 时间范围
    
    企业用户只能查看自己的数据，管理员可以查看所有数据
    """
    try:
        task_repo = TaskRepository(session)
        result_repo = TaskResultRepository(session)
        
        # 构建查询条件
        filters = {}
        query_conditions = []
        
        # 用户权限过滤
        if current_user.role != UserRole.ADMIN:
            # 企业用户只能查看自己的任务结果
            user_task_ids = await task_repo.get_user_task_ids(current_user.id)
            if not user_task_ids:
                return TaskResultsResponse(
                    results=[],
                    total=0,
                    page=page,
                    size=size,
                    filters=filters
                )
            query_conditions.append(TaskResult.task_id.in_(user_task_ids))
        
        # 任务ID过滤
        if task_id:
            try:
                task_uuid = uuid.UUID(task_id)
                query_conditions.append(TaskResult.task_id == task_uuid)
                filters["task_id"] = task_id
            except ValueError:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="无效的任务ID格式"
                )
        
        # 代理ID过滤
        if agent_id:
            try:
                agent_uuid = uuid.UUID(agent_id)
                query_conditions.append(TaskResult.agent_id == agent_uuid)
                filters["agent_id"] = agent_id
            except ValueError:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="无效的代理ID格式"
                )
        
        # 协议类型过滤
        if protocol:
            # 需要通过任务表关联查询
            query_conditions.append(Task.protocol == protocol)
            filters["protocol"] = protocol
        
        # 结果状态过滤
        if status:
            query_conditions.append(TaskResult.status == status)
            filters["status"] = status
        
        # 时间范围过滤
        if start_time:
            query_conditions.append(TaskResult.execution_time >= start_time)
            filters["start_time"] = start_time.isoformat()
        
        if end_time:
            query_conditions.append(TaskResult.execution_time <= end_time)
            filters["end_time"] = end_time.isoformat()
        
        # 获取结果数据
        results, total = await result_repo.get_results_with_filters(
            conditions=query_conditions,
            skip=(page - 1) * size,
            limit=size
        )
        
        # 转换为响应格式
        result_data = []
        for result in results:
            result_dict = {
                "id": str(result.id),
                "task_id": str(result.task_id),
                "agent_id": str(result.agent_id),
                "execution_time": result.execution_time.isoformat(),
                "duration": result.duration,
                "status": result.status,
                "error_message": result.error_message,
                "metrics": result.metrics,
                "raw_data": result.raw_data
            }
            
            # 如果有关联的任务信息，添加任务详情
            if hasattr(result, 'task') and result.task:
                result_dict["task_info"] = {
                    "name": result.task.name,
                    "protocol": result.task.protocol,
                    "target": result.task.target,
                    "port": result.task.port
                }
            
            # 如果有关联的代理信息，添加代理详情
            if hasattr(result, 'agent') and result.agent:
                result_dict["agent_info"] = {
                    "name": result.agent.name,
                    "location": result.agent.location,
                    "isp": result.agent.isp
                }
            
            result_data.append(result_dict)
        
        return TaskResultsResponse(
            results=result_data,
            total=total,
            page=page,
            size=size,
            filters=filters
        )
        
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"获取拨测结果失败: {str(e)}"
        )


@router.get("/statistics", response_model=StatisticsResponse, summary="获取统计数据")
async def get_statistics(
    start_time: Optional[datetime] = Query(None, description="统计开始时间"),
    end_time: Optional[datetime] = Query(None, description="统计结束时间"),
    current_user: User = Depends(get_current_user),
    session = Depends(get_db_session)
):
    """
    获取系统统计数据
    
    包括：
    - 总体统计（任务数量、执行次数、成功率等）
    - 任务统计（按状态、协议分组）
    - 代理统计（在线状态、性能指标）
    - 协议统计（各协议使用情况和性能）
    
    企业用户只能查看自己的统计数据，管理员可以查看全局统计
    """
    try:
        task_repo = TaskRepository(session)
        result_repo = TaskResultRepository(session)
        agent_repo = AgentRepository(session)
        
        # 设置默认时间范围（最近30天）
        if not end_time:
            end_time = datetime.utcnow()
        if not start_time:
            start_time = end_time - timedelta(days=30)
        
        # 用户权限过滤
        user_filter = None
        if current_user.role != UserRole.ADMIN:
            user_filter = current_user.id
        
        # 获取总体统计
        summary_stats = await result_repo.get_summary_statistics(
            start_time=start_time,
            end_time=end_time,
            user_id=user_filter
        )
        
        # 获取任务统计
        task_stats = await task_repo.get_task_statistics(
            start_time=start_time,
            end_time=end_time,
            user_id=user_filter
        )
        
        # 获取代理统计（仅管理员可见）
        agent_stats = {}
        if current_user.role == UserRole.ADMIN:
            agent_stats = await agent_repo.get_agent_statistics()
        
        # 获取协议统计
        protocol_stats = await result_repo.get_protocol_statistics(
            start_time=start_time,
            end_time=end_time,
            user_id=user_filter
        )
        
        return StatisticsResponse(
            summary=summary_stats,
            task_statistics=task_stats,
            agent_statistics=agent_stats,
            protocol_statistics=protocol_stats,
            time_range={
                "start_time": start_time.isoformat(),
                "end_time": end_time.isoformat()
            }
        )
        
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"获取统计数据失败: {str(e)}"
        )


@router.post("/export", summary="导出数据")
async def export_data(
    export_request: ExportRequest,
    current_user: User = Depends(get_current_user),
    session = Depends(get_db_session)
):
    """
    导出拨测数据
    
    支持格式：
    - CSV: 表格格式，适合Excel打开
    - JSON: 结构化数据，适合程序处理
    
    支持过滤条件：
    - 任务ID列表
    - 时间范围
    - 协议类型
    - 结果状态
    
    企业用户只能导出自己的数据
    """
    try:
        if export_request.format not in ["csv", "json"]:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="不支持的导出格式，仅支持 csv 和 json"
            )
        
        task_repo = TaskRepository(session)
        result_repo = TaskResultRepository(session)
        
        # 构建查询条件
        query_conditions = []
        
        # 用户权限过滤
        if current_user.role != UserRole.ADMIN:
            user_task_ids = await task_repo.get_user_task_ids(current_user.id)
            if not user_task_ids:
                # 用户没有任务，返回空数据
                if export_request.format == "csv":
                    output = io.StringIO()
                    writer = csv.writer(output)
                    writer.writerow(["message"])
                    writer.writerow(["没有可导出的数据"])
                    content = output.getvalue()
                    output.close()
                    
                    return Response(
                        content=content,
                        media_type="text/csv",
                        headers={"Content-Disposition": "attachment; filename=export_empty.csv"}
                    )
                else:
                    return Response(
                        content=json.dumps({"message": "没有可导出的数据", "data": []}),
                        media_type="application/json",
                        headers={"Content-Disposition": "attachment; filename=export_empty.json"}
                    )
            
            query_conditions.append(TaskResult.task_id.in_(user_task_ids))
        
        # 任务ID过滤
        if export_request.task_ids:
            try:
                task_uuids = [uuid.UUID(tid) for tid in export_request.task_ids]
                query_conditions.append(TaskResult.task_id.in_(task_uuids))
            except ValueError:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="无效的任务ID格式"
                )
        
        # 时间范围过滤
        if export_request.start_time:
            query_conditions.append(TaskResult.execution_time >= export_request.start_time)
        
        if export_request.end_time:
            query_conditions.append(TaskResult.execution_time <= export_request.end_time)
        
        # 协议类型过滤
        if export_request.protocols:
            query_conditions.append(Task.protocol.in_(export_request.protocols))
        
        # 结果状态过滤
        if export_request.status_filter:
            query_conditions.append(TaskResult.status.in_(export_request.status_filter))
        
        # 获取导出数据（不分页，获取所有符合条件的数据）
        results, total = await result_repo.get_results_with_filters(
            conditions=query_conditions,
            skip=0,
            limit=None  # 不限制数量
        )
        
        # 生成文件名
        timestamp = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
        filename = f"probe_results_{timestamp}.{export_request.format}"
        
        if export_request.format == "csv":
            # CSV格式导出
            output = io.StringIO()
            writer = csv.writer(output)
            
            # 写入表头
            headers = [
                "结果ID", "任务ID", "任务名称", "协议", "目标", "端口",
                "代理ID", "代理名称", "代理位置", "代理ISP",
                "执行时间", "持续时间(ms)", "状态", "错误信息", "指标数据"
            ]
            writer.writerow(headers)
            
            # 写入数据行
            for result in results:
                row = [
                    str(result.id),
                    str(result.task_id),
                    result.task.name if hasattr(result, 'task') and result.task else "",
                    result.task.protocol if hasattr(result, 'task') and result.task else "",
                    result.task.target if hasattr(result, 'task') and result.task else "",
                    result.task.port if hasattr(result, 'task') and result.task else "",
                    str(result.agent_id),
                    result.agent.name if hasattr(result, 'agent') and result.agent else "",
                    json.dumps(result.agent.location) if hasattr(result, 'agent') and result.agent and result.agent.location else "",
                    result.agent.isp if hasattr(result, 'agent') and result.agent else "",
                    result.execution_time.isoformat(),
                    result.duration,
                    result.status,
                    result.error_message or "",
                    json.dumps(result.metrics) if result.metrics else ""
                ]
                writer.writerow(row)
            
            content = output.getvalue()
            output.close()
            
            return Response(
                content=content,
                media_type="text/csv",
                headers={"Content-Disposition": f"attachment; filename={filename}"}
            )
        
        else:
            # JSON格式导出
            export_data = {
                "export_info": {
                    "timestamp": datetime.utcnow().isoformat(),
                    "user_id": str(current_user.id),
                    "username": current_user.username,
                    "total_records": total,
                    "filters": {
                        "task_ids": export_request.task_ids,
                        "start_time": export_request.start_time.isoformat() if export_request.start_time else None,
                        "end_time": export_request.end_time.isoformat() if export_request.end_time else None,
                        "protocols": export_request.protocols,
                        "status_filter": export_request.status_filter
                    }
                },
                "data": []
            }
            
            for result in results:
                result_dict = {
                    "id": str(result.id),
                    "task_id": str(result.task_id),
                    "agent_id": str(result.agent_id),
                    "execution_time": result.execution_time.isoformat(),
                    "duration": result.duration,
                    "status": result.status,
                    "error_message": result.error_message,
                    "metrics": result.metrics,
                    "raw_data": result.raw_data
                }
                
                # 添加任务信息
                if hasattr(result, 'task') and result.task:
                    result_dict["task_info"] = {
                        "name": result.task.name,
                        "description": result.task.description,
                        "protocol": result.task.protocol,
                        "target": result.task.target,
                        "port": result.task.port,
                        "parameters": result.task.parameters
                    }
                
                # 添加代理信息
                if hasattr(result, 'agent') and result.agent:
                    result_dict["agent_info"] = {
                        "name": result.agent.name,
                        "ip_address": result.agent.ip_address,
                        "location": result.agent.location,
                        "isp": result.agent.isp
                    }
                
                export_data["data"].append(result_dict)
            
            content = json.dumps(export_data, ensure_ascii=False, indent=2)
            
            return Response(
                content=content,
                media_type="application/json",
                headers={"Content-Disposition": f"attachment; filename={filename}"}
            )
        
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"导出数据失败: {str(e)}"
        )


@router.get("/export", summary="导出数据（GET方式）")
async def export_data_get(
    format: str = Query("csv", description="导出格式: csv, json"),
    task_ids: Optional[str] = Query(None, description="任务ID列表，逗号分隔"),
    start_time: Optional[datetime] = Query(None, description="开始时间"),
    end_time: Optional[datetime] = Query(None, description="结束时间"),
    protocols: Optional[str] = Query(None, description="协议类型，逗号分隔"),
    status_filter: Optional[str] = Query(None, description="结果状态，逗号分隔"),
    current_user: User = Depends(get_current_user),
    session = Depends(get_db_session)
):
    """
    导出数据的GET方式接口
    
    为了方便浏览器直接访问下载，提供GET方式的导出接口
    参数通过查询字符串传递
    """
    # 转换参数格式
    export_request = ExportRequest(format=format)
    
    if task_ids:
        export_request.task_ids = [tid.strip() for tid in task_ids.split(",") if tid.strip()]
    
    if start_time:
        export_request.start_time = start_time
    
    if end_time:
        export_request.end_time = end_time
    
    if protocols:
        try:
            export_request.protocols = [ProtocolType(p.strip()) for p in protocols.split(",") if p.strip()]
        except ValueError as e:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"无效的协议类型: {str(e)}"
            )
    
    if status_filter:
        try:
            export_request.status_filter = [TaskResultStatus(s.strip()) for s in status_filter.split(",") if s.strip()]
        except ValueError as e:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"无效的状态类型: {str(e)}"
            )
    
    # 调用POST方式的导出函数
    return await export_data(export_request, current_user, session)