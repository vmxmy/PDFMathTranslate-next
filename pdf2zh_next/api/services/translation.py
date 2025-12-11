"""翻译服务"""
import asyncio
import json
import logging
import shutil
import zipfile
from datetime import datetime
from datetime import timedelta
from pathlib import Path
from typing import Any
from uuid import uuid4

from fastapi import UploadFile

from pdf2zh_next.config.model import SettingsModel
from pdf2zh_next.high_level import do_translate_async_stream

from ..exceptions import BadRequestException
from ..exceptions import FileFormatException
from ..exceptions import InternalServerException
from ..exceptions import NotFoundException
from ..exceptions import TranslationEngineException
from ..models import BatchOperationRequest
from ..models import CleanupResult
from ..models import TranslationEngine
from ..models import TranslationFile
from ..models import TranslationPreview
from ..models import TranslationPreviewRequest
from ..models import TranslationProgress
from ..models import TranslationRequest
from ..models import TranslationResult
from ..models import TranslationTask
from ..models.enums import TaskStatus
from ..models.enums import TranslationStage
from ..models.enums import UserRole
from ..utils import ENGINE_TYPE_MAP
from ..utils import build_settings_model
from .config import config_service
from ..settings import api_settings
from .task_manager import task_manager

logger = logging.getLogger(__name__)


class TranslationService:
    """翻译服务"""
    def __init__(self):
        self.supported_formats = set(api_settings.api_supported_formats)
        self.max_file_size = api_settings.api_max_file_size
        labels = api_settings.api_engine_labels
        self.engines = {
            TranslationEngine.GOOGLE: labels.get("google", "Google 翻译"),
            TranslationEngine.DEEPL: labels.get("deepl", "DeepL 翻译"),
            TranslationEngine.OPENAI: labels.get("openai", "OpenAI 翻译"),
            TranslationEngine.OPENAI_COMPATIBLE: labels.get("openaicompatible", "OpenAI 兼容"),
            TranslationEngine.BAIDU: labels.get("baidu", "百度翻译"),
            TranslationEngine.TENCENT: labels.get("tencent", "腾讯翻译"),
            TranslationEngine.SILICONFLOWFREE: labels.get("siliconflowfree", "SiliconFlow Free"),
        }
        self.storage_root = api_settings.api_storage_root
        self.seconds_per_mb = api_settings.api_seconds_per_mb
        self.estimate_min_seconds = api_settings.api_estimate_min_seconds
        self.estimate_max_seconds = api_settings.api_estimate_max_seconds
        self.preview_confidence = api_settings.api_preview_confidence
        self.artifact_expire_days = api_settings.api_artifact_expire_days
        self.task_dirs: dict[str, Path] = {}
        self.task_configs: dict[str, dict[str, Any]] = {}
        self.file_registry: dict[str, dict[str, Path]] = {}
        self.task_settings: dict[str, SettingsModel] = {}
        self.task_inputs: dict[str, Path] = {}
        self.storage_root.mkdir(parents=True, exist_ok=True)
        task_manager.register_translation_service(self)

    async def create_task(
        self,
        request: TranslationRequest,
        user_info: dict[str, Any]
    ) -> TranslationTask:
        """创建翻译任务"""
        logger.info(f"开始创建翻译任务，用户：{user_info['user_id']}")
        task = None
        try:
            # 如果未指定引擎，回退到配置默认
            if request.translation_engine is None:
                cfg_default = (
                    config_service.get_config().current_config.get("translation", {})
                )
                request.translation_engine = cfg_default.get(
                    "default_engine", TranslationEngine.GOOGLE.value
                )

            logger.info("验证翻译引擎参数")
            if isinstance(request.translation_engine, str):
                try:
                    logger.info(f"转换字符串引擎：{request.translation_engine}")
                    request.translation_engine = TranslationEngine(
                        request.translation_engine.lower()
                    )
                except ValueError as exc:
                    logger.error(f"不支持的翻译引擎：{request.translation_engine}")
                    raise BadRequestException(
                        message=f"不支持的翻译引擎：{request.translation_engine}",
                        details={"supported_engines": list(self.engines.keys())},
                    ) from exc

            # 验证文件
            logger.info("开始验证文件")
            await self._validate_files(request.files, user_info)
            logger.info("文件验证成功")

            # 验证翻译引擎
            logger.info(f"验证翻译引擎：{request.translation_engine}")
            if request.translation_engine not in self.engines:
                logger.error(f"不支持的翻译引擎：{request.translation_engine}")
                raise BadRequestException(
                    message=f"不支持的翻译引擎：{request.translation_engine}",
                    details={"supported_engines": list(self.engines.keys())}
                )
            logger.info("翻译引擎验证成功")

            # 估算处理时间
            logger.info("估算处理时间")
            estimated_duration = await self._estimate_processing_time(request.files)

            # 创建任务
            logger.info("创建任务记录")
            task = await task_manager.create_task(
                user_id=user_info["user_id"],
                priority=request.priority,
                estimated_duration=estimated_duration
            )
            logger.info(f"任务记录创建成功：{task.task_id}")

            # 保存文件
            logger.info(f"开始保存文件：{task.task_id}")
            await self._save_files(task.task_id, request.files)
            logger.info(f"文件保存成功：{task.task_id}")

            # 保存任务配置
            logger.info(f"开始保存任务配置：{task.task_id}")
            await self._save_task_config(task.task_id, request)
            logger.info(f"任务配置保存成功：{task.task_id}")

            # 验证任务是否真正创建成功
            if not await self._verify_task_created(task.task_id):
                logger.error(f"任务创建验证失败：{task.task_id}")
                await self.cleanup_task(task.task_id)
                raise InternalServerException(
                    message="任务创建验证失败",
                    details={"task_id": task.task_id}
                )

            logger.info(f"创建翻译任务成功：{task.task_id}, 用户：{user_info['user_id']}")
            return task

        except Exception as exc:
            logger.exception(f"创建翻译任务失败：{exc}")
            if task:
                logger.info(f"清理失败任务：{task.task_id}")
                # 清理已创建的任务相关数据
                try:
                    await self.cleanup_task(task.task_id)
                except Exception as cleanup_exc:
                    logger.error(f"清理任务失败：{task.task_id}, 错误：{cleanup_exc}")

            if isinstance(exc, (FileFormatException, BadRequestException)):
                raise
            raise InternalServerException(
                message="创建翻译任务失败",
                details={"error": str(exc)}
            ) from exc

    async def get_task(self, task_id: str, user_info: dict[str, Any]) -> TranslationTask:
        """获取任务状态"""
        return await task_manager.get_task(task_id, user_info["user_id"])

    async def get_task_progress(self, task_id: str, user_info: dict[str, Any]) -> TranslationProgress:
        """获取任务进度"""
        task = await task_manager.get_task(task_id, user_info["user_id"])
        return task.progress

    async def get_task_result(self, task_id: str, user_info: dict[str, Any]) -> TranslationResult:
        """获取任务结果"""
        task = await task_manager.get_task(task_id, user_info["user_id"])

        if task.status != "completed":
            raise BadRequestException(
                message=f"任务 {task_id} 尚未完成，无法获取结果"
            )

        if not task.result:
            raise InternalServerException(
                message=f"任务 {task_id} 完成但无结果数据"
            )

        if not task.result.files:
            raise NotFoundException(
                message="翻译结果已清理或不存在，请重新执行任务",
                resource="translation_file",
                resource_id=task_id,
            )

        return task.result

    async def cancel_task(self, task_id: str, user_info: dict[str, Any]) -> bool:
        """取消任务"""
        return await task_manager.cancel_task(task_id, user_info["user_id"])

    async def delete_task(self, task_id: str, user_info: dict[str, Any]) -> bool:
        """删除任务并清理产物"""
        task = await task_manager.get_task(task_id, user_info["user_id"])
        if task.status not in {TaskStatus.COMPLETED, TaskStatus.FAILED}:
            raise BadRequestException(message="任务尚未结束，无法删除")

        await self.clean_task_artifacts(task_id, user_info)
        return await task_manager.delete_task(task_id, user_info["user_id"])

    async def list_tasks(
        self,
        user_info: dict[str, Any],
        page: int = 1,
        page_size: int = 20,
        **filters
    ) -> dict[str, Any]:
        """列出用户任务"""
        from ..models import TaskFilterRequest

        filter_request = TaskFilterRequest(**filters)
        return await task_manager.list_tasks(
            user_info["user_id"],
            filter_request,
            page,
            page_size
        )

    async def batch_operation(
        self,
        request: BatchOperationRequest,
        user_info: dict[str, Any]
    ) -> dict[str, Any]:
        """批量操作任务"""
        return await task_manager.batch_operation(request, user_info["user_id"])

    async def get_statistics(self, user_info: dict[str, Any]) -> dict[str, Any]:
        """获取用户统计信息"""
        return await task_manager.get_statistics(user_info["user_id"])

    async def preview_translation(
        self,
        request: TranslationPreviewRequest,
        user_info: dict[str, Any]
    ) -> TranslationPreview:
        """预览翻译结果"""
        try:
            # 调用翻译引擎进行预览
            translated_text = await self._translate_text(
                text=request.text,
                source_language=request.source_language,
                target_language=request.target_language,
                engine=request.translation_engine
            )

            preview = TranslationPreview(
                original_text=request.text,
                translated_text=translated_text,
                source_language=request.source_language or "auto",
                target_language=request.target_language,
                engine_used=request.translation_engine,
                confidence=self.preview_confidence,  # TODO: 从翻译引擎获取置信度
            )

            logger.info(f"翻译预览成功：用户 {user_info['user_id']}, 引擎 {request.translation_engine}")
            return preview

        except Exception as exc:
            logger.error(f"翻译预览失败：{exc}")
            raise TranslationEngineException(
                message="翻译预览失败",
                engine=request.translation_engine,
                details={"error": str(exc)}
            ) from exc

    async def _validate_files(self, files: list[UploadFile], user_info: dict[str, Any]):
        """验证文件"""
        if not files:
            raise BadRequestException(message="必须上传至少一个文件")

        total_size = 0
        for file in files:
            # 检查文件格式
            file_ext = Path(file.filename).suffix.lower()
            if file_ext not in self.supported_formats:
                raise FileFormatException(
                    message=f"不支持的文件格式：{file_ext}",
                    file_name=file.filename,
                    supported_formats=list(self.supported_formats)
                )

            # 检查文件大小
            file_size = await self._get_file_size(file)
            total_size += file_size

            if file_size > self.max_file_size:
                raise BadRequestException(
                    message=f"文件 {file.filename} 大小超过限制：{file_size / (1024*1024):.1f}MB > {self.max_file_size / (1024*1024):.1f}MB"
                )

            # 检查用户配额
            if total_size > user_info.get("max_file_size", self.max_file_size):
                raise BadRequestException(
                    message="总文件大小超过用户配额限制"
                )

    async def _get_file_size(self, file: UploadFile) -> int:
        """获取文件大小"""
        # 保存当前位置
        current_pos = await file.read(0)

        # 移动到文件末尾
        size = 0
        while True:
            chunk = await file.read(8192)
            if not chunk:
                break
            size += len(chunk)

        # 重置文件指针
        await file.seek(0)
        return size

    async def _estimate_processing_time(self, files: list[UploadFile]) -> int:
        """估算处理时间"""
        total_size = 0
        for file in files:
            size = await self._get_file_size(file)
            total_size += size

        # 基于文件大小估算处理时间（粗略估算）
        estimated_seconds = int((total_size / (1024 * 1024)) * self.seconds_per_mb)

        return max(self.estimate_min_seconds, min(estimated_seconds, self.estimate_max_seconds))

    async def _save_files(self, task_id: str, files: list[UploadFile]):
        """保存上传的源文件到任务目录"""
        task_dir = self.storage_root / task_id
        input_dir = task_dir / "input"
        input_dir.mkdir(parents=True, exist_ok=True)

        saved_files = []
        for uploaded in files:
            target_path = input_dir / uploaded.filename
            content = await uploaded.read()
            target_path.write_bytes(content)
            await uploaded.seek(0)
            saved_files.append(target_path)

        self.task_dirs[task_id] = task_dir
        self.file_registry.setdefault(task_id, {})
        if saved_files:
            self.task_inputs[task_id] = saved_files[0]

        logger.info(
            "保存任务文件：%s, 文件数：%s, 路径：%s",
            task_id,
            len(saved_files),
            input_dir,
        )

    async def _save_task_config(self, task_id: str, request: TranslationRequest):
        """保存任务配置"""
        logger.info(f"开始保存任务配置：{task_id}")

        try:
            task_dir = self.task_dirs.get(task_id)
            if not task_dir:
                logger.info(f"创建任务目录：{task_id}")
                task_dir = self.storage_root / task_id
                task_dir.mkdir(parents=True, exist_ok=True)
                self.task_dirs[task_id] = task_dir
            else:
                logger.info(f"使用已存在的任务目录：{task_dir}")

            logger.info(f"构建配置对象：{task_id}")
            engine_value = (
                request.translation_engine.value
                if isinstance(request.translation_engine, TranslationEngine)
                else request.translation_engine
            )

            config = {
                "target_language": request.target_language,
                "source_language": request.source_language,
                "translation_engine": engine_value,
                "preserve_formatting": request.preserve_formatting,
                "translate_tables": request.translate_tables,
                "translate_equations": request.translate_equations,
                "disable_rapidocr": request.disable_rapidocr,
                "custom_glossary": request.custom_glossary,
                "webhook_url": request.webhook_url,
                "priority": request.priority,
                "timeout": request.timeout,
                "settings_json": request.settings_json,
            }

            logger.info(f"写入配置文件：{task_id}")
            config_path = task_dir / "task_config.json"
            config_path.write_text(json.dumps(config, ensure_ascii=False, indent=2))
            self.task_configs[task_id] = config
            logger.info(f"保存任务配置成功：{task_id}")

            logger.info(f"开始初始化任务设置：{task_id}")
            self._initialize_task_settings(task_id, request)
            logger.info(f"任务配置和设置初始化完成：{task_id}")

        except Exception as exc:
            logger.exception(f"保存任务配置失败：{task_id}, 错误：{exc}")
            raise

    async def _translate_text(
        self,
        text: str,
        source_language: str | None,
        target_language: str,
        engine: TranslationEngine
    ) -> str:
        """翻译文本"""
        # TODO: 集成实际的翻译引擎
        # 这里应该调用配置的翻译引擎 API

        # 模拟翻译过程
        await asyncio.sleep(1)

        # 返回模拟的翻译结果
        if "hello" in text.lower():
            return text.replace("hello", "你好").replace("Hello", "你好")
        elif "world" in text.lower():
            return text.replace("world", "世界").replace("World", "世界")
        else:
            return f"[{target_language}] {text}"

    async def _notify_webhook(self, task_id: str, webhook_url: str, status: str):
        """通知 webhook"""
        # TODO: 实现 webhook 通知逻辑
        logger.info(f"通知 webhook: {webhook_url}, 任务：{task_id}, 状态：{status}")

    async def execute_task(self, task: TranslationTask) -> TranslationResult:
        """执行真实翻译流程并返回结果"""
        task_id = task.task_id
        settings = self.task_settings.get(task_id)
        input_path = self.task_inputs.get(task_id)
        if not settings or not input_path:
            await self._wait_for_task_materialized(task_id)
            settings = self.task_settings.get(task_id)
            input_path = self.task_inputs.get(task_id)
        if not settings or not input_path:
            raise InternalServerException(
                message="任务配置缺失",
                details={"task_id": task_id},
            )

        output_dir = self.task_dirs.get(task_id, self.storage_root / task_id) / "output"
        output_dir.mkdir(parents=True, exist_ok=True)

        settings = settings.clone()
        settings.translation.output = str(output_dir)
        settings.basic.input_files = set()

        translate_result = None
        unknown_event_logged = 0
        try:
            await task_manager.update_task_progress(
                task_id, TranslationStage.PARSING, 15.0, "解析 PDF"
            )
            await task_manager.update_task_progress(
                task_id, TranslationStage.TRANSLATING, 60.0, "翻译进行中"
            )
            last_progress_details: dict[str, Any] | None = None
            async for event in do_translate_async_stream(settings, input_path):
                event_type = event.get("type")
                progress_candidate = (
                    event_type in {"progress", "progress_start", "stage_summary"}
                    or "page" in event
                    or "current_page" in event
                    or "total_pages" in event
                    or "pages_total" in event
                    or "overall_progress" in event
                    or "stage_progress" in event
                )
                if progress_candidate:
                    progress_value, progress_details = self._extract_progress_from_event(event)
                    if progress_value is not None or progress_details:
                        logger.info(
                            "翻译进度：task=%s | stage=%s | progress=%s | page=%s/%s",
                            task_id,
                            (progress_details or {}).get("stage", "translating"),
                            f"{progress_value:.2f}" if progress_value is not None else "n/a",
                            (progress_details or {}).get("page"),
                            (progress_details or {}).get("total_pages"),
                        )
                        await task_manager.update_task_progress(
                            task_id,
                            TranslationStage.TRANSLATING,
                            progress_value if progress_value is not None else 60.0,
                            "翻译进行中",
                            details=progress_details or None,
                        )
                        last_progress_details = progress_details
                    continue
                if event_type == "log":
                    logger.log(
                        getattr(logging, event.get("level", "INFO"), logging.INFO),
                        "翻译日志：task=%s | message=%s",
                        task_id,
                        event.get("message"),
                    )
                    continue
                if unknown_event_logged < 5:
                    logger.info(
                        "未识别的翻译事件：task=%s | type=%s | keys=%s | sample=%s",
                        task_id,
                        event_type,
                        list(event.keys()),
                        {k: event[k] for k in list(event.keys())[:5]},
                    )
                    unknown_event_logged += 1
                if event_type == "error":
                    error_message = event.get("error", "Unknown error")
                    raise TranslationEngineException(
                        message="翻译过程出现错误",
                        details={"error": error_message},
                    )
                if event_type == "finish":
                    translate_result = event.get("translate_result")
                    break
        except TranslationEngineException:
            raise
        except Exception as exc:  # noqa: BLE001
            logger.exception("任务执行失败：%s", exc)
            raise TranslationEngineException(
                message="翻译流程异常",
                details={"error": str(exc)},
            ) from exc

        if translate_result is None:
            raise InternalServerException(
                message="翻译流程未返回结果",
                details={"task_id": task_id},
            )

        await task_manager.update_task_progress(
            task_id, TranslationStage.COMPOSING, 85.0, "生成译文"
        )

        result = self._build_translation_result(task_id, translate_result, settings)
        await task_manager.complete_task(task_id, result)
        self.task_settings.pop(task_id, None)
        return result

    def _build_translation_result(
        self,
        task_id: str,
        translate_result: Any,
        settings: SettingsModel,
    ) -> TranslationResult:
        files: list[TranslationFile] = []
        registry = self.file_registry.setdefault(task_id, {})
        artifact_sources: list[Path] = []
        config = self.task_configs.get(task_id, {})
        now = datetime.now()

        attachment_map = [
            ("mono_pdf_path", "mono.pdf"),
            ("dual_pdf_path", "dual.pdf"),
            ("no_watermark_mono_pdf_path", "mono.nowatermark.pdf"),
            ("no_watermark_dual_pdf_path", "dual.nowatermark.pdf"),
            ("auto_extracted_glossary_path", "glossary.csv"),
        ]

        for attr, _default_name in attachment_map:
            path_str = getattr(translate_result, attr, None)
            if not path_str:
                continue
            file_path = Path(path_str)
            if not file_path.exists():
                continue
            file_id = f"{uuid4().hex}"
            registry[file_id] = file_path
            artifact_sources.append(file_path)
            files.append(
                TranslationFile(
                    file_id=file_id,
                    original_name=file_path.name,
                    translated_name=file_path.name,
                    size=file_path.stat().st_size,
                    page_count=getattr(translate_result, "total_pages", 0) or 0,
                    download_url=
                    f"/v1/translations/{task_id}/files/{file_id}/download",
                    expires_at=now + timedelta(days=self.artifact_expire_days),
                )
            )

        engine_name = settings.translate_engine_settings.translate_engine_type
        engine_mapping = {v: k for k, v in ENGINE_TYPE_MAP.items()}
        engine_key = engine_mapping.get(engine_name)
        if not engine_key and isinstance(config.get("translation_engine"), TranslationEngine):
            engine_key = config["translation_engine"].value
        elif not engine_key and isinstance(config.get("translation_engine"), str):
            try:
                engine_key = TranslationEngine(config["translation_engine"].lower()).value
            except ValueError:
                engine_key = None
        if not engine_key:
            try:
                engine_key = TranslationEngine(engine_name.lower()).value
            except ValueError:
                engine_key = TranslationEngine.GOOGLE.value
        engine_used = TranslationEngine(engine_key)

        logger.debug(
            "Building translation result | task=%s | engine_name=%s | engine_key=%s | config_engine=%s",
            task_id,
            engine_name,
            engine_key,
            config.get("translation_engine"),
        )

        if artifact_sources:
            unique_sources: dict[str, Path] = {}
            for path in artifact_sources:
                try:
                    key = str(path.resolve())
                except OSError:
                    key = str(path)
                if key not in unique_sources:
                    unique_sources[key] = path

            zip_filename = "artifacts.zip"
            zip_path = (Path(settings.translation.output) if settings.translation.output else Path.cwd()) / zip_filename
            zip_path.parent.mkdir(parents=True, exist_ok=True)
            if zip_path.exists():
                zip_path.unlink()
            with zipfile.ZipFile(zip_path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
                for source in unique_sources.values():
                    if source.exists():
                        archive.write(source, arcname=source.name)

            zip_file_id = f"{uuid4().hex}"
            registry[zip_file_id] = zip_path
            files.insert(
                0,
                TranslationFile(
                    file_id=zip_file_id,
                    original_name=zip_path.name,
                    translated_name=zip_path.name,
                    size=zip_path.stat().st_size,
                    page_count=0,
                    download_url=
                    f"/v1/translations/{task_id}/files/{zip_file_id}/download",
                    expires_at=now + timedelta(days=self.artifact_expire_days),
                ),
            )

        def _extract_metric(obj: Any, names: tuple[str, ...], default: int = 0) -> int:
            for name in names:
                value = getattr(obj, name, None)
                if isinstance(value, (int, float)) and value > 0:
                    return int(value)
            return default

        total_pages = _extract_metric(
            translate_result,
            ("total_pages", "page_count", "pages", "num_pages"),
            default=0,
        )
        total_chars = _extract_metric(
            translate_result,
            ("total_characters", "character_count", "total_chars"),
            default=0,
        )

        def _summarize_attr(name: str) -> str:
            value = getattr(translate_result, name, None)
            if value is None:
                return "missing"
            if isinstance(value, dict):
                return f"dict[{len(value)}]"
            if isinstance(value, (list, tuple, set)):
                return f"sequence[{len(value)}]"
            if isinstance(value, (int, float)):
                return str(value)
            return type(value).__name__

        logger.debug(
            "Translation metrics | task=%s | pages=%s | chars=%s | available_attrs=%s",
            task_id,
            total_pages,
            total_chars,
            {
                name: _summarize_attr(name)
                for name in (
                    "total_pages",
                    "page_count",
                    "pages",
                    "num_pages",
                    "total_characters",
                    "character_count",
                    "total_chars",
                )
            },
        )

        if total_pages > 0:
            for translation_file in files:
                if translation_file.page_count == 0:
                    translation_file.page_count = total_pages

        return TranslationResult(
            files=files,
            processing_time=getattr(translate_result, "total_seconds", 0.0) or 0.0,
            total_pages=total_pages,
            total_chars=total_chars,
            engine_used=engine_used,
            quality_score=getattr(translate_result, "quality", None),
            warnings=[],
        )

    async def get_translated_file_path(
        self, task_id: str, file_id: str, user_info: dict[str, Any]
    ) -> Path:
        """获取可下载的翻译文件路径，检查用户权限"""
        await task_manager.get_task(task_id, user_info["user_id"])
        task_files = self.file_registry.get(task_id, {})
        path = task_files.get(file_id)
        if not path or not path.exists():
            raise NotFoundException(message="翻译文件不存在", resource="translation_file")
        return path

    async def clean_task_artifacts(self, task_id: str, user_info: dict[str, Any]) -> CleanupResult:
        """清理指定任务的临时与输出文件并返回详细状态"""

        allow_admin_override = user_info.get("role") == UserRole.ADMIN
        task_exists = False
        file_exists = False

        task_dir = self.task_dirs.get(task_id, self.storage_root / task_id)
        if task_dir.exists():
            file_exists = True

        try:
            task = await task_manager.get_task(task_id, user_info["user_id"])
            task_exists = True
        except NotFoundException as exc:
            if file_exists and allow_admin_override:
                shutil.rmtree(task_dir, ignore_errors=True)
                self.task_dirs.pop(task_id, None)
                self.task_configs.pop(task_id, None)
                self.file_registry.pop(task_id, None)
                self.task_settings.pop(task_id, None)
                self.task_inputs.pop(task_id, None)

                return CleanupResult(
                    task_exists=False,
                    files_removed=True,
                    message="任务记录丢失，但已清理残留文件",
                    download_links_valid=False,
                )
            message = "任务不存在，且没有发现可清理的文件"
            if file_exists:
                message = "任务不存在，但检测到残留文件；请使用管理员密钥再次清理"
            raise NotFoundException(
                message=message,
                resource="translation_task",
                resource_id=task_id,
            ) from exc

        if task.status not in {
            TaskStatus.COMPLETED,
            TaskStatus.FAILED,
            TaskStatus.CANCELLED,
        }:
            raise BadRequestException(message="任务尚未结束，无法清理")

        files_removed = False
        if task_dir.exists():
            shutil.rmtree(task_dir, ignore_errors=True)
            files_removed = True

        self.task_dirs.pop(task_id, None)
        self.task_configs.pop(task_id, None)
        self.file_registry.pop(task_id, None)
        self.task_settings.pop(task_id, None)
        self.task_inputs.pop(task_id, None)
        download_links_valid = True
        if task_exists and task.result:
            task.result = task.result.model_copy(update={"files": []})
            download_links_valid = False

        return CleanupResult(
            task_exists=task_exists,
            files_removed=files_removed,
            message="任务与文件已清理" if files_removed else "任务存在，未发现可清理文件",
            download_links_valid=download_links_valid,
        )

    def _extract_progress_from_event(
        self, event: dict[str, Any]
    ) -> tuple[float | None, dict[str, Any] | None]:
        """从 BabelDOC 事件中提取进度与页码信息"""
        page = event.get("page") or event.get("current_page")
        total_pages = event.get("total_pages") or event.get("pages_total")
        percent = (
            event.get("progress")
            or event.get("percentage")
            or event.get("percent")
            or event.get("progress_percent")
            or event.get("overall_progress")
            or event.get("stage_progress")
        )

        if percent is None and page is not None and total_pages:
            try:
                percent = float(page) / float(total_pages) * 100.0
            except Exception:
                percent = None

        details: dict[str, Any] = {}
        if page is not None:
            details["page"] = page
        if total_pages is not None:
            details["total_pages"] = total_pages
        stage = event.get("stage") or event.get("status")
        if stage:
            details["stage"] = stage
        if "stage_current" in event:
            details["stage_current"] = event.get("stage_current")
        if "stage_total" in event:
            details["stage_total"] = event.get("stage_total")
        if "part_index" in event:
            details["part_index"] = event.get("part_index")
        if "total_parts" in event:
            details["total_parts"] = event.get("total_parts")

        return percent, details or None

    def _initialize_task_settings(
        self, task_id: str, request: TranslationRequest
    ) -> None:
        logger.info(f"开始初始化任务设置：{task_id}")

        try:
            output_dir = self.task_dirs.get(task_id, self.storage_root / task_id) / "output"
            logger.info(f"输出目录：{output_dir}")

            cfg = config_service.get_config().current_config
            translation_cfg = cfg.get("translation", {})
            logger.info(f"获取翻译配置成功：{task_id}")

            logger.info(f"构建翻译覆盖配置：{task_id}")
            translation_overrides: dict[str, Any] = {
                "translation": {
                    "lang_out": request.target_language,
                },
                "pdf": {
                    "translate_table_text": request.translate_tables,
                    "disable_rapidocr": request.disable_rapidocr,
                },
            }
            if request.source_language:
                translation_overrides["translation"]["lang_in"] = request.source_language
            if not request.preserve_formatting:
                translation_overrides.setdefault("pdf", {})[
                    "disable_rich_text_translate"
                ] = True
            if not request.translate_equations:
                translation_overrides.setdefault("pdf", {})[
                    "no_remove_non_formula_lines"
                ] = True

            logger.info(f"处理额外设置：{task_id}")
            extra_overrides: dict[str, Any] | None = None
            if request.settings_json:
                try:
                    extra_overrides = json.loads(request.settings_json)
                    logger.info(f"解析额外设置成功：{task_id}")
                except json.JSONDecodeError as exc:
                    logger.error(f"settings_json JSON解析失败：{task_id}, 错误：{exc}")
                    raise BadRequestException(
                        message="settings_json 不是合法的 JSON",
                        details={"error": str(exc)},
                    ) from exc
                if extra_overrides is not None and not isinstance(extra_overrides, dict):
                    logger.error(f"settings_json 不是对象类型：{task_id}")
                    raise BadRequestException(
                        message="settings_json 必须是 JSON 对象",
                    )

            # 如果 settings_json 指定了 translate_engine_type，则优先使用该类型
            override_engine = None
            if extra_overrides:
                override_engine = (
                    extra_overrides.get("translate_engine_settings", {})
                    .get("translate_engine_type")
                )

            default_engine = translation_cfg.get("default_engine", "google")
            logger.info(
                f"解析翻译引擎：{task_id}, 请求参数={request.translation_engine}, 覆盖={override_engine}, 默认={default_engine}"
            )
            engine_member = override_engine or request.translation_engine or default_engine
            if isinstance(engine_member, TranslationEngine):
                engine_key_value = engine_member.value
                logger.info(f"使用枚举引擎类型：{engine_key_value}")
            elif isinstance(engine_member, str):
                normalized_engine = engine_member.lower()
                # 兼容 OpenAICompatible 之类的自定义值
                if normalized_engine in ENGINE_TYPE_MAP:
                    engine_key_value = normalized_engine
                    logger.info(f"使用字符串引擎类型：{engine_key_value}")
                else:
                    try:
                        engine_key_value = TranslationEngine(normalized_engine).value
                        logger.info(f"转换字符串引擎类型：{engine_member} -> {engine_key_value}")
                    except ValueError as exc:
                        logger.error(f"不支持的翻译引擎：{engine_member}, 任务：{task_id}")
                        raise BadRequestException(
                            message=f"不支持的翻译引擎：{engine_member}",
                            details={"supported_engines": list(self.engines.keys())},
                        ) from exc
            else:
                logger.error(f"翻译引擎参数类型无效：{type(engine_member)}, 任务：{task_id}")
                raise BadRequestException(
                    message="翻译引擎参数无效",
                    details={"type": str(type(engine_member))},
                )

            logger.info(
                "初始化设置：任务=%s, 引擎=%s", task_id, engine_key_value
            )

            logger.info(f"配置引擎参数：{task_id}")
            engine_key = engine_key_value.lower()
            engine_type = ENGINE_TYPE_MAP.get(engine_key, "Google")
            engine_config = translation_cfg.get("engines", {}).get(engine_key, {})
            engine_payload: dict[str, Any] = {
                "translate_engine_type": engine_type,
            }
            for field, cfg_key in (
                ("openai_api_key", "api_key"),
                ("openai_model", "model"),
                ("deepl_auth_key", "api_key"),
            ):
                if engine_type == "OpenAI" and field.startswith("openai"):
                    value = engine_config.get(cfg_key)
                    if value:
                        engine_payload[field] = value
                if engine_type == "DeepL" and field.startswith("deepl"):
                    value = engine_config.get(cfg_key)
                    if value:
                        engine_payload[field] = value

            logger.info(f"构建设置模型：{task_id}")
            cli_model = build_settings_model(
                translation_overrides,
                engine_payload,
                extra_overrides,
            )
            settings = cli_model.to_settings_model()
            settings.translation.output = str(output_dir)
            settings.basic.input_files = set()
            self.task_settings[task_id] = settings
            logger.info(f"任务设置初始化完成：{task_id}")

        except Exception as exc:
            logger.exception(f"初始化任务设置失败：{task_id}, 错误：{exc}")
            raise

    def _restore_task_runtime(self, task_id: str) -> None:
        """在内存缺失时，从磁盘恢复任务目录、输入文件与设置。"""
        try:
            task_dir = self.storage_root / task_id
            config_path = task_dir / "task_config.json"
            input_dir = task_dir / "input"

            if not task_dir.exists() or not config_path.exists() or not input_dir.exists():
                logger.error("任务目录或配置不存在，无法恢复：%s", task_id)
                return

            self.task_dirs[task_id] = task_dir

            input_files = sorted(input_dir.iterdir())
            if input_files:
                self.task_inputs[task_id] = input_files[0]

            config = json.loads(config_path.read_text(encoding="utf-8"))
            self.task_configs[task_id] = config

            # 构造最小 request 结构用于初始化设置
            from types import SimpleNamespace

            request_stub = SimpleNamespace(
                target_language=config.get("target_language"),
                source_language=config.get("source_language"),
                translation_engine=config.get("translation_engine"),
                preserve_formatting=config.get("preserve_formatting", True),
                translate_tables=config.get("translate_tables", False),
                translate_equations=config.get("translate_equations", True),
                disable_rapidocr=config.get("disable_rapidocr", False),
                custom_glossary=config.get("custom_glossary"),
                webhook_url=config.get("webhook_url"),
                priority=config.get("priority", 1),
                timeout=config.get("timeout"),
                settings_json=config.get("settings_json"),
            )

            self._initialize_task_settings(task_id, request_stub)
            logger.info("任务运行时从磁盘恢复完成：%s", task_id)
        except Exception as exc:  # noqa: BLE001
            logger.exception("恢复任务运行时失败：%s, 错误：%s", task_id, exc)

    async def _wait_for_task_materialized(self, task_id: str, timeout: float = 5.0):
        """
        等待任务的文件和配置落盘/内存就绪，防止工作进程先于创建流程执行。
        """
        deadline = asyncio.get_event_loop().time() + timeout
        while asyncio.get_event_loop().time() < deadline:
            settings = self.task_settings.get(task_id)
            input_path = self.task_inputs.get(task_id)
            if settings and input_path:
                return
            # 尝试从磁盘恢复
            self._restore_task_runtime(task_id)
            settings = self.task_settings.get(task_id)
            input_path = self.task_inputs.get(task_id)
            if settings and input_path:
                return
            await asyncio.sleep(0.1)
        logger.warning("等待任务资源就绪超时：%s", task_id)

    async def _verify_task_created(self, task_id: str) -> bool:
        """验证任务是否真正创建成功"""
        try:
            # 检查任务目录是否存在
            task_dir = self.task_dirs.get(task_id, self.storage_root / task_id)
            if not task_dir.exists():
                logger.error(f"任务目录不存在：{task_dir}")
                return False

            # 检查配置文件是否存在
            config_file = task_dir / "task_config.json"
            if not config_file.exists():
                logger.error(f"任务配置文件不存在：{config_file}")
                return False

            # 检查输入文件是否存在
            input_file = self.task_inputs.get(task_id)
            if not input_file or not input_file.exists():
                logger.error(f"任务输入文件不存在：{input_file}")
                return False

            # 检查任务设置是否存在
            settings = self.task_settings.get(task_id)
            if not settings:
                logger.error(f"任务设置不存在：{task_id}")
                return False

            logger.info(f"任务创建验证成功：{task_id}")
            return True

        except Exception as exc:
            logger.exception(f"任务创建验证异常：{task_id}, 错误：{exc}")
            return False


# 全局翻译服务实例
translation_service = TranslationService()
