from __future__ import annotations

from typing import Any


class ErrorMessages:
    """友好错误信息映射"""

    # 内存相关错误
    MEMORY_ERRORS = {
        "exit code -9": {
            "user_message": "翻译任务因内存不足被系统终止",
            "suggestions": [
                "尝试翻译较小的 PDF 文件",
                "联系管理员增加服务器内存",
                "检查服务器内存配置是否合理"
            ],
            "error_code": "OUT_OF_MEMORY"
        },
        "memory limit exceeded": {
            "user_message": "翻译任务超出内存限制",
            "suggestions": [
                "尝试分页翻译较大的 PDF 文件",
                "调整 TRANSLATION_MEMORY_LIMIT_MB 环境变量",
                "减少同时翻译的任务数量"
            ],
            "error_code": "MEMORY_LIMIT_EXCEEDED"
        },
        "cannot allocate memory": {
            "user_message": "系统无法分配足够的内存",
            "suggestions": [
                "释放其他程序占用的内存",
                "重启应用服务",
                "增加服务器内存配置"
            ],
            "error_code": "CANNOT_ALLOCATE_MEMORY"
        }
    }

    # 网络相关错误
    NETWORK_ERRORS = {
        "connection": {
            "user_message": "网络连接失败",
            "suggestions": [
                "检查网络连接是否正常",
                "验证 LLM 服务地址是否正确",
                "检查防火墙设置"
            ],
            "error_code": "CONNECTION_ERROR"
        },
        "timeout": {
            "user_message": "网络请求超时",
            "suggestions": [
                "检查网络延迟",
                "增加请求超时时间",
                "尝试切换网络环境"
            ],
            "error_code": "NETWORK_TIMEOUT"
        },
        "ssl": {
            "user_message": "SSL/TLS 证书验证失败",
            "suggestions": [
                "检查系统时间是否正确",
                "更新证书库",
                "临时禁用证书验证（仅用于测试环境）"
            ],
            "error_code": "SSL_ERROR"
        }
    }

    # API 相关错误
    API_ERRORS = {
        "api_key": {
            "user_message": "API 密钥配置错误",
            "suggestions": [
                "检查 API 密钥是否正确",
                "验证 API 密钥是否有效",
                "确认 API 服务是否正常"
            ],
            "error_code": "API_KEY_ERROR"
        },
        "rate_limit": {
            "user_message": "API 请求频率超限",
            "suggestions": [
                "降低请求频率",
                "升级 API 服务套餐",
                "在请求间添加适当延迟"
            ],
            "error_code": "RATE_LIMIT_ERROR"
        },
        "quota": {
            "user_message": "API 配额已用完",
            "suggestions": [
                "检查 API 账户余额",
                "升级 API 服务套餐",
                "等待配额重置"
            ],
            "error_code": "QUOTA_EXCEEDED"
        }
    }

    # PDF 相关错误
    PDF_ERRORS = {
        "corrupted": {
            "user_message": "PDF 文件损坏或格式不支持",
            "suggestions": [
                "尝试用其他 PDF 阅读器打开文件",
                "重新生成 PDF 文件",
                "尝试转换为其他格式再转换回 PDF"
            ],
            "error_code": "CORRUPTED_PDF"
        },
        "encrypted": {
            "user_message": "PDF 文件已加密",
            "suggestions": [
                "提供正确的密码",
                "使用未加密的 PDF 文件",
                "先解除 PDF 密码保护"
            ],
            "error_code": "ENCRYPTED_PDF"
        },
        "too_large": {
            "user_message": "PDF 文件过大",
            "suggestions": [
                "压缩 PDF 文件大小",
                "分页处理",
                "使用更小的文件进行测试"
            ],
            "error_code": "FILE_TOO_LARGE"
        }
    }

    # 系统相关错误
    SYSTEM_ERRORS = {
        "permission": {
            "user_message": "文件权限不足",
            "suggestions": [
                "检查文件和目录权限",
                "使用正确的用户运行服务",
                "确保临时目录可写"
            ],
            "error_code": "PERMISSION_ERROR"
        },
        "disk_space": {
            "user_message": "磁盘空间不足",
            "suggestions": [
                "清理临时文件",
                "扩展磁盘空间",
                "移动大文件到其他位置"
            ],
            "error_code": "DISK_SPACE_ERROR"
        }
    }

    @classmethod
    def get_friendly_error(cls, error_message: str) -> dict[str, Any]:
        """根据原始错误信息返回友好的错误描述"""
        error_lower = error_message.lower()

        # 检查内存错误
        for pattern, error_info in cls.MEMORY_ERRORS.items():
            if pattern in error_lower:
                return error_info

        # 检查网络错误
        for pattern, error_info in cls.NETWORK_ERRORS.items():
            if pattern in error_lower:
                return error_info

        # 检查 API 错误
        for pattern, error_info in cls.API_ERRORS.items():
            if pattern in error_lower:
                return error_info

        # 检查 PDF 错误
        for pattern, error_info in cls.PDF_ERRORS.items():
            if pattern in error_lower:
                return error_info

        # 检查系统错误
        for pattern, error_info in cls.SYSTEM_ERRORS.items():
            if pattern in error_lower:
                return error_info

        # 默认错误信息
        return {
            "user_message": "翻译过程中发生未知错误",
            "suggestions": [
                "检查错误日志获取更多详细信息",
                "尝试使用较小的 PDF 文件",
                "联系技术支持"
            ],
            "error_code": "UNKNOWN_ERROR"
        }

    @classmethod
    def format_api_error_response(cls, original_error: str) -> dict[str, Any]:
        """格式化 API 错误响应"""
        friendly_error = cls.get_friendly_error(original_error)

        return {
            "success": False,
            "error": {
                "code": friendly_error["error_code"],
                "message": friendly_error["user_message"],
                "suggestions": friendly_error["suggestions"],
                "technical_details": original_error
            },
            "timestamp": None  # 会在调用处设置
        }