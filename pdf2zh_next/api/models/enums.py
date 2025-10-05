"""API枚举定义"""

from enum import Enum


class TaskStatus(str, Enum):
    """任务状态枚举"""

    QUEUED = "queued"
    PARSING = "parsing"
    TRANSLATING = "translating"
    COMPOSING = "composing"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class TranslationStage(str, Enum):
    """翻译阶段枚举"""

    QUEUED = "queued"
    PARSING = "parsing"
    TRANSLATING = "translating"
    COMPOSING = "composing"
    COMPLETED = "completed"
    FAILED = "failed"


class ErrorCode(str, Enum):
    """错误码枚举"""

    INVALID_FILE_FORMAT = "INVALID_FILE_FORMAT"
    TRANSLATION_ENGINE_ERROR = "TRANSLATION_ENGINE_ERROR"
    TIMEOUT = "TIMEOUT"
    RESOURCE_EXHAUSTED = "RESOURCE_EXHAUSTED"
    INTERNAL_ERROR = "INTERNAL_ERROR"
    TASK_NOT_FOUND = "TASK_NOT_FOUND"
    INVALID_PARAMETERS = "INVALID_PARAMETERS"
    UNAUTHORIZED = "UNAUTHORIZED"
    FORBIDDEN = "FORBIDDEN"
    RATE_LIMIT_EXCEEDED = "RATE_LIMIT_EXCEEDED"


class UserRole(str, Enum):
    """用户角色枚举"""

    ADMIN = "admin"
    DEVELOPER = "developer"
    USER = "user"
    GUEST = "guest"


class OfflineAssetType(str, Enum):
    """离线资源类型枚举"""

    TRANSLATION_MODELS = "translation_models"
    LANGUAGE_PACKS = "language_packs"
    FONTS = "fonts"


class TranslationEngine(str, Enum):
    """翻译引擎枚举"""

    GOOGLE = "google"
    DEEPL = "deepl"
    OPENAI = "openai"
    BAIDU = "baidu"
    TENCENT = "tencent"


class ValidationMode(str, Enum):
    """验证模式枚举"""

    STRICT = "strict"
    PERMISSIVE = "permissive"
