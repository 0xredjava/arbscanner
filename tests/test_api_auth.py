from fastapi.testclient import TestClient

from app import app, settings


def test_manual_scan_requires_admin_token():
    original = settings.admin_token
    settings.admin_token = "secret"
    try:
        client = TestClient(app)
        response = client.post("/api/scans/run")
        assert response.status_code == 401
    finally:
        settings.admin_token = original
