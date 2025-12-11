"""API 运行时配置（读取环境变量与 .env）"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from dotenv import load_dotenv
from pydantic import Field
from pydantic import field_validator
from pydantic_settings import BaseSettings
from pydantic_settings import SettingsConfigDict

load_dotenv()

class APISettings(BaseSettings):
    """API 配置，统一从环境变量读取"""

    model_config = SettingsConfigDict(
        env_prefix="PDF2ZH_",
        env_file=".env",
        extra="ignore",
    )

    # 翻译服务相关
    api_supported_formats: list[str] = Field(
        default_factory=lambda: [".pdf"], env="API_SUPPORTED_FORMATS"
    )
    api_max_file_size: int = Field(100 * 1024 * 1024, env="API_MAX_FILE_SIZE")
    api_storage_root: Path = Field(default=Path("storage/tasks"), env="API_STORAGE_ROOT")
    api_seconds_per_mb: int = Field(30, env="API_SECONDS_PER_MB")
    api_estimate_min_seconds: int = Field(30, env="API_ESTIMATE_MIN_SECONDS")
    api_estimate_max_seconds: int = Field(7200, env="API_ESTIMATE_MAX_SECONDS")
    api_preview_confidence: float = Field(0.95, env="API_PREVIEW_CONFIDENCE")
    api_artifact_expire_days: int = Field(7, env="API_ARTIFACT_EXPIRE_DAYS")
    api_engine_labels: dict[str, str] = Field(
        default_factory=lambda: {
            "google": "Google 翻译",
            "deepl": "DeepL 翻译",
            "openai": "OpenAI 翻译",
            "baidu": "百度翻译",
            "tencent": "腾讯翻译",
        },
        env="API_ENGINE_LABELS",
    )

    # 任务管理
    api_max_concurrency: int = Field(10, env="API_MAX_CONCURRENCY")
    api_task_timeout: int = Field(3600, env="API_TASK_TIMEOUT")
    api_cleanup_interval: int = Field(300, env="API_CLEANUP_INTERVAL")
    api_task_retention_hours: int = Field(24, env="API_TASK_RETENTION_HOURS")

    # 认证模板（普通用户）
    api_user_id: str = Field("user-123", env="API_USER_ID")
    api_user_permissions: list[str] = Field(
        default_factory=lambda: ["translate", "read_config"],
        env="API_USER_PERMISSIONS",
    )
    api_user_rate_limit: int = Field(60, env="API_USER_RATE_LIMIT")
    api_user_max_file_size: int = Field(100 * 1024 * 1024, env="API_USER_MAX_FILE_SIZE")
    api_user_max_concurrent_tasks: int = Field(3, env="API_USER_MAX_CONCURRENT_TASKS")
    api_user_allowed_engines: list[str] = Field(
        default_factory=lambda: ["google", "deepl", "baidu", "openaicompatible"],
        env="API_USER_ALLOWED_ENGINES",
    )
    api_user_webhook_support: bool = Field(True, env="API_USER_WEBHOOK_SUPPORT")
    api_user_quota_limit: int = Field(1000, env="API_USER_QUOTA_LIMIT")

    # 认证模板（管理员）
    api_admin_id: str = Field("admin-456", env="API_ADMIN_ID")
    api_admin_permissions: list[str] = Field(default_factory=lambda: ["*"], env="API_ADMIN_PERMISSIONS")
    api_admin_rate_limit: int = Field(1000, env="API_ADMIN_RATE_LIMIT")
    api_admin_max_file_size: int = Field(
        500 * 1024 * 1024, env="API_ADMIN_MAX_FILE_SIZE"
    )
    api_admin_max_concurrent_tasks: int = Field(20, env="API_ADMIN_MAX_CONCURRENT_TASKS")
    api_admin_allowed_engines: list[str] = Field(
        default_factory=lambda: ["google", "deepl", "openai", "openaicompatible", "baidu", "tencent"],
        env="API_ADMIN_ALLOWED_ENGINES",
    )
    api_admin_webhook_support: bool = Field(True, env="API_ADMIN_WEBHOOK_SUPPORT")
    api_admin_quota_limit: int = Field(10000, env="API_ADMIN_QUOTA_LIMIT")

    @field_validator(
        "api_supported_formats",
        "api_user_allowed_engines",
        "api_user_permissions",
        "api_admin_allowed_engines",
        "api_admin_permissions",
        mode="before",
    )
    @classmethod
    def _split_comma(cls, value: Any):
        """支持逗号分隔的字符串写法"""
        if isinstance(value, str):
            parts = [item.strip() for item in value.split(",")]
            return [item for item in parts if item]
        return value

    @field_validator("api_engine_labels", mode="before")
    @classmethod
    def _load_json_dict(cls, value: Any):
        """支持 JSON 字符串覆盖引擎名称映射"""
        if isinstance(value, str):
            try:
                return json.loads(value)
            except json.JSONDecodeError:
                return value
        return value


# 全局设置实例
api_settings = APISettings()
