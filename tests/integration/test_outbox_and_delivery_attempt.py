from datetime import UTC, datetime, timedelta
from hashlib import sha256
from uuid import uuid4

import pytest
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from webhook_delivery_platform.models import (
    Application,
    Delivery,
    DeliveryAttempt,
    Destination,
    Event,
    OutboxMessage,
)


def create_delivery(db_session: Session) -> Delivery:
    """Create the database records required for a Delivery."""

    application = Application(name="Outbox Integration Test")
    db_session.add(application)
    db_session.flush()

    event = Event(
        application=application,
        event_type="order.created",
        idempotency_key=str(uuid4()),
        request_hash=sha256(uuid4().bytes).hexdigest(),
        payload={"order_id": "123"},
    )

    destination = Destination(
        application=application,
        url=f"https://receiver.example/{uuid4()}",
        signing_secret_ciphertext="test-ciphertext",
    )

    db_session.add_all([event, destination])
    db_session.flush()

    delivery = Delivery(
        application_id=application.id,
        event_id=event.id,
        destination_id=destination.id,
    )

    db_session.add(delivery)
    db_session.flush()

    return delivery


def create_published_message(
    db_session: Session,
    delivery: Delivery,
    published_at: datetime | None = None,
) -> OutboxMessage:
    """Create an OutboxMessage that has been published."""

    message = OutboxMessage(
        delivery_id=delivery.id,
        status="published",
        published_at=published_at or datetime.now(UTC),
    )

    db_session.add(message)
    db_session.flush()

    return message


def test_outbox_message_belongs_to_delivery(
    db_session: Session,
) -> None:
    delivery = create_delivery(db_session)

    message = OutboxMessage(delivery=delivery)

    db_session.add(message)
    db_session.flush()

    assert message.delivery_id == delivery.id
    assert message.delivery.id == delivery.id
    assert message.retry_cycle == 1
    assert message.attempt_number == 1
    assert message.status == "pending"
    assert message.available_at is not None
    assert message.delivery_attempt is None


def test_outbox_rejects_duplicate_scheduled_attempt(
    db_session: Session,
) -> None:
    delivery = create_delivery(db_session)

    first_message = OutboxMessage(
        delivery_id=delivery.id,
        retry_cycle=1,
        attempt_number=1,
    )

    db_session.add(first_message)
    db_session.flush()

    duplicate = OutboxMessage(
        delivery_id=delivery.id,
        retry_cycle=1,
        attempt_number=1,
    )

    db_session.add(duplicate)

    with pytest.raises(IntegrityError):
        db_session.flush()


def test_outbox_allows_distinct_retry_attempts(
    db_session: Session,
) -> None:
    delivery = create_delivery(db_session)

    messages = [
        OutboxMessage(
            delivery_id=delivery.id,
            retry_cycle=1,
            attempt_number=1,
        ),
        OutboxMessage(
            delivery_id=delivery.id,
            retry_cycle=1,
            attempt_number=2,
        ),
        OutboxMessage(
            delivery_id=delivery.id,
            retry_cycle=2,
            attempt_number=1,
        ),
    ]

    db_session.add_all(messages)
    db_session.flush()

    assert len({message.id for message in messages}) == 3


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("retry_cycle", 0),
        ("attempt_number", 0),
    ],
)
def test_outbox_rejects_non_positive_numbers(
    db_session: Session,
    field: str,
    value: int,
) -> None:
    delivery = create_delivery(db_session)

    message = OutboxMessage(
        delivery_id=delivery.id,
        **{field: value},
    )

    db_session.add(message)

    with pytest.raises(IntegrityError):
        db_session.flush()


def test_outbox_rejects_unknown_status(
    db_session: Session,
) -> None:
    delivery = create_delivery(db_session)

    message = OutboxMessage(
        delivery_id=delivery.id,
        status="unknown",
    )

    db_session.add(message)

    with pytest.raises(IntegrityError):
        db_session.flush()


@pytest.mark.parametrize(
    ("status", "published_at", "processed_at"),
    [
        ("published", None, None),
        ("pending", datetime.now(UTC), None),
        ("pending", None, datetime.now(UTC)),
        ("completed", datetime.now(UTC), None),
        ("completed", None, datetime.now(UTC)),
    ],
)
def test_outbox_rejects_inconsistent_status_timestamps(
    db_session: Session,
    status: str,
    published_at: datetime | None,
    processed_at: datetime | None,
) -> None:
    delivery = create_delivery(db_session)

    message = OutboxMessage(
        delivery_id=delivery.id,
        status=status,
        published_at=published_at,
        processed_at=processed_at,
    )

    db_session.add(message)

    with pytest.raises(IntegrityError):
        db_session.flush()


def test_outbox_accepts_completed_status(
    db_session: Session,
) -> None:
    delivery = create_delivery(db_session)
    published_at = datetime.now(UTC)

    message = OutboxMessage(
        delivery_id=delivery.id,
        status="completed",
        published_at=published_at,
        processed_at=published_at + timedelta(seconds=2),
    )

    db_session.add(message)
    db_session.flush()

    assert message.status == "completed"
    assert message.published_at == published_at
    assert message.processed_at is not None


def test_delivery_attempt_belongs_to_outbox_message(
    db_session: Session,
) -> None:
    delivery = create_delivery(db_session)
    message = create_published_message(db_session, delivery)

    attempt = DeliveryAttempt(
        outbox_message=message,
    )

    db_session.add(attempt)
    db_session.flush()

    assert attempt.outbox_message_id == message.id
    assert attempt.outbox_message.id == message.id
    assert message.delivery_attempt.id == attempt.id

    assert attempt.started_at is not None
    assert attempt.completed_at is None


def test_delivery_attempt_accepts_http_response(
    db_session: Session,
) -> None:
    delivery = create_delivery(db_session)
    started_at = datetime.now(UTC)

    message = create_published_message(
        db_session,
        delivery,
        published_at=started_at - timedelta(seconds=1),
    )

    attempt = DeliveryAttempt(
        outbox_message=message,
        response_status=204,
        started_at=started_at,
        completed_at=started_at + timedelta(seconds=1),
    )

    db_session.add(attempt)
    db_session.flush()

    assert attempt.response_status == 204
    assert attempt.error_type is None
    assert attempt.completed_at > attempt.started_at


def test_delivery_attempt_accepts_network_error(
    db_session: Session,
) -> None:
    delivery = create_delivery(db_session)
    started_at = datetime.now(UTC)

    message = create_published_message(
        db_session,
        delivery,
        published_at=started_at - timedelta(seconds=1),
    )

    attempt = DeliveryAttempt(
        outbox_message=message,
        error_type="ConnectTimeout",
        error_message="Connection timed out",
        started_at=started_at,
        completed_at=started_at + timedelta(seconds=5),
    )

    db_session.add(attempt)
    db_session.flush()

    assert attempt.response_status is None
    assert attempt.error_type == "ConnectTimeout"
    assert attempt.error_message == "Connection timed out"


def test_outbox_message_cannot_have_multiple_attempts(
    db_session: Session,
) -> None:
    delivery = create_delivery(db_session)
    message = create_published_message(db_session, delivery)

    first_attempt = DeliveryAttempt(
        outbox_message=message,
    )

    db_session.add(first_attempt)
    db_session.flush()

    duplicate_attempt = DeliveryAttempt(
        outbox_message_id=message.id,
    )

    db_session.add(duplicate_attempt)

    with pytest.raises(IntegrityError):
        db_session.flush()


def test_delivery_attempt_rejects_nonexistent_outbox_message(
    db_session: Session,
) -> None:
    attempt = DeliveryAttempt(
        outbox_message_id=uuid4(),
    )

    db_session.add(attempt)

    with pytest.raises(IntegrityError):
        db_session.flush()


@pytest.mark.parametrize("response_status", [99, 600])
def test_delivery_attempt_rejects_invalid_http_status(
    db_session: Session,
    response_status: int,
) -> None:
    delivery = create_delivery(db_session)
    started_at = datetime.now(UTC)
    message = create_published_message(db_session, delivery)

    attempt = DeliveryAttempt(
        outbox_message=message,
        response_status=response_status,
        started_at=started_at,
        completed_at=started_at + timedelta(seconds=1),
    )

    db_session.add(attempt)

    with pytest.raises(IntegrityError):
        db_session.flush()


def test_delivery_attempt_rejects_blank_error_type(
    db_session: Session,
) -> None:
    delivery = create_delivery(db_session)
    started_at = datetime.now(UTC)
    message = create_published_message(db_session, delivery)

    attempt = DeliveryAttempt(
        outbox_message=message,
        error_type="   ",
        started_at=started_at,
        completed_at=started_at + timedelta(seconds=1),
    )

    db_session.add(attempt)

    with pytest.raises(IntegrityError):
        db_session.flush()


@pytest.mark.parametrize(
    ("response_status", "error_type"),
    [
        (None, None),
        (204, "ConnectTimeout"),
    ],
)
def test_completed_attempt_requires_exactly_one_result(
    db_session: Session,
    response_status: int | None,
    error_type: str | None,
) -> None:
    delivery = create_delivery(db_session)
    started_at = datetime.now(UTC)
    message = create_published_message(db_session, delivery)

    attempt = DeliveryAttempt(
        outbox_message=message,
        response_status=response_status,
        error_type=error_type,
        started_at=started_at,
        completed_at=started_at + timedelta(seconds=1),
    )

    db_session.add(attempt)

    with pytest.raises(IntegrityError):
        db_session.flush()


def test_delivery_attempt_rejects_completion_before_start(
    db_session: Session,
) -> None:
    delivery = create_delivery(db_session)
    started_at = datetime.now(UTC)
    message = create_published_message(db_session, delivery)

    attempt = DeliveryAttempt(
        outbox_message=message,
        response_status=204,
        started_at=started_at,
        completed_at=started_at - timedelta(seconds=1),
    )

    db_session.add(attempt)

    with pytest.raises(IntegrityError):
        db_session.flush()
