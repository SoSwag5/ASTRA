"""Bounded read-only Gmail sync and minimized confirmation evidence (#45).

A frozen query interval and page checkpoint allow bounded continuation. Bodies
exist only while parsing. No application records are read or mutated. See
docs/architecture/GMAIL_SYNC.md for limits, retention and recovery semantics."""
import threading
import time
from datetime import datetime, timezone

from sqlalchemy import Index, delete as sql_delete, select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy import JSON

from .models import Base, Record, Session, engine
from . import gmail_accounts as accounts
from . import gmail_confirmations as confirmations
from . import gmail_content as content
from . import gmail_messages as messages
from .gmail_messages import GmailReadError
from .gmail_oauth import ACCOUNT_SLOTS, OAuthError
from .security_events import record as security_event

SCHEMA_VERSION = 'gmail-sync-v1'
SYNC_STATE_VERSION = 'gmail-sync-cursor-v2'
MAX_SYNC_SECONDS = 120.0

# ---------------------------------------------------------------------------
# Window bounds
# ---------------------------------------------------------------------------
#: How far back a first sync -- or a sync whose cursor is unusable --
#: looks. Deliberately short: a job application confirmation is acted on
#: within weeks, and a longer default would read more mail for no gain.
DEFAULT_LOOKBACK_DAYS = 30
#: The absolute floor on any window, applied last and unconditionally. No
#: cursor value, however old or however corrupted, can produce a window
#: wider than this, so "sync the whole mailbox" is unreachable by
#: construction rather than by convention.
MAX_LOOKBACK_DAYS = 90
#: Re-scan one day for delayed visibility; epoch-second queries avoid timezone ambiguity.
CURSOR_OVERLAP_DAYS = 1

#: Cursor states reported in a run summary. Bounded tokens, never free text.
CURSOR_INITIAL = 'INITIAL'
CURSOR_INCREMENTAL = 'INCREMENTAL'
CURSOR_RESET_CONSERVATIVE = 'RESET_CONSERVATIVE'
CURSOR_STATES = (CURSOR_INITIAL, CURSOR_INCREMENTAL, CURSOR_RESET_CONSERVATIVE)

#: Gmail read errors that concern one message only. The message is
#: skipped and counted; the run continues and the cursor may still
#: advance, because retrying these forever would stall the cursor on a
#: message that will never be readable.
PER_MESSAGE_ERRORS = frozenset({'GMAIL_MESSAGE_TOO_LARGE', 'GMAIL_READ_NOT_FOUND',
                                'GMAIL_RESPONSE_INVALID'})

#: Serializes runs per slot in this process, so two concurrent syncs
#: cannot interleave their cursor writes.
_run_locks = {slot: threading.Lock() for slot in ACCOUNT_SLOTS}


class GmailConfirmation(Record, Base):
    """Minimized evidence, unique per opaque connection identity and Gmail message.

    The account identity is a digest of fresh random local credential-handle
    material, never an address or token. Reconnecting creates a new namespace.
    Evidence survives disconnect; explicit full local erase removes it.
    The separate model preserves the pinned #42 models.py provenance."""
    __tablename__ = 'gmail_confirmations'

    account_slot: Mapped[str] = mapped_column(default='')
    gmail_account_id: Mapped[str] = mapped_column(default='')
    gmail_message_id: Mapped[str] = mapped_column(default='')
    sender: Mapped[str] = mapped_column(default='')
    subject: Mapped[str] = mapped_column(default='')
    received_at: Mapped[str] = mapped_column(default='')
    detected_company: Mapped[str] = mapped_column(default='')
    detected_role: Mapped[str] = mapped_column(default='')
    detected_state: Mapped[str] = mapped_column(default='')
    confidence: Mapped[str] = mapped_column(default=confirmations.LOW)
    parser_id: Mapped[str] = mapped_column(default='')
    evidence_signals: Mapped[list] = mapped_column(JSON, default=list)
    application_url: Mapped[str] = mapped_column(default='')

    __table_args__ = (
        # Idempotency: one evidence row per (account, message). A repeated
        # sync over an overlapping window cannot create a second record
        # for the same message, and the constraint is in the database
        # rather than only in the code path that writes it.
        Index('uq_gmail_confirmation_message', 'gmail_account_id',
              'gmail_message_id', unique=True),
        Index('ix_gmail_confirmation_received', 'received_at'),
    )


def initialize_sync_schema():
    """Create the evidence table and its indexes. Additive and idempotent.

    Same convention as #44: one new table, no existing table, column,
    index or row altered, so an existing database upgrades by gaining a
    table and needs no backfill or destructive migration.
    """
    Base.metadata.create_all(engine, tables=[GmailConfirmation.__table__])
    with engine.begin() as connection:
        # create_all() emits __table_args__ indexes only when it creates
        # the table itself, so ensure them for a database whose table
        # already existed.
        connection.execute(text(
            'CREATE UNIQUE INDEX IF NOT EXISTS uq_gmail_confirmation_message '
            'ON gmail_confirmations (gmail_account_id, gmail_message_id)'))
        connection.execute(text(
            'CREATE INDEX IF NOT EXISTS ix_gmail_confirmation_received '
            'ON gmail_confirmations (received_at)'))


def schema_ready():
    """Whether the evidence table exists yet (non-destructive check)."""
    from sqlalchemy import inspect
    try:
        return inspect(engine).has_table(GmailConfirmation.__tablename__)
    except Exception:
        return False


def purge_all_confirmations():
    """Delete every Gmail-derived evidence row.

    Called only by the full local erase ("Delete All Local Data"), never
    by a disconnect: ADR-0008 is explicit that disconnecting an account
    removes its token and sync state but does **not** delete evidence
    already created, and that removing Gmail-derived history is a
    separate, explicit user action.
    """
    initialize_sync_schema()
    with Session.begin() as db:
        db.execute(sql_delete(GmailConfirmation))


# ---------------------------------------------------------------------------
# Query and window
# ---------------------------------------------------------------------------
def build_query(after, before):
    return messages.build_query(after, before)


def plan_window(state, reference=None):
    """Resume an entire frozen interval; never advance past an unfinished page.

    Checkpoints hold times and one opaque page token only. Invalid/expired
    state resets to 30 days, never an unbounded history/list call.
    """
    end = int((reference or datetime.now(timezone.utc)).timestamp()) + 1
    floor = end - MAX_LOOKBACK_DAYS * 86400
    default = (end - DEFAULT_LOOKBACK_DAYS * 86400, end, None, CURSOR_INITIAL)
    if not state:
        return default
    reset = (*default[:3], CURSOR_RESET_CONSERVATIVE)
    if not isinstance(state, dict) or state.get('version') != SYNC_STATE_VERSION:
        return reset
    after, before, token = state.get('after'), state.get('before'), state.get('page_token')
    if 'after' in state or 'before' in state or 'page_token' in state:
        if (type(after) is int and type(before) is int and floor <= after < before <= end
                and (token is None or isinstance(token, str) and messages.PAGE_TOKEN_PATTERN.fullmatch(token))):
            return after, before, token, CURSOR_INCREMENTAL
        return reset
    completed = state.get('completed_through')
    if type(completed) is not int or not floor <= completed <= end:
        return reset
    return max(floor, completed - CURSOR_OVERLAP_DAYS * 86400), end, None, CURSOR_INCREMENTAL


def _checkpoint(slot, account_id, state):
    with accounts._slot_locks[slot], Session.begin() as db:
        row = accounts.require_connection(db, slot, account_id)
        row.sync_state = state


# ---------------------------------------------------------------------------
# One message
# ---------------------------------------------------------------------------
def _process_message(message, *, slot, account_id):
    """Parse one Gmail message into a minimized record, or `None`.

    `message` is the raw Gmail response. It is read here, the minimized
    fields are copied out, and it is never stored, logged, attached to an
    exception, or returned. The decoded body lives in `extracted` for the
    duration of this call only.
    """
    payload = message.get('payload') if isinstance(message, dict) else None
    headers = content.headers_of(payload if isinstance(payload, dict) else {})
    subject = content.sanitize_text(headers.get('subject', ''), content.MAX_SUBJECT_CHARS)
    sender = content.sender_address(headers.get('from', ''))
    domain = content.sender_domain(sender)
    authentication = content.authentication_evidence(headers)
    extracted = content.extract_content(payload)

    result = confirmations.parse(
        subject=subject,
        sender_domain=domain,
        text=extracted.text,
        urls=extracted.urls,
        authentication=authentication,
        unsafe_links_dropped=bool(extracted.unsafe_urls_dropped),
    )

    if (extracted.truncated or extracted.malformed_parts or extracted.depth_exceeded
            or extracted.parts_seen >= content.MAX_MIME_PARTS or headers.get('_ambiguous')
            or not content.received_at(message)) and result.confidence == confirmations.HIGH:
        result.confidence = confirmations.MEDIUM
    identifier = message.get('id') if isinstance(message, dict) else ''
    record = {
        'account_slot': slot,
        'gmail_account_id': account_id,
        'gmail_message_id': identifier if isinstance(identifier, str) else '',
        'sender': sender,
        'subject': subject,
        'received_at': content.received_at(message),
        'detected_company': result.company,
        'detected_role': result.role,
        'detected_state': result.state,
        'confidence': result.confidence,
        'parser_id': result.parser_id,
        # Bounded tokens only: which signals corroborated, the three
        # normalized authentication verdicts, and which limits the
        # message hit. No header text and no free text.
        'evidence_signals': sorted(set(result.signals) | set(result.evidence_tokens) | set(extracted.limits())),
        'application_url': result.application_url,
    }
    return result, record


def _store(record):
    """Insert one evidence row, or report it as an already-known duplicate.

    Checked first and guarded by the unique index second, so a concurrent
    run racing on the same message still cannot produce two rows.
    """
    with Session() as db:
        existing = db.scalar(select(GmailConfirmation.id).where(
            GmailConfirmation.gmail_account_id == record['gmail_account_id'],
            GmailConfirmation.gmail_message_id == record['gmail_message_id']))
    if existing is not None:
        return False
    try:
        with accounts._slot_locks[record['account_slot']], Session.begin() as db:
            accounts.require_connection(db, record['account_slot'], record['gmail_account_id'])
            db.add(GmailConfirmation(**record))
    except IntegrityError:
        return False
    return True


def known_message_ids(account_id, identifiers):
    """Which of `identifiers` this account already has evidence for.

    Consulted before fetching, so a repeated sync over an overlapping
    window does not re-download a message it already parsed -- less work,
    and one fewer occasion on which a body is decoded at all.
    """
    if not identifiers:
        return set()
    with Session() as db:
        rows = db.scalars(select(GmailConfirmation.gmail_message_id).where(
            GmailConfirmation.gmail_account_id == account_id,
            GmailConfirmation.gmail_message_id.in_(list(identifiers)))).all()
    return set(rows)


# ---------------------------------------------------------------------------
# The run
# ---------------------------------------------------------------------------
def sync_account(slot='PRIMARY', *, reference=None):
    """Explicit invocation only. No scheduler, mailbox mutation or reconciliation."""
    accounts.oauth.require_enabled_slot(slot)
    if not _run_locks[slot].acquire(blocking=False):
        raise OAuthError('SYNC_ALREADY_RUNNING', accounts.oauth.message_for('SYNC_ALREADY_RUNNING'))
    access = None
    try:
        initialize_sync_schema()
        access, account_id = accounts.access_token_for(slot)
        return _run(slot, access, account_id, reference)
    except OAuthError:
        raise
    except Exception:
        # Database/driver failures may embed bound private field values.
        # Never let them reach the app's generic traceback logger.
        raise GmailReadError('GMAIL_SYNC_FAILED', messages.message_for('GMAIL_SYNC_FAILED')) from None
    finally:
        if access is not None:
            access.clear()
        _run_locks[slot].release()


def _run(slot, access, account_id, reference):
    with Session() as db:
        row = accounts.require_connection(db, slot, account_id)
        previous = row.sync_state
    after, before, page_token, cursor_state = plan_window(previous, reference)
    query = build_query(after, before)
    # Freeze the first page too: an interrupted first page must replay the
    # original interval, even when the next invocation is days later.
    _checkpoint(slot, account_id, {'version': SYNC_STATE_VERSION, 'after': after,
                                 'before': before, 'page_token': page_token})
    summary = {'slot': slot, 'schema': SCHEMA_VERSION, 'cursor_state': cursor_state,
               'window_start': datetime.fromtimestamp(after, timezone.utc).isoformat(),
               'window_end': datetime.fromtimestamp(before, timezone.utc).isoformat(),
               'pages_fetched': 0, 'messages_listed': 0, 'messages_fetched': 0,
               'skipped_already_recorded': 0, 'confirmations_recorded': 0,
               'duplicates_ignored': 0, 'not_confirmation': 0,
               'messages_skipped_unreadable': 0, 'out_of_window': 0,
               'by_confidence': {level: 0 for level in confirmations.CONFIDENCE_LEVELS},
               'limits_reached': [], 'cursor_advanced': False, 'complete': False,
               'body_retained': False}
    deadline = time.monotonic() + MAX_SYNC_SECONDS
    limits, tokens_seen = set(), set()
    security_event('GMAIL_SYNC_STARTED', slot=slot, result=cursor_state)
    try:
        for _ in range(messages.MAX_PAGES):
            if time.monotonic() >= deadline:
                limits.add('TIME_LIMIT_REACHED')
                break
            with Session() as db:
                accounts.require_connection(db, slot, account_id)
            remaining = messages.MAX_MESSAGES_PER_SYNC - summary['messages_listed']
            if remaining <= 0:
                limits.add('MESSAGE_LIMIT_REACHED')
                break
            identifiers, next_token = messages.list_message_ids(
                access, query=query, page_token=page_token,
                page_size=min(remaining, messages.MAX_PAGE_SIZE), timeout=deadline - time.monotonic())
            if next_token and (next_token == page_token or next_token in tokens_seen):
                raise GmailReadError('GMAIL_RESPONSE_INVALID', messages.message_for('GMAIL_RESPONSE_INVALID'))
            summary['pages_fetched'] += 1
            summary['messages_listed'] += len(identifiers)
            already = known_message_ids(account_id, identifiers)
            page_complete = True
            for identifier in identifiers:
                if time.monotonic() >= deadline:
                    limits.add('TIME_LIMIT_REACHED')
                    page_complete = False
                    break
                if identifier in already:
                    summary['skipped_already_recorded'] += 1
                    continue
                with Session() as db:
                    accounts.require_connection(db, slot, account_id)
                message = None
                try:
                    summary['messages_fetched'] += 1
                    message = messages.fetch_message(access, identifier, timeout=deadline - time.monotonic())
                    timestamp = content.internal_date_ms(message) // 1000
                    if not after <= timestamp < before:
                        summary['out_of_window'] += 1
                        continue
                    result, record = _process_message(message, slot=slot, account_id=account_id)
                except GmailReadError as error:
                    if error.code not in PER_MESSAGE_ERRORS:
                        raise
                    summary['messages_skipped_unreadable'] += 1
                    security_event('GMAIL_MESSAGE_SKIPPED', slot=slot, result=error.code)
                    continue
                except Exception:
                    # Never retain a raw parser exception or include locals.
                    summary['messages_skipped_unreadable'] += 1
                    security_event('GMAIL_MESSAGE_SKIPPED', slot=slot, result='GMAIL_PARSE_FAILED')
                    continue
                finally:
                    message = None
                limits.update(token for token in record['evidence_signals'] if token in (
                    'BODY_TRUNCATED', 'MALFORMED_PART_SKIPPED', 'MIME_DEPTH_EXCEEDED',
                    'MIME_PART_LIMIT_REACHED', 'UNSAFE_LINKS_DROPPED'))
                if not result.is_confirmation:
                    summary['not_confirmation'] += 1
                elif _store(record):
                    summary['confirmations_recorded'] += 1
                    summary['by_confidence'][result.confidence] += 1
                    already.add(identifier)
                else:
                    summary['duplicates_ignored'] += 1
            if not page_complete:
                break  # replay this page next run; no unprocessed IDs skipped
            if next_token:
                state = {'version': SYNC_STATE_VERSION, 'after': after, 'before': before,
                         'page_token': next_token}
                _checkpoint(slot, account_id, state)
                tokens_seen.add(next_token)
                page_token = next_token
            else:
                _checkpoint(slot, account_id, {'version': SYNC_STATE_VERSION,
                            'completed_through': before})
                summary['complete'] = summary['cursor_advanced'] = True
                break
        if not summary['complete']:
            limits.add('PAGE_LIMIT_REACHED' if summary['pages_fetched'] >= messages.MAX_PAGES else 'INCOMPLETE')
    except GmailReadError as error:
        if error.code == 'GMAIL_RESPONSE_INVALID':
            # Expired/invalid page tokens cannot widen scope. Start a new
            # bounded window on the next explicit invocation.
            _checkpoint(slot, account_id, {'version': 'RESET_REQUIRED'})
        security_event('GMAIL_SYNC_FAILED', slot=slot, result=error.code)
        raise GmailReadError(error.code, messages.message_for(error.code)) from None
    summary['limits_reached'] = sorted(limits)
    security_event('GMAIL_SYNC_COMPLETED', slot=slot,
                   result='COMPLETED' if summary['complete'] else 'INCOMPLETE')
    return summary


# ---------------------------------------------------------------------------
# Read models
# ---------------------------------------------------------------------------
MAX_LISTED_CONFIRMATIONS = 200


def _public(row):
    """One evidence row as the API returns it.

    Every field here is one of the approved minimized fields and has
    already been sanitized. No raw message content exists to expose.
    """
    return {'id': row.id,
            'account_slot': row.account_slot,
            'gmail_account_id': row.gmail_account_id,
            'gmail_message_id': row.gmail_message_id,
            'sender': row.sender,
            'subject': row.subject,
            'received_at': row.received_at,
            'detected_company': row.detected_company,
            'detected_role': row.detected_role,
            'detected_state': row.detected_state,
            'confidence': row.confidence,
            'parser_id': row.parser_id,
            'evidence_signals': list(row.evidence_signals or []),
            'application_url': row.application_url,
            'created_at': row.created_at}


def list_confirmations(*, limit=50):
    """Most recent detected confirmations, bounded."""
    if not schema_ready():
        return {'schema': 'NOT_INITIALIZED', 'confirmations': [], 'count': 0}
    bounded = max(1, min(int(limit), MAX_LISTED_CONFIRMATIONS))
    with Session() as db:
        rows = db.scalars(
            select(GmailConfirmation)
            .order_by(GmailConfirmation.received_at.desc(), GmailConfirmation.id.desc())
            .limit(bounded)).all()
        total = db.scalar(select(GmailConfirmation.id).order_by(
            GmailConfirmation.id.desc()).limit(1))
    return {'schema': SCHEMA_VERSION,
            'confirmations': [_public(row) for row in rows],
            'count': len(rows),
            'highest_id': total or 0}


def sync_status():
    """Report fixed limits and cursor presence only; never raw checkpoints."""
    ready = schema_ready()
    slots = {}
    for slot in ACCOUNT_SLOTS:
        state = accounts.read_sync_state(slot) if accounts.schema_ready() else {}
        versioned = isinstance(state, dict) and state.get('version') == SYNC_STATE_VERSION
        slots[slot] = {
            'slot': slot,
            'enabled': slot in accounts.oauth.ENABLED_SLOTS,
            'cursor': 'PRESENT' if versioned else 'NONE',
        }
        if slot not in accounts.oauth.ENABLED_SLOTS:
            slots[slot]['gate_code'] = 'SECONDARY_NOT_ENABLED'
    return {'schema': SCHEMA_VERSION if ready else 'NOT_INITIALIZED',
            'read_only': True,
            'accounts': slots,
            'parsers': list(confirmations.PARSER_IDS) + [confirmations.GENERIC_PARSER_ID],
            'limits': {'default_lookback_days': DEFAULT_LOOKBACK_DAYS,
                       'max_lookback_days': MAX_LOOKBACK_DAYS,
                       'cursor_overlap_days': CURSOR_OVERLAP_DAYS,
                       'max_pages': messages.MAX_PAGES,
                       'max_page_size': messages.MAX_PAGE_SIZE,
                       'max_messages_per_sync': messages.MAX_MESSAGES_PER_SYNC,
                       'max_message_response_bytes': messages.MAX_MESSAGE_RESPONSE_BYTES,
                       'max_decoded_body_bytes': content.MAX_DECODED_BODY_BYTES,
                       'max_mime_depth': content.MAX_MIME_DEPTH,
                       'max_mime_parts': content.MAX_MIME_PARTS},
            'retains_message_bodies': False}
