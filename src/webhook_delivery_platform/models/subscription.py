from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING
from uuid import UUID, uuid4

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    String,
    UniqueConstraint,
    Uuid,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from webhook_delivery_platform.models.base import Base

if TYPE_CHECKING:
    from webhook_delivery_platform.models.destination import Destination


class Subscription(Base):
    __tablename__ = "subscriptions"

    __table_args__ = (
        UniqueConstraint(
            "destination_id",
            "event_type",
            name="uq_subscriptions_destination_event_type",
        ),
        CheckConstraint(
            "length(trim(event_type)) > 0",
            name="ck_subscriptions_event_type_not_empty",
        ),
    )

    id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True),
        primary_key=True,
        default=uuid4,
    )

    destination_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("webhook.destinations.id"),
        nullable=False,
    )

    event_type: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )

    destination: Mapped[Destination] = relationship(
        back_populates="subscriptions",
    )
