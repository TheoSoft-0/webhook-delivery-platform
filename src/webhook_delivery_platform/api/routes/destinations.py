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
from webhook_delivery_platform.services.destination_registration import (
    register_destination,
)

router = APIRouter(
    prefix="/v1/destinations",
    tags=["Destinations"],
)


class DestinationCreateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    url: str


class DestinationCreateResponse(BaseModel):
    id: UUID
    url: str
    is_enabled: bool
    created_at: datetime
    signing_secret: str


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
