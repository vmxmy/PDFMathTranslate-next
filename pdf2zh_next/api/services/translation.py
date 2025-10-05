"""翻译服务"""
import asyncio
import json
import shutil
import tempfile
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional
import logging
from uuid import uuid4

from fastapi import UploadFile

from pdf2zh_next.config.model import SettingsModel
from pdf2zh_next.high_level import do_translate_async_stream

from ..models import (
    TranslationRequest,
    TranslationTask,
    TranslationPreview,
    TranslationProgress,
    TranslationResult,
    TranslationFile,
    TranslationEngine,
    BatchOperationRequest,
    TranslationPreviewRequest,
)
from ..models import CleanupResult
from ..models.enums import UserRole, TranslationStage, TaskStatus
from ..exceptions import (
    FileFormatException,
    TranslationEngineException,
    InternalServerException,
    BadRequestException,
    NotFoundException,
)
from ..utils import build_settings_model, ENGINE_TYPE_MAP
from .config import config_service
from .task_manager import task_manager

logger = logging.getLogger(__name__)


class TranslationService:
    """翻译服务"""
    def __init__(self):
        self.supported_formats = {'.pdf'}
        self.max_file_size = 100 * 1024 * 1024  # 100MB
        self.engines = {
            TranslationEngine.GOOGLE: "Google翻译",
            TranslationEngine.DEEPL: "DeepL翻译",
            TranslationEngine.OPENAI: "OpenAI翻译",
            TranslationEngine.BAIDU: "百度翻译",
            TranslationEngine.TENCENT: "腾讯翻译"
        }
        self.storage_root = Path("storage/tasks")
        self.task_dirs: Dict[str, Path] = {}
        self.task_configs: Dict[str, Dict[str, Any]] = {}
        self.file_registry: Dict[str, Dict[str, Path]] = {}
        self.task_settings: Dict[str, SettingsModel] = {}
        self.task_inputs: Dict[str, Path] = {}
        self.storage_root.mkdir(parents=True, exist_ok=True)
        task_manager.register_translation_service(self)

    async def create_task(
        self,
        request: TranslationRequest,
        user_info: Dict[str, Any]
    ) -> TranslationTask:
        """创建翻译任务"""
        try:
            if isinstance(request.translation_engine, str):
                try:
                    request.translation_engine = TranslationEngine(
                        request.translation_engine.lower()
                    )
                except ValueError:
                    raise BadRequestException(
                        message=f"不支持的翻译引擎: {request.translation_engine}",
                        details={"supported_engines": list(self.engines.keys())},
                    )

            # 验证文件
            await self._validate_files(request.files, user_info)

            # 验证翻译引擎
            if request.translation_engine not in self.engines:
                raise BadRequestException(
                    message=f"不支持的翻译引擎: {request.translation_engine}",
                    details={"supported_engines": list(self.engines.keys())}
                )

            # 估算处理时间
            estimated_duration = await self._estimate_processing_time(request.files)

            # 创建任务
            task = await task_manager.create_task(
                user_id=user_info["user_id"],
                priority=request.priority,
                estimated_duration=estimated_duration
            )

            # 保存文件
            await self._save_files(task.task_id, request.files)

            # 保存任务配置
            await self._save_task_config(task.task_id, request)

            logger.info(f"创建翻译任务成功: {task.task_id}, 用户: {user_info['user_id']}")
            return task

        except Exception as e:
            logger.error(f"创建翻译任务失败: {e}")
            if isinstance(e, (FileFormatException, BadRequestException)):
                raise
            raise InternalServerException(
                message="创建翻译任务失败",
                details={"error": str(e)}
            )

    async def get_task(self, task_id: str, user_info: Dict[str, Any]) -> TranslationTask:
        """获取任务状态"""
        return await task_manager.get_task(task_id, user_info["user_id"])

    async def get_task_progress(self, task_id: str, user_info: Dict[str, Any]) -> TranslationProgress:
        """获取任务进度"""
        task = await task_manager.get_task(task_id, user_info["user_id"])
        return task.progress

    async def get_task_result(self, task_id: str, user_info: Dict[str, Any]) -> TranslationResult:
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

    async def cancel_task(self, task_id: str, user_info: Dict[str, Any]) -> bool:
        """取消任务"""
        return await task_manager.cancel_task(task_id, user_info["user_id"])

    async def delete_task(self, task_id: str, user_info: Dict[str, Any]) -> bool:
        """删除任务并清理产物"""
        task = await task_manager.get_task(task_id, user_info["user_id"])
        if task.status not in {TaskStatus.COMPLETED, TaskStatus.FAILED}:
            raise BadRequestException(message="任务尚未结束，无法删除")

        await self.clean_task_artifacts(task_id, user_info)
        return await task_manager.delete_task(task_id, user_info["user_id"])

    async def list_tasks(
        self,
        user_info: Dict[str, Any],
        page: int = 1,
        page_size: int = 20,
        **filters
    ) -> Dict[str, Any]:
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
        user_info: Dict[str, Any]
    ) -> Dict[str, Any]:
        """批量操作任务"""
        return await task_manager.batch_operation(request, user_info["user_id"])

    async def get_statistics(self, user_info: Dict[str, Any]) -> Dict[str, Any]:
        """获取用户统计信息"""
        return await task_manager.get_statistics(user_info["user_id"])

    async def preview_translation(
        self,
        request: TranslationPreviewRequest,
        user_info: Dict[str, Any]
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
                confidence=0.95  # TODO: 从翻译引擎获取置信度
            )

            logger.info(f"翻译预览成功: 用户 {user_info['user_id']}, 引擎 {request.translation_engine}")
            return preview

        except Exception as e:
            logger.error(f"翻译预览失败: {e}")
            raise TranslationEngineException(
                message="翻译预览失败",
                engine=request.translation_engine,
                details={"error": str(e)}
            )

    async def _validate_files(self, files: List[UploadFile], user_info: Dict[str, Any]):
        """验证文件"""
        if not files:
            raise BadRequestException(message="必须上传至少一个文件")

        total_size = 0
        for file in files:
            # 检查文件格式
            file_ext = Path(file.filename).suffix.lower()
            if file_ext not in self.supported_formats:
                raise FileFormatException(
                    message=f"不支持的文件格式: {file_ext}",
                    file_name=file.filename,
                    supported_formats=list(self.supported_formats)
                )

            # 检查文件大小
            file_size = await self._get_file_size(file)
            total_size += file_size

            if file_size > self.max_file_size:
                raise BadRequestException(
                    message=f"文件 {file.filename} 大小超过限制: {file_size / (1024*1024):.1f}MB > {self.max_file_size / (1024*1024):.1f}MB"
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

    async def _estimate_processing_time(self, files: List[UploadFile]) -> int:
        """估算处理时间"""
        total_size = 0
        for file in files:
            size = await self._get_file_size(file)
            total_size += size

        # 基于文件大小估算处理时间（粗略估算）
        # 假设每MB需要30秒处理时间
        estimated_seconds = int((total_size / (1024 * 1024)) * 30)

        # 最小30秒，最大2小时
        return max(30, min(estimated_seconds, 7200))

    async def _save_files(self, task_id: str, files: List[UploadFile]):
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
            "保存任务文件: %s, 文件数: %s, 路径: %s",
            task_id,
            len(saved_files),
            input_dir,
        )

    async def _save_task_config(self, task_id: str, request: TranslationRequest):
        """保存任务配置"""
        task_dir = self.task_dirs.get(task_id)
        if not task_dir:
            task_dir = self.storage_root / task_id
            task_dir.mkdir(parents=True, exist_ok=True)
            self.task_dirs[task_id] = task_dir

        config = {
            "target_language": request.target_language,
            "source_language": request.source_language,
            "translation_engine": request.translation_engine,
            "preserve_formatting": request.preserve_formatting,
            "translate_tables": request.translate_tables,
            "translate_equations": request.translate_equations,
            "custom_glossary": request.custom_glossary,
            "webhook_url": request.webhook_url,
            "priority": request.priority,
            "timeout": request.timeout
        }
        config_path = task_dir / "task_config.json"
        config_path.write_text(json.dumps(config, ensure_ascii=False, indent=2))
        self.task_configs[task_id] = config
        logger.info(f"保存任务配置: {task_id}")
        self._initialize_task_settings(task_id, request)

    async def _translate_text(
        self,
        text: str,
        source_language: Optional[str],
        target_language: str,
        engine: TranslationEngine
    ) -> str:
        """翻译文本"""
        # TODO: 集成实际的翻译引擎
        # 这里应该调用配置的翻译引擎API

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
        """通知webhook"""
        # TODO: 实现webhook通知逻辑
        logger.info(f"通知webhook: {webhook_url}, 任务: {task_id}, 状态: {status}")

    async def execute_task(self, task: TranslationTask) -> TranslationResult:
        """执行真实翻译流程并返回结果"""
        task_id = task.task_id
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
        try:
            await task_manager.update_task_progress(
                task_id, TranslationStage.PARSING, 15.0, "解析PDF"
            )
            await task_manager.update_task_progress(
                task_id, TranslationStage.TRANSLATING, 60.0, "翻译进行中"
            )
            async for event in do_translate_async_stream(settings, input_path):
                event_type = event.get("type")
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
            logger.exception("任务执行失败: %s", exc)
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
        files: List[TranslationFile] = []
        registry = self.file_registry.setdefault(task_id, {})
        now = datetime.now()

        attachment_map = [
            ("mono_pdf_path", "mono.pdf"),
            ("dual_pdf_path", "dual.pdf"),
            ("no_watermark_mono_pdf_path", "mono.nowatermark.pdf"),
            ("no_watermark_dual_pdf_path", "dual.nowatermark.pdf"),
            ("auto_extracted_glossary_path", "glossary.csv"),
        ]

        for attr, default_name in attachment_map:
            path_str = getattr(translate_result, attr, None)
            if not path_str:
                continue
            file_path = Path(path_str)
            if not file_path.exists():
                continue
            file_id = f"{uuid4().hex}"
            registry[file_id] = file_path
            files.append(
                TranslationFile(
                    file_id=file_id,
                    original_name=file_path.name,
                    translated_name=file_path.name,
                    size=file_path.stat().st_size,
                    page_count=getattr(translate_result, "total_pages", 0) or 0,
                    download_url=
                    f"/v1/translations/{task_id}/files/{file_id}/download",
                    expires_at=now + timedelta(days=7),
                )
            )

        engine_name = settings.translate_engine_settings.translate_engine_type
        engine_mapping = {v: k for k, v in ENGINE_TYPE_MAP.items()}
        engine_key = engine_mapping.get(engine_name)
        if not engine_key:
            try:
                engine_key = TranslationEngine(engine_name.lower()).value
            except ValueError:
                engine_key = TranslationEngine.GOOGLE.value
        engine_used = TranslationEngine(engine_key)

        return TranslationResult(
            files=files,
            processing_time=getattr(translate_result, "total_seconds", 0.0) or 0.0,
            total_pages=getattr(translate_result, "total_pages", 0) or 0,
            total_chars=getattr(translate_result, "total_characters", 0) or 0,
            engine_used=engine_used,
            quality_score=getattr(translate_result, "quality", None),
            warnings=[],
        )

    async def get_translated_file_path(
        self, task_id: str, file_id: str, user_info: Dict[str, Any]
    ) -> Path:
        """获取可下载的翻译文件路径，检查用户权限"""
        await task_manager.get_task(task_id, user_info["user_id"])
        task_files = self.file_registry.get(task_id, {})
        path = task_files.get(file_id)
        if not path or not path.exists():
            raise NotFoundException(message="翻译文件不存在", resource="translation_file")
        return path

    async def clean_task_artifacts(self, task_id: str, user_info: Dict[str, Any]) -> CleanupResult:
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
        except NotFoundException:
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
            )

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

    def _initialize_task_settings(
        self, task_id: str, request: TranslationRequest
    ) -> None:
        output_dir = self.task_dirs.get(task_id, self.storage_root / task_id) / "output"
        cfg = config_service.get_config().current_config
        translation_cfg = cfg.get("translation", {})

        translation_overrides: Dict[str, Any] = {
            "translation": {
                "lang_out": request.target_language,
            },
            "pdf": {
                "translate_table_text": request.translate_tables,
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

        extra_overrides: Dict[str, Any] | None = None
        if request.settings_json:
            try:
                extra_overrides = json.loads(request.settings_json)
            except json.JSONDecodeError as exc:
                raise BadRequestException(
                    message="settings_json 不是合法的 JSON",
                    details={"error": str(exc)},
                )
            if extra_overrides is not None and not isinstance(extra_overrides, dict):
                raise BadRequestException(
                    message="settings_json 必须是 JSON 对象",
                )

        engine_key = request.translation_engine.value.lower()
        engine_type = ENGINE_TYPE_MAP.get(engine_key, "Google")
        engine_config = translation_cfg.get("engines", {}).get(engine_key, {})
        engine_payload: Dict[str, Any] = {
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

        cli_model = build_settings_model(
            translation_overrides,
            engine_payload,
            extra_overrides,
        )
        settings = cli_model.to_settings_model()
        settings.translation.output = str(output_dir)
        settings.basic.input_files = set()
        self.task_settings[task_id] = settings


# 全局翻译服务实例
translation_service = TranslationService()
