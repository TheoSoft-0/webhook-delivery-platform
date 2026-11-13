import ipaddress
import socket
import time
from collections.abc import Iterable, Iterator
from contextlib import contextmanager

import httpcore
import httpx

_HTTPCORE_EXCEPTION_MAP: dict[
    type[Exception],
    type[httpx.HTTPError],
] = {
    httpcore.TimeoutException: httpx.TimeoutException,
    httpcore.ConnectTimeout: httpx.ConnectTimeout,
    httpcore.ReadTimeout: httpx.ReadTimeout,
    httpcore.WriteTimeout: httpx.WriteTimeout,
    httpcore.PoolTimeout: httpx.PoolTimeout,
    httpcore.NetworkError: httpx.NetworkError,
    httpcore.ConnectError: httpx.ConnectError,
    httpcore.ReadError: httpx.ReadError,
    httpcore.WriteError: httpx.WriteError,
    httpcore.ProxyError: httpx.ProxyError,
    httpcore.UnsupportedProtocol: httpx.UnsupportedProtocol,
    httpcore.ProtocolError: httpx.ProtocolError,
    httpcore.LocalProtocolError: httpx.LocalProtocolError,
    httpcore.RemoteProtocolError: httpx.RemoteProtocolError,
}


@contextmanager
def _map_httpcore_exceptions() -> Iterator[None]:
    """Convert HTTP Core exceptions into equivalent HTTPX exceptions."""

    try:
        yield

    except Exception as exc:
        mapped_exception: type[httpx.HTTPError] | None = None

        for source_exception, target_exception in _HTTPCORE_EXCEPTION_MAP.items():
            if not isinstance(exc, source_exception):
                continue

            if mapped_exception is None or issubclass(
                target_exception, mapped_exception
            ):
                mapped_exception = target_exception

        if mapped_exception is None:
            raise

        raise mapped_exception(str(exc)) from exc


class DNSValidatedNetworkBackend(httpcore.SyncBackend):
    """Resolve destination hostnames and validate every returned IP address."""

    def connect_tcp(
        self,
        host: str,
        port: int,
        timeout: float | None = None,
        local_address: str | None = None,
        socket_options: Iterable[httpcore.SOCKET_OPTION] | None = None,
    ) -> httpcore.NetworkStream:
        started_at = time.monotonic()

        try:
            resolved_addresses = socket.getaddrinfo(
                host,
                port,
                family=socket.AF_UNSPEC,
                type=socket.SOCK_STREAM,
                proto=socket.IPPROTO_TCP,
            )

        except OSError as exc:
            raise httpcore.ConnectError(
                f"Could not resolve destination hostname {host!r}."
            ) from exc

        if not resolved_addresses:
            raise httpcore.ConnectError(
                "Destination hostname resolved to no IP addresses."
            )

        validated_addresses: list[str] = []
        seen_addresses: set[str] = set()

        for family, _, _, _, sockaddr in resolved_addresses:
            try:
                address_text = sockaddr[0]

                if not isinstance(address_text, str) or "%" in address_text:
                    raise ValueError("Invalid or scoped IP address.")

                address = ipaddress.ip_address(address_text)

            except (IndexError, TypeError, ValueError) as exc:
                raise httpcore.ConnectError(
                    "DNS resolution returned an invalid IP address."
                ) from exc

            if family == socket.AF_INET and (
                address.version != 4 or len(sockaddr) != 2
            ):
                raise httpcore.ConnectError(
                    "DNS resolution returned an incorrect IPv4 address."
                )

            if family == socket.AF_INET6:
                if address.version != 6 or len(sockaddr) != 4:
                    raise httpcore.ConnectError(
                        "DNS resolution returned an incorrect IPv6 address."
                    )

                if sockaddr[2] != 0 or sockaddr[3] != 0:
                    raise httpcore.ConnectError(
                        "DNS resolution returned a scoped IPv6 address."
                    )

            if not address.is_global or address.is_multicast or address.is_reserved:
                raise httpcore.ConnectError(
                    "Destination hostname resolved to a prohibited IP address: "
                    f"{address.compressed}."
                )

            normalized_address = address.compressed

            if normalized_address not in seen_addresses:
                seen_addresses.add(normalized_address)
                validated_addresses.append(normalized_address)

        # Preserve the socket options when multiple addresses are attempted.
        reusable_socket_options = (
            tuple(socket_options) if socket_options is not None else None
        )

        last_error: httpcore.ConnectError | httpcore.ConnectTimeout | None = None

        for address in validated_addresses:
            remaining_timeout = timeout

            if timeout is not None:
                remaining_timeout = timeout - (time.monotonic() - started_at)

                if remaining_timeout <= 0:
                    raise httpcore.ConnectTimeout(
                        "Connection timeout expired before connection succeeded."
                    )

            try:
                # The address is now a validated numeric IP address.
                # SyncBackend performs the actual TCP and socket operations.
                return super().connect_tcp(
                    host=address,
                    port=port,
                    timeout=remaining_timeout,
                    local_address=local_address,
                    socket_options=reusable_socket_options,
                )

            except (httpcore.ConnectError, httpcore.ConnectTimeout) as exc:
                last_error = exc

        if last_error is not None:
            raise last_error

        raise httpcore.ConnectError("No valid destination IP addresses were available.")


class _HTTPcoreResponseStream(httpx.SyncByteStream):
    """Adapt an HTTP Core response stream to HTTPX's stream interface."""

    def __init__(self, stream: Iterable[bytes]) -> None:
        self._stream = stream

    def __iter__(self) -> Iterator[bytes]:
        with _map_httpcore_exceptions():
            yield from self._stream

    def close(self) -> None:
        if hasattr(self._stream, "close"):
            self._stream.close()


class DNSValidatedHTTPTransport(httpx.BaseTransport):
    """HTTPX transport that uses DNS-validated TCP connections."""

    def __init__(self) -> None:
        limits = httpx.Limits()

        self._pool = httpcore.ConnectionPool(
            max_connections=limits.max_connections,
            max_keepalive_connections=limits.max_keepalive_connections,
            keepalive_expiry=limits.keepalive_expiry,
            network_backend=DNSValidatedNetworkBackend(),
            retries=0,
        )

    def handle_request(self, request: httpx.Request) -> httpx.Response:
        """Send a request through the DNS-validated connection pool."""

        assert isinstance(request.stream, httpx.SyncByteStream)

        core_request = httpcore.Request(
            method=request.method,
            url=httpcore.URL(
                scheme=request.url.raw_scheme,
                host=request.url.raw_host,
                port=request.url.port,
                target=request.url.raw_path,
            ),
            headers=request.headers.raw,
            content=request.stream,
            extensions=request.extensions,
        )

        with _map_httpcore_exceptions():
            core_response = self._pool.handle_request(core_request)

        assert isinstance(core_response.stream, Iterable)

        return httpx.Response(
            status_code=core_response.status,
            headers=core_response.headers,
            stream=_HTTPcoreResponseStream(core_response.stream),
            extensions=core_response.extensions,
        )

    def close(self) -> None:
        """Close the underlying HTTP Core connection pool."""

        with _map_httpcore_exceptions():
            self._pool.close()


def create_destination_http_client() -> httpx.Client:
    """Create an HTTP client with DNS validation and redirects disabled."""

    return httpx.Client(
        transport=DNSValidatedHTTPTransport(),
        trust_env=False,
        follow_redirects=False,
    )
