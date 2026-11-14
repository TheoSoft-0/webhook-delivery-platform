from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from webhook_delivery_platform.models import (
    Application,
    Delivery,
    DeliveryAttempt,
    OutboxMessage,
)


def get_application_delivery(
    session: Session,
    application: Application,
    delivery_id: UUID,
) -> Delivery | None:
    """Retrieve a delivery belonging to an application."""

    statement = select(Delivery).where(
        Delivery.id == delivery_id,
        Delivery.application_id == application.id,
    )

    return session.scalar(statement)


def list_application_delivery_attempts(
    session: Session,
    application: Application,
    delivery_id: UUID,
) -> list[DeliveryAttempt] | None:
    """Retrieve attempts belonging to an application-owned delivery."""

    delivery_statement = select(Delivery.id).where(
        Delivery.id == delivery_id,
        Delivery.application_id == application.id,
    )

    owned_delivery_id = session.scalar(delivery_statement)

    if owned_delivery_id is None:
        return None

    attempts_statement = (
        select(DeliveryAttempt)
        .join(
            OutboxMessage,
            OutboxMessage.id == DeliveryAttempt.outbox_message_id,
        )
        .where(
            OutboxMessage.delivery_id == delivery_id,
        )
        .order_by(
            DeliveryAttempt.started_at.asc(),
            DeliveryAttempt.id.asc(),
        )
    )

    return list(session.scalars(attempts_statement).all())
