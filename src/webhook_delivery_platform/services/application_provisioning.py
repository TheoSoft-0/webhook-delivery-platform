from dataclasses import dataclass, field
from uuid import UUID

from sqlalchemy.orm import Session

from webhook_delivery_platform.models import ApiKey, Application
from webhook_delivery_platform.security.api_keys import (
    generate_api_key,
    hash_api_key,
)


@dataclass(frozen=True, slots=True)
class ProvisionedApplication:
    application_id: UUID
    api_key_id: UUID
    raw_api_key: str = field(repr=False)


def provision_application(
    session: Session,
    name: str,
) -> ProvisionedApplication:
    """Create an application and its first API key."""

    normalized_name = name.strip()

    if not normalized_name:
        raise ValueError("Application name cannot be empty.")

    if len(normalized_name) > 120:
        raise ValueError("Application name cannot exceed 120 characters.")

    raw_api_key = generate_api_key()

    application = Application(name=normalized_name)

    api_key = ApiKey(
        key_hash=hash_api_key(raw_api_key),
        application=application,
    )

    session.add(application)
    session.add(api_key)

    session.flush()

    return ProvisionedApplication(
        application_id=application.id,
        api_key_id=api_key.id,
        raw_api_key=raw_api_key,
    )
