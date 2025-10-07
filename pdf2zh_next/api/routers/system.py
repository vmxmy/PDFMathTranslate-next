"""系统管理相关路由"""

import logging
import time
from typing import Annotated
from typing import Any

from fastapi import APIRouter
from fastapi import Depends
from fastapi import HTTPException

from ..dependencies import get_request_id
from ..dependencies import require_role
from ..exceptions import BadRequestException
from ..exceptions import InternalServerException
from ..models import APIResponse
from ..models import OfflineAssetStatus
from ..models import WarmupResponse
from ..models.enums import UserRole
from ..services import system_service

router = APIRouter(prefix="/system", tags=["system"])

logger = logging.getLogger(__name__)
AdminUser = Annotated[dict[str, Any], Depends(require_role(UserRole.ADMIN))]


@router.post("/warmup", response_model=APIResponse[WarmupResponse])
async def warmup_system(
    _current_user: AdminUser,
    preload_engines: list[str] | None = None,
    cache_models: bool = True,
    test_connections: bool = True,
):
    """系统预热"""
    try:
        from ..models import WarmupRequest

        engines = preload_engines if preload_engines is not None else ["google", "deepl"]

        request = WarmupRequest(
            preload_engines=engines,
            cache_models=cache_models,
            test_connections=test_connections,
        )

        response = await system_service.warmup_system(
            preload_engines=request.preload_engines,
            cache_models=request.cache_models,
            test_connections=request.test_connections,
        )

        return APIResponse(
            success=True,
            data=response,
            timestamp=time.time(),
            request_id=get_request_id(),
        )
    except Exception as exc:
        if isinstance(exc, (BadRequestException, InternalServerException)):
            raise
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@router.post(
    "/offline-assets/generate", response_model=APIResponse[list[OfflineAssetStatus]]
)
async def generate_offline_assets(
    _current_user: AdminUser,
    asset_types: list[str] | None = None,
    languages: list[str] | None = None,
    include_dependencies: bool = True,
    compression_level: int = 6,
):
    """生成离线资源"""
    try:
        from ..models import OfflineAssetRequest

        selected_assets = (
            asset_types if asset_types is not None else ["translation_models", "language_packs"]
        )

        request = OfflineAssetRequest(
            asset_types=selected_assets,
            languages=languages,
            include_dependencies=include_dependencies,
            compression_level=compression_level,
        )

        results = await system_service.generate_offline_assets(
            asset_types=request.asset_types,
            languages=request.languages,
            include_dependencies=request.include_dependencies,
            compression_level=request.compression_level,
        )

        return APIResponse(
            success=True,
            data=results,
            timestamp=time.time(),
            request_id=get_request_id(),
        )
    except Exception as exc:
        if isinstance(exc, (BadRequestException, InternalServerException)):
            raise
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@router.post("/offline-assets/restore", response_model=APIResponse[bool])
async def restore_offline_assets(
    asset_types: list[str],
    _current_user: AdminUser,
):
    """恢复离线资源"""
    try:
        success = await system_service.restore_offline_assets(asset_types)

        return APIResponse(
            success=True,
            data=success,
            timestamp=time.time(),
            request_id=get_request_id(),
        )
    except Exception as exc:
        if isinstance(exc, (BadRequestException, InternalServerException)):
            raise
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@router.get("/info", response_model=APIResponse[dict[str, Any]])
async def get_system_info(_current_user: AdminUser):
    """获取系统信息"""
    try:
        system_info = await system_service.get_system_info()

        return APIResponse(
            success=True,
            data=system_info,
            timestamp=time.time(),
            request_id=get_request_id(),
        )
    except Exception as exc:
        if isinstance(exc, InternalServerException):
            raise
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@router.post("/cache/clear", response_model=APIResponse[bool])
async def clear_cache(
    _current_user: AdminUser,
    cache_types: list[str] | None = None,
):
    """清除缓存"""
    try:
        # TODO: 实现缓存清除逻辑
        success = True
        targets = cache_types if cache_types is not None else ["translation", "config"]
        logger.info("清除缓存：%s", targets)

        return APIResponse(
            success=True,
            data=success,
            timestamp=time.time(),
            request_id=get_request_id(),
        )
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@router.get("/logs", response_model=APIResponse[dict[str, Any]])
async def get_system_logs(
    _current_user: AdminUser,
    lines: int = 100,
    level: str | None = None,
    start_time: str | None = None,
    end_time: str | None = None,
):
    """获取系统日志"""
    try:
        # TODO: 实现日志获取逻辑
        # 这里应该从日志文件或日志服务获取
        logs = {
            "lines": lines,
            "level": level,
            "start_time": start_time,
            "end_time": end_time,
            "logs": [
                "2024-01-01 12:00:00 INFO Application started",
                "2024-01-01 12:00:01 INFO System initialized",
                "2024-01-01 12:00:02 INFO Ready to serve requests",
            ],
        }

        return APIResponse(
            success=True, data=logs, timestamp=time.time(), request_id=get_request_id()
        )
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@router.post("/restart", response_model=APIResponse[bool])
async def restart_system(
    _current_user: AdminUser,
    restart_type: str = "soft",
):
    """重启系统"""
    try:
        # TODO: 实现系统重启逻辑
        # 这里应该实现优雅的重启机制
        if restart_type not in ["soft", "hard"]:
            raise BadRequestException(
                message="无效的重启类型", details={"supported_types": ["soft", "hard"]}
            )

        success = True
        logger.warning(
            "系统重启请求：类型=%s, 用户=%s",
            restart_type,
            _current_user.get("user_id", "unknown"),
        )

        return APIResponse(
            success=True,
            data=success,
            timestamp=time.time(),
            request_id=get_request_id(),
        )
    except Exception as exc:
        if isinstance(exc, BadRequestException):
            raise
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@router.get("/metrics", response_model=APIResponse[dict[str, Any]])
async def get_system_metrics(
    _current_user: AdminUser,
    metric_types: list[str] | None = None,
    time_range: str = "1h",
):
    """获取系统指标"""
    try:
        # TODO: 实现系统指标获取逻辑
        # 这里应该从监控系统获取实时指标
        metrics = {
            "cpu": {"usage_percent": 45.2, "load_average": [1.2, 1.5, 1.8], "cores": 8},
            "memory": {
                "total": 17179869184,  # 16GB
                "used": 10307921510,  # 9.6GB
                "free": 6871947674,  # 6.4GB
                "percent": 60.0,
            },
            "disk": {
                "total": 536870912000,  # 500GB
                "used": 268435456000,  # 250GB
                "free": 268435456000,  # 250GB
                "percent": 50.0,
            },
            "network": {
                "bytes_sent": 10485760,
                "bytes_recv": 20971520,
                "packets_sent": 10000,
                "packets_recv": 20000,
            },
            "process": {
                "memory_rss": 536870912,  # 512MB
                "memory_percent": 3.1,
                "cpu_percent": 15.2,
                "num_threads": 20,
                "num_fds": 100,
            },
            "time_range": time_range,
            "timestamp": time.time(),
        }

        # 只返回请求的指标类型
        requested_metrics = metric_types if metric_types is not None else ["cpu", "memory", "disk"]

        filtered_metrics = {
            k: v
            for k, v in metrics.items()
            if k in requested_metrics or k in ["time_range", "timestamp"]
        }

        return APIResponse(
            success=True,
            data=filtered_metrics,
            timestamp=time.time(),
            request_id=get_request_id(),
        )
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc
