import ipaddress
import re
from urllib.parse import urlsplit, urlunsplit

_ALLOWED_SCHEMES = {"http", "https"}

_FORBIDDEN_DOMAIN_SUFFIXES = (
    ".localhost",
    ".local",
    ".internal",
    ".home.arpa",
)

_DOMAIN_LABEL_PATTERN = re.compile(r"^[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?$")

_NUMERIC_IP_VARIANT_PATTERN = re.compile(
    r"(?i)^(?:0x[0-9a-f]+|[0-9]+)"
    r"(?:\.(?:0x[0-9a-f]+|[0-9]+))*$"
)


def validate_destination_url(url: str) -> str:
    """Validate and normalize a destination URL."""

    if not isinstance(url, str) or not url:
        raise ValueError("Destination URL cannot be empty.")

    if url != url.strip():
        raise ValueError("Destination URL cannot contain surrounding whitespace.")

    if "\\" in url:
        raise ValueError("Destination URL cannot contain backslashes.")

    if any(ord(character) <= 32 or ord(character) == 127 for character in url):
        raise ValueError("Destination URL cannot contain control characters or spaces.")

    if "#" in url:
        raise ValueError("Destination URL cannot contain a fragment.")

    try:
        parsed = urlsplit(url)
    except ValueError as exc:
        raise ValueError("Destination URL is malformed.") from exc

    scheme = parsed.scheme.lower()

    if scheme not in _ALLOWED_SCHEMES:
        raise ValueError("Destination URL must use HTTP or HTTPS.")

    if not parsed.netloc:
        raise ValueError("Destination URL must contain a hostname.")

    if "@" in parsed.netloc:
        raise ValueError("Destination URL cannot contain credentials.")

    if parsed.netloc.endswith(":"):
        raise ValueError("Destination URL cannot have an empty port.")

    try:
        hostname = parsed.hostname
        port = parsed.port
    except ValueError as exc:
        raise ValueError(
            "Destination URL contains an invalid hostname or port."
        ) from exc

    if hostname is None:
        raise ValueError("Destination URL must contain a hostname.")

    if "%" in hostname:
        raise ValueError("Destination hostname cannot contain percent encoding.")

    if port is not None and not 1 <= port <= 65535:
        raise ValueError("Destination URL contains an invalid port.")

    try:
        address = ipaddress.ip_address(hostname)
    except ValueError:
        normalized_hostname = _validate_domain_name(hostname)
    else:
        if not address.is_global or address.is_multicast:
            raise ValueError(
                "Destination IP address must be a globally reachable unicast address."
            )

        normalized_hostname = address.compressed

        if address.version == 6:
            normalized_hostname = f"[{normalized_hostname}]"

    authority = normalized_hostname

    if port is not None:
        authority = f"{authority}:{port}"

    return urlunsplit(
        (
            scheme,
            authority,
            parsed.path,
            parsed.query,
            "",
        )
    )


def _validate_domain_name(hostname: str) -> str:
    """Validate a hostname that is not an IP address."""

    try:
        ascii_hostname = hostname.encode("idna").decode("ascii").lower()
    except UnicodeError as exc:
        raise ValueError("Destination hostname is invalid.") from exc

    if len(ascii_hostname) > 253:
        raise ValueError("Destination hostname is too long.")

    if ascii_hostname.endswith("."):
        raise ValueError("Destination hostname cannot end with a dot.")

    if _NUMERIC_IP_VARIANT_PATTERN.fullmatch(ascii_hostname):
        raise ValueError("Destination hostname uses an ambiguous numeric format.")

    if any(ascii_hostname.endswith(suffix) for suffix in _FORBIDDEN_DOMAIN_SUFFIXES):
        raise ValueError("Destination hostname uses a prohibited local domain.")

    labels = ascii_hostname.split(".")

    if len(labels) < 2:
        raise ValueError("Destination hostname must be a fully qualified domain name.")

    if not all(_DOMAIN_LABEL_PATTERN.fullmatch(label) for label in labels):
        raise ValueError("Destination hostname contains an invalid domain label.")

    return ascii_hostname
