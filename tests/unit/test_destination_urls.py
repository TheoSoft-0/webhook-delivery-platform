import pytest

from webhook_delivery_platform.security.destination_urls import (
    validate_destination_url,
)


@pytest.mark.parametrize(
    ("url", "expected"),
    [
        (
            "https://example.com/webhooks",
            "https://example.com/webhooks",
        ),
        (
            "http://example.com",
            "http://example.com",
        ),
        (
            "HTTPS://Example.COM:8443/webhooks?source=test",
            "https://example.com:8443/webhooks?source=test",
        ),
        (
            "https://8.8.8.8/webhooks",
            "https://8.8.8.8/webhooks",
        ),
        (
            "https://[2606:4700:4700::1111]/webhooks",
            "https://[2606:4700:4700::1111]/webhooks",
        ),
        (
            "https://bücher.example/webhooks",
            "https://xn--bcher-kva.example/webhooks",
        ),
    ],
)
def test_valid_destination_urls_are_accepted(
    url: str,
    expected: str,
) -> None:
    assert validate_destination_url(url) == expected


@pytest.mark.parametrize(
    "url",
    [
        "",
        " ",
        "example.com",
        "ftp://example.com/webhooks",
        "file:///etc/passwd",
        "https:///missing-host",
        "https://",
        " https://example.com",
        "https://example.com ",
        "https://example.com/path with spaces",
        "https://example.com\\@evil.com",
        "https://example.com#fragment",
        "https://example.com:",
        "https://example.com:abc",
        "https://example.com:0",
        "https://example.com:65536",
        "https://user@example.com",
        "https://user:password@example.com",
        "https://localhost",
        "https://service.localhost",
        "https://service.local",
        "https://service.internal",
        "https://internal",
        "https://127.1",
        "https://0177.0.0.1",
        "https://0x7f.0x0.0x0.0x1",
        "https://-invalid.example",
        "https://invalid-.example",
        "https://invalid_host.example",
        "https://example.com.",
        "https://example%2ecom",
    ],
)
def test_invalid_destination_urls_are_rejected(url: str) -> None:
    with pytest.raises(ValueError):
        validate_destination_url(url)


@pytest.mark.parametrize(
    "address",
    [
        "0.0.0.0",
        "10.0.0.1",
        "100.64.0.1",
        "127.0.0.1",
        "169.254.169.254",
        "172.16.0.1",
        "192.168.1.1",
        "192.0.2.1",
        "224.0.0.1",
        "240.0.0.1",
        "::",
        "::1",
        "::ffff:127.0.0.1",
        "fc00::1",
        "fe80::1",
        "ff02::1",
    ],
)
def test_non_global_ip_addresses_are_rejected(address: str) -> None:
    url = f"https://[{address}]" if ":" in address else f"https://{address}"

    with pytest.raises(ValueError, match="globally reachable unicast"):
        validate_destination_url(url)


@pytest.mark.parametrize(
    "url",
    [
        "http://[64:ff9b::a9fe:a9fe]/webhooks",
        "http://[::a9fe:a9fe]/webhooks",
    ],
)
def test_rejects_ipv6_transition_addresses(url):
    with pytest.raises(ValueError):
        validate_destination_url(url)
