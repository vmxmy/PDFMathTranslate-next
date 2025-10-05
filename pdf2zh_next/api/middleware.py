"""API中间件模块"""

import logging
import time
from typing import Any

from fastapi import Request
from fastapi import Response
from fastapi.responses import JSONResponse
from fastapi.security import HTTPAuthorizationCredentials
from fastapi.security.utils import get_authorization_scheme_param
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.types import ASGIApp

from .dependencies import set_request_id, auth_service
from .exceptions import RateLimitException, UnauthorizedException
from .models.enums import UserRole

logger = logging.getLogger(__name__)

HEALTH_ENDPOINT_WHITELIST = {
    "/v1/health",
    "/v1/health/",
    "/v1/health/ready",
    "/v1/health/live",
    "/v1/health/dependencies",
}


class LoggingMiddleware(BaseHTTPMiddleware):
    """日志中间件"""

    def __init__(self, app: ASGIApp):
        super().__init__(app)
        self.logger = logging.getLogger("api.access")

    async def dispatch(self, request: Request, call_next):
        # 设置请求ID
        request_id = await set_request_id(request)

        # 记录请求开始
        start_time = time.time()
        self.logger.info(
            f"Request started: {request.method} {request.url.path}",
            extra={
                "request_id": request_id,
                "method": request.method,
                "path": request.url.path,
                "client_host": request.client.host if request.client else None,
                "user_agent": request.headers.get("user-agent", ""),
            },
        )

        # 处理请求
        response = await call_next(request)

        # 计算处理时间
        process_time = time.time() - start_time

        # 记录请求完成
        self.logger.info(
            f"Request completed: {request.method} {request.url.path}",
            extra={
                "request_id": request_id,
                "method": request.method,
                "path": request.url.path,
                "status_code": response.status_code,
                "process_time": f"{process_time:.3f}s",
            },
        )

        # 添加响应头
        response.headers["X-Request-ID"] = request_id
        response.headers["X-Process-Time"] = f"{process_time:.3f}"

        return response


class RateLimitMiddleware(BaseHTTPMiddleware):
    """速率限制中间件"""

    def __init__(self, app: ASGIApp, default_limit: int = 60):
        super().__init__(app)
        self.default_limit = default_limit
        # TODO: 使用Redis存储请求计数
        self.request_counts: dict[str, dict[str, Any]] = {}

    async def dispatch(self, request: Request, call_next):
        # 跳过健康检查等非API请求
        if (
            request.url.path in HEALTH_ENDPOINT_WHITELIST
            or request.url.path.startswith("/health")
            or request.url.path == "/docs"
            or request.url.path == "/redoc"
        ):
            return await call_next(request)

        # 获取用户信息
        user_info = getattr(request.state, "user_info", None)
        if not user_info:
            auth_header = request.headers.get("Authorization")
            if auth_header:
                scheme, token = get_authorization_scheme_param(auth_header)
                if scheme.lower() == "bearer" and token:
                    credentials = HTTPAuthorizationCredentials(
                        scheme=scheme, credentials=token
                    )
                    try:
                        user_info = await auth_service.verify_api_key(credentials)
                        request.state.user_info = user_info
                    except UnauthorizedException:
                        user_info = None

        if user_info and user_info.get("role") == UserRole.ADMIN:
            return await call_next(request)

        if not user_info:
            rate_limit = 10  # 每分钟10次
            user_id = (
                f"anonymous:{request.client.host if request.client else 'unknown'}"
            )
        else:
            rate_limit = user_info.get("rate_limit", self.default_limit)
            user_id = user_info["user_id"]

        # 检查速率限制
        current_time = int(time.time())
        window_start = (current_time // 60) * 60  # 当前分钟的开始时间

        # 获取或创建请求计数
        if user_id not in self.request_counts:
            self.request_counts[user_id] = {
                "count": 0,
                "window_start": window_start,
                "limit": rate_limit,
            }

        user_data = self.request_counts[user_id]

        # 重置计数器（新窗口）
        if user_data["window_start"] != window_start:
            user_data["count"] = 0
            user_data["window_start"] = window_start

        # 检查是否超限
        if user_data["count"] >= user_data["limit"]:
            raise RateLimitException(
                message="请求频率超限",
                limit=user_data["limit"],
                remaining=0,
                retry_after=60 - (current_time % 60),
            )

        # 增加计数
        user_data["count"] += 1

        # 处理请求
        response = await call_next(request)

        # 添加速率限制相关的响应头
        response.headers["X-RateLimit-Limit"] = str(user_data["limit"])
        response.headers["X-RateLimit-Remaining"] = str(
            max(0, user_data["limit"] - user_data["count"])
        )
        response.headers["X-RateLimit-Reset"] = str(user_data["window_start"] + 60)

        return response

    async def cleanup_old_entries(self):
        """清理旧的请求计数记录"""
        # TODO: 定期清理过期的记录
        current_time = int(time.time())
        expired_time = current_time - 3600  # 1小时前的记录

        expired_users = []
        for user_id, data in self.request_counts.items():
            if data["window_start"] < expired_time:
                expired_users.append(user_id)

        for user_id in expired_users:
            del self.request_counts[user_id]


class CORSMiddleware(BaseHTTPMiddleware):
    """CORS中间件（如果需要在应用级别处理）"""

    def __init__(
        self, app: ASGIApp, allow_origins: list = None, allow_credentials: bool = True
    ):
        super().__init__(app)
        self.allow_origins = allow_origins or ["*"]
        self.allow_credentials = allow_credentials

    async def dispatch(self, request: Request, call_next):
        # 处理预检请求
        if request.method == "OPTIONS":
            response = Response()
            self._set_cors_headers(response, request)
            return response

        # 处理正常请求
        response = await call_next(request)
        self._set_cors_headers(response, request)
        return response

    def _set_cors_headers(self, response: Response, request: Request):
        """设置CORS响应头"""
        origin = request.headers.get("origin")

        if "*" in self.allow_origins:
            response.headers["Access-Control-Allow-Origin"] = "*"
        elif origin in self.allow_origins:
            response.headers["Access-Control-Allow-Origin"] = origin

        if self.allow_credentials:
            response.headers["Access-Control-Allow-Credentials"] = "true"

        response.headers["Access-Control-Allow-Methods"] = (
            "GET, POST, PUT, DELETE, OPTIONS"
        )
        response.headers["Access-Control-Allow-Headers"] = "*"
        response.headers["Access-Control-Expose-Headers"] = (
            "X-Request-ID, X-Process-Time, X-RateLimit-*"
        )


class ErrorHandlingMiddleware(BaseHTTPMiddleware):
    """错误处理中间件"""

    def __init__(self, app: ASGIApp):
        super().__init__(app)

    async def dispatch(self, request: Request, call_next):
        try:
            response = await call_next(request)
            return response
        except Exception as e:
            # 记录错误日志
            request_id = getattr(request.state, "request_id", "unknown")
            logger.error(f"Unhandled error in request {request_id}: {e}", exc_info=True)

            # 返回统一的错误响应
            return JSONResponse(
                status_code=500,
                content={
                    "success": False,
                    "error": {
                        "code": "INTERNAL_ERROR",
                        "message": "服务器内部错误",
                        "details": {"request_id": request_id},
                    },
                    "timestamp": time.time(),
                    "request_id": request_id,
                },
            )


class SecurityMiddleware(BaseHTTPMiddleware):
    """安全中间件"""

    def __init__(self, app: ASGIApp):
        super().__init__(app)

    async def dispatch(self, request: Request, call_next):
        # 添加安全响应头
        response = await call_next(request)

        # 基本的安全头
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["X-XSS-Protection"] = "1; mode=block"
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"

        # 如果HTTPS，添加HSTS
        if request.url.scheme == "https":
            response.headers["Strict-Transport-Security"] = (
                "max-age=31536000; includeSubDomains"
            )

        return response


class RequestTimingMiddleware(BaseHTTPMiddleware):
    """请求时间记录中间件"""

    def __init__(self, app: ASGIApp):
        super().__init__(app)

    async def dispatch(self, request: Request, call_next):
        start_time = time.time()

        # 处理请求
        response = await call_next(request)

        # 计算处理时间
        process_time = time.time() - start_time

        # 记录慢请求
        if process_time > 5.0:  # 超过5秒的请求
            request_id = getattr(request.state, "request_id", "unknown")
            logger.warning(
                f"Slow request detected: {process_time:.2f}s, Request ID: {request_id}"
            )

        return response


# 中间件配置函数
def setup_middlewares(app):
    """设置所有中间件"""
    # 注意：中间件的顺序很重要，最先添加的最后执行

    # 错误处理中间件（最外层）
    app.add_middleware(ErrorHandlingMiddleware)

    # 安全中间件
    app.add_middleware(SecurityMiddleware)

    # 速率限制中间件
    app.add_middleware(RateLimitMiddleware)

    # 日志中间件
    app.add_middleware(LoggingMiddleware)

    # 请求时间记录中间件
    app.add_middleware(RequestTimingMiddleware)

    return app
