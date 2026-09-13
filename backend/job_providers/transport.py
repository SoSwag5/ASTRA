"""Centralized, policy-bound outbound transport for job-discovery providers.

Every provider fetch goes through `fetch_json` here rather than inventing
its own timeouts, redirect handling, or size caps -- the same rule ADR-0009
requires for every adapter.

DNS-rebinding note: `backend.policy.validate_url()` resolves and checks the
destination *before* httpx connects, but httpx/httpcore then independently
re-resolve the hostname at actual connect time (`socket.create_connection`
inside `httpcore.SyncBackend.connect_tcp`) -- a TOCTOU gap an attacker
controlling DNS could exploit between the two lookups. `_PinnedTransport`
closes it by resolving+validating the destination once and connecting the
raw socket directly to that validated address. TLS SNI and certificate
verification are unaffected: httpcore derives `server_hostname` from the
connection's origin (the real hostname), never from what `connect_tcp()`
was asked to dial, so pinning the socket target never weakens hostname
verification.
"""
import ipaddress
import json as json_module
import socket
import ssl
import time
from urllib.parse import urljoin

import httpcore
import httpx

from ..policy import validate_url

MAX_RESPONSE_BYTES = 5_000_000  # matches backend/adapters.py's existing cap
MAX_REDIRECTS = 5               # matches backend/adapters.py's existing cap
CONNECT_TIMEOUT = 10.0
READ_TIMEOUT = 20.0
RETRY_STATUSES = (429, 500, 502, 503, 504)
MAX_RETRIES = 2
MAX_RETRY_AFTER_SECONDS = 30.0
USER_AGENT = 'ASTRA/1.0 personal-career-assistant'


class TransportError(ValueError):
    """Sanitized transport failure. `code` is safe to log/report; `message`
    never embeds raw upstream payloads, headers, or URLs with query data.
    """
    def __init__(self, code, message):
        super().__init__(message)
        self.code = code


class Budget:
    """Mutable counters and a wall-clock deadline shared across every
    request one provider fetch makes, so a single source can never exceed
    its own request/byte/time budget no matter how many list/detail calls
    it issues.
    """
    def __init__(self, deadline_seconds):
        self.deadline = time.monotonic() + deadline_seconds
        self.requests = 0
        self.retries = 0
        self.bytes_read = 0

    def remaining(self):
        return max(0.0, self.deadline - time.monotonic())

    def check(self):
        if self.remaining() <= 0:
            raise TransportError('DEADLINE_EXCEEDED', 'Source deadline exceeded')


def _resolve_and_pin(host, port):
    try:
        infos = socket.getaddrinfo(host, port, type=socket.SOCK_STREAM)
    except OSError as error:
        raise TransportError('DNS_RESOLUTION_FAILED', 'Destination could not be resolved') from error
    addresses = [info[4][0] for info in infos]
    if not addresses:
        raise TransportError('DNS_RESOLUTION_FAILED', 'Destination could not be resolved')
    for address in addresses:
        if not ipaddress.ip_address(address).is_global:
            raise TransportError('DESTINATION_BLOCKED', 'Private network addresses are blocked')
    return addresses[0]


class _ValidatedNetworkBackend(httpcore.NetworkBackend):
    def __init__(self):
        self._inner = httpcore.SyncBackend()

    def connect_tcp(self, host, port, timeout=None, local_address=None, socket_options=None):
        pinned = _resolve_and_pin(host, port)
        return self._inner.connect_tcp(pinned, port, timeout=timeout, local_address=local_address, socket_options=socket_options)

    def connect_unix_socket(self, path, timeout=None, socket_options=None):
        raise TransportError('UNSUPPORTED_TRANSPORT', 'Unix sockets are never used for provider fetches')

    def sleep(self, seconds):
        self._inner.sleep(seconds)


class _PinnedTransport(httpx.HTTPTransport):
    def __init__(self):
        self._pool = httpcore.ConnectionPool(
            ssl_context=ssl.create_default_context(),
            network_backend=_ValidatedNetworkBackend(),
            retries=0,
            max_connections=10,
        )


def _bounded_retry_after(value):
    try:
        seconds = float(value)
    except (TypeError, ValueError):
        seconds = 1.0
    return max(0.0, min(seconds, MAX_RETRY_AFTER_SECONDS))


def fetch_json(url, budget, accept_types=('application/json',)):
    """Fetch one URL under `budget`, following bounded redirects
    (revalidated against policy.py on every hop), enforcing a decoded-size
    cap during streaming (bounds decompression expansion, not just the
    final size), and retrying transient failures a bounded number of times
    with a capped Retry-After wait. Returns parsed JSON or raises
    TransportError.
    """
    budget.check()
    validate_url(url)
    attempt = 0
    with httpx.Client(
        transport=_PinnedTransport(),
        timeout=httpx.Timeout(connect=CONNECT_TIMEOUT, read=READ_TIMEOUT, write=READ_TIMEOUT, pool=CONNECT_TIMEOUT),
        trust_env=False,
        follow_redirects=False,
        headers={'User-Agent': USER_AGENT},
    ) as client:
        for _ in range(MAX_REDIRECTS + 1):
            budget.check()
            budget.requests += 1
            try:
                with client.stream('GET', url) as stream:
                    if stream.is_redirect:
                        location = stream.headers.get('location', '')
                        stream.close()
                        url = urljoin(url, location)
                        validate_url(url)
                        continue
                    if stream.status_code in RETRY_STATUSES:
                        retry_after = _bounded_retry_after(stream.headers.get('retry-after'))
                        last_status = stream.status_code
                        stream.close()
                        if attempt >= MAX_RETRIES:
                            code = 'RATE_LIMITED' if last_status == 429 else 'UPSTREAM_UNAVAILABLE'
                            raise TransportError(code, f'Upstream returned {last_status} after retries')
                        attempt += 1
                        budget.retries += 1
                        budget.check()
                        time.sleep(min(retry_after, budget.remaining()))
                        continue
                    if stream.status_code >= 400:
                        raise TransportError('UPSTREAM_ERROR', f'Upstream returned {stream.status_code}')
                    content_type = stream.headers.get('content-type', '')
                    if not any(t in content_type for t in accept_types):
                        raise TransportError('UNEXPECTED_CONTENT_TYPE', 'Response was not the expected content type')
                    chunks = []
                    size = 0
                    for chunk in stream.iter_bytes():
                        size += len(chunk)
                        if size > MAX_RESPONSE_BYTES:
                            raise TransportError('RESPONSE_TOO_LARGE', 'Response exceeded the size cap')
                        chunks.append(chunk)
                    budget.bytes_read += size
                    body = b''.join(chunks)
            except httpx.TimeoutException as error:
                raise TransportError('TIMEOUT', 'Request timed out') from error
            try:
                return json_module.loads(body)
            except ValueError as error:
                raise TransportError('MALFORMED_RESPONSE', 'Response was not valid JSON') from error
        raise TransportError('TOO_MANY_REDIRECTS', 'Too many redirects')
