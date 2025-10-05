"""API路由模块"""
from .translation import router as translation_router
from .system import router as system_router
from .config import router as config_router
from .health import router as health_router

__all__ = [
    'translation_router',
    'system_router',
    'config_router',
    'health_router'
]