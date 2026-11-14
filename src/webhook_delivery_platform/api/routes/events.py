from datetime import datetime
from typing import Annotated, Any
from uuid import UUID

from fastapi import APIRouter, Depends, Header, HTTPException, status
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.orm import Session

from webhook_delivery_platform.api.authentication import (
    get_current_application,
)
from webhook_delivery_platform.api.dependencies import get_db_session
from webhook_delivery_platform.models import Application
from webhook_delivery_platform.services.event_queries import (
    get_application_event,
    list_application_event_deliveries,
)
from webhook_delivery_platform.services.event_submission import (
    IdempotencyConflictError,
    submit_event,
)

router = APIRouter(
    prefix="/v1/events",
    tags=["Events"],
)


class EventCreateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    event_type: str = Field(min_length=1, max_length=255)
    payload: dict[str, Any]


class EventCreateResponse(BaseModel):
    id: UUID
    event_type: str
    created_at: datetime
    delivery_count: int


class EventInspectionResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    event_type: str
    payload: dict[str, Any]
    created_at: datetime


class EventDeliveryResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    destination_id: UUID
    status: str
    retry_cycle: int
    created_at: datetime


@router.post(
    "",
    response_model=EventCreateResponse,
    status_code=status.HTTP_202_ACCEPTED,
)
def create_event(
    request: EventCreateRequest,
    idempotency_key: Annotated[
        str,
        Header(
            alias="Idempotency-Key",
            min_length=1,
            max_length=255,
        ),
    ],
    application: Annotated[
        Application,
        Depends(get_current_application),
    ],
    session: Annotated[
        Session,
        Depends(get_db_session),
    ],
) -> EventCreateResponse:
    """Submit an event for asynchronous webhook delivery."""

    try:
        result = submit_event(
            session=session,
            application=application,
            event_type=request.event_type,
            idempotency_key=idempotency_key,
            payload=request.payload,
        )

        response = EventCreateResponse(
            id=result.event.id,
            event_type=result.event.event_type,
            created_at=result.event.created_at,
            delivery_count=result.delivery_count,
        )

        session.commit()

    except IdempotencyConflictError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=str(exc),
        ) from exc

    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=str(exc),
        ) from exc

    except Exception:
        session.rollback()
        raise

    return response


@router.get(
    "/{event_id}",
    response_model=EventInspectionResponse,
)
def get_event(
    event_id: UUID,
    application: Annotated[
        Application,
        Depends(get_current_application),
    ],
    session: Annotated[
        Session,
        Depends(get_db_session),
    ],
) -> EventInspectionResponse:
    """Retrieve an event belonging to the authenticated application."""

    event = get_application_event(
        session=session,
        application=application,
        event_id=event_id,
    )

    if event is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Event not found",
        )

    return EventInspectionResponse.model_validate(event)


@router.get(
    "/{event_id}/deliveries",
    response_model=list[EventDeliveryResponse],
)
def list_event_deliveries(
    event_id: UUID,
    application: Annotated[
        Application,
        Depends(get_current_application),
    ],
    session: Annotated[
        Session,
        Depends(get_db_session),
    ],
) -> list[EventDeliveryResponse]:
    """List deliveries belonging to an application-owned event."""

    deliveries = list_application_event_deliveries(
        session=session,
        application=application,
        event_id=event_id,
    )

    if deliveries is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Event not found",
        )

    return [EventDeliveryResponse.model_validate(delivery) for delivery in deliveries]
