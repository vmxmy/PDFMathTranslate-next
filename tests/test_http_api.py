from fastapi.testclient import TestClient

from pdf2zh_next.http_api import app


def test_health_endpoint():
    client = TestClient(app)
    response = client.get("/v1/health")
    assert response.status_code == 200
    payload = response.json()
    assert payload.get("status") == "ok"
    assert "version" in payload
