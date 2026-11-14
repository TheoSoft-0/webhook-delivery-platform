from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from webhook_delivery_platform.api.dependencies import get_db_session
from webhook_delivery_platform.main import create_app
from webhook_delivery_platform.models import (
    ApiKey,
    Application,
    Destination,
    Subscription,
)
from webhook_delivery_platform.security.api_keys import (
    generate_api_key,
    hash_api_key,
)
from webhook_delivery_platform.security.destination_secrets import (
    decrypt_signing_secret,
    encrypt_signing_secret,
    generate_signing_secret,
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


def create_destination_record(
    session,
    application,
    url,
    is_enabled=True,
):
    destination = Destination(
        application_id=application.id,
        url=url,
        signing_secret_ciphertext=encrypt_signing_secret(generate_signing_secret()),
        is_enabled=is_enabled,
    )

    session.add(destination)
    session.flush()

    return destination


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


def test_list_destinations_returns_only_authenticated_applications_destinations(
    client,
    db_session,
):
    application, raw_api_key = create_authenticated_application(db_session)

    another_application, _ = create_authenticated_application(db_session)

    first_destination = create_destination_record(
        db_session,
        application,
        "https://first.example.com/webhooks",
    )

    second_destination = create_destination_record(
        db_session,
        application,
        "https://second.example.com/webhooks",
        is_enabled=False,
    )

    foreign_destination = create_destination_record(
        db_session,
        another_application,
        "https://foreign.example.com/webhooks",
    )

    response = client.get(
        "/v1/destinations",
        headers={"Authorization": f"Bearer {raw_api_key}"},
    )

    assert response.status_code == 200

    body = response.json()

    returned_ids = {item["id"] for item in body}

    assert returned_ids == {
        str(first_destination.id),
        str(second_destination.id),
    }

    assert str(foreign_destination.id) not in returned_ids

    for item in body:
        assert set(item) == {
            "id",
            "url",
            "is_enabled",
            "created_at",
        }


def test_list_destinations_returns_empty_list_when_application_has_none(
    client,
    db_session,
):
    _, raw_api_key = create_authenticated_application(db_session)

    response = client.get(
        "/v1/destinations",
        headers={"Authorization": f"Bearer {raw_api_key}"},
    )

    assert response.status_code == 200
    assert response.json() == []


def test_get_destination_returns_owned_destination(client, db_session):
    application, raw_api_key = create_authenticated_application(db_session)

    destination = create_destination_record(
        db_session,
        application,
        "https://example.com/webhooks",
    )

    response = client.get(
        f"/v1/destinations/{destination.id}",
        headers={"Authorization": f"Bearer {raw_api_key}"},
    )

    assert response.status_code == 200

    body = response.json()

    assert body["id"] == str(destination.id)
    assert body["url"] == destination.url
    assert body["is_enabled"] is True
    assert body["created_at"] is not None

    assert "signing_secret" not in body
    assert "signing_secret_ciphertext" not in body


def test_get_destination_rejects_another_applications_destination(
    client,
    db_session,
):
    _application, raw_api_key = create_authenticated_application(db_session)

    another_application, _ = create_authenticated_application(db_session)

    foreign_destination = create_destination_record(
        db_session,
        another_application,
        "https://foreign.example.com/webhooks",
    )

    response = client.get(
        f"/v1/destinations/{foreign_destination.id}",
        headers={"Authorization": f"Bearer {raw_api_key}"},
    )

    assert response.status_code == 404
    assert response.json()["detail"] == "Destination not found"


def test_get_destination_returns_404_for_unknown_destination(
    client,
    db_session,
):
    _, raw_api_key = create_authenticated_application(db_session)

    response = client.get(
        f"/v1/destinations/{uuid4()}",
        headers={"Authorization": f"Bearer {raw_api_key}"},
    )

    assert response.status_code == 404


def test_list_destinations_requires_authentication(client):
    response = client.get("/v1/destinations")

    assert response.status_code == 401


def test_get_destination_requires_authentication(client):
    response = client.get(f"/v1/destinations/{uuid4()}")

    assert response.status_code == 401


def test_disable_destination(client, db_session):
    application, raw_api_key = create_authenticated_application(db_session)

    destination = create_destination_record(
        db_session,
        application,
        "https://example.com/webhooks",
    )

    response = client.patch(
        f"/v1/destinations/{destination.id}",
        headers={"Authorization": f"Bearer {raw_api_key}"},
        json={"is_enabled": False},
    )

    assert response.status_code == 200

    body = response.json()

    assert body["id"] == str(destination.id)
    assert body["is_enabled"] is False
    assert "signing_secret" not in body
    assert "signing_secret_ciphertext" not in body

    assert destination.is_enabled is False


def test_enable_destination(client, db_session):
    application, raw_api_key = create_authenticated_application(db_session)

    destination = create_destination_record(
        db_session,
        application,
        "https://example.com/webhooks",
        is_enabled=False,
    )

    response = client.patch(
        f"/v1/destinations/{destination.id}",
        headers={"Authorization": f"Bearer {raw_api_key}"},
        json={"is_enabled": True},
    )

    assert response.status_code == 200
    assert response.json()["is_enabled"] is True
    assert destination.is_enabled is True


def test_update_destination_rejects_another_applications_destination(
    client,
    db_session,
):
    _, raw_api_key = create_authenticated_application(db_session)

    another_application, _ = create_authenticated_application(db_session)

    foreign_destination = create_destination_record(
        db_session,
        another_application,
        "https://foreign.example.com/webhooks",
    )

    response = client.patch(
        f"/v1/destinations/{foreign_destination.id}",
        headers={"Authorization": f"Bearer {raw_api_key}"},
        json={"is_enabled": False},
    )

    assert response.status_code == 404
    assert foreign_destination.is_enabled is True


def test_update_destination_returns_404_for_unknown_destination(
    client,
    db_session,
):
    _, raw_api_key = create_authenticated_application(db_session)

    response = client.patch(
        f"/v1/destinations/{uuid4()}",
        headers={"Authorization": f"Bearer {raw_api_key}"},
        json={"is_enabled": False},
    )

    assert response.status_code == 404


def test_update_destination_requires_authentication(client, db_session):
    response = client.patch(
        f"/v1/destinations/{uuid4()}",
        json={"is_enabled": False},
    )

    assert response.status_code == 401


def test_update_destination_rejects_empty_request(client, db_session):
    _, raw_api_key = create_authenticated_application(db_session)

    destination_id = uuid4()

    response = client.patch(
        f"/v1/destinations/{destination_id}",
        headers={"Authorization": f"Bearer {raw_api_key}"},
        json={},
    )

    assert response.status_code == 422


def test_add_destination_subscription(client, db_session):
    application, raw_api_key = create_authenticated_application(db_session)

    destination = create_destination_record(
        db_session,
        application,
        "https://example.com/webhooks",
    )

    response = client.put(
        f"/v1/destinations/{destination.id}/subscriptions/payment.completed",
        headers={"Authorization": f"Bearer {raw_api_key}"},
    )

    assert response.status_code == 204

    subscription = db_session.scalar(
        select(Subscription).where(
            Subscription.destination_id == destination.id,
            Subscription.event_type == "payment.completed",
        )
    )

    assert subscription is not None


def test_add_destination_subscription_is_idempotent(client, db_session):
    application, raw_api_key = create_authenticated_application(db_session)

    destination = create_destination_record(
        db_session,
        application,
        "https://example.com/webhooks",
    )

    url = f"/v1/destinations/{destination.id}/subscriptions/payment.completed"

    headers = {"Authorization": f"Bearer {raw_api_key}"}

    first_response = client.put(url, headers=headers)
    second_response = client.put(url, headers=headers)

    assert first_response.status_code == 204
    assert second_response.status_code == 204

    subscriptions = db_session.scalars(
        select(Subscription).where(
            Subscription.destination_id == destination.id,
            Subscription.event_type == "payment.completed",
        )
    ).all()

    assert len(subscriptions) == 1


def test_add_subscription_rejects_another_applications_destination(
    client,
    db_session,
):
    _, raw_api_key = create_authenticated_application(db_session)

    another_application, _ = create_authenticated_application(db_session)

    foreign_destination = create_destination_record(
        db_session,
        another_application,
        "https://foreign.example.com/webhooks",
    )

    response = client.put(
        f"/v1/destinations/{foreign_destination.id}/subscriptions/payment.completed",
        headers={"Authorization": f"Bearer {raw_api_key}"},
    )

    assert response.status_code == 404

    subscription = db_session.scalar(
        select(Subscription).where(
            Subscription.destination_id == foreign_destination.id,
            Subscription.event_type == "payment.completed",
        )
    )

    assert subscription is None


def test_add_subscription_rejects_blank_event_type(client, db_session):
    application, raw_api_key = create_authenticated_application(db_session)

    destination = create_destination_record(
        db_session,
        application,
        "https://example.com/webhooks",
    )

    response = client.put(
        f"/v1/destinations/{destination.id}/subscriptions/%20%20%20",
        headers={"Authorization": f"Bearer {raw_api_key}"},
    )

    assert response.status_code == 422


def test_add_subscription_requires_authentication(client, db_session):
    response = client.put(
        f"/v1/destinations/{uuid4()}/subscriptions/payment.completed",
    )

    assert response.status_code == 401


def test_delete_destination_subscription(client, db_session):
    application, raw_api_key = create_authenticated_application(db_session)

    destination = create_destination_record(
        db_session,
        application,
        "https://example.com/webhooks",
    )

    subscription = Subscription(
        destination=destination,
        event_type="payment.completed",
    )

    db_session.add(subscription)
    db_session.flush()

    response = client.delete(
        f"/v1/destinations/{destination.id}/subscriptions/payment.completed",
        headers={"Authorization": f"Bearer {raw_api_key}"},
    )

    assert response.status_code == 204

    remaining_subscription = db_session.scalar(
        select(Subscription).where(
            Subscription.destination_id == destination.id,
            Subscription.event_type == "payment.completed",
        )
    )

    assert remaining_subscription is None


def test_delete_destination_subscription_is_idempotent(client, db_session):
    application, raw_api_key = create_authenticated_application(db_session)

    destination = create_destination_record(
        db_session,
        application,
        "https://example.com/webhooks",
    )

    url = f"/v1/destinations/{destination.id}/subscriptions/payment.completed"

    headers = {"Authorization": f"Bearer {raw_api_key}"}

    first_response = client.delete(url, headers=headers)
    second_response = client.delete(url, headers=headers)

    assert first_response.status_code == 204
    assert second_response.status_code == 204


def test_delete_subscription_rejects_another_applications_destination(
    client,
    db_session,
):
    _, raw_api_key = create_authenticated_application(db_session)

    another_application, _ = create_authenticated_application(db_session)

    foreign_destination = create_destination_record(
        db_session,
        another_application,
        "https://foreign.example.com/webhooks",
    )

    subscription = Subscription(
        destination=foreign_destination,
        event_type="payment.completed",
    )

    db_session.add(subscription)
    db_session.flush()

    response = client.delete(
        f"/v1/destinations/{foreign_destination.id}/subscriptions/payment.completed",
        headers={"Authorization": f"Bearer {raw_api_key}"},
    )

    assert response.status_code == 404

    remaining_subscription = db_session.scalar(
        select(Subscription).where(
            Subscription.destination_id == foreign_destination.id,
            Subscription.event_type == "payment.completed",
        )
    )

    assert remaining_subscription is not None


def test_delete_subscription_requires_authentication(client, db_session):
    response = client.delete(
        f"/v1/destinations/{uuid4()}/subscriptions/payment.completed",
    )

    assert response.status_code == 401
