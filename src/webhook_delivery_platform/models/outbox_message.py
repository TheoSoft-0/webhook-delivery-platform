from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING
from uuid import UUID, uuid4

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    Uuid,
    func,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from webhook_delivery_platform.models.base import Base

if TYPE_CHECKING:
    from webhook_delivery_platform.models.delivery import Delivery
    from webhook_delivery_platform.models.delivery_attempt import DeliveryAttempt


class OutboxMessage(Base):
    __tablename__ = "outbox_messages"

    __table_args__ = (
        UniqueConstraint(
            "delivery_id",
            "retry_cycle",
            "attempt_number",
            name="uq_outbox_messages_delivery_cycle_attempt",
        ),
        CheckConstraint(
            "retry_cycle >= 1",
            name="ck_outbox_messages_retry_cycle_positive",
        ),
        CheckConstraint(
            "attempt_number >= 1",
            name="ck_outbox_messages_attempt_number_positive",
        ),
        CheckConstraint(
            "status IN ('pending', 'published', 'completed')",
            name="ck_outbox_messages_status",
        ),
        CheckConstraint(
            """
            (
                status = 'pending'
                AND published_at IS NULL
                AND processed_at IS NULL
            )
            OR
            (
                status = 'published'
                AND published_at IS NOT NULL
                AND processed_at IS NULL
            )
            OR
            (
                status = 'completed'
                AND published_at IS NOT NULL
                AND processed_at IS NOT NULL
            )
            """,
            name="ck_outbox_messages_status_timestamps",
        ),
        Index(
            "ix_outbox_messages_status_available_at",
            "status",
            "available_at",
        ),
    )

    id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True),
        primary_key=True,
        default=uuid4,
    )

    delivery_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("webhook.deliveries.id"),
        nullable=False,
    )

    retry_cycle: Mapped[int] = mapped_column(
        Integer,
        default=1,
        server_default=text("1"),
        nullable=False,
    )

    attempt_number: Mapped[int] = mapped_column(
        Integer,
        default=1,
        server_default=text("1"),
        nullable=False,
    )

    status: Mapped[str] = mapped_column(
        String(16),
        default="pending",
        server_default=text("'pending'"),
        nullable=False,
    )

    available_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )

    published_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )

    processed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )

    last_error: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )

    delivery: Mapped[Delivery] = relationship(
        back_populates="outbox_messages",
    )

    delivery_attempt: Mapped[DeliveryAttempt | None] = relationship(
        back_populates="outbox_message",
        uselist=False,
    )
