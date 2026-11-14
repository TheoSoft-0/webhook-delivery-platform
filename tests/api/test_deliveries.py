from datetime import UTC, datetime, timedelta
from hashlib import sha256
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from webhook_delivery_platform.api.dependencies import get_db_session
from webhook_delivery_platform.main import create_app
from webhook_delivery_platform.models import (
    ApiKey,
    Application,
    Delivery,
    DeliveryAttempt,
    Destination,
    Event,
    OutboxMessage,
)
from webhook_delivery_platform.security.api_keys import (
    generate_api_key,
    hash_api_key,
)


@pytest.fixture
def client(db_session):
    app = create_app()

    app.dependency_overrides[get_db_session] = lambda: db_session

    with TestClient(app) as test_client:
        yield test_client

    app.dependency_overrides.clear()


def create_authenticated_application(
    session,
    name="Delivery Test Application",
):
    application = Application(name=name)
    raw_api_key = generate_api_key()

    api_key = ApiKey(
        application=application,
        key_hash=hash_api_key(raw_api_key),
    )

    session.add_all([application, api_key])
    session.flush()

    return application, raw_api_key


def create_delivery_records(session, application):
    event = Event(
        application=application,
        event_type="order.created",
        idempotency_key=str(uuid4()),
        request_hash=sha256(uuid4().bytes).hexdigest(),
        payload={"order_id": "123"},
    )

    destination = Destination(
        application=application,
        url="https://example.com/webhooks",
        signing_secret_ciphertext="test-ciphertext",
    )

    session.add_all([event, destination])
    session.flush()

    delivery = Delivery(
        application_id=application.id,
        event_id=event.id,
        destination_id=destination.id,
    )

    session.add(delivery)
    session.flush()

    outbox_message = OutboxMessage(
        delivery_id=delivery.id,
    )

    session.add(outbox_message)
    session.flush()

    return delivery, outbox_message


def test_get_delivery_returns_owned_delivery(client, db_session):
    application, raw_api_key = create_authenticated_application(db_session)

    delivery, _ = create_delivery_records(db_session, application)

    response = client.get(
        f"/v1/deliveries/{delivery.id}",
        headers={"Authorization": f"Bearer {raw_api_key}"},
    )

    assert response.status_code == 200

    body = response.json()

    assert body["id"] == str(delivery.id)
    assert body["event_id"] == str(delivery.event_id)
    assert body["destination_id"] == str(delivery.destination_id)
    assert body["status"] == "pending"
    assert body["retry_cycle"] == 1
    assert body["created_at"] is not None


def test_get_delivery_returns_404_for_unknown_delivery(client, db_session):
    _, raw_api_key = create_authenticated_application(db_session)

    response = client.get(
        f"/v1/deliveries/{uuid4()}",
        headers={"Authorization": f"Bearer {raw_api_key}"},
    )

    assert response.status_code == 404
    assert response.json()["detail"] == "Delivery not found"


def test_get_delivery_rejects_another_applications_delivery(
    client,
    db_session,
):
    first_application, _ = create_authenticated_application(
        db_session,
        name="First Application",
    )

    _second_application, second_api_key = create_authenticated_application(
        db_session,
        name="Second Application",
    )

    delivery, _ = create_delivery_records(
        db_session,
        first_application,
    )

    response = client.get(
        f"/v1/deliveries/{delivery.id}",
        headers={"Authorization": f"Bearer {second_api_key}"},
    )

    assert response.status_code == 404


def test_get_delivery_requires_authentication(client):
    response = client.get(f"/v1/deliveries/{uuid4()}")

    assert response.status_code == 401


def test_list_delivery_attempts_returns_owned_attempts(
    client,
    db_session,
):
    application, raw_api_key = create_authenticated_application(db_session)

    delivery, outbox_message = create_delivery_records(
        db_session,
        application,
    )

    started_at = datetime.now(UTC)

    attempt = DeliveryAttempt(
        outbox_message=outbox_message,
        response_status=204,
        started_at=started_at,
        completed_at=started_at + timedelta(seconds=1),
    )

    db_session.add(attempt)
    db_session.flush()

    response = client.get(
        f"/v1/deliveries/{delivery.id}/attempts",
        headers={"Authorization": f"Bearer {raw_api_key}"},
    )

    assert response.status_code == 200

    body = response.json()

    assert len(body) == 1
    assert body[0]["id"] == str(attempt.id)
    assert body[0]["outbox_message_id"] == str(outbox_message.id)
    assert body[0]["response_status"] == 204
    assert body[0]["error_type"] is None
    assert body[0]["error_message"] is None
    assert body[0]["started_at"] is not None
    assert body[0]["completed_at"] is not None


def test_list_delivery_attempts_returns_empty_list_when_none_exist(
    client,
    db_session,
):
    application, raw_api_key = create_authenticated_application(db_session)

    delivery, _ = create_delivery_records(
        db_session,
        application,
    )

    response = client.get(
        f"/v1/deliveries/{delivery.id}/attempts",
        headers={"Authorization": f"Bearer {raw_api_key}"},
    )

    assert response.status_code == 200
    assert response.json() == []


def test_list_delivery_attempts_returns_404_for_unknown_delivery(
    client,
    db_session,
):
    _, raw_api_key = create_authenticated_application(db_session)

    response = client.get(
        f"/v1/deliveries/{uuid4()}/attempts",
        headers={"Authorization": f"Bearer {raw_api_key}"},
    )

    assert response.status_code == 404


def test_list_delivery_attempts_rejects_another_applications_delivery(
    client,
    db_session,
):
    first_application, _ = create_authenticated_application(
        db_session,
        name="First Application",
    )

    _, second_api_key = create_authenticated_application(
        db_session,
        name="Second Application",
    )

    delivery, _ = create_delivery_records(
        db_session,
        first_application,
    )

    response = client.get(
        f"/v1/deliveries/{delivery.id}/attempts",
        headers={"Authorization": f"Bearer {second_api_key}"},
    )

    assert response.status_code == 404


def test_list_delivery_attempts_requires_authentication(client):
    response = client.get(
        f"/v1/deliveries/{uuid4()}/attempts",
    )

    assert response.status_code == 401
