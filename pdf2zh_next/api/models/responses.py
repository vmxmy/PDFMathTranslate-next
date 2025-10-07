"""响应数据模型"""
from datetime import datetime
from typing import Any

from pydantic import Field
from pydantic import field_validator

from .enums import TaskStatus
from .enums import TranslationEngine
from .enums import TranslationStage
from .enums import UserRole
from .schemas import BaseSchema


class StageProgress(BaseSchema):
    """阶段进度模型"""
    stage: TranslationStage = Field(description="阶段名称")
    progress: float = Field(0.0, ge=0.0, le=100.0, description="阶段进度百分比")
    status: str = Field(description="阶段状态描述")
    started_at: datetime | None = Field(None, description="阶段开始时间")
    completed_at: datetime | None = Field(None, description="阶段完成时间")
    details: dict[str, Any] | None = Field(None, description="阶段详细信息")


class TranslationProgress(BaseSchema):
    """翻译进度模型"""
    overall_progress: float = Field(0.0, ge=0.0, le=100.0, description="整体进度百分比")
    current_stage: TranslationStage = Field(description="当前阶段")
    stage_details: list[StageProgress] = Field(default_factory=list, description="各阶段详细进度")
    estimated_remaining_time: int | None = Field(None, description="预计剩余时间（秒）")
    processed_pages: int = Field(0, description="已处理页数")
    total_pages: int = Field(0, description="总页数")
    processed_chars: int = Field(0, description="已处理字符数")
    total_chars: int = Field(0, description="总字符数")
    processed_paragraphs: int = Field(0, description="已处理段落数")
    total_paragraphs: int = Field(0, description="总段落数")

    @field_validator("estimated_remaining_time")
    @classmethod
    def validate_remaining_time(cls, v):
        if v is not None and v < 0:
            raise ValueError('剩余时间不能为负数')
        return v

    @field_validator("processed_pages", "processed_chars", "processed_paragraphs")
    @classmethod
    def validate_processed_values(cls, v):
        if v < 0:
            raise ValueError('处理数量不能为负数')
        return v


class TranslationFile(BaseSchema):
    """翻译文件模型"""
    file_id: str = Field(description="文件 ID")
    original_name: str = Field(description="原始文件名")
    translated_name: str = Field(description="翻译后的文件名")
    size: int = Field(description="文件大小（字节）")
    page_count: int = Field(description="页数")
    download_url: str = Field(description="下载 URL")
    expires_at: datetime = Field(description="下载链接过期时间")


class TranslationResult(BaseSchema):
    """翻译结果模型"""
    files: list[TranslationFile] = Field(description="翻译文件列表")
    processing_time: float = Field(description="处理时间（秒）")
    total_pages: int = Field(description="总页数")
    total_chars: int = Field(description="总字符数")
    engine_used: TranslationEngine = Field(description="使用的翻译引擎")
    quality_score: float | None = Field(None, ge=0.0, le=1.0, description="质量评分")
    warnings: list[str] = Field(default_factory=list, description="警告信息")


class TranslationTask(BaseSchema):
    """翻译任务模型"""
    task_id: str = Field(description="任务 ID")
    status: TaskStatus = Field(description="任务状态")
    created_at: datetime = Field(description="创建时间")
    updated_at: datetime = Field(description="更新时间")
    started_at: datetime | None = Field(None, description="开始处理时间")
    completed_at: datetime | None = Field(None, description="完成时间")
    progress: TranslationProgress = Field(description="任务进度")
    result: TranslationResult | None = Field(None, description="翻译结果")
    user_id: str = Field(description="用户 ID")
    priority: int = Field(description="任务优先级")
    estimated_duration: int | None = Field(None, description="预计处理时间（秒）")
    retry_count: int = Field(0, description="重试次数")
    max_retries: int = Field(3, description="最大重试次数")

    @field_validator("priority")
    @classmethod
    def validate_priority(cls, v):
        if not 1 <= v <= 5:
            raise ValueError('优先级必须在 1-5 之间')
        return v

    @field_validator("retry_count", "max_retries")
    @classmethod
    def validate_retries(cls, v):
        if v < 0:
            raise ValueError('重试次数不能为负数')
        return v


class TranslationPreview(BaseSchema):
    """翻译预览模型"""
    original_text: str = Field(description="原始文本")
    translated_text: str = Field(description="翻译文本")
    source_language: str = Field(description="源语言")
    target_language: str = Field(description="目标语言")
    engine_used: TranslationEngine = Field(description="使用的翻译引擎")
    confidence: float | None = Field(None, ge=0.0, le=1.0, description="翻译置信度")


class WarmupResponse(BaseSchema):
    """系统预热响应"""
    status: str = Field(description="预热状态")
    preloaded_engines: list[TranslationEngine] = Field(description="预加载的翻译引擎")
    cache_status: dict[str, bool] = Field(description="缓存状态")
    connection_tests: dict[str, bool] = Field(description="连接测试结果")
    duration_ms: int = Field(description="预热耗时（毫秒）")
    memory_usage: dict[str, Any] = Field(description="内存使用情况")


class OfflineAssetStatus(BaseSchema):
    """离线资源状态模型"""
    asset_type: str = Field(description="资源类型")
    total_size: int = Field(description="总大小（字节）")
    file_count: int = Field(description="文件数量")
    languages: list[str] = Field(description="包含的语言")
    generated_at: datetime = Field(description="生成时间")
    expires_at: datetime | None = Field(None, description="过期时间")
    compression_ratio: float | None = Field(None, description="压缩比率")


class ConfigResponse(BaseSchema):
    """配置响应模型"""
    current_config: dict[str, Any] = Field(description="当前配置")
    schema: dict[str, Any] = Field(description="配置 schema")
    last_updated: datetime = Field(description="最后更新时间")
    validation_errors: list[str] | None = Field(None, description="验证错误")


class HealthStatus(BaseSchema):
    """健康状态模型"""
    status: str = Field(description="整体健康状态")
    timestamp: datetime = Field(description="检查时间戳")
    version: str = Field(description="API 版本")
    uptime_seconds: float = Field(description="运行时间（秒）")
    dependencies: dict[str, Any] = Field(description="依赖服务状态")
    performance_metrics: dict[str, float] = Field(description="性能指标")


class WebhookTestResponse(BaseSchema):
    """Webhook 测试响应"""
    webhook_url: str = Field(description="测试的 webhook URL")
    status_code: int = Field(description="HTTP 状态码")
    response_time_ms: int = Field(description="响应时间（毫秒）")
    response_body: str | None = Field(None, description="响应体")
    success: bool = Field(description="是否成功")


class BatchOperationResponse(BaseSchema):
    """批量操作响应"""
    total_tasks: int = Field(description="总任务数")
    successful_tasks: int = Field(description="成功任务数")
    failed_tasks: int = Field(description="失败任务数")
    results: list[dict[str, Any]] = Field(description="详细结果")


class UserInfo(BaseSchema):
    """用户信息模型"""
    user_id: str = Field(description="用户 ID")
    role: UserRole = Field(description="用户角色")
    permissions: list[str] = Field(description="权限列表")
    rate_limit: int = Field(description="速率限制（每分钟）")
    max_file_size: int = Field(description="最大文件大小（字节）")
    max_concurrent_tasks: int = Field(description="最大并发任务数")
    allowed_engines: list[TranslationEngine] = Field(description="允许的翻译引擎")
    webhook_support: bool = Field(description="是否支持 webhook")
    quota_used: int = Field(description="已使用配额")
    quota_limit: int = Field(description="配额限制")


class CleanupResult(BaseSchema):
    """任务清理结果"""

    task_exists: bool = Field(description="任务记录是否仍存在")
    files_removed: bool = Field(description="是否删除了本地文件")
    message: str = Field(description="详细提示信息")
    download_links_valid: bool = Field(
        description="当前任务的下载链接是否仍然有效"
    )
