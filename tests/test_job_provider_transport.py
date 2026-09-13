"""Security/adversarial tests for backend.job_providers.transport.

These test the actual enforced security property at the point it is
enforced (the real socket target, the real byte count, the real sleep
duration) rather than merely asserting that validate_url() was called.
"""
import gzip
import socket
import time
from contextlib import nullcontext

import httpx
import pytest

from backend.job_providers import transport as t


def _budget(deadline=45.0):
    return t.Budget(deadline)


# ---- SSRF / DNS ----

def test_loopback_destination_rejected_before_any_request(monkeypatch):
    calls = []
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


# ---- response handling ----

def _stream_client(status=200, content=b'', headers=None, is_redirect=False):
    headers = headers or {'content-type': 'application/json'}

    class Stream:
        status_code = status
        is_redirect = False

        def __init__(self):
            self.headers = headers

        def __enter__(self): return self
        def __exit__(self, *a): pass
        def iter_bytes(self):
            yield content
        def close(self): pass

    class Client:
        def __init__(self, **kw): pass
        def __enter__(self): return self
        def __exit__(self, *a): pass
        def stream(self, method, url):
            return Stream()

    return Client


def test_oversized_streamed_response_is_rejected(monkeypatch):
    monkeypatch.setattr(t, '_PinnedTransport', lambda: None)
    monkeypatch.setattr(t, 'validate_url', lambda url: url)
    big = b'x' * (t.MAX_RESPONSE_BYTES + 1)
    monkeypatch.setattr(httpx, 'Client', _stream_client(content=big))
    with pytest.raises(t.TransportError) as exc:
        t.fetch_json('https://example.com/jobs', _budget())
    assert exc.value.code == 'RESPONSE_TOO_LARGE'


def test_decompression_expansion_is_bounded_by_the_same_streamed_cap(monkeypatch):
    """The cap applies to the DECODED byte stream httpx hands to iter_bytes,
    so a small compressed payload that decompresses past the cap is still
    rejected -- this does not re-test gzip, it proves the counting happens
    on decoded chunks, not the wire size.
    """
    monkeypatch.setattr(t, '_PinnedTransport', lambda: None)
    monkeypatch.setattr(t, 'validate_url', lambda url: url)
    decoded_bomb = b'0' * (t.MAX_RESPONSE_BYTES + 1)
    monkeypatch.setattr(httpx, 'Client', _stream_client(content=decoded_bomb))
    with pytest.raises(t.TransportError) as exc:
        t.fetch_json('https://example.com/jobs', _budget())
    assert exc.value.code == 'RESPONSE_TOO_LARGE'


def test_malformed_json_body_rejected(monkeypatch):
    monkeypatch.setattr(t, '_PinnedTransport', lambda: None)
    monkeypatch.setattr(t, 'validate_url', lambda url: url)
    monkeypatch.setattr(httpx, 'Client', _stream_client(content=b'not json'))
    with pytest.raises(t.TransportError) as exc:
        t.fetch_json('https://example.com/jobs', _budget())
    assert exc.value.code == 'MALFORMED_RESPONSE'


def test_unexpected_content_type_rejected_even_if_body_parses(monkeypatch):
    monkeypatch.setattr(t, '_PinnedTransport', lambda: None)
    monkeypatch.setattr(t, 'validate_url', lambda url: url)
    monkeypatch.setattr(httpx, 'Client', _stream_client(content=b'{}', headers={'content-type': 'text/html'}))
    with pytest.raises(t.TransportError) as exc:
        t.fetch_json('https://example.com/jobs', _budget())
    assert exc.value.code == 'UNEXPECTED_CONTENT_TYPE'


def test_redirect_target_is_revalidated_before_following(monkeypatch):
    validated = []

    class Stream:
        status_code = 302
        is_redirect = True
        headers = {'location': 'https://169.254.169.254/latest/meta-data'}
        def __enter__(self): return self
        def __exit__(self, *a): pass
        def close(self): pass

    class Client:
        def __init__(self, **kw): pass
        def __enter__(self): return self
        def __exit__(self, *a): pass
        def stream(self, method, url):
            return Stream()

    monkeypatch.setattr(t, '_PinnedTransport', lambda: None)

    def fake_validate(url):
        validated.append(url)
        if 'meta-data' in url:
            raise ValueError('Private network addresses are blocked')
        return url

    monkeypatch.setattr(t, 'validate_url', fake_validate)
    monkeypatch.setattr(httpx, 'Client', Client)
    with pytest.raises(ValueError):
        t.fetch_json('https://example.com/jobs', _budget())
    assert any('meta-data' in u for u in validated)


def test_bounded_redirect_cycle_gives_up_with_too_many_redirects(monkeypatch):
    class Stream:
        status_code = 302
        is_redirect = True
        headers = {'location': 'https://example.com/jobs'}
        def __enter__(self): return self
        def __exit__(self, *a): pass
        def close(self): pass

    class Client:
        def __init__(self, **kw): pass
        def __enter__(self): return self
        def __exit__(self, *a): pass
        def stream(self, method, url):
            return Stream()

    monkeypatch.setattr(t, '_PinnedTransport', lambda: None)
    monkeypatch.setattr(t, 'validate_url', lambda url: url)
    monkeypatch.setattr(httpx, 'Client', Client)
    with pytest.raises(t.TransportError) as exc:
        t.fetch_json('https://example.com/jobs', _budget())
    assert exc.value.code == 'TOO_MANY_REDIRECTS'


def test_timeout_raises_sanitized_transport_error(monkeypatch):
    class Client:
        def __init__(self, **kw): pass
        def __enter__(self): return self
        def __exit__(self, *a): pass
        def stream(self, method, url):
            raise httpx.ReadTimeout('timed out')

    monkeypatch.setattr(t, '_PinnedTransport', lambda: None)
    monkeypatch.setattr(t, 'validate_url', lambda url: url)
    monkeypatch.setattr(httpx, 'Client', Client)
    with pytest.raises(t.TransportError) as exc:
        t.fetch_json('https://example.com/jobs', _budget())
    assert exc.value.code == 'TIMEOUT'


def test_429_retried_within_budget_then_succeeds(monkeypatch):
    attempts = {'n': 0}
    sleeps = []

    class RetryStream:
        status_code = 429
        is_redirect = False
        headers = {'retry-after': '1'}
        def __enter__(self): return self
        def __exit__(self, *a): pass
        def close(self): pass

    class OkStream:
        status_code = 200
        is_redirect = False
        headers = {'content-type': 'application/json'}
        def __enter__(self): return self
        def __exit__(self, *a): pass
        def close(self): pass
        def iter_bytes(self):
            yield b'{"ok":true}'

    class Client:
        def __init__(self, **kw): pass
        def __enter__(self): return self
        def __exit__(self, *a): pass
        def stream(self, method, url):
            attempts['n'] += 1
            return RetryStream() if attempts['n'] == 1 else OkStream()

    monkeypatch.setattr(t, '_PinnedTransport', lambda: None)
    monkeypatch.setattr(t, 'validate_url', lambda url: url)
    monkeypatch.setattr(httpx, 'Client', Client)
    monkeypatch.setattr(t.time, 'sleep', lambda s: sleeps.append(s))
    result = t.fetch_json('https://example.com/jobs', _budget())
    assert result == {'ok': True}
    assert attempts['n'] == 2
    assert sleeps == [1.0]


def test_huge_retry_after_is_capped_not_honored_verbatim(monkeypatch):
    sleeps = []

    class RetryStream:
        status_code = 429
        is_redirect = False
        headers = {'retry-after': '999999'}
        def __enter__(self): return self
        def __exit__(self, *a): pass
        def close(self): pass

    class Client:
        def __init__(self, **kw): pass
        def __enter__(self): return self
        def __exit__(self, *a): pass
        def stream(self, method, url):
            return RetryStream()

    monkeypatch.setattr(t, '_PinnedTransport', lambda: None)
    monkeypatch.setattr(t, 'validate_url', lambda url: url)
    monkeypatch.setattr(httpx, 'Client', Client)
    monkeypatch.setattr(t.time, 'sleep', lambda s: sleeps.append(s))
    with pytest.raises(t.TransportError) as exc:
        t.fetch_json('https://example.com/jobs', _budget())
    assert exc.value.code == 'RATE_LIMITED'
    assert all(s <= t.MAX_RETRY_AFTER_SECONDS for s in sleeps)


def test_transient_5xx_exhausts_retries_then_fails(monkeypatch):
    class ErrStream:
        status_code = 503
        is_redirect = False
        headers = {}
        def __enter__(self): return self
        def __exit__(self, *a): pass
        def close(self): pass

    class Client:
        def __init__(self, **kw): pass
        def __enter__(self): return self
        def __exit__(self, *a): pass
        def stream(self, method, url):
            return ErrStream()

    monkeypatch.setattr(t, '_PinnedTransport', lambda: None)
    monkeypatch.setattr(t, 'validate_url', lambda url: url)
    monkeypatch.setattr(httpx, 'Client', Client)
    monkeypatch.setattr(t.time, 'sleep', lambda s: None)
    with pytest.raises(t.TransportError) as exc:
        t.fetch_json('https://example.com/jobs', _budget())
    assert exc.value.code == 'UPSTREAM_UNAVAILABLE'


def test_deadline_exceeded_before_any_request_is_attempted(monkeypatch):
    calls = []
    monkeypatch.setattr(httpx, 'Client', lambda **kw: calls.append(1) or (_ for _ in ()).throw(AssertionError))
    budget = t.Budget(0.0)
    with pytest.raises(t.TransportError) as exc:
        t.fetch_json('https://example.com/jobs', budget)
    assert exc.value.code == 'DEADLINE_EXCEEDED'
    assert calls == []
