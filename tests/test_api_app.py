from __future__ import annotations

from typing import Any

from fastapi.testclient import TestClient
from pdf2zh_next.api.app import app
from pdf2zh_next.config.cli_env_model import CLIEnvSettingsModel
from pdf2zh_next.config.translate_engine_model import TRANSLATION_ENGINE_METADATA_MAP


def _build_settings_from_overrides(overrides: dict[str, Any]):
    overrides = overrides or {}
    cli_kwargs: dict[str, Any] = {}
    translate_overrides = overrides.get("translate_engine_settings")

    if translate_overrides:
        translate_overrides = dict(translate_overrides)
        engine_type = translate_overrides.pop("translate_engine_type", None)
        if engine_type:
            metadata = TRANSLATION_ENGINE_METADATA_MAP[engine_type]
            cli_kwargs[metadata.cli_flag_name] = True
            if metadata.cli_detail_field_name:
                cli_kwargs[metadata.cli_detail_field_name] = metadata.setting_model_type(
                    **translate_overrides
                )

    cli_settings = CLIEnvSettingsModel(**cli_kwargs)
    return cli_settings.to_settings_model()


def test_health_endpoint():
    client = TestClient(app)
    response = client.get("/v1/health/")
    assert response.status_code == 200
    payload = response.json()
    assert payload["success"] is True
    assert payload["data"]["status"] in {"healthy", "unhealthy"}


def test_build_settings_respects_engine_override():
    overrides = {
        "translate_engine_settings": {
            "translate_engine_type": "OpenAI",
            "openai_api_key": "sk-test",
            "openai_model": "gpt-4o-mini",
        }
    }
    settings = _build_settings_from_overrides(overrides)
    assert settings.translate_engine_settings.translate_engine_type == "OpenAI"


def test_build_settings_defaults_to_siliconflowfree():
    settings = _build_settings_from_overrides({})
    assert (
        settings.translate_engine_settings.translate_engine_type
        == "SiliconFlowFree"
    )
