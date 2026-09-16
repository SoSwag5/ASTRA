"""Gmail OAuth 2.0 authorization mechanics for ASTRA (issue #44).

This module owns *only* the standards flow and its transport: fixed Google
endpoints, PKCE (S256), single-use cryptographic `state`, an ephemeral
loopback callback listener, the authorization-code exchange, granted-scope
validation, the authorized-identity lookup, and token revocation.  It holds
no database knowledge -- `backend.gmail_accounts` supplies the finalizer
that binds a validated credential to an account record, so this module can
be exercised in isolation.

Implements ADR-0007 (Gmail OAuth and credential storage).  ADR-0007 being
`Accepted` is an architecture decision, never evidence a control exists;
the controls below are the implementation, and their negative tests live in
`tests/test_gmail_oauth.py` / `tests/security/test_gmail_oauth_secrets.py`.

Secret handling rules enforced here, per ADR-0007 and issue #44:

- Authorization codes, PKCE verifiers, `state`, access tokens and refresh
  tokens are **never** logged, persisted, returned in an API model, or
  placed in an exception message.  Every one of them is carried in a
  `Secret` wrapper whose `repr`/`str` redact the value, so an accidental
  f-string, container dump or traceback cannot expose it.
- The attempt store is process memory only.  Restarting ASTRA therefore
  invalidates every pending authorization attempt, by construction.
- Outbound calls go to fixed HTTPS constants with certificate verification
  on, redirects disabled, environment proxies ignored, bounded deadlines
  and bounded response bytes.  The authorization-code exchange is never
  retried: codes are single-use and an ambiguous retry could produce a
  confusing or unsafe outcome.

Official Google references verified for this implementation (2026-09-16):
installed-app OAuth
<https://developers.google.com/identity/protocols/oauth2/native-app>,
Gmail scopes
<https://developers.google.com/workspace/gmail/api/auth/scopes>,
token revocation
<https://developers.google.com/identity/protocols/oauth2/web-server#tokenrevoke>,
Gmail profile
<https://developers.google.com/workspace/gmail/api/reference/rest/v1/users/getProfile>.

Version-pin note: `_FixedHostBackend` relies on
`httpcore.ConnectionPool(network_backend=...)` being an accepted
constructor argument and on `httpx.HTTPTransport`'s `_pool` attribute
being the object whose `handle_request`/`close` it inherits -- the same
documented reliance `backend/job_providers/transport.py` already carries,
verified against httpx==0.28.1 / httpcore==1.0.9 and asserted by
`test_oauth_transport_dependency_versions_are_pinned`.
"""
import base64
import hashlib
import ipaddress
import json as json_module
import os
import re
import secrets
import ssl
import threading
import time
import zlib
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, HTTPServer
from urllib.parse import urlencode, urlsplit, parse_qs

import httpcore
import httpx

PINNED_HTTPX_VERSION = '0.28.1'
PINNED_HTTPCORE_VERSION = '1.0.9'

# ---------------------------------------------------------------------------
# Fixed Google endpoints and scope. Never caller-controlled, never read from
# configuration or a request body: a caller that could choose the token or
# authorization endpoint could redirect a credential to a host of its choice.
# ---------------------------------------------------------------------------
AUTHORIZATION_ENDPOINT = 'https://accounts.google.com/o/oauth2/v2/auth'
TOKEN_ENDPOINT = 'https://oauth2.googleapis.com/token'
REVOCATION_ENDPOINT = 'https://oauth2.googleapis.com/revoke'
PROFILE_ENDPOINT = 'https://gmail.googleapis.com/gmail/v1/users/me/profile'

GMAIL_READONLY_SCOPE = 'https://www.googleapis.com/auth/gmail.readonly'
#: Exactly what ASTRA requests, and exactly what a granted token must carry.
#: ADR-0008 forbids any mutating Gmail capability; a broader granted scope is
#: rejected before a credential is stored rather than silently accepted.
REQUESTED_SCOPES = (GMAIL_READONLY_SCOPE,)
REQUIRED_SCOPES = frozenset(REQUESTED_SCOPES)

ALLOWED_HOSTS = frozenset({'accounts.google.com', 'oauth2.googleapis.com',
                           'gmail.googleapis.com'})

CALLBACK_PATH = '/astra/gmail/oauth2/callback'
LOOPBACK_ADDRESS = '127.0.0.1'

ACCOUNT_SLOTS = ('PRIMARY', 'SECONDARY')
#: OD-012 / ADR-0007: architect for two accounts, activate the primary only.
ENABLED_SLOTS = frozenset({'PRIMARY'})

ATTEMPT_TTL_SECONDS = 300          # <= 5 minutes, per issue #44
CALLBACK_POLL_SECONDS = 0.25
LISTENER_SOCKET_TIMEOUT = 5.0
MAX_REQUEST_LINE_BYTES = 2048
MAX_REQUEST_HEADERS = 32
MAX_CALLBACK_QUERY_BYTES = 4096

CONNECT_TIMEOUT = 10.0
READ_TIMEOUT = 20.0
TOTAL_TIMEOUT = 30.0
REVOCATION_TOTAL_TIMEOUT = 8.0
MAX_RESPONSE_BYTES = 262_144

#: Installed-app client IDs are configuration, not secrets (Google's own
#: guidance for native apps), but they are still validated strictly and
#: length-bounded so a malformed or oversized value fails closed instead of
#: being sent to Google.
CLIENT_ID_ENVIRONMENT_VARIABLE = 'ASTRA_GMAIL_CLIENT_ID'
CLIENT_ID_MAX_LENGTH = 200
CLIENT_ID_PATTERN = re.compile(
    r'^[0-9]{6,32}-[a-z0-9_-]{8,64}\.apps\.googleusercontent\.com$')

#: The three parameters ASTRA's security decisions actually depend on. Each
#: must appear at most once; a duplicate makes the callback ambiguous and is
#: rejected rather than resolved by picking one.
SINGLE_VALUE_CALLBACK_PARAMETERS = ('state', 'code', 'error')

#: Non-secret metadata Google may attach to an authorization response.
#: These are tolerated and then ignored -- they never influence a security
#: decision.
#:
#: RFC 6749 section 4.1.2 requires a client to ignore unrecognized response
#: parameters, and Google's OpenID Connect documentation repeats that
#: requirement verbatim ("clients MUST ignore unrecognized response
#: parameters"). Google's installed-app documentation only promises `code`/
#: `error` plus `state`, and does not enumerate the additional metadata it
#: actually sends, so the real set is wider than the documented minimum --
#: which is exactly what live validation of issue #44 discovered. This list
#: is therefore the union of what Google and the relevant specifications
#: document: the OAuth/OIDC authorization-response fields (`scope`,
#: `session_state`, `nonce`, `expires_in`, error metadata), Google's
#: incremental-authorization and account-selection echoes
#: (`granted_scopes`, `authuser`, `prompt`, `hd`, `login_hint`,
#: `approval_prompt`), and RFC 9207 issuer identification (`iss`).
ALLOWED_CALLBACK_METADATA = frozenset({
    'scope', 'granted_scopes', 'authuser', 'prompt', 'hd', 'login_hint',
    'approval_prompt', 'session_state', 'iss', 'nonce', 'expires_in',
    'error_description', 'error_subtype', 'error_uri',
})

#: Names that must never appear in an authorization-code callback query.
#: A bearer credential or a PKCE verifier arriving here means the flow is
#: not the one ASTRA started (an implicit-flow response, a redirect from a
#: different client, or an injection attempt), so it is refused outright
#: rather than ignored as unrecognized metadata.
FORBIDDEN_CALLBACK_PARAMETERS = frozenset({
    'access_token', 'id_token', 'refresh_token', 'token', 'token_type',
    'client_secret', 'code_verifier', 'assertion', 'password',
})

#: Every name the callback may carry. Anything outside this set is rejected:
#: ASTRA tolerates documented metadata, never arbitrary unknown parameters.
ALLOWED_CALLBACK_PARAMETERS = (frozenset(SINGLE_VALUE_CALLBACK_PARAMETERS)
                               | ALLOWED_CALLBACK_METADATA)

#: A callback carrying an implausible number of parameters is refused before
#: any of them is inspected.
MAX_CALLBACK_PARAMETERS = 24

_PERCENT_ENCODING = re.compile(r'%(?![0-9A-Fa-f]{2})')


class Secret:
    """A value that must never be printed, logged, or serialized.

    `repr`/`str`/`format` all redact, so the value cannot leak through an
    f-string, a container dump (`repr` of a dict/list/dataclass calls
    `repr` on its members), a logging call, or a traceback that renders an
    argument.  `reveal()` is the single, greppable place a caller opts in
    to the raw value.

    Python cannot cryptographically wipe memory and this makes no such
    claim -- `clear()` only drops this object's reference so the value
    becomes collectable sooner.
    """
    __slots__ = ('_value',)
    REDACTED = '<redacted secret>'

    def __init__(self, value):
        if not isinstance(value, str):
            raise TypeError('Secret wraps a string value')
        self._value = value

    def reveal(self):
        if self._value is None:
            raise ValueError('This secret has already been cleared')
        return self._value

    def clear(self):
        self._value = None

    def __repr__(self):
        return self.REDACTED

    __str__ = __repr__

    def __format__(self, spec):
        return self.REDACTED

    def __len__(self):
        return len(self._value or '')

    def __bool__(self):
        return bool(self._value)


class OAuthError(ValueError):
    """A bounded, secret-free OAuth failure.

    `code` is a stable token safe to log, record as a security event, and
    return to the local frontend.  `message` is text ASTRA itself authored
    -- never a raw Google response, never a URL with query values, and
    never a token, code, verifier or state value.
    """

    def __init__(self, code, message):
        super().__init__(message)
        self.code = code


def _now():
    return datetime.now(timezone.utc).isoformat()


# ---------------------------------------------------------------------------
# Client configuration
# ---------------------------------------------------------------------------
def client_id():
    """The configured installed-app client ID, or None when unset.

    Raises OAuthError for a present-but-invalid value so a typo fails
    closed with a clear status instead of being forwarded to Google.
    """
    raw = os.getenv(CLIENT_ID_ENVIRONMENT_VARIABLE, '').strip()
    if not raw:
        return None
    if len(raw) > CLIENT_ID_MAX_LENGTH or not CLIENT_ID_PATTERN.fullmatch(raw):
        raise OAuthError('CLIENT_ID_INVALID',
                         'The configured Gmail OAuth client ID is not a valid '
                         'Google installed-app client ID. Re-copy it from your '
                         'dedicated ASTRA Google Cloud project.')
    return raw


def configuration_status():
    """Bounded, secret-free configuration state for the status API.

    The client ID itself is never returned: it is configuration rather
    than a secret, but it identifies the Owner's Google Cloud project and
    has no purpose in an API response or a log line.
    """
    try:
        configured = client_id()
    except OAuthError as error:
        return {'state': 'INVALID', 'detail_code': error.code}
    return {'state': 'CONFIGURED' if configured else 'NOT_CONFIGURED',
            'detail_code': 'OK' if configured else 'CLIENT_NOT_CONFIGURED',
            'environment_variable': CLIENT_ID_ENVIRONMENT_VARIABLE,
            'client_secret_required': False}


def require_client_id():
    configured = client_id()
    if not configured:
        raise OAuthError('CLIENT_NOT_CONFIGURED',
                         'Set the Gmail OAuth client ID for your dedicated '
                         'ASTRA Google Cloud project before connecting Gmail.')
    return configured


def require_enabled_slot(slot):
    """Validate an account slot and enforce the primary-only activation gate."""
    if slot not in ACCOUNT_SLOTS:
        raise OAuthError('UNKNOWN_ACCOUNT_SLOT', 'Unknown Gmail account slot')
    if slot not in ENABLED_SLOTS:
        raise OAuthError('SECONDARY_NOT_ENABLED',
                         'The second Gmail account is not enabled yet. The '
                         'primary account is validated end to end first '
                         '(Owner Decision OD-012).')
    return slot


# ---------------------------------------------------------------------------
# PKCE and state
# ---------------------------------------------------------------------------
def generate_code_verifier():
    """An RFC 7636 code verifier.

    `token_urlsafe(64)` yields ~86 characters drawn from the unreserved
    set `[A-Za-z0-9_-]`, inside RFC 7636's 43..128 length range, with 512
    bits of entropy.
    """
    return Secret(secrets.token_urlsafe(64))


def code_challenge(verifier):
    """The S256 challenge: base64url(SHA-256(verifier)) without padding."""
    digest = hashlib.sha256(verifier.reveal().encode('ascii')).digest()
    return base64.urlsafe_b64encode(digest).rstrip(b'=').decode('ascii')


def generate_state():
    """A single-use CSRF/binding nonce with 256 bits of entropy."""
    return Secret(secrets.token_urlsafe(32))


def authorization_url(*, configured_client_id, redirect_uri, state, verifier):
    """Build Google's authorization URL from fixed constants only.

    The verifier never appears -- only its S256 challenge does.  Nothing
    in this URL is caller-supplied except the loopback port ASTRA itself
    just bound.
    """
    parameters = {
        'client_id': configured_client_id,
        'redirect_uri': redirect_uri,
        'response_type': 'code',
        'scope': ' '.join(REQUESTED_SCOPES),
        'state': state.reveal(),
        'code_challenge': code_challenge(verifier),
        'code_challenge_method': 'S256',
        # Offline access is what yields a refresh token at all.
        'access_type': 'offline',
        # Force an explicit account choice and an explicit consent screen:
        # `select_account` keeps the two-account model unambiguous, and
        # `consent` guarantees Google returns a refresh token rather than
        # silently reusing a prior grant.
        'prompt': 'consent select_account',
        # Never silently inherit scopes this client was granted earlier.
        'include_granted_scopes': 'false',
    }
    return AUTHORIZATION_ENDPOINT + '?' + urlencode(parameters)


# ---------------------------------------------------------------------------
# Loopback callback listener
# ---------------------------------------------------------------------------
_SUCCESS_PAGE = (b'<!doctype html><meta charset="utf-8"><title>ASTRA</title>'
                 b'<p>Gmail authorization received. Return to ASTRA to finish '
                 b'connecting this account. You can close this tab.</p>')
_FAILURE_PAGE = (b'<!doctype html><meta charset="utf-8"><title>ASTRA</title>'
                 b'<p>This authorization response was not accepted. Return to '
                 b'ASTRA and start the connection again. You can close this '
                 b'tab.</p>')


class _CallbackHandler(BaseHTTPRequestHandler):
    """Accepts exactly one well-formed GET on the fixed callback path.

    The response body is static: it never reflects a query value, an
    account identity, or an error detail, so the page cannot echo an
    authorization code or `state` back into the page, the browser cache,
    or the browser history of a shared machine.
    """
    protocol_version = 'HTTP/1.0'   # no keep-alive holding the listener open
    timeout = LISTENER_SOCKET_TIMEOUT
    server_version = 'ASTRA'
    sys_version = ''

    def log_message(self, format, *args):
        """Silence the default handler log.

        BaseHTTPRequestHandler would otherwise write the full request
        line -- including the authorization code and `state` in the query
        string -- to stderr.  Nothing about this request is ever logged.
        """

    def parse_request(self):
        if len(self.raw_requestline) > MAX_REQUEST_LINE_BYTES:
            self.requestline = ''
            self.request_version = 'HTTP/1.0'
            self.command = 'GET'
            self.send_error(414)
            return False
        if not super().parse_request():
            return False
        if len(self.headers) > MAX_REQUEST_HEADERS:
            self.send_error(431)
            return False
        return True

    def _respond(self, status, body):
        self.send_response(status)
        self.send_header('Content-Type', 'text/html; charset=utf-8')
        self.send_header('Content-Length', str(len(body)))
        self.send_header('Cache-Control', 'no-store')
        self.send_header('Referrer-Policy', 'no-referrer')
        self.send_header('X-Content-Type-Options', 'nosniff')
        self.send_header('Content-Security-Policy', "default-src 'none'")
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        split = urlsplit(self.path)
        if split.path != CALLBACK_PATH:
            self._respond(404, _FAILURE_PAGE)
            return
        if len(split.query) > MAX_CALLBACK_QUERY_BYTES:
            self.server.astra_reject('CALLBACK_INVALID')
            self._respond(414, _FAILURE_PAGE)
            return
        # A real OAuth redirect puts its parameters in the query string. A
        # fragment cannot be read server-side at all, so a request-target
        # fragment is either a malformed client or an attempt to smuggle
        # parameters past this validation.
        if split.fragment or not split.query:
            self.server.astra_reject('CALLBACK_INVALID')
            self._respond(400, _FAILURE_PAGE)
            return
        # Strict parsing refuses empty fields and name-only fields; the
        # pattern check refuses a stray '%' that is not a valid escape.
        # Neither is something Google's redirect produces.
        if _PERCENT_ENCODING.search(split.query):
            self.server.astra_reject('CALLBACK_MALFORMED_QUERY')
            self._respond(400, _FAILURE_PAGE)
            return
        try:
            parameters = parse_qs(split.query, keep_blank_values=True,
                                  strict_parsing=True)
        except ValueError:
            self.server.astra_reject('CALLBACK_MALFORMED_QUERY')
            self._respond(400, _FAILURE_PAGE)
            return
        accepted = self.server.astra_callback(parameters)
        self._respond(200 if accepted else 400,
                      _SUCCESS_PAGE if accepted else _FAILURE_PAGE)

    def do_POST(self):
        # Google's loopback redirect is a GET. Anything else is rejected
        # without touching attempt state.
        self._respond(405, _FAILURE_PAGE)

    do_PUT = do_DELETE = do_PATCH = do_HEAD = do_OPTIONS = do_POST


class _CallbackServer(HTTPServer):
    allow_reuse_address = False   # never silently share a port with another socket

    def __init__(self, on_callback, on_reject):
        super().__init__((LOOPBACK_ADDRESS, 0), _CallbackHandler)
        self.astra_callback = on_callback
        self.astra_reject = on_reject

    def handle_error(self, request, client_address):
        """Swallow per-connection errors without printing a traceback.

        The default implementation writes the traceback to stderr, which
        on this socket could render request data.
        """


class CallbackListener:
    """A short-lived HTTP listener bound to loopback on an ephemeral port.

    Binds only to the numeric loopback address `127.0.0.1` with port 0
    (kernel-assigned ephemeral port) -- never `0.0.0.0`, a hostname
    wildcard, a LAN address, or ASTRA's own API port.  It serves at most
    one accepted callback and closes immediately on success, terminal
    failure, cancellation or the authorization deadline.
    """

    def __init__(self, on_callback):
        self._on_callback = on_callback
        self._terminal = threading.Event()
        self._server = _CallbackServer(self._handle, self._reject)
        self._server.timeout = CALLBACK_POLL_SECONDS
        self.port = self._server.server_address[1]
        self.redirect_uri = f'http://{LOOPBACK_ADDRESS}:{self.port}{CALLBACK_PATH}'
        self._thread = None

    @property
    def bound_address(self):
        return self._server.server_address[0]

    def _handle(self, parameters):
        accepted = bool(self._on_callback(parameters))
        # One valid callback only: whatever the outcome, this listener is
        # finished. A replay therefore cannot even reach the consume step.
        self._terminal.set()
        return accepted

    def _reject(self, _code):
        self._terminal.set()

    def serve(self, deadline):
        """Serve until a callback arrives, the deadline passes, or close().

        `close()` can be called from another thread at any moment -- a
        superseded attempt, a cancellation, or a disconnect all do that --
        including while this thread is blocked selecting on the socket.
        Once the socket is closed underneath it, `handle_request()` raises
        on the stale descriptor, so that is caught and treated as the stop
        signal it is, rather than escaping and printing a traceback (which
        on this socket could render request data).
        """
        try:
            while not self._terminal.is_set() and time.monotonic() < deadline:
                try:
                    self._server.handle_request()
                except (OSError, ValueError):
                    break
        finally:
            self.close()

    def start(self, deadline):
        self._thread = threading.Thread(target=self.serve, args=(deadline,),
                                        name='astra-gmail-oauth-callback',
                                        daemon=True)
        self._thread.start()
        return self.redirect_uri

    def close(self):
        self._terminal.set()
        try:
            self._server.server_close()
        except OSError:
            pass

    def closed(self):
        return self._server.fileno() == -1


# ---------------------------------------------------------------------------
# Hardened outbound transport
# ---------------------------------------------------------------------------
class _FixedHostBackend(httpcore.NetworkBackend):
    """Only ever dials a fixed Google host on 443, over a global address.

    The authoritative control that a request cannot be answered by some
    other endpoint is TLS certificate verification against the fixed
    hostname (enabled, with the system trust store).  This backend adds
    two cheap, non-blocking checks on top: the requested host must be one
    of ASTRA's three fixed Google hosts, and the address actually
    connected to must be globally routable -- so a poisoned DNS answer or
    a hosts-file entry pointing at loopback, a private range, or a cloud
    metadata address is refused at connect time rather than relying on
    the TLS handshake alone.  No extra DNS lookup is performed, so there
    is no unbounded resolution step.
    """

    def __init__(self):
        self._inner = httpcore.SyncBackend()

    def connect_tcp(self, host, port, timeout=None, local_address=None,
                    socket_options=None):
        if host not in ALLOWED_HOSTS or port != 443:
            raise OAuthError('DESTINATION_NOT_ALLOWED',
                             'Gmail OAuth requests only ever contact Google '
                             'over HTTPS')
        stream = self._inner.connect_tcp(
            host, port, timeout=timeout if timeout is not None else CONNECT_TIMEOUT,
            local_address=local_address, socket_options=socket_options)
        sock = stream.get_extra_info('socket')
        try:
            peer = sock.getpeername()[0] if sock is not None else None
        except OSError:
            peer = None
        if peer is not None:
            try:
                routable = ipaddress.ip_address(peer).is_global
            except ValueError:
                routable = False
            if not routable:
                stream.close()
                raise OAuthError('DESTINATION_NOT_ALLOWED',
                                 'A Gmail OAuth endpoint resolved to a '
                                 'non-routable address and was refused')
        return stream

    def connect_unix_socket(self, path, timeout=None, socket_options=None):
        raise OAuthError('DESTINATION_NOT_ALLOWED',
                         'Unix sockets are never used for Gmail OAuth')

    def sleep(self, seconds):
        self._inner.sleep(seconds)


class _PinnedTransport(httpx.HTTPTransport):
    def __init__(self):
        self._pool = httpcore.ConnectionPool(
            ssl_context=ssl.create_default_context(),
            network_backend=_FixedHostBackend(),
            retries=0,
            max_connections=4,
        )


def _client(total_timeout):
    """An httpx client that cannot be redirected, proxied, or retried.

    - `trust_env=False` ignores `HTTPS_PROXY`/`HTTP_PROXY`/`NO_PROXY` and
      any `SSLKEYLOGFILE`: a credential exchange never inherits an
      ambient proxy, and ASTRA has no approved proxy policy.
    - `follow_redirects=False` means a 3xx is a bounded error, never a
      hop to another destination.
    - `verify` defaults to the standard certificate verification of the
      SSL context built above; it is never disabled.
    """
    return httpx.Client(
        transport=_PinnedTransport(),
        trust_env=False,
        follow_redirects=False,
        timeout=httpx.Timeout(connect=min(CONNECT_TIMEOUT, total_timeout),
                              read=min(READ_TIMEOUT, total_timeout),
                              write=min(READ_TIMEOUT, total_timeout),
                              pool=min(CONNECT_TIMEOUT, total_timeout)),
        headers={'User-Agent': 'ASTRA/1.1 personal-career-assistant',
                 'Accept': 'application/json',
                 'Accept-Encoding': 'identity'},
    )


def _read_bounded(response, failure_code):
    """Read at most MAX_RESPONSE_BYTES of wire bytes, then decode them.

    `iter_raw()` is used rather than `iter_bytes()` so the cap applies to
    the bytes actually on the wire, before any expansion -- httpx's
    decoding stream would happily inflate a small compressed body past
    the cap first. That means this function owns the `Content-Encoding`
    step itself.
    """
    raw = bytearray()
    for chunk in response.iter_raw():
        raw.extend(chunk)
        if len(raw) > MAX_RESPONSE_BYTES:
            raise OAuthError(failure_code,
                             'A Google response exceeded the allowed size')
    return _decode_body(bytes(raw), response.headers.get('content-encoding', ''),
                        failure_code)


def _decode_body(raw, encoding, failure_code):
    """Decode a Content-Encoding body within the same size bound.

    ASTRA asks for `Accept-Encoding: identity` because an uncompressed
    token/profile/revocation response has no downside and keeps this path
    trivial. That is a preference, not a guarantee: a server may compress
    anyway, and issue #44's live validation showed how that ends --
    `json.loads` on still-compressed bytes fails, and the whole exchange
    reports a bounded transport failure with no way to see why. So the
    encodings a server may legitimately choose are decoded here, and
    anything else is refused.

    Decompression is bounded the same way the provider transport bounds
    it (`backend/job_providers/transport.py`): output is capped by
    `decompress(max_length=...)`, a non-empty `unconsumed_tail` means the
    cap was hit, and the total is re-checked after `flush()`. A small
    compressed body cannot expand into an unbounded allocation.
    """
    name = (encoding or '').strip().lower()
    if name in ('', 'identity'):
        return raw
    if name not in ('gzip', 'deflate'):
        raise OAuthError(failure_code,
                         'A Google response used an unsupported content-encoding')
    # gzip has its own header; `deflate` is sent both zlib-wrapped and raw
    # in the wild, so both window settings are tried.
    windows = [zlib.MAX_WBITS | 16] if name == 'gzip' else [zlib.MAX_WBITS,
                                                            -zlib.MAX_WBITS]
    for wbits in windows:
        decompressor = zlib.decompressobj(wbits)
        try:
            decoded = decompressor.decompress(raw, MAX_RESPONSE_BYTES + 1)
            if decompressor.unconsumed_tail:
                raise OAuthError(failure_code,
                                 'A Google response exceeded the allowed size')
            decoded += decompressor.flush()
        except OAuthError:
            raise
        except zlib.error:
            continue
        if len(decoded) > MAX_RESPONSE_BYTES:
            raise OAuthError(failure_code,
                             'A Google response exceeded the allowed size')
        return decoded
    raise OAuthError(failure_code, 'A Google response could not be decompressed')


def _strict_json_object(body, failure_code):
    try:
        parsed = json_module.loads(body)
    except ValueError:
        raise OAuthError(failure_code, 'A Google response was not valid JSON') from None
    if not isinstance(parsed, dict):
        raise OAuthError(failure_code, 'A Google response had an unexpected shape')
    return parsed


def _request(method, url, *, failure_code, total_timeout, data=None, bearer=None):
    """One bounded, non-redirecting HTTPS request to a fixed Google URL.

    Never logs the request or the response, never puts a token in a query
    string, and never lets a raw upstream body or header reach an
    exception message.
    """
    if urlsplit(url).hostname not in ALLOWED_HOSTS or not url.startswith('https://'):
        raise OAuthError('DESTINATION_NOT_ALLOWED',
                         'Gmail OAuth requests only ever contact Google over HTTPS')
    # The client secret authenticates ASTRA to exactly one endpoint. This is
    # the single chokepoint every outbound call passes through, so the
    # restriction is enforced here rather than trusted to each caller: a
    # future call site cannot send it to the profile or revocation endpoint
    # even by mistake.
    if isinstance(data, dict) and 'client_secret' in data and url != TOKEN_ENDPOINT:
        raise OAuthError('DESTINATION_NOT_ALLOWED',
                         'Client authentication is only ever sent to Google\'s '
                         'token endpoint')
    headers = {}
    if bearer is not None:
        headers['Authorization'] = 'Bearer ' + bearer.reveal()
    try:
        with _client(total_timeout) as client:
            with client.stream(method, url, data=data, headers=headers) as response:
                if response.is_redirect:
                    raise OAuthError(failure_code,
                                     'A Google endpoint attempted a redirect, '
                                     'which is not followed for credentials')
                status = response.status_code
                content_type = response.headers.get('content-type', '')
                body = _read_bounded(response, failure_code)
    except OAuthError:
        raise
    except httpx.TimeoutException:
        raise OAuthError(failure_code, 'A Google request timed out') from None
    except httpx.HTTPError:
        raise OAuthError(failure_code, 'A Google request could not be completed') from None
    return status, content_type, body


#: Standard OAuth 2.0 error identifiers (RFC 6749 section 5.2) mapped to
#: bounded ASTRA codes and actionable messages. Only these fixed tokens are
#: ever read from an error response -- `error_description` is free text that
#: can restate the request, so it is never parsed, surfaced or logged.
_OAUTH_ERROR_CODES = {
    'invalid_client': ('CLIENT_AUTHENTICATION_REQUIRED',
                       'Google rejected ASTRA\'s client authentication. Check '
                       'the configured Gmail client secret and try again.'),
    'unauthorized_client': ('CLIENT_AUTHENTICATION_REQUIRED',
                            'Google rejected ASTRA\'s client authentication. '
                            'Check the configured Gmail client secret and try '
                            'again.'),
    'invalid_request': ('CLIENT_AUTHENTICATION_REQUIRED',
                        'Google rejected the request. If Gmail has never '
                        'connected on this machine, configure the Gmail client '
                        'secret for your OAuth client, then try again.'),
    'invalid_grant': ('AUTHORIZATION_EXPIRED',
                      'Google would not accept this authorization. Start the '
                      'connection again.'),
    'unsupported_grant_type': ('AUTHORIZATION_EXPIRED',
                               'Google would not accept this authorization. '
                               'Start the connection again.'),
    'invalid_scope': ('SCOPE_MISSING_REQUIRED',
                      'Google did not grant Gmail read-only access. Connect '
                      'again and approve the read-only permission.'),
}


def _standard_oauth_error(body):
    """The RFC 6749 `error` identifier, if the body carries a known one.

    Returns a bounded (code, message) pair or None. Nothing else from the
    response is read, so no free text can escape.
    """
    try:
        parsed = json_module.loads(body)
    except ValueError:
        return None
    if not isinstance(parsed, dict):
        return None
    identifier = parsed.get('error')
    if not isinstance(identifier, str):
        return None
    return _OAUTH_ERROR_CODES.get(identifier.strip().lower())


def _json_request(method, url, *, failure_code, total_timeout, data=None, bearer=None):
    status, content_type, body = _request(
        method, url, failure_code=failure_code, total_timeout=total_timeout,
        data=data, bearer=bearer)
    if status != 200:
        # Google's own error *text* is never surfaced: it can restate the
        # request. Its standard `error` identifier is a fixed token from a
        # closed set, so it is mapped to a bounded ASTRA code that tells the
        # user what to actually do -- which is what the opaque failure
        # during live validation could not.
        mapped = _standard_oauth_error(body)
        if mapped is not None:
            raise OAuthError(*mapped)
        raise OAuthError(failure_code,
                         'Google rejected the request. Start the connection again.')
    if 'application/json' not in content_type.lower():
        raise OAuthError(failure_code, 'A Google response was not JSON')
    return _strict_json_object(body, failure_code)


def exchange_code(*, configured_client_id, code, verifier, redirect_uri,
                  client_secret=None):
    """Exchange a single-use authorization code for tokens.

    Never retried. The redirect URI is byte-identical to the one used in
    the authorization request, and the PKCE verifier is sent exactly once.

    `client_secret` is included only when one is configured. Google's
    installed-app documentation marks it optional, but live validation of
    issue #44 proved this Desktop client enforces client authentication at
    the token endpoint before it evaluates the grant at all: without a
    secret it answered `400 invalid_request` naming the missing secret,
    and with a deliberately wrong one `401 invalid_client`. PKCE is still
    sent and still required -- the secret authenticates the client, it
    does not replace proof of possession.
    """
    payload = {
        'client_id': configured_client_id,
        'code': code.reveal(),
        'code_verifier': verifier.reveal(),
        'grant_type': 'authorization_code',
        'redirect_uri': redirect_uri,
    }
    if client_secret is not None:
        payload['client_secret'] = client_secret.reveal()
    parsed = _json_request('POST', TOKEN_ENDPOINT, failure_code='TOKEN_EXCHANGE_FAILED',
                           total_timeout=TOTAL_TIMEOUT, data=payload)
    access = parsed.get('access_token')
    if not isinstance(access, str) or not access.strip():
        raise OAuthError('ACCESS_TOKEN_MISSING',
                         'Google did not return a usable access token')
    scope = parsed.get('scope')
    if not isinstance(scope, str):
        raise OAuthError('TOKEN_RESPONSE_INVALID',
                         'Google did not report the granted scope')
    refresh = parsed.get('refresh_token')
    if refresh is not None and not isinstance(refresh, str):
        raise OAuthError('TOKEN_RESPONSE_INVALID',
                         'Google returned an unexpected refresh-token field')
    # Only these three values are carried forward. The raw response object
    # is deliberately dropped here so nothing else in it can be logged,
    # persisted, or attached to an error.
    return {
        'access_token': Secret(access),
        'refresh_token': Secret(refresh) if refresh and refresh.strip() else None,
        'granted_scopes': normalize_scopes(scope),
    }


def refresh_access_token(*, configured_client_id, refresh_token, client_secret=None):
    """Exchange a stored refresh token for a short-lived access token.

    This is the credential layer completing its own contract: it proves a
    stored refresh token is usable, and it is what makes a revoked
    credential verifiably unusable. It performs **no** mailbox work -- no
    message listing, no history sync, no parsing -- so issue #45 remains
    unstarted; #45 will call this rather than reinvent it.

    Returns a memory-only access token and the scopes Google reports for
    it. The granted scope is re-validated by the caller on every refresh,
    so a grant that widened after the fact cannot be used silently.
    """
    payload = {
        'client_id': configured_client_id,
        'grant_type': 'refresh_token',
        'refresh_token': refresh_token.reveal(),
    }
    if client_secret is not None:
        payload['client_secret'] = client_secret.reveal()
    parsed = _json_request('POST', TOKEN_ENDPOINT, failure_code='TOKEN_REFRESH_FAILED',
                           total_timeout=TOTAL_TIMEOUT, data=payload)
    access = parsed.get('access_token')
    if not isinstance(access, str) or not access.strip():
        raise OAuthError('ACCESS_TOKEN_MISSING',
                         'Google did not return a usable access token')
    # A refresh response omits `scope` when the grant is unchanged, which is
    # not an error -- the caller then relies on the scope recorded at
    # connection time, which was validated then.
    scope = parsed.get('scope')
    if scope is not None and not isinstance(scope, str):
        raise OAuthError('TOKEN_RESPONSE_INVALID',
                         'Google reported an unexpected granted scope')
    return {'access_token': Secret(access),
            'granted_scopes': normalize_scopes(scope) if scope else None}


def normalize_scopes(scope):
    """A sorted, de-duplicated, non-secret list of granted scope strings."""
    return sorted({part for part in (scope or '').split(' ') if part})


def validate_granted_scopes(granted):
    """Reject a token that is missing `gmail.readonly` or carries more.

    ASTRA never relies on what it requested: this inspects what Google
    actually granted.  A broader-than-requested grant stops the flow
    before any credential is stored, per ADR-0008.
    """
    actual = set(granted)
    if not REQUIRED_SCOPES.issubset(actual):
        raise OAuthError('SCOPE_MISSING_REQUIRED',
                         'Google did not grant Gmail read-only access. Connect '
                         'again and approve the read-only permission.')
    extra = actual - REQUIRED_SCOPES
    if extra:
        raise OAuthError('SCOPE_BROADER_THAN_REQUESTED',
                         'Google granted more access than ASTRA requested. '
                         'Nothing was stored. Remove ASTRA from your Google '
                         'account permissions and connect again.')
    return sorted(actual)


_EMAIL_PATTERN = re.compile(r'^[^\s@]{1,64}@[A-Za-z0-9.-]{1,255}$')


def normalize_identity(email):
    """Derive the uniqueness key for an authorized mailbox address.

    Only the domain is lowercased (DNS is case-insensitive).  The local
    part is left byte-identical: dot- and plus-folding are Gmail-specific
    delivery conveniences, and applying them would change mailbox
    identity semantics -- wrongly merging two genuinely distinct
    mailboxes on a Google Workspace domain.  This rule is documented in
    `docs/architecture/GMAIL_OAUTH.md`.
    """
    local, _, domain = email.rpartition('@')
    return local + '@' + domain.lower()


def fetch_authorized_identity(access_token):
    """Ask Gmail who the token actually belongs to (`userId=me`).

    This is the authoritative identity: never the address the user typed,
    never a login hint, never a UI selection.  Only the address is kept --
    `messagesTotal`, `threadsTotal` and `historyId` are not needed to
    prove identity and are deliberately dropped, and no message or thread
    data is requested or stored (ADR-0008, and `threadId` is never
    persisted per Owner Decision 6).

    Known contract limitation, verified against Google's published
    `users.getProfile` reference: at `gmail.readonly` the response carries
    **no opaque immutable subject identifier** -- only `emailAddress`.
    ASTRA therefore records the authenticated address as the account
    identity and labels it `GMAIL_PROFILE_EMAIL`, rather than inventing a
    stable identifier or requesting an OpenID/`userinfo.email` scope just
    to obtain one (issue #44 forbids both).  See the residual-limitation
    note in `docs/architecture/GMAIL_OAUTH.md`.
    """
    parsed = _json_request('GET', PROFILE_ENDPOINT, failure_code='IDENTITY_LOOKUP_FAILED',
                           total_timeout=TOTAL_TIMEOUT, bearer=access_token)
    email = parsed.get('emailAddress')
    if not isinstance(email, str):
        raise OAuthError('IDENTITY_RESPONSE_INVALID',
                         'Google did not return the authorized Gmail address')
    email = email.strip()
    if not email or len(email) > 320 or not _EMAIL_PATTERN.fullmatch(email):
        raise OAuthError('IDENTITY_RESPONSE_INVALID',
                         'Google returned an unusable Gmail address')
    return {'authorized_email': email,
            'identity_key': normalize_identity(email),
            'identity_kind': 'GMAIL_PROFILE_EMAIL'}


def revoke_refresh_token(refresh_token):
    """Best-effort Google-side revocation. Returns SUCCEEDED or FAILED.

    The token goes in the form body, never the query string.  Every
    failure mode -- DNS, TLS, timeout, an error status, a malformed body
    -- returns FAILED rather than raising, because local disconnection
    must proceed regardless and must never be reported as a remote
    success that did not happen.  There is no retry loop.
    """
    try:
        status, _content_type, _body = _request(
            'POST', REVOCATION_ENDPOINT, failure_code='REVOCATION_FAILED',
            total_timeout=REVOCATION_TOTAL_TIMEOUT,
            data={'token': refresh_token.reveal()})
    except OAuthError:
        return 'FAILED'
    except Exception:
        # Revocation is best-effort by design; nothing here may escape and
        # block the local deletion that follows.
        return 'FAILED'
    return 'SUCCEEDED' if status == 200 else 'FAILED'


# ---------------------------------------------------------------------------
# In-memory authorization attempts
# ---------------------------------------------------------------------------
#: Terminal statuses. PENDING is the only resumable one, and only in this
#: process: the store below is memory-only, so a restart leaves nothing.
PENDING = 'PENDING'
COMPLETED = 'COMPLETED'
FAILED = 'FAILED'


class _Attempt:
    """One authorization attempt. Holds only what the flow requires."""
    __slots__ = ('attempt_id', 'slot', 'state', 'verifier', 'redirect_uri',
                 'listener', 'created_at', 'expires_at', 'deadline',
                 'status', 'result_code', 'consumed')

    def __init__(self, slot):
        self.attempt_id = secrets.token_urlsafe(12)
        self.slot = slot
        self.state = generate_state()
        self.verifier = generate_code_verifier()
        self.redirect_uri = ''
        self.listener = None
        self.created_at = _now()
        self.expires_at = time.monotonic() + ATTEMPT_TTL_SECONDS
        self.deadline = self.expires_at
        self.status = PENDING
        self.result_code = 'AWAITING_GOOGLE'
        self.consumed = False

    def expired(self):
        return time.monotonic() >= self.expires_at

    def public(self):
        """Bounded, secret-free status for the API and the UI."""
        remaining = (max(0, int(self.expires_at - time.monotonic()))
                     if self.status is PENDING else 0)
        return {'attempt_id': self.attempt_id, 'slot': self.slot,
                'status': self.status, 'result_code': self.result_code,
                'created_at': self.created_at, 'expires_in_seconds': remaining}

    def discard(self):
        """Drop the secrets this attempt held and close its listener."""
        self.state.clear()
        self.verifier.clear()
        if self.listener is not None:
            self.listener.close()


class AttemptManager:
    """Process-memory store of pending authorization attempts.

    At most one attempt per account slot: starting a new one supersedes
    and discards the old one, so a stale `state` can never complete a
    flow.  A callback is consumed atomically under the lock *before* any
    token exchange happens, which is what makes a replayed callback
    unable to trigger a second exchange.  Nothing here is ever written to
    disk, so restarting ASTRA invalidates every pending attempt.
    """

    def __init__(self):
        self._lock = threading.Lock()
        self._attempts = {}          # attempt_id -> _Attempt (PENDING only)
        self._by_slot = {}           # slot -> attempt_id
        # The last terminal outcome per slot, so a UI polling just after
        # completion sees the real result instead of "no attempt". Bounded
        # by the number of slots and holds no secret.
        self._finished = {}          # slot -> bounded public status

    # -- lifecycle ---------------------------------------------------------
    def start(self, slot, finalizer, *, listener_factory=CallbackListener):
        """Create an attempt, bind a loopback listener, and return it.

        `finalizer(attempt_id, slot, code, verifier, redirect_uri)` runs on
        the listener thread once a callback is accepted, and returns a
        bounded result code.
        """
        configured = require_client_id()
        require_enabled_slot(slot)
        attempt = _Attempt(slot)
        try:
            listener = listener_factory(
                lambda parameters: self._on_callback(
                    attempt.attempt_id, slot, parameters, finalizer))
        except OSError:
            attempt.discard()
            raise OAuthError('LISTENER_UNAVAILABLE',
                             'A local callback port could not be opened. Close '
                             'other applications and try again.') from None
        attempt.listener = listener
        attempt.redirect_uri = listener.redirect_uri
        with self._lock:
            self._supersede(slot)
            self._finished.pop(slot, None)
            self._attempts[attempt.attempt_id] = attempt
            self._by_slot[slot] = attempt.attempt_id
        listener.start(attempt.deadline)
        # Recorded here rather than in the service layer so every path that
        # opens an attempt leaves the same audit trail.
        from .security_events import record
        record('GMAIL_OAUTH_ATTEMPT_STARTED', slot=slot, result='STARTED')
        url = authorization_url(configured_client_id=configured,
                                redirect_uri=attempt.redirect_uri,
                                state=attempt.state, verifier=attempt.verifier)
        return attempt, url

    def _supersede(self, slot):
        """Invalidate the slot's previous attempt. Caller holds the lock."""
        previous_id = self._by_slot.pop(slot, None)
        previous = self._attempts.pop(previous_id, None) if previous_id else None
        if previous is not None:
            previous.status = FAILED
            previous.result_code = 'SUPERSEDED'
            previous.discard()

    def _retire(self, slot, attempt, status, result_code):
        """Move an attempt to its terminal state. Caller holds the lock."""
        self._attempts.pop(attempt.attempt_id, None)
        if self._by_slot.get(slot) == attempt.attempt_id:
            self._by_slot.pop(slot, None)
        attempt.status = status
        attempt.result_code = result_code
        record = attempt.public()
        self._finished[slot] = record
        return record

    def cancel(self, slot):
        with self._lock:
            attempt_id = self._by_slot.get(slot)
            attempt = self._attempts.get(attempt_id) if attempt_id else None
            if attempt is None:
                return self._finished.get(slot)
            result = self._retire(slot, attempt, FAILED, 'CANCELLED')
        attempt.discard()
        return result

    def status(self, slot):
        """Bounded status for a slot, expiring a stale attempt as it reads."""
        expired = None
        with self._lock:
            attempt_id = self._by_slot.get(slot)
            attempt = self._attempts.get(attempt_id) if attempt_id else None
            if attempt is None:
                return self._finished.get(slot)
            if attempt.status is PENDING and attempt.expired():
                result = self._retire(slot, attempt, FAILED, 'EXPIRED')
                expired = attempt
            else:
                result = attempt.public()
        if expired is not None:
            expired.discard()
        return result

    def finish(self, slot, attempt_id, status, result_code):
        """Record a terminal outcome and release the attempt's secrets.

        Always leaves a bounded terminal record for the slot, including
        when the attempt was already superseded or expired, so the caller
        never has to invent a status.
        """
        attempt = None
        with self._lock:
            attempt = self._attempts.get(attempt_id)
            if attempt is not None:
                record = self._retire(slot, attempt, status, result_code)
            else:
                record = {'attempt_id': attempt_id, 'slot': slot, 'status': status,
                          'result_code': result_code, 'created_at': _now(),
                          'expires_in_seconds': 0}
                self._finished[slot] = record
        if attempt is not None:
            attempt.discard()
        return record

    def invalidate_slot(self, slot, result_code='INVALIDATED'):
        """Drop any pending attempt for a slot (used by disconnect)."""
        with self._lock:
            attempt_id = self._by_slot.get(slot)
            attempt = self._attempts.get(attempt_id) if attempt_id else None
            if attempt is None:
                return False
            self._retire(slot, attempt, FAILED, result_code)
        attempt.discard()
        return True

    def pending_slots(self):
        with self._lock:
            return sorted(self._by_slot)

    # -- callback handling -------------------------------------------------
    def _consume(self, attempt_id, state_value):
        """Atomically claim an attempt for exactly one callback.

        Returns the attempt on success.  The comparison is constant-time
        and the `consumed` flag is set under the same lock acquisition, so
        two concurrent callbacks cannot both proceed to a token exchange.
        """
        with self._lock:
            attempt = self._attempts.get(attempt_id)
            if attempt is None or attempt.status is not PENDING or attempt.consumed:
                return None, 'CALLBACK_REPLAYED'
            if attempt.expired():
                return None, 'ATTEMPT_EXPIRED'
            if not isinstance(state_value, str) or not secrets.compare_digest(
                    state_value.encode('utf-8'), attempt.state.reveal().encode('utf-8')):
                return None, 'CALLBACK_STATE_MISMATCH'
            attempt.consumed = True
            return attempt, 'OK'

    def _on_callback(self, attempt_id, slot, parameters, finalizer):
        """Validate a callback's shape, then consume it and finalize.

        Returns True only when the whole flow succeeded, so the static
        page the browser sees distinguishes accepted from rejected without
        revealing why.
        """
        code_value, state_value, reject = _validate_callback(parameters)
        if reject is not None:
            self._reject(slot, attempt_id, reject)
            return False
        attempt, outcome = self._consume(attempt_id, state_value)
        if attempt is None:
            self._reject(slot, attempt_id, outcome)
            return False
        code = Secret(code_value)
        try:
            result_code = finalizer(attempt_id=attempt.attempt_id, slot=attempt.slot,
                                    code=code, verifier=attempt.verifier,
                                    redirect_uri=attempt.redirect_uri)
        except OAuthError as error:
            self.finish(slot, attempt_id, FAILED, error.code)
            return False
        except Exception:
            # Never let an unexpected internal failure surface a token, a
            # code, or a stack trace. The attempt ends bounded and failed.
            self.finish(slot, attempt_id, FAILED, 'CONNECTION_FAILED')
            return False
        finally:
            code.clear()
        connected = result_code == 'CONNECTED'
        self.finish(slot, attempt_id, COMPLETED if connected else FAILED, result_code)
        return connected

    def _reject(self, slot, attempt_id, code):
        from .security_events import record
        record('GMAIL_OAUTH_CALLBACK_REJECTED', slot=slot, result=code)
        self.finish(slot, attempt_id, FAILED, code)


def _validate_callback(parameters):
    """Structural validation of the loopback callback query.

    Rejects duplicate, missing, malformed, oversized, forbidden and
    unexpected parameters.  `state` and PKCE are the security controls
    here -- the browser's `Origin`/`Referer` headers are deliberately not
    consulted, because Google's redirect carries neither reliably and
    neither is authority for an OAuth callback.

    Parameter policy (three tiers, not one):

    1. `state`, `code` and `error` drive every security decision, so each
       may appear at most once and `state` must always be present.
    2. `ALLOWED_CALLBACK_METADATA` is documented non-secret metadata:
       tolerated, then ignored. RFC 6749 section 4.1.2 and Google's own
       OIDC documentation both require a client to ignore unrecognized
       response parameters, and live validation of issue #44 confirmed
       Google sends more of them than its installed-app page enumerates.
    3. `FORBIDDEN_CALLBACK_PARAMETERS` and anything not listed at all are
       refused. Tolerating documented metadata is not the same as
       accepting arbitrary unknown parameters, and this keeps the
       difference explicit.
    """
    if not isinstance(parameters, dict):
        return None, None, 'CALLBACK_INVALID'
    if not parameters or len(parameters) > MAX_CALLBACK_PARAMETERS:
        return None, None, 'CALLBACK_INVALID'
    names = set(parameters)
    # A credential or a PKCE verifier in the query is never "unrecognized
    # metadata" -- it means this is not the flow ASTRA started.
    if names & FORBIDDEN_CALLBACK_PARAMETERS:
        return None, None, 'CALLBACK_FORBIDDEN_PARAMETER'
    if names - ALLOWED_CALLBACK_PARAMETERS:
        return None, None, 'CALLBACK_UNEXPECTED_PARAMETER'
    for name in SINGLE_VALUE_CALLBACK_PARAMETERS:
        if len(parameters.get(name, [])) > 1:
            return None, None, 'CALLBACK_DUPLICATE_PARAMETER'
    state_values = parameters.get('state', [])
    if len(state_values) != 1 or not state_values[0]:
        return None, None, 'CALLBACK_STATE_MISSING'
    error_values = parameters.get('error', [])
    code_values = parameters.get('code', [])
    if error_values:
        if code_values:
            return None, None, 'CALLBACK_INVALID'
        # Google's error string is never reflected into the page, a log,
        # or a security event -- only this bounded code is.
        return None, None, 'CALLBACK_PROVIDER_ERROR'
    if len(code_values) != 1 or not code_values[0] or len(code_values[0]) > 2048:
        return None, None, 'CALLBACK_MISSING_CODE'
    return code_values[0], state_values[0], None


#: The single process-wide attempt store. Recreated on every start of the
#: process, which is what makes a restart invalidate pending attempts.
attempts = AttemptManager()
