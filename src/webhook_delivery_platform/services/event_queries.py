from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from webhook_delivery_platform.models import (
    Application,
    Delivery,
    Event,
)


def get_application_event(
    session: Session,
    application: Application,
    event_id: UUID,
) -> Event | None:
    """Retrieve an event belonging to an application."""

    statement = select(Event).where(
        Event.id == event_id,
        Event.application_id == application.id,
    )

    return session.scalar(statement)


def list_application_event_deliveries(
    session: Session,
    application: Application,
    event_id: UUID,
) -> list[Delivery] | None:
    """Retrieve deliveries for an application-owned event."""

    event_statement = select(Event.id).where(
        Event.id == event_id,
        Event.application_id == application.id,
    )

    owned_event_id = session.scalar(event_statement)

    if owned_event_id is None:
        return None

    delivery_statement = (
        select(Delivery)
        .where(
            Delivery.event_id == event_id,
            Delivery.application_id == application.id,
        )
        .order_by(
            Delivery.created_at.asc(),
            Delivery.id.asc(),
        )
    )

    return list(session.scalars(delivery_statement).all())
