from dataclasses import dataclass, field

from sqlalchemy.orm import Session

from webhook_delivery_platform.models import Application, Destination
from webhook_delivery_platform.security.destination_secrets import (
    encrypt_signing_secret,
    generate_signing_secret,
)
from webhook_delivery_platform.security.destination_urls import (
    validate_destination_url,
)


@dataclass(frozen=True, slots=True)
class RegisteredDestination:
    destination: Destination
    signing_secret: str = field(repr=False)


def register_destination(
    session: Session,
    application: Application,
    url: str,
) -> RegisteredDestination:
    """Register a webhook destination for an application."""

    normalized_url = validate_destination_url(url)

    signing_secret = generate_signing_secret()
    encrypted_secret = encrypt_signing_secret(signing_secret)

    destination = Destination(
        application_id=application.id,
        url=normalized_url,
        signing_secret_ciphertext=encrypted_secret,
    )

    session.add(destination)
    session.flush()

    return RegisteredDestination(
        destination=destination,
        signing_secret=signing_secret,
    )
