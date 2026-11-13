from hashlib import sha256
from secrets import token_urlsafe

API_KEY_PREFIX = "wdp_"
API_KEY_RANDOM_BYTES = 32


def generate_api_key() -> str:
    """Generate a cryptographically random API key."""

    random_secret = token_urlsafe(API_KEY_RANDOM_BYTES)

    return f"{API_KEY_PREFIX}{random_secret}"


def hash_api_key(api_key: str) -> str:
    """Return the SHA-256 hexadecimal hash of an API key."""

    return sha256(api_key.encode("utf-8")).hexdigest()
