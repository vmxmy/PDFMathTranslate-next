"""翻译相关路由"""

import time
from datetime import datetime
from typing import Any, Dict

from fastapi import APIRouter
from fastapi import Depends
from fastapi import File
from fastapi import Form
from fastapi import HTTPException
from fastapi import Query
from fastapi import UploadFile
from fastapi.responses import FileResponse

from ..dependencies import get_current_user
from ..dependencies import get_request_id
from ..exceptions import BadRequestException
from ..exceptions import NotFoundException
from ..exceptions import create_validation_exception
from ..models import APIResponse
from ..models import BatchOperationRequest
from ..models import PaginatedResponse
from ..models import TranslationPreview
from ..models import TranslationPreviewRequest
from ..models import TranslationProgress
from ..models import TranslationRequest
from ..models import TranslationResult
from ..models import TranslationTask
from ..models import CleanupResult
from ..services import translation_service

router = APIRouter(prefix="/translations", tags=["translations"])


@router.post("/", response_model=APIResponse[TranslationTask])
async def create_translation(
    files: list[UploadFile] = File(..., description="要翻译的PDF文件列表"),
    target_language: str = Form("zh", description="目标语言代码"),
    source_language: str | None = Form(
        None, description="源语言代码（可选，自动检测）"
    ),
    translation_engine: str = Form("google", description="翻译引擎"),
    preserve_formatting: bool = Form(True, description="是否保持格式"),
    translate_tables: bool = Form(True, description="是否翻译表格"),
    translate_equations: bool = Form(True, description="是否处理数学公式"),
    custom_glossary: str | None = Form(None, description="自定义术语词典（JSON格式）"),
    webhook_url: str | None = Form(None, description="完成通知的webhook URL"),
    priority: int = Form(1, ge=1, le=5, description="任务优先级（1-5，5最高）"),
    timeout: int | None = Form(None, ge=60, description="超时时间（秒）"),
    current_user: dict = Depends(get_current_user),
):
    """创建PDF翻译任务"""
    try:
        # 解析自定义术语词典
        glossary_dict = None
        if custom_glossary:
            import json

            try:
                glossary_dict = json.loads(custom_glossary)
            except json.JSONDecodeError as e:
                raise create_validation_exception(
                    "custom_glossary", f"无效的JSON格式: {e}"
                )

        # 构建请求对象
        request = TranslationRequest(
            files=files,
            target_language=target_language,
            source_language=source_language,
            translation_engine=translation_engine,
            preserve_formatting=preserve_formatting,
            translate_tables=translate_tables,
            translate_equations=translate_equations,
            custom_glossary=glossary_dict,
            webhook_url=webhook_url,
            priority=priority,
            timeout=timeout,
        )

        # 创建翻译任务
        task = await translation_service.create_task(request, current_user)

        return APIResponse(
            success=True, data=task, timestamp=time.time(), request_id=get_request_id()
        )

    except Exception as e:
        if isinstance(e, (BadRequestException, NotFoundException)):
            raise
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/{task_id}", response_model=APIResponse[TranslationTask])
async def get_translation_status(
    task_id: str, current_user: dict = Depends(get_current_user)
):
    """获取翻译任务状态"""
    try:
        task = await translation_service.get_task(task_id, current_user)

        return APIResponse(
            success=True, data=task, timestamp=time.time(), request_id=get_request_id()
        )
    except NotFoundException as e:
        raise e
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/{task_id}/progress", response_model=APIResponse[TranslationProgress])
async def get_translation_progress(
    task_id: str, current_user: dict = Depends(get_current_user)
):
    """获取翻译任务进度"""
    try:
        progress = await translation_service.get_task_progress(task_id, current_user)

        return APIResponse(
            success=True,
            data=progress,
            timestamp=time.time(),
            request_id=get_request_id(),
        )
    except NotFoundException as e:
        raise e
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/{task_id}/result", response_model=APIResponse[TranslationResult])
async def get_translation_result(
    task_id: str, current_user: dict = Depends(get_current_user)
):
    """获取翻译结果"""
    try:
        result = await translation_service.get_task_result(task_id, current_user)

        return APIResponse(
            success=True,
            data=result,
            timestamp=time.time(),
            request_id=get_request_id(),
        )
    except NotFoundException as e:
        raise e
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get(
    "/{task_id}/files/{file_id}/download",
    response_class=FileResponse,
    tags=["translations"],
)
async def download_translation_file(
    task_id: str,
    file_id: str,
    current_user: dict = Depends(get_current_user),
):
    """下载翻译结果文件"""
    try:
        file_path = await translation_service.get_translated_file_path(
            task_id, file_id, current_user
        )
        return FileResponse(
            file_path,
            filename=file_path.name,
            media_type="application/zip",
        )
    except NotFoundException as e:
        raise e
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/{task_id}", response_model=APIResponse[bool])
async def delete_translation_task(
    task_id: str, current_user: dict = Depends(get_current_user)
):
    """删除翻译任务"""
    try:
        success = await translation_service.delete_task(task_id, current_user)

        return APIResponse(
            success=True,
            data=success,
            timestamp=time.time(),
            request_id=get_request_id(),
        )
    except NotFoundException as e:
        raise e
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/{task_id}/clean", response_model=APIResponse[CleanupResult])
async def clean_translation_artifacts(
    task_id: str, current_user: dict = Depends(get_current_user)
):
    """清理任务产物（临时文件与打包结果）"""
    try:
        result = await translation_service.clean_task_artifacts(task_id, current_user)
        return APIResponse(
            success=True,
            data=result,
            timestamp=time.time(),
            request_id=get_request_id(),
        )
    except NotFoundException as e:
        raise e
    except BadRequestException as e:
        raise e
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/{task_id}/cancel", response_model=APIResponse[bool])
async def cancel_translation_task(
    task_id: str, current_user: dict = Depends(get_current_user)
):
    """取消翻译任务"""
    try:
        success = await translation_service.cancel_task(task_id, current_user)

        return APIResponse(
            success=True,
            data=success,
            timestamp=time.time(),
            request_id=get_request_id(),
        )
    except NotFoundException as e:
        raise e
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/", response_model=APIResponse[PaginatedResponse[TranslationTask]])
async def list_translation_tasks(
    page: int = Query(1, ge=1, description="页码"),
    page_size: int = Query(20, ge=1, le=100, description="每页大小"),
    status: list[str] | None = Query(None, description="任务状态过滤"),
    engine: list[str] | None = Query(None, description="翻译引擎过滤"),
    date_from: datetime | None = Query(None, description="开始时间过滤"),
    date_to: datetime | None = Query(None, description="结束时间过滤"),
    priority_min: int | None = Query(None, ge=1, le=5, description="最小优先级"),
    priority_max: int | None = Query(None, ge=1, le=5, description="最大优先级"),
    sort_by: str | None = Query(None, description="排序字段"),
    sort_order: str = Query("desc", regex="^(asc|desc)$", description="排序方式"),
    current_user: dict = Depends(get_current_user),
):
    """列出翻译任务"""
    try:
        # 构建过滤条件
        filters = {
            "status": status,
            "engine": engine,
            "date_from": date_from,
            "date_to": date_to,
            "priority_min": priority_min,
            "priority_max": priority_max,
        }

        # 移除None值
        filters = {k: v for k, v in filters.items() if v is not None}

        # 获取任务列表
        result = await translation_service.list_tasks(
            current_user, page=page, page_size=page_size, **filters
        )

        return APIResponse(
            success=True,
            data=result,
            timestamp=time.time(),
            request_id=get_request_id(),
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/batch", response_model=APIResponse[Dict[str, Any]])
async def batch_operation_tasks(
    request: BatchOperationRequest, current_user: dict = Depends(get_current_user)
):
    """批量操作翻译任务"""
    try:
        result = await translation_service.batch_operation(request, current_user)

        return APIResponse(
            success=True,
            data=result,
            timestamp=time.time(),
            request_id=get_request_id(),
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/statistics", response_model=APIResponse[Dict[str, Any]])
async def get_translation_statistics(current_user: dict = Depends(get_current_user)):
    """获取翻译统计信息"""
    try:
        statistics = await translation_service.get_statistics(current_user)

        return APIResponse(
            success=True,
            data=statistics,
            timestamp=time.time(),
            request_id=get_request_id(),
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/preview", response_model=APIResponse[TranslationPreview])
async def preview_translation(
    request: TranslationPreviewRequest, current_user: dict = Depends(get_current_user)
):
    """预览翻译结果"""
    try:
        preview = await translation_service.preview_translation(request, current_user)

        return APIResponse(
            success=True,
            data=preview,
            timestamp=time.time(),
            request_id=get_request_id(),
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/webhook/test", response_model=APIResponse[Dict[str, Any]])
async def test_webhook(
    webhook_url: str, current_user: dict = Depends(get_current_user)
):
    """测试webhook连接"""
    try:
        # TODO: 实现webhook测试逻辑
        result = {
            "webhook_url": webhook_url,
            "status_code": 200,
            "response_time_ms": 150,
            "success": True,
        }

        return APIResponse(
            success=True,
            data=result,
            timestamp=time.time(),
            request_id=get_request_id(),
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
