"""Gmail account records, OS-backed credential storage, connect/disconnect.

Issue #44 / ADR-0007.  This module owns three things:

1. `GmailAccount` -- the **non-secret** per-account metadata row.  No token,
   code, verifier, `state`, raw token response, client secret, Gmail
   message, subject, sender, history value or `threadId` is ever stored
   here (Owner Decision 6 and 9).  Because ASTRA's private export dumps
   every mapped table (`backend/privacy.py`) and the daily backup copies
   the SQLite file verbatim, "no secret in this table" *is* the control
   that keeps refresh tokens out of exports and backups.
2. The refresh-token credential store: the existing native OS-backed
   keyring, under a dedicated service namespace separate from the OpenAI
   credential, with no plaintext fallback of any kind.
3. The connect/disconnect services, including their ordering and the
   compensating delete that keeps a credential and its metadata row from
   drifting apart.

Why the model lives here and not in `backend/models.py`: `models.py` is a
SHA-256-pinned input of issue #42's evaluation provenance manifest
(`docs/evaluation/fit_evaluation_provenance_v1.json`), enforced by
`tests/test_fit_evaluation.py`.  Editing it would invalidate #42's
durable provenance, which PROJECT_STATE.md reserves for a separate
Owner-authorized regeneration.  Issue #43 set the same precedent by
leaving the pinned `backend/recall.py` untouched.  This module therefore
declares its table against the shared `Base` and owns its own idempotent,
additive schema initialization -- no existing table, column or index is
altered, so an existing database upgrades by gaining one new table.
"""
import os
import secrets
import threading

from sqlalchemy import JSON, Index, select, text
from sqlalchemy.orm import Mapped, mapped_column

from .models import Base, Record, Session, engine, now
from . import gmail_oauth as oauth
from .gmail_oauth import ACCOUNT_SLOTS, OAuthError, Secret
from .security_events import record as security_event

#: Dedicated credential namespace. Deliberately NOT 'LocalJobHunter' (the
#: OpenAI key's service name), so Gmail credentials are independently
#: enumerable, independently deletable, and can never be confused with or
#: overwritten by the existing AI-provider credential.
CREDENTIAL_SERVICE = 'ASTRA-Gmail-OAuth'
#: The OAuth *client* secret lives in its own keyring service, deliberately
#: separate from the per-account refresh tokens in CREDENTIAL_SERVICE. They
#: are different kinds of secret with different lifetimes: the client
#: credential belongs to the installation's OAuth client and is shared by
#: every account slot, while a refresh token belongs to one mailbox. Keeping
#: them in separate namespaces means neither can be read, overwritten or
#: deleted while operating on the other, and an audit of either namespace is
#: unambiguous.
CLIENT_CREDENTIAL_SERVICE = 'ASTRA-Gmail-OAuth-Client'
CLIENT_SECRET_KEY = 'client-secret'
#: Google client secrets are short; this only bounds obvious paste errors.
CLIENT_SECRET_MAX_LENGTH = 512
#: On Windows this is keyring's native Credential Manager backend, which
#: protects the secret with DPAPI under the *current user* profile --
#: never machine-wide. ADR-0007 requires CurrentUser scope explicitly.
WINDOWS_NATIVE_BACKEND = 'keyring.backends.Windows'

CONNECTED = 'CONNECTED'
DISCONNECTED = 'DISCONNECTED'

REMOTE_SUCCEEDED = 'SUCCEEDED'
REMOTE_FAILED = 'FAILED'
REMOTE_NOT_ATTEMPTED = 'NOT_ATTEMPTED_NO_LOCAL_CREDENTIAL'

#: Serializes connect-finalization and disconnect per process so a start and
#: a disconnect racing on the same slot cannot interleave their credential
#: and metadata writes.
_slot_locks = {slot: threading.Lock() for slot in ACCOUNT_SLOTS}


class GmailAccount(Record, Base):
    """Non-secret connection metadata for one Gmail account slot.

    Uniqueness is enforced on `slot` for every row, and on `identity_key`
    and `credential_key` for *connected* rows only (partial unique
    indexes).  That keeps a disconnected tombstone -- which clears both
    keys so nothing points at a deleted credential -- from colliding with
    another tombstone, while still making it impossible for two connected
    records to share one mailbox identity or one credential entry.
    """
    __tablename__ = 'gmail_accounts'

    slot: Mapped[str] = mapped_column(unique=True)
    status: Mapped[str] = mapped_column(default=DISCONNECTED)
    #: The address Google's authenticated profile actually reported. Never
    #: the address the user intended, a login hint, or a UI selection.
    authorized_email: Mapped[str] = mapped_column(default='')
    identity_key: Mapped[str] = mapped_column(default='')
    #: 'GMAIL_PROFILE_EMAIL' -- see gmail_oauth.fetch_authorized_identity
    #: for why no opaque immutable provider identifier is available at the
    #: gmail.readonly scope.
    identity_kind: Mapped[str] = mapped_column(default='')
    granted_scopes: Mapped[list] = mapped_column(JSON, default=list)
    #: Opaque local handle for the keyring entry. Derived from the trusted
    #: local slot plus fresh local randomness -- never from the email
    #: address or any other externally supplied string, and never reused.
    credential_key: Mapped[str] = mapped_column(default='')
    connected_at: Mapped[str] = mapped_column(default='')
    last_validated_at: Mapped[str] = mapped_column(default='')
    disconnected_at: Mapped[str] = mapped_column(default='')
    last_remote_revocation: Mapped[str] = mapped_column(default='')
    #: Structural placeholder for issue #45's per-account sync cursor. It
    #: is account-scoped and always `{}` in #44 -- no mailbox state exists
    #: yet -- and disconnect clears it (ADR-0008).
    sync_state: Mapped[dict] = mapped_column(JSON, default=dict)

    __table_args__ = (
        Index('uq_gmail_account_identity', 'identity_key', unique=True,
              sqlite_where=text("status = 'CONNECTED'")),
        Index('uq_gmail_account_credential', 'credential_key', unique=True,
              sqlite_where=text("status = 'CONNECTED'")),
    )


def initialize_gmail_schema():
    """Create the Gmail account table and its partial unique indexes.

    Additive and idempotent: safe to call on every start and on an
    existing pre-#44 database.  It creates one new table and never
    touches an existing table, column, index or row, so there is no
    destructive migration step and no backfill.
    """
    Base.metadata.create_all(engine, tables=[GmailAccount.__table__])
    with engine.begin() as connection:
        # create_all() only emits __table_args__ indexes when it creates the
        # table itself, so ensure them explicitly for a database whose table
        # already existed.
        connection.execute(text(
            "CREATE UNIQUE INDEX IF NOT EXISTS uq_gmail_account_identity "
            "ON gmail_accounts (identity_key) WHERE status = 'CONNECTED'"))
        connection.execute(text(
            "CREATE UNIQUE INDEX IF NOT EXISTS uq_gmail_account_credential "
            "ON gmail_accounts (credential_key) WHERE status = 'CONNECTED'"))


# ---------------------------------------------------------------------------
# Credential storage
# ---------------------------------------------------------------------------
def credential_store():
    """The native OS credential store, or a hard failure.

    Reuses `backend.privacy.credential_backend()` so Gmail inherits the
    existing, tested fail-closed rule: only a native Windows/macOS/
    SecretService backend is accepted and there is no plaintext, file,
    environment-variable or in-database fallback.  On Windows the backend
    must additionally be the native Credential Manager one (DPAPI,
    CurrentUser), never a substitute.
    """
    from .privacy import credential_backend
    try:
        backend = credential_backend()
    except Exception:
        security_event('GMAIL_CREDENTIAL_STORE_FAILED', result='STORE_UNAVAILABLE')
        raise OAuthError('CREDENTIAL_STORE_UNAVAILABLE',
                         'A supported native OS credential store is '
                         'unavailable. ASTRA never falls back to storing a '
                         'Gmail token in plaintext.') from None
    module = type(backend).__module__
    if os.name == 'nt' and module != WINDOWS_NATIVE_BACKEND:
        security_event('GMAIL_CREDENTIAL_STORE_FAILED', result='STORE_NOT_NATIVE')
        raise OAuthError('CREDENTIAL_STORE_UNAVAILABLE',
                         'The Windows native credential store is unavailable. '
                         'ASTRA never falls back to storing a Gmail token in '
                         'plaintext.')
    return backend


def credential_store_status():
    """Bounded store status. Never names a backend module or a file path."""
    try:
        credential_store()
    except OAuthError as error:
        return {'state': 'UNAVAILABLE', 'detail_code': error.code}
    return {'state': 'OS_SECURE_STORE', 'detail_code': 'OK'}


def new_credential_key(slot):
    """A fresh, opaque, local-only keyring handle for one connection.

    Built from the trusted local slot name plus 128 bits of local
    randomness.  The mailbox address is deliberately not part of it: a
    credential handle should not embed a personal identifier, and a fresh
    handle per connection means a key is never reused across a
    disconnect/reconnect cycle.
    """
    return f'{slot.lower()}-{secrets.token_hex(16)}'


def write_credential(credential_key, refresh_token):
    try:
        credential_store().set_password(CREDENTIAL_SERVICE, credential_key,
                                        refresh_token.reveal())
    except OAuthError:
        raise
    except Exception:
        # The keyring failure text can name a local path or backend
        # internals, and must never carry the token onward.
        security_event('GMAIL_CREDENTIAL_STORE_FAILED', result='WRITE_FAILED')
        raise OAuthError('CREDENTIAL_STORE_FAILED',
                         'The Gmail token could not be saved to the OS '
                         'credential store. The account was not connected.') from None


def read_credential(credential_key):
    """Read a refresh token, wrapped so it cannot be printed. None if absent."""
    if not credential_key:
        return None
    try:
        value = credential_store().get_password(CREDENTIAL_SERVICE, credential_key)
    except OAuthError:
        raise
    except Exception:
        security_event('GMAIL_CREDENTIAL_STORE_FAILED', result='READ_FAILED')
        return None
    return Secret(value) if value else None


def delete_credential(credential_key):
    """Delete one credential entry. Idempotent; never raises."""
    if not credential_key:
        return False
    try:
        import keyring.errors
        try:
            credential_store().delete_password(CREDENTIAL_SERVICE, credential_key)
        except keyring.errors.PasswordDeleteError:
            return False
    except OAuthError:
        return False
    except Exception:
        security_event('GMAIL_CREDENTIAL_STORE_FAILED', result='DELETE_FAILED')
        return False
    return True


def delete_all_credentials():
    """Remove every Gmail credential ASTRA knows a handle for.

    Handles are read from the metadata rows; the keyring is never
    enumerated, so this can only ever delete entries ASTRA itself wrote
    and never touches the existing OpenAI credential or anything else in
    the user's credential store.
    """
    removed = 0
    with Session() as db:
        keys = [row.credential_key for row in db.scalars(select(GmailAccount))
                if row.credential_key]
    for key in keys:
        removed += bool(delete_credential(key))
    return removed


# ---------------------------------------------------------------------------
# OAuth client secret
# ---------------------------------------------------------------------------
# Google's installed-app documentation marks `client_secret` optional and
# states that installed apps cannot keep a secret confidential. Live
# validation of issue #44 nevertheless proved this Desktop client enforces
# client authentication at the token endpoint. Both facts are true at once,
# and the design reflects both: a Desktop client secret is NOT a globally
# confidential credential -- anyone who distributes the application
# distributes it -- so ASTRA never treats possession of it as proof of
# anything. It is still the Owner's configured credential for their own
# Google Cloud project, so ASTRA protects it locally exactly as it protects
# a refresh token: DPAPI-backed OS credential store, current user only, no
# plaintext fallback anywhere. See docs/architecture/GMAIL_OAUTH.md.
def store_client_secret(secret):
    """Persist the OAuth client secret in the OS credential store.

    `secret` is a `Secret`, so the value cannot be logged by the caller.
    """
    value = secret.reveal()
    if not value.strip() or len(value) > CLIENT_SECRET_MAX_LENGTH:
        raise OAuthError('CLIENT_SECRET_INVALID',
                         'That does not look like a Google OAuth client '
                         'secret. Nothing was stored.')
    try:
        credential_store().set_password(CLIENT_CREDENTIAL_SERVICE,
                                        CLIENT_SECRET_KEY, value)
    except OAuthError:
        raise
    except Exception:
        security_event('GMAIL_CREDENTIAL_STORE_FAILED', result='WRITE_FAILED')
        raise OAuthError('CREDENTIAL_STORE_FAILED',
                         'The Gmail client secret could not be saved to the OS '
                         'credential store. Nothing was stored.') from None
    return True


def read_client_secret():
    """The configured client secret as a `Secret`, or None when unset."""
    try:
        value = credential_store().get_password(CLIENT_CREDENTIAL_SERVICE,
                                                CLIENT_SECRET_KEY)
    except OAuthError:
        raise
    except Exception:
        security_event('GMAIL_CREDENTIAL_STORE_FAILED', result='READ_FAILED')
        return None
    return Secret(value) if value else None


def delete_client_secret():
    """Remove the stored client secret. Idempotent; never raises."""
    try:
        import keyring.errors
        try:
            credential_store().delete_password(CLIENT_CREDENTIAL_SERVICE,
                                               CLIENT_SECRET_KEY)
        except keyring.errors.PasswordDeleteError:
            return False
    except OAuthError:
        return False
    except Exception:
        security_event('GMAIL_CREDENTIAL_STORE_FAILED', result='DELETE_FAILED')
        return False
    return True


def client_secret_status():
    """Bounded state only -- the value is never returned or described."""
    try:
        secret = read_client_secret()
    except OAuthError as error:
        return {'state': 'UNAVAILABLE', 'detail_code': error.code}
    if secret is None:
        return {'state': 'NOT_CONFIGURED',
                'detail_code': 'CLIENT_SECRET_NOT_CONFIGURED',
                'setup_command': 'python -m backend.gmail_setup'}
    secret.clear()
    return {'state': 'CONFIGURED', 'detail_code': 'OK'}


def purge_all_local():
    """Remove every Gmail credential and account row.

    Called by "Delete All Local Data", whose documented scope already
    includes all credentials (that path removes the OpenAI key too, and a
    Gmail refresh token is the same class of secret).  Distinct from
    disconnect: this is the full local erase, makes no Google revocation
    call, and is never triggered by disconnecting an account.

    Deliberately tolerant: the schema is ensured first so a pre-#44
    database erases cleanly, and a credential store that is unavailable
    cannot abort the wider deletion -- the metadata rows still go, and
    `delete_credential` reports rather than raises.
    """
    from sqlalchemy import delete as sql_delete
    initialize_gmail_schema()
    removed = delete_all_credentials()
    # The client credential is Gmail OAuth material too, so a full local
    # erase takes it with the refresh tokens.
    delete_client_secret()
    with Session.begin() as db:
        db.execute(sql_delete(GmailAccount))
    return removed


# ---------------------------------------------------------------------------
# Status
# ---------------------------------------------------------------------------
def _account_status(row):
    """Bounded, secret-free per-slot status.

    Reports DISCONNECTED_INCONSISTENT -- and never CONNECTED -- when the
    metadata says connected but the credential entry is gone (a restored
    database, a cleared Windows profile, a manually deleted credential).
    Failing closed here is what stops #45 from later trying to use a
    credential that does not exist.
    """
    if row is None or row.status != CONNECTED:
        return {'status': DISCONNECTED,
                'authorized_email': (row.authorized_email if row else ''),
                'identity_kind': (row.identity_kind if row else ''),
                'granted_scopes': [],
                'connected_at': '', 'last_validated_at': '',
                'disconnected_at': (row.disconnected_at if row else ''),
                'last_remote_revocation': (row.last_remote_revocation if row else '')}
    # `keyring` offers no existence check, so presence is tested by reading
    # the entry and immediately releasing it. The value is never returned,
    # logged or compared -- only whether one exists.
    credential = read_credential(row.credential_key)
    present = credential is not None
    if credential is not None:
        credential.clear()
    return {'status': CONNECTED if present else 'DISCONNECTED_INCONSISTENT',
            'authorized_email': row.authorized_email,
            'identity_kind': row.identity_kind,
            'granted_scopes': list(row.granted_scopes or []),
            'connected_at': row.connected_at,
            'last_validated_at': row.last_validated_at,
            'disconnected_at': row.disconnected_at,
            'last_remote_revocation': row.last_remote_revocation}


def schema_ready():
    """Whether the account table exists yet.

    `backend.doctor` is explicitly non-destructive and must not create a
    database, so a read-only status call has to tolerate a pre-#44
    database that the application has not started against yet.
    """
    from sqlalchemy import inspect
    try:
        return inspect(engine).has_table(GmailAccount.__tablename__)
    except Exception:
        return False


def status():
    """Whole-integration status: both slots, configuration, store, gate.

    Read-only and non-destructive: it never creates or migrates the
    schema. On a database without the table it reports every slot as
    disconnected with `schema: 'NOT_INITIALIZED'` rather than failing.
    """
    ready = schema_ready()
    rows = {}
    if ready:
        with Session() as db:
            rows = {row.slot: row for row in db.scalars(select(GmailAccount))}
    accounts = {}
    for slot in ACCOUNT_SLOTS:
        entry = _account_status(rows.get(slot))
        entry['slot'] = slot
        entry['enabled'] = slot in oauth.ENABLED_SLOTS
        if slot not in oauth.ENABLED_SLOTS:
            # The secondary slot is architected but gated (OD-012). It
            # always reports the same stable code rather than looking
            # merely "not yet connected".
            entry['gate_code'] = 'SECONDARY_NOT_ENABLED'
        entry['pending_attempt'] = oauth.attempts.status(slot)
        accounts[slot] = entry
    return {'schema': 'gmail-oauth-v1' if ready else 'NOT_INITIALIZED',
            'requested_scopes': list(oauth.REQUESTED_SCOPES),
            'configuration': oauth.configuration_status(),
            'client_secret': client_secret_status(),
            'credential_store': credential_store_status(),
            'read_only': True,
            'accounts': accounts}


# ---------------------------------------------------------------------------
# Connect
# ---------------------------------------------------------------------------
def start_authorization(slot):
    """Begin an authorization attempt for an enabled slot.

    Returns the bounded attempt status plus the authorization URL, which
    the trusted local frontend opens.  The URL is never logged and never
    persisted.
    """
    oauth.require_enabled_slot(slot)
    # Fail before opening a browser window if the client is not configured
    # or the credential store could not hold the result anyway. Client
    # configuration is checked first because it is the step the user has to
    # perform, so it is the more useful of the two messages.
    oauth.require_client_id()
    credential_store()
    attempt, url = oauth.attempts.start(slot, _finalize)
    return {**attempt.public(), 'authorization_url': url}


def cancel_authorization(slot):
    oauth.require_enabled_slot(slot)
    result = oauth.attempts.cancel(slot)
    if result is not None:
        security_event('GMAIL_OAUTH_ATTEMPT_ENDED', slot=slot,
                       result=result.get('result_code', 'CANCELLED'))
    return result


def _finalize(*, attempt_id, slot, code, verifier, redirect_uri):
    """Complete an accepted callback. Runs on the listener thread.

    Ordering is exactly ADR-0007's: validate the callback (already done by
    the attempt manager), exchange the code, validate the *granted*
    scopes, resolve and validate the real authorized identity, check slot
    and identity conflicts, store the refresh token in the OS credential
    store, persist the non-secret metadata, then drop every transient
    secret.  Nothing is reported as connected until the last two steps
    both succeed.
    """
    del attempt_id  # bounded status is tracked by the attempt manager
    configured = oauth.require_client_id()
    # Sent only when configured. A client that does not enforce client
    # authentication still works without one; a client that does enforce it
    # returns a bounded CLIENT_AUTHENTICATION_REQUIRED telling the user to
    # configure it, rather than an opaque transport failure.
    client_secret = read_client_secret()
    try:
        tokens = oauth.exchange_code(configured_client_id=configured, code=code,
                                     verifier=verifier, redirect_uri=redirect_uri,
                                     client_secret=client_secret)
    finally:
        if client_secret is not None:
            client_secret.clear()
    access = tokens['access_token']
    refresh = tokens['refresh_token']
    try:
        try:
            granted = oauth.validate_granted_scopes(tokens['granted_scopes'])
        except OAuthError as error:
            security_event('GMAIL_OAUTH_SCOPE_MISMATCH', slot=slot, result=error.code)
            raise
        identity = oauth.fetch_authorized_identity(access)
        if refresh is None:
            # Google returns no refresh token when a prior grant is reused.
            # An existing stored credential must NOT be overwritten with an
            # empty value, and the account must not be reported as newly
            # connected.
            raise OAuthError('REFRESH_TOKEN_NOT_RETURNED',
                             'Google did not return a refresh token, so no '
                             'credential was stored and nothing was changed. '
                             'Remove ASTRA at your Google account permissions '
                             'page, then connect again and approve access.')
        return _bind_credential(slot, identity, granted, refresh)
    finally:
        # The access token exists only for the identity lookup above.
        access.clear()
        if refresh is not None:
            refresh.clear()


def _bind_credential(slot, identity, granted, refresh):
    """Store the credential and its metadata as one atomic outcome."""
    with _slot_locks[slot]:
        with Session() as db:
            conflict = db.scalar(select(GmailAccount).where(
                GmailAccount.status == CONNECTED,
                GmailAccount.identity_key == identity['identity_key'],
                GmailAccount.slot != slot))
            if conflict is not None:
                security_event('GMAIL_OAUTH_IDENTITY_CONFLICT', slot=slot,
                               result='IDENTITY_ALREADY_CONNECTED')
                raise OAuthError('IDENTITY_ALREADY_CONNECTED',
                                 'That Gmail account is already connected to a '
                                 'different ASTRA account slot. Nothing was '
                                 'stored. Disconnect it there first.')
            existing = db.scalar(select(GmailAccount).where(GmailAccount.slot == slot))
            previous_key = existing.credential_key if existing else ''

        credential_key = new_credential_key(slot)
        write_credential(credential_key, refresh)
        try:
            with Session.begin() as db:
                row = db.scalar(select(GmailAccount).where(GmailAccount.slot == slot))
                if row is None:
                    row = GmailAccount(slot=slot)
                    db.add(row)
                row.status = CONNECTED
                row.authorized_email = identity['authorized_email']
                row.identity_key = identity['identity_key']
                row.identity_kind = identity['identity_kind']
                row.granted_scopes = list(granted)
                row.credential_key = credential_key
                row.connected_at = now()
                row.last_validated_at = now()
                row.disconnected_at = ''
                row.last_remote_revocation = ''
                # A reconnect starts from no mailbox state at all, so #45
                # can never resume a cursor belonging to a different
                # mailbox that previously occupied this slot.
                row.sync_state = {}
        except Exception:
            # Compensate: a credential with no metadata row would be an
            # orphaned secret nothing can later find or revoke.
            delete_credential(credential_key)
            security_event('GMAIL_CREDENTIAL_STORE_FAILED', result='PERSISTENCE_FAILED')
            raise OAuthError('PERSISTENCE_FAILED',
                             'The Gmail connection could not be saved, so the '
                             'stored token was removed again. Nothing was '
                             'connected. Try connecting once more.') from None
        # Only now is the previous credential for this slot unreachable by
        # any record, so it is safe to remove.
        if previous_key and previous_key != credential_key:
            delete_credential(previous_key)
    security_event('GMAIL_OAUTH_CONNECTED', slot=slot, result='CONNECTED')
    return 'CONNECTED'


# ---------------------------------------------------------------------------
# Disconnect
# ---------------------------------------------------------------------------
def disconnect(slot):
    """Disconnect one account. Local removal always succeeds.

    Order (ADR-0007 / ADR-0008):

    1. Stop new token use for this local account (the row leaves CONNECTED
       and its credential handle is cleared).
    2. Invalidate any pending OAuth attempt for the slot.
    3. Read the refresh token from the secure store, only to revoke it.
    4. Attempt Google-side revocation at the fixed HTTPS endpoint.
    5. Delete the local credential regardless of that result.
    6. Delete this account's Gmail sync state.
    7. Record the disconnection metadata.

    Already-created minimized evidence and application transition history
    are untouched: erasing Gmail-derived data is a separate future action
    (ADR-0008, Owner Decision 7 and 8), and #44 creates no such data yet.

    Returns `local_disconnected` and `remote_revocation` separately, so a
    failed Google revocation is never reported as an overall success.
    """
    if slot not in ACCOUNT_SLOTS:
        raise OAuthError('UNKNOWN_ACCOUNT_SLOT', 'Unknown Gmail account slot')
    with _slot_locks[slot]:
        oauth.attempts.invalidate_slot(slot, 'INVALIDATED_BY_DISCONNECT')
        with Session() as db:
            row = db.scalar(select(GmailAccount).where(GmailAccount.slot == slot))
            credential_key = row.credential_key if row else ''
            was_connected = bool(row and row.status == CONNECTED)

        refresh = read_credential(credential_key)
        if refresh is None:
            remote = REMOTE_NOT_ATTEMPTED
        else:
            try:
                remote = oauth.revoke_refresh_token(refresh)
            finally:
                refresh.clear()
        if remote == REMOTE_FAILED:
            security_event('GMAIL_REMOTE_REVOCATION_FAILED', slot=slot,
                           result=REMOTE_FAILED)

        # Local deletion happens whatever Google said, including when
        # Google was unreachable, timed out, errored, or answered with
        # something malformed.
        removal = {'refresh_token': delete_credential(credential_key)}

        with Session.begin() as db:
            row = db.scalar(select(GmailAccount).where(GmailAccount.slot == slot))
            if row is None:
                row = GmailAccount(slot=slot)
                db.add(row)
            row.status = DISCONNECTED
            row.identity_key = ''
            row.credential_key = ''
            row.granted_scopes = []
            row.connected_at = ''
            row.last_validated_at = ''
            row.sync_state = {}
            row.disconnected_at = now()
            row.last_remote_revocation = remote
            remaining_connected = db.scalars(select(GmailAccount).where(
                GmailAccount.status == CONNECTED)).all()

        # The client secret belongs to the installation's OAuth client and is
        # shared by every account slot, so it is removed once no account is
        # connected any more -- never while another slot still needs it. With
        # only PRIMARY enabled (OD-012) that means disconnecting it clears the
        # client credential too, leaving no Gmail OAuth material behind.
        if not remaining_connected:
            secret_present = client_secret_status()['state'] == 'CONFIGURED'
            removal['client_secret'] = delete_client_secret() if secret_present else True
            removal['client_secret_absent_after'] = (
                client_secret_status()['state'] != 'CONFIGURED')
        else:
            removal['client_secret'] = 'RETAINED_ANOTHER_ACCOUNT_CONNECTED'
            removal['client_secret_absent_after'] = False
        # An access token is memory-only and never stored, so there is
        # nothing to delete -- recorded explicitly so the report is complete
        # rather than silent about it.
        removal['access_token'] = 'NEVER_STORED'
        removal['credential_entry_absent_after'] = (
            read_credential(credential_key) is None if credential_key else True)

    incomplete = [name for name, outcome in removal.items()
                  if name.endswith('_absent_after') and outcome is False]
    if was_connected:
        security_event('GMAIL_ACCOUNT_DISCONNECTED', slot=slot, result=remote)
    if incomplete:
        # Bounded: names the credential class that could not be confirmed
        # removed, never a value, and never a keyring error string.
        security_event('GMAIL_CREDENTIAL_STORE_FAILED', slot=slot,
                       result='DELETE_FAILED')
    return {'slot': slot, 'local_disconnected': True, 'remote_revocation': remote,
            'was_connected': was_connected,
            'credential_removal': removal,
            'credential_removal_complete': not incomplete,
            'credential_removal_incomplete': incomplete,
            'preserved': 'Application records, evidence and application history '
                         'are not deleted by disconnecting Gmail.'}
