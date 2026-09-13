"""L2 hardening regressions: AI response byte cap (R-13) and tamper-evident
security-event chain plus expanded coverage (R-14)."""
import json
import pytest
import backend.security_events as se
from backend.models import DATA
from backend.providers import _read_capped, MAX_RESPONSE_BYTES


class _FakeResponse:
    def __init__(self, chunks):
        self._chunks = chunks
        self.closed = False
    def iter_bytes(self):
        yield from self._chunks
    def close(self):
        self.closed = True


# ---- R-13: AI response streaming byte cap ----

def test_read_capped_allows_bounded_body():
    body = b'{"ok": true}'
    assert _read_capped(_FakeResponse([body[:4], body[4:]])) == body

def test_read_capped_blocks_oversized_body():
    _reset_log()
    huge = _FakeResponse([b'x' * (MAX_RESPONSE_BYTES // 2 + 1)] * 2)
    with pytest.raises(ValueError):
        _read_capped(huge)
    assert huge.closed is True
    assert any(e['event'] == 'AI_RESPONSE_OVERSIZED' for e in se.tail(50))


# ---- R-14: expanded taxonomy + tamper-evident chain ----

def _reset_log():
    DATA.mkdir(parents=True, exist_ok=True)
    (DATA / 'security-events.log').unlink(missing_ok=True)
    (DATA / 'security-events.log.1').unlink(missing_ok=True)
    se._last_chain = None

@pytest.mark.parametrize('event', ['SESSION_INVALID', 'REQUEST_REJECTED',
                                   'AI_QUOTA_EXCEEDED', 'AI_RESPONSE_OVERSIZED',
                                   'UNHANDLED_ERROR'])
def test_new_events_are_registered(event):
    assert event in se.SEVERITY

def test_record_builds_verifiable_chain():
    _reset_log()
    for _ in range(3):
        se.record('PEER_BLOCKED')
    result = se.verify()
    assert result['ok'] is True and result['checked'] == 3

def test_unknown_event_is_not_recorded():
    _reset_log()
    se.record('NOT_A_REAL_EVENT')
    assert se.verify()['checked'] == 0

def test_chain_detects_modified_line():
    _reset_log()
    for _ in range(3):
        se.record('SSRF_DESTINATION_BLOCKED')
    log = DATA / 'security-events.log'
    lines = log.read_text(encoding='utf-8').splitlines()
    entry = json.loads(lines[1]); entry['event'] = 'CSRF_REJECTED'
    lines[1] = json.dumps(entry, ensure_ascii=True)
    log.write_text('\n'.join(lines) + '\n', encoding='utf-8')
    result = se.verify()
    assert result['ok'] is False and result['broken_at'] == 1

def test_chain_detects_deleted_line():
    _reset_log()
    for _ in range(3):
        se.record('SESSION_INVALID')
    log = DATA / 'security-events.log'
    lines = log.read_text(encoding='utf-8').splitlines()
    del lines[1]
    log.write_text('\n'.join(lines) + '\n', encoding='utf-8')
    assert se.verify()['ok'] is False

def test_record_never_raises_on_bad_state(monkeypatch):
    # Telemetry must never break a control path even if storage is unusable.
    monkeypatch.setattr(se, '_load_last_chain', lambda p: 1 / 0)
    se._last_chain = None
    se.record('PEER_BLOCKED')  # must not raise
