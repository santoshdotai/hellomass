from fastapi.testclient import TestClient

from backend.main import app


def test_health_endpoint_reports_ok():
    with TestClient(app) as client:
        resp = client.get("/api/health")
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "ok"
        assert data["app"] == "SOUVENO VISION"
        assert "inference_device" in data


def test_zone_types_endpoint():
    with TestClient(app) as client:
        resp = client.get("/api/zones/types")
        assert resp.status_code == 200
        assert "QUEUE_ZONE" in resp.json()["zone_types"]


def test_upload_rejects_unsupported_extension():
    with TestClient(app) as client:
        resp = client.post("/api/sessions/upload", files={"file": ("clip.txt", b"not a video", "text/plain")})
        assert resp.status_code == 400
