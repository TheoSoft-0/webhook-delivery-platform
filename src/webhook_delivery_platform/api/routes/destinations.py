from datetime import datetime
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Path, Response, status
from pydantic import BaseModel, ConfigDict
from sqlalchemy.orm import Session

from webhook_delivery_platform.api.authentication import (
    get_current_application,
)
from webhook_delivery_platform.api.dependencies import get_db_session
from webhook_delivery_platform.models import Application
from webhook_delivery_platform.services.destination_management import (
    update_destination_enabled,
)
from webhook_delivery_platform.services.destination_queries import (
    get_application_destination,
    list_application_destinations,
)
from webhook_delivery_platform.services.destination_registration import (
    register_destination,
)
from webhook_delivery_platform.services.destination_subscriptions import (
    add_destination_subscription,
    remove_destination_subscription,
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


class DestinationUpdateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    is_enabled: bool


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


@router.patch(
    "/{destination_id}",
    response_model=DestinationResponse,
)
def update_destination(
    destination_id: UUID,
    request: DestinationUpdateRequest,
    application: Annotated[
        Application,
        Depends(get_current_application),
    ],
    session: Annotated[
        Session,
        Depends(get_db_session),
    ],
) -> DestinationResponse:
    """Enable or disable a destination belonging to the authenticated application."""

    try:
        destination = update_destination_enabled(
            session=session,
            application=application,
            destination_id=destination_id,
            is_enabled=request.is_enabled,
        )

        if destination is not None:
            response = DestinationResponse.model_validate(destination)
            session.commit()

    except Exception:
        session.rollback()
        raise

    if destination is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Destination not found",
        )

    return response


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


@router.put(
    "/{destination_id}/subscriptions/{event_type}",
    status_code=status.HTTP_204_NO_CONTENT,
)
def create_destination_subscription(
    destination_id: UUID,
    event_type: Annotated[str, Path(min_length=1, max_length=255)],
    application: Annotated[
        Application,
        Depends(get_current_application),
    ],
    session: Annotated[
        Session,
        Depends(get_db_session),
    ],
) -> Response:
    """Subscribe an application-owned destination to an event type."""

    try:
        destination_exists = add_destination_subscription(
            session=session,
            application=application,
            destination_id=destination_id,
            event_type=event_type,
        )

        if destination_exists:
            session.commit()

    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=str(exc),
        ) from exc
    except Exception:
        session.rollback()
        raise

    if not destination_exists:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Destination not found",
        )

    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.delete(
    "/{destination_id}/subscriptions/{event_type}",
    status_code=status.HTTP_204_NO_CONTENT,
)
def delete_destination_subscription(
    destination_id: UUID,
    event_type: Annotated[str, Path(min_length=1, max_length=255)],
    application: Annotated[
        Application,
        Depends(get_current_application),
    ],
    session: Annotated[
        Session,
        Depends(get_db_session),
    ],
) -> Response:
    """Remove a subscription from an application-owned destination."""

    try:
        destination_exists = remove_destination_subscription(
            session=session,
            application=application,
            destination_id=destination_id,
            event_type=event_type,
        )

        if destination_exists:
            session.commit()

    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=str(exc),
        ) from exc
    except Exception:
        session.rollback()
        raise

    if not destination_exists:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Destination not found",
        )

    return Response(status_code=status.HTTP_204_NO_CONTENT)
