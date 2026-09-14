"""Test storage is isolated before test modules import application models."""
import os
import socket
import tempfile
from pathlib import Path

import pytest

_TEST_ROOT = tempfile.TemporaryDirectory(prefix='astra-tests-')
os.environ['HUNTER_DATA_DIR'] = str(Path(_TEST_ROOT.name) / 'data')
os.environ['DATABASE_URL'] = 'sqlite:///' + str(Path(_TEST_ROOT.name) / 'tests.db')
os.environ['APP_TOKEN'] = ''
os.environ['PYTHON_KEYRING_BACKEND'] = 'keyring.backends.fail.Keyring'


class UnexpectedNetworkAccess(RuntimeError):
    """Raised when a test that must be network-hermetic (job-provider
    fixtures should never depend on live DNS/network) attempts a real
    DNS resolution instead of hitting a mocked transport seam. See issue
    #38 Codex round-2 finding F7: a stale monkeypatch target let
    test_greenhouse_characterization.py silently fall through to live
    network calls once the underlying fetch implementation moved.
    """


@pytest.fixture
def no_unexpected_network():
    """Opt-in guard: fails loudly instead of quietly reaching the real
    network if the module under test calls socket.getaddrinfo while this
    fixture is active. Not applied globally -- several existing tests
    legitimately resolve real loopback/private addresses to exercise
    policy.py's SSRF checks themselves, which this guard would otherwise
    break.
    """
    real = socket.getaddrinfo

    def blocked(host, *a, **kw):
        raise UnexpectedNetworkAccess(
            f'Unexpected real DNS resolution for {host!r} during a test that must be '
            'network-hermetic; mock the transport boundary (fetch_json) instead.'
        )

    socket.getaddrinfo = blocked
    try:
        yield
    finally:
        socket.getaddrinfo = real

def pytest_sessionfinish(session, exitstatus):
    import sys
    models=sys.modules.get('backend.models')
    if models is not None:
        models.engine.dispose()
    _TEST_ROOT.cleanup()
