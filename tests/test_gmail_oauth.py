"""Issue #44 -- Gmail OAuth credential foundation.

Covers PKCE and state handling, the loopback callback listener, the
authorization request, the token exchange transport, granted-scope
validation, authorized-identity binding, the two-slot account model,
OS-backed credential storage, and disconnect/revocation semantics.

Everything is synthetic: no live Google call, no real client ID, no real
mailbox, no real token.  See `tests/gmail_fixtures.py`.
"""
import base64
import hashlib
import http.client
import json
import re
import threading

import httpx
import pytest
from sqlalchemy import select

from backend import gmail_accounts as accounts
from backend import gmail_oauth as oauth
from backend.models import Session
from tests.gmail_fixtures import (OTHER_EMAIL, SENTINEL_ACCESS, SENTINEL_CODE,
                                  SENTINEL_REFRESH, SYNTHETIC_CLIENT_ID,
                                  SYNTHETIC_EMAIL, FakeKeyring, FakeListener,
                                  gmail_env, install_google_double,
                                  keyring_backend, reset_accounts, token_response)

pytestmark = pytest.mark.usefixtures('gmail_env')


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def start_attempt(slot='PRIMARY', finalizer=None):
    """Start an attempt against the fake listener and return both."""
    calls = []

    def default_finalizer(**kwargs):
        calls.append(kwargs)
        return 'CONNECTED'

    attempt, url = oauth.attempts.start(slot, finalizer or default_finalizer,
                                        listener_factory=FakeListener)
    return attempt, url, FakeListener.instances[-1], calls


def callback_query(attempt, *, code=SENTINEL_CODE, state=None, extra=None):
    query = {}
    if code is not None:
        query['code'] = [code]
    if state is not False:
        query['state'] = [state if state is not None else attempt.state.reveal()]
    if extra:
        query.update(extra)
    return query


def connect_primary(monkeypatch, **double):
    """Drive a full successful connection through the fake listener."""
    install_google_double(monkeypatch, **double)
    attempt, _url, listener, _calls = start_attempt(finalizer=accounts._finalize)
    accepted = listener.on_callback(callback_query(attempt))
    return accepted, attempt


# ===========================================================================
# PKCE and state
# ===========================================================================
def test_code_verifier_meets_rfc_length_charset_and_entropy():
    verifier = oauth.generate_code_verifier()
    raw = verifier.reveal()
    assert 43 <= len(raw) <= 128
    assert re.fullmatch(r'[A-Za-z0-9._~-]+', raw)
    # Distinct across many draws: a constant or low-entropy verifier would collide.
    assert len({oauth.generate_code_verifier().reveal() for _ in range(200)}) == 200


def test_s256_challenge_matches_the_rfc_7636_known_vector():
    verifier = oauth.Secret('dBjftJeZ4CVP-mB92K27uhbUJU1p1r_wW1gFWFOEjXk')
    assert oauth.code_challenge(verifier) == 'E9Melhoa2OwvFrEMTJguCHaoeK1t8URWbuGJSstw-cM'


def test_s256_challenge_is_unpadded_base64url_of_the_sha256_digest():
    verifier = oauth.generate_code_verifier()
    expected = base64.urlsafe_b64encode(
        hashlib.sha256(verifier.reveal().encode('ascii')).digest()).rstrip(b'=').decode()
    assert oauth.code_challenge(verifier) == expected
    assert '=' not in oauth.code_challenge(verifier)


def test_only_s256_is_ever_offered_and_plain_is_never_sent():
    _attempt, url, _listener, _calls = start_attempt()
    assert 'code_challenge_method=S256' in url
    assert 'plain' not in url


def test_state_has_at_least_128_bits_of_entropy_and_is_unique_per_attempt():
    state = oauth.generate_state()
    # token_urlsafe(32) is 32 random bytes = 256 bits, ~43 base64url chars.
    assert len(state.reveal()) >= 32
    assert len({oauth.generate_state().reveal() for _ in range(200)}) == 200
    first, _u1, _l1, _c1 = start_attempt()
    # Read before starting the next attempt: superseding the first attempt
    # deliberately clears its secrets, which the supersede test asserts.
    first_state, first_verifier = first.state.reveal(), first.verifier.reveal()
    second, _u2, _l2, _c2 = start_attempt()
    assert first_state != second.state.reveal()
    assert first_verifier != second.verifier.reveal()


def test_correct_state_is_accepted_exactly_once():
    attempt, _url, listener, calls = start_attempt()
    assert listener.on_callback(callback_query(attempt)) is True
    assert len(calls) == 1


def test_incorrect_state_is_rejected():
    attempt, _url, listener, calls = start_attempt()
    assert listener.on_callback(callback_query(attempt, state='not-the-state')) is False
    assert calls == []
    assert oauth.attempts.status('PRIMARY')['result_code'] == 'CALLBACK_STATE_MISMATCH'


def test_missing_state_is_rejected():
    attempt, _url, listener, calls = start_attempt()
    assert listener.on_callback(callback_query(attempt, state=False)) is False
    assert calls == []
    assert oauth.attempts.status('PRIMARY')['result_code'] == 'CALLBACK_STATE_MISSING'


def test_duplicate_state_parameter_is_rejected():
    attempt, _url, listener, calls = start_attempt()
    query = {'code': [SENTINEL_CODE], 'state': [attempt.state.reveal(), 'second']}
    assert listener.on_callback(query) is False
    assert calls == []
    assert oauth.attempts.status('PRIMARY')['result_code'] == 'CALLBACK_DUPLICATE_PARAMETER'


def test_replayed_callback_cannot_trigger_a_second_exchange():
    attempt, _url, listener, calls = start_attempt()
    state = attempt.state.reveal()
    assert listener.on_callback(callback_query(attempt)) is True
    # Replay the identical, previously valid callback.
    assert listener.on_callback({'code': [SENTINEL_CODE], 'state': [state]}) is False
    assert len(calls) == 1, 'a replayed callback must never reach a second exchange'


def test_expired_attempt_is_rejected(monkeypatch):
    attempt, _url, listener, calls = start_attempt()
    monkeypatch.setattr(attempt, 'expires_at', 0.0)
    assert listener.on_callback(callback_query(attempt)) is False
    assert calls == []


def test_cancelled_attempt_cannot_complete():
    attempt, _url, listener, calls = start_attempt()
    state = attempt.state.reveal()
    result = oauth.attempts.cancel('PRIMARY')
    assert result['result_code'] == 'CANCELLED'
    assert listener.is_closed is True
    assert listener.on_callback({'code': [SENTINEL_CODE], 'state': [state]}) is False
    assert calls == []


def test_a_new_attempt_supersedes_the_previous_one_for_that_slot():
    first, _u1, first_listener, calls = start_attempt()
    first_state = first.state.reveal()
    second, _u2, _l2, calls2 = start_attempt()
    assert second.attempt_id != first.attempt_id
    assert first_listener.is_closed is True, 'the superseded listener must close'
    assert first_listener.on_callback({'code': [SENTINEL_CODE],
                                       'state': [first_state]}) is False
    assert oauth.attempts.pending_slots() == ['PRIMARY']


def test_concurrent_callbacks_produce_exactly_one_terminal_success():
    attempt, _url, listener, calls = start_attempt()
    state = attempt.state.reveal()
    results = []
    barrier = threading.Barrier(4)

    def fire():
        barrier.wait()
        results.append(listener.on_callback({'code': [SENTINEL_CODE], 'state': [state]}))

    threads = [threading.Thread(target=fire) for _ in range(4)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()
    assert results.count(True) == 1, 'exactly one concurrent callback may win'
    assert len(calls) == 1


def test_restart_leaves_no_resumable_attempt():
    start_attempt()
    assert oauth.attempts.pending_slots() == ['PRIMARY']
    # A restart builds a brand-new in-memory manager: nothing persisted.
    restarted = oauth.AttemptManager()
    assert restarted.pending_slots() == []
    assert restarted.status('PRIMARY') is None


def test_attempt_state_and_verifier_are_never_exposed_in_bounded_status():
    attempt, _url, _listener, _calls = start_attempt()
    payload = json.dumps(attempt.public())
    assert attempt.state.reveal() not in payload
    assert attempt.verifier.reveal() not in payload
    assert 'state' not in attempt.public() and 'verifier' not in attempt.public()


def test_secret_wrapper_redacts_every_representation():
    secret = oauth.Secret(SENTINEL_REFRESH)
    assert SENTINEL_REFRESH not in repr(secret)
    assert SENTINEL_REFRESH not in str(secret)
    assert SENTINEL_REFRESH not in f'{secret}'
    assert SENTINEL_REFRESH not in '{}'.format(secret)
    assert SENTINEL_REFRESH not in repr({'token': secret})
    assert SENTINEL_REFRESH not in repr([secret])
    assert secret.reveal() == SENTINEL_REFRESH
    secret.clear()
    with pytest.raises(ValueError):
        secret.reveal()


# ===========================================================================
# Loopback listener (real sockets, loopback only)
# ===========================================================================
@pytest.fixture
def listener():
    received = []
    made = oauth.CallbackListener(lambda parameters: (received.append(parameters), True)[1])
    made.received = received
    yield made
    made.close()


def request_callback(listener, path, method='GET', raw=None):
    connection = http.client.HTTPConnection(oauth.LOOPBACK_ADDRESS, listener.port,
                                            timeout=5)
    try:
        if raw is not None:
            connection.connect()
            connection.sock.sendall(raw)
            response = connection.response_class(connection.sock, method=method)
            response.begin()
        else:
            connection.request(method, path)
            response = connection.getresponse()
        body = response.read()
        return response.status, dict(response.getheaders()), body
    finally:
        connection.close()


def serve_one(listener):
    thread = threading.Thread(target=listener._server.handle_request, daemon=True)
    thread.start()
    return thread


def test_listener_binds_only_to_numeric_loopback_on_an_ephemeral_port(listener):
    assert listener.bound_address == '127.0.0.1'
    assert listener.bound_address not in ('0.0.0.0', '::', 'localhost')
    assert listener.port > 0 and listener.port != 8787
    assert listener.redirect_uri == f'http://127.0.0.1:{listener.port}{oauth.CALLBACK_PATH}'


def test_listener_never_binds_a_wildcard_or_reuses_the_api_port():
    # A wildcard bind would make the callback reachable from the network.
    assert oauth.LOOPBACK_ADDRESS == '127.0.0.1'
    assert oauth._CallbackServer.allow_reuse_address is False
    ports = set()
    for _ in range(3):
        made = oauth.CallbackListener(lambda parameters: True)
        ports.add(made.port)
        assert made.bound_address == '127.0.0.1'
        made.close()
    assert len(ports) == 3, 'each attempt gets its own ephemeral port'


def test_wrong_callback_path_is_rejected(listener):
    serve_one(listener)
    status, _headers, body = request_callback(listener, '/not-the-callback?code=x&state=y')
    assert status == 404
    assert listener.received == []
    assert b'code' not in body


def test_wrong_method_is_rejected_without_touching_attempt_state(listener):
    serve_one(listener)
    status, _headers, _body = request_callback(
        listener, oauth.CALLBACK_PATH + '?code=x&state=y', method='POST')
    assert status == 405
    assert listener.received == []


def test_oversized_request_line_is_rejected(listener):
    serve_one(listener)
    raw = (b'GET ' + oauth.CALLBACK_PATH.encode() + b'?code='
           + b'A' * (oauth.MAX_REQUEST_LINE_BYTES + 200) + b' HTTP/1.0\r\n\r\n')
    status, _headers, _body = request_callback(listener, '', raw=raw)
    assert status == 414
    assert listener.received == []


def test_oversized_query_is_rejected(listener):
    serve_one(listener)
    long_code = 'A' * (oauth.MAX_CALLBACK_QUERY_BYTES + 10)
    raw = (b'GET ' + oauth.CALLBACK_PATH.encode() + b'?code=' + long_code.encode()
           + b' HTTP/1.0\r\n\r\n')
    status, _headers, _body = request_callback(listener, '', raw=raw)
    assert status in (414, 400)
    assert listener.received == []


def test_static_response_carries_no_query_data_and_is_not_cacheable(listener):
    serve_one(listener)
    status, headers, body = request_callback(
        listener, oauth.CALLBACK_PATH + '?code=' + SENTINEL_CODE + '&state=abc123state')
    assert status == 200
    assert headers['Cache-Control'] == 'no-store'
    assert headers['Referrer-Policy'] == 'no-referrer'
    assert SENTINEL_CODE.encode() not in body
    assert b'abc123state' not in body
    assert b'@' not in body, 'no account identity is rendered'


def test_missing_and_duplicate_code_are_rejected_by_shape_validation():
    assert _reject({'state': ['s']}) == 'CALLBACK_MISSING_CODE'
    assert _reject({'state': ['s'], 'code': ['a', 'b']}) == 'CALLBACK_DUPLICATE_PARAMETER'
    assert _reject({'state': ['s'], 'code': ['']}) == 'CALLBACK_MISSING_CODE'


def test_oauth_error_callback_is_handled_without_reflecting_the_message():
    code = _reject({'state': ['s'], 'error': ['access_denied'],
                    'error_description': ['The user denied <script>alert(1)</script>']})
    assert code == 'CALLBACK_PROVIDER_ERROR'
    # Only the bounded code is available to callers; the description is dropped.
    assert 'access_denied' not in code and 'script' not in code


def test_unexpected_parameters_and_error_plus_code_are_rejected():
    assert _reject({'state': ['s'], 'code': ['c'], 'surprise': ['1']}) == \
        'CALLBACK_UNEXPECTED_PARAMETER'
    assert _reject({'state': ['s'], 'code': ['c'], 'error': ['e']}) == 'CALLBACK_INVALID'
    # Parameters Google legitimately adds do not make a callback ambiguous.
    assert _reject({'state': ['s'], 'code': ['c'], 'scope': [oauth.GMAIL_READONLY_SCOPE],
                    'authuser': ['0'], 'prompt': ['consent']}) is None


# --- Live-validation regression: Google's real callback shape -------------
# Live validation of issue #44 rejected a genuine Google callback with
# CALLBACK_UNEXPECTED_PARAMETER: the allowlist only covered the parameters
# Google's installed-app page enumerates, but the real redirect carries
# more non-secret metadata than that. RFC 6749 section 4.1.2 and Google's
# own OIDC documentation both require unrecognized response parameters to
# be ignored. These tests pin the corrected three-tier policy.
@pytest.mark.parametrize('extra', [
    {},
    {'scope': [oauth.GMAIL_READONLY_SCOPE]},
    {'scope': [oauth.GMAIL_READONLY_SCOPE], 'authuser': ['0'], 'prompt': ['consent']},
    {'granted_scopes': [oauth.GMAIL_READONLY_SCOPE]},
    {'iss': ['https://accounts.google.com']},
    {'hd': ['example.com']},
    {'session_state': ['opaque-value']},
    {'nonce': ['opaque-value']},
    {'expires_in': ['3599']},
    {'login_hint': ['opaque']},
    {'approval_prompt': ['force']},
    # The full realistic shape, all documented metadata at once.
    {'scope': [oauth.GMAIL_READONLY_SCOPE], 'granted_scopes': [oauth.GMAIL_READONLY_SCOPE],
     'authuser': ['0'], 'prompt': ['consent'], 'hd': ['example.com'],
     'iss': ['https://accounts.google.com'], 'session_state': ['opaque']},
])
def test_a_real_google_callback_with_documented_metadata_is_accepted(extra):
    query = {'state': ['s'], 'code': ['c'], **extra}
    assert _reject(query) is None, f'documented metadata must be tolerated: {sorted(extra)}'


def test_documented_metadata_is_ignored_and_never_influences_the_decision():
    """Tolerated metadata must not be able to change the outcome."""
    plain = oauth._validate_callback({'state': ['s'], 'code': ['c']})
    decorated = oauth._validate_callback({
        'state': ['s'], 'code': ['c'], 'scope': ['anything at all'],
        'authuser': ['9'], 'iss': ['https://impostor.example'],
        'granted_scopes': ['https://mail.google.com/']})
    assert plain == decorated == ('c', 's', None)
    # In particular, a hostile `scope`/`granted_scopes` in the callback is
    # not the scope ASTRA trusts -- that comes from the token response.
    assert oauth.REQUIRED_SCOPES == frozenset({oauth.GMAIL_READONLY_SCOPE})


@pytest.mark.parametrize('forbidden', [
    'access_token', 'id_token', 'refresh_token', 'token', 'token_type',
    'client_secret', 'code_verifier', 'assertion', 'password',
])
def test_a_credential_bearing_callback_parameter_is_refused_outright(forbidden):
    """A bearer credential here means this is not the flow ASTRA started."""
    query = {'state': ['s'], 'code': ['c'], forbidden: ['value']}
    assert _reject(query) == 'CALLBACK_FORBIDDEN_PARAMETER'
    # Refused even when it is the only thing wrong, and even without a code.
    assert _reject({'state': ['s'], forbidden: ['value']}) == \
        'CALLBACK_FORBIDDEN_PARAMETER'


@pytest.mark.parametrize('query,expected', [
    # Genuinely unknown names are still rejected -- tolerating documented
    # metadata is not the same as accepting anything.
    ({'state': ['s'], 'code': ['c'], 'surprise': ['1']}, 'CALLBACK_UNEXPECTED_PARAMETER'),
    ({'state': ['s'], 'code': ['c'], 'SCOPE': ['x']}, 'CALLBACK_UNEXPECTED_PARAMETER'),
    ({'state': ['s'], 'code': ['c'], '': ['x']}, 'CALLBACK_UNEXPECTED_PARAMETER'),
    # Duplicates of the security-sensitive three stay ambiguous, so refused.
    ({'state': ['a', 'b'], 'code': ['c']}, 'CALLBACK_DUPLICATE_PARAMETER'),
    ({'state': ['s'], 'code': ['a', 'b']}, 'CALLBACK_DUPLICATE_PARAMETER'),
    ({'state': ['s'], 'error': ['a', 'b']}, 'CALLBACK_DUPLICATE_PARAMETER'),
    # Conflicting success and error responses.
    ({'state': ['s'], 'code': ['c'], 'error': ['access_denied']}, 'CALLBACK_INVALID'),
    # Missing or empty essentials.
    ({'code': ['c']}, 'CALLBACK_STATE_MISSING'),
    ({'state': [''], 'code': ['c']}, 'CALLBACK_STATE_MISSING'),
    ({'state': ['s']}, 'CALLBACK_MISSING_CODE'),
    ({'state': ['s'], 'code': ['']}, 'CALLBACK_MISSING_CODE'),
    ({'state': ['s'], 'code': ['x' * 2049]}, 'CALLBACK_MISSING_CODE'),
    # Structurally impossible callbacks.
    ({}, 'CALLBACK_INVALID'),
    ([], 'CALLBACK_INVALID'),
])
def test_adversarial_callback_shapes_are_rejected(query, expected):
    assert _reject(query) == expected


def test_an_implausible_number_of_parameters_is_rejected_before_inspection():
    query = {'state': ['s'], 'code': ['c']}
    query.update({f'scope': ['x']})
    flood = {**query, **{f'unknown{i}': ['x'] for i in range(oauth.MAX_CALLBACK_PARAMETERS)}}
    assert _reject(flood) == 'CALLBACK_INVALID'
    assert len(flood) > oauth.MAX_CALLBACK_PARAMETERS


def test_the_allowlist_tiers_are_disjoint_and_exclude_secrets():
    sensitive = frozenset(oauth.SINGLE_VALUE_CALLBACK_PARAMETERS)
    assert not (sensitive & oauth.ALLOWED_CALLBACK_METADATA)
    assert not (oauth.ALLOWED_CALLBACK_METADATA & oauth.FORBIDDEN_CALLBACK_PARAMETERS)
    assert not (sensitive & oauth.FORBIDDEN_CALLBACK_PARAMETERS)
    assert oauth.ALLOWED_CALLBACK_PARAMETERS == sensitive | oauth.ALLOWED_CALLBACK_METADATA
    # No metadata name may be something that carries a credential.
    for name in oauth.ALLOWED_CALLBACK_METADATA:
        assert 'token' not in name and 'secret' not in name and 'verifier' not in name


def _reject(parameters):
    return oauth._validate_callback(parameters)[2]


def test_the_listener_accepts_googles_real_callback_shape_over_http(listener):
    """End-to-end over a real socket, with the metadata Google actually sends.

    This is the HTTP-level regression for the live-validation failure: the
    same request previously produced CALLBACK_UNEXPECTED_PARAMETER.
    """
    serve_one(listener)
    query = ('?state=opaque-state-value&code=opaque-code-value'
             '&scope=https%3A%2F%2Fwww.googleapis.com%2Fauth%2Fgmail.readonly'
             '&authuser=0&prompt=consent&iss=https%3A%2F%2Faccounts.google.com')
    status, headers, body = request_callback(listener, oauth.CALLBACK_PATH + query)
    assert status == 200, 'a real Google callback must be accepted'
    assert listener.received and set(listener.received[0]) == {
        'state', 'code', 'scope', 'authuser', 'prompt', 'iss'}
    assert headers['Cache-Control'] == 'no-store'
    # The accepted page still reflects nothing from the query.
    for leaked in (b'opaque-state-value', b'opaque-code-value', b'authuser',
                   b'accounts.google.com'):
        assert leaked not in body


@pytest.mark.parametrize('query', [
    '?code=a&&state=b',          # empty field
    '?code=a&state=b&x',         # name-only field
    '?code=%ZZ&state=b',         # invalid percent escape
    '?code=a&state=%',           # truncated percent escape
])
def test_a_malformed_query_is_rejected_by_the_listener(listener, query):
    serve_one(listener)
    status, _headers, _body = request_callback(listener, oauth.CALLBACK_PATH + query)
    assert status == 400
    assert listener.received == [], 'a malformed query never reaches validation'


def test_a_fragment_or_empty_query_is_rejected_by_the_listener(listener):
    serve_one(listener)
    status, _headers, _body = request_callback(
        listener, oauth.CALLBACK_PATH + '#code=a&state=b')
    assert status == 400
    assert listener.received == [], 'parameters cannot be smuggled in a fragment'


def test_a_bare_callback_path_with_no_query_is_rejected(listener):
    serve_one(listener)
    status, _headers, _body = request_callback(listener, oauth.CALLBACK_PATH)
    assert status == 400
    assert listener.received == []


def test_listener_closes_after_a_terminal_callback(listener):
    serve_one(listener)
    request_callback(listener, oauth.CALLBACK_PATH + '?code=c&state=s')
    listener.serve(deadline=0)      # the serve loop exits and closes
    assert listener.closed() is True


def test_listener_closes_after_its_deadline():
    made = oauth.CallbackListener(lambda parameters: True)
    made.serve(deadline=0)          # already past the deadline
    assert made.closed() is True


def test_closing_the_listener_mid_serve_stops_it_without_raising(capsys):
    """Supersede, cancel and disconnect all close a live serve thread."""
    import time
    made = oauth.CallbackListener(lambda parameters: True)
    made.start(time.monotonic() + 30)
    time.sleep(0.4)
    made.close()
    for _ in range(40):
        if made._thread is not None and not made._thread.is_alive():
            break
        time.sleep(0.05)
    assert made._thread is not None and not made._thread.is_alive()
    assert made.closed() is True
    captured = capsys.readouterr()
    assert 'Traceback' not in captured.err and 'Traceback' not in captured.out


def test_a_local_request_without_the_correct_state_cannot_complete_the_flow():
    """Another local process hitting the callback must not connect anything."""
    attempt, _url, listener, calls = start_attempt()
    real = oauth.CallbackListener(listener.on_callback)
    try:
        serve_one(real)
        status, _headers, _body = request_callback(
            real, oauth.CALLBACK_PATH + '?code=attacker-code&state=attacker-state')
        assert status == 400
        assert calls == [], 'state is the control: a guessed callback connects nothing'
    finally:
        real.close()


# ===========================================================================
# Authorization request
# ===========================================================================
def test_authorization_request_asks_for_exactly_gmail_readonly():
    _attempt, url, _listener, _calls = start_attempt()
    query = httpx.URL(url).params
    assert query['scope'] == 'https://www.googleapis.com/auth/gmail.readonly'
    assert oauth.REQUESTED_SCOPES == (oauth.GMAIL_READONLY_SCOPE,)


@pytest.mark.parametrize('broader', [
    'https://mail.google.com/',
    'https://www.googleapis.com/auth/gmail.modify',
    'https://www.googleapis.com/auth/gmail.send',
    'https://www.googleapis.com/auth/gmail.compose',
    'https://www.googleapis.com/auth/gmail.insert',
    'https://www.googleapis.com/auth/gmail.settings.basic',
    'https://www.googleapis.com/auth/drive',
    'https://www.googleapis.com/auth/contacts',
    'openid', 'profile', 'email',
])
def test_authorization_request_never_asks_for_a_broader_or_unrelated_scope(broader):
    _attempt, url, _listener, _calls = start_attempt()
    assert broader not in url


def test_authorization_request_carries_the_pkce_and_offline_parameters():
    attempt, url, _listener, _calls = start_attempt()
    query = httpx.URL(url).params
    assert query['code_challenge_method'] == 'S256'
    assert query['code_challenge'] == oauth.code_challenge(attempt.verifier)
    assert query['response_type'] == 'code'
    assert query['access_type'] == 'offline'
    assert query['client_id'] == SYNTHETIC_CLIENT_ID
    assert query['state'] == attempt.state.reveal()
    # Explicit account choice, explicit consent, and no silent inheritance
    # of scopes granted to this client earlier.
    assert 'consent' in query['prompt'] and 'select_account' in query['prompt']
    assert query['include_granted_scopes'] == 'false'


def test_authorization_request_uses_the_exact_loopback_redirect_uri():
    attempt, url, listener, _calls = start_attempt()
    assert httpx.URL(url).params['redirect_uri'] == listener.redirect_uri
    assert attempt.redirect_uri == listener.redirect_uri
    assert attempt.redirect_uri.startswith('http://127.0.0.1:')
    assert attempt.redirect_uri.endswith(oauth.CALLBACK_PATH)


def test_authorization_endpoint_is_fixed_and_not_caller_controlled():
    _attempt, url, _listener, _calls = start_attempt()
    assert url.startswith(oauth.AUTHORIZATION_ENDPOINT + '?')
    assert oauth.AUTHORIZATION_ENDPOINT == 'https://accounts.google.com/o/oauth2/v2/auth'
    # The builder takes no endpoint argument at all.
    assert 'endpoint' not in oauth.authorization_url.__code__.co_varnames


def test_the_secondary_slot_cannot_start_an_attempt():
    with pytest.raises(oauth.OAuthError) as raised:
        oauth.attempts.start('SECONDARY', lambda **kwargs: 'CONNECTED',
                             listener_factory=FakeListener)
    assert raised.value.code == 'SECONDARY_NOT_ENABLED'
    with pytest.raises(oauth.OAuthError) as unknown:
        oauth.require_enabled_slot('TERTIARY')
    assert unknown.value.code == 'UNKNOWN_ACCOUNT_SLOT'


def test_no_secret_appears_in_the_authorization_url():
    attempt, url, _listener, _calls = start_attempt()
    assert attempt.verifier.reveal() not in url, 'only the S256 challenge may appear'
    assert SENTINEL_REFRESH not in url and SENTINEL_ACCESS not in url


def test_a_missing_or_malformed_client_id_fails_closed(monkeypatch):
    monkeypatch.delenv(oauth.CLIENT_ID_ENVIRONMENT_VARIABLE, raising=False)
    assert oauth.client_id() is None
    assert oauth.configuration_status()['detail_code'] == 'CLIENT_NOT_CONFIGURED'
    with pytest.raises(oauth.OAuthError) as raised:
        oauth.require_client_id()
    assert raised.value.code == 'CLIENT_NOT_CONFIGURED'
    for bad in ('not-a-client-id', 'A' * 400, 'https://evil.example/token',
                '1-x.apps.googleusercontent.com',
                '123456789012-abc.apps.evil.com'):
        monkeypatch.setenv(oauth.CLIENT_ID_ENVIRONMENT_VARIABLE, bad)
        assert oauth.configuration_status()['state'] == 'INVALID'
        with pytest.raises(oauth.OAuthError):
            oauth.require_client_id()


# ===========================================================================
# Token exchange transport
# ===========================================================================
def test_token_and_revocation_endpoints_are_the_fixed_google_urls():
    assert oauth.TOKEN_ENDPOINT == 'https://oauth2.googleapis.com/token'
    assert oauth.REVOCATION_ENDPOINT == 'https://oauth2.googleapis.com/revoke'
    assert oauth.PROFILE_ENDPOINT == \
        'https://gmail.googleapis.com/gmail/v1/users/me/profile'
    for url in (oauth.AUTHORIZATION_ENDPOINT, oauth.TOKEN_ENDPOINT,
                oauth.REVOCATION_ENDPOINT, oauth.PROFILE_ENDPOINT):
        assert url.startswith('https://')
        assert httpx.URL(url).host in oauth.ALLOWED_HOSTS


def test_oauth_client_disables_redirects_proxies_and_bounds_every_timeout():
    client = oauth._client(oauth.TOTAL_TIMEOUT)
    try:
        assert client.trust_env is False, 'environment proxies must not be inherited'
        assert client.follow_redirects is False
        timeout = client.timeout
        assert timeout.connect and timeout.connect <= oauth.CONNECT_TIMEOUT
        assert timeout.read and timeout.read <= oauth.READ_TIMEOUT
        assert timeout.write and timeout.write <= oauth.READ_TIMEOUT
        assert timeout.pool and timeout.pool <= oauth.CONNECT_TIMEOUT
    finally:
        client.close()


def test_oauth_transport_verifies_tls_and_pins_the_allowed_hosts():
    import ssl
    transport = oauth._PinnedTransport()
    backend = transport._pool._network_backend
    assert isinstance(backend, oauth._FixedHostBackend)
    context = transport._pool._ssl_context
    # Standard verification against the system trust store, never disabled.
    assert context.verify_mode == ssl.CERT_REQUIRED
    assert context.check_hostname is True
    for host in ('evil.example', 'localhost', '127.0.0.1', 'accounts.google.com.evil'):
        with pytest.raises(oauth.OAuthError) as raised:
            backend.connect_tcp(host, 443)
        assert raised.value.code == 'DESTINATION_NOT_ALLOWED'
    with pytest.raises(oauth.OAuthError):
        backend.connect_tcp('oauth2.googleapis.com', 80)
    with pytest.raises(oauth.OAuthError):
        backend.connect_unix_socket('/tmp/socket')


def test_oauth_transport_dependency_versions_are_pinned():
    """Fails loudly on an upgrade so the pinning notes get re-verified."""
    assert httpx.__version__ == oauth.PINNED_HTTPX_VERSION
    import httpcore
    assert httpcore.__version__ == oauth.PINNED_HTTPCORE_VERSION
    assert hasattr(oauth._PinnedTransport(), '_pool')


def mock_google(monkeypatch, handler):
    """Drive the real `_request` against an in-process mock transport.

    `handler` must build a *fresh* `httpx.Response` per call: a response
    object may only be streamed once.
    """
    def fake_client(total_timeout):
        return httpx.Client(transport=httpx.MockTransport(handler),
                            trust_env=False, follow_redirects=False,
                            timeout=httpx.Timeout(connect=1, read=1, write=1, pool=1))
    monkeypatch.setattr(oauth, '_client', fake_client)


def responds(status, content, content_type='application/json'):
    """A handler returning a newly built *streaming* response per call.

    `content` is handed over as an iterator so httpx treats the body as a
    stream, which is what the production reader consumes -- a response
    built from a plain bytes body is already consumed and could not
    exercise the bounded `iter_raw()` path at all.
    """
    def handler(request):
        return httpx.Response(
            status, content=iter([content]),
            headers={'content-type': content_type} if content_type else {})
    return handler


def exchange_now():
    return oauth.exchange_code(configured_client_id=SYNTHETIC_CLIENT_ID,
                               code=oauth.Secret(SENTINEL_CODE),
                               verifier=oauth.generate_code_verifier(),
                               redirect_uri='http://127.0.0.1:1/x')


def test_token_exchange_rejects_a_redirect_instead_of_following_it(monkeypatch):
    mock_google(monkeypatch, lambda request: httpx.Response(
        302, headers={'location': 'https://evil.example/token'}))
    with pytest.raises(oauth.OAuthError) as raised:
        exchange_now()
    assert raised.value.code == 'TOKEN_EXCHANGE_FAILED'
    assert 'evil.example' not in str(raised.value)


# --- Live-validation regression: Content-Encoding on a Google response ----
# The reader consumes iter_raw() so the size cap applies to wire bytes, which
# means it owns the Content-Encoding step. It previously did not, so a
# compressed response reached json.loads as compressed bytes and the whole
# exchange failed as TOKEN_EXCHANGE_FAILED with no way to see why. ASTRA asks
# for `identity`, but that is a preference a server may ignore.
def _encoded(body, encoding):
    if encoding == 'gzip':
        import gzip
        return gzip.compress(body)
    if encoding == 'deflate':
        import zlib
        return zlib.compress(body)
    if encoding == 'deflate-raw':
        import zlib
        compressor = zlib.compressobj(wbits=-zlib.MAX_WBITS)
        return compressor.compress(body) + compressor.flush()
    return body


@pytest.mark.parametrize('encoding,header', [
    (None, None), ('identity', 'identity'), ('gzip', 'gzip'),
    ('deflate', 'deflate'), ('deflate-raw', 'deflate'),
])
def test_a_compressed_token_response_is_decoded_not_rejected(monkeypatch, encoding, header):
    payload = json.dumps({'access_token': SENTINEL_ACCESS,
                          'refresh_token': SENTINEL_REFRESH,
                          'scope': oauth.GMAIL_READONLY_SCOPE}).encode()

    def handler(request):
        headers = {'content-type': 'application/json'}
        if header:
            headers['content-encoding'] = header
        return httpx.Response(200, content=iter([_encoded(payload, encoding)]),
                              headers=headers)

    mock_google(monkeypatch, handler)
    result = exchange_now()
    assert result['granted_scopes'] == [oauth.GMAIL_READONLY_SCOPE]
    assert result['refresh_token'].reveal() == SENTINEL_REFRESH
    result['access_token'].clear()
    result['refresh_token'].clear()


def test_the_client_still_prefers_an_uncompressed_response():
    """Decoding compression is a fallback, not a reason to invite it."""
    client = oauth._client(oauth.TOTAL_TIMEOUT)
    try:
        assert client.headers['accept-encoding'] == 'identity'
    finally:
        client.close()


@pytest.mark.parametrize('header,body', [
    ('br', b'{"access_token":"x"}'),                       # unsupported codec
    ('gzip', b'\x1f\x8b not actually gzip'),               # corrupt
    ('deflate', b'not actually deflate at all'),           # corrupt
])
def test_an_undecodable_response_is_rejected(monkeypatch, header, body):
    mock_google(monkeypatch, lambda request: httpx.Response(
        200, content=iter([body]),
        headers={'content-type': 'application/json', 'content-encoding': header}))
    with pytest.raises(oauth.OAuthError) as raised:
        exchange_now()
    assert raised.value.code == 'TOKEN_EXCHANGE_FAILED'


def test_a_decompression_bomb_is_refused_within_the_size_bound(monkeypatch):
    """A small compressed body must not expand into an unbounded read."""
    import gzip
    bomb = gzip.compress(b'\0' * (oauth.MAX_RESPONSE_BYTES * 40))
    assert len(bomb) < oauth.MAX_RESPONSE_BYTES, 'the bomb must pass the wire cap'
    mock_google(monkeypatch, lambda request: httpx.Response(
        200, content=iter([bomb]),
        headers={'content-type': 'application/json', 'content-encoding': 'gzip'}))
    with pytest.raises(oauth.OAuthError) as raised:
        exchange_now()
    assert raised.value.code == 'TOKEN_EXCHANGE_FAILED'


def test_decoding_applies_to_the_profile_and_revocation_calls_too(monkeypatch):
    """All three outbound calls share the reader, so all three decode."""
    import gzip
    profile = json.dumps({'emailAddress': SYNTHETIC_EMAIL}).encode()
    mock_google(monkeypatch, lambda request: httpx.Response(
        200, content=iter([gzip.compress(profile)]),
        headers={'content-type': 'application/json', 'content-encoding': 'gzip'}))
    identity = oauth.fetch_authorized_identity(oauth.Secret(SENTINEL_ACCESS))
    assert identity['authorized_email'] == SYNTHETIC_EMAIL
    # Revocation only inspects the status, but must not trip on encoding.
    assert oauth.revoke_refresh_token(oauth.Secret(SENTINEL_REFRESH)) == 'SUCCEEDED'


def test_token_exchange_bounds_the_response_size(monkeypatch):
    oversized = b'{"padding":"' + b'A' * (oauth.MAX_RESPONSE_BYTES + 1000) + b'"}'
    mock_google(monkeypatch, responds(200, oversized))
    with pytest.raises(oauth.OAuthError) as raised:
        exchange_now()
    assert raised.value.code == 'TOKEN_EXCHANGE_FAILED'


@pytest.mark.parametrize('status,content,content_type', [
    (200, b'<html>not json</html>', 'text/html'),
    (200, b'{not valid json', 'application/json'),
    (200, b'["a","list"]', 'application/json'),
    (200, b'{"access_token":"x","scope":"y"}', None),
    # Unmapped/absent standard identifiers stay generic. The six standard
    # RFC 6749 identifiers map to bounded actionable codes instead, which
    # `test_a_standard_oauth_error_maps_to_a_bounded_actionable_code` covers.
    (400, b'{"error":"backend_error"}', 'application/json'),
    (500, b'{"error":"something_unmapped"}', 'application/json'),
])
def test_token_exchange_rejects_bad_content_type_json_shape_and_status(
        monkeypatch, status, content, content_type):
    mock_google(monkeypatch, responds(status, content, content_type))
    with pytest.raises(oauth.OAuthError) as raised:
        exchange_now()
    assert raised.value.code == 'TOKEN_EXCHANGE_FAILED'
    # A raw Google error string never reaches the caller.
    assert 'backend_error' not in str(raised.value)
    assert 'something_unmapped' not in str(raised.value)


def test_token_exchange_posts_form_fields_and_is_never_retried(monkeypatch):
    seen = []

    def handler(request):
        seen.append(request)
        return httpx.Response(400, content=iter([b'{"error":"invalid_grant"}']),
                              headers={'content-type': 'application/json'})

    mock_google(monkeypatch, handler)
    verifier = oauth.generate_code_verifier()
    with pytest.raises(oauth.OAuthError):
        oauth.exchange_code(configured_client_id=SYNTHETIC_CLIENT_ID,
                            code=oauth.Secret(SENTINEL_CODE), verifier=verifier,
                            redirect_uri='http://127.0.0.1:1/exact-path')
    assert len(seen) == 1, 'a single-use authorization code is never re-exchanged'
    assert seen[0].method == 'POST'
    assert seen[0].headers['content-type'] == 'application/x-www-form-urlencoded'
    body = seen[0].content.decode()
    assert 'grant_type=authorization_code' in body
    assert 'code_verifier=' + verifier.reveal() in body
    assert 'redirect_uri=http%3A%2F%2F127.0.0.1%3A1%2Fexact-path' in body
    # No secret is ever placed in the query string.
    assert oauth.TOKEN_ENDPOINT.count('?') == 0
    assert SENTINEL_CODE not in str(seen[0].url)


def test_token_exchange_sends_the_exact_redirect_uri_and_verifier(monkeypatch):
    calls = install_google_double(monkeypatch)
    attempt, _url, listener, _calls = start_attempt(finalizer=accounts._finalize)
    listener.on_callback(callback_query(attempt))
    exchange = next(call for call in calls if call['url'] == oauth.TOKEN_ENDPOINT)
    assert exchange['data']['redirect_uri'] == attempt.redirect_uri
    assert exchange['data']['grant_type'] == 'authorization_code'
    assert exchange['data']['client_id'] == SYNTHETIC_CLIENT_ID
    assert exchange['data']['code'] == SENTINEL_CODE
    assert 'client_secret' not in exchange['data'], 'PKCE replaces a client secret'


@pytest.mark.parametrize('payload,expected', [
    ({'scope': oauth.GMAIL_READONLY_SCOPE, 'token_type': 'Bearer'}, 'ACCESS_TOKEN_MISSING'),
    ({'access_token': '', 'scope': oauth.GMAIL_READONLY_SCOPE}, 'ACCESS_TOKEN_MISSING'),
    ({'access_token': '   ', 'scope': oauth.GMAIL_READONLY_SCOPE}, 'ACCESS_TOKEN_MISSING'),
    ({'access_token': 12345, 'scope': oauth.GMAIL_READONLY_SCOPE}, 'ACCESS_TOKEN_MISSING'),
    ({'access_token': SENTINEL_ACCESS}, 'TOKEN_RESPONSE_INVALID'),
    ({'access_token': SENTINEL_ACCESS, 'scope': ['a', 'list']}, 'TOKEN_RESPONSE_INVALID'),
    ({'access_token': SENTINEL_ACCESS, 'scope': oauth.GMAIL_READONLY_SCOPE,
      'refresh_token': 42}, 'TOKEN_RESPONSE_INVALID'),
])
def test_a_structurally_invalid_token_response_is_rejected(monkeypatch, payload, expected):
    mock_google(monkeypatch, responds(200, json.dumps(payload).encode()))
    with pytest.raises(oauth.OAuthError) as raised:
        exchange_now()
    assert raised.value.code == expected


def test_a_missing_refresh_token_fails_safely_and_preserves_the_existing_one(monkeypatch):
    accepted, _attempt = connect_primary(monkeypatch)
    assert accepted is True
    stored = _stored_credentials()
    assert list(stored.values()) == [SENTINEL_REFRESH]

    # Google omits refresh_token when reusing a prior grant.
    install_google_double(monkeypatch, token=token_response(refresh=None))
    attempt, _url, listener, _calls = start_attempt(finalizer=accounts._finalize)
    assert listener.on_callback(callback_query(attempt)) is False
    assert oauth.attempts.status('PRIMARY')['result_code'] == 'REFRESH_TOKEN_NOT_RETURNED'
    assert _stored_credentials() == stored, 'the existing credential is untouched'
    assert accounts.status()['accounts']['PRIMARY']['status'] == 'CONNECTED'


def test_a_blank_refresh_token_is_treated_as_absent(monkeypatch):
    install_google_double(monkeypatch, token=token_response(refresh='   '))
    attempt, _url, listener, _calls = start_attempt(finalizer=accounts._finalize)
    assert listener.on_callback(callback_query(attempt)) is False
    assert oauth.attempts.status('PRIMARY')['result_code'] == 'REFRESH_TOKEN_NOT_RETURNED'
    assert _stored_credentials() == {}


# ===========================================================================
# Granted scope and authorized identity
# ===========================================================================
def test_the_exact_granted_scope_is_accepted_and_recorded_normalized():
    assert oauth.validate_granted_scopes([oauth.GMAIL_READONLY_SCOPE]) == \
        [oauth.GMAIL_READONLY_SCOPE]
    assert oauth.normalize_scopes(
        f'{oauth.GMAIL_READONLY_SCOPE}  {oauth.GMAIL_READONLY_SCOPE} ') == \
        [oauth.GMAIL_READONLY_SCOPE]


def test_a_token_missing_gmail_readonly_is_rejected():
    for granted in ([], ['https://www.googleapis.com/auth/gmail.metadata'], ['openid']):
        with pytest.raises(oauth.OAuthError) as raised:
            oauth.validate_granted_scopes(granted)
        assert raised.value.code == 'SCOPE_MISSING_REQUIRED'


def test_a_broader_than_requested_grant_is_rejected():
    for extra in ('https://mail.google.com/',
                  'https://www.googleapis.com/auth/gmail.modify',
                  'https://www.googleapis.com/auth/drive', 'openid'):
        with pytest.raises(oauth.OAuthError) as raised:
            oauth.validate_granted_scopes([oauth.GMAIL_READONLY_SCOPE, extra])
        assert raised.value.code == 'SCOPE_BROADER_THAN_REQUESTED'


def test_a_broader_grant_stores_nothing_at_all(monkeypatch):
    install_google_double(monkeypatch, token=token_response(
        scope=f'{oauth.GMAIL_READONLY_SCOPE} https://mail.google.com/'))
    attempt, _url, listener, _calls = start_attempt(finalizer=accounts._finalize)
    assert listener.on_callback(callback_query(attempt)) is False
    assert oauth.attempts.status('PRIMARY')['result_code'] == 'SCOPE_BROADER_THAN_REQUESTED'
    assert _stored_credentials() == {}
    assert _rows() == []


def test_the_profile_is_queried_as_me_with_a_bearer_token(monkeypatch):
    calls = install_google_double(monkeypatch)
    attempt, _url, listener, _calls = start_attempt(finalizer=accounts._finalize)
    listener.on_callback(callback_query(attempt))
    profile = next(call for call in calls if call['url'] == oauth.PROFILE_ENDPOINT)
    assert profile['method'] == 'GET'
    assert profile['url'].endswith('/users/me/profile')
    # Captured while the secret was still live; the production code clears
    # it the moment the lookup returns.
    assert profile['bearer_value'] == SENTINEL_ACCESS


def test_the_returned_identity_overrides_any_intent_or_login_hint(monkeypatch):
    """Google's authenticated profile is the only identity ASTRA trusts."""
    install_google_double(monkeypatch, profile={'emailAddress': OTHER_EMAIL})
    attempt, url, listener, _calls = start_attempt(finalizer=accounts._finalize)
    # ASTRA never sends a login hint at all, so there is nothing to conflate.
    assert 'login_hint' not in url
    assert listener.on_callback(callback_query(attempt)) is True
    row = _rows()[0]
    assert row.authorized_email == OTHER_EMAIL
    assert row.identity_kind == 'GMAIL_PROFILE_EMAIL'


@pytest.mark.parametrize('profile', [
    {}, {'emailAddress': ''}, {'emailAddress': '   '}, {'emailAddress': 123},
    {'emailAddress': 'no-at-sign'}, {'emailAddress': 'a@' + 'x' * 400},
    {'emailAddress': 'two@at@signs.example'}, {'emailAddress': 'spaces in@example.com'},
])
def test_an_invalid_or_malformed_profile_is_rejected(monkeypatch, profile):
    install_google_double(monkeypatch, profile=profile)
    attempt, _url, listener, _calls = start_attempt(finalizer=accounts._finalize)
    assert listener.on_callback(callback_query(attempt)) is False
    assert oauth.attempts.status('PRIMARY')['result_code'] == 'IDENTITY_RESPONSE_INVALID'
    assert _stored_credentials() == {}


def test_an_identity_lookup_failure_leaves_no_credential(monkeypatch):
    install_google_double(monkeypatch, profile=oauth.OAuthError(
        'IDENTITY_LOOKUP_FAILED', 'A Google request timed out'))
    attempt, _url, listener, _calls = start_attempt(finalizer=accounts._finalize)
    assert listener.on_callback(callback_query(attempt)) is False
    assert oauth.attempts.status('PRIMARY')['result_code'] == 'IDENTITY_LOOKUP_FAILED'
    assert _stored_credentials() == {}
    assert _rows() == []


def test_identity_normalization_lowercases_only_the_domain():
    assert oauth.normalize_identity('First.Last@Example.COM') == 'First.Last@example.com'
    # Dot- and plus-folding are deliberately NOT applied: they would change
    # mailbox identity semantics on a Workspace domain.
    assert oauth.normalize_identity('a.b@example.com') != \
        oauth.normalize_identity('ab@example.com')
    assert oauth.normalize_identity('a+tag@example.com') != \
        oauth.normalize_identity('a@example.com')


def test_the_same_identity_cannot_be_connected_to_two_slots(monkeypatch):
    accepted, _attempt = connect_primary(monkeypatch)
    assert accepted is True
    identity = {'authorized_email': SYNTHETIC_EMAIL,
                'identity_key': oauth.normalize_identity(SYNTHETIC_EMAIL),
                'identity_kind': 'GMAIL_PROFILE_EMAIL'}
    with pytest.raises(oauth.OAuthError) as raised:
        accounts._bind_credential('SECONDARY', identity,
                                  [oauth.GMAIL_READONLY_SCOPE],
                                  oauth.Secret('another-synthetic-refresh-value'))
    assert raised.value.code == 'IDENTITY_ALREADY_CONNECTED'
    assert len(_rows()) == 1


def test_one_credential_key_can_never_be_shared_by_two_connected_records(monkeypatch):
    import sqlalchemy.exc
    connect_primary(monkeypatch)
    shared = _rows()[0].credential_key
    with pytest.raises(sqlalchemy.exc.IntegrityError):
        with Session.begin() as db:
            db.add(accounts.GmailAccount(
                slot='SECONDARY', status=accounts.CONNECTED,
                identity_key='other@example.com', credential_key=shared))
    assert len(_rows()) == 1


def test_no_mailbox_message_or_thread_data_is_persisted(monkeypatch):
    install_google_double(monkeypatch, profile={
        'emailAddress': SYNTHETIC_EMAIL, 'messagesTotal': 40321,
        'threadsTotal': 18022, 'historyId': '998877'})
    attempt, _url, listener, _calls = start_attempt(finalizer=accounts._finalize)
    assert listener.on_callback(callback_query(attempt)) is True
    columns = set(accounts.GmailAccount.__table__.columns.keys())
    for forbidden in ('thread_id', 'threadId', 'message_id', 'messages_total',
                      'threads_total', 'history_id', 'subject', 'sender', 'snippet',
                      'body', 'refresh_token', 'access_token', 'authorization_code',
                      'code_verifier', 'state', 'client_secret', 'token'):
        assert forbidden not in columns
    serialized = json.dumps({c: str(getattr(_rows()[0], c)) for c in columns})
    for leaked in ('40321', '18022', '998877'):
        assert leaked not in serialized


# ===========================================================================
# Credential storage
# ===========================================================================
def _stored_credentials():
    from backend.privacy import credential_backend
    return {name: value for (service, name), value
            in credential_backend().store.items()
            if service == accounts.CREDENTIAL_SERVICE}


def _rows():
    with Session() as db:
        return list(db.scalars(select(accounts.GmailAccount)))


def test_a_supported_native_backend_is_accepted():
    assert accounts.credential_store_status() == {'state': 'OS_SECURE_STORE',
                                                  'detail_code': 'OK'}
    assert accounts.CREDENTIAL_SERVICE == 'ASTRA-Gmail-OAuth'
    assert accounts.CREDENTIAL_SERVICE != 'LocalJobHunter', \
        'Gmail uses a namespace separate from the OpenAI credential'


def test_an_unsupported_or_failing_keyring_is_rejected_with_no_plaintext_fallback(monkeypatch):
    class Unsupported:
        pass

    Unsupported.__module__ = 'keyring.backends.fail'
    monkeypatch.setattr('backend.privacy.credential_backend', lambda: Unsupported())
    if __import__('os').name == 'nt':
        with pytest.raises(oauth.OAuthError) as raised:
            accounts.credential_store()
        assert raised.value.code == 'CREDENTIAL_STORE_UNAVAILABLE'

    def refuse():
        raise ValueError('A supported native secure credential store is unavailable')

    monkeypatch.setattr('backend.privacy.credential_backend', refuse)
    with pytest.raises(oauth.OAuthError) as raised:
        accounts.credential_store()
    assert raised.value.code == 'CREDENTIAL_STORE_UNAVAILABLE'
    assert accounts.credential_store_status()['state'] == 'UNAVAILABLE'
    # No environment, file or database fallback exists anywhere in the module.
    source = __import__('pathlib').Path('backend/gmail_accounts.py').read_text(encoding='utf-8')
    assert 'getenv' not in source.replace('CLIENT_ID_ENVIRONMENT_VARIABLE', '')
    assert 'open(' not in source


def test_a_credential_store_write_failure_leaves_the_account_disconnected(monkeypatch, gmail_env):
    install_google_double(monkeypatch)
    gmail_env.fail_set = True
    attempt, _url, listener, _calls = start_attempt(finalizer=accounts._finalize)
    assert listener.on_callback(callback_query(attempt)) is False
    assert oauth.attempts.status('PRIMARY')['result_code'] == 'CREDENTIAL_STORE_FAILED'
    assert accounts.status()['accounts']['PRIMARY']['status'] == 'DISCONNECTED'
    assert _rows() == []


def test_a_database_failure_after_the_credential_write_deletes_that_credential(monkeypatch):
    install_google_double(monkeypatch)
    real_begin = Session.begin

    def failing_begin(*args, **kwargs):
        raise RuntimeError('synthetic database failure')

    attempt, _url, listener, _calls = start_attempt(finalizer=accounts._finalize)
    monkeypatch.setattr(Session, 'begin', failing_begin)
    accepted = listener.on_callback(callback_query(attempt))
    monkeypatch.setattr(Session, 'begin', real_begin)
    assert accepted is False
    assert oauth.attempts.status('PRIMARY')['result_code'] == 'PERSISTENCE_FAILED'
    assert _stored_credentials() == {}, 'the orphaned credential must be removed'
    assert _rows() == []


def test_per_account_credential_keys_are_isolated_opaque_and_never_reused(monkeypatch):
    keys = {accounts.new_credential_key(slot) for slot in ('PRIMARY', 'SECONDARY')
            for _ in range(20)}
    assert len(keys) == 40, 'each connection gets a fresh key'
    for key in keys:
        assert SYNTHETIC_EMAIL not in key and '@' not in key
    assert all(key.startswith(('primary-', 'secondary-')) for key in keys)

    connect_primary(monkeypatch)
    first = _rows()[0].credential_key
    install_google_double(monkeypatch)
    attempt, _url, listener, _calls = start_attempt(finalizer=accounts._finalize)
    assert listener.on_callback(callback_query(attempt)) is True
    second = _rows()[0].credential_key
    assert second != first, 'a reconnect never reuses the previous key'
    assert first not in _stored_credentials(), 'the superseded credential is removed'


def test_the_access_token_is_never_persisted_and_is_cleared_after_use(monkeypatch):
    holder = {}

    def capturing_json_request(method, url, *, failure_code, total_timeout,
                               data=None, bearer=None):
        if url == oauth.TOKEN_ENDPOINT:
            return token_response()
        holder['bearer'] = bearer
        return {'emailAddress': SYNTHETIC_EMAIL}

    monkeypatch.setattr(oauth, '_json_request', capturing_json_request)
    attempt, _url, listener, _calls = start_attempt(finalizer=accounts._finalize)
    assert listener.on_callback(callback_query(attempt)) is True
    # The access token was usable during the lookup and released afterwards.
    with pytest.raises(ValueError):
        holder['bearer'].reveal()
    assert SENTINEL_ACCESS not in json.dumps(
        {c: str(getattr(_rows()[0], c)) for c in
         accounts.GmailAccount.__table__.columns.keys()})
    assert SENTINEL_ACCESS not in json.dumps(_stored_credentials())


def test_a_connected_account_records_only_non_secret_metadata(monkeypatch):
    connect_primary(monkeypatch)
    row = _rows()[0]
    assert row.slot == 'PRIMARY'
    assert row.status == accounts.CONNECTED
    assert row.authorized_email == SYNTHETIC_EMAIL
    assert row.granted_scopes == [oauth.GMAIL_READONLY_SCOPE]
    assert row.connected_at and row.last_validated_at
    assert row.sync_state == {}
    assert _stored_credentials() == {row.credential_key: SENTINEL_REFRESH}


# ===========================================================================
# OAuth client secret (Owner-authorized, evidence-backed: this Desktop
# client enforces client authentication at the token endpoint -- without a
# secret Google answered 400 invalid_request naming the missing secret, and
# with a wrong one 401 invalid_client)
# ===========================================================================
SENTINEL_CLIENT_SECRET = 'astra-sentinel-clientsecret-6d3f81b904ae572c1fb8'


def test_the_client_secret_is_stored_in_its_own_keyring_namespace(gmail_env):
    assert accounts.store_client_secret(oauth.Secret(SENTINEL_CLIENT_SECRET)) is True
    assert accounts.CLIENT_CREDENTIAL_SERVICE == 'ASTRA-Gmail-OAuth-Client'
    assert accounts.CLIENT_CREDENTIAL_SERVICE != accounts.CREDENTIAL_SERVICE
    assert accounts.CLIENT_CREDENTIAL_SERVICE != 'LocalJobHunter'
    stored = {(service, name) for (service, name) in gmail_env.store}
    assert (accounts.CLIENT_CREDENTIAL_SERVICE, 'client-secret') in stored
    # Round-trips through the OS-backed store, wrapped so it cannot be printed.
    secret = accounts.read_client_secret()
    assert isinstance(secret, oauth.Secret)
    assert SENTINEL_CLIENT_SECRET not in repr(secret)
    assert secret.reveal() == SENTINEL_CLIENT_SECRET


def test_client_secret_status_never_reveals_or_describes_the_value(gmail_env):
    assert accounts.client_secret_status()['state'] == 'NOT_CONFIGURED'
    assert accounts.client_secret_status()['detail_code'] == 'CLIENT_SECRET_NOT_CONFIGURED'
    accounts.store_client_secret(oauth.Secret(SENTINEL_CLIENT_SECRET))
    status = accounts.client_secret_status()
    assert status == {'state': 'CONFIGURED', 'detail_code': 'OK'}
    assert SENTINEL_CLIENT_SECRET not in json.dumps(status)
    assert SENTINEL_CLIENT_SECRET not in json.dumps(accounts.status())


@pytest.mark.parametrize('bad', ['', '   ', 'x' * 513])
def test_an_implausible_client_secret_is_refused(gmail_env, bad):
    with pytest.raises(oauth.OAuthError) as raised:
        accounts.store_client_secret(oauth.Secret(bad))
    assert raised.value.code == 'CLIENT_SECRET_INVALID'
    if bad.strip():
        assert bad.strip() not in str(raised.value)
    assert accounts.client_secret_status()['state'] == 'NOT_CONFIGURED'


def test_a_credential_store_failure_while_saving_the_secret_is_bounded(gmail_env):
    gmail_env.fail_set = True
    with pytest.raises(oauth.OAuthError) as raised:
        accounts.store_client_secret(oauth.Secret(SENTINEL_CLIENT_SECRET))
    assert raised.value.code == 'CREDENTIAL_STORE_FAILED'
    assert SENTINEL_CLIENT_SECRET not in str(raised.value)
    assert SENTINEL_CLIENT_SECRET not in repr(raised.value)


def test_the_token_exchange_includes_the_configured_secret(monkeypatch, gmail_env):
    accounts.store_client_secret(oauth.Secret(SENTINEL_CLIENT_SECRET))
    calls = install_google_double(monkeypatch)
    attempt, _url, listener, _calls = start_attempt(finalizer=accounts._finalize)
    assert listener.on_callback(callback_query(attempt)) is True
    exchange = next(call for call in calls if call['url'] == oauth.TOKEN_ENDPOINT)
    assert exchange['data']['client_secret'] == SENTINEL_CLIENT_SECRET
    assert exchange['data']['code_verifier'], 'PKCE is still sent alongside it'
    assert exchange['data']['grant_type'] == 'authorization_code'


def test_the_token_exchange_omits_the_secret_when_none_is_configured(monkeypatch, gmail_env):
    calls = install_google_double(monkeypatch)
    attempt, _url, listener, _calls = start_attempt(finalizer=accounts._finalize)
    assert listener.on_callback(callback_query(attempt)) is True
    exchange = next(call for call in calls if call['url'] == oauth.TOKEN_ENDPOINT)
    assert 'client_secret' not in exchange['data']


def test_a_refresh_includes_the_secret_and_stays_read_only(monkeypatch, gmail_env):
    accounts.store_client_secret(oauth.Secret(SENTINEL_CLIENT_SECRET))
    calls = []

    def double(method, url, *, failure_code, total_timeout, data=None, bearer=None):
        calls.append({'url': url, 'data': data})
        return {'access_token': SENTINEL_ACCESS, 'expires_in': 3599,
                'scope': oauth.GMAIL_READONLY_SCOPE}

    monkeypatch.setattr(oauth, '_json_request', double)
    secret = accounts.read_client_secret()
    result = oauth.refresh_access_token(
        configured_client_id=SYNTHETIC_CLIENT_ID,
        refresh_token=oauth.Secret(SENTINEL_REFRESH), client_secret=secret)
    assert calls[0]['url'] == oauth.TOKEN_ENDPOINT
    assert calls[0]['data']['grant_type'] == 'refresh_token'
    assert calls[0]['data']['client_secret'] == SENTINEL_CLIENT_SECRET
    assert calls[0]['data']['refresh_token'] == SENTINEL_REFRESH
    assert result['granted_scopes'] == [oauth.GMAIL_READONLY_SCOPE]
    assert isinstance(result['access_token'], oauth.Secret)
    result['access_token'].clear()


def test_a_refresh_without_a_scope_field_is_accepted_as_unchanged(monkeypatch):
    monkeypatch.setattr(oauth, '_json_request', lambda *a, **k: {
        'access_token': SENTINEL_ACCESS, 'expires_in': 3599})
    result = oauth.refresh_access_token(
        configured_client_id=SYNTHETIC_CLIENT_ID,
        refresh_token=oauth.Secret(SENTINEL_REFRESH))
    assert result['granted_scopes'] is None
    result['access_token'].clear()


def test_the_secret_is_only_ever_sent_to_the_exact_google_token_endpoint(monkeypatch):
    """Enforced at the single transport chokepoint, not per call site."""
    for url in (oauth.PROFILE_ENDPOINT, oauth.REVOCATION_ENDPOINT,
                oauth.AUTHORIZATION_ENDPOINT, 'https://evil.example/token'):
        with pytest.raises(oauth.OAuthError) as raised:
            oauth._request('POST', url, failure_code='X', total_timeout=5,
                           data={'client_secret': SENTINEL_CLIENT_SECRET})
        assert raised.value.code == 'DESTINATION_NOT_ALLOWED'
        assert SENTINEL_CLIENT_SECRET not in str(raised.value)
    # Revocation and the profile lookup never carry one in the first place.
    import pathlib
    source = pathlib.Path('backend/gmail_oauth.py').read_text(encoding='utf-8')
    revoke = source[source.index('def revoke_refresh_token'):]
    assert 'client_secret' not in revoke[:revoke.index('\n\n\n')]


@pytest.mark.parametrize('identifier,expected', [
    ('invalid_client', 'CLIENT_AUTHENTICATION_REQUIRED'),
    ('unauthorized_client', 'CLIENT_AUTHENTICATION_REQUIRED'),
    ('invalid_request', 'CLIENT_AUTHENTICATION_REQUIRED'),
    ('invalid_grant', 'AUTHORIZATION_EXPIRED'),
    ('unsupported_grant_type', 'AUTHORIZATION_EXPIRED'),
    ('invalid_scope', 'SCOPE_MISSING_REQUIRED'),
])
def test_a_standard_oauth_error_maps_to_a_bounded_actionable_code(
        monkeypatch, identifier, expected):
    """The opaque failure that live validation hit is now actionable."""
    body = json.dumps({'error': identifier,
                       'error_description': 'free text that must not surface '
                                            'and may restate the request'}).encode()
    mock_google(monkeypatch, responds(400, body))
    with pytest.raises(oauth.OAuthError) as raised:
        exchange_now()
    assert raised.value.code == expected
    assert 'free text' not in str(raised.value)
    assert 'restate' not in str(raised.value)


def test_an_unknown_or_absent_error_identifier_stays_generic(monkeypatch):
    for body in (b'{"error":"something_new"}', b'{"error":123}', b'{}',
                 b'not json at all'):
        mock_google(monkeypatch, responds(400, body))
        with pytest.raises(oauth.OAuthError) as raised:
            exchange_now()
        assert raised.value.code == 'TOKEN_EXCHANGE_FAILED'


def test_an_incorrect_secret_surfaces_a_bounded_authentication_failure(
        monkeypatch, gmail_env):
    accounts.store_client_secret(oauth.Secret('astra-sentinel-wrong-secret-value'))
    mock_google(monkeypatch, responds(401, json.dumps(
        {'error': 'invalid_client',
         'error_description': 'The OAuth client was not found.'}).encode()))
    attempt, _url, listener, _calls = start_attempt(finalizer=accounts._finalize)
    assert listener.on_callback(callback_query(attempt)) is False
    status = oauth.attempts.status('PRIMARY')
    assert status['result_code'] == 'CLIENT_AUTHENTICATION_REQUIRED'
    assert _stored_credentials() == {}, 'nothing is stored on an auth failure'
    assert _rows() == []
    assert accounts.status()['accounts']['PRIMARY']['status'] == 'DISCONNECTED'


# --- CodeQL-driven hardening: exception text must not reach any output ---
# Hosted CodeQL flagged two real taint paths in this feature:
#   py/clear-text-logging-sensitive-data (high) -- an exception raised by a
#     function that had handled the secret flowed into print().
#   py/stack-trace-exposure (medium) -- str(error) flowed into an HTTP body.
# Both are now structurally impossible: user-facing text comes only from the
# authored message table, keyed by a bounded code.
def test_every_bounded_code_has_an_authored_message():
    import re
    import pathlib
    source = ''.join(pathlib.Path(f'backend/{name}').read_text(encoding='utf-8')
                     for name in ('gmail_oauth.py', 'gmail_accounts.py'))
    raised = set(re.findall(r"OAuthError\('([A-Z_]+)'", source))
    assert raised, 'the sweep must actually find raise sites'
    missing = sorted(raised - set(oauth.MESSAGES))
    assert not missing, f'codes without an authored message: {missing}'
    # Result codes the attempt manager reports are covered too.
    for code in ('AWAITING_GOOGLE', 'CONNECTED', 'CANCELLED', 'EXPIRED',
                 'SUPERSEDED', 'INVALIDATED', 'INVALIDATED_BY_DISCONNECT',
                 'CONNECTION_FAILED', 'ATTEMPT_EXPIRED',
                 'CLIENT_AUTHENTICATION_REQUIRED', 'AUTHORIZATION_EXPIRED',
                 'CLIENT_SECRET_NOT_CONFIGURED', 'TOKEN_REFRESH_FAILED'):
        assert code in oauth.MESSAGES, code


def test_message_for_never_returns_exception_or_upstream_text():
    assert oauth.message_for('SECONDARY_NOT_ENABLED') == \
        oauth.MESSAGES['SECONDARY_NOT_ENABLED']
    # An unmapped, hostile or non-string code falls back to a generic line,
    # never to anything derived from input.
    for code in ('NOT_A_CODE', '', None, 123, SENTINEL_REFRESH,
                 '<script>alert(1)</script>'):
        assert oauth.message_for(code) == oauth.DEFAULT_MESSAGE
    assert SENTINEL_REFRESH not in oauth.DEFAULT_MESSAGE


def _executable_python(path):
    """Source with comments and string literals removed.

    A module that documents why it avoids `str(error)` would otherwise
    fail a scan for that very phrase, so only real code tokens are kept.
    """
    import io
    import pathlib
    import tokenize
    text = pathlib.Path(path).read_text(encoding='utf-8')
    kept = []
    for token in tokenize.generate_tokens(io.StringIO(text).readline):
        if token.type in (tokenize.COMMENT, tokenize.STRING):
            continue
        kept.append(token.string)
    return ' '.join(kept)


def test_the_api_body_is_built_from_the_code_not_the_exception(monkeypatch):
    """`str(error)` must never reach a response body."""
    code = _executable_python('backend/gmail_api.py')
    assert 'str ( error )' not in code, 'the API must not stringify an exception'
    assert 'message_for' in code
    assert 'traceback' not in code and 'format_exc' not in code

    from backend.gmail_api import _bounded_error
    marker = 'INTERNAL DETAIL THAT MUST NOT SURFACE'
    response = _bounded_error(oauth.OAuthError('SCOPE_MISSING_REQUIRED', marker))
    body = json.loads(response.body)
    assert marker not in json.dumps(body)
    assert body['code'] == 'SCOPE_MISSING_REQUIRED'
    assert body['detail'] == oauth.MESSAGES['SCOPE_MISSING_REQUIRED']
    # An unmapped code still yields authored text, never the message.
    body = json.loads(_bounded_error(oauth.OAuthError('UNMAPPED', marker)).body)
    assert body['detail'] == oauth.DEFAULT_MESSAGE
    assert marker not in json.dumps(body)


def test_the_setup_command_can_only_print_authored_lines():
    """No free string reaches print() in the secret-handling module."""
    import pathlib
    import re
    code = _executable_python('backend/gmail_setup.py')
    # Every print() call site is one of the three authored helpers.
    prints = re.findall(r'^\s*print\(', pathlib.Path('backend/gmail_setup.py')
                        .read_text(encoding='utf-8'), re.M)
    assert len(prints) == 3, f'unexpected print() call sites: {len(prints)}'
    assert 'str ( error )' not in code
    assert 'type ( error )' not in code, \
        'even an exception type is derived from the call that read the secret'
    # The value read at the prompt is wrapped immediately and never held as
    # a bare local string that a later line could interpolate.
    assert 'Secret ( getpass . getpass' in code


def test_the_setup_command_replaces_unexpected_interpolated_tokens(capsys):
    from backend import gmail_setup
    gmail_setup._report('secret', SENTINEL_CLIENT_SECRET)
    output = capsys.readouterr().out
    assert SENTINEL_CLIENT_SECRET not in output
    assert 'UNKNOWN' in output
    # Allowlisted state words pass through unchanged.
    gmail_setup._report('secret', 'CONFIGURED')
    assert 'CONFIGURED' in capsys.readouterr().out


def test_no_schema_column_can_hold_the_client_secret():
    columns = set(accounts.GmailAccount.__table__.columns.keys())
    for forbidden in ('client_secret', 'secret', 'client_credential'):
        assert forbidden not in columns


def test_the_setup_command_never_accepts_a_secret_as_an_argument(gmail_env, capsys):
    from backend import gmail_setup
    for argv in (['--secret=' + SENTINEL_CLIENT_SECRET],
                 ['--secret', SENTINEL_CLIENT_SECRET], ['--nonsense']):
        assert gmail_setup.main(argv) == 2
        output = capsys.readouterr().out
        assert SENTINEL_CLIENT_SECRET not in output
    assert accounts.client_secret_status()['state'] == 'NOT_CONFIGURED'


def test_the_setup_command_reports_bounded_status_and_removes(gmail_env, capsys):
    from backend import gmail_setup
    accounts.store_client_secret(oauth.Secret(SENTINEL_CLIENT_SECRET))
    assert gmail_setup.main(['--status']) == 0
    output = capsys.readouterr().out
    assert 'CONFIGURED' in output
    assert SENTINEL_CLIENT_SECRET not in output
    assert gmail_setup.main(['--remove']) == 0
    assert SENTINEL_CLIENT_SECRET not in capsys.readouterr().out
    assert accounts.client_secret_status()['state'] == 'NOT_CONFIGURED'


def test_the_setup_command_reads_only_from_a_hidden_console_prompt(monkeypatch, gmail_env, capsys):
    from backend import gmail_setup
    entered = {}

    def fake_getpass(prompt=''):
        entered['prompt'] = prompt
        return SENTINEL_CLIENT_SECRET

    monkeypatch.setattr(gmail_setup.getpass, 'getpass', fake_getpass)
    assert gmail_setup.main([]) == 0
    output = capsys.readouterr().out
    # getpass reads the console directly, so the value is never echoed and
    # cannot be piped in; and it is never printed back.
    assert SENTINEL_CLIENT_SECRET not in output
    assert 'hidden' in entered['prompt'].lower()
    assert accounts.read_client_secret().reveal() == SENTINEL_CLIENT_SECRET


def test_cancelling_the_setup_prompt_stores_nothing(monkeypatch, gmail_env):
    from backend import gmail_setup
    monkeypatch.setattr(gmail_setup.getpass, 'getpass', lambda prompt='': '   ')
    assert gmail_setup.main([]) == 1
    assert accounts.client_secret_status()['state'] == 'NOT_CONFIGURED'


# ===========================================================================
# Disconnect and revocation
# ===========================================================================
def test_disconnect_deletes_the_local_credential_on_successful_revocation(monkeypatch):
    connect_primary(monkeypatch)
    install_google_double(monkeypatch, revoke_status=200)
    result = accounts.disconnect('PRIMARY')
    assert result['local_disconnected'] is True
    assert result['remote_revocation'] == 'SUCCEEDED'
    assert _stored_credentials() == {}
    assert accounts.status()['accounts']['PRIMARY']['status'] == 'DISCONNECTED'


@pytest.mark.parametrize('failure,expected', [
    (400, 'FAILED'),
    (500, 'FAILED'),
    (oauth.OAuthError('REVOCATION_FAILED', 'A Google request timed out'), 'FAILED'),
    (httpx.ConnectError('dns failure'), 'FAILED'),
])
def test_local_disconnection_always_succeeds_and_reports_remote_failure_truthfully(
        monkeypatch, failure, expected):
    connect_primary(monkeypatch)
    install_google_double(monkeypatch, revoke_status=failure)
    result = accounts.disconnect('PRIMARY')
    assert result['local_disconnected'] is True
    assert result['remote_revocation'] == expected
    assert result['remote_revocation'] != 'SUCCEEDED'
    assert _stored_credentials() == {}, 'local access is removed regardless'
    row = _rows()[0]
    assert row.status == accounts.DISCONNECTED
    assert row.credential_key == '' and row.identity_key == ''
    assert row.last_remote_revocation == expected


def test_a_malformed_revocation_response_still_removes_local_access(monkeypatch):
    connect_primary(monkeypatch)

    def malformed(method, url, *, failure_code, total_timeout, data=None, bearer=None):
        return 200, 'text/html', b'<html>not json at all'

    monkeypatch.setattr(oauth, '_request', malformed)
    result = accounts.disconnect('PRIMARY')
    assert result['local_disconnected'] is True
    assert _stored_credentials() == {}


def test_revocation_sends_the_token_in_the_form_body_never_the_query(monkeypatch):
    connect_primary(monkeypatch)
    calls = install_google_double(monkeypatch, revoke_status=200)
    accounts.disconnect('PRIMARY')
    revocation = next(call for call in calls if call['url'] == oauth.REVOCATION_ENDPOINT)
    assert revocation['method'] == 'POST'
    assert revocation['data'] == {'token': SENTINEL_REFRESH}
    assert '?' not in revocation['url']
    assert SENTINEL_REFRESH not in revocation['url']


def test_disconnect_without_a_local_credential_reports_not_attempted():
    result = accounts.disconnect('PRIMARY')
    assert result['local_disconnected'] is True
    assert result['remote_revocation'] == 'NOT_ATTEMPTED_NO_LOCAL_CREDENTIAL'
    assert result['was_connected'] is False


def test_repeated_disconnect_is_idempotent(monkeypatch):
    connect_primary(monkeypatch)
    install_google_double(monkeypatch, revoke_status=200)
    first = accounts.disconnect('PRIMARY')
    second = accounts.disconnect('PRIMARY')
    third = accounts.disconnect('PRIMARY')
    assert first['remote_revocation'] == 'SUCCEEDED'
    assert second['remote_revocation'] == 'NOT_ATTEMPTED_NO_LOCAL_CREDENTIAL'
    assert second == third
    assert len(_rows()) == 1


def test_disconnect_leaves_the_other_slot_untouched(monkeypatch):
    connect_primary(monkeypatch)
    # Bind the secondary slot directly: the API gate blocks it, but the
    # storage model must still keep the two accounts isolated.
    accounts._bind_credential('SECONDARY',
                              {'authorized_email': OTHER_EMAIL,
                               'identity_key': oauth.normalize_identity(OTHER_EMAIL),
                               'identity_kind': 'GMAIL_PROFILE_EMAIL'},
                              [oauth.GMAIL_READONLY_SCOPE],
                              oauth.Secret('astra-sentinel-secondary-refresh-value'))
    secondary_key = next(row.credential_key for row in _rows() if row.slot == 'SECONDARY')
    install_google_double(monkeypatch, revoke_status=200)
    accounts.disconnect('PRIMARY')
    remaining = _stored_credentials()
    assert remaining == {secondary_key: 'astra-sentinel-secondary-refresh-value'}
    secondary = next(row for row in _rows() if row.slot == 'SECONDARY')
    assert secondary.status == accounts.CONNECTED
    assert secondary.authorized_email == OTHER_EMAIL


def test_a_failure_connecting_one_slot_never_alters_the_other(monkeypatch):
    connect_primary(monkeypatch)
    before = {row.slot: (row.status, row.credential_key, row.authorized_email)
              for row in _rows()}
    install_google_double(monkeypatch, profile={'emailAddress': 'bad'})
    with pytest.raises(oauth.OAuthError):
        accounts._finalize(attempt_id='x', slot='SECONDARY',
                           code=oauth.Secret(SENTINEL_CODE),
                           verifier=oauth.generate_code_verifier(),
                           redirect_uri='http://127.0.0.1:1/x')
    after = {row.slot: (row.status, row.credential_key, row.authorized_email)
             for row in _rows()}
    assert after == before


def test_disconnect_invalidates_a_pending_attempt(monkeypatch):
    connect_primary(monkeypatch)
    attempt, _url, listener, calls = start_attempt()
    state = attempt.state.reveal()
    install_google_double(monkeypatch, revoke_status=200)
    accounts.disconnect('PRIMARY')
    assert listener.is_closed is True
    assert oauth.attempts.status('PRIMARY')['result_code'] == 'INVALIDATED_BY_DISCONNECT'
    # The now-stale callback is rejected outright and reaches no exchange.
    assert listener.on_callback({'code': [SENTINEL_CODE], 'state': [state]}) is False
    assert calls == []
    assert oauth.attempts.status('PRIMARY')['result_code'] == 'CALLBACK_REPLAYED'


def test_disconnect_clears_only_that_accounts_sync_state(monkeypatch):
    connect_primary(monkeypatch)
    with Session.begin() as db:
        row = db.scalar(select(accounts.GmailAccount)
                        .where(accounts.GmailAccount.slot == 'PRIMARY'))
        row.sync_state = {'cursor': 'synthetic-placeholder'}
    install_google_double(monkeypatch, revoke_status=200)
    accounts.disconnect('PRIMARY')
    assert _rows()[0].sync_state == {}


def test_disconnect_never_touches_application_records(monkeypatch):
    from backend.models import Application, Job
    with Session.begin() as db:
        job = Job(company='Synthetic Employer', title='SOC Analyst')
        db.add(job)
        db.flush()
        db.add(Application(job_id=job.id, status='APPLIED', applied_date='2026-01-01',
                           confirmation='synthetic confirmation reference'))
        job_id = job.id
    connect_primary(monkeypatch)
    install_google_double(monkeypatch, revoke_status=200)
    accounts.disconnect('PRIMARY')
    with Session() as db:
        application = db.scalar(select(Application).where(Application.job_id == job_id))
        assert application is not None
        assert application.status == 'APPLIED'
        assert application.confirmation == 'synthetic confirmation reference'
        assert db.get(Job, job_id) is not None
    with Session.begin() as db:
        db.execute(__import__('sqlalchemy').delete(Application)
                   .where(Application.job_id == job_id))
        db.execute(__import__('sqlalchemy').delete(Job).where(Job.id == job_id))


def test_disconnect_removes_the_refresh_token_and_the_client_secret(monkeypatch, gmail_env):
    accounts.store_client_secret(oauth.Secret(SENTINEL_CLIENT_SECRET))
    connect_primary(monkeypatch)
    assert _stored_credentials(), 'connected with a stored refresh token'
    assert accounts.client_secret_status()['state'] == 'CONFIGURED'
    install_google_double(monkeypatch, revoke_status=200)
    result = accounts.disconnect('PRIMARY')
    assert result['local_disconnected'] is True
    assert result['credential_removal_complete'] is True
    assert result['credential_removal_incomplete'] == []
    assert result['credential_removal']['access_token'] == 'NEVER_STORED'
    assert result['credential_removal']['credential_entry_absent_after'] is True
    assert result['credential_removal']['client_secret_absent_after'] is True
    assert _stored_credentials() == {}
    assert accounts.client_secret_status()['state'] == 'NOT_CONFIGURED'
    # No Gmail OAuth material of any kind is left in either namespace.
    assert not [key for key in gmail_env.store
                if key[0] in (accounts.CREDENTIAL_SERVICE,
                              accounts.CLIENT_CREDENTIAL_SERVICE)]


def test_disconnect_retains_the_shared_secret_while_another_account_is_connected(
        monkeypatch, gmail_env):
    """The client credential is shared, so it outlives one slot's disconnect."""
    accounts.store_client_secret(oauth.Secret(SENTINEL_CLIENT_SECRET))
    connect_primary(monkeypatch)
    accounts._bind_credential('SECONDARY',
                              {'authorized_email': OTHER_EMAIL,
                               'identity_key': oauth.normalize_identity(OTHER_EMAIL),
                               'identity_kind': 'GMAIL_PROFILE_EMAIL'},
                              [oauth.GMAIL_READONLY_SCOPE],
                              oauth.Secret('astra-sentinel-secondary-refresh'))
    install_google_double(monkeypatch, revoke_status=200)
    result = accounts.disconnect('PRIMARY')
    assert result['credential_removal']['client_secret'] == \
        'RETAINED_ANOTHER_ACCOUNT_CONNECTED'
    assert accounts.client_secret_status()['state'] == 'CONFIGURED'
    # Disconnecting the last account then clears it.
    result = accounts.disconnect('SECONDARY')
    assert result['credential_removal']['client_secret_absent_after'] is True
    assert accounts.client_secret_status()['state'] == 'NOT_CONFIGURED'


def test_a_partial_credential_removal_failure_is_reported_and_bounded(
        monkeypatch, gmail_env):
    """A store that refuses deletion must not be reported as fully cleaned."""
    accounts.store_client_secret(oauth.Secret(SENTINEL_CLIENT_SECRET))
    connect_primary(monkeypatch)
    install_google_double(monkeypatch, revoke_status=200)
    gmail_env.fail_delete = True
    result = accounts.disconnect('PRIMARY')
    # Local access is still gone -- the row is disconnected and its key
    # cleared, so nothing can find the residue -- but the report is honest
    # that removal could not be confirmed.
    assert result['local_disconnected'] is True
    assert result['credential_removal_complete'] is False
    assert set(result['credential_removal_incomplete']) == {
        'credential_entry_absent_after', 'client_secret_absent_after'}
    assert accounts.status()['accounts']['PRIMARY']['status'] == 'DISCONNECTED'
    payload = json.dumps(result)
    assert SENTINEL_CLIENT_SECRET not in payload
    assert SENTINEL_REFRESH not in payload
    assert 'synthetic keyring' not in payload, 'no store error text leaks'


def test_full_local_deletion_also_removes_the_client_secret(monkeypatch, tmp_path, gmail_env):
    import backend.privacy as privacy
    accounts.store_client_secret(oauth.Secret(SENTINEL_CLIENT_SECRET))
    connect_primary(monkeypatch)
    monkeypatch.setattr(privacy, 'DATA', tmp_path)
    monkeypatch.setattr(privacy, 'delete_credential', lambda name: None)
    privacy.delete_data(privacy.DeleteRequest(
        scope='all', confirmation='DELETE ALL LOCAL DATA'))
    assert accounts.client_secret_status()['state'] == 'NOT_CONFIGURED'
    assert _stored_credentials() == {}


def test_an_unknown_slot_cannot_be_disconnected():
    with pytest.raises(oauth.OAuthError) as raised:
        accounts.disconnect('TERTIARY')
    assert raised.value.code == 'UNKNOWN_ACCOUNT_SLOT'


# ===========================================================================
# Schema and status
# ===========================================================================
def test_the_schema_initialization_is_additive_and_idempotent():
    from sqlalchemy import inspect
    from backend.models import engine
    accounts.initialize_gmail_schema()
    accounts.initialize_gmail_schema()      # repeatable, no error
    inspector = inspect(engine)
    assert 'gmail_accounts' in inspector.get_table_names()
    indexes = {index['name'] for index in inspector.get_indexes('gmail_accounts')}
    assert {'uq_gmail_account_identity', 'uq_gmail_account_credential'} <= indexes
    # Every pre-existing table still exists: nothing was renamed or dropped.
    for table in ('jobs', 'applications', 'job_observations', 'settings',
                  'automation_runs', 'application_events'):
        assert table in inspector.get_table_names()


def test_models_py_is_not_modified_by_this_feature():
    """backend/models.py is a SHA-256-pinned #42 evaluation-provenance input.

    Issue #44 adds its table from backend/gmail_accounts.py precisely so
    that manifest stays valid; this asserts the boundary explicitly.
    """
    import hashlib
    import pathlib
    manifest = json.loads(pathlib.Path(
        'docs/evaluation/fit_evaluation_provenance_v1.json').read_text(encoding='utf-8'))
    pinned = {item['path']: item['sha256'] for item in manifest['inputs']}
    assert 'backend/models.py' in pinned
    content = pathlib.Path('backend/models.py').read_bytes().replace(b'\r\n', b'\n')
    assert hashlib.sha256(content).hexdigest() == pinned['backend/models.py']
    assert 'gmail' not in pathlib.Path('backend/models.py').read_text(encoding='utf-8').lower()


def test_status_is_read_only_on_a_database_without_the_table(monkeypatch):
    """`backend.doctor` must never create schema, so status must tolerate
    a pre-#44 database the application has not started against yet."""
    monkeypatch.setattr(accounts, 'schema_ready', lambda: False)
    state = accounts.status()
    assert state['schema'] == 'NOT_INITIALIZED'
    assert state['accounts']['PRIMARY']['status'] == accounts.DISCONNECTED
    assert state['accounts']['SECONDARY']['gate_code'] == 'SECONDARY_NOT_ENABLED'
    # The diagnostic surface reports it as a bounded state, not an error.
    from backend.doctor import run_checks
    gmail = next(check for check in run_checks()
                 if check['check'] == 'gmail_integration')
    assert gmail['status'] == 'PASS'
    assert 'primary=DISCONNECTED' in gmail['detail']


def test_status_reports_both_slots_the_gate_and_no_secret(monkeypatch):
    connect_primary(monkeypatch)
    state = accounts.status()
    payload = json.dumps(state)
    for secret in (SENTINEL_REFRESH, SENTINEL_ACCESS, SENTINEL_CODE,
                   SYNTHETIC_CLIENT_ID):
        assert secret not in payload
    assert state['accounts']['PRIMARY']['status'] == 'CONNECTED'
    assert state['accounts']['PRIMARY']['authorized_email'] == SYNTHETIC_EMAIL
    assert state['accounts']['SECONDARY']['enabled'] is False
    assert state['accounts']['SECONDARY']['gate_code'] == 'SECONDARY_NOT_ENABLED'
    assert state['credential_store'] == {'state': 'OS_SECURE_STORE', 'detail_code': 'OK'}
    assert state['read_only'] is True
    assert state['requested_scopes'] == [oauth.GMAIL_READONLY_SCOPE]
    # No token field at all, not even as a null placeholder. Compared against
    # the actual key names rather than as substrings, so a legitimate key
    # such as `detail_code` does not mask a real `code` field.
    for forbidden in ('refresh_token', 'access_token', 'token', 'code', 'client_id',
                      'credential_key', 'authorization_url',
                      'identity_key', 'code_verifier', 'code_challenge',
                      'oauth_state', 'redirect_uri'):
        assert forbidden not in _all_keys(state)
    # `state` appears only as bounded configuration/store state, never as an
    # OAuth state value.
    assert state['configuration']['state'] in ('CONFIGURED', 'NOT_CONFIGURED', 'INVALID')
    # `client_secret` is a key, but it carries only bounded state -- never a
    # value, and nothing that describes one.
    assert set(state['client_secret']) <= {'state', 'detail_code', 'setup_command'}
    assert state['client_secret']['state'] in ('CONFIGURED', 'NOT_CONFIGURED',
                                               'UNAVAILABLE')
    assert SENTINEL_CLIENT_SECRET not in json.dumps(state)


def _all_keys(value):
    """Every mapping key anywhere in a nested structure."""
    found = set()
    if isinstance(value, dict):
        for key, nested in value.items():
            found.add(key)
            found |= _all_keys(nested)
    elif isinstance(value, (list, tuple)):
        for nested in value:
            found |= _all_keys(nested)
    return found


def test_metadata_without_its_credential_reports_inconsistent_not_connected(monkeypatch, gmail_env):
    connect_primary(monkeypatch)
    gmail_env.store.clear()          # e.g. a restored database, or a cleared profile
    state = accounts.status()
    assert state['accounts']['PRIMARY']['status'] == 'DISCONNECTED_INCONSISTENT'
    assert state['accounts']['PRIMARY']['status'] != 'CONNECTED'


def test_connected_status_appears_only_after_both_writes_succeed(monkeypatch):
    observed = []
    install_google_double(monkeypatch)
    real_write = accounts.write_credential

    def observing_write(credential_key, refresh_token):
        real_write(credential_key, refresh_token)
        # Between the credential write and the metadata write the account
        # must not yet be reported as connected.
        observed.append(accounts.status()['accounts']['PRIMARY']['status'])

    monkeypatch.setattr(accounts, 'write_credential', observing_write)
    attempt, _url, listener, _calls = start_attempt(finalizer=accounts._finalize)
    assert listener.on_callback(callback_query(attempt)) is True
    assert observed == ['DISCONNECTED']
    assert accounts.status()['accounts']['PRIMARY']['status'] == 'CONNECTED'


def test_the_gmail_client_wrapper_exposes_no_mutating_operation():
    """ADR-0008: read-only is enforced in code, not only by the scope."""
    import pathlib
    source = (pathlib.Path('backend/gmail_oauth.py').read_text(encoding='utf-8')
              + pathlib.Path('backend/gmail_accounts.py').read_text(encoding='utf-8')
              + pathlib.Path('backend/gmail_api.py').read_text(encoding='utf-8'))
    # No Gmail API path other than the profile lookup exists in the module
    # at all, so no code path can call a mutating operation.
    for mutating in ('messages/send', 'messages/trash', 'messages/delete',
                     'messages/modify', 'messages/batchModify', '/labels',
                     'users/me/messages', 'users/me/threads', 'users/me/history',
                     'users/me/drafts', 'users/me/settings', '/watch', '/stop'):
        assert mutating not in source
    # The profile lookup is the only Gmail API URL anywhere in the feature.
    assert set(re.findall(r'https://gmail\.googleapis\.com[^\'"\s]*', source)) == \
        {'https://gmail.googleapis.com/gmail/v1/users/me/profile'}
    assert set(re.findall(r'/gmail/v1/[^\'"\s]*', source)) == \
        {'/gmail/v1/users/me/profile'}
    assert oauth.PROFILE_ENDPOINT.endswith('/users/me/profile')
