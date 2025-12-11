"""Helpers to construct SettingsModel for translation tasks."""

from __future__ import annotations

import copy
from typing import Any

from pdf2zh_next.config.cli_env_model import CLIEnvSettingsModel
from pdf2zh_next.config.translate_engine_model import TRANSLATION_ENGINE_METADATA_MAP

DEFAULT_CLI_SETTINGS = CLIEnvSettingsModel()
DEFAULT_CLI_SETTINGS_DICT = DEFAULT_CLI_SETTINGS.model_dump(mode="json")

ENGINE_TYPE_MAP = {
    "google": "Google",
    "deepl": "DeepL",
    "openai": "OpenAI",
    "openaicompatible": "OpenAICompatible",
    "tencent": "TencentMechineTranslation",
    "baidu": "Baidu",
}


def _deep_merge(base: dict[str, Any], overrides: dict[str, Any]) -> dict[str, Any]:
    result: dict[str, Any] = copy.deepcopy(base)
    for key, value in overrides.items():
        if (
            key in result
            and isinstance(result[key], dict)
            and isinstance(value, dict)
        ):
            result[key] = _deep_merge(result[key], value)
        else:
            result[key] = value
    return result


def _normalize_translate_engine_payload(payload: dict[str, Any]) -> dict[str, Any]:
    payload = copy.deepcopy(payload)
    engine_payload = payload.get("translate_engine_settings") or {}
    if not engine_payload:
        return payload

    engine_type = engine_payload.get("translate_engine_type")
    if not engine_type:
        return payload

    metadata = TRANSLATION_ENGINE_METADATA_MAP.get(engine_type)
    if metadata is None:
        return payload

    normalized: dict[str, Any] = {}
    for meta in TRANSLATION_ENGINE_METADATA_MAP.values():
        normalized[meta.cli_flag_name] = False
        if meta.cli_detail_field_name:
            normalized[meta.cli_detail_field_name] = {}

    normalized[metadata.cli_flag_name] = True
    detail_fields = {
        key: value
        for key, value in engine_payload.items()
        if key != "translate_engine_type"
    }
    if metadata.cli_detail_field_name:
        normalized[metadata.cli_detail_field_name] = detail_fields

    payload.pop("translate_engine_settings", None)
    payload.update(normalized)
    return payload


def build_settings_model(
    request_overrides: dict[str, Any] | None = None,
    engine_payload: dict[str, Any] | None = None,
    extra_overrides: dict[str, Any] | None = None,
) -> CLIEnvSettingsModel:
    merged = copy.deepcopy(DEFAULT_CLI_SETTINGS_DICT)
    if engine_payload:
        merged = _deep_merge(
            merged,
            _normalize_translate_engine_payload(
                {"translate_engine_settings": engine_payload}
            ),
        )
    if extra_overrides:
        merged = _deep_merge(
            merged,
            _normalize_translate_engine_payload(extra_overrides),
        )
    if request_overrides:
        merged = _deep_merge(merged, request_overrides)
    return CLIEnvSettingsModel.model_validate(merged)


__all__ = [
    "build_settings_model",
    "ENGINE_TYPE_MAP",
]
