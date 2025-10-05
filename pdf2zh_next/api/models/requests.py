"""请求数据模型"""

from datetime import datetime
from typing import Any

from fastapi import UploadFile
from pydantic import Field
from pydantic import field_validator

from .enums import TranslationEngine
from .enums import ValidationMode
from .schemas import BaseSchema


class TranslationRequest(BaseSchema):
    """翻译请求模型"""

    files: list[UploadFile] = Field(..., description="要翻译的PDF文件列表")
    target_language: str = Field("zh", description="目标语言代码")
    source_language: str | None = Field(
        None, description="源语言代码（可选，自动检测）"
    )
    translation_engine: TranslationEngine = Field(
        TranslationEngine.GOOGLE, description="翻译引擎"
    )
    preserve_formatting: bool = Field(True, description="是否保持格式")
    translate_tables: bool = Field(True, description="是否翻译表格")
    translate_equations: bool = Field(True, description="是否处理数学公式")
    custom_glossary: dict[str, str] | None = Field(None, description="自定义术语词典")
    webhook_url: str | None = Field(None, description="完成通知的webhook URL")
    priority: int = Field(1, ge=1, le=5, description="任务优先级（1-5，5最高）")
    timeout: int | None = Field(None, ge=60, description="超时时间（秒）")
    settings_json: str | None = Field(
        None,
        description=(
            "可选的 JSON 字符串，用于覆盖 BabelDOC 的高级设置，"
            "格式与 CLI 配置一致 (例如 translate_engine_settings 等)。"
        ),
    )

    @field_validator("files")
    @classmethod
    def validate_files(cls, v):
        if not v:
            raise ValueError("至少需要上传一个文件")
        for file in v:
            if not file.filename.lower().endswith(".pdf"):
                raise ValueError(f"文件 {file.filename} 必须是PDF格式")
        return v

    @field_validator("webhook_url")
    @classmethod
    def validate_webhook_url(cls, v):
        if v and not (v.startswith("http://") or v.startswith("https://")):
            raise ValueError("Webhook URL必须是有效的HTTP/HTTPS地址")
        return v


class WarmupRequest(BaseSchema):
    """系统预热请求"""

    preload_engines: list[TranslationEngine] = Field(
        default_factory=list, description="预加载的翻译引擎"
    )
    cache_models: bool = Field(True, description="是否缓存模型")
    test_connections: bool = Field(True, description="是否测试连接")

    @field_validator("preload_engines")
    @classmethod
    def validate_engines(cls, v):
        if len(v) != len(set(v)):
            raise ValueError("翻译引擎列表不能包含重复项")
        return v


class OfflineAssetRequest(BaseSchema):
    """离线资源生成请求"""

    asset_types: list[str] = Field(..., description="资源类型列表")
    languages: list[str] | None = Field(None, description="语言列表")
    include_dependencies: bool = Field(True, description="是否包含依赖项")
    compression_level: int = Field(6, ge=1, le=9, description="压缩级别（1-9）")


class ConfigUpdateRequest(BaseSchema):
    """配置更新请求"""

    translation: dict[str, Any] | None = Field(None, description="翻译配置")
    system: dict[str, Any] | None = Field(None, description="系统配置")
    logging: dict[str, Any] | None = Field(None, description="日志配置")
    validation_mode: ValidationMode = Field(
        ValidationMode.STRICT, description="验证模式"
    )

    @field_validator("*", mode="before")
    @classmethod
    def validate_config_sections(cls, v, info):
        if v is not None and not isinstance(v, dict):
            field_name = info.field_name if hasattr(info, "field_name") else "配置字段"
            raise ValueError(f"{field_name} 必须是字典类型")
        return v


class TaskFilterRequest(BaseSchema):
    """任务过滤请求"""

    status: list[str] | None = Field(None, description="任务状态过滤")
    engine: list[TranslationEngine] | None = Field(None, description="翻译引擎过滤")
    date_from: datetime | None = Field(None, description="开始时间过滤")
    date_to: datetime | None = Field(None, description="结束时间过滤")
    user_id: str | None = Field(None, description="用户ID过滤")
    priority_min: int | None = Field(None, ge=1, le=5, description="最小优先级")
    priority_max: int | None = Field(None, ge=1, le=5, description="最大优先级")
    sort_by: str | None = Field(None, description="排序字段")
    sort_order: str | None = Field(None, description="排序方式")


class BatchOperationRequest(BaseSchema):
    """批量操作请求"""

    task_ids: list[str] = Field(..., description="任务ID列表")
    operation: str = Field(..., description="操作类型")

    @field_validator("task_ids")
    @classmethod
    def validate_task_ids(cls, v):
        if not v:
            raise ValueError("任务ID列表不能为空")
        if len(v) > 100:
            raise ValueError("批量操作最多支持100个任务")
        return v

    @field_validator("operation")
    @classmethod
    def validate_operation(cls, v):
        allowed_operations = ["cancel", "delete", "retry", "pause", "resume"]
        if v not in allowed_operations:
            raise ValueError(f"不支持的操作类型: {v}")
        return v


class WebhookTestRequest(BaseSchema):
    """Webhook测试请求"""

    webhook_url: str = Field(..., description="要测试的webhook URL")
    test_payload: dict[str, Any] | None = Field(None, description="测试负载")

    @field_validator("webhook_url")
    @classmethod
    def validate_webhook_url(cls, v):
        if not (v.startswith("http://") or v.startswith("https://")):
            raise ValueError("Webhook URL必须是有效的HTTP/HTTPS地址")
        return v


class TranslationPreviewRequest(BaseSchema):
    """翻译预览请求"""

    text: str = Field(..., description="要预览翻译的文本")
    target_language: str = Field("zh", description="目标语言")
    source_language: str | None = Field(None, description="源语言")
    translation_engine: TranslationEngine = Field(
        TranslationEngine.GOOGLE, description="翻译引擎"
    )

    @field_validator("text")
    @classmethod
    def validate_text(cls, v):
        if not v.strip():
            raise ValueError("翻译文本不能为空")
        if len(v) > 10000:
            raise ValueError("翻译文本长度不能超过10000字符")
        return v.strip()
