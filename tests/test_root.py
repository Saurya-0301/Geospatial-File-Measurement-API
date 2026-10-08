from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def test_root_serves_the_browser_interface() -> None:
    response = client.get("/")

    assert response.status_code == 200
    assert "Measure a map file" in response.text


def test_health_reports_service_is_running() -> None:
    response = client.get("/api/health")

    assert response.status_code == 200
    assert response.json() == {"message": "Geospatial File Measurement API is running."}
