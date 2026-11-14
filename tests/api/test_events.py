import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select

from webhook_delivery_platform.api.dependencies import get_db_session
from webhook_delivery_platform.main import create_app
from webhook_delivery_platform.models import (
    ApiKey,
    Application,
    Delivery,
    Destination,
    Event,
    OutboxMessage,
    Subscription,
)
from webhook_delivery_platform.security.api_keys import (
    generate_api_key,
    hash_api_key,
)
from webhook_delivery_platform.security.destination_secrets import (
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


def create_authenticated_application(session, name="Event Test Application"):
    application = Application(name=name)
    raw_api_key = generate_api_key()

    api_key = ApiKey(
        application=application,
        key_hash=hash_api_key(raw_api_key),
    )

    session.add_all([application, api_key])
    session.flush()

    return application, raw_api_key


def create_destination_record(
    session,
    application,
    event_type="order.created",
    is_enabled=True,
):
    destination = Destination(
        application_id=application.id,
        url="https://example.com/webhooks",
        signing_secret_ciphertext=encrypt_signing_secret(generate_signing_secret()),
        is_enabled=is_enabled,
    )

    session.add(destination)
    session.flush()

    subscription = Subscription(
        destination_id=destination.id,
        event_type=event_type,
    )

    session.add(subscription)
    session.flush()

    return destination


def submit_event(
    client,
    raw_api_key,
    idempotency_key="event-request-001",
    event_type="order.created",
    payload=None,
):
    if payload is None:
        payload = {"order_id": "123", "amount": 49.99}

    return client.post(
        "/v1/events",
        headers={
            "Authorization": f"Bearer {raw_api_key}",
            "Idempotency-Key": idempotency_key,
        },
        json={
            "event_type": event_type,
            "payload": payload,
        },
    )


def test_submit_event_creates_event_delivery_and_outbox_message(
    client,
    db_session,
):
    application, raw_api_key = create_authenticated_application(db_session)

    destination = create_destination_record(
        db_session,
        application,
    )

    response = submit_event(client, raw_api_key)

    assert response.status_code == 202

    body = response.json()

    assert body["event_type"] == "order.created"
    assert body["delivery_count"] == 1
    assert body["created_at"] is not None

    event = db_session.scalar(select(Event).where(Event.id == body["id"]))

    assert event is not None
    assert event.application_id == application.id
    assert event.idempotency_key == "event-request-001"
    assert event.payload == {"order_id": "123", "amount": 49.99}
    assert len(event.request_hash) == 64

    delivery = db_session.scalar(
        select(Delivery).where(
            Delivery.event_id == event.id,
            Delivery.destination_id == destination.id,
        )
    )

    assert delivery is not None
    assert delivery.status == "pending"

    outbox_message = db_session.scalar(
        select(OutboxMessage).where(OutboxMessage.delivery_id == delivery.id)
    )

    assert outbox_message is not None
    assert outbox_message.status == "pending"
    assert outbox_message.retry_cycle == 1
    assert outbox_message.attempt_number == 1


def test_event_without_matching_subscriptions_is_stored(
    client,
    db_session,
):
    _, raw_api_key = create_authenticated_application(db_session)

    response = submit_event(client, raw_api_key)

    assert response.status_code == 202
    assert response.json()["delivery_count"] == 0

    event = db_session.scalar(select(Event).where(Event.id == response.json()["id"]))

    assert event is not None

    delivery_count = db_session.scalar(
        select(func.count()).select_from(Delivery).where(Delivery.event_id == event.id)
    )

    assert delivery_count == 0


def test_event_creates_deliveries_only_for_enabled_matching_destinations(
    client,
    db_session,
):
    application, raw_api_key = create_authenticated_application(db_session)

    first_destination = create_destination_record(
        db_session,
        application,
    )

    disabled_destination = create_destination_record(
        db_session,
        application,
        is_enabled=False,
    )

    unrelated_destination = create_destination_record(
        db_session,
        application,
        event_type="customer.created",
    )

    response = submit_event(client, raw_api_key)

    assert response.status_code == 202
    assert response.json()["delivery_count"] == 1

    event_id = response.json()["id"]

    deliveries = db_session.scalars(
        select(Delivery).where(Delivery.event_id == event_id)
    ).all()

    assert len(deliveries) == 1

    assert deliveries[0].destination_id == first_destination.id

    assert deliveries[0].destination_id != disabled_destination.id
    assert deliveries[0].destination_id != unrelated_destination.id


def test_identical_idempotent_request_returns_original_event(
    client,
    db_session,
):
    application, raw_api_key = create_authenticated_application(db_session)

    create_destination_record(db_session, application)

    first_response = submit_event(client, raw_api_key)

    second_response = submit_event(client, raw_api_key)

    assert first_response.status_code == 202
    assert second_response.status_code == 202

    assert first_response.json()["id"] == second_response.json()["id"]

    event_count = db_session.scalar(
        select(func.count())
        .select_from(Event)
        .where(Event.application_id == application.id)
    )

    assert event_count == 1

    delivery_count = db_session.scalar(
        select(func.count())
        .select_from(Delivery)
        .where(Delivery.event_id == first_response.json()["id"])
    )

    assert delivery_count == 1

    outbox_count = db_session.scalar(select(func.count()).select_from(OutboxMessage))

    assert outbox_count == 1


def test_same_idempotency_key_with_different_payload_returns_409(
    client,
    db_session,
):
    _, raw_api_key = create_authenticated_application(db_session)

    first_response = submit_event(client, raw_api_key)

    second_response = submit_event(
        client,
        raw_api_key,
        payload={"order_id": "456", "amount": 99.99},
    )

    assert first_response.status_code == 202
    assert second_response.status_code == 409

    event = db_session.scalar(
        select(Event).where(Event.id == first_response.json()["id"])
    )

    assert event is not None
    assert event.payload == {"order_id": "123", "amount": 49.99}


def test_same_idempotency_key_with_different_event_type_returns_409(
    client,
    db_session,
):
    _, raw_api_key = create_authenticated_application(db_session)

    first_response = submit_event(
        client,
        raw_api_key,
        event_type="order.created",
    )

    second_response = submit_event(
        client,
        raw_api_key,
        event_type="customer.created",
    )

    assert first_response.status_code == 202
    assert second_response.status_code == 409


def test_idempotency_key_is_scoped_to_application(
    client,
    db_session,
):
    first_application, first_api_key = create_authenticated_application(
        db_session,
        name="First Application",
    )

    second_application, second_api_key = create_authenticated_application(
        db_session,
        name="Second Application",
    )

    create_destination_record(db_session, first_application)
    create_destination_record(db_session, second_application)

    first_response = submit_event(
        client,
        first_api_key,
        idempotency_key="shared-request-key",
    )

    second_response = submit_event(
        client,
        second_api_key,
        idempotency_key="shared-request-key",
    )

    assert first_response.status_code == 202
    assert second_response.status_code == 202

    assert first_response.json()["id"] != second_response.json()["id"]


def test_event_rejects_missing_idempotency_key(client, db_session):
    _, raw_api_key = create_authenticated_application(db_session)

    response = client.post(
        "/v1/events",
        headers={"Authorization": f"Bearer {raw_api_key}"},
        json={
            "event_type": "order.created",
            "payload": {"order_id": "123"},
        },
    )

    assert response.status_code == 422


def test_event_rejects_blank_event_type(client, db_session):
    _, raw_api_key = create_authenticated_application(db_session)

    response = submit_event(
        client,
        raw_api_key,
        event_type="   ",
    )

    assert response.status_code == 422


def test_event_rejects_invalid_payload_type(client, db_session):
    _, raw_api_key = create_authenticated_application(db_session)

    response = client.post(
        "/v1/events",
        headers={
            "Authorization": f"Bearer {raw_api_key}",
            "Idempotency-Key": "invalid-payload",
        },
        json={
            "event_type": "order.created",
            "payload": ["invalid", "payload"],
        },
    )

    assert response.status_code == 422


def test_event_rejects_unauthenticated_request(client):
    response = client.post(
        "/v1/events",
        headers={"Idempotency-Key": "event-request-001"},
        json={
            "event_type": "order.created",
            "payload": {"order_id": "123"},
        },
    )

    assert response.status_code == 401
