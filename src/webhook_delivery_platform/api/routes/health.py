from fastapi import APIRouter, HTTPException
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError

from webhook_delivery_platform.database import engine

router = APIRouter(tags=["Health"])


@router.get("/health/live")
def health_live() -> dict[str, str]:
    """Report whether the API process is running."""

    return {"status": "alive"}


@router.get("/health/ready")
def health_ready() -> dict[str, str]:
    """Report whether the API can communicate with PostgreSQL."""

    try:
        with engine.connect() as connection:
            connection.execute(text("SELECT 1"))

    except SQLAlchemyError as exc:
        raise HTTPException(
            status_code=503,
            detail="Database unavailable",
        ) from exc

    return {
        "status": "ready",
        "database": "connected",
    }
