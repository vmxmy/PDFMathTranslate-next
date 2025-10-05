"""主FastAPI应用"""

import logging
import time
from contextlib import asynccontextmanager
from datetime import datetime, timezone

from fastapi import FastAPI
from fastapi import Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.encoders import jsonable_encoder

from .dependencies import get_request_id
from .services import config_service
from .services import system_service
from .services import task_manager
from .exceptions import APIException
from .exceptions import InternalServerException
from .middleware import setup_middlewares
from .models import APIResponse
from .models import ErrorDetail
from .routers import config_router
from .routers import health_router
from .routers import system_router
from .routers import translation_router

# 配置日志
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """应用生命周期管理"""
    # 启动时执行
    logger.info("正在启动PDFMathTranslate API服务...")

    try:
        # 初始化任务管理器
        await task_manager.initialize()
        logger.info("任务管理器初始化成功")

        # 初始化系统服务
        await system_service.get_health_status()  # 预热健康检查
        logger.info("系统服务初始化成功")

        # 加载配置
        config_service.get_config()
        logger.info("配置服务初始化成功")

        logger.info("PDFMathTranslate API服务启动成功")

    except Exception as e:
        logger.error(f"服务启动失败: {e}")
        raise

    yield

    # 关闭时执行
    logger.info("正在关闭PDFMathTranslate API服务...")

    try:
        # 关闭任务管理器
        await task_manager.shutdown()
        logger.info("任务管理器关闭成功")

        logger.info("PDFMathTranslate API服务关闭成功")

    except Exception as e:
        logger.error(f"服务关闭失败: {e}")


def create_app() -> FastAPI:
    """创建FastAPI应用"""
    app = FastAPI(
        title="PDFMathTranslate API",
        description="专业PDF文档翻译服务，支持数学公式、图表和格式保持",
        version="1.0.0",
        terms_of_service="https://pdf2zh.com/terms/",
        contact={
            "name": "API Support",
            "url": "https://pdf2zh.com/support",
            "email": "api@pdf2zh.com",
        },
        license_info={
            "name": "MIT",
            "url": "https://opensource.org/licenses/MIT",
        },
        servers=[
            {"url": "https://api.pdf2zh.com", "description": "生产环境"},
            {"url": "https://staging-api.pdf2zh.com", "description": "测试环境"},
            {"url": "http://localhost:8000", "description": "本地开发"},
        ],
        docs_url="/docs",
        redoc_url="/redoc",
        openapi_url="/openapi.json",
        lifespan=lifespan,
    )

    # 配置CORS
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # 设置其他中间件
    app = setup_middlewares(app)

    # 注册全局异常处理
    @app.exception_handler(APIException)
    async def api_exception_handler(request: Request, exc: APIException):
        """处理API异常"""
        request_id = get_request_id()

        error_detail = ErrorDetail(
            code=exc.error_code,
            message=exc.message,
            details=exc.details,
            timestamp=datetime.now(timezone.utc),
            retryable=exc.retryable,
        )

        response = APIResponse(
            success=False,
            error=error_detail,
            metadata={"request_id": request_id},
            timestamp=time.time(),
            request_id=request_id,
            version="v1",
        )

        return JSONResponse(
            status_code=exc.status_code,
            content=jsonable_encoder(response),
            headers=exc.headers,
        )

    @app.exception_handler(InternalServerException)
    async def internal_exception_handler(
        request: Request, exc: InternalServerException
    ):
        """处理内部服务器异常"""
        request_id = get_request_id()

        logger.error(
            f"内部服务器错误: {exc.message}, 请求ID: {request_id}", exc_info=True
        )

        return JSONResponse(
            status_code=exc.status_code,
            content={
                "success": False,
                "error": {
                    "code": exc.error_code,
                    "message": exc.message,
                    "details": exc.details,
                    "retryable": exc.retryable,
                },
                "timestamp": time.time(),
                "request_id": request_id,
                "version": "v1",
            },
        )

    @app.exception_handler(Exception)
    async def general_exception_handler(request: Request, exc: Exception):
        """处理未捕获的异常"""
        request_id = get_request_id()

        logger.error(f"未捕获的异常: {exc}, 请求ID: {request_id}", exc_info=True)

        return JSONResponse(
            status_code=500,
            content={
                "success": False,
                "error": {
                    "code": "INTERNAL_ERROR",
                    "message": "服务器内部错误",
                    "details": {"request_id": request_id},
                    "retryable": True,
                },
                "timestamp": time.time(),
                "request_id": request_id,
                "version": "v1",
            },
        )

    # 根路径
    @app.get("/")
    async def root():
        """根路径"""
        return {
            "service": "PDFMathTranslate API",
            "version": "1.0.0",
            "status": "running",
            "timestamp": time.time(),
            "documentation": "/docs",
            "health": "/health",
        }

    # 注册路由
    app.include_router(translation_router, prefix="/v1")
    app.include_router(system_router, prefix="/v1")
    app.include_router(config_router, prefix="/v1")
    app.include_router(health_router, prefix="/v1")

    # 自定义OpenAPI schema
    def custom_openapi():
        if app.openapi_schema:
            return app.openapi_schema

        from fastapi.openapi.utils import get_openapi

        openapi_schema = get_openapi(
            title=app.title,
            version=app.version,
            description=app.description,
            routes=app.routes,
        )

        # 添加安全方案
        openapi_schema["components"]["securitySchemes"] = {
            "BearerAuth": {
                "type": "http",
                "scheme": "bearer",
                "bearerFormat": "JWT",
                "description": "使用API密钥进行认证，在Authorization头中添加Bearer token",
            }
        }

        # 添加通用错误响应
        error_response = {
            "description": "错误响应",
            "content": {
                "application/json": {
                    "schema": {
                        "type": "object",
                        "properties": {
                            "success": {"type": "boolean", "example": False},
                            "error": {
                                "type": "object",
                                "properties": {
                                    "code": {
                                        "type": "string",
                                        "example": "INTERNAL_ERROR",
                                    },
                                    "message": {
                                        "type": "string",
                                        "example": "服务器内部错误",
                                    },
                                    "details": {"type": "object"},
                                    "retryable": {"type": "boolean", "example": True},
                                },
                            },
                            "timestamp": {"type": "number", "example": 1640995200.0},
                            "request_id": {
                                "type": "string",
                                "example": "123e4567-e89b-12d3-a456-426614174000",
                            },
                            "version": {"type": "string", "example": "v1"},
                        },
                    }
                }
            },
        }

        # 为所有路径添加错误响应
        for path_data in openapi_schema["paths"].values():
            for operation in path_data.values():
                if isinstance(operation, dict) and "responses" in operation:
                    operation["responses"]["default"] = error_response

        app.openapi_schema = openapi_schema
        return app.openapi_schema

    app.openapi = custom_openapi

    return app


# 创建应用实例
app = create_app()


# 启动函数（用于开发环境）
if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "pdf2zh_next.api.app:app",
        host="0.0.0.0",
        port=8000,
        reload=True,
        log_level="info",
    )
