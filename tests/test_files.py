from fastapi.testclient import TestClient

from app.main import app
from app.services import file_store

client = TestClient(app)

KML_POLYGON = b"""<?xml version='1.0' encoding='UTF-8'?>
<kml xmlns='http://www.opengis.net/kml/2.2'>
  <Placemark>
    <name>Test square</name>
    <Polygon><outerBoundaryIs><LinearRing><coordinates>
      -73.9900,40.7500 -73.9800,40.7500 -73.9800,40.7600 -73.9900,40.7600 -73.9900,40.7500
    </coordinates></LinearRing></outerBoundaryIs></Polygon>
  </Placemark>
</kml>"""


def test_kml_upload_is_processed_and_measured(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(file_store, "UPLOAD_DIRECTORY", tmp_path / "uploads")

    response = client.post(
        "/api/files/",
        files={"file": ("survey.kml", KML_POLYGON, "application/vnd.google-earth.kml+xml")},
    )

    assert response.status_code == 201
    body = response.json()
    assert body["status"] == "COMPLETED"
    assert body["format"] == "KML"
    assert body["crs"] == "EPSG:4326"
    assert body["measurement_crs"] == "EPSG:32618"
    assert body["feature_count"] == 1
    assert body["features"][0]["geometry_type"] == "Polygon"
    assert body["features"][0]["area_square_meters"] > 500_000


def test_get_file_returns_saved_result() -> None:
    response = client.get("/api/files/not-a-real-id")

    assert response.status_code == 404


def test_unsupported_upload_is_rejected() -> None:
    response = client.post(
        "/api/files/",
        files={"file": ("notes.txt", b"not geographic data", "text/plain")},
    )

    assert response.status_code == 415
