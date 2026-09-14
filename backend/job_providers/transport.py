"""Centralized, policy-bound outbound transport for job-discovery providers.

Every provider fetch goes through `fetch_json` here rather than inventing
its own timeouts, redirect handling, or size caps -- the same rule ADR-0009
requires for every adapter.

DNS-rebinding note: this module is the ONLY place that resolves DNS for a
provider fetch. `backend.policy.validate_url()` is called with
`resolve=False` here -- it still enforces every *structural* policy check
(HTTPS-only, no credentials, no LinkedIn, fixed port) without touching the
network, so a slow/hostile DNS server can never make that call block past
the source deadline. The actual (bounded, deadline-aware) DNS resolution
and private/loopback/link-local rejection happens exactly once, in
`_resolve_and_pin`, called from `_ValidatedNetworkBackend.connect_tcp` --
the real point of connection -- closing the TOCTOU gap a separate
pre-flight `getaddrinfo()` call would otherwise leave between validation
and httpx/httpcore's own independent connect-time resolution. TLS SNI and
certificate verification are unaffected: httpcore derives `server_hostname`
from the connection's origin (the real hostname), never from what
`connect_tcp()` was asked to dial, so pinning the socket target never
weakens hostname verification.

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
import queue
import socket
import ssl
import threading
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

DNS_MAX_WORKERS = 4
DNS_MAX_PENDING = 16  # workers + a bounded backlog; never an unbounded queue

class _DNSResolver:
    """Fixed daemon workers and a physically bounded backlog.

    Cancelled jobs remain in this bounded queue until a worker discards
    them. No cancellation callback grants extra queue capacity. Active OS
    lookups cannot be interrupted; at most four can remain stuck. Daemon
    workers do not prevent process exit. close() is for bounded fixture
    cleanup, not an attempt to cancel running OS calls.
    """
    def __init__(self):
        self.queue = queue.Queue(maxsize=DNS_MAX_PENDING - DNS_MAX_WORKERS)
        self._closed = threading.Event()
        self._submit_lock = threading.Lock()
        self.workers = [threading.Thread(target=self._worker, daemon=True,
                        name=f'job-provider-dns-{i}') for i in range(DNS_MAX_WORKERS)]
        for worker in self.workers:
            worker.start()

    def submit(self, function, *args, **kwargs):
        future = concurrent.futures.Future()
        with self._submit_lock:
            if self._closed.is_set():
                raise RuntimeError('DNS resolver is closed')
            try:
                self.queue.put_nowait((future, function, args, kwargs))
            except queue.Full:
                raise TransportError('DNS_QUEUE_SATURATED', 'Too many DNS resolutions are already pending') from None
        return future

    def _worker(self):
        while not self._closed.is_set() or not self.queue.empty():
            try:
                future, function, args, kwargs = self.queue.get(timeout=0.1)
            except queue.Empty:
                continue
            try:
                if future.set_running_or_notify_cancel():
                    try:
                        result = function(*args, **kwargs)
                    except BaseException as error:
                        # Preserve worker exceptions for the caller, including
                        # programmer bugs; do not classify them as network errors.
                        future.set_exception(error)
                    else:
                        future.set_result(result)
            finally:
                self.queue.task_done()

    def close(self):
        with self._submit_lock:
            self._closed.set()
        for worker in self.workers:
            worker.join(timeout=0.2)


_DNS_RESOLVER = _DNSResolver()


class TransportError(ValueError):
    """Sanitized transport failure. `code` is safe to log/report; `message`
    never embeds raw upstream payloads, headers, or URLs with query data.
    """
    def __init__(self, code, message, *, counted=False):
        super().__init__(message)
        self.code = code
        self.counted = counted


class Budget:
    """Mutable counters and a wall-clock deadline shared across every
    request one provider fetch makes (list and detail calls alike, since
    callers thread the same Budget through every fetch_json() call), so a
    single source can never exceed its own request/byte/time budget no
    matter how many calls it issues, and the deadline is a real upper
    bound on the whole operation rather than just a between-calls check.

    Byte/error counters are incremented as data actually arrives, not
    only once a request fully succeeds, so a response that is rejected
    partway through (oversized, malformed, deadline hit) still leaves a
    truthful record of what was actually read before the rejection.
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
            self.fail('DEADLINE_EXCEEDED', 'Source deadline exceeded')

    def clamped_timeout(self, cap):
        """Raises if the deadline has already passed; otherwise returns a
        timeout no larger than both `cap` and whatever time is left, so no
        single blocking operation can outlive the source's own deadline.
        """
        remaining = self.remaining()
        if remaining <= 0:
            self.fail('DEADLINE_EXCEEDED', 'Source deadline exceeded')
        return min(cap, remaining)

    def record_error(self, error):
        """Count an external failure once as it crosses nested boundaries."""
        if not error.counted:
            self.errors_count += 1
            error.counted = True

    def fail(self, code, message, cause=None):
        """The single point every typed failure raises through, so
        errors_count increments exactly once per logical failure no
        matter which layer (transport, decoder) detects it.
        """
        self.errors_count += 1
        raise TransportError(code, message, counted=True) from cause


def _resolve_and_pin(host, port, timeout=None):
    """Resolves `host` and validates every returned address is global,
    bounded to `timeout` seconds via a bounded-admission thread pool (see
    module docstring / B3): a fixed number of workers plus a fixed
    backlog, never an unbounded queue -- once both are full, resolution
    fails fast and typed instead of piling up more pending work or
    blocking the caller indefinitely trying to submit it.

    Python's socket.getaddrinfo() cannot be force-cancelled. Running
    lookups occupy one of four workers until they finish. Cancelled queued
    jobs stay in the fixed-capacity physical queue until discarded; they
    never grant capacity while still retaining queue memory.
    """
    future = _DNS_RESOLVER.submit(socket.getaddrinfo, host, port, type=socket.SOCK_STREAM)
    try:
        infos = future.result(timeout=timeout)
    except concurrent.futures.TimeoutError:
        future.cancel()  # best-effort: only takes effect if it hasn't started running yet
        raise TransportError('DEADLINE_EXCEEDED', 'DNS resolution exceeded the remaining source deadline')
    except OSError as error:
        raise TransportError('DNS_FAILURE', 'Destination could not be resolved') from error
    addresses = [info[4][0] for info in infos]
    if not addresses:
        raise TransportError('DNS_FAILURE', 'Destination could not be resolved')
    for address in addresses:
        if not ipaddress.ip_address(address).is_global:
            raise TransportError('DESTINATION_BLOCKED', 'Private network addresses are blocked')
    return addresses[0]


class _DeadlineStream(httpcore.NetworkStream):
    """Refresh the absolute budget at each actual read, write and TLS step.

    This includes HTTPcore's repeated reads while assembling response
    headers. HTTPX inactivity timeouts alone cannot bound those reads.
    """
    def __init__(self, inner, budget):
        self._inner = inner
        self._budget = budget

    def _timeout(self, timeout):
        return self._budget.clamped_timeout(timeout if timeout is not None else float('inf'))

    def read(self, max_bytes, timeout=None):
        try:
            result = self._inner.read(max_bytes, timeout=self._timeout(timeout))
        except httpcore.ReadTimeout:
            self._budget.check()
            raise
        self._budget.check()
        return result

    def write(self, buffer, timeout=None):
        # Both HTTPcore SyncStream.write and Python SSLSocket.sendall can
        # loop over partial sends with one unchanged timeout. Refresh it
        # ourselves before every actual socket/SSL write.
        sock = self._inner.get_extra_info('socket')
        try:
            with memoryview(buffer) as view:
                sent = 0
                while sent < len(view):
                    sock.settimeout(self._timeout(timeout))
                    count = sock.send(view[sent:])
                    if count == 0:
                        raise httpcore.WriteError('Connection made no write progress')
                    sent += count
        except socket.timeout as error:
            self._budget.check()
            raise httpcore.WriteTimeout('Write timed out') from error
        except OSError as error:
            raise httpcore.WriteError('Write failed') from error
        self._budget.check()

    def start_tls(self, ssl_context, server_hostname=None, timeout=None):
        try:
            inner = self._inner.start_tls(ssl_context, server_hostname=server_hostname,
                                          timeout=self._timeout(timeout))
        except httpcore.ConnectTimeout:
            self._budget.check()
            raise
        if self._budget.remaining() <= 0:
            inner.close()
            self._budget.check()
        return _DeadlineStream(inner, self._budget)

    def close(self):
        self._inner.close()

    def get_extra_info(self, info):
        return self._inner.get_extra_info(info)


class _ValidatedNetworkBackend(httpcore.NetworkBackend):
    def __init__(self, budget=None):
        self._inner = httpcore.SyncBackend()
        self._budget = budget

    def connect_tcp(self, host, port, timeout=None, local_address=None, socket_options=None):
        if self._budget is not None:
            timeout = self._budget.clamped_timeout(timeout if timeout is not None else CONNECT_TIMEOUT)
        started = time.monotonic()
        pinned = _resolve_and_pin(host, port, timeout=timeout)
        if timeout is not None:
            remaining = timeout - (time.monotonic() - started)
            if remaining <= 0:
                raise TransportError('DEADLINE_EXCEEDED', 'Source deadline exceeded during DNS resolution')
            timeout = remaining
        stream = self._inner.connect_tcp(pinned, port, timeout=timeout, local_address=local_address, socket_options=socket_options)
        if self._budget is None:
            return stream
        if self._budget.remaining() <= 0:
            stream.close()
            self._budget.check()
        return _DeadlineStream(stream, self._budget)

    def connect_unix_socket(self, path, timeout=None, socket_options=None):
        raise TransportError('UNSUPPORTED_TRANSPORT', 'Unix sockets are never used for provider fetches')

    def sleep(self, seconds):
        self._inner.sleep(seconds)


class _PinnedTransport(httpx.HTTPTransport):
    def __init__(self, budget):
        self._pool = httpcore.ConnectionPool(
            ssl_context=ssl.create_default_context(),
            network_backend=_ValidatedNetworkBackend(budget),
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
    """Incrementally decompresses at most `cap` decoded bytes total from a
    SINGLE compressed member, raising the moment that is exceeded -- never
    decompressing a whole payload into memory before checking its size.
    `zlib.decompressobj`'s `max_length` argument bounds how much a single
    decompress() call can return, so a small compressed input that would
    expand into a huge output is caught after at most one
    DECOMPRESS_CHUNK-sized burst past the cap, not after materializing the
    full expansion.

    Explicit state machine (Codex B2): once the wrapped stream reports
    `eof`, decoding stops for good -- concatenated members and trailing
    garbage after the first member are rejected outright (Option A) rather
    than re-fed into a decompressor that has already finished, which is
    what caused the original zero-progress infinite loop (repeatedly
    re-decompressing stale unconsumed_tail state after eof). A truncated
    stream (input exhausted without ever reaching eof) is rejected by
    flush(). Every inner iteration must make progress (consume input or
    produce output or reach eof); zero-progress is detected and rejected
    rather than looped on.
    """
    def __init__(self, wbits, cap, budget):
        try:
            self._z = zlib.decompressobj(wbits)
        except zlib.error as error:
            budget.fail('DECODE_FAILED', 'Unsupported compression parameters', cause=error)
        self._cap = cap
        self._budget = budget
        self._total = 0
        self._finished = False

    def _accumulate(self, piece):
        """Counts bytes as they are produced, before deciding pass/fail
        (Codex B6.1): a piece that pushes the total over the cap was
        still real memory the decompressor allocated, and the caller
        that raises here never gets a return value from feed()/flush()
        to count it from -- so it must be counted here, immediately.
        """
        if piece:
            self._total += len(piece)
            self._budget.decoded_bytes_read += len(piece)
            if self._total > self._cap:
                self._budget.fail('RESPONSE_TOO_LARGE', 'Decoded response exceeded the size cap')

    def feed(self, data):
        if self._finished:
            if data:
                self._budget.fail('DECODE_FAILED', 'Unexpected trailing data after the compressed stream ended')
            return b''
        collected = bytearray()
        pending = data
        try:
            while True:
                self._budget.check()
                before = len(pending)
                piece = self._z.decompress(pending, DECOMPRESS_CHUNK)
                self._accumulate(piece)
                collected.extend(piece)
                tail = self._z.unconsumed_tail
                if self._z.eof:
                    self._finished = True
                    if tail or self._z.unused_data:
                        self._budget.fail('DECODE_FAILED', 'Unexpected trailing data after the compressed stream ended')
                    break
                if not tail:
                    break
                if not piece and len(tail) >= before:
                    self._budget.fail('DECODE_FAILED', 'Compressed stream made no decoding progress')
                pending = tail
        except zlib.error as error:
            self._budget.fail('DECODE_FAILED', 'Response could not be decompressed', cause=error)
        return bytes(collected)

    def flush(self):
        if self._finished:
            return b''
        try:
            piece = self._z.flush(DECOMPRESS_CHUNK)
        except zlib.error as error:
            self._budget.fail('DECODE_FAILED', 'Response could not be decompressed', cause=error)
        self._accumulate(piece)
        if not self._z.eof:
            self._budget.fail('DECODE_FAILED', 'Compressed stream ended unexpectedly (truncated)')
        return piece


def _decoder_for(content_encoding, cap, budget):
    encoding = (content_encoding or '').strip().lower()
    if encoding in ('', 'identity'):
        return None
    if encoding == 'gzip':
        return _BoundedDecoder(zlib.MAX_WBITS | 16, cap, budget)
    if encoding == 'deflate':
        return _BoundedDecoder(zlib.MAX_WBITS, cap, budget)
    budget.fail('UNSUPPORTED_CONTENT_ENCODING', 'Unsupported content-encoding')


def _validate_structural(url, budget):
    """Structural/policy checks only (scheme, credentials, port, LinkedIn)
    -- never resolves DNS. See module docstring: DNS resolution and
    private-network rejection happen exactly once, in _resolve_and_pin,
    at actual connect time.
    """
    try:
        validate_url(url, resolve=False)
    except ValueError as error:
        budget.fail('POLICY_BLOCKED', str(error), cause=error)


def _resolve_redirect(url, location, budget):
    try:
        return urljoin(url, location)
    except ValueError as error:
        budget.fail('INVALID_REDIRECT', 'Redirect target could not be parsed', cause=error)


def fetch_json(url, budget, accept_types=('application/json',)):
    """Fetch JSON, counting each typed external failure exactly once."""
    try:
        return _fetch_json(url, budget, accept_types)
    except TransportError as error:
        budget.record_error(error)
        raise


def _fetch_json(url, budget, accept_types):
    """Fetch one URL under `budget`, following bounded redirects
    (revalidated against policy.py on every hop), enforcing a decoded-size
    cap via bounded incremental decompression (never decompressing a full
    payload before checking its size), and retrying transient failures a
    bounded number of times with a capped Retry-After wait.

    The pinned network stream refreshes remaining absolute time on each
    read/write/TLS operation, including reads of partial response headers.
    DNS and TCP consume the same source Budget. Parsing is checked before
    and after, and retries/details never reset the deadline.

    Returns parsed JSON or raises TransportError -- this never lets an
    un-typed exception (DNS failure, connection refused, TLS failure, a
    protocol error, a blocked-redirect ValueError from policy.py) escape
    uncaught.
    """
    budget.check()
    _validate_structural(url, budget)
    attempt = 0
    with httpx.Client(
        transport=_PinnedTransport(budget),
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
            budget.check()
            # Phase caps remain useful, but the network stream enforces
            # the shrinking absolute deadline within each phase.
            connect_timeout = budget.clamped_timeout(CONNECT_TIMEOUT)
            read_timeout = budget.clamped_timeout(READ_TIMEOUT)
            if connect_timeout <= 0 or read_timeout <= 0:
                budget.fail('DEADLINE_EXCEEDED', 'Source deadline exceeded')
            timeout = httpx.Timeout(connect=connect_timeout, read=read_timeout, write=read_timeout, pool=connect_timeout)
            budget.requests_attempted += 1
            try:
                with client.stream('GET', url, timeout=timeout) as stream:
                    if stream.is_redirect:
                        location = stream.headers.get('location', '')
                        stream.close()
                        url = _resolve_redirect(url, location, budget)
                        _validate_structural(url, budget)
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
                    decoder = _decoder_for(stream.headers.get('content-encoding', ''), MAX_DECODED_BYTES, budget)
                    request_encoded_size = 0
                    decoded_chunks = []
                    for raw_chunk in stream.iter_raw():
                        request_encoded_size += len(raw_chunk)
                        budget.encoded_bytes_read += len(raw_chunk)
                        if decoder is None:
                            budget.decoded_bytes_read += len(raw_chunk)
                        if budget.remaining() <= 0:
                            budget.fail('DEADLINE_EXCEEDED', 'Source deadline exceeded mid-stream')
                        if request_encoded_size > MAX_ENCODED_BYTES:
                            budget.fail('RESPONSE_TOO_LARGE', 'Response exceeded the size cap')
                        if decoder:
                            # _BoundedDecoder.feed() increments
                            # budget.decoded_bytes_read itself, as each
                            # small piece is produced -- including the
                            # final over-cap piece right before it raises,
                            # which a return-value-based increment here
                            # would never see (Codex B6.1).
                            piece = decoder.feed(raw_chunk)
                        else:
                            piece = raw_chunk
                        decoded_chunks.append(piece)
                    if decoder:
                        decoded_chunks.append(decoder.flush())
                    body = b''.join(decoded_chunks)
            except httpx.ConnectTimeout as error:
                budget.fail('CONNECT_TIMEOUT', 'Connection timed out', cause=error)
            except httpx.ReadTimeout as error:
                budget.fail('READ_TIMEOUT', 'Read timed out', cause=error)
            except httpx.WriteTimeout as error:
                budget.fail('WRITE_TIMEOUT', 'Write timed out', cause=error)
            except httpx.TimeoutException as error:
                budget.fail('READ_TIMEOUT', 'Request timed out', cause=error)
            except httpx.ConnectError as error:
                budget.fail('CONNECT_FAILED', 'Could not connect to the destination', cause=error)
            except httpx.ReadError as error:
                budget.fail('READ_FAILED', 'Connection failed while reading the response', cause=error)
            except httpx.WriteError as error:
                budget.fail('WRITE_FAILED', 'Connection failed while writing the request', cause=error)
            except (httpx.InvalidURL, UnicodeError) as error:
                budget.fail('INVALID_EXTERNAL_URL', 'External URL could not be parsed', cause=error)
            except httpx.RemoteProtocolError as error:
                budget.fail('REMOTE_PROTOCOL_ERROR', 'The server violated the HTTP protocol', cause=error)
            except httpx.DecodingError as error:
                budget.fail('DECODE_FAILED', 'Response could not be decoded', cause=error)
            if budget.remaining() <= 0:
                budget.fail('DEADLINE_EXCEEDED', 'Source deadline exceeded before the response could be used')
            try:
                result = json_module.loads(body)
            except ValueError as error:
                budget.fail('INVALID_JSON', 'Response was not valid JSON', cause=error)
            if budget.remaining() <= 0:
                budget.fail('DEADLINE_EXCEEDED', 'Source deadline exceeded after parsing the response')
            budget.requests_succeeded += 1
            return result
        budget.fail('TOO_MANY_REDIRECTS', 'Too many redirects')
