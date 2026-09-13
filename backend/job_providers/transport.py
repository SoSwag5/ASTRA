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

Version-pin note: this relies on `httpcore.ConnectionPool(network_backend=...)`
being an accepted constructor argument, and on `httpx.HTTPTransport`'s
`_pool` attribute being the object whose `.handle_request`/`.close`/
`__enter__`/`__exit__` it inherits (there is no public API for injecting a
custom NetworkBackend through `httpx.HTTPTransport` itself, so
`_PinnedTransport` builds the pool directly rather than going through
`httpx.HTTPTransport.__init__`). It also relies on `server_hostname` for
TLS being derived from the connection's origin host, never from what
`connect_tcp()` is asked to dial. Verified against httpx==0.28.1,
httpcore==1.0.9 (see test_transport_dependency_versions_are_pinned below,
which fails loudly on an upgrade so this note and the pinning behavior get
re-verified together rather than silently drifting).
"""
import concurrent.futures
import ipaddress
import json as json_module
import socket
import ssl
import time
import zlib
from urllib.parse import urljoin

import httpcore
import httpx

from ..policy import validate_url

PINNED_HTTPX_VERSION = '0.28.1'
PINNED_HTTPCORE_VERSION = '1.0.9'

MAX_ENCODED_BYTES = 5_000_000   # raw wire bytes, before any decompression
MAX_DECODED_BYTES = 5_000_000   # usable content bytes, after decompression
DECOMPRESS_CHUNK = 65_536       # bounds peak temporary allocation per decompress() call
MAX_REDIRECTS = 5               # matches backend/adapters.py's existing cap
CONNECT_TIMEOUT = 10.0
READ_TIMEOUT = 20.0
RETRY_STATUSES = (429, 500, 502, 503, 504)
MAX_RETRIES = 2
MAX_RETRY_AFTER_SECONDS = 30.0
USER_AGENT = 'ASTRA/1.0 personal-career-assistant'

_DNS_EXECUTOR = concurrent.futures.ThreadPoolExecutor(max_workers=4, thread_name_prefix='job-provider-dns')


class TransportError(ValueError):
    """Sanitized transport failure. `code` is safe to log/report; `message`
    never embeds raw upstream payloads, headers, or URLs with query data.
    """
    def __init__(self, code, message):
        super().__init__(message)
        self.code = code


class Budget:
    """Mutable counters and a wall-clock deadline shared across every
    request one provider fetch makes (list and detail calls alike, since
    callers thread the same Budget through every fetch_json() call), so a
    single source can never exceed its own request/byte/time budget no
    matter how many calls it issues, and the deadline is a real upper
    bound on the whole operation rather than just a between-calls check.
    """
    def __init__(self, deadline_seconds):
        self.deadline = time.monotonic() + deadline_seconds
        self.requests_attempted = 0
        self.requests_succeeded = 0
        self.retries = 0
        self.encoded_bytes_read = 0
        self.decoded_bytes_read = 0
        self.errors_count = 0

    def remaining(self):
        return max(0.0, self.deadline - time.monotonic())

    def check(self):
        if self.remaining() <= 0:
            raise TransportError('DEADLINE_EXCEEDED', 'Source deadline exceeded')

    def clamped_timeout(self, cap):
        """Raises if the deadline has already passed; otherwise returns a
        timeout no larger than both `cap` and whatever time is left, so no
        single blocking operation can outlive the source's own deadline.
        """
        remaining = self.remaining()
        if remaining <= 0:
            raise TransportError('DEADLINE_EXCEEDED', 'Source deadline exceeded')
        return min(cap, remaining)

    def fail(self, code, message, cause=None):
        self.errors_count += 1
        raise TransportError(code, message) from cause


def _resolve_and_pin(host, port, timeout=None):
    """Resolves `host` and validates every returned address is global,
    bounded to `timeout` seconds. Python's socket.getaddrinfo() has no
    native cancellation, so an already-hung OS-level resolution is not
    forcibly killed when the timeout fires -- the waiting caller gives up
    and the background thread is abandoned to finish or die on its own.
    This bounds how long a provider fetch *waits* on DNS, which is what
    the source deadline needs; it does not guarantee the underlying
    syscall itself stops.
    """
    future = _DNS_EXECUTOR.submit(socket.getaddrinfo, host, port, type=socket.SOCK_STREAM)
    try:
        infos = future.result(timeout=timeout)
    except concurrent.futures.TimeoutError:
        raise TransportError('DEADLINE_EXCEEDED', 'DNS resolution exceeded the remaining source deadline')
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
        started = time.monotonic()
        pinned = _resolve_and_pin(host, port, timeout=timeout)
        if timeout is not None:
            remaining = timeout - (time.monotonic() - started)
            if remaining <= 0:
                raise TransportError('DEADLINE_EXCEEDED', 'Source deadline exceeded during DNS resolution')
            timeout = remaining
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


class _BoundedDecoder:
    """Incrementally decompresses at most `cap` decoded bytes total,
    raising the moment that is exceeded -- never decompressing a whole
    payload into memory before checking its size. `zlib.decompressobj`'s
    `max_length` argument bounds how much a single decompress() call can
    return, so a small compressed input that would expand into a huge
    output is caught after at most one DECOMPRESS_CHUNK-sized burst past
    the cap, not after materializing the full expansion.
    """
    def __init__(self, wbits, cap):
        try:
            self._z = zlib.decompressobj(wbits)
        except zlib.error as error:
            raise TransportError('MALFORMED_RESPONSE', 'Unsupported compression parameters') from error
        self._cap = cap
        self._total = 0

    def _produce(self, piece_bytes):
        """One bounded decompress()/flush() call. `piece_bytes` must
        already be a single call's worth of *compressed input* -- the
        caller is responsible for re-feeding `unconsumed_tail`, not the
        original data, on the next call; decompressobj is stateful and
        re-feeding already-consumed input would desync it.
        """
        if piece_bytes:
            self._total += len(piece_bytes)
            if self._total > self._cap:
                raise TransportError('RESPONSE_TOO_LARGE', 'Decoded response exceeded the size cap')
        return piece_bytes

    def feed(self, data):
        try:
            collected = bytearray(self._produce(self._z.decompress(data, DECOMPRESS_CHUNK)))
            while self._z.unconsumed_tail:
                collected.extend(self._produce(self._z.decompress(self._z.unconsumed_tail, DECOMPRESS_CHUNK)))
        except zlib.error as error:
            raise TransportError('MALFORMED_RESPONSE', 'Response could not be decompressed') from error
        return bytes(collected)

    def flush(self):
        """zlib's flush(length) hint does not truncate/bound its return
        value the way decompress()'s max_length does -- it is only a
        buffer-size hint, and flush() always returns everything left in
        one call. The cap is still enforced on the result (a pathological
        stream that defers content to flush() is still rejected), but
        unlike feed() this single call is not itself incrementally
        bounded. In practice a real stream's content is already yielded
        progressively by feed()'s decompress() calls; flush() typically
        returns only a small/empty tail.
        """
        try:
            return self._produce(self._z.flush(DECOMPRESS_CHUNK))
        except zlib.error as error:
            raise TransportError('MALFORMED_RESPONSE', 'Response could not be decompressed') from error


def _decoder_for(content_encoding, cap):
    encoding = (content_encoding or '').strip().lower()
    if encoding in ('', 'identity'):
        return None
    if encoding == 'gzip':
        return _BoundedDecoder(zlib.MAX_WBITS | 16, cap)
    if encoding == 'deflate':
        return _BoundedDecoder(zlib.MAX_WBITS, cap)
    raise TransportError('UNSUPPORTED_ENCODING', 'Unsupported content-encoding')


def _validate_redirect_target(url, budget):
    try:
        validate_url(url)
    except ValueError as error:
        budget.fail('POLICY_BLOCKED', str(error), cause=error)


def fetch_json(url, budget, accept_types=('application/json',)):
    """Fetch one URL under `budget`, following bounded redirects
    (revalidated against policy.py on every hop), enforcing a decoded-size
    cap via bounded incremental decompression (never decompressing a full
    payload before checking its size), and retrying transient failures a
    bounded number of times with a capped Retry-After wait. Every blocking
    step (connect/read timeout, DNS resolution, the Retry-After wait, the
    streaming loop itself) is clamped to whatever time remains on `budget`,
    so an active operation cannot outlive the source deadline and expired
    work never returns success. Returns parsed JSON or raises
    TransportError -- this never lets an un-typed exception (DNS failure,
    connection refused, TLS failure, a blocked-redirect ValueError from
    policy.py) escape uncaught.
    """
    budget.check()
    try:
        validate_url(url)
    except ValueError as error:
        budget.fail('POLICY_BLOCKED', str(error), cause=error)
    attempt = 0
    with httpx.Client(
        transport=_PinnedTransport(),
        trust_env=False,
        follow_redirects=False,
        # Prefer uncooperative servers to simply not compress (Codex F2
        # option A): a well-behaved API has no reason to compress and this
        # reduces the common-case attack surface. A server that ignores
        # this and sends Content-Encoding anyway (or a malicious one)
        # still hits the bounded decoder below (option B) -- identity is
        # a preference, never the actual safety boundary.
        headers={'User-Agent': USER_AGENT, 'Accept-Encoding': 'identity'},
    ) as client:
        for _ in range(MAX_REDIRECTS + 1):
            connect_timeout = budget.clamped_timeout(CONNECT_TIMEOUT)
            read_timeout = budget.clamped_timeout(READ_TIMEOUT)
            timeout = httpx.Timeout(connect=connect_timeout, read=read_timeout, write=read_timeout, pool=connect_timeout)
            budget.requests_attempted += 1
            try:
                with client.stream('GET', url, timeout=timeout) as stream:
                    if stream.is_redirect:
                        location = stream.headers.get('location', '')
                        stream.close()
                        url = urljoin(url, location)
                        _validate_redirect_target(url, budget)
                        continue
                    if stream.status_code in RETRY_STATUSES:
                        retry_after = _bounded_retry_after(stream.headers.get('retry-after'))
                        last_status = stream.status_code
                        stream.close()
                        if attempt >= MAX_RETRIES:
                            code = 'RATE_LIMITED' if last_status == 429 else 'UPSTREAM_UNAVAILABLE'
                            budget.fail(code, f'Upstream returned {last_status} after retries')
                        attempt += 1
                        budget.retries += 1
                        wait = budget.clamped_timeout(retry_after)
                        time.sleep(wait)
                        continue
                    if stream.status_code >= 400:
                        budget.fail('UPSTREAM_ERROR', f'Upstream returned {stream.status_code}')
                    content_type = stream.headers.get('content-type', '')
                    if not any(t in content_type for t in accept_types):
                        budget.fail('UNEXPECTED_CONTENT_TYPE', 'Response was not the expected content type')
                    try:
                        decoder = _decoder_for(stream.headers.get('content-encoding', ''), MAX_DECODED_BYTES)
                    except TransportError:
                        budget.errors_count += 1
                        raise
                    decoded_chunks = []
                    encoded_size = 0
                    for raw_chunk in stream.iter_raw():
                        if budget.remaining() <= 0:
                            budget.fail('DEADLINE_EXCEEDED', 'Source deadline exceeded mid-stream')
                        encoded_size += len(raw_chunk)
                        if encoded_size > MAX_ENCODED_BYTES:
                            budget.fail('RESPONSE_TOO_LARGE', 'Response exceeded the size cap')
                        try:
                            piece = decoder.feed(raw_chunk) if decoder else raw_chunk
                        except TransportError:
                            budget.errors_count += 1
                            raise
                        decoded_chunks.append(piece)
                    if decoder:
                        try:
                            decoded_chunks.append(decoder.flush())
                        except TransportError:
                            budget.errors_count += 1
                            raise
                    budget.encoded_bytes_read += encoded_size
                    body = b''.join(decoded_chunks)
                    budget.decoded_bytes_read += len(body)
            except httpx.TimeoutException as error:
                budget.fail('TIMEOUT', 'Request timed out', cause=error)
            except httpx.ConnectError as error:
                budget.fail('CONNECT_FAILED', 'Could not connect to the destination', cause=error)
            if budget.remaining() <= 0:
                budget.fail('DEADLINE_EXCEEDED', 'Source deadline exceeded before the response could be used')
            try:
                result = json_module.loads(body)
            except ValueError as error:
                budget.fail('MALFORMED_RESPONSE', 'Response was not valid JSON', cause=error)
            budget.requests_succeeded += 1
            return result
        budget.fail('TOO_MANY_REDIRECTS', 'Too many redirects')
