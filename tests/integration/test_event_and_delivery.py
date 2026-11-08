from hashlib import sha256
from uuid import uuid4

import pytest
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from webhook_delivery_platform.models import (
    Application,
    Delivery,
    Destination,
    Event,
)


def generate_request_hash() -> str:
    """Generate a valid SHA-256 hexadecimal digest for testing."""

    return sha256(uuid4().bytes).hexdigest()


def create_application(
    db_session: Session,
    name: str = "Integration Test Application",
) -> Application:
    application = Application(name=name)
    db_session.add(application)
    db_session.flush()
    return application


def create_event(
    db_session: Session,
    application: Application,
    idempotency_key: str | None = None,
) -> Event:
    event = Event(
        application=application,
        event_type="order.created",
        idempotency_key=idempotency_key or str(uuid4()),
        request_hash=generate_request_hash(),
        payload={"order_id": "123", "amount": 49.99},
    )
    db_session.add(event)
    db_session.flush()
    return event


def create_destination(
    db_session: Session,
    application: Application,
) -> Destination:
    destination = Destination(
        application=application,
        url=f"https://receiver.example/{uuid4()}",
        signing_secret_ciphertext="test-ciphertext",
    )
    db_session.add(destination)
    db_session.flush()
    return destination


def create_delivery(
    db_session: Session,
    application: Application,
    event: Event,
    destination: Destination,
) -> Delivery:
    delivery = Delivery(
        application_id=application.id,
        event_id=event.id,
        destination_id=destination.id,
    )
    db_session.add(delivery)
    db_session.flush()
    return delivery


def test_event_belongs_to_application(
    db_session: Session,
) -> None:
    application = create_application(db_session)

    event = create_event(db_session, application)

    assert event.application_id == application.id
    assert event.application.id == application.id
    assert event.event_type == "order.created"
    assert event.payload == {"order_id": "123", "amount": 49.99}


def test_duplicate_idempotency_key_is_rejected_within_application(
    db_session: Session,
) -> None:
    application = create_application(db_session)
    idempotency_key = "request-123"

    create_event(db_session, application, idempotency_key)

    duplicate = Event(
        application_id=application.id,
        event_type="order.created",
        idempotency_key=idempotency_key,
        request_hash=generate_request_hash(),
        payload={"order_id": "456"},
    )

    db_session.add(duplicate)

    with pytest.raises(IntegrityError):
        db_session.flush()


def test_same_idempotency_key_is_allowed_for_different_applications(
    db_session: Session,
) -> None:
    first_application = create_application(db_session, "First Application")
    second_application = create_application(db_session, "Second Application")

    idempotency_key = "request-123"

    first_event = create_event(
        db_session,
        first_application,
        idempotency_key,
    )

    second_event = create_event(
        db_session,
        second_application,
        idempotency_key,
    )

    assert first_event.id != second_event.id
    assert first_event.application_id != second_event.application_id
    assert first_event.idempotency_key == second_event.idempotency_key


def test_event_rejects_blank_event_type(
    db_session: Session,
) -> None:
    application = create_application(db_session)

    event = Event(
        application_id=application.id,
        event_type="   ",
        idempotency_key="request-123",
        request_hash=generate_request_hash(),
        payload={"order_id": "123"},
    )

    db_session.add(event)

    with pytest.raises(IntegrityError):
        db_session.flush()


def test_event_rejects_blank_idempotency_key(
    db_session: Session,
) -> None:
    application = create_application(db_session)

    event = Event(
        application_id=application.id,
        event_type="order.created",
        idempotency_key="   ",
        request_hash=generate_request_hash(),
        payload={"order_id": "123"},
    )

    db_session.add(event)

    with pytest.raises(IntegrityError):
        db_session.flush()


def test_event_rejects_invalid_request_hash_length(
    db_session: Session,
) -> None:
    application = create_application(db_session)

    event = Event(
        application_id=application.id,
        event_type="order.created",
        idempotency_key="request-123",
        request_hash="too-short",
        payload={"order_id": "123"},
    )

    db_session.add(event)

    with pytest.raises(IntegrityError):
        db_session.flush()


def test_delivery_belongs_to_event_and_destination(
    db_session: Session,
) -> None:
    application = create_application(db_session)
    event = create_event(db_session, application)
    destination = create_destination(db_session, application)

    delivery = create_delivery(
        db_session,
        application,
        event,
        destination,
    )

    assert delivery.application_id == application.id
    assert delivery.event.id == event.id
    assert delivery.destination.id == destination.id
    assert delivery.status == "pending"
    assert delivery.retry_cycle == 1


def test_delivery_rejects_event_from_another_application(
    db_session: Session,
) -> None:
    first_application = create_application(db_session, "First Application")
    second_application = create_application(db_session, "Second Application")

    event = create_event(db_session, second_application)
    destination = create_destination(db_session, first_application)

    delivery = Delivery(
        application_id=first_application.id,
        event_id=event.id,
        destination_id=destination.id,
    )

    db_session.add(delivery)

    with pytest.raises(IntegrityError):
        db_session.flush()


def test_delivery_rejects_destination_from_another_application(
    db_session: Session,
) -> None:
    first_application = create_application(db_session, "First Application")
    second_application = create_application(db_session, "Second Application")

    event = create_event(db_session, first_application)
    destination = create_destination(db_session, second_application)

    delivery = Delivery(
        application_id=first_application.id,
        event_id=event.id,
        destination_id=destination.id,
    )

    db_session.add(delivery)

    with pytest.raises(IntegrityError):
        db_session.flush()


def test_duplicate_delivery_for_same_event_and_destination_is_rejected(
    db_session: Session,
) -> None:
    application = create_application(db_session)
    event = create_event(db_session, application)
    destination = create_destination(db_session, application)

    create_delivery(db_session, application, event, destination)

    duplicate = Delivery(
        application_id=application.id,
        event_id=event.id,
        destination_id=destination.id,
    )

    db_session.add(duplicate)

    with pytest.raises(IntegrityError):
        db_session.flush()


def test_delivery_rejects_invalid_status(
    db_session: Session,
) -> None:
    application = create_application(db_session)
    event = create_event(db_session, application)
    destination = create_destination(db_session, application)

    delivery = Delivery(
        application_id=application.id,
        event_id=event.id,
        destination_id=destination.id,
        status="unknown",
    )

    db_session.add(delivery)

    with pytest.raises(IntegrityError):
        db_session.flush()


def test_delivery_rejects_non_positive_retry_cycle(
    db_session: Session,
) -> None:
    application = create_application(db_session)
    event = create_event(db_session, application)
    destination = create_destination(db_session, application)

    delivery = Delivery(
        application_id=application.id,
        event_id=event.id,
        destination_id=destination.id,
        retry_cycle=0,
    )

    db_session.add(delivery)

    with pytest.raises(IntegrityError):
        db_session.flush()


def test_event_can_have_multiple_distinct_destinations(
    db_session: Session,
) -> None:
    application = create_application(db_session)
    event = create_event(db_session, application)

    first_destination = create_destination(db_session, application)
    second_destination = create_destination(db_session, application)

    first_delivery = create_delivery(
        db_session,
        application,
        event,
        first_destination,
    )

    second_delivery = create_delivery(
        db_session,
        application,
        event,
        second_destination,
    )

    assert first_delivery.event_id == second_delivery.event_id
    assert first_delivery.destination_id != second_delivery.destination_id
