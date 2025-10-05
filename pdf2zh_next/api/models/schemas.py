"""共享schema定义"""

from datetime import datetime
from typing import Any
from typing import Generic
from typing import TypeVar

from pydantic import BaseModel
from pydantic import Field
from pydantic import field_validator

from .enums import ErrorCode

T = TypeVar("T")


class BaseSchema(BaseModel):
    """基础schema"""

    class Config:
        use_enum_values = True
        validate_assignment = True
        json_encoders = {datetime: lambda v: v.isoformat()}


class ErrorDetail(BaseSchema):
    """错误详情schema"""

    code: ErrorCode
    message: str
    details: dict[str, Any] | None = None
    timestamp: datetime
    retryable: bool = False


class PaginationParams(BaseSchema):
    """分页参数"""

    page: int = Field(1, ge=1, description="页码")
    page_size: int = Field(20, ge=1, le=100, description="每页大小")
    sort_by: str | None = Field(None, description="排序字段")
    sort_order: str = Field("desc", pattern="^(asc|desc)$", description="排序方式")
    filters: dict[str, Any] | None = Field(None, description="过滤条件")


class PaginatedResponse(BaseSchema, Generic[T]):
    """分页响应schema"""

    items: list[T] = Field(description="数据项列表")
    total: int = Field(description="总记录数")
    page: int = Field(description="当前页码")
    page_size: int = Field(description="每页大小")
    total_pages: int = Field(description="总页数")
    has_next: bool = Field(description="是否有下一页")
    has_prev: bool = Field(description="是否有上一页")
    sort_by: str | None = Field(None, description="排序字段")
    sort_order: str = Field(description="排序方式")

    @field_validator("total_pages")
    def calculate_total_pages(cls, v, info):
        total = info.data.get("total", 0)
        page_size = info.data.get("page_size", 1)
        return (total + page_size - 1) // page_size

    @field_validator("has_next")
    def calculate_has_next(cls, v, info):
        page = info.data.get("page", 1)
        total_pages = info.data.get("total_pages", 0)
        return page < total_pages

    @field_validator("has_prev")
    def calculate_has_prev(cls, v, info):
        page = info.data.get("page", 1)
        return page > 1


class APIResponse(BaseSchema, Generic[T]):
    """统一API响应schema"""

    success: bool = Field(description="请求是否成功")
    data: T | None = Field(None, description="响应数据")
    error: ErrorDetail | None = Field(None, description="错误信息")
    metadata: dict[str, Any] | None = Field(None, description="元数据")
    timestamp: datetime = Field(description="响应时间戳")
    request_id: str = Field(description="请求ID")
    version: str = Field("v1", description="API版本")

    @field_validator("error")
    def validate_consistency(cls, v, info):
        success = info.data.get("success")
        if success and v is not None:
            raise ValueError("成功响应不能包含错误信息")
        if not success and v is None:
            raise ValueError("失败响应必须包含错误信息")
        return v


class FileUploadResponse(BaseSchema):
    """文件上传响应"""

    file_id: str
    filename: str
    size: int
    content_type: str
    uploaded_at: datetime


class TaskStatistics(BaseSchema):
    """任务统计信息"""

    total_tasks: int
    completed_tasks: int
    failed_tasks: int
    processing_tasks: int
    average_processing_time: float | None = None
    success_rate: float | None = None
