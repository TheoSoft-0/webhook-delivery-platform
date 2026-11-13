from uuid import UUID

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from webhook_delivery_platform.api.dependencies import get_db_session
from webhook_delivery_platform.main import create_app
from webhook_delivery_platform.models import (
    ApiKey,
    Application,
    Destination,
)
from webhook_delivery_platform.security.api_keys import (
    generate_api_key,
    hash_api_key,
)
from webhook_delivery_platform.security.destination_secrets import (
    decrypt_signing_secret,
)


@pytest.fixture
def client(db_session):
    app = create_app()

    app.dependency_overrides[get_db_session] = lambda: db_session

    with TestClient(app) as test_client:
        yield test_client

    app.dependency_overrides.clear()


def create_authenticated_application(session):
    application = Application(name="Destination Test Application")
    raw_api_key = generate_api_key()

    api_key = ApiKey(
        application=application,
        key_hash=hash_api_key(raw_api_key),
    )

    session.add(application)
    session.add(api_key)
    session.flush()

    return application, raw_api_key


def test_create_destination(client, db_session):
    application, raw_api_key = create_authenticated_application(db_session)

    response = client.post(
        "/v1/destinations",
        headers={"Authorization": f"Bearer {raw_api_key}"},
        json={"url": "https://example.com/webhooks"},
    )

    assert response.status_code == 201

    body = response.json()

    assert body["url"] == "https://example.com/webhooks"
    assert body["is_enabled"] is True
    assert body["signing_secret"].startswith("whsec_")
    assert body["created_at"] is not None

    destination = db_session.scalar(
        select(Destination).where(Destination.id == UUID(body["id"]))
    )

    assert destination is not None
    assert destination.application_id == application.id

    assert destination.signing_secret_ciphertext != body["signing_secret"]

    assert (
        decrypt_signing_secret(destination.signing_secret_ciphertext)
        == body["signing_secret"]
    )


@pytest.mark.parametrize(
    "url",
    [
        "http://127.0.0.1/webhooks",
        "http://localhost/webhooks",
        "ftp://example.com/webhooks",
    ],
)
def test_create_destination_rejects_invalid_urls(
    client,
    db_session,
    url,
):
    _, raw_api_key = create_authenticated_application(db_session)

    response = client.post(
        "/v1/destinations",
        headers={"Authorization": f"Bearer {raw_api_key}"},
        json={"url": url},
    )

    assert response.status_code == 422


def test_create_destination_rejects_application_id_from_client(
    client,
    db_session,
):
    _, raw_api_key = create_authenticated_application(db_session)

    response = client.post(
        "/v1/destinations",
        headers={"Authorization": f"Bearer {raw_api_key}"},
        json={
            "url": "https://example.com/webhooks",
            "application_id": "00000000-0000-0000-0000-000000000001",
        },
    )

    assert response.status_code == 422


def test_create_destination_requires_authentication(client):
    response = client.post(
        "/v1/destinations",
        json={"url": "https://example.com/webhooks"},
    )

    assert response.status_code == 401
