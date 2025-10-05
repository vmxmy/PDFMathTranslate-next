"""配置管理相关路由"""

import time
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


@router.get("/", response_model=APIResponse[ConfigResponse])
async def get_config(current_user: dict = Depends(get_current_user)):
    """获取当前配置"""
    try:
        config = config_service.get_config()

        return APIResponse(
            success=True,
            data=config,
            timestamp=time.time(),
            request_id=get_request_id(),
        )
    except Exception as e:
        if isinstance(e, InternalServerException):
            raise
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/schema", response_model=APIResponse[dict[str, Any]])
async def get_config_schema(current_user: dict = Depends(get_current_user)):
    """获取配置schema"""
    try:
        schema = config_service.get_config_schema()

        return APIResponse(
            success=True,
            data=schema,
            timestamp=time.time(),
            request_id=get_request_id(),
        )
    except Exception as e:
        if isinstance(e, InternalServerException):
            raise
        raise HTTPException(status_code=500, detail=str(e))


@router.put("/", response_model=APIResponse[ConfigResponse])
async def update_config(
    request: ConfigUpdateRequest,
    current_user: dict = Depends(require_role(UserRole.ADMIN)),
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
    except Exception as e:
        if isinstance(e, (BadRequestException, InternalServerException)):
            raise
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/reset", response_model=APIResponse[ConfigResponse])
async def reset_config(current_user: dict = Depends(require_role(UserRole.ADMIN))):
    """重置配置为默认值"""
    try:
        result = config_service.reset_config()

        return APIResponse(
            success=True,
            data=result,
            timestamp=time.time(),
            request_id=get_request_id(),
        )
    except Exception as e:
        if isinstance(e, InternalServerException):
            raise
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/translation", response_model=APIResponse[dict[str, Any]])
async def get_translation_config(current_user: dict = Depends(get_current_user)):
    """获取翻译配置"""
    try:
        config = config_service.get_translation_config()

        return APIResponse(
            success=True,
            data=config,
            timestamp=time.time(),
            request_id=get_request_id(),
        )
    except Exception as e:
        if isinstance(e, InternalServerException):
            raise
        raise HTTPException(status_code=500, detail=str(e))


@router.put("/translation", response_model=APIResponse[ConfigResponse])
async def update_translation_config(
    config: dict[str, Any],
    validation_mode: ValidationMode = ValidationMode.STRICT,
    current_user: dict = Depends(require_role(UserRole.ADMIN)),
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
    except Exception as e:
        if isinstance(e, (BadRequestException, InternalServerException)):
            raise
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/system", response_model=APIResponse[dict[str, Any]])
async def get_system_config(current_user: dict = Depends(get_current_user)):
    """获取系统配置"""
    try:
        config = config_service.get_system_config()

        return APIResponse(
            success=True,
            data=config,
            timestamp=time.time(),
            request_id=get_request_id(),
        )
    except Exception as e:
        if isinstance(e, InternalServerException):
            raise
        raise HTTPException(status_code=500, detail=str(e))


@router.put("/system", response_model=APIResponse[ConfigResponse])
async def update_system_config(
    config: dict[str, Any],
    validation_mode: ValidationMode = ValidationMode.STRICT,
    current_user: dict = Depends(require_role(UserRole.ADMIN)),
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
    except Exception as e:
        if isinstance(e, (BadRequestException, InternalServerException)):
            raise
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/api", response_model=APIResponse[dict[str, Any]])
async def get_api_config(current_user: dict = Depends(get_current_user)):
    """获取API配置"""
    try:
        config = config_service.get_api_config()

        return APIResponse(
            success=True,
            data=config,
            timestamp=time.time(),
            request_id=get_request_id(),
        )
    except Exception as e:
        if isinstance(e, InternalServerException):
            raise
        raise HTTPException(status_code=500, detail=str(e))


@router.put("/api", response_model=APIResponse[ConfigResponse])
async def update_api_config(
    config: dict[str, Any],
    validation_mode: ValidationMode = ValidationMode.STRICT,
    current_user: dict = Depends(require_role(UserRole.ADMIN)),
):
    """更新API配置"""
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
    except Exception as e:
        if isinstance(e, (BadRequestException, InternalServerException)):
            raise
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/logging", response_model=APIResponse[dict[str, Any]])
async def get_logging_config(current_user: dict = Depends(get_current_user)):
    """获取日志配置"""
    try:
        config = config_service.get_logging_config()

        return APIResponse(
            success=True,
            data=config,
            timestamp=time.time(),
            request_id=get_request_id(),
        )
    except Exception as e:
        if isinstance(e, InternalServerException):
            raise
        raise HTTPException(status_code=500, detail=str(e))


@router.put("/logging", response_model=APIResponse[ConfigResponse])
async def update_logging_config(
    config: dict[str, Any],
    validation_mode: ValidationMode = ValidationMode.STRICT,
    current_user: dict = Depends(require_role(UserRole.ADMIN)),
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
    except Exception as e:
        if isinstance(e, (BadRequestException, InternalServerException)):
            raise
        raise HTTPException(status_code=500, detail=str(e))
