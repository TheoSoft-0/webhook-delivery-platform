from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING
from uuid import UUID, uuid4

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKeyConstraint,
    Integer,
    String,
    UniqueConstraint,
    Uuid,
    func,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from webhook_delivery_platform.models.base import Base

if TYPE_CHECKING:
    from webhook_delivery_platform.models.destination import Destination
    from webhook_delivery_platform.models.event import Event


class Delivery(Base):
    __tablename__ = "deliveries"

    __table_args__ = (
        ForeignKeyConstraint(
            ["event_id", "application_id"],
            ["webhook.events.id", "webhook.events.application_id"],
            name="fk_deliveries_event_application",
        ),
        ForeignKeyConstraint(
            ["destination_id", "application_id"],
            [
                "webhook.destinations.id",
                "webhook.destinations.application_id",
            ],
            name="fk_deliveries_destination_application",
        ),
        UniqueConstraint(
            "event_id",
            "destination_id",
            name="uq_deliveries_event_destination",
        ),
        CheckConstraint(
            "status IN ('pending', 'scheduled', 'processing', "
            "'succeeded', 'permanently_failed')",
            name="ck_deliveries_status",
        ),
        CheckConstraint(
            "retry_cycle >= 1",
            name="ck_deliveries_retry_cycle_positive",
        ),
    )

    id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True),
        primary_key=True,
        default=uuid4,
    )

    application_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True),
        nullable=False,
        index=True,
    )

    event_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True),
        nullable=False,
    )

    destination_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True),
        nullable=False,
    )

    status: Mapped[str] = mapped_column(
        String(32),
        default="pending",
        server_default=text("'pending'"),
        nullable=False,
    )

    retry_cycle: Mapped[int] = mapped_column(
        Integer,
        default=1,
        server_default=text("1"),
        nullable=False,
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )

    event: Mapped[Event] = relationship(
        back_populates="deliveries",
        foreign_keys=[event_id],
    )

    destination: Mapped[Destination] = relationship(
        back_populates="deliveries",
        foreign_keys=[destination_id],
    )
