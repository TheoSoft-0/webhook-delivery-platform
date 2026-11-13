from collections.abc import Generator

from sqlalchemy.orm import Session

from webhook_delivery_platform.database import SessionFactory


def get_db_session() -> Generator[Session]:
    """Provide a database session for one API request."""

    with SessionFactory() as session:
        yield session
