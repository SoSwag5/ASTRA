"""Local session security: no private installation or real credentials."""
import base64
from concurrent.futures import ThreadPoolExecutor

from backend.access import AccessSessions

KEY = 'synthetic-fixture-access-key-not-a-real-secret'


def test_tokens_are_random_dynamic_and_only_digest_is_stored():
    store = AccessSessions()
    first, _ = store.issue(KEY, KEY)
    second, _ = store.issue(KEY, KEY)
    assert first != second and first != KEY
    assert len(base64.urlsafe_b64decode(first + '=')) == 32
    assert first not in store.sessions and KEY not in str(store.sessions)
    assert store.verify(KEY, first)
    assert not store.verify(KEY, KEY)
    assert not store.verify(KEY, first + 'x')


def test_reauthentication_revokes_previous_session():
    store = AccessSessions()
    first, _ = store.issue(KEY, KEY)
    second, _ = store.issue(KEY, KEY, first)
    assert not store.verify(KEY, first)
    assert store.verify(KEY, second)
    store.revoke(second)
    assert not store.verify(KEY, second)


def test_idle_and_absolute_expiration_cannot_be_extended():
    tick = [0]
    store = AccessSessions(lambda: tick[0])
    first, _ = store.issue(KEY, KEY)
    tick[0] = store.IDLE_SECONDS
    assert not store.verify(KEY, first)
    tick[0] = 0
    second, _ = store.issue(KEY, KEY)
    for t in range(0, store.MAX_SECONDS, 100):
        tick[0] = t
        assert store.verify(KEY, second)
    tick[0] = store.MAX_SECONDS
    assert not store.verify(KEY, second)


def test_restart_and_key_rotation_invalidate_every_session():
    store = AccessSessions()
    token, _ = store.issue(KEY, KEY)
    assert not AccessSessions().verify(KEY, token)
    assert not store.verify('changed-key', token)
    assert not store.verify(KEY, token)


def test_bruteforce_window_is_global_bounded_and_not_extended_by_rejections():
    tick = [0]
    store = AccessSessions(lambda: tick[0])
    with ThreadPoolExecutor(max_workers=12) as pool:
        results = list(pool.map(lambda _: store.issue(KEY, 'wrong'), range(20)))
    assert sum(retry == 0 for _, retry in results) == store.ATTEMPTS
    assert len(store.failures) == store.ATTEMPTS
    tick[0] = 59
    assert store.issue(KEY, KEY)[0] is None
    tick[0] = 60
    assert store.issue(KEY, KEY)[0] is not None
    assert len(store.failures) == 0


def test_session_storage_stays_bounded():
    store = AccessSessions()
    first, _ = store.issue(KEY, KEY)
    for _ in range(store.MAX_SESSIONS):
        assert store.issue(KEY, KEY)[0]
    assert len(store.sessions) == store.MAX_SESSIONS
    assert not store.verify(KEY, first)
