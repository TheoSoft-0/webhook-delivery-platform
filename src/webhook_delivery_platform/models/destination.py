from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING
from uuid import UUID, uuid4

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Text,
    UniqueConstraint,
    Uuid,
    func,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from webhook_delivery_platform.models.base import Base

if TYPE_CHECKING:
    from webhook_delivery_platform.models.application import Application
    from webhook_delivery_platform.models.subscription import Subscription


class Destination(Base):
    __tablename__ = "destinations"

    __table_args__ = (
        CheckConstraint(
            "length(trim(url)) > 0",
            name="ck_destinations_url_not_empty",
        ),
        UniqueConstraint(
            "id",
            "application_id",
            name="uq_destinations_id_application_id",
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

    url: Mapped[str] = mapped_column(
        Text,
        nullable=False,
    )

    signing_secret_ciphertext: Mapped[str] = mapped_column(
        Text,
        nullable=False,
    )

    is_enabled: Mapped[bool] = mapped_column(
        Boolean,
        default=True,
        server_default=text("true"),
        nullable=False,
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )

    application: Mapped[Application] = relationship(
        back_populates="destinations",
    )

    subscriptions: Mapped[list[Subscription]] = relationship(
        back_populates="destination",
    )
