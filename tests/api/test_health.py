import pytest
from fastapi.testclient import TestClient
from sqlalchemy.exc import SQLAlchemyError

from webhook_delivery_platform.api.routes import health
from webhook_delivery_platform.main import create_app


@pytest.fixture
def client() -> TestClient:
    return TestClient(create_app())


def test_health_live_returns_success(client: TestClient) -> None:
    response = client.get("/health/live")

    assert response.status_code == 200
    assert response.json() == {"status": "alive"}


def test_health_ready_returns_success(client: TestClient) -> None:
    response = client.get("/health/ready")

    assert response.status_code == 200
    assert response.json() == {
        "status": "ready",
        "database": "connected",
    }


def test_health_ready_returns_503_when_database_unavailable(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fail_connection():
        raise SQLAlchemyError("Simulated database failure")

    monkeypatch.setattr(health.engine, "connect", fail_connection)

    response = client.get("/health/ready")

    assert response.status_code == 503
    assert response.json() == {"detail": "Database unavailable"}
