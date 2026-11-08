from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING
from uuid import UUID, uuid4

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
    Uuid,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from webhook_delivery_platform.models.base import Base

if TYPE_CHECKING:
    from webhook_delivery_platform.models.outbox_message import OutboxMessage


class DeliveryAttempt(Base):
    __tablename__ = "delivery_attempts"

    __table_args__ = (
        UniqueConstraint(
            "outbox_message_id",
            name="uq_delivery_attempts_outbox_message_id",
        ),
        CheckConstraint(
            """
            response_status IS NULL
            OR response_status BETWEEN 100 AND 599
            """,
            name="ck_delivery_attempts_response_status",
        ),
        CheckConstraint(
            """
            error_type IS NULL
            OR length(trim(error_type)) > 0
            """,
            name="ck_delivery_attempts_error_type_not_empty",
        ),
        CheckConstraint(
            """
            (
                completed_at IS NULL
                AND response_status IS NULL
                AND error_type IS NULL
            )
            OR
            (
                completed_at IS NOT NULL
                AND
                (
                    (
                        response_status IS NOT NULL
                        AND error_type IS NULL
                    )
                    OR
                    (
                        response_status IS NULL
                        AND error_type IS NOT NULL
                    )
                )
            )
            """,
            name="ck_delivery_attempts_result_state",
        ),
        CheckConstraint(
            "completed_at IS NULL OR completed_at >= started_at",
            name="ck_delivery_attempts_completion_after_start",
        ),
    )

    id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True),
        primary_key=True,
        default=uuid4,
    )

    outbox_message_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("webhook.outbox_messages.id"),
        nullable=False,
    )

    response_status: Mapped[int | None] = mapped_column(
        Integer,
        nullable=True,
    )

    error_type: Mapped[str | None] = mapped_column(
        String(255),
        nullable=True,
    )

    error_message: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
    )

    started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )

    completed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )

    outbox_message: Mapped[OutboxMessage] = relationship(
        back_populates="delivery_attempt",
    )
