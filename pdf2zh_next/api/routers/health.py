"""健康检查相关路由"""

import time
from typing import Any

from fastapi import APIRouter
from fastapi import HTTPException

from ..dependencies import get_request_id
from ..exceptions import InternalServerException
from ..models import APIResponse
from ..models import HealthStatus
from ..services import system_service

router = APIRouter(prefix="/health", tags=["health"])


@router.get("/", response_model=APIResponse[HealthStatus])
async def health_check():
    """基础健康检查"""
    try:
        health_status = await system_service.get_health_status()

        return APIResponse(
            success=True,
            data=health_status,
            timestamp=time.time(),
            request_id=get_request_id(),
        )
    except Exception as exc:
        if isinstance(exc, InternalServerException):
            raise
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@router.get("/ready", response_model=APIResponse[dict[str, Any]])
async def readiness_check():
    """就绪检查 - 检查服务是否准备好接收请求"""
    try:
        # 检查关键依赖是否就绪
        health_status = await system_service.get_health_status()

        # 如果任何关键依赖不健康，则服务未就绪
        if health_status.status != "healthy":
            return APIResponse(
                success=False,
                error={
                    "code": "SERVICE_NOT_READY",
                    "message": "服务未就绪",
                    "details": {"status": health_status.status},
                },
                timestamp=time.time(),
                request_id=get_request_id(),
            )

        return APIResponse(
            success=True,
            data={"status": "ready", "timestamp": time.time()},
            timestamp=time.time(),
            request_id=get_request_id(),
        )
    except Exception as e:
        return APIResponse(
            success=False,
            error={
                "code": "READINESS_CHECK_FAILED",
                "message": "就绪检查失败",
                "details": {"error": str(e)},
            },
            timestamp=time.time(),
            request_id=get_request_id(),
        )


@router.get("/live", response_model=APIResponse[dict[str, Any]])
async def liveness_check():
    """存活检查 - 检查服务是否存活"""
    try:
        # 基础存活检查 - 只需服务能响应请求即可
        return APIResponse(
            success=True,
            data={
                "status": "alive",
                "timestamp": time.time(),
                "uptime_seconds": (time.time() - system_service.start_time.timestamp()),
            },
            timestamp=time.time(),
            request_id=get_request_id(),
        )
    except Exception as e:
        return APIResponse(
            success=False,
            error={
                "code": "LIVENESS_CHECK_FAILED",
                "message": "存活检查失败",
                "details": {"error": str(e)},
            },
            timestamp=time.time(),
            request_id=get_request_id(),
        )


@router.get("/error-codes", response_model=APIResponse[dict[str, Any]])
async def get_error_codes():
    """获取错误码定义"""
    try:
        error_codes = {
            "INVALID_FILE_FORMAT": {
                "code": "INVALID_FILE_FORMAT",
                "message": "不支持的文件格式",
                "description": "上传的文件格式不受支持",
                "retryable": False,
                "http_status": 400,
            },
            "TRANSLATION_ENGINE_ERROR": {
                "code": "TRANSLATION_ENGINE_ERROR",
                "message": "翻译引擎错误",
                "description": "翻译引擎处理过程中发生错误",
                "retryable": True,
                "http_status": 502,
            },
            "TIMEOUT": {
                "code": "TIMEOUT",
                "message": "请求超时",
                "description": "请求处理时间超过最大允许时间",
                "retryable": True,
                "http_status": 504,
            },
            "RESOURCE_EXHAUSTED": {
                "code": "RESOURCE_EXHAUSTED",
                "message": "资源耗尽",
                "description": "系统资源（内存、磁盘等）已耗尽",
                "retryable": True,
                "http_status": 429,
            },
            "INTERNAL_ERROR": {
                "code": "INTERNAL_ERROR",
                "message": "内部错误",
                "description": "服务器内部发生未预期的错误",
                "retryable": True,
                "http_status": 500,
            },
            "TASK_NOT_FOUND": {
                "code": "TASK_NOT_FOUND",
                "message": "任务不存在",
                "description": "请求的任务ID不存在",
                "retryable": False,
                "http_status": 404,
            },
            "INVALID_PARAMETERS": {
                "code": "INVALID_PARAMETERS",
                "message": "参数无效",
                "description": "请求参数格式或值无效",
                "retryable": False,
                "http_status": 400,
            },
            "UNAUTHORIZED": {
                "code": "UNAUTHORIZED",
                "message": "未授权",
                "description": "请求缺少有效的认证凭据",
                "retryable": False,
                "http_status": 401,
            },
            "FORBIDDEN": {
                "code": "FORBIDDEN",
                "message": "权限不足",
                "description": "用户没有执行此操作的权限",
                "retryable": False,
                "http_status": 403,
            },
            "RATE_LIMIT_EXCEEDED": {
                "code": "RATE_LIMIT_EXCEEDED",
                "message": "请求频率超限",
                "description": "请求频率超过允许的限制",
                "retryable": True,
                "http_status": 429,
            },
        }

        return APIResponse(
            success=True,
            data={"error_codes": error_codes},
            timestamp=time.time(),
            request_id=get_request_id(),
        )
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@router.get("/dependencies", response_model=APIResponse[dict[str, Any]])
async def get_dependency_status():
    """获取依赖服务状态"""
    try:
        health_status = await system_service.get_health_status()

        return APIResponse(
            success=True,
            data={"dependencies": health_status.dependencies},
            timestamp=time.time(),
            request_id=get_request_id(),
        )
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@router.get("/metrics", response_model=APIResponse[dict[str, Any]])
async def get_health_metrics():
    """获取健康指标"""
    try:
        health_status = await system_service.get_health_status()

        return APIResponse(
            success=True,
            data=health_status.performance_metrics,
            timestamp=time.time(),
            request_id=get_request_id(),
        )
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc
