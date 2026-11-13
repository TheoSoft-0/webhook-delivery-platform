from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from webhook_delivery_platform.models import Application, Destination


def update_destination_enabled(
    session: Session,
    application: Application,
    destination_id: UUID,
    is_enabled: bool,
) -> Destination | None:
    """Update the enabled state of an application-owned destination."""

    statement = select(Destination).where(
        Destination.id == destination_id,
        Destination.application_id == application.id,
    )

    destination = session.scalar(statement)

    if destination is None:
        return None

    destination.is_enabled = is_enabled

    session.flush()

    return destination
