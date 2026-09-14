"""Regressions for the final, narrowly scoped PR #53 remediation."""
import gzip
import socket
import ssl

import httpcore
import httpx
import pytest

from backend.job_providers import greenhouse as g, transport as t
from backend.job_providers.contracts import FetchContext


class Raw(httpx.SyncByteStream):
    def __init__(self, chunks):
        self.chunks = chunks

    def __iter__(self):
        yield from self.chunks


def response(body=b'{}', **kwargs):
    return httpx.Response(200, headers={'content-type': 'application/json',
                                      **kwargs}, stream=Raw([body]))


def install(monkeypatch, handler):
    monkeypatch.setattr(t, '_PinnedTransport', lambda budget: httpx.MockTransport(handler))


def test_slow_headers_obey_absolute_deadline_through_httpcore(monkeypatch):
    # The real HTTPX/HTTPcore header parser sees 40ms byte drips. Only the
    # socket clock is simulated: no sleeps, public DNS, or timing races.
    clock = [0.0]
    monkeypatch.setattr(t.time, 'monotonic', lambda: clock[0])
    budget = t.Budget(0.2)
    reads = []
    seen = {}

    class Sock:
        def settimeout(self, timeout):
            assert 0 < timeout <= budget.remaining()

        def send(self, data):
            seen['request'] = seen.get('request', b'') + bytes(data)
            clock[0] += 0.005
            return len(data)

    class Stream(httpcore.NetworkStream):
        def read(self, max_bytes, timeout=None):
            reads.append(timeout)
            assert len(reads) < 20, 'Absolute deadline did not interrupt header drips'
            if timeout < 0.04:
                clock[0] += timeout
                raise httpcore.ReadTimeout('fixture timeout')
            clock[0] += 0.04
            return b'HTTP/1.1 200 OK\r\nX-Slow: ' if len(reads) == 1 else b'a'

        def start_tls(self, ssl_context, server_hostname=None, timeout=None):
            assert ssl_context.check_hostname
            assert ssl_context.verify_mode == ssl.CERT_REQUIRED
            seen['sni'] = server_hostname
            clock[0] += 0.01
            return self

        def close(self):
            pass

        def get_extra_info(self, info):
            return Sock() if info == 'socket' else None

    monkeypatch.setattr(t, '_resolve_and_pin', lambda *a, **kw: '93.184.216.34')
    def connect(self, host, port, **kwargs):
        assert host == '93.184.216.34'
        return Stream()
    monkeypatch.setattr(httpcore.SyncBackend, 'connect_tcp', connect)
    with pytest.raises(t.TransportError) as exc:
        t.fetch_json('https://example.com/jobs', budget)
    assert exc.value.code == 'DEADLINE_EXCEEDED'
    assert clock[0] == pytest.approx(0.2)
    assert reads[-1] < reads[0]
    assert seen['sni'] == 'example.com'
    assert b'Host: example.com' in seen['request']
    assert budget.errors_count == 1


def test_partial_socket_writes_refresh_the_absolute_deadline(monkeypatch):
    clock = [0.0]
    monkeypatch.setattr(t.time, 'monotonic', lambda: clock[0])
    budget = t.Budget(0.2)
    caps = []
    class Sock:
        def settimeout(self, timeout):
            caps.append(timeout)
        def send(self, buffer):
            if caps[-1] < 0.04:
                clock[0] += caps[-1]
                raise socket.timeout()
            clock[0] += 0.04
            return 1
    class Inner:
        def get_extra_info(self, name):
            return Sock()
    with pytest.raises(t.TransportError) as exc:
        t._DeadlineStream(Inner(), budget).write(b'x' * 100, timeout=1)
    assert exc.value.code == 'DEADLINE_EXCEEDED'
    assert clock[0] == pytest.approx(0.2)
    assert caps[-1] < caps[0]
    assert budget.errors_count == 1


def test_successful_network_read_that_crosses_deadline_is_rejected(monkeypatch):
    clock = [0.0]
    monkeypatch.setattr(t.time, 'monotonic', lambda: clock[0])
    budget = t.Budget(0.2)
    class Inner:
        def read(self, max_bytes, timeout=None):
            assert timeout == pytest.approx(0.2)
            clock[0] = 0.2
            return b'late'
    with pytest.raises(t.TransportError) as exc:
        t._DeadlineStream(Inner(), budget).read(100, timeout=1)
    assert exc.value.code == 'DEADLINE_EXCEEDED'
    assert budget.errors_count == 1


@pytest.mark.parametrize('error,code', [
    (httpx.WriteError('private diagnostic'), 'WRITE_FAILED'),
    (httpx.WriteTimeout('private diagnostic'), 'WRITE_TIMEOUT'),
    (httpx.ReadError('private diagnostic'), 'READ_FAILED'),
    (httpx.RemoteProtocolError('private diagnostic'), 'REMOTE_PROTOCOL_ERROR'),
])
def test_external_failures_are_sanitized_and_counted_once(monkeypatch, error, code):
    def handler(request):
        raise error
    install(monkeypatch, handler)
    budget = t.Budget(2)
    with pytest.raises(t.TransportError) as exc:
        t.fetch_json('https://example.com', budget)
    assert exc.value.code == code
    assert 'private' not in str(exc.value)
    assert budget.errors_count == 1


def test_invalid_idna_redirect_is_typed(monkeypatch):
    install(monkeypatch, lambda request: httpx.Response(
        302, headers={'location': 'https://xn--/jobs'}, stream=Raw([])))
    budget = t.Budget(2)
    with pytest.raises(t.TransportError) as exc:
        t.fetch_json('https://example.com', budget)
    assert exc.value.code == 'INVALID_EXTERNAL_URL'
    assert budget.errors_count == 1


@pytest.mark.parametrize('bug', [AssertionError, TypeError])
def test_programmer_errors_still_surface(monkeypatch, bug):
    def handler(request):
        raise bug('implementation failure')
    install(monkeypatch, handler)
    with pytest.raises(bug):
        g.GreenhouseProvider().fetch(FetchContext(), 'fixture')


def test_dns_and_initial_deadline_failures_count_once(monkeypatch):
    def broken(*args, **kwargs):
        raise socket.gaierror('private resolver diagnostic')
    monkeypatch.setattr(socket, 'getaddrinfo', broken)
    batch = g.GreenhouseProvider().fetch(FetchContext(), 'fixture')
    assert batch.error.code == 'DNS_FAILURE'
    assert batch.metrics.errors_count == 1
    batch = g.GreenhouseProvider().fetch(FetchContext(deadline_seconds=0), 'fixture')
    assert batch.error.code == 'DEADLINE_EXCEEDED'
    assert batch.metrics.errors_count == 1


@pytest.mark.parametrize('compressed', [False, True])
def test_late_consumed_chunk_is_counted_before_deadline_rejection(monkeypatch, compressed):
    budget = t.Budget(2)
    body = gzip.compress(b'{}') if compressed else b'{}'
    class Late(httpx.SyncByteStream):
        def __iter__(self):
            budget.deadline = 0
            yield body
    install(monkeypatch, lambda request: httpx.Response(200, headers={
        'content-type': 'application/json',
        'content-encoding': 'gzip' if compressed else 'identity'}, stream=Late()))
    with pytest.raises(t.TransportError):
        t.fetch_json('https://example.com', budget)
    assert budget.encoded_bytes_read == len(body)
    assert budget.decoded_bytes_read == (0 if compressed else len(body))
    assert budget.errors_count == 1


def test_decode_expiry_counts_once_with_produced_bytes(monkeypatch):
    budget = t.Budget(2)
    install(monkeypatch, lambda request: response(
        gzip.compress(b'"' + b'x' * 200000 + b'"'), **{'content-encoding': 'gzip'}))
    original = t._BoundedDecoder._accumulate
    def expire(self, piece):
        original(self, piece)
        budget.deadline = 0
    monkeypatch.setattr(t._BoundedDecoder, '_accumulate', expire)
    with pytest.raises(t.TransportError) as exc:
        t.fetch_json('https://example.com', budget)
    assert exc.value.code == 'DEADLINE_EXCEEDED'
    assert budget.decoded_bytes_read == 65536
    assert budget.errors_count == 1


ROW = {'id': 1, 'title': 'Engineer', 'location': {'name': 'Dubai'},
       'absolute_url': 'https://example.com/1', 'content': 'Duties'}


@pytest.mark.parametrize('fallback', [False, True])
def test_provider_transform_cannot_return_expired_success(monkeypatch, fallback):
    budget = t.Budget(2)
    monkeypatch.setattr(g, 'Budget', lambda seconds: budget)
    def fetch(url, shared):
        assert shared is budget
        if fallback and url.endswith('?content=true'):
            shared.fail('RESPONSE_TOO_LARGE', 'Fixture cap')
        return {'jobs': [dict(ROW)]}
    monkeypatch.setattr(g, 'fetch_json', fetch)
    original = g._to_records
    def expire(*args):
        result = original(*args)
        budget.deadline = 0
        return result
    monkeypatch.setattr(g, '_to_records', expire)
    batch = g.GreenhouseProvider().fetch(FetchContext(detail_budget=0), 'fixture')
    assert batch.completion.value == 'FAILED'
    assert batch.error.code == 'DEADLINE_EXCEEDED'
    assert batch.metrics.errors_count == (2 if fallback else 1)


@pytest.mark.parametrize('detail', [{}, {'content': 'Duties', 'title': {}},
                                    httpx.WriteError('private'),
                                    httpx.RemoteProtocolError('private')])
def test_bad_detail_preserves_summary_and_counts_one_detail_failure(monkeypatch, detail):
    import json
    def handler(request):
        url = str(request.url)
        if 'content=true' in url:
            return response(b' ' * 501)
        if url.endswith('/1'):
            if isinstance(detail, Exception):
                raise detail
            return response(json.dumps(detail).encode())
        return response(json.dumps({'jobs': [ROW]}).encode())
    monkeypatch.setattr(t, 'MAX_ENCODED_BYTES', 500)
    install(monkeypatch, handler)
    batch = g.GreenhouseProvider().fetch(FetchContext(), 'fixture')
    assert batch.completion.value == 'PARTIAL'
    assert len(batch.records) == 1
    assert batch.records[0].title == 'Engineer'
    assert batch.metrics.detail_requests_attempted == 1
    assert batch.metrics.detail_requests_succeeded == 0
    assert batch.metrics.errors_count == 2  # list cap + rejected detail


@pytest.mark.parametrize('payload,expected', [
    ({'jobs': [ROW, {'id': {}}]}, 1),
    ({'jobs': [{'id': {}}, {'id': {}}]}, 2),
    ({'wrong': []}, 1),
])
def test_schema_failure_counts_are_not_duplicated(monkeypatch, payload, expected):
    monkeypatch.setattr(g, 'fetch_json', lambda *a: payload)
    batch = g.GreenhouseProvider().fetch(FetchContext(), 'fixture')
    assert batch.metrics.errors_count == expected


def test_detail_deadline_is_not_counted_again_by_final_transform(monkeypatch):
    def fetch(url, budget):
        if url.endswith('?content=true'):
            budget.fail('RESPONSE_TOO_LARGE', 'Fixture cap')
        if url.endswith('/1'):
            budget.deadline = 0
            budget.check()
        return {'jobs': [dict(ROW)]}
    monkeypatch.setattr(g, 'fetch_json', fetch)
    batch = g.GreenhouseProvider().fetch(FetchContext(), 'fixture')
    assert batch.completion.value == 'FAILED'
    assert batch.metrics.detail_requests_attempted == 1
    assert batch.metrics.errors_count == 2  # cap + deadline, not cap + two deadlines
