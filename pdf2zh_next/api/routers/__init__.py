"""API路由模块"""
from .config import router as config_router
from .health import router as health_router
from .system import router as system_router
from .translation import router as translation_router

__all__ = [
    'translation_router',
    'system_router',
    'config_router',
    'health_router'
]