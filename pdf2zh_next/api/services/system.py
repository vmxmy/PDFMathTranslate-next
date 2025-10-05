"""系统服务"""
import asyncio
import time
from datetime import datetime
from typing import Any, Dict, List, Optional
import logging
import psutil

from ..models import (
    WarmupResponse, OfflineAssetStatus, TranslationEngine,
    HealthStatus, UserRole
)
from ..exceptions import (
    InternalServerException, BadRequestException
)

logger = logging.getLogger(__name__)


class SystemService:
    """系统服务"""
    def __init__(self):
        self.start_time = datetime.now()
        self.warmed_engines = set()
        self.offline_assets = {}
        self.health_checks = {
            "database": self._check_database,
            "redis": self._check_redis,
            "storage": self._check_storage,
            "translation_engines": self._check_translation_engines
        }

    async def warmup_system(self, preload_engines: List[TranslationEngine], cache_models: bool, test_connections: bool) -> WarmupResponse:
        """系统预热"""
        start_time = time.time()

        try:
            logger.info("开始系统预热")

            # 预加载翻译引擎
            preloaded_engines = []
            cache_status = {}
            connection_tests = {}

            for engine in preload_engines:
                try:
                    if cache_models:
                        await self._preload_engine_model(engine)
                        cache_status[engine] = True

                    if test_connections:
                        connection_result = await self._test_engine_connection(engine)
                        connection_tests[engine] = connection_result

                    preloaded_engines.append(engine)
                    self.warmed_engines.add(engine)

                    logger.info(f"翻译引擎预热成功: {engine}")
                except Exception as e:
                    logger.error(f"翻译引擎预热失败: {engine}, {e}")
                    if cache_models:
                        cache_status[engine] = False
                    if test_connections:
                        connection_tests[engine] = False

            # 获取内存使用情况
            memory_usage = self._get_memory_usage()

            duration_ms = int((time.time() - start_time) * 1000)

            response = WarmupResponse(
                status="success",
                preloaded_engines=preloaded_engines,
                cache_status=cache_status,
                connection_tests=connection_tests,
                duration_ms=duration_ms,
                memory_usage=memory_usage
            )

            logger.info(f"系统预热完成，耗时: {duration_ms}ms")
            return response

        except Exception as e:
            logger.error(f"系统预热失败: {e}")
            raise InternalServerException(
                message="系统预热失败",
                details={"error": str(e)}
            )

    async def generate_offline_assets(self, asset_types: List[str], languages: Optional[List[str]], include_dependencies: bool, compression_level: int) -> List[OfflineAssetStatus]:
        """生成离线资源"""
        try:
            logger.info(f"开始生成离线资源: {asset_types}")

            results = []

            for asset_type in asset_types:
                try:
                    result = await self._generate_asset_type(asset_type, languages, include_dependencies, compression_level)
                    results.append(result)
                    self.offline_assets[asset_type] = result
                    logger.info(f"离线资源生成成功: {asset_type}")
                except Exception as e:
                    logger.error(f"离线资源生成失败: {asset_type}, {e}")
                    # 继续处理其他资源类型
                    continue

            if not results:
                raise InternalServerException(
                    message="所有离线资源生成失败",
                    details={"asset_types": asset_types}
                )

            return results

        except Exception as e:
            logger.error(f"生成离线资源失败: {e}")
            if isinstance(e, InternalServerException):
                raise
            raise InternalServerException(
                message="生成离线资源失败",
                details={"error": str(e)}
            )

    async def restore_offline_assets(self, asset_types: List[str]) -> bool:
        """恢复离线资源"""
        try:
            logger.info(f"开始恢复离线资源: {asset_types}")

            success_count = 0
            for asset_type in asset_types:
                try:
                    if asset_type in self.offline_assets:
                        await self._restore_asset_type(asset_type)
                        success_count += 1
                        logger.info(f"离线资源恢复成功: {asset_type}")
                    else:
                        logger.warning(f"离线资源不存在: {asset_type}")
                except Exception as e:
                    logger.error(f"离线资源恢复失败: {asset_type}, {e}")
                    continue

            if success_count == 0:
                raise BadRequestException(
                    message="没有成功恢复任何离线资源",
                    details={"asset_types": asset_types}
                )

            return success_count == len(asset_types)

        except Exception as e:
            logger.error(f"恢复离线资源失败: {e}")
            if isinstance(e, BadRequestException):
                raise
            raise InternalServerException(
                message="恢复离线资源失败",
                details={"error": str(e)}
            )

    async def get_health_status(self) -> HealthStatus:
        """获取健康状态"""
        try:
            timestamp = datetime.now()
            uptime = (timestamp - self.start_time).total_seconds()

            # 检查各项依赖
            dependencies = {}
            for name, check_func in self.health_checks.items():
                try:
                    dependencies[name] = await check_func()
                except Exception as e:
                    dependencies[name] = {
                        "status": "unhealthy",
                        "error": str(e)
                    }

            # 计算整体状态
            overall_status = "healthy"
            for dep_status in dependencies.values():
                if isinstance(dep_status, dict) and dep_status.get("status") != "healthy":
                    overall_status = "unhealthy"
                    break

            # 获取性能指标
            performance_metrics = self._get_performance_metrics()

            return HealthStatus(
                status=overall_status,
                timestamp=timestamp,
                version="1.0.0",
                uptime_seconds=uptime,
                dependencies=dependencies,
                performance_metrics=performance_metrics
            )

        except Exception as e:
            logger.error(f"获取健康状态失败: {e}")
            raise InternalServerException(
                message="获取健康状态失败",
                details={"error": str(e)}
            )

    async def get_system_info(self) -> Dict[str, Any]:
        """获取系统信息"""
        try:
            # 获取系统资源使用情况
            cpu_percent = psutil.cpu_percent(interval=1)
            memory = psutil.virtual_memory()
            disk = psutil.disk_usage('/')

            # 获取进程信息
            process = psutil.Process()
            process_memory = process.memory_info()
            process_cpu = process.cpu_percent()

            return {
                "system": {
                    "cpu_percent": cpu_percent,
                    "memory_percent": memory.percent,
                    "memory_available": memory.available,
                    "memory_total": memory.total,
                    "disk_percent": disk.percent,
                    "disk_free": disk.free,
                    "disk_total": disk.total
                },
                "process": {
                    "memory_rss": process_memory.rss,
                    "memory_vms": process_memory.vms,
                    "cpu_percent": process_cpu,
                    "num_threads": process.num_threads(),
                    "num_fds": process.num_fds() if hasattr(process, 'num_fds') else None
                },
                "application": {
                    "start_time": self.start_time.isoformat(),
                    "uptime_seconds": (datetime.now() - self.start_time).total_seconds(),
                    "warmed_engines": list(self.warmed_engines),
                    "offline_assets": list(self.offline_assets.keys())
                }
            }

        except Exception as e:
            logger.error(f"获取系统信息失败: {e}")
            raise InternalServerException(
                message="获取系统信息失败",
                details={"error": str(e)}
            )

    async def _preload_engine_model(self, engine: TranslationEngine):
        """预加载翻译引擎模型"""
        # TODO: 实现实际的模型预加载逻辑
        logger.info(f"预加载翻译引擎模型: {engine}")
        await asyncio.sleep(1)  # 模拟加载时间

    async def _test_engine_connection(self, engine: TranslationEngine) -> bool:
        """测试翻译引擎连接"""
        # TODO: 实现实际的连接测试逻辑
        logger.info(f"测试翻译引擎连接: {engine}")
        await asyncio.sleep(0.5)  # 模拟测试时间
        return True

    async def _generate_asset_type(self, asset_type: str, languages: Optional[List[str]], include_dependencies: bool, compression_level: int) -> OfflineAssetStatus:
        """生成特定类型的离线资源"""
        from datetime import datetime, timedelta

        logger.info(f"生成离线资源: {asset_type}, 语言: {languages}")

        # 模拟资源生成过程
        await asyncio.sleep(2)

        # 生成模拟数据
        generated_at = datetime.now()
        expires_at = generated_at + timedelta(days=30)

        # 根据资源类型生成不同的数据
        if asset_type == "translation_models":
            total_size = 500 * 1024 * 1024  # 500MB
            file_count = 10
            languages = languages or ["zh", "en", "ja", "ko"]
        elif asset_type == "language_packs":
            total_size = 100 * 1024 * 1024  # 100MB
            file_count = 50
            languages = languages or ["zh", "en", "ja", "ko", "fr", "de", "es"]
        elif asset_type == "fonts":
            total_size = 50 * 1024 * 1024   # 50MB
            file_count = 20
            languages = languages or ["zh", "en", "ja", "ko"]
        else:
            raise BadRequestException(
                message=f"不支持的离线资源类型: {asset_type}",
                details={"supported_types": ["translation_models", "language_packs", "fonts"]}
            )

        compression_ratio = 0.7  # 假设压缩率为70%

        return OfflineAssetStatus(
            asset_type=asset_type,
            total_size=total_size,
            file_count=file_count,
            languages=languages,
            generated_at=generated_at,
            expires_at=expires_at,
            compression_ratio=compression_ratio
        )

    async def _restore_asset_type(self, asset_type: str):
        """恢复特定类型的离线资源"""
        logger.info(f"恢复离线资源: {asset_type}")
        # 模拟资源恢复过程
        await asyncio.sleep(1)

    def _get_memory_usage(self) -> Dict[str, Any]:
        """获取内存使用情况"""
        memory = psutil.virtual_memory()
        process = psutil.Process()
        process_memory = process.memory_info()

        return {
            "system": {
                "total": memory.total,
                "available": memory.available,
                "percent": memory.percent,
                "used": memory.used,
                "free": memory.free
            },
            "process": {
                "rss": process_memory.rss,
                "vms": process_memory.vms,
                "percent": process.memory_percent()
            }
        }

    def _get_performance_metrics(self) -> Dict[str, float]:
        """获取性能指标"""
        cpu_percent = psutil.cpu_percent(interval=1)
        memory_percent = psutil.virtual_memory().percent

        return {
            "cpu_percent": cpu_percent,
            "memory_percent": memory_percent,
            "load_average": getattr(psutil, 'getloadavg', lambda: (0, 0, 0))()[0] if hasattr(psutil, 'getloadavg') else 0
        }

    async def _check_database(self) -> Dict[str, Any]:
        """检查数据库连接"""
        # TODO: 实现实际的数据库连接检查
        return {
            "status": "healthy",
            "latency_ms": 5,
            "connections": 10
        }

    async def _check_redis(self) -> Dict[str, Any]:
        """检查Redis连接"""
        # TODO: 实现实际的Redis连接检查
        return {
            "status": "healthy",
            "latency_ms": 2,
            "memory_usage": "100MB"
        }

    async def _check_storage(self) -> Dict[str, Any]:
        """检查存储连接"""
        # TODO: 实现实际的存储连接检查
        return {
            "status": "healthy",
            "available_space": "10GB",
            "used_space": "5GB"
        }

    async def _check_translation_engines(self) -> Dict[str, Any]:
        """检查翻译引擎连接"""
        # TODO: 实现实际的翻译引擎连接检查
        engine_status = {}
        for engine in TranslationEngine:
            engine_status[engine] = {
                "status": "healthy",
                "latency_ms": 100
            }

        return engine_status


# 全局系统服务实例
system_service = SystemService()