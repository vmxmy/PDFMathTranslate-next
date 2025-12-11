"""配置服务"""
import json
import logging
from datetime import datetime
from pathlib import Path
from typing import Any

from ..exceptions import InternalServerException
from ..models import ConfigResponse
from ..models import ConfigUpdateRequest
from ..models import ValidationMode

logger = logging.getLogger(__name__)


class ConfigService:
    """配置服务"""
    def __init__(self):
        self.config_file = Path("config/api_config.json")
        self.config_schema_file = Path("config/api_config_schema.json")
        self.config_data = {}
        self.config_schema = {}
        self.last_updated = datetime.now()
        self._load_config()
        self._load_schema()

    def _load_config(self):
        """加载配置文件"""
        try:
            if self.config_file.exists():
                with self.config_file.open(encoding="utf-8") as file:
                    self.config_data = json.load(file)
                logger.info("配置文件加载成功")
            else:
                # 使用默认配置
                self.config_data = self._get_default_config()
                self._save_config()
                logger.info("使用默认配置")
        except Exception as e:
            logger.error(f"加载配置文件失败：{e}")
            self.config_data = self._get_default_config()

    def _load_schema(self):
        """加载配置 schema"""
        try:
            if self.config_schema_file.exists():
                with self.config_schema_file.open(encoding="utf-8") as file:
                    self.config_schema = json.load(file)
                logger.info("配置 schema 加载成功")
            else:
                # 使用默认 schema
                self.config_schema = self._get_default_schema()
                self._save_schema()
                logger.info("使用默认配置 schema")
        except Exception as e:
            logger.error(f"加载配置 schema 失败：{e}")
            self.config_schema = self._get_default_schema()

    def _save_config(self):
        """保存配置文件"""
        try:
            self.config_file.parent.mkdir(parents=True, exist_ok=True)
            with self.config_file.open("w", encoding="utf-8") as file:
                json.dump(self.config_data, file, indent=2, ensure_ascii=False)
            logger.info("配置文件保存成功")
        except Exception as exc:
            logger.error(f"保存配置文件失败：{exc}")
            raise InternalServerException(
                message="保存配置失败",
                details={"error": str(exc)}
            ) from exc

    def _save_schema(self):
        """保存配置 schema"""
        try:
            self.config_schema_file.parent.mkdir(parents=True, exist_ok=True)
            with self.config_schema_file.open("w", encoding="utf-8") as file:
                json.dump(self.config_schema, file, indent=2, ensure_ascii=False)
            logger.info("配置 schema 保存成功")
        except Exception as exc:
            logger.error(f"保存配置 schema 失败：{exc}")
            raise InternalServerException(
                message="保存配置 schema 失败",
                details={"error": str(exc)}
            ) from exc

    def _get_default_config(self) -> dict[str, Any]:
        """获取默认配置"""
        return {
            "translation": {
                "default_engine": "google",
                "timeout": 3600,
                "max_file_size": 104857600,  # 100MB
                "max_concurrent_tasks": 10,
                "supported_formats": [".pdf"],
                "quality_threshold": 0.8,
                "retry_count": 3,
                "retry_delay": 5,
                "engines": {
                    "google": {
                        "enabled": True,
                        "api_key": "",
                        "timeout": 30,
                        "max_chars_per_request": 5000
                    },
                    "deepl": {
                        "enabled": True,
                        "api_key": "",
                        "timeout": 30,
                        "max_chars_per_request": 5000
                    },
                    "openai": {
                        "enabled": True,
                        "api_key": "",
                        "timeout": 60,
                        "max_chars_per_request": 4000,
                        "model": "gpt-3.5-turbo"
                    }
                }
            },
            "system": {
                "cleanup_interval": 300,  # 5 分钟
                "task_retention_hours": 24,
                "log_level": "INFO",
                "max_log_files": 10,
                "log_rotation_size": 10485760,  # 10MB
                "performance_monitoring": {
                    "enabled": True,
                    "metrics_interval": 60,
                    "alert_thresholds": {
                        "cpu_percent": 80,
                        "memory_percent": 85,
                        "disk_percent": 90
                    }
                }
            },
            "logging": {
                "level": "INFO",
                "format": "%(asctime)s - %(name)s - %(levelname)s - %(message)s",
                "handlers": {
                    "console": {
                        "enabled": True,
                        "level": "INFO"
                    },
                    "file": {
                        "enabled": True,
                        "level": "DEBUG",
                        "filename": "logs/api.log",
                        "max_size": 10485760,  # 10MB
                        "backup_count": 5
                    }
                }
            },
            "api": {
                "rate_limit": {
                    "default": {
                        "requests_per_minute": 60,
                        "requests_per_hour": 1000,
                        "burst_size": 10
                    },
                    "user": {
                        "requests_per_minute": 30,
                        "requests_per_hour": 500,
                        "burst_size": 5
                    },
                    "guest": {
                        "requests_per_minute": 10,
                        "requests_per_hour": 100,
                        "burst_size": 2
                    }
                },
                "cors": {
                    "enabled": True,
                    "allow_origins": ["*"],
                    "allow_methods": ["*"],
                    "allow_headers": ["*"]
                },
                "timeout": {
                    "request": 300,  # 5 分钟
                    "keep_alive": 75
                }
            }
        }

    def _get_default_schema(self) -> dict[str, Any]:
        """获取默认配置 schema"""
        return {
            "$schema": "http://json-schema.org/draft-07/schema#",
            "type": "object",
            "properties": {
                "translation": {
                    "type": "object",
                    "properties": {
                        "default_engine": {
                            "type": "string",
                            "enum": [
                                "google",
                                "deepl",
                                "openai",
                                "openaicompatible",
                                "baidu",
                                "tencent",
                                "siliconflowfree",
                            ],
                        },
                        "timeout": {"type": "integer", "minimum": 60, "maximum": 7200},
                        "max_file_size": {"type": "integer", "minimum": 1048576, "maximum": 1073741824},
                        "max_concurrent_tasks": {"type": "integer", "minimum": 1, "maximum": 100},
                        "supported_formats": {"type": "array", "items": {"type": "string"}},
                        "quality_threshold": {"type": "number", "minimum": 0.0, "maximum": 1.0},
                        "retry_count": {"type": "integer", "minimum": 0, "maximum": 10},
                        "retry_delay": {"type": "integer", "minimum": 1, "maximum": 300}
                    },
                    "required": ["default_engine", "timeout", "max_file_size"]
                },
                "system": {
                    "type": "object",
                    "properties": {
                        "cleanup_interval": {"type": "integer", "minimum": 60, "maximum": 3600},
                        "task_retention_hours": {"type": "integer", "minimum": 1, "maximum": 168},
                        "log_level": {"type": "string", "enum": ["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"]}
                    }
                },
                "logging": {
                    "type": "object",
                    "properties": {
                        "level": {"type": "string", "enum": ["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"]},
                        "format": {"type": "string"},
                        "handlers": {"type": "object"}
                    }
                },
                "api": {
                    "type": "object",
                    "properties": {
                        "rate_limit": {"type": "object"},
                        "cors": {"type": "object"},
                        "timeout": {"type": "object"}
                    }
                }
            },
            "required": ["translation", "system", "api"]
        }

    def get_config(self) -> ConfigResponse:
        """获取当前配置"""
        return ConfigResponse(
            current_config=self.config_data,
            config_schema=self.config_schema,
            last_updated=self.last_updated,
            validation_errors=None
        )

    def get_config_schema(self) -> dict[str, Any]:
        """获取配置 schema"""
        return self.config_schema

    def update_config(self, request: ConfigUpdateRequest) -> ConfigResponse:
        """更新配置"""
        validation_errors = []

        try:
            # 验证和更新各个配置段
            if request.translation is not None:
                errors = self._validate_and_update_section("translation", request.translation, request.validation_mode)
                validation_errors.extend(errors)

            if request.system is not None:
                errors = self._validate_and_update_section("system", request.system, request.validation_mode)
                validation_errors.extend(errors)

            if request.logging is not None:
                errors = self._validate_and_update_section("logging", request.logging, request.validation_mode)
                validation_errors.extend(errors)

            # 如果有验证错误且是严格模式，则不保存
            if validation_errors and request.validation_mode == ValidationMode.STRICT:
                return ConfigResponse(
                    current_config=self.config_data,
                    config_schema=self.config_schema,
                    last_updated=self.last_updated,
                    validation_errors=validation_errors
                )

            # 保存配置
            self.last_updated = datetime.now()
            self._save_config()

            logger.info("配置更新成功")
            return ConfigResponse(
                current_config=self.config_data,
                config_schema=self.config_schema,
                last_updated=self.last_updated,
                validation_errors=validation_errors if validation_errors else None
            )

        except Exception as exc:
            logger.error(f"配置更新失败：{exc}")
            raise InternalServerException(
                message="配置更新失败",
                details={"error": str(exc)}
            ) from exc

    def reset_config(self) -> ConfigResponse:
        """重置为默认配置"""
        try:
            self.config_data = self._get_default_config()
            self.last_updated = datetime.now()
            self._save_config()

            logger.info("配置重置成功")
            return self.get_config()

        except Exception as exc:
            logger.error(f"配置重置失败：{exc}")
            raise InternalServerException(
                message="配置重置失败",
                details={"error": str(exc)}
            ) from exc

    def _validate_and_update_section(self, section: str, new_config: dict[str, Any], validation_mode: ValidationMode) -> list[str]:
        """验证和更新配置段"""
        errors = []

        try:
            # 获取对应段的 schema
            section_schema = self.config_schema.get("properties", {}).get(section)
            if not section_schema:
                if validation_mode == ValidationMode.STRICT:
                    errors.append(f"未知的配置段：{section}")
                return errors

            # 基本验证
            for key, value in new_config.items():
                if key not in section_schema.get("properties", {}):
                    if validation_mode == ValidationMode.STRICT:
                        errors.append(f"未知的配置项：{section}.{key}")
                    continue

                # 类型验证
                expected_type = section_schema["properties"][key].get("type")
                if expected_type and not self._validate_type(value, expected_type):
                    errors.append(f"配置项类型错误：{section}.{key}, 期望类型：{expected_type}")

            # 如果有错误且是严格模式，返回错误
            if errors and validation_mode == ValidationMode.STRICT:
                return errors

            # 更新配置
            if section not in self.config_data:
                self.config_data[section] = {}

            self.config_data[section].update(new_config)

        except Exception as e:
            errors.append(f"配置段验证失败：{section}, {str(e)}")

        return errors

    def _validate_type(self, value: Any, expected_type: str) -> bool:
        """验证类型"""
        if expected_type == "string":
            return isinstance(value, str)
        elif expected_type == "integer":
            return isinstance(value, int)
        elif expected_type == "number":
            return isinstance(value, (int, float))
        elif expected_type == "boolean":
            return isinstance(value, bool)
        elif expected_type == "array":
            return isinstance(value, list)
        elif expected_type == "object":
            return isinstance(value, dict)
        return True

    def get_translation_config(self) -> dict[str, Any]:
        """获取翻译配置"""
        return self.config_data.get("translation", {})

    def get_system_config(self) -> dict[str, Any]:
        """获取系统配置"""
        return self.config_data.get("system", {})

    def get_api_config(self) -> dict[str, Any]:
        """获取 API 配置"""
        return self.config_data.get("api", {})

    def get_logging_config(self) -> dict[str, Any]:
        """获取日志配置"""
        return self.config_data.get("logging", {})


# 全局配置服务实例
config_service = ConfigService()
