from uuid import UUID, uuid4

from sqlalchemy import delete, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from webhook_delivery_platform.models import Application, Destination, Subscription

MAX_EVENT_TYPE_LENGTH = 255


def validate_event_type(event_type: str) -> None:
    """Validate an event type against the database constraints."""

    if not event_type.strip():
        raise ValueError("Event type cannot be empty.")

    if len(event_type) > MAX_EVENT_TYPE_LENGTH:
        raise ValueError("Event type cannot exceed 255 characters.")


def add_destination_subscription(
    session: Session,
    application: Application,
    destination_id: UUID,
    event_type: str,
) -> bool:
    """Subscribe an application-owned destination to an event type."""

    validate_event_type(event_type)

    destination_statement = select(Destination.id).where(
        Destination.id == destination_id,
        Destination.application_id == application.id,
    )

    owned_destination_id = session.scalar(destination_statement)

    if owned_destination_id is None:
        return False

    statement = (
        insert(Subscription)
        .values(
            id=uuid4(),
            destination_id=destination_id,
            event_type=event_type,
        )
        .on_conflict_do_nothing(constraint="uq_subscriptions_destination_event_type")
    )

    session.execute(statement)

    return True


def remove_destination_subscription(
    session: Session,
    application: Application,
    destination_id: UUID,
    event_type: str,
) -> bool:
    """Remove a subscription from an application-owned destination."""

    validate_event_type(event_type)

    destination_statement = select(Destination.id).where(
        Destination.id == destination_id,
        Destination.application_id == application.id,
    )

    owned_destination_id = session.scalar(destination_statement)

    if owned_destination_id is None:
        return False

    statement = delete(Subscription).where(
        Subscription.destination_id == destination_id,
        Subscription.event_type == event_type,
    )

    session.execute(statement)

    return True
