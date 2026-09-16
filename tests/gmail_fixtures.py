"""Shared synthetic fixtures for the Gmail OAuth suites (issue #44).

Everything here is fabricated. No real client ID, client secret, refresh
token, access token, authorization code, Gmail address or mailbox content
appears in these tests, and no test ever contacts Google or touches the
user's own credential store or ASTRA database -- the pytest session runs
against an isolated temporary data directory and database (see
`tests/conftest.py`) and against the in-memory credential backend below.
"""
import contextlib

import pytest

from backend import gmail_accounts as accounts
from backend import gmail_oauth as oauth

#: A structurally valid but entirely fictional installed-app client ID.
SYNTHETIC_CLIENT_ID = '123456789012-astrasynthetictestclient.apps.googleusercontent.com'

#: High-entropy sentinels. If any of these ever appears in a log, a security
#: event, the database file, an export, a backup, a diagnostic payload, an
#: API response or an exception string, the corresponding negative test
#: fails. None of them matches ASTRA's publication-gate secret patterns, so
#: they are safe to commit.
SENTINEL_REFRESH = 'astra-sentinel-refresh-4f9c2a71b0e83d5647fa19cb8e2d70a3'
SENTINEL_ACCESS = 'astra-sentinel-access-7b1d48e6c35a90f2148dbe57ac6039f1'
SENTINEL_CODE = 'astra-sentinel-authcode-2e7a5c90b4f16d83a0c95d2f7e14b68c'

SYNTHETIC_EMAIL = 'primary.tester@example.com'
OTHER_EMAIL = 'second.tester@example.com'


class FakeKeyring:
    """In-memory stand-in for the OS credential store.

    Its `__module__` is set below to the native Windows backend's module
    name so `gmail_accounts.credential_store()` accepts it under the same
    rule it applies in production.  Nothing is written to disk.
    """

    def __init__(self):
        self.store = {}
        self.fail_set = False
        self.fail_get = False
        self.fail_delete = False

    def set_password(self, service, name, value):
        if self.fail_set:
            raise RuntimeError('synthetic keyring write failure')
        self.store[(service, name)] = value

    def get_password(self, service, name):
        if self.fail_get:
            raise RuntimeError('synthetic keyring read failure')
        return self.store.get((service, name))

    def delete_password(self, service, name):
        if self.fail_delete:
            raise RuntimeError('synthetic keyring delete failure')
        import keyring.errors
        if (service, name) not in self.store:
            raise keyring.errors.PasswordDeleteError('not found')
        del self.store[(service, name)]


# Presented as the native Windows credential backend so the production
# backend allowlist is exercised rather than bypassed.
FakeKeyring.__module__ = accounts.WINDOWS_NATIVE_BACKEND


class FakeListener:
    """Stands in for the loopback listener, exposing its callback directly.

    Lets a test drive the attempt/consume/replay logic without binding a
    socket.  The real listener is exercised over real HTTP in
    `test_gmail_oauth.py`'s loopback section.
    """
    instances = []

    def __init__(self, on_callback):
        self.on_callback = on_callback
        self.redirect_uri = 'http://127.0.0.1:54321' + oauth.CALLBACK_PATH
        self.port = 54321
        self.is_closed = False
        self.started_with = None
        FakeListener.instances.append(self)

    def start(self, deadline):
        self.started_with = deadline
        return self.redirect_uri

    def close(self):
        self.is_closed = True


def reset_accounts():
    from sqlalchemy import delete
    from backend.models import Session
    accounts.initialize_gmail_schema()
    with Session.begin() as db:
        db.execute(delete(accounts.GmailAccount))


@pytest.fixture
def keyring_backend(monkeypatch):
    """Install the in-memory credential backend for one test."""
    fake = FakeKeyring()
    monkeypatch.setattr('backend.privacy.credential_backend', lambda: fake)
    return fake


@pytest.fixture
def gmail_env(monkeypatch, keyring_backend):
    """A configured client, a clean schema, and a fresh attempt manager."""
    from backend.models import initialize
    monkeypatch.setenv(oauth.CLIENT_ID_ENVIRONMENT_VARIABLE, SYNTHETIC_CLIENT_ID)
    initialize()
    reset_accounts()
    # A fresh manager per test, which also models what a process restart
    # does: pending attempts live only in the manager's memory.
    monkeypatch.setattr(oauth, 'attempts', oauth.AttemptManager())
    FakeListener.instances = []
    yield keyring_backend
    for listener in FakeListener.instances:
        listener.close()
    reset_accounts()


def token_response(*, refresh=SENTINEL_REFRESH, access=SENTINEL_ACCESS,
                   scope=oauth.GMAIL_READONLY_SCOPE):
    payload = {'access_token': access, 'expires_in': 3599, 'token_type': 'Bearer',
               'scope': scope}
    if refresh is not None:
        payload['refresh_token'] = refresh
    return payload


def install_google_double(monkeypatch, *, token=None, profile=None, revoke_status=200,
                          calls=None):
    """Replace the two outbound JSON calls and revocation with doubles.

    The real transport's own properties (fixed hosts, TLS verification,
    disabled redirects, ignored proxies, bounded timeouts and bounded
    response size) are asserted separately against the real
    `_client`/`_request`/`_FixedHostBackend`, so stubbing here never
    hides them.
    """
    seen = calls if calls is not None else []

    def fake_json_request(method, url, *, failure_code, total_timeout, data=None,
                          bearer=None):
        # `bearer_value` is read here, while the secret is still live: the
        # production code clears it as soon as the lookup returns, so a test
        # cannot reveal it afterwards.
        seen.append({'method': method, 'url': url, 'data': data,
                     'bearer': bearer, 'failure_code': failure_code,
                     'bearer_value': bearer.reveal() if bearer is not None else None})
        if url == oauth.TOKEN_ENDPOINT:
            result = token_response() if token is None else token
            if isinstance(result, Exception):
                raise result
            return result
        if url == oauth.PROFILE_ENDPOINT:
            result = {'emailAddress': SYNTHETIC_EMAIL, 'messagesTotal': 1,
                      'threadsTotal': 1, 'historyId': '1'} if profile is None else profile
            if isinstance(result, Exception):
                raise result
            return result
        raise AssertionError('unexpected URL in a test double')

    def fake_request(method, url, *, failure_code, total_timeout, data=None, bearer=None):
        seen.append({'method': method, 'url': url, 'data': data,
                     'failure_code': failure_code})
        if isinstance(revoke_status, Exception):
            raise revoke_status
        return revoke_status, 'application/json', b'{}'

    monkeypatch.setattr(oauth, '_json_request', fake_json_request)
    monkeypatch.setattr(oauth, '_request', fake_request)
    return seen


@contextlib.contextmanager
def redirected_data_dir(monkeypatch, path):
    """Point security-event telemetry at an isolated directory."""
    import backend.models as models
    monkeypatch.setattr(models, 'DATA', path)
    yield path
