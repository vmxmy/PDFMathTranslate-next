from __future__ import annotations

import asyncio
import contextlib
import copy
import io
import json
import logging
import os
import shutil
import tempfile
import zipfile
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Any
from uuid import uuid4

from fastapi import FastAPI
from fastapi import File
from fastapi import Form
from fastapi import HTTPException
from fastapi import UploadFile
from fastapi.responses import JSONResponse
from fastapi.responses import StreamingResponse
from pydantic import ValidationError

from babeldoc.assets import assets as babeldoc_assets

from pdf2zh_next.const import __version__
from pdf2zh_next.config.cli_env_model import CLIEnvSettingsModel
from pdf2zh_next.config.model import SettingsModel
from pdf2zh_next.config.translate_engine_model import (
    TRANSLATION_ENGINE_METADATA_MAP,
)
from pdf2zh_next.high_level import do_translate_async_stream

logger = logging.getLogger(__name__)
logging.getLogger("pdf2zh_next").setLevel(logging.DEBUG)
logging.getLogger("babeldoc").setLevel(logging.DEBUG)


class TaskState(str, Enum):
    QUEUED = "queued"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"


def parse_stage_summary_from_logs(logs: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """从 logs 数组中提取 stage_summary 事件"""
    stage_summaries = []

    for log_entry in logs:
        # 查找包含 stage_summary 的 DEBUG 消息
        if log_entry.get(
            "level"
        ) == "DEBUG" and "sub process generate event" in log_entry.get("message", ""):
            # 解析消息中的 event JSON
            message = log_entry["message"]
            # 提取 JSON 部分
            json_start = message.find("{")
            if json_start != -1:
                try:
                    event_data = json.loads(message[json_start:])
                    if event_data.get("type") == "stage_summary":
                        stage_summaries.append(event_data)
                except json.JSONDecodeError:
                    continue

    return stage_summaries


def calculate_translation_progress(logs: list[dict[str, Any]]) -> dict[str, Any]:
    """计算翻译进度信息"""
    if not logs:
        return {
            "overall_progress": 0.0,
            "current_stage": None,
            "stage_summaries": [],
            "estimated_total_progress": 0.0,
            "stage_current": None,
            "stage_total": None,
            "part_index": None,
            "total_parts": None,
        }

    # 解析 stage_summary 事件
    stage_summaries = parse_stage_summary_from_logs(logs)

    # 查找最新的进度更新事件
    latest_progress_event = None
    for log_entry in reversed(logs):
        if log_entry.get(
            "level"
        ) == "DEBUG" and "sub process generate event" in log_entry.get("message", ""):
            message = log_entry["message"]
            json_start = message.find("{")
            if json_start != -1:
                try:
                    event_data = json.loads(message[json_start:])

                    if event_data.get("type") in [
                        "progress_update",
                        "progress_start",
                        "progress_end",
                    ]:
                        latest_progress_event = event_data
                        break

                except json.JSONDecodeError:
                    continue

    # 如果找到了进度事件，使用其信息
    if latest_progress_event:
        return {
            "overall_progress": latest_progress_event.get("overall_progress", 0.0),
            "current_stage": latest_progress_event.get("stage"),
            "stage_summaries": stage_summaries,
            "estimated_total_progress": sum(
                stage.get("percent", 0) for stage in stage_summaries
            ),
            "stage_current": latest_progress_event.get("stage_current"),
            "stage_total": latest_progress_event.get("stage_total"),
            "part_index": latest_progress_event.get("part_index"),
            "total_parts": latest_progress_event.get("total_parts"),
        }

    # 如果没有找到进度事件，但找到了 stage_summary，尝试估算进度
    if stage_summaries:
        return {
            "overall_progress": 0.0,  # 没有实时进度信息
            "current_stage": "初始化中",
            "stage_summaries": stage_summaries,
            "estimated_total_progress": sum(
                stage.get("percent", 0) for stage in stage_summaries
            ),
            "stage_current": None,
            "stage_total": None,
            "part_index": None,
            "total_parts": None,
        }

    # 默认返回无进度信息
    return {
        "overall_progress": 0.0,
        "current_stage": None,
        "stage_summaries": [],
        "estimated_total_progress": 0.0,
        "stage_current": None,
        "stage_total": None,
        "part_index": None,
        "total_parts": None,
    }


@dataclass
class TaskRecord:
    id: str
    state: TaskState
    created_at: datetime
    updated_at: datetime
    settings: SettingsModel
    tmp_dir: Path
    input_path: Path
    output_dir: Path
    result_event: dict[str, Any] | None = None
    error: str | None = None
    logs: list[dict[str, Any]] = field(default_factory=list)
    event: asyncio.Event = field(default_factory=asyncio.Event, repr=False)


DEFAULT_CLI_SETTINGS = CLIEnvSettingsModel()
DEFAULT_CLI_SETTINGS_DICT = DEFAULT_CLI_SETTINGS.model_dump(mode="json")

MAX_CONCURRENCY = int(os.getenv("PDF2ZH_API_MAX_CONCURRENCY", "20"))
if MAX_CONCURRENCY < 1:
    raise RuntimeError("PDF2ZH_API_MAX_CONCURRENCY must be >= 1")

QUEUE_MAX_SIZE = int(os.getenv("PDF2ZH_API_QUEUE_MAXSIZE", "0"))
EXEC_TIMEOUT_RAW = os.getenv("PDF2ZH_API_EXEC_TIMEOUT")
EXEC_TIMEOUT = None if EXEC_TIMEOUT_RAW in (None, "") else float(EXEC_TIMEOUT_RAW)
SEMAPHORE = asyncio.Semaphore(MAX_CONCURRENCY)
TASKS: dict[str, TaskRecord] = {}
TASK_QUEUE: asyncio.Queue[TaskRecord] = asyncio.Queue()
WORKER_COUNT_RAW = os.getenv("PDF2ZH_API_WORKERS")
try:
    WORKER_COUNT = int(WORKER_COUNT_RAW) if WORKER_COUNT_RAW else MAX_CONCURRENCY
except ValueError as exc:  # noqa: BLE001
    raise RuntimeError("PDF2ZH_API_WORKERS must be an integer") from exc
if WORKER_COUNT < 1:
    raise RuntimeError("PDF2ZH_API_WORKERS must be >= 1")
WORKER_TASKS: list[asyncio.Task] = []
# Track active asyncio tasks so we can await completion on shutdown
ACTIVE_TASKS: set[asyncio.Task[None]] = set()

# Limit the amount of data kept in RAM when persisting uploads to disk.
UPLOAD_CHUNK_SIZE_RAW = os.getenv("PDF2ZH_API_UPLOAD_CHUNK_SIZE", str(1 << 20))
try:
    UPLOAD_CHUNK_SIZE = int(UPLOAD_CHUNK_SIZE_RAW)
except ValueError as exc:  # noqa: BLE001
    raise RuntimeError("PDF2ZH_API_UPLOAD_CHUNK_SIZE must be an integer") from exc
if UPLOAD_CHUNK_SIZE < 1:
    raise RuntimeError("PDF2ZH_API_UPLOAD_CHUNK_SIZE must be >= 1")


@contextlib.asynccontextmanager
async def _lifespan(app: FastAPI):  # noqa: ARG001
    # 启动时预加载资源，减少首次请求延迟
    logger.info("Starting application and preloading resources...")

    global WORKER_TASKS
    WORKER_TASKS = [
        asyncio.create_task(_task_worker_loop()) for _ in range(WORKER_COUNT)
    ]
    logger.info("Task workers started (count=%d)", WORKER_COUNT)

    # 异步预热 BabelDOC 资源，不阻塞应用启动
    warmup_task = asyncio.create_task(babeldoc_assets.async_warmup())

    try:
        yield
    finally:
        # 清理资源
        warmup_task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await warmup_task

        for worker in WORKER_TASKS:
            worker.cancel()
        for worker in WORKER_TASKS:
            with contextlib.suppress(asyncio.CancelledError):
                await worker
        WORKER_TASKS.clear()
        if ACTIVE_TASKS:
            await asyncio.gather(*ACTIVE_TASKS, return_exceptions=True)
        for task_id, task in list(TASKS.items()):
            _cleanup_task(task)
            TASKS.pop(task_id, None)


app = FastAPI(
    title="PDFMathTranslate-next API", version=__version__, lifespan=_lifespan
)


def _deep_merge(base: dict[str, Any], overrides: dict[str, Any]) -> dict[str, Any]:
    merged: dict[str, Any] = {}
    for key, value in base.items():
        merged[key] = value
    for key, value in overrides.items():
        if key in merged and isinstance(merged[key], dict) and isinstance(value, dict):
            merged[key] = _deep_merge(merged[key], value)
        else:
            merged[key] = value
    return merged


def _normalize_translate_engine_payload(payload: dict[str, Any]) -> dict[str, Any]:
    if "translate_engine_settings" not in payload:
        return payload

    engine_payload = payload.pop("translate_engine_settings") or {}
    engine_type = engine_payload.get("translate_engine_type")
    if not engine_type:
        raise HTTPException(
            status_code=400,
            detail="translate_engine_settings requires translate_engine_type",
        )

    metadata = TRANSLATION_ENGINE_METADATA_MAP.get(engine_type)
    if metadata is None:
        raise HTTPException(
            status_code=400,
            detail=f"Unsupported translate_engine_type: {engine_type}",
        )

    payload[metadata.cli_flag_name] = True

    detail_payload = {
        k: v for k, v in engine_payload.items() if k != "translate_engine_type"
    }
    if metadata.cli_detail_field_name:
        existing_detail = payload.get(metadata.cli_detail_field_name) or {}
        if not isinstance(existing_detail, dict):
            raise HTTPException(
                status_code=400,
                detail=f"{metadata.cli_detail_field_name} must be an object",
            )
        merged_detail = _deep_merge(existing_detail, detail_payload)
        payload[metadata.cli_detail_field_name] = merged_detail
    elif detail_payload:
        raise HTTPException(
            status_code=400,
            detail=(
                "translate_engine_settings includes unsupported detail fields "
                f"for engine {engine_type}"
            ),
        )

    return payload


def _build_cli_settings(overrides: dict[str, Any]) -> CLIEnvSettingsModel:
    if overrides is None:
        overrides = {}
    payload = copy.deepcopy(overrides)
    payload = _normalize_translate_engine_payload(payload)
    merged_dict = _deep_merge(DEFAULT_CLI_SETTINGS_DICT, payload)
    try:
        return CLIEnvSettingsModel.model_validate(merged_dict)
    except ValidationError as exc:
        logger.warning("Invalid settings payload: %s", exc)
        raise HTTPException(status_code=400, detail="Invalid settings payload") from exc


def _build_settings(overrides: dict[str, Any]) -> SettingsModel:
    cli_settings = _build_cli_settings(overrides)
    settings = cli_settings.to_settings_model()
    return settings


def _resolve_optional_path(raw_path: str | None) -> Path | None:
    if raw_path in (None, ""):
        return None
    try:
        return Path(raw_path).expanduser().resolve()
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(
            status_code=400, detail=f"Invalid path: {raw_path}"
        ) from exc


async def _acquire_slot(timeout: float | None) -> None:
    try:
        if timeout is None:
            await SEMAPHORE.acquire()
        else:
            await asyncio.wait_for(SEMAPHORE.acquire(), timeout)
    except asyncio.TimeoutError as exc:
        raise RuntimeError("Translation concurrency limit timeout") from exc


def _release_slot() -> None:
    SEMAPHORE.release()


async def _stream_translation(
    settings: SettingsModel,
    input_path: Path,
    task: TaskRecord,
) -> dict[str, Any]:
    result_event: dict[str, Any] | None = None

    async for event in do_translate_async_stream(settings, input_path):
        event_type = event.get("type")
        if event_type == "log":
            log_entry = {
                "timestamp": event.get("timestamp"),
                "level": event.get("level"),
                "message": event.get("message"),
            }
            task.logs.append(log_entry)
            task.updated_at = datetime.now(timezone.utc)
            continue
        if event_type == "error":
            error_message = event.get("error", "Unknown error")
            error_type = event.get("error_type", "TranslationError")
            logger.error(
                "Translation failed for %s: %s (%s)",
                input_path,
                error_message,
                error_type,
            )
            raise RuntimeError(error_message)
        if event_type == "finish":
            result_event = dict(event)
            result_event["logs"] = list(task.logs)

    if result_event is None:
        logger.error("Translation finished without finish event for %s", input_path)
        raise RuntimeError("Translation did not complete")

    return result_event


def _maybe_str(path_value: Any) -> str | None:
    if not path_value:
        return None
    return str(path_value)


def _build_zip_payload(result_event: dict[str, Any]) -> bytes:
    translate_result = result_event.get("translate_result")
    if translate_result is None:
        raise RuntimeError("Missing translation result")

    attachments: dict[str, Path] = {}
    for attr, name in (
        ("mono_pdf_path", "mono.pdf"),
        ("dual_pdf_path", "dual.pdf"),
        ("no_watermark_mono_pdf_path", "mono.nowatermark.pdf"),
        ("no_watermark_dual_pdf_path", "dual.nowatermark.pdf"),
        ("auto_extracted_glossary_path", "glossary.csv"),
    ):
        file_path = getattr(translate_result, attr, None)
        if file_path:
            path_obj = Path(file_path)
            if path_obj.exists():
                attachments[name] = path_obj

    metadata = {
        "original_pdf": _maybe_str(
            getattr(translate_result, "original_pdf_path", None)
        ),
        "total_seconds": getattr(translate_result, "total_seconds", None),
        "peak_memory_usage": getattr(translate_result, "peak_memory_usage", None),
        "files": list(attachments.keys()),
        "mono_pdf": _maybe_str(getattr(translate_result, "mono_pdf_path", None)),
        "dual_pdf": _maybe_str(getattr(translate_result, "dual_pdf_path", None)),
        "no_watermark_mono_pdf": _maybe_str(
            getattr(translate_result, "no_watermark_mono_pdf_path", None)
        ),
        "no_watermark_dual_pdf": _maybe_str(
            getattr(translate_result, "no_watermark_dual_pdf_path", None)
        ),
        "auto_extracted_glossary": _maybe_str(
            getattr(translate_result, "auto_extracted_glossary_path", None)
        ),
    }

    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        archive.writestr(
            "metadata.json", json.dumps(metadata, ensure_ascii=False, indent=2)
        )
        for arc_name, path in attachments.items():
            archive.write(path, arcname=arc_name)
    buffer.seek(0)
    return buffer.getvalue()


async def _persist_upload(upload: UploadFile, destination: Path) -> int:
    total_bytes = 0
    try:
        with destination.open("wb") as output_file:
            while True:
                chunk = await upload.read(UPLOAD_CHUNK_SIZE)
                if not chunk:
                    break
                output_file.write(chunk)
                total_bytes += len(chunk)
    finally:
        with contextlib.suppress(Exception):
            await upload.close()
    return total_bytes


def _serialize_task(task: TaskRecord) -> dict[str, Any]:
    # 计算进度信息
    progress_info = calculate_translation_progress(task.logs)

    return {
        "task_id": task.id,
        "state": task.state.value,
        "created_at": task.created_at.isoformat(),
        "updated_at": task.updated_at.isoformat(),
        "error": task.error,
        "result_available": task.result_event is not None,
        "logs": task.logs,
        "progress": progress_info,
    }


async def _execute_task(task: TaskRecord) -> None:
    task.state = TaskState.RUNNING
    task.updated_at = datetime.now(timezone.utc)

    try:
        await _acquire_slot(EXEC_TIMEOUT)
        try:
            settings = task.settings.clone()
            settings.translation.output = str(task.output_dir)
            settings.basic.input_files = set()
            try:
                settings.validate_settings()
            except ValueError as exc:
                raise RuntimeError(str(exc)) from exc

            result_event = await _stream_translation(settings, task.input_path, task)
            task.result_event = result_event
            task.state = TaskState.SUCCEEDED
        finally:
            _release_slot()
    except Exception as exc:  # noqa: BLE001
        task.error = str(exc)
        task.state = TaskState.FAILED
        logger.exception("Task %s failed", task.id)
    finally:
        task.updated_at = datetime.now(timezone.utc)
        task.event.set()


async def _task_worker_loop() -> None:
    while True:
        task = await TASK_QUEUE.get()

        async def _run_task(record: TaskRecord) -> None:
            try:
                await _execute_task(record)
            finally:
                TASK_QUEUE.task_done()

        worker = asyncio.create_task(_run_task(task))
        ACTIVE_TASKS.add(worker)

        def _cleanup_completed(finished: asyncio.Task[None]) -> None:
            ACTIVE_TASKS.discard(finished)

        worker.add_done_callback(_cleanup_completed)


def _cleanup_task(task: TaskRecord) -> None:
    if task.tmp_dir.exists():
        shutil.rmtree(task.tmp_dir, ignore_errors=True)


def _get_active_tasks_count() -> int:
    return sum(
        1
        for task in TASKS.values()
        if task.state in {TaskState.QUEUED, TaskState.RUNNING}
    )


@app.post("/v1/translate")
async def translate_pdf(
    file: UploadFile = File(...),
    settings_json: str = Form("{}"),
    wait: bool = False,
    wait_timeout: float | None = None,
):
    if QUEUE_MAX_SIZE and _get_active_tasks_count() >= QUEUE_MAX_SIZE:
        raise HTTPException(status_code=503, detail="Queue is full")

    try:
        overrides_raw = json.loads(settings_json)
        if not isinstance(overrides_raw, dict):
            raise ValueError("settings must be a JSON object")
    except (json.JSONDecodeError, ValueError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    settings = _build_settings(overrides_raw)

    suffix = Path(file.filename or "uploaded.pdf").suffix or ".pdf"
    tmp_dir = Path(tempfile.mkdtemp(prefix="pdf2zh_next_"))
    input_path = tmp_dir / f"input{suffix}"
    output_dir = tmp_dir / "output"
    output_dir.mkdir(parents=True, exist_ok=True)

    bytes_written = await _persist_upload(file, input_path)
    if bytes_written == 0:
        shutil.rmtree(tmp_dir, ignore_errors=True)
        raise HTTPException(status_code=400, detail="Uploaded file is empty")

    settings = settings.clone()
    settings.basic.input_files = set()
    settings.translation.output = str(output_dir)

    try:
        settings.validate_settings()
    except ValueError as exc:
        shutil.rmtree(tmp_dir, ignore_errors=True)
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    task_id = uuid4().hex
    now = datetime.now(timezone.utc)
    task = TaskRecord(
        id=task_id,
        state=TaskState.QUEUED,
        created_at=now,
        updated_at=now,
        settings=settings,
        tmp_dir=tmp_dir,
        input_path=input_path,
        output_dir=output_dir,
    )
    TASKS[task_id] = task
    await TASK_QUEUE.put(task)

    if wait:
        try:
            timeout = wait_timeout
            if timeout is None and EXEC_TIMEOUT is not None:
                timeout = EXEC_TIMEOUT
            if timeout is None:
                await task.event.wait()
            else:
                await asyncio.wait_for(task.event.wait(), timeout=timeout)
        except asyncio.TimeoutError as exc:
            raise HTTPException(status_code=202, detail="Task queued") from exc

        if task.state == TaskState.SUCCEEDED and task.result_event:
            zip_payload = _build_zip_payload(task.result_event)
            headers = {"Content-Disposition": "attachment; filename=translation.zip"}
            return StreamingResponse(
                io.BytesIO(zip_payload),
                media_type="application/zip",
                headers=headers,
            )
        if task.state == TaskState.FAILED:
            raise HTTPException(status_code=500, detail=task.error or "Task failed")

    return JSONResponse(
        status_code=202,
        content={
            "task_id": task_id,
            "status": task.state.value,
            "status_url": f"/v1/tasks/{task_id}",
            "result_url": f"/v1/tasks/{task_id}/result",
        },
    )


@app.get("/v1/tasks/{task_id}")
async def get_task(task_id: str):
    task = TASKS.get(task_id)
    if task is None:
        raise HTTPException(status_code=404, detail="Task not found")
    return _serialize_task(task)


@app.get("/v1/tasks/{task_id}/progress")
async def get_task_progress(task_id: str):
    """获取任务的详细进度信息"""
    task = TASKS.get(task_id)
    if task is None:
        raise HTTPException(status_code=404, detail="Task not found")

    # 计算进度信息
    progress_info = calculate_translation_progress(task.logs)

    return JSONResponse(
        {
            "task_id": task_id,
            "state": task.state.value,
            "progress": progress_info,
            "updated_at": task.updated_at.isoformat(),
        }
    )


@app.get("/v1/tasks/{task_id}/result")
async def get_task_result(task_id: str, cleanup: bool = False):
    task = TASKS.get(task_id)
    if task is None:
        raise HTTPException(status_code=404, detail="Task not found")
    if task.state in {TaskState.QUEUED, TaskState.RUNNING}:
        raise HTTPException(status_code=409, detail="Task still running")
    if task.state == TaskState.FAILED:
        raise HTTPException(status_code=500, detail=task.error or "Task failed")
    if task.result_event is None:
        raise HTTPException(status_code=500, detail="Result not available")

    zip_payload = _build_zip_payload(task.result_event)
    if cleanup:
        _cleanup_task(task)
        TASKS.pop(task_id, None)

    headers = {"Content-Disposition": f"attachment; filename=translation-{task_id}.zip"}
    return StreamingResponse(
        io.BytesIO(zip_payload), media_type="application/zip", headers=headers
    )


@app.delete("/v1/tasks/{task_id}")
async def delete_task(task_id: str):
    task = TASKS.pop(task_id, None)
    if task is None:
        raise HTTPException(status_code=404, detail="Task not found")
    if task.state in {TaskState.QUEUED, TaskState.RUNNING}:
        raise HTTPException(status_code=409, detail="Cannot delete running task")
    _cleanup_task(task)
    return JSONResponse({"task_id": task_id, "deleted": True})


@app.post("/v1/system/warmup")
async def warmup_system():
    try:
        await babeldoc_assets.async_warmup()
    except SystemExit as exc:  # pragma: no cover
        raise HTTPException(status_code=500, detail="Warmup failed") from exc
    return JSONResponse({"status": "completed"})


@app.post("/v1/system/offline-assets/generate")
async def generate_offline_assets(directory: str | None = None):
    output_dir = _resolve_optional_path(directory)
    try:
        await babeldoc_assets.generate_offline_assets_package_async(output_dir)
    except SystemExit as exc:  # pragma: no cover
        raise HTTPException(
            status_code=500, detail="Failed to generate offline assets"
        ) from exc

    assets_tag = babeldoc_assets.get_offline_assets_tag()
    if output_dir is None:
        output_path = babeldoc_assets.get_cache_file_path(
            f"offline_assets_{assets_tag}.zip", "assets"
        )
    else:
        output_path = output_dir / f"offline_assets_{assets_tag}.zip"

    return JSONResponse(
        {
            "status": "completed",
            "output_path": str(output_path),
            "assets_tag": assets_tag,
        }
    )


@app.post("/v1/system/offline-assets/restore")
async def restore_offline_assets(path: str | None = None):
    input_path = _resolve_optional_path(path)
    try:
        await babeldoc_assets.restore_offline_assets_package_async(input_path)
    except SystemExit as exc:  # pragma: no cover
        raise HTTPException(
            status_code=500, detail="Failed to restore offline assets"
        ) from exc

    effective_path: Path
    if input_path is None:
        assets_tag = babeldoc_assets.get_offline_assets_tag()
        effective_path = babeldoc_assets.get_cache_file_path(
            f"offline_assets_{assets_tag}.zip", "assets"
        )
    else:
        effective_path = input_path

    return JSONResponse(
        {
            "status": "completed",
            "source_path": str(effective_path),
        }
    )


@app.get("/v1/config/schema")
async def get_config_schema():
    schema = CLIEnvSettingsModel.model_json_schema()
    defaults = DEFAULT_CLI_SETTINGS.model_dump(mode="json")
    engines = [
        {
            "translate_engine_type": metadata.translate_engine_type,
            "cli_flag_name": metadata.cli_flag_name,
            "cli_detail_field_name": metadata.cli_detail_field_name,
            "support_llm": metadata.support_llm,
        }
        for metadata in sorted(
            TRANSLATION_ENGINE_METADATA_MAP.values(),
            key=lambda m: m.translate_engine_type,
        )
    ]
    return JSONResponse(
        {
            "schema": schema,
            "defaults": defaults,
            "translation_engines": engines,
        }
    )


@app.get("/v1/health")
async def health_check():
    return JSONResponse(
        {
            "status": "ok",
            "max_concurrency": MAX_CONCURRENCY,
            "queue_limit": QUEUE_MAX_SIZE or None,
            "queue_size": _get_active_tasks_count(),
            "version": __version__,
        }
    )
