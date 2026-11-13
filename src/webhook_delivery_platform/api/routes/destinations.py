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
from webhook_delivery_platform.services.destination_queries import (
    get_application_destination,
    list_application_destinations,
)
from webhook_delivery_platform.services.destination_registration import (
    register_destination,
)

router = APIRouter(
    prefix="/v1/destinations",
    tags=["Destinations"],
)


class DestinationResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    url: str
    is_enabled: bool
    created_at: datetime


class DestinationCreateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    url: str


class DestinationCreateResponse(DestinationResponse):
    signing_secret: str


@router.get(
    "",
    response_model=list[DestinationResponse],
)
def list_destinations(
    application: Annotated[
        Application,
        Depends(get_current_application),
    ],
    session: Annotated[
        Session,
        Depends(get_db_session),
    ],
) -> list[DestinationResponse]:
    """List destinations belonging to the authenticated application."""

    destinations = list_application_destinations(
        session=session,
        application=application,
    )

    return [
        DestinationResponse.model_validate(destination) for destination in destinations
    ]


@router.get(
    "/{destination_id}",
    response_model=DestinationResponse,
)
def get_destination(
    destination_id: UUID,
    application: Annotated[
        Application,
        Depends(get_current_application),
    ],
    session: Annotated[
        Session,
        Depends(get_db_session),
    ],
) -> DestinationResponse:
    """Retrieve one destination belonging to the authenticated application."""

    destination = get_application_destination(
        session=session,
        application=application,
        destination_id=destination_id,
    )

    if destination is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Destination not found",
        )

    return DestinationResponse.model_validate(destination)


@router.post(
    "",
    response_model=DestinationCreateResponse,
    status_code=status.HTTP_201_CREATED,
)
def create_destination(
    request: DestinationCreateRequest,
    application: Annotated[
        Application,
        Depends(get_current_application),
    ],
    session: Annotated[
        Session,
        Depends(get_db_session),
    ],
) -> DestinationCreateResponse:
    """Register a new webhook destination."""

    try:
        registered = register_destination(
            session=session,
            application=application,
            url=request.url,
        )
    except ValueError as exc:
        session.rollback()
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=str(exc),
        ) from exc
    except Exception:
        session.rollback()
        raise

    destination = registered.destination

    try:
        session.refresh(destination)

        response = DestinationCreateResponse(
            id=destination.id,
            url=destination.url,
            is_enabled=destination.is_enabled,
            created_at=destination.created_at,
            signing_secret=registered.signing_secret,
        )

        session.commit()

    except Exception:
        session.rollback()
        raise

    return response
