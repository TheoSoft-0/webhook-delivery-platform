from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING
from uuid import UUID, uuid4

from sqlalchemy import DateTime, ForeignKey, String, Uuid, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from webhook_delivery_platform.models.base import Base

if TYPE_CHECKING:
    from webhook_delivery_platform.models.application import Application


class ApiKey(Base):
    __tablename__ = "api_keys"

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

    key_hash: Mapped[str] = mapped_column(
        String(64),
        nullable=False,
        unique=True,
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )

    revoked_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )

    application: Mapped[Application] = relationship(
        back_populates="api_keys",
    )
