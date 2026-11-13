import ipaddress
import socket
import ssl

import httpcore
import pytest

from webhook_delivery_platform.security.destination_http import (
    DNSValidatedHTTPTransport,
    DNSValidatedNetworkBackend,
    create_destination_http_client,
)


class FakeNetworkStream:
    """Simulate a network connection for HTTP transport tests."""

    def __init__(self):
        self.response_data = bytearray(
            b"HTTP/1.1 200 OK\r\nContent-Length: 2\r\nConnection: close\r\n\r\nOK"
        )

        self.request_data = bytearray()
        self.tls_server_hostname = None
        self.ssl_context = None
        self.closed = False

    def read(self, max_bytes, timeout=None):
        data = bytes(self.response_data[:max_bytes])
        del self.response_data[:max_bytes]
        return data

    def write(self, buffer, timeout=None):
        self.request_data.extend(buffer)

    def close(self):
        self.closed = True

    def start_tls(
        self,
        ssl_context: ssl.SSLContext,
        server_hostname=None,
        timeout=None,
    ):
        self.ssl_context = ssl_context
        self.tls_server_hostname = server_hostname
        return self

    def get_extra_info(self, info):
        return None


def test_http_client_sends_request_using_validated_ip(monkeypatch):
    records = [make_address_record("8.8.8.8")]
    install_resolver(monkeypatch, records)

    connected_addresses = []
    stream = FakeNetworkStream()

    def fake_connect_tcp(
        self,
        host,
        port,
        timeout=None,
        local_address=None,
        socket_options=None,
    ):
        connected_addresses.append((host, port))
        return stream

    monkeypatch.setattr(
        httpcore.SyncBackend,
        "connect_tcp",
        fake_connect_tcp,
    )

    client = create_destination_http_client()

    try:
        response = client.post(
            "http://webhook.example.com/events",
            content=b"test payload",
        )

        assert response.status_code == 200
        assert response.content == b"OK"

    finally:
        client.close()

    assert connected_addresses == [("8.8.8.8", 80)]
    assert b"Host: webhook.example.com" in stream.request_data
    assert b"test payload" in stream.request_data


def test_https_passes_original_hostname_to_tls(monkeypatch):
    records = [make_address_record("8.8.8.8")]
    install_resolver(monkeypatch, records)

    connected_addresses = []
    stream = FakeNetworkStream()

    def fake_connect_tcp(
        self,
        host,
        port,
        timeout=None,
        local_address=None,
        socket_options=None,
    ):
        connected_addresses.append((host, port))
        return stream

    monkeypatch.setattr(
        httpcore.SyncBackend,
        "connect_tcp",
        fake_connect_tcp,
    )

    client = create_destination_http_client()

    try:
        response = client.post(
            "https://webhook.example.com/events",
            content=b"test payload",
        )

        assert response.status_code == 200
        assert response.content == b"OK"

    finally:
        client.close()

    assert connected_addresses == [("8.8.8.8", 443)]

    assert stream.tls_server_hostname == "webhook.example.com"

    assert stream.ssl_context is not None
    assert stream.ssl_context.check_hostname is True
    assert stream.ssl_context.verify_mode == ssl.CERT_REQUIRED

    assert b"Host: webhook.example.com" in stream.request_data


def make_address_record(address_text: str) -> tuple:
    address = ipaddress.ip_address(address_text)

    if address.version == 4:
        family = socket.AF_INET
        sockaddr = (address_text, 443)
    else:
        family = socket.AF_INET6
        sockaddr = (address_text, 443, 0, 0)

    return (
        family,
        socket.SOCK_STREAM,
        socket.IPPROTO_TCP,
        "",
        sockaddr,
    )


def install_resolver(monkeypatch, records):
    def fake_getaddrinfo(*args, **kwargs):
        return records

    monkeypatch.setattr(socket, "getaddrinfo", fake_getaddrinfo)


def test_connects_using_resolved_ip_address(monkeypatch):
    records = [make_address_record("8.8.8.8")]
    install_resolver(monkeypatch, records)

    calls = []
    expected_stream = object()

    def fake_connect_tcp(
        self,
        host,
        port,
        timeout=None,
        local_address=None,
        socket_options=None,
    ):
        calls.append((host, port))
        return expected_stream

    monkeypatch.setattr(httpcore.SyncBackend, "connect_tcp", fake_connect_tcp)

    backend = DNSValidatedNetworkBackend()

    result = backend.connect_tcp(
        host="webhook.example.com",
        port=443,
    )

    assert result is expected_stream
    assert calls == [("8.8.8.8", 443)]


@pytest.mark.parametrize(
    "address",
    [
        "127.0.0.1",
        "10.0.0.1",
        "169.254.1.1",
        "224.0.0.1",
        "192.0.2.1",
        "255.255.255.255",
        "::1",
        "fc00::1",
        "fe80::1",
        "ff02::1",
        "2001:db8::1",
        "64:ff9b::a9fe:a9fe",
        "::a9fe:a9fe",
    ],
)
def test_rejects_prohibited_resolved_addresses(monkeypatch, address):
    records = [make_address_record(address)]
    install_resolver(monkeypatch, records)

    calls = []

    def fake_connect_tcp(self, host, port, **kwargs):
        calls.append(host)
        return object()

    monkeypatch.setattr(httpcore.SyncBackend, "connect_tcp", fake_connect_tcp)

    backend = DNSValidatedNetworkBackend()

    with pytest.raises(httpcore.ConnectError, match="prohibited IP address"):
        backend.connect_tcp(
            host="webhook.example.com",
            port=443,
        )

    assert calls == []


def test_rejects_mixed_public_and_private_dns_results(monkeypatch):
    records = [
        make_address_record("8.8.8.8"),
        make_address_record("127.0.0.1"),
    ]
    install_resolver(monkeypatch, records)

    calls = []

    def fake_connect_tcp(self, host, port, **kwargs):
        calls.append(host)
        return object()

    monkeypatch.setattr(httpcore.SyncBackend, "connect_tcp", fake_connect_tcp)

    backend = DNSValidatedNetworkBackend()

    with pytest.raises(httpcore.ConnectError, match="prohibited IP address"):
        backend.connect_tcp(
            host="webhook.example.com",
            port=443,
        )

    assert calls == []


def test_tries_next_valid_address_after_connection_failure(monkeypatch):
    records = [
        make_address_record("8.8.8.8"),
        make_address_record("1.1.1.1"),
    ]
    install_resolver(monkeypatch, records)

    calls = []
    expected_stream = object()

    def fake_connect_tcp(self, host, port, **kwargs):
        calls.append(host)

        if host == "8.8.8.8":
            raise httpcore.ConnectError("Connection failed.")

        return expected_stream

    monkeypatch.setattr(httpcore.SyncBackend, "connect_tcp", fake_connect_tcp)

    backend = DNSValidatedNetworkBackend()

    result = backend.connect_tcp(
        host="webhook.example.com",
        port=443,
    )

    assert result is expected_stream
    assert calls == ["8.8.8.8", "1.1.1.1"]


def test_rejects_failed_dns_resolution(monkeypatch):
    def fake_getaddrinfo(*args, **kwargs):
        raise socket.gaierror("DNS resolution failed.")

    monkeypatch.setattr(socket, "getaddrinfo", fake_getaddrinfo)

    backend = DNSValidatedNetworkBackend()

    with pytest.raises(httpcore.ConnectError, match="Could not resolve"):
        backend.connect_tcp(
            host="webhook.example.com",
            port=443,
        )


def test_rejects_empty_dns_results(monkeypatch):
    install_resolver(monkeypatch, [])

    backend = DNSValidatedNetworkBackend()

    with pytest.raises(httpcore.ConnectError, match="no IP addresses"):
        backend.connect_tcp(
            host="webhook.example.com",
            port=443,
        )


def test_http_transport_installs_dns_validated_backend(monkeypatch):
    captured_arguments = {}

    class FakeConnectionPool:
        def __init__(self, **kwargs):
            captured_arguments.update(kwargs)

        def close(self):
            pass

    monkeypatch.setattr(httpcore, "ConnectionPool", FakeConnectionPool)

    transport = DNSValidatedHTTPTransport()

    try:
        assert isinstance(
            captured_arguments["network_backend"],
            DNSValidatedNetworkBackend,
        )
    finally:
        transport.close()
