"""依赖注入模块"""

import logging
import uuid
from typing import Annotated
from typing import Any

from fastapi import Depends
from fastapi import Request
from fastapi import Security
from fastapi.security import HTTPAuthorizationCredentials
from fastapi.security import HTTPBearer

from .exceptions import ForbiddenException
from .exceptions import UnauthorizedException
from .models import UserInfo
from .models import UserRole

logger = logging.getLogger(__name__)

# 安全配置
security = HTTPBearer()
BearerCredentials = Annotated[HTTPAuthorizationCredentials, Security(security)]

# 全局请求 ID 存储
_request_id_context = {}


def get_request_id() -> str:
    """获取当前请求的 ID"""
    return _request_id_context.get("request_id", "unknown")


async def set_request_id(request: Request) -> str:
    """设置请求 ID"""
    request_id = str(uuid.uuid4())
    _request_id_context["request_id"] = request_id

    # 将请求 ID 添加到请求对象中，供后续使用
    request.state.request_id = request_id
    return request_id


class AuthService:
    """认证服务"""

    def __init__(self):
        # TODO: 从配置文件或数据库加载 API 密钥
        self.api_keys = {
            "test-key-1": {
                "user_id": "user-123",
                "role": UserRole.USER,
                "permissions": ["translate", "read_config"],
                "rate_limit": 60,  # 每分钟 60 次
                "max_file_size": 100 * 1024 * 1024,  # 100MB
                "max_concurrent_tasks": 3,
                "allowed_engines": ["google", "deepl", "baidu"],
                "webhook_support": True,
                "quota_used": 0,
                "quota_limit": 1000,
            },
            "admin-key-1": {
                "user_id": "admin-456",
                "role": UserRole.ADMIN,
                "permissions": ["*"],  # 所有权限
                "rate_limit": 1000,  # 每分钟 1000 次
                "max_file_size": 500 * 1024 * 1024,  # 500MB
                "max_concurrent_tasks": 20,
                "allowed_engines": ["google", "deepl", "openai", "baidu", "tencent"],
                "webhook_support": True,
                "quota_used": 0,
                "quota_limit": 10000,
            },
        }

    async def verify_api_key(
        self, credentials: HTTPAuthorizationCredentials
    ) -> dict[str, Any]:
        """验证 API 密钥"""
        api_key = credentials.credentials

        if api_key not in self.api_keys:
            raise UnauthorizedException(
                message="无效的 API 密钥",
                details={"api_key": api_key[:8] + "..."},  # 只显示前 8 位
            )

        user_info = self.api_keys[api_key].copy()
        user_info["api_key"] = api_key

        # 记录认证成功
        logger.info(
            f"API 密钥认证成功：用户={user_info['user_id']}, 角色={user_info['role']}"
        )

        return user_info

    async def check_rate_limit(self, user_info: dict[str, Any], endpoint: str) -> bool:
        """检查速率限制"""
        # TODO: 实现基于 Redis 的分布式速率限制
        # 这里简化处理，实际应该使用 Redis 等外部存储

        rate_limit = user_info.get("rate_limit", 60)
        # 这里应该检查实际的请求频率
        # 暂时返回 True，表示未超限

        return True

    async def log_access(self, user_info: dict[str, Any], endpoint: str, method: str):
        """记录访问日志"""
        logger.info(
            f"API 访问：用户={user_info['user_id']}, 端点={method} {endpoint}, 角色={user_info['role']}"
        )


# 全局认证服务实例
auth_service = AuthService()


async def get_current_user(
    request: Request,
    credentials: BearerCredentials,
) -> dict[str, Any]:
    """获取当前用户信息"""
    cached = getattr(request.state, "user_info", None)
    if cached and cached.get("api_key") == credentials.credentials:
        return cached

    user_info = await auth_service.verify_api_key(credentials)
    request.state.user_info = user_info

    # 检查速率限制
    # TODO: 从 request 对象获取 endpoint 信息
    # await auth_service.check_rate_limit(user_info, endpoint)

    return user_info


async def get_current_user_info(
    current_user: Annotated[dict[str, Any], Depends(get_current_user)],
) -> UserInfo:
    """获取当前用户详细信息"""
    return UserInfo(
        user_id=current_user["user_id"],
        role=current_user["role"],
        permissions=current_user["permissions"],
        rate_limit=current_user["rate_limit"],
        max_file_size=current_user["max_file_size"],
        max_concurrent_tasks=current_user["max_concurrent_tasks"],
        allowed_engines=current_user["allowed_engines"],
        webhook_support=current_user["webhook_support"],
        quota_used=current_user["quota_used"],
        quota_limit=current_user["quota_limit"],
    )


def require_role(required_role: UserRole):
    """角色权限装饰器"""

    def role_checker(
        current_user: Annotated[dict[str, Any], Depends(get_current_user)],
    ) -> dict[str, Any]:
        user_role = current_user.get("role")

        # 检查角色权限
        role_hierarchy = {
            UserRole.GUEST: 1,
            UserRole.USER: 2,
            UserRole.DEVELOPER: 3,
            UserRole.ADMIN: 4,
        }

        user_role_level = role_hierarchy.get(user_role, 0)
        required_role_level = role_hierarchy.get(required_role, 0)

        if user_role_level < required_role_level:
            raise ForbiddenException(
                message=f"权限不足，需要{required_role}角色",
                details={"required_role": required_role, "current_role": user_role},
            )

        return current_user

    return role_checker


def require_permission(permission: str):
    """权限检查装饰器"""

    def permission_checker(
        current_user: Annotated[dict[str, Any], Depends(get_current_user)],
    ) -> dict[str, Any]:
        permissions = current_user.get("permissions", [])

        # 管理员拥有所有权限
        if "*" in permissions:
            return current_user

        if permission not in permissions:
            raise ForbiddenException(
                message=f"权限不足，需要{permission}权限",
                details={
                    "required_permission": permission,
                    "current_permissions": permissions,
                },
            )

        return current_user

    return permission_checker


async def get_request_info(request: Request) -> dict[str, Any]:
    """获取请求信息"""
    return {
        "method": request.method,
        "url": str(request.url),
        "headers": dict(request.headers),
        "client_host": request.client.host if request.client else None,
        "request_id": getattr(request.state, "request_id", "unknown"),
    }

