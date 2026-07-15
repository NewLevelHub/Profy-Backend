from fastapi.testclient import TestClient

from app.main import app


def test_app_boots_and_serves_openapi():
    """Proves the harness: app.main:app imports cleanly, its lifespan can
    reach the real Postgres service (TestClient runs startup/shutdown), and
    routing/schemas assemble without error."""
    with TestClient(app) as client:
        response = client.get("/openapi.json")
    assert response.status_code == 200
