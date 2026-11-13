from typing import Annotated

from fastapi import Depends, HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import select
from sqlalchemy.orm import Session

from webhook_delivery_platform.api.dependencies import get_db_session
from webhook_delivery_platform.models import ApiKey, Application
from webhook_delivery_platform.security.api_keys import (
    API_KEY_PREFIX,
    hash_api_key,
)

bearer_scheme = HTTPBearer(auto_error=False)


def get_current_application(
    credentials: Annotated[
        HTTPAuthorizationCredentials | None,
        Depends(bearer_scheme),
    ],
    session: Annotated[Session, Depends(get_db_session)],
) -> Application:
    """Authenticate an API key and return its owning application."""

    unauthorized = HTTPException(
        status_code=401,
        detail="Invalid or missing API key",
        headers={"WWW-Authenticate": "Bearer"},
    )

    if credentials is None:
        raise unauthorized

    if credentials.scheme.lower() != "bearer":
        raise unauthorized

    raw_api_key = credentials.credentials

    if not raw_api_key.startswith(API_KEY_PREFIX):
        raise unauthorized

    key_hash = hash_api_key(raw_api_key)

    statement = (
        select(Application)
        .join(ApiKey, ApiKey.application_id == Application.id)
        .where(
            ApiKey.key_hash == key_hash,
            ApiKey.revoked_at.is_(None),
        )
    )

    application = session.scalar(statement)

    if application is None:
        raise unauthorized

    return application
