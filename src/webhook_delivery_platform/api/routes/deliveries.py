from datetime import datetime
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, ConfigDict
from sqlalchemy.orm import Session

from webhook_delivery_platform.api.authentication import (
    get_current_application,
)
from webhook_delivery_platform.api.dependencies import get_db_session
from webhook_delivery_platform.models import Application
from webhook_delivery_platform.services.delivery_queries import (
    get_application_delivery,
    list_application_delivery_attempts,
)

router = APIRouter(
    prefix="/v1/deliveries",
    tags=["Deliveries"],
)


class DeliveryInspectionResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    event_id: UUID
    destination_id: UUID
    status: str
    retry_cycle: int
    created_at: datetime


class DeliveryAttemptResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    outbox_message_id: UUID
    response_status: int | None
    error_type: str | None
    error_message: str | None
    started_at: datetime
    completed_at: datetime | None


@router.get(
    "/{delivery_id}",
    response_model=DeliveryInspectionResponse,
)
def get_delivery(
    delivery_id: UUID,
    application: Annotated[
        Application,
        Depends(get_current_application),
    ],
    session: Annotated[
        Session,
        Depends(get_db_session),
    ],
) -> DeliveryInspectionResponse:
    """Retrieve a delivery belonging to the authenticated application."""

    delivery = get_application_delivery(
        session=session,
        application=application,
        delivery_id=delivery_id,
    )

    if delivery is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Delivery not found",
        )

    return DeliveryInspectionResponse.model_validate(delivery)


@router.get(
    "/{delivery_id}/attempts",
    response_model=list[DeliveryAttemptResponse],
)
def list_delivery_attempts(
    delivery_id: UUID,
    application: Annotated[
        Application,
        Depends(get_current_application),
    ],
    session: Annotated[
        Session,
        Depends(get_db_session),
    ],
) -> list[DeliveryAttemptResponse]:
    """List attempts belonging to an application-owned delivery."""

    attempts = list_application_delivery_attempts(
        session=session,
        application=application,
        delivery_id=delivery_id,
    )

    if attempts is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Delivery not found",
        )

    return [DeliveryAttemptResponse.model_validate(attempt) for attempt in attempts]
