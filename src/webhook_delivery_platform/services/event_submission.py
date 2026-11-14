import json
from dataclasses import dataclass
from hashlib import sha256
from typing import Any
from uuid import uuid4

from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from webhook_delivery_platform.models import (
    Application,
    Delivery,
    Destination,
    Event,
    OutboxMessage,
    Subscription,
)

MAX_EVENT_TYPE_LENGTH = 255
MAX_IDEMPOTENCY_KEY_LENGTH = 255


class IdempotencyConflictError(Exception):
    """Raised when an idempotency key is reused with different content."""


@dataclass(frozen=True)
class EventSubmissionResult:
    event: Event
    delivery_count: int
    created: bool


def calculate_request_hash(
    event_type: str,
    payload: dict[str, Any],
) -> str:
    """Calculate a stable SHA-256 hash of the submitted event content."""

    try:
        canonical_request = json.dumps(
            {
                "event_type": event_type,
                "payload": payload,
            },
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
            allow_nan=False,
        )
    except (TypeError, ValueError) as exc:
        raise ValueError("Payload must contain valid JSON values.") from exc

    return sha256(canonical_request.encode("utf-8")).hexdigest()


def validate_event_submission(
    event_type: str,
    idempotency_key: str,
) -> None:
    """Validate event type and idempotency key lengths and contents."""

    if not event_type.strip():
        raise ValueError("Event type cannot be empty.")

    if len(event_type) > MAX_EVENT_TYPE_LENGTH:
        raise ValueError("Event type cannot exceed 255 characters.")

    if not idempotency_key.strip():
        raise ValueError("Idempotency key cannot be empty.")

    if len(idempotency_key) > MAX_IDEMPOTENCY_KEY_LENGTH:
        raise ValueError("Idempotency key cannot exceed 255 characters.")


def submit_event(
    session: Session,
    application: Application,
    event_type: str,
    idempotency_key: str,
    payload: dict[str, Any],
) -> EventSubmissionResult:
    """Create an event and schedule deliveries for matching destinations.

    Repeated submissions with identical content return the original event.
    Reusing an idempotency key with different content raises an exception.

    The caller is responsible for committing or rolling back the transaction.
    """

    validate_event_submission(event_type, idempotency_key)

    request_hash = calculate_request_hash(event_type, payload)

    event_id = session.execute(
        insert(Event)
        .values(
            id=uuid4(),
            application_id=application.id,
            event_type=event_type,
            idempotency_key=idempotency_key,
            request_hash=request_hash,
            payload=payload,
        )
        .on_conflict_do_nothing(
            constraint="uq_events_application_id_idempotency_key",
        )
        .returning(Event.id)
    ).scalar_one_or_none()

    if event_id is None:
        existing_event = session.scalar(
            select(Event).where(
                Event.application_id == application.id,
                Event.idempotency_key == idempotency_key,
            )
        )

        if existing_event is None:
            raise RuntimeError(
                "The existing event could not be retrieved after an "
                "idempotency conflict."
            )

        if existing_event.request_hash != request_hash:
            raise IdempotencyConflictError(
                "This idempotency key has already been used "
                "with different event content."
            )

        existing_delivery_count = session.scalar(
            select(func.count())
            .select_from(Delivery)
            .where(Delivery.event_id == existing_event.id)
        )

        return EventSubmissionResult(
            event=existing_event,
            delivery_count=existing_delivery_count or 0,
            created=False,
        )

    event = session.get(Event, event_id)

    if event is None:
        raise RuntimeError("The newly created event could not be retrieved.")

    destination_statement = (
        select(Destination.id)
        .join(
            Subscription,
            Subscription.destination_id == Destination.id,
        )
        .where(
            Destination.application_id == application.id,
            Destination.is_enabled.is_(True),
            Subscription.event_type == event_type,
        )
        .order_by(Destination.id)
    )

    destination_ids = session.scalars(destination_statement).all()

    deliveries = [
        Delivery(
            application_id=application.id,
            event_id=event.id,
            destination_id=destination_id,
        )
        for destination_id in destination_ids
    ]

    session.add_all(deliveries)
    session.flush()

    outbox_messages = [
        OutboxMessage(delivery_id=delivery.id) for delivery in deliveries
    ]

    session.add_all(outbox_messages)
    session.flush()

    return EventSubmissionResult(
        event=event,
        delivery_count=len(deliveries),
        created=True,
    )
