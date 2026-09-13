"""Security/adversarial tests for backend.job_providers.transport.

These test the actual enforced security/resource property at the point it
is enforced (the real socket target, the real peak decompression memory,
the real clamped timeout, the real deadline check between chunks) rather
than merely asserting that validate_url() was called or that some cap
constant exists.
"""
import gzip
import socket
import tracemalloc
import zlib

import httpcore
import httpx
import pytest

from backend.job_providers import transport as t


def _budget(deadline=45.0):
    return t.Budget(deadline)


class FakeStream:
    status_code = 200
    is_redirect = False

    def __init__(self, chunks=(b'{}',), headers=None):
        self._chunks = list(chunks)
        self.headers = headers or {'content-type': 'application/json'}

    def __enter__(self): return self
    def __exit__(self, *a): pass
    def close(self): pass
    def iter_raw(self):
        yield from self._chunks


class FakeClient:
    """A minimal stand-in for httpx.Client that hands back pre-scripted
    FakeStream/exception objects and records the timeout each call was
    made with, so tests can assert on the real clamped value rather than
    just that *some* timeout object was passed.
    """
    def __init__(self, script):
        self._script = list(script)
        self.calls = []

    def __call__(self, **kw):
        return self

    def __enter__(self): return self
    def __exit__(self, *a): pass

    def stream(self, method, url, timeout=None):
        self.calls.append({'url': url, 'timeout': timeout})
        item = self._script.pop(0)
        if isinstance(item, Exception):
            raise item
        return item


def _install(monkeypatch, script):
    monkeypatch.setattr(t, '_PinnedTransport', lambda: None)
    monkeypatch.setattr(t, 'validate_url', lambda url: url)
    client = FakeClient(script)
    monkeypatch.setattr(httpx, 'Client', client)
    return client


# ---- SSRF / DNS ----

def test_loopback_destination_rejected_before_any_request(monkeypatch):
    monkeypatch.setattr(httpx, 'Client', lambda **kw: (_ for _ in ()).throw(AssertionError('should not connect')))
    with pytest.raises(ValueError):
        t.fetch_json('https://127.0.0.1/jobs', _budget())


def test_connect_tcp_dials_the_pinned_resolved_ip_not_the_hostname(monkeypatch):
    """Proves the real security property: the raw socket connects to the
    address _resolve_and_pin() validated, not to whatever httpcore's
    default backend would independently re-resolve the hostname to.
    """
    seen = {}

    def fake_getaddrinfo(host, port, type=None):
        return [(socket.AF_INET, socket.SOCK_STREAM, 6, '', ('93.184.216.34', port))]

    def fake_connect_tcp(self, host, port, timeout=None, local_address=None, socket_options=None):
        seen['host'] = host
        raise t.TransportError('STOP', 'stop before a real socket is opened')

    monkeypatch.setattr(t.socket, 'getaddrinfo', fake_getaddrinfo)
    monkeypatch.setattr(t.httpcore.SyncBackend, 'connect_tcp', fake_connect_tcp)
    backend = t._ValidatedNetworkBackend()
    with pytest.raises(t.TransportError):
        backend.connect_tcp('example.com', 443)
    assert seen['host'] == '93.184.216.34'
    assert seen['host'] != 'example.com'


def test_any_private_address_in_a_mixed_dns_result_blocks_the_destination(monkeypatch):
    def fake_getaddrinfo(host, port, type=None):
        return [
            (socket.AF_INET, socket.SOCK_STREAM, 6, '', ('93.184.216.34', port)),
            (socket.AF_INET, socket.SOCK_STREAM, 6, '', ('10.0.0.5', port)),
        ]
    monkeypatch.setattr(t.socket, 'getaddrinfo', fake_getaddrinfo)
    with pytest.raises(t.TransportError) as exc:
        t._resolve_and_pin('rebinding.example.com', 443)
    assert exc.value.code == 'DESTINATION_BLOCKED'


def test_dns_resolution_failure_is_a_sanitized_transport_error(monkeypatch):
    def fake_getaddrinfo(host, port, type=None):
        raise OSError('no such host')
    monkeypatch.setattr(t.socket, 'getaddrinfo', fake_getaddrinfo)
    with pytest.raises(t.TransportError) as exc:
        t._resolve_and_pin('nxdomain.invalid', 443)
    assert exc.value.code == 'DNS_RESOLUTION_FAILED'


def test_dns_resolution_bounded_to_remaining_timeout(monkeypatch):
    """A real (short) sleep is unavoidable here: this is testing the actual
    timeout-based concurrency primitive (_DNS_EXECUTOR + future.result
    timeout), which cannot be simulated through Budget's own fake-clock
    bookkeeping the way transport-level deadline tests below are.
    """
    import time as real_time

    def slow_getaddrinfo(host, port, type=None):
        real_time.sleep(0.3)
        return [(socket.AF_INET, socket.SOCK_STREAM, 6, '', ('93.184.216.34', port))]

    monkeypatch.setattr(t.socket, 'getaddrinfo', slow_getaddrinfo)
    started = real_time.monotonic()
    with pytest.raises(t.TransportError) as exc:
        t._resolve_and_pin('slow.example.com', 443, timeout=0.02)
    assert exc.value.code == 'DEADLINE_EXCEEDED'
    assert real_time.monotonic() - started < 0.25  # returned promptly, did not wait for the full slow resolution


# ---- response handling ----

def test_oversized_streamed_response_is_rejected(monkeypatch):
    _install(monkeypatch, [FakeStream(chunks=[b'x' * (t.MAX_ENCODED_BYTES + 1)])])
    with pytest.raises(t.TransportError) as exc:
        t.fetch_json('https://example.com/jobs', _budget())
    assert exc.value.code == 'RESPONSE_TOO_LARGE'


def test_malformed_json_body_rejected(monkeypatch):
    _install(monkeypatch, [FakeStream(chunks=[b'not json'])])
    with pytest.raises(t.TransportError) as exc:
        t.fetch_json('https://example.com/jobs', _budget())
    assert exc.value.code == 'MALFORMED_RESPONSE'


def test_unexpected_content_type_rejected_even_if_body_parses(monkeypatch):
    _install(monkeypatch, [FakeStream(chunks=[b'{}'], headers={'content-type': 'text/html'})])
    with pytest.raises(t.TransportError) as exc:
        t.fetch_json('https://example.com/jobs', _budget())
    assert exc.value.code == 'UNEXPECTED_CONTENT_TYPE'


def test_misleading_content_length_does_not_bypass_the_real_byte_count(monkeypatch):
    """The cap is enforced on actual streamed bytes, never on a
    Content-Length header we do not trust."""
    headers = {'content-type': 'application/json', 'content-length': '2'}
    _install(monkeypatch, [FakeStream(chunks=[b'x' * (t.MAX_ENCODED_BYTES + 1)], headers=headers)])
    with pytest.raises(t.TransportError) as exc:
        t.fetch_json('https://example.com/jobs', _budget())
    assert exc.value.code == 'RESPONSE_TOO_LARGE'


class RedirectStream(FakeStream):
    status_code = 302
    is_redirect = True

    def __init__(self, location):
        super().__init__(headers={'location': location})


def test_redirect_target_is_revalidated_and_a_blocked_target_is_typed(monkeypatch):
    _install(monkeypatch, [RedirectStream('https://169.254.169.254/latest/meta-data')])
    validated = []

    def fake_validate(url):
        validated.append(url)
        if 'meta-data' in url:
            raise ValueError('Private network addresses are blocked')
        return url

    monkeypatch.setattr(t, 'validate_url', fake_validate)
    with pytest.raises(t.TransportError) as exc:
        t.fetch_json('https://example.com/jobs', _budget())
    assert exc.value.code == 'POLICY_BLOCKED'
    assert any('meta-data' in u for u in validated)  # the redirect target itself was revalidated


def test_initial_policy_block_is_typed_not_a_raw_valueerror_escaping(monkeypatch):
    monkeypatch.setattr(t, '_PinnedTransport', lambda: None)

    def fake_validate(url):
        raise ValueError('LinkedIn is manual-only. Paste the job description instead.')

    monkeypatch.setattr(t, 'validate_url', fake_validate)
    monkeypatch.setattr(httpx, 'Client', lambda **kw: (_ for _ in ()).throw(AssertionError('should not connect')))
    with pytest.raises(t.TransportError) as exc:
        t.fetch_json('https://www.linkedin.com/jobs/1', _budget())
    assert exc.value.code == 'POLICY_BLOCKED'


def test_bounded_redirect_cycle_gives_up_with_too_many_redirects(monkeypatch):
    script = [RedirectStream('https://example.com/jobs') for _ in range(t.MAX_REDIRECTS + 1)]
    _install(monkeypatch, script)
    with pytest.raises(t.TransportError) as exc:
        t.fetch_json('https://example.com/jobs', _budget())
    assert exc.value.code == 'TOO_MANY_REDIRECTS'


def test_timeout_raises_sanitized_transport_error(monkeypatch):
    _install(monkeypatch, [httpx.ReadTimeout('timed out')])
    with pytest.raises(t.TransportError) as exc:
        t.fetch_json('https://example.com/jobs', _budget())
    assert exc.value.code == 'TIMEOUT'


def test_connect_error_raises_sanitized_transport_error_not_raw_httpx_exception(monkeypatch):
    """Codex F4: httpx.ConnectError (connection refused, TLS handshake
    failure) must not escape the provider/transport contract."""
    _install(monkeypatch, [httpx.ConnectError('connection refused')])
    with pytest.raises(t.TransportError) as exc:
        t.fetch_json('https://example.com/jobs', _budget())
    assert exc.value.code == 'CONNECT_FAILED'


def test_429_retried_within_budget_then_succeeds(monkeypatch):
    sleeps = []
    retry_stream = type('S', (FakeStream,), {'status_code': 429, 'headers': {'retry-after': '1'}})
    _install(monkeypatch, [retry_stream(), FakeStream(chunks=[b'{"ok":true}'])])
    monkeypatch.setattr(t.time, 'sleep', lambda s: sleeps.append(s))
    result = t.fetch_json('https://example.com/jobs', _budget())
    assert result == {'ok': True}
    assert sleeps == [1.0]


def test_huge_retry_after_is_capped_not_honored_verbatim(monkeypatch):
    sleeps = []
    retry_stream = type('S', (FakeStream,), {'status_code': 429, 'headers': {'retry-after': '999999'}})
    _install(monkeypatch, [retry_stream(), retry_stream(), retry_stream()])
    monkeypatch.setattr(t.time, 'sleep', lambda s: sleeps.append(s))
    with pytest.raises(t.TransportError) as exc:
        t.fetch_json('https://example.com/jobs', _budget())
    assert exc.value.code == 'RATE_LIMITED'
    assert all(s <= t.MAX_RETRY_AFTER_SECONDS for s in sleeps)


def test_transient_5xx_exhausts_retries_then_fails(monkeypatch):
    err_stream = type('S', (FakeStream,), {'status_code': 503, 'headers': {}})
    _install(monkeypatch, [err_stream(), err_stream(), err_stream()])
    monkeypatch.setattr(t.time, 'sleep', lambda s: None)
    with pytest.raises(t.TransportError) as exc:
        t.fetch_json('https://example.com/jobs', _budget())
    assert exc.value.code == 'UPSTREAM_UNAVAILABLE'


# ---- F1: the source deadline is a real upper bound ----

def test_deadline_exceeded_before_any_request_is_attempted(monkeypatch):
    monkeypatch.setattr(httpx, 'Client', lambda **kw: (_ for _ in ()).throw(AssertionError))
    budget = t.Budget(0.0)
    with pytest.raises(t.TransportError) as exc:
        t.fetch_json('https://example.com/jobs', budget)
    assert exc.value.code == 'DEADLINE_EXCEEDED'


def test_request_timeout_is_clamped_to_remaining_budget_not_the_full_default(monkeypatch):
    client = _install(monkeypatch, [FakeStream()])
    budget = t.Budget(2.0)  # far below CONNECT_TIMEOUT/READ_TIMEOUT defaults
    t.fetch_json('https://example.com/jobs', budget)
    used_timeout = client.calls[0]['timeout']
    assert used_timeout.connect <= 2.0
    assert used_timeout.read <= 2.0


def test_deadline_expiring_mid_stream_aborts_before_returning_success(monkeypatch):
    """Reproduces Codex's exact class of finding without any real sleep:
    a Budget whose deadline (backed by real time.monotonic) is
    artificially forced to look expired partway through consuming
    iter_raw()'s chunks, proving the loop checks between chunks rather
    than only before the request starts.
    """
    class SlowStream(FakeStream):
        def __init__(self):
            super().__init__()

        def iter_raw(self):
            yield b'{"partial":'
            budget.deadline = 0  # simulate the deadline having passed mid-stream
            yield b'"never delivered"}'

    _install(monkeypatch, [SlowStream()])
    budget = _budget()
    with pytest.raises(t.TransportError) as exc:
        t.fetch_json('https://example.com/jobs', budget)
    assert exc.value.code == 'DEADLINE_EXCEEDED'


def test_result_is_not_returned_as_success_if_deadline_passed_during_final_parse(monkeypatch):
    class SlowStream(FakeStream):
        def iter_raw(self):
            yield b'{"ok":true}'
            budget.deadline = 0  # expires after the last chunk, before parsing completes

    _install(monkeypatch, [SlowStream()])
    budget = _budget()
    with pytest.raises(t.TransportError) as exc:
        t.fetch_json('https://example.com/jobs', budget)
    assert exc.value.code == 'DEADLINE_EXCEEDED'


def test_retry_sequence_cannot_extend_past_the_deadline(monkeypatch):
    retry_stream = type('S', (FakeStream,), {'status_code': 429, 'headers': {'retry-after': '5'}})
    client = _install(monkeypatch, [retry_stream(), retry_stream()])
    budget = _budget()
    slept = []

    def fake_sleep(seconds):
        slept.append(seconds)
        budget.deadline = 0  # the wait itself consumed the remaining deadline

    monkeypatch.setattr(t.time, 'sleep', fake_sleep)
    with pytest.raises(t.TransportError) as exc:
        t.fetch_json('https://example.com/jobs', budget)
    assert exc.value.code == 'DEADLINE_EXCEEDED'
    assert len(client.calls) == 1  # never attempted a second request past the deadline


# ---- F2: bounded incremental decompression through the real transport path ----

def test_small_valid_gzip_decodes_correctly(monkeypatch):
    body = gzip.compress(b'{"jobs": []}')
    headers = {'content-type': 'application/json', 'content-encoding': 'gzip'}
    _install(monkeypatch, [FakeStream(chunks=[body], headers=headers)])
    assert t.fetch_json('https://example.com/jobs', _budget()) == {'jobs': []}


def test_chunked_compressed_response_reassembles_correctly(monkeypatch):
    payload = b'{"jobs": [' + b','.join([b'{"id":%d}' % i for i in range(50)]) + b']}'
    compressed = gzip.compress(payload)
    mid = len(compressed) // 2
    headers = {'content-type': 'application/json', 'content-encoding': 'gzip'}
    _install(monkeypatch, [FakeStream(chunks=[compressed[:mid], compressed[mid:]], headers=headers)])
    result = t.fetch_json('https://example.com/jobs', _budget())
    assert len(result['jobs']) == 50


def test_invalid_compressed_body_is_rejected(monkeypatch):
    headers = {'content-type': 'application/json', 'content-encoding': 'gzip'}
    _install(monkeypatch, [FakeStream(chunks=[b'this is not gzip data at all'], headers=headers)])
    with pytest.raises(t.TransportError) as exc:
        t.fetch_json('https://example.com/jobs', _budget())
    assert exc.value.code == 'MALFORMED_RESPONSE'


def test_unsupported_content_encoding_is_rejected(monkeypatch):
    headers = {'content-type': 'application/json', 'content-encoding': 'br'}
    _install(monkeypatch, [FakeStream(chunks=[b'anything'], headers=headers)])
    with pytest.raises(t.TransportError) as exc:
        t.fetch_json('https://example.com/jobs', _budget())
    assert exc.value.code == 'UNSUPPORTED_ENCODING'


def test_compression_bomb_rejected_without_materializing_the_full_expansion(monkeypatch):
    """Real gzip input through the real decompression path, sized so the
    decoded output would be far larger than the cap (Codex reproduced
    ~19KB -> ~20MB -> ~50MB peak). tracemalloc proves the cap engages
    without the process ever holding anywhere near the full decoded size
    in memory at once.
    """
    decoded_size = t.MAX_DECODED_BYTES * 4
    compressed = gzip.compress(b'0' * decoded_size)
    assert len(compressed) < 100_000  # highly compressible, a small wire payload
    headers = {'content-type': 'application/json', 'content-encoding': 'gzip'}
    _install(monkeypatch, [FakeStream(chunks=[compressed], headers=headers)])

    tracemalloc.start()
    try:
        with pytest.raises(t.TransportError) as exc:
            t.fetch_json('https://example.com/jobs', _budget())
        _, peak = tracemalloc.get_traced_memory()
    finally:
        tracemalloc.stop()
    assert exc.value.code == 'RESPONSE_TOO_LARGE'
    # Peak stays within a small multiple of the cap, nowhere near the ~4x-cap
    # decoded size the bomb would expand to if fully materialized first.
    assert peak < t.MAX_DECODED_BYTES * 2


def test_bounded_decoder_rejects_output_exceeding_cap_incrementally():
    decoder = t._BoundedDecoder(zlib.MAX_WBITS | 16, cap=100)
    compressed = gzip.compress(b'x' * 1000)
    with pytest.raises(t.TransportError) as exc:
        for i in range(0, len(compressed), 16):
            decoder.feed(compressed[i:i + 16])
    assert exc.value.code == 'RESPONSE_TOO_LARGE'


# ---- F6: request/retry/byte counters ----

def test_metrics_count_attempts_and_successes_separately(monkeypatch):
    _install(monkeypatch, [FakeStream(chunks=[b'{"ok":true}'])])
    budget = _budget()
    t.fetch_json('https://example.com/jobs', budget)
    assert budget.requests_attempted == 1
    assert budget.requests_succeeded == 1


def test_metrics_retain_attempt_and_error_counts_on_failure(monkeypatch):
    _install(monkeypatch, [httpx.ConnectError('refused')])
    budget = _budget()
    with pytest.raises(t.TransportError):
        t.fetch_json('https://example.com/jobs', budget)
    assert budget.requests_attempted == 1
    assert budget.requests_succeeded == 0
    assert budget.errors_count == 1


def test_metrics_distinguish_encoded_from_decoded_bytes(monkeypatch):
    payload = b'{"jobs": []}'
    compressed = gzip.compress(payload)
    headers = {'content-type': 'application/json', 'content-encoding': 'gzip'}
    _install(monkeypatch, [FakeStream(chunks=[compressed], headers=headers)])
    budget = _budget()
    t.fetch_json('https://example.com/jobs', budget)
    assert budget.encoded_bytes_read == len(compressed)
    assert budget.decoded_bytes_read == len(payload)
    assert budget.encoded_bytes_read != budget.decoded_bytes_read


# ---- transport dependency pin (Codex note) ----

def test_transport_dependency_versions_are_pinned():
    """Fails loudly on an httpx/httpcore upgrade so the DNS-pinning/TLS
    assumptions documented in transport.py's module docstring (private
    httpx.HTTPTransport._pool attribute; server_hostname derived from the
    connection's origin, not from connect_tcp()'s target) get re-verified
    against the new version rather than silently drifting.
    """
    assert httpx.__version__ == t.PINNED_HTTPX_VERSION, (
        f'httpx upgraded to {httpx.__version__}; re-verify _PinnedTransport against '
        'the new internals before updating PINNED_HTTPX_VERSION.'
    )
    assert httpcore.__version__ == t.PINNED_HTTPCORE_VERSION, (
        f'httpcore upgraded to {httpcore.__version__}; re-verify _ValidatedNetworkBackend '
        'against the new internals before updating PINNED_HTTPCORE_VERSION.'
    )
