from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from webhook_delivery_platform.models import Application, Destination


def list_application_destinations(
    session: Session,
    application: Application,
) -> list[Destination]:
    """Return all destinations belonging to an application."""

    statement = (
        select(Destination)
        .where(Destination.application_id == application.id)
        .order_by(
            Destination.created_at.desc(),
            Destination.id.asc(),
        )
    )

    return list(session.scalars(statement).all())


def get_application_destination(
    session: Session,
    application: Application,
    destination_id: UUID,
) -> Destination | None:
    """Return an owned destination, or None when it does not exist."""

    statement = select(Destination).where(
        Destination.id == destination_id,
        Destination.application_id == application.id,
    )

    return session.scalar(statement)
