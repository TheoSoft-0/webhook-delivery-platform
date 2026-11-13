from secrets import token_urlsafe

from cryptography.fernet import Fernet, InvalidToken

from webhook_delivery_platform.config import get_settings

SIGNING_SECRET_PREFIX = "whsec_"
SIGNING_SECRET_RANDOM_BYTES = 32


def generate_signing_secret() -> str:
    """Generate a cryptographically random destination signing secret."""

    random_secret = token_urlsafe(SIGNING_SECRET_RANDOM_BYTES)

    return f"{SIGNING_SECRET_PREFIX}{random_secret}"


def _get_fernet() -> Fernet:
    """Create a Fernet instance using the configured encryption key."""

    settings = get_settings()

    encryption_key = settings.destination_encryption_key.get_secret_value()

    return Fernet(encryption_key)


def encrypt_signing_secret(signing_secret: str) -> str:
    """Encrypt a signing secret for database storage."""

    if not signing_secret:
        raise ValueError("Signing secret cannot be empty.")

    encrypted_secret = _get_fernet().encrypt(signing_secret.encode("utf-8"))

    return encrypted_secret.decode("ascii")


def decrypt_signing_secret(ciphertext: str) -> str:
    """Decrypt a signing secret retrieved from database storage."""

    try:
        encrypted_secret = ciphertext.encode("ascii")
        decrypted_secret = _get_fernet().decrypt(encrypted_secret)

        return decrypted_secret.decode("utf-8")

    except (InvalidToken, UnicodeError) as exc:
        raise ValueError(
            "Signing secret ciphertext is invalid or cannot be decrypted."
        ) from exc
