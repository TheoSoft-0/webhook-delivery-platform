from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING, Any
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
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from webhook_delivery_platform.models.base import Base

if TYPE_CHECKING:
    from webhook_delivery_platform.models.application import Application
    from webhook_delivery_platform.models.delivery import Delivery


class Event(Base):
    __tablename__ = "events"

    __table_args__ = (
        UniqueConstraint(
            "id",
            "application_id",
            name="uq_events_id_application_id",
        ),
        UniqueConstraint(
            "application_id",
            "idempotency_key",
            name="uq_events_application_id_idempotency_key",
        ),
        CheckConstraint(
            "length(trim(event_type)) > 0",
            name="ck_events_event_type_not_empty",
        ),
        CheckConstraint(
            "length(trim(idempotency_key)) > 0",
            name="ck_events_idempotency_key_not_empty",
        ),
        CheckConstraint(
            "length(request_hash) = 64",
            name="ck_events_request_hash_length",
        ),
    )

    id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True),
        primary_key=True,
        default=uuid4,
    )

    application_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("webhook.applications.id"),
        nullable=False,
        index=True,
    )

    event_type: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
    )

    idempotency_key: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
    )

    request_hash: Mapped[str] = mapped_column(
        String(64),
        nullable=False,
    )

    payload: Mapped[dict[str, Any]] = mapped_column(
        JSONB,
        nullable=False,
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )

    application: Mapped[Application] = relationship(
        back_populates="events",
    )

    deliveries: Mapped[list[Delivery]] = relationship(
        back_populates="event",
        foreign_keys="Delivery.event_id",
    )
