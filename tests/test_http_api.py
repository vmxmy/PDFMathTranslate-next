from fastapi.testclient import TestClient
from pdf2zh_next.http_api import _build_settings
from pdf2zh_next.http_api import app


def test_health_endpoint():
    client = TestClient(app)
    response = client.get("/v1/health")
    assert response.status_code == 200
    payload = response.json()
    assert payload.get("status") == "ok"
    assert "version" in payload


def test_build_settings_respects_engine_override():
    overrides = {
        "translate_engine_settings": {
            "translate_engine_type": "OpenAI",
            "openai_api_key": "sk-test",
            "openai_model": "gpt-4o-mini",
        }
    }
    settings = _build_settings(overrides)
    assert settings.translate_engine_settings.translate_engine_type == "OpenAI"


def test_build_settings_defaults_to_siliconflowfree():
    settings = _build_settings({})
    assert settings.translate_engine_settings.translate_engine_type == "SiliconFlowFree"
