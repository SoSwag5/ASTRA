"""Minimal local API for the Gmail OAuth credential layer (issue #44).

Every route here is mounted on the same FastAPI app as the rest of ASTRA's
private API, so it inherits the existing boundary controls unchanged
(`backend/main.py::guard`): loopback-only peers, the TrustedHost allowlist,
the Origin allowlist, `Sec-Fetch-Site: cross-site` rejection, the
`Sec-Fetch-Dest` browser-navigation block, the optional access-key session,
bounded request size, and `Cache-Control: no-store` on every response.  No
control is weakened or bypassed for OAuth.

Contract rules this router enforces:

- State-changing operations are POST or DELETE, never GET.
- A caller cannot choose a callback host, a Google endpoint, a scope, a
  client ID or a credential key -- the slot is the only input, and it is
  validated against a fixed two-value enum.
- No response carries a token, an authorization code, a PKCE value, a
  `state` value, a raw Google error, or a token field as a null
  placeholder. Errors are stable bounded codes.
- The authorization URL is returned once to the trusted local frontend so
  it can open the system browser. It is never logged and never stored.
"""
from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import JSONResponse

from . import gmail_accounts as accounts
from . import gmail_oauth as oauth
from . import gmail_sync as sync
from . import gmail_messages as messages
from .gmail_oauth import ACCOUNT_SLOTS, OAuthError

router = APIRouter(prefix='/api/gmail')

#: Path slugs accepted for an account slot. A caller cannot name anything
#: outside this fixed map.
_SLUGS = {slot.lower(): slot for slot in ACCOUNT_SLOTS}


def _slot(slug):
    slot = _SLUGS.get(slug.lower()) if isinstance(slug, str) and len(slug) <= 16 else None
    if slot is None:
        raise HTTPException(404, 'Unknown Gmail account slot')
    return slot


def _bounded_error(error):
    """Map a bounded OAuth failure to a bounded HTTP response.

    The body is built from the failure's stable **code** only, and its
    text comes from `oauth.message_for()` -- ASTRA's authored message
    table. `str(error)` is deliberately never used: exception-derived
    data must not reach a response body at all, so a Google payload, a
    URL with query values, an exception chain or a future message that
    embedded something sensitive cannot leak through this path. CodeQL's
    `py/stack-trace-exposure` rule flagged the earlier `str(error)`
    version on exactly that basis.
    """
    code = error.code if error.code in oauth.MESSAGES or error.code in messages.READ_ERROR_CODES else 'UNKNOWN_ERROR'
    status = 409 if code in ('SECONDARY_NOT_ENABLED', 'IDENTITY_ALREADY_CONNECTED', 'SYNC_ALREADY_RUNNING') else 400
    if error.code in ('CLIENT_NOT_CONFIGURED', 'CLIENT_ID_INVALID',
                      'CREDENTIAL_STORE_UNAVAILABLE'):
        status = 503
    detail = messages.message_for(code) if code in messages.READ_ERROR_CODES else oauth.message_for(code)
    return JSONResponse({'detail': detail,
                         'code': code}, status,
                        headers={'Cache-Control': 'no-store'})


@router.get('/status')
def gmail_status():
    """Read the Gmail connection status. No secret, no token field.

    `OAuthError` subclasses `ValueError`, and ASTRA's global handler
    returns `str(exc)` for a `ValueError`. Catching it here keeps every
    Gmail failure on the bounded-code path instead of letting an
    exception message become a response body.
    """
    try:
        return accounts.status()
    except OAuthError as error:
        return _bounded_error(error)


@router.post('/accounts/{slug}/authorize')
def start_authorization(slug: str):
    """Start an authorization attempt and return the Google consent URL."""
    slot = _slot(slug)
    try:
        return accounts.start_authorization(slot)
    except OAuthError as error:
        return _bounded_error(error)


@router.get('/accounts/{slug}/authorize')
def authorization_status(slug: str):
    """Bounded pending/terminal status for a slot's attempt."""
    slot = _slot(slug)
    try:
        return {'slot': slot, 'enabled': slot in oauth.ENABLED_SLOTS,
                'attempt': oauth.attempts.status(slot)}
    except OAuthError as error:
        return _bounded_error(error)


@router.post('/accounts/{slug}/authorize/cancel')
def cancel_authorization(slug: str):
    """Cancel a pending attempt. Idempotent."""
    slot = _slot(slug)
    try:
        return {'slot': slot, 'cancelled': True,
                'attempt': accounts.cancel_authorization(slot)}
    except OAuthError as error:
        return _bounded_error(error)


@router.post('/accounts/{slug}/disconnect')
def disconnect_account(slug: str):
    """Disconnect one account, reporting local and remote results apart.

    POST rather than DELETE, matching every other state-changing route in
    ASTRA (`/api/privacy/delete` included): the shared guard middleware
    requires a bounded `Content-Length` on non-GET requests, which a
    browser `fetch` does not reliably send for a bodyless DELETE.  Using
    POST keeps the existing boundary control intact instead of relaxing it
    for this one route.
    """
    slot = _slot(slug)
    try:
        return accounts.disconnect(slot)
    except OAuthError as error:
        return _bounded_error(error)


@router.get('/sync/status')
def sync_status():
    try:
        return sync.sync_status()
    except Exception:
        return _bounded_error(OAuthError('GMAIL_SYNC_FAILED', 'Unavailable'))


@router.get('/confirmations')
def confirmations(limit: int = Query(default=50, ge=1, le=200)):
    try:
        return sync.list_confirmations(limit=limit)
    except Exception:
        return _bounded_error(OAuthError('GMAIL_SYNC_FAILED', 'Unavailable'))


@router.post('/accounts/{slug}/sync')
def synchronize(slug: str):
    slot = _slot(slug)
    # Coordinate with deletion, exports, discovery and other processes.
    from .main import task_lock
    if not task_lock.acquire(False):
        return _bounded_error(OAuthError('SYNC_ALREADY_RUNNING', 'Busy'))
    try:
        return sync.sync_account(slot)
    except OAuthError as error:
        return _bounded_error(error)
    finally:
        task_lock.release()
