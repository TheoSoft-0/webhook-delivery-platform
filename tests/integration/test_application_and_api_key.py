from hashlib import sha256
from uuid import UUID, uuid4

import pytest
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from webhook_delivery_platform.models import ApiKey, Application


def generate_key_hash() -> str:
    """Generate a unique test hash without creating a real API key."""

    return sha256(uuid4().bytes).hexdigest()


def test_application_can_be_created(db_session: Session) -> None:
    application = Application(name="Integration Test Application")

    db_session.add(application)
    db_session.flush()

    assert isinstance(application.id, UUID)
    assert application.name == "Integration Test Application"
    assert application.created_at is not None

    persisted_application = db_session.get(
        Application,
        application.id,
    )

    assert persisted_application is not None
    assert persisted_application.name == application.name


def test_api_key_belongs_to_application(db_session: Session) -> None:
    application = Application(name="API Key Test Application")

    api_key = ApiKey(
        key_hash=generate_key_hash(),
        application=application,
    )

    db_session.add(api_key)
    db_session.flush()

    assert api_key.application_id == application.id
    assert api_key.application.id == application.id
    assert api_key.application.name == application.name


def test_api_key_rejects_nonexistent_application(
    db_session: Session,
) -> None:
    api_key = ApiKey(
        application_id=uuid4(),
        key_hash=generate_key_hash(),
    )

    db_session.add(api_key)

    with pytest.raises(IntegrityError):
        db_session.flush()


def test_api_key_hash_must_be_unique(db_session: Session) -> None:
    application = Application(name="Unique Hash Test Application")
    db_session.add(application)
    db_session.flush()

    key_hash = generate_key_hash()

    first_key = ApiKey(
        application_id=application.id,
        key_hash=key_hash,
    )

    db_session.add(first_key)
    db_session.flush()

    second_key = ApiKey(
        application_id=application.id,
        key_hash=key_hash,
    )

    db_session.add(second_key)

    with pytest.raises(IntegrityError):
        db_session.flush()
