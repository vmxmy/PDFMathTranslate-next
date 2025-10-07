"""配置管理相关路由"""

import time
from typing import Annotated
from typing import Any

from fastapi import APIRouter
from fastapi import Depends
from fastapi import HTTPException

from ..dependencies import get_current_user
from ..dependencies import get_request_id
from ..dependencies import require_role
from ..exceptions import BadRequestException
from ..exceptions import InternalServerException
from ..models import APIResponse
from ..models import ConfigResponse
from ..models import ConfigUpdateRequest
from ..models.enums import UserRole
from ..models.enums import ValidationMode
from ..services import config_service

router = APIRouter(prefix="/config", tags=["config"])

CurrentUser = Annotated[dict[str, Any], Depends(get_current_user)]
AdminUser = Annotated[dict[str, Any], Depends(require_role(UserRole.ADMIN))]


@router.get("/", response_model=APIResponse[ConfigResponse])
async def get_config(_current_user: CurrentUser):
    """获取当前配置"""
    try:
        config = config_service.get_config()

        return APIResponse(
            success=True,
            data=config,
            timestamp=time.time(),
            request_id=get_request_id(),
        )
    except Exception as exc:
        if isinstance(exc, InternalServerException):
            raise
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@router.get("/schema", response_model=APIResponse[dict[str, Any]])
async def get_config_schema(_current_user: CurrentUser):
    """获取配置 schema"""
    try:
        schema = config_service.get_config_schema()

        return APIResponse(
            success=True,
            data=schema,
            timestamp=time.time(),
            request_id=get_request_id(),
        )
    except Exception as exc:
        if isinstance(exc, InternalServerException):
            raise
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@router.put("/", response_model=APIResponse[ConfigResponse])
async def update_config(
    request: ConfigUpdateRequest,
    _current_user: AdminUser,
):
    """更新配置"""
    try:
        result = config_service.update_config(request)

        return APIResponse(
            success=True,
            data=result,
            timestamp=time.time(),
            request_id=get_request_id(),
        )
    except Exception as exc:
        if isinstance(exc, (BadRequestException, InternalServerException)):
            raise
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@router.post("/reset", response_model=APIResponse[ConfigResponse])
async def reset_config(_current_user: AdminUser):
    """重置配置为默认值"""
    try:
        result = config_service.reset_config()

        return APIResponse(
            success=True,
            data=result,
            timestamp=time.time(),
            request_id=get_request_id(),
        )
    except Exception as exc:
        if isinstance(exc, InternalServerException):
            raise
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@router.get("/translation", response_model=APIResponse[dict[str, Any]])
async def get_translation_config(_current_user: CurrentUser):
    """获取翻译配置"""
    try:
        config = config_service.get_translation_config()

        return APIResponse(
            success=True,
            data=config,
            timestamp=time.time(),
            request_id=get_request_id(),
        )
    except Exception as exc:
        if isinstance(exc, InternalServerException):
            raise
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@router.put("/translation", response_model=APIResponse[ConfigResponse])
async def update_translation_config(
    config: dict[str, Any],
    _current_user: AdminUser,
    validation_mode: ValidationMode = ValidationMode.STRICT,
):
    """更新翻译配置"""
    try:
        from ..models import ConfigUpdateRequest

        request = ConfigUpdateRequest(
            translation=config, validation_mode=validation_mode
        )

        result = config_service.update_config(request)

        return APIResponse(
            success=True,
            data=result,
            timestamp=time.time(),
            request_id=get_request_id(),
        )
    except Exception as exc:
        if isinstance(exc, (BadRequestException, InternalServerException)):
            raise
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@router.get("/system", response_model=APIResponse[dict[str, Any]])
async def get_system_config(_current_user: CurrentUser):
    """获取系统配置"""
    try:
        config = config_service.get_system_config()

        return APIResponse(
            success=True,
            data=config,
            timestamp=time.time(),
            request_id=get_request_id(),
        )
    except Exception as exc:
        if isinstance(exc, InternalServerException):
            raise
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@router.put("/system", response_model=APIResponse[ConfigResponse])
async def update_system_config(
    config: dict[str, Any],
    _current_user: AdminUser,
    validation_mode: ValidationMode = ValidationMode.STRICT,
):
    """更新系统配置"""
    try:
        from ..models import ConfigUpdateRequest

        request = ConfigUpdateRequest(system=config, validation_mode=validation_mode)

        result = config_service.update_config(request)

        return APIResponse(
            success=True,
            data=result,
            timestamp=time.time(),
            request_id=get_request_id(),
        )
    except Exception as exc:
        if isinstance(exc, (BadRequestException, InternalServerException)):
            raise
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@router.get("/api", response_model=APIResponse[dict[str, Any]])
async def get_api_config(_current_user: CurrentUser):
    """获取 API 配置"""
    try:
        config = config_service.get_api_config()

        return APIResponse(
            success=True,
            data=config,
            timestamp=time.time(),
            request_id=get_request_id(),
        )
    except Exception as exc:
        if isinstance(exc, InternalServerException):
            raise
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@router.put("/api", response_model=APIResponse[ConfigResponse])
async def update_api_config(
    config: dict[str, Any],
    _current_user: AdminUser,
    validation_mode: ValidationMode = ValidationMode.STRICT,
):
    """更新 API 配置"""
    try:
        from ..models import ConfigUpdateRequest

        request = ConfigUpdateRequest(api=config, validation_mode=validation_mode)

        result = config_service.update_config(request)

        return APIResponse(
            success=True,
            data=result,
            timestamp=time.time(),
            request_id=get_request_id(),
        )
    except Exception as exc:
        if isinstance(exc, (BadRequestException, InternalServerException)):
            raise
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@router.get("/logging", response_model=APIResponse[dict[str, Any]])
async def get_logging_config(_current_user: CurrentUser):
    """获取日志配置"""
    try:
        config = config_service.get_logging_config()

        return APIResponse(
            success=True,
            data=config,
            timestamp=time.time(),
            request_id=get_request_id(),
        )
    except Exception as exc:
        if isinstance(exc, InternalServerException):
            raise
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@router.put("/logging", response_model=APIResponse[ConfigResponse])
async def update_logging_config(
    config: dict[str, Any],
    _current_user: AdminUser,
    validation_mode: ValidationMode = ValidationMode.STRICT,
):
    """更新日志配置"""
    try:
        from ..models import ConfigUpdateRequest

        request = ConfigUpdateRequest(logging=config, validation_mode=validation_mode)

        result = config_service.update_config(request)

        return APIResponse(
            success=True,
            data=result,
            timestamp=time.time(),
            request_id=get_request_id(),
        )
    except Exception as exc:
        if isinstance(exc, (BadRequestException, InternalServerException)):
            raise
        raise HTTPException(status_code=500, detail=str(exc)) from exc
