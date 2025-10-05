"""API异常定义"""

from typing import Any

from fastapi import HTTPException
from fastapi import status

from .models.enums import ErrorCode


class APIException(HTTPException):
    """API基础异常"""

    def __init__(
        self,
        status_code: int,
        error_code: ErrorCode,
        message: str,
        details: dict[str, Any] | None = None,
        retryable: bool = False,
        headers: dict[str, str] | None = None,
    ):
        self.error_code = error_code
        self.message = message
        self.details = details or {}
        self.retryable = retryable

        # 构建错误响应
        error_response = {
            "success": False,
            "error": {
                "code": error_code,
                "message": message,
                "details": details,
                "retryable": retryable,
            },
        }

        super().__init__(
            status_code=status_code, detail=error_response, headers=headers
        )


class BadRequestException(APIException):
    """400 错误请求"""

    def __init__(
        self,
        message: str = "错误的请求参数",
        details: dict[str, Any] | None = None,
        error_code: ErrorCode = ErrorCode.INVALID_PARAMETERS,
    ):
        super().__init__(
            status_code=status.HTTP_400_BAD_REQUEST,
            error_code=error_code,
            message=message,
            details=details,
        )


class UnauthorizedException(APIException):
    """401 未授权"""

    def __init__(
        self, message: str = "未授权访问", details: dict[str, Any] | None = None
    ):
        super().__init__(
            status_code=status.HTTP_401_UNAUTHORIZED,
            error_code=ErrorCode.UNAUTHORIZED,
            message=message,
            details=details,
            headers={"WWW-Authenticate": "Bearer"},
        )


class ForbiddenException(APIException):
    """403 权限不足"""

    def __init__(
        self, message: str = "权限不足", details: dict[str, Any] | None = None
    ):
        super().__init__(
            status_code=status.HTTP_403_FORBIDDEN,
            error_code=ErrorCode.FORBIDDEN,
            message=message,
            details=details,
        )


class NotFoundException(APIException):
    """404 资源不存在"""

    def __init__(
        self,
        message: str = "请求的资源不存在",
        resource: str | None = None,
        resource_id: str | None = None,
    ):
        details = {}
        if resource:
            details["resource"] = resource
        if resource_id:
            details["resource_id"] = resource_id

        super().__init__(
            status_code=status.HTTP_404_NOT_FOUND,
            error_code=ErrorCode.TASK_NOT_FOUND,
            message=message,
            details=details,
        )


class ConflictException(APIException):
    """409 资源冲突"""

    def __init__(
        self, message: str = "资源冲突", details: dict[str, Any] | None = None
    ):
        super().__init__(
            status_code=status.HTTP_409_CONFLICT,
            error_code=ErrorCode.RESOURCE_EXHAUSTED,
            message=message,
            details=details,
        )


class RateLimitException(APIException):
    """429 请求频率限制"""

    def __init__(
        self,
        message: str = "请求频率超限",
        retry_after: int | None = None,
        limit: int | None = None,
        remaining: int | None = None,
    ):
        details = {}
        if limit is not None:
            details["limit"] = limit
        if remaining is not None:
            details["remaining"] = remaining

        headers = {}
        if retry_after is not None:
            headers["Retry-After"] = str(retry_after)
            details["retry_after"] = retry_after

        super().__init__(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            error_code=ErrorCode.RATE_LIMIT_EXCEEDED,
            message=message,
            details=details,
            headers=headers,
        )


class InternalServerException(APIException):
    """500 服务器内部错误"""

    def __init__(
        self,
        message: str = "服务器内部错误",
        details: dict[str, Any] | None = None,
        retryable: bool = True,
    ):
        super().__init__(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            error_code=ErrorCode.INTERNAL_ERROR,
            message=message,
            details=details,
            retryable=retryable,
        )


class TranslationEngineException(APIException):
    """翻译引擎异常"""

    def __init__(
        self,
        message: str = "翻译引擎错误",
        engine: str | None = None,
        details: dict[str, Any] | None = None,
        retryable: bool = True,
    ):
        error_details = details or {}
        if engine:
            error_details["engine"] = engine

        super().__init__(
            status_code=status.HTTP_502_BAD_GATEWAY,
            error_code=ErrorCode.TRANSLATION_ENGINE_ERROR,
            message=message,
            details=error_details,
            retryable=retryable,
        )


class FileFormatException(APIException):
    """文件格式异常"""

    def __init__(
        self,
        message: str = "不支持的文件格式",
        file_name: str | None = None,
        supported_formats: list | None = None,
    ):
        details = {}
        if file_name:
            details["file_name"] = file_name
        if supported_formats:
            details["supported_formats"] = supported_formats

        super().__init__(
            status_code=status.HTTP_400_BAD_REQUEST,
            error_code=ErrorCode.INVALID_FILE_FORMAT,
            message=message,
            details=details,
        )


class TimeoutException(APIException):
    """超时异常"""

    def __init__(
        self,
        message: str = "请求超时",
        timeout_seconds: int | None = None,
        retryable: bool = True,
    ):
        details = {}
        if timeout_seconds is not None:
            details["timeout_seconds"] = timeout_seconds

        super().__init__(
            status_code=status.HTTP_504_GATEWAY_TIMEOUT,
            error_code=ErrorCode.TIMEOUT,
            message=message,
            details=details,
            retryable=retryable,
        )


def create_validation_exception(field: str, message: str) -> BadRequestException:
    """创建验证异常"""
    return BadRequestException(
        message=f"参数验证失败: {message}", details={"field": field, "message": message}
    )


def create_business_exception(
    code: ErrorCode, message: str, details: dict[str, Any] | None = None
) -> APIException:
    """创建业务异常"""
    return APIException(
        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        error_code=code,
        message=message,
        details=details,
    )
