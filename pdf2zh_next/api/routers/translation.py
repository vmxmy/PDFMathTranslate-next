"""翻译相关路由"""

import time
from datetime import datetime
from typing import Annotated
from typing import Any

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
from ..models import CleanupResult
from ..models import PaginatedResponse
from ..models import TranslationPreview
from ..models import TranslationPreviewRequest
from ..models import TranslationProgress
from ..models import TranslationRequest
from ..models import TranslationResult
from ..models import TranslationTask
from ..services import translation_service

router = APIRouter(prefix="/translations", tags=["translations"])

CurrentUser = Annotated[dict[str, Any], Depends(get_current_user)]


@router.post("/", response_model=APIResponse[TranslationTask])
async def create_translation(
    files: Annotated[ list[UploadFile], File(..., description="要翻译的 PDF 文件列表") ],
    target_language: Annotated[str, Form(description="目标语言代码")] = "zh",
    source_language: Annotated[str | None, Form(description="源语言代码（可选，自动检测）")] = None,
    translation_engine: Annotated[str, Form(description="翻译引擎")] = "google",
    preserve_formatting: Annotated[bool, Form(description="是否保持格式")] = True,
    translate_tables: Annotated[bool, Form(description="是否翻译表格")] = True,
    translate_equations: Annotated[bool, Form(description="是否处理数学公式")] = True,
    custom_glossary: Annotated[str | None, Form(description="自定义术语词典（JSON 格式）")] = None,
    webhook_url: Annotated[str | None, Form(description="完成通知的 webhook URL")] = None,
    priority: Annotated[int, Form(ge=1, le=5, description="任务优先级（1-5，5 最高）")] = 1,
    timeout: Annotated[int | None, Form(ge=60, description="超时时间（秒）")] = None,
    *,
    current_user: CurrentUser,
):
    """创建 PDF 翻译任务"""
    try:
        # 解析自定义术语词典
        glossary_dict = None
        if custom_glossary:
            import json

            try:
                glossary_dict = json.loads(custom_glossary)
            except json.JSONDecodeError as exc:
                raise create_validation_exception(
                    "custom_glossary", f"无效的 JSON 格式：{exc}"
                ) from exc

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

    except Exception as exc:
        if isinstance(exc, (BadRequestException, NotFoundException)):
            raise
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@router.get("/{task_id}", response_model=APIResponse[TranslationTask])
async def get_translation_status(
    task_id: str, current_user: CurrentUser
):
    """获取翻译任务状态"""
    try:
        task = await translation_service.get_task(task_id, current_user)

        return APIResponse(
            success=True, data=task, timestamp=time.time(), request_id=get_request_id()
        )
    except NotFoundException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@router.get("/{task_id}/progress", response_model=APIResponse[TranslationProgress])
async def get_translation_progress(
    task_id: str, current_user: CurrentUser
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
    except NotFoundException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@router.get("/{task_id}/result", response_model=APIResponse[TranslationResult])
async def get_translation_result(
    task_id: str, current_user: CurrentUser
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
    except NotFoundException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@router.get(
    "/{task_id}/files/{file_id}/download",
    response_class=FileResponse,
    tags=["translations"],
)
async def download_translation_file(
    task_id: str,
    file_id: str,
    current_user: CurrentUser,
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
    except NotFoundException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@router.delete("/{task_id}", response_model=APIResponse[bool])
async def delete_translation_task(
    task_id: str, current_user: CurrentUser
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
    except NotFoundException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@router.post("/{task_id}/clean", response_model=APIResponse[CleanupResult])
async def clean_translation_artifacts(
    task_id: str, current_user: CurrentUser
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
    except NotFoundException:
        raise
    except BadRequestException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@router.post("/{task_id}/cancel", response_model=APIResponse[bool])
async def cancel_translation_task(
    task_id: str, current_user: CurrentUser
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
    except NotFoundException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@router.get("/", response_model=APIResponse[PaginatedResponse[TranslationTask]])
async def list_translation_tasks(
    page: Annotated[int, Query(ge=1, description="页码")] = 1,
    page_size: Annotated[int, Query(ge=1, le=100, description="每页大小")] = 20,
    status: Annotated[list[str] | None, Query(description="任务状态过滤")] = None,
    engine: Annotated[list[str] | None, Query(description="翻译引擎过滤")] = None,
    date_from: Annotated[datetime | None, Query(description="开始时间过滤")] = None,
    date_to: Annotated[datetime | None, Query(description="结束时间过滤")] = None,
    priority_min: Annotated[int | None, Query(ge=1, le=5, description="最小优先级")] = None,
    priority_max: Annotated[int | None, Query(ge=1, le=5, description="最大优先级")] = None,
    sort_by: Annotated[str | None, Query(description="排序字段")] = None,
    sort_order: Annotated[str, Query(regex="^(asc|desc)$", description="排序方式")] = "desc",
    *,
    current_user: CurrentUser,
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
            "sort_by": sort_by,
            "sort_order": sort_order,
        }

        # 移除 None 值
        filters = {k: v for k, v in filters.items() if v is not None}

        # 获取任务列表
        result = await translation_service.list_tasks(
            current_user,
            page=page,
            page_size=page_size,
            **filters,
        )

        return APIResponse(
            success=True,
            data=result,
            timestamp=time.time(),
            request_id=get_request_id(),
        )
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@router.post("/batch", response_model=APIResponse[dict[str, Any]])
async def batch_operation_tasks(
    request: BatchOperationRequest, current_user: CurrentUser
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
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@router.get("/statistics", response_model=APIResponse[dict[str, Any]])
async def get_translation_statistics(current_user: CurrentUser):
    """获取翻译统计信息"""
    try:
        statistics = await translation_service.get_statistics(current_user)

        return APIResponse(
            success=True,
            data=statistics,
            timestamp=time.time(),
            request_id=get_request_id(),
        )
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@router.post("/preview", response_model=APIResponse[TranslationPreview])
async def preview_translation(
    request: TranslationPreviewRequest, current_user: CurrentUser
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
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@router.post("/webhook/test", response_model=APIResponse[dict[str, Any]])
async def test_webhook(
    webhook_url: str, _current_user: CurrentUser
):
    """测试 webhook 连接"""
    try:
        # TODO: 实现 webhook 测试逻辑
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
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc
