from collections.abc import Iterator

import pytest
from sqlalchemy import text
from sqlalchemy.orm import Session

from webhook_delivery_platform.config import get_settings
from webhook_delivery_platform.database import engine


@pytest.fixture(scope="session", autouse=True)
def verify_test_database() -> None:
    """Prevent integration tests from using the development database."""

    expected_database = "webhook_delivery_test"
    settings = get_settings()

    if settings.postgres_db != expected_database:
        pytest.exit(
            f"Tests require {expected_database!r}. "
            f"Configured database: {settings.postgres_db!r}",
            returncode=1,
        )

    with engine.connect() as connection:
        actual_database = connection.scalar(text("SELECT current_database()"))

        actual_user = connection.scalar(text("SELECT current_user"))

    if actual_database != expected_database or actual_user != "webhook_app":
        pytest.exit(
            "Unexpected database connection. "
            f"Database: {actual_database!r}, user: {actual_user!r}",
            returncode=1,
        )


@pytest.fixture
def db_session(verify_test_database: None) -> Iterator[Session]:
    """Provide an isolated database transaction for each test."""

    with engine.connect() as connection:
        transaction = connection.begin()

        session = Session(
            bind=connection,
            autoflush=False,
            expire_on_commit=False,
            join_transaction_mode="create_savepoint",
        )

        try:
            yield session
        finally:
            session.close()
            transaction.rollback()
