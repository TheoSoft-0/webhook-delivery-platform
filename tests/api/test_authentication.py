from collections.abc import Iterator
from datetime import UTC, datetime
from typing import Annotated
from uuid import UUID

import pytest
from fastapi import Depends, FastAPI
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from webhook_delivery_platform.api.authentication import (
    get_current_application,
)
from webhook_delivery_platform.api.dependencies import get_db_session
from webhook_delivery_platform.models import ApiKey, Application
from webhook_delivery_platform.security.api_keys import (
    generate_api_key,
    hash_api_key,
)


@pytest.fixture
def auth_client(db_session: Session) -> Iterator[TestClient]:
    """Create a test application with database-backed authentication."""

    test_app = FastAPI()

    @test_app.get("/protected")
    def protected_endpoint(
        application: Annotated[
            Application,
            Depends(get_current_application),
        ],
    ) -> dict[str, str]:
        return {"application_id": str(application.id)}

    test_app.dependency_overrides[get_db_session] = lambda: db_session

    try:
        with TestClient(test_app) as client:
            yield client
    finally:
        test_app.dependency_overrides.clear()


def create_test_api_key(
    session: Session,
    revoked: bool = False,
) -> tuple[str, UUID]:
    """Create an application and API key for authentication tests."""

    raw_api_key = generate_api_key()

    application = Application(name="Authentication Test Application")

    api_key = ApiKey(
        application=application,
        key_hash=hash_api_key(raw_api_key),
        revoked_at=datetime.now(UTC) if revoked else None,
    )

    session.add(api_key)
    session.flush()

    return raw_api_key, application.id


def test_valid_api_key_authenticates_application(
    auth_client: TestClient,
    db_session: Session,
) -> None:
    raw_api_key, application_id = create_test_api_key(db_session)

    response = auth_client.get(
        "/protected",
        headers={"Authorization": f"Bearer {raw_api_key}"},
    )

    assert response.status_code == 200
    assert response.json() == {
        "application_id": str(application_id),
    }


def test_missing_api_key_is_rejected(
    auth_client: TestClient,
) -> None:
    response = auth_client.get("/protected")

    assert response.status_code == 401
    assert response.headers["www-authenticate"] == "Bearer"


def test_invalid_api_key_is_rejected(
    auth_client: TestClient,
) -> None:
    response = auth_client.get(
        "/protected",
        headers={"Authorization": "Bearer wdp_invalid_key"},
    )

    assert response.status_code == 401


def test_non_bearer_authorization_is_rejected(
    auth_client: TestClient,
) -> None:
    response = auth_client.get(
        "/protected",
        headers={"Authorization": "Basic invalid_credentials"},
    )

    assert response.status_code == 401


def test_revoked_api_key_is_rejected(
    auth_client: TestClient,
    db_session: Session,
) -> None:
    raw_api_key, _ = create_test_api_key(
        db_session,
        revoked=True,
    )

    response = auth_client.get(
        "/protected",
        headers={"Authorization": f"Bearer {raw_api_key}"},
    )

    assert response.status_code == 401
