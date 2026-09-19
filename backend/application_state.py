"""Authoritative application-state model, transition rules and history (#46).

ASTRA already carries three overlapping status vocabularies, all of which
predate this issue and all of which remain in place:

* `backend/policy.py::STATUSES` -- the job *workflow* status, which mixes
  discovery triage (`FOUND`, `MAYBE`, `SKIP`) with application outcomes.
* `backend/campaign.py::STAGES` -- the campaign tracker's stage list.
* `Application.status`, `Application.tracking['stage']` and `Job.status` --
  three columns that the two vocabularies above are written into.

This module does **not** unify them and does not rewrite them. It adds one
explicit, authoritative application-state model beside them:

* `STATES` is the canonical vocabulary. It is the authority for #47 and for
  every provenance question ("how do we know this application is APPLIED?").
* `PERMITTED` is the complete transition table, declared once. No API
  handler, reconciliation path or migration may invent its own rule -- every
  state change goes through `assert_state()`.
* `ApplicationStateTransition` is an append-only history. It is the record of
  record. `ApplicationStateRecord` is a projection of the latest accepted
  transition, maintained transactionally in the same unit of work, and is
  never a substitute for the history.

The older columns keep their existing behaviour so the current frontend and
API stay compatible (#46 has no UI scope). They are **compatibility
projections**: a reader that needs a provable state reads this module, a
reader that only needs the legacy shape keeps reading the old column. When a
legacy path asserts a move this table does not permit, the legacy column
still moves exactly as it did before, and this module records a bounded
`TRANSITION_NOT_PERMITTED` decision instead of silently following it -- the
divergence is recorded, never hidden, and the canonical state never regresses.

`backend/models.py`, `backend/policy.py` and `backend/services.py` are
SHA-256-pinned #42 evaluation-provenance inputs. This module therefore
declares its own tables against the shared `Base` and owns its own idempotent
schema initializer, exactly as #44 and #45 did.
"""
import threading
from datetime import datetime, timedelta, timezone

from sqlalchemy import ForeignKey, Index, JSON, delete as sql_delete, select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Mapped, mapped_column

from .models import Application, Base, Job, Record, Session, engine, now

SCHEMA_VERSION = 'application-state-v1'

# ---------------------------------------------------------------------------
# Canonical states
# ---------------------------------------------------------------------------
DISCOVERED = 'DISCOVERED'
SAVED = 'SAVED'
APPLIED = 'APPLIED'
VIEWED = 'VIEWED'
ASSESSMENT = 'ASSESSMENT'
INTERVIEW = 'INTERVIEW'
OFFER = 'OFFER'
REJECTED = 'REJECTED'
CLOSED = 'CLOSED'

#: The complete canonical vocabulary, in progression order. The index of a
#: state in this tuple is its ordinal, used only to express "no regression"
#: compactly in tests and in the manual-authority check; `PERMITTED` below,
#: not the ordinal, is the authority on what is allowed.
STATES = (DISCOVERED, SAVED, APPLIED, VIEWED, ASSESSMENT, INTERVIEW,
          OFFER, REJECTED, CLOSED)
ORDINAL = {state: index for index, state in enumerate(STATES)}

#: States from which no transition leaves. `CLOSED` is the single sink.
TERMINAL = frozenset({CLOSED})

#: States that can only be reached after an application was actually
#: submitted. An employer cannot view, assess, interview, reject or make an
#: offer on an application that was never sent.
POST_SUBMISSION = frozenset({VIEWED, ASSESSMENT, INTERVIEW, OFFER, REJECTED})

#: **The transition table.** Complete and explicit: every canonical state is
#: a key, and a target absent from a state's set is forbidden. Rules encoded
#: here, each one testable on its own:
#:
#: * Normal progress is DISCOVERED -> SAVED -> APPLIED.
#: * Forward skips are legitimate: DISCOVERED -> APPLIED (applied without
#:   ever shortlisting), APPLIED -> INTERVIEW (invited without a recorded
#:   "viewed" signal), APPLIED -> OFFER, VIEWED -> INTERVIEW.
#: * Nothing moves to a lower ordinal: there is no silent regression.
#: * A self-transition is not a transition and is never recorded.
#: * `OFFER` and `REJECTED` are terminal outcomes that may only be closed.
#: * `CLOSED` has no outgoing transition at all.
#: * `CLOSED` is reachable from every other state, because abandoning or
#:   archiving an application is always legitimate.
PERMITTED = {
    DISCOVERED: frozenset({SAVED, APPLIED, CLOSED}),
    SAVED:      frozenset({APPLIED, CLOSED}),
    APPLIED:    frozenset({VIEWED, ASSESSMENT, INTERVIEW, OFFER, REJECTED, CLOSED}),
    VIEWED:     frozenset({ASSESSMENT, INTERVIEW, OFFER, REJECTED, CLOSED}),
    ASSESSMENT: frozenset({INTERVIEW, OFFER, REJECTED, CLOSED}),
    INTERVIEW:  frozenset({OFFER, REJECTED, CLOSED}),
    OFFER:      frozenset({CLOSED}),
    REJECTED:   frozenset({CLOSED}),
    CLOSED:     frozenset(),
}


def is_permitted(previous, new):
    """Whether `previous -> new` is in the transition table.

    A self-transition returns False: it is a no-op, not a state change, and
    recording one would pad the history with events that prove nothing.
    """
    if previous not in PERMITTED or new not in STATES:
        return False
    return new in PERMITTED[previous]


# ---------------------------------------------------------------------------
# Provenance vocabulary
# ---------------------------------------------------------------------------
#: Who or what asserted a transition. Every history row carries exactly one.
SOURCE_USER_ACTION = 'USER_ACTION'
SOURCE_USER_CONFIRMED_GMAIL = 'USER_CONFIRMED_GMAIL_EVIDENCE'
SOURCE_GMAIL_PARSER = 'GMAIL_PARSER'
SOURCE_LEGACY_MIGRATION = 'LEGACY_MIGRATION'
SOURCE_BROWSER_CONFIRMATION = 'BROWSER_CONFIRMATION'
SOURCE_FUTURE_INTEGRATION = 'FUTURE_INTEGRATION'
SOURCE_CATEGORIES = (SOURCE_USER_ACTION, SOURCE_USER_CONFIRMED_GMAIL,
                     SOURCE_GMAIL_PARSER, SOURCE_LEGACY_MIGRATION,
                     SOURCE_BROWSER_CONFIRMATION, SOURCE_FUTURE_INTEGRATION)

#: Sources whose assertion is treated as the user's own. A weaker automated
#: signal may never overwrite or supersede a state one of these established.
MANUAL_SOURCES = frozenset({SOURCE_USER_ACTION, SOURCE_USER_CONFIRMED_GMAIL,
                            SOURCE_BROWSER_CONFIRMATION})
#: Sources that carry a confidence level and are subject to confidence gating.
AUTOMATED_SOURCES = frozenset({SOURCE_GMAIL_PARSER, SOURCE_FUTURE_INTEGRATION})

HIGH = 'HIGH'
MEDIUM = 'MEDIUM'
LOW = 'LOW'
CONFIDENCE_LEVELS = (HIGH, MEDIUM, LOW)

#: The only canonical state an *automated* source may set in v1.1.
#:
#: Issue #45 parses application confirmations and nothing else -- it detects
#: `APPLICATION_CONFIRMED` and explicitly defers viewed, assessment,
#: interview, rejection and offer (`gmail_confirmations.DEFERRED_STATES`).
#: There is therefore no automated evidence for any later state, at any
#: confidence, and this set says so structurally rather than by convention.
#: Widening it requires a parser that actually produces the evidence.
AUTOMATED_TARGET_STATES = frozenset({APPLIED})
#: The minimum confidence an automated source needs to change state at all.
#: MEDIUM produces a review item; only HIGH may apply a transition, and only
#: together with a unique strong multi-field reconciliation match.
AUTOMATIC_CONFIDENCE = HIGH

# ---------------------------------------------------------------------------
# Bounded reason codes
# ---------------------------------------------------------------------------
#: Why an accepted transition happened.
REASON_USER_ACTION = 'USER_ACTION'
REASON_LEGACY_BOOTSTRAP = 'LEGACY_BOOTSTRAP'
REASON_BROWSER_CONFIRMED = 'BROWSER_CONFIRMED_SUBMISSION'
REASON_GMAIL_AUTOMATIC = 'GMAIL_HIGH_CONFIDENCE_UNIQUE_MATCH'
REASON_GMAIL_USER_CONFIRMED = 'GMAIL_EVIDENCE_USER_CONFIRMED'
ACCEPTED_REASONS = (REASON_USER_ACTION, REASON_LEGACY_BOOTSTRAP,
                    REASON_BROWSER_CONFIRMED, REASON_GMAIL_AUTOMATIC,
                    REASON_GMAIL_USER_CONFIRMED)

#: Why a requested transition was refused. Returned to the caller and, where
#: useful, recorded as a bounded security event. Never free text.
REFUSED_UNKNOWN_STATE = 'UNKNOWN_STATE'
REFUSED_NOT_PERMITTED = 'TRANSITION_NOT_PERMITTED'
REFUSED_NO_CHANGE = 'ALREADY_IN_STATE'
REFUSED_TERMINAL = 'TERMINAL_STATE_HAS_NO_TRANSITION'
REFUSED_STATE_NOT_AUTOMATABLE = 'STATE_NOT_AUTOMATABLE'
REFUSED_CONFIDENCE_TOO_LOW = 'CONFIDENCE_TOO_LOW'
REFUSED_WEAKER_THAN_MANUAL = 'AUTOMATED_WEAKER_THAN_MANUAL'
REFUSED_UNKNOWN_SOURCE = 'UNKNOWN_SOURCE_CATEGORY'
REFUSED_NO_APPLICATION = 'APPLICATION_NOT_FOUND'
#: Another writer appended to this application's history first. The unique
#: `(application_id, sequence)` index turns a lost race into a refusal rather
#: than a gap, a duplicate or an overwrite. SQLite fixes a transaction's read
#: snapshot at its first read, so the loser cannot usefully retry inside the
#: same transaction -- it is told what happened and the caller, which owns the
#: transaction, decides whether to start a new one.
REFUSED_CONCURRENT_UPDATE = 'CONCURRENT_HISTORY_APPEND'
REFUSAL_REASONS = (REFUSED_UNKNOWN_STATE, REFUSED_NOT_PERMITTED,
                   REFUSED_NO_CHANGE, REFUSED_TERMINAL,
                   REFUSED_STATE_NOT_AUTOMATABLE, REFUSED_CONFIDENCE_TOO_LOW,
                   REFUSED_WEAKER_THAN_MANUAL, REFUSED_UNKNOWN_SOURCE,
                   REFUSED_NO_APPLICATION, REFUSED_CONCURRENT_UPDATE)

#: Bounded evidence tokens this module may add itself. Tokens supplied by a
#: caller are filtered against `gmail_confirmations`/`gmail_content`
#: vocabularies plus this set by `_bounded_tokens()`; anything else is
#: dropped, so no company name, subject, URL or free text can enter history
#: through the token list.
TOKEN_LEGACY_STAGE_DERIVED = 'LEGACY_STAGE_DERIVED'
TOKEN_LEGACY_STATUS_DERIVED = 'LEGACY_STATUS_DERIVED'
TOKEN_LEGACY_JOB_STATUS_DERIVED = 'LEGACY_JOB_STATUS_DERIVED'
TOKEN_LEGACY_NO_EVIDENCE = 'LEGACY_NO_EVIDENCE'
TOKEN_APPLIED_DATE_PRESENT = 'LEGACY_APPLIED_DATE_PRESENT'
TOKEN_OCCURRED_AT_INVALID = 'OCCURRED_AT_INVALID'
TOKEN_OCCURRED_AT_FUTURE = 'OCCURRED_AT_CLAMPED_NOT_FUTURE'
OWN_TOKENS = frozenset({TOKEN_LEGACY_STAGE_DERIVED, TOKEN_LEGACY_STATUS_DERIVED,
                        TOKEN_LEGACY_JOB_STATUS_DERIVED, TOKEN_LEGACY_NO_EVIDENCE,
                        TOKEN_APPLIED_DATE_PRESENT, TOKEN_OCCURRED_AT_INVALID,
                        TOKEN_OCCURRED_AT_FUTURE})

MAX_EVIDENCE_TOKENS = 24
MAX_TOKEN_CHARS = 64
MAX_IDENTIFIER_CHARS = 128
MAX_PARSER_ID_CHARS = 64
#: No transition may be recorded as happening more than this far in the
#: future; a hostile or broken `internalDate` cannot backdate or postdate the
#: history beyond a small clock-skew allowance.
MAX_FUTURE_SKEW = timedelta(minutes=5)

# ---------------------------------------------------------------------------
# Legacy vocabulary mapping (compatibility only)
# ---------------------------------------------------------------------------
#: `campaign.STAGES` -> canonical state. A stage with no canonical meaning
#: maps to `None`, which means "this legacy value asserts nothing about the
#: canonical state" -- never "DISCOVERED". Inventing a state for an
#: unmappable legacy value would be exactly the silent regression this
#: module exists to prevent.
STAGE_TO_STATE = {
    'DISCOVERED': DISCOVERED,
    'SHORTLISTED': SAVED,
    'PREPARING': SAVED,
    'APPLIED': APPLIED,
    'RECRUITER_CONTACT': VIEWED,
    'SCREENING': VIEWED,
    'ASSESSMENT': ASSESSMENT,
    'INTERVIEW': INTERVIEW,
    'FINAL_INTERVIEW': INTERVIEW,
    'OFFER': OFFER,
    'HIRED': CLOSED,
    'REJECTED': REJECTED,
    'WITHDRAWN': CLOSED,
    'NO_RESPONSE': None,
    'ARCHIVED': CLOSED,
}

#: `policy.STATUSES` -> canonical state, same `None` convention. Discovery
#: triage values (`SKIP`, `FAILED`) assert nothing about an application.
STATUS_TO_STATE = {
    'FOUND': DISCOVERED,
    'ANALYZED': DISCOVERED,
    'HIGH_PRIORITY': DISCOVERED,
    'MAYBE': DISCOVERED,
    'SKIP': None,
    'READY_TO_APPLY': SAVED,
    'NEEDS_REVIEW': SAVED,
    'NEEDS_HUMAN_ACTION': SAVED,
    'APPLYING': SAVED,
    'APPLIED': APPLIED,
    'FAILED': None,
    'INTERVIEW': INTERVIEW,
    'REJECTED': REJECTED,
    'WITHDRAWN': CLOSED,
    'OFFER': OFFER,
}


def canonical_for_legacy(value):
    """Canonical state for a legacy stage or workflow status, or `None`."""
    if not isinstance(value, str):
        return None
    key = value.strip().upper()
    if key in STAGE_TO_STATE:
        return STAGE_TO_STATE[key]
    return STATUS_TO_STATE.get(key)


# ---------------------------------------------------------------------------
# Tables
# ---------------------------------------------------------------------------
class ApplicationStateRecord(Record, Base):
    """Current canonical state: one row per application.

    A **projection**, maintained in the same transaction as the history row
    that produced it. It exists so a reader does not have to replay the whole
    history for the common question, and it carries no fact the history does
    not already prove. `manual_ordinal` caches the highest ordinal any manual
    source has asserted, so the "weaker automated signal never supersedes a
    manually confirmed state" rule is a cheap, explicit check rather than a
    history scan on every candidate transition.
    """
    __tablename__ = 'application_states'

    application_id: Mapped[int] = mapped_column(ForeignKey('applications.id'), unique=True)
    current_state: Mapped[str] = mapped_column(default=DISCOVERED)
    #: Ordinal of `current_state`. Denormalized for indexed ordering only.
    state_ordinal: Mapped[int] = mapped_column(default=0)
    #: Highest ordinal asserted by a MANUAL_SOURCES transition, or -1.
    manual_ordinal: Mapped[int] = mapped_column(default=-1)
    #: Source category of the transition that produced `current_state`.
    source_category: Mapped[str] = mapped_column(default=SOURCE_LEGACY_MIGRATION)
    #: When the change this state reflects actually happened.
    entered_at: Mapped[str] = mapped_column(default='')
    #: Monotonic per-application sequence of the transition behind this row.
    sequence: Mapped[int] = mapped_column(default=0)
    schema_version: Mapped[str] = mapped_column(default=SCHEMA_VERSION)

    __table_args__ = (
        Index('uq_application_state_application', 'application_id', unique=True),
        Index('ix_application_state_current', 'current_state'),
    )


class ApplicationStateTransition(Record, Base):
    """Append-only transition history. The authoritative record.

    Nothing in ordinary application operation updates or deletes a row here.
    Rows leave only with the application itself, through the privacy
    controls' explicit deletion scopes.

    Retention is deliberately narrow. Every column is either an identifier,
    a member of a fixed vocabulary, or a timestamp. There is no column that
    could hold an email body, HTML, a MIME structure, a snippet, an
    authentication header, a URL with a query string, an exception string or
    any other unbounded external content -- see `docs/architecture/
    APPLICATION_STATE.md`.
    """
    __tablename__ = 'application_state_transitions'

    application_id: Mapped[int] = mapped_column(ForeignKey('applications.id'))
    #: Per-application monotonic counter, starting at 1.
    sequence: Mapped[int] = mapped_column(default=1)
    #: Empty string for the first (bootstrap) row: there was no prior state.
    previous_state: Mapped[str] = mapped_column(default='')
    new_state: Mapped[str] = mapped_column(default=DISCOVERED)
    #: One of SOURCE_CATEGORIES.
    source_category: Mapped[str] = mapped_column(default=SOURCE_USER_ACTION)
    #: Bounded actor token, e.g. 'USER', 'GMAIL_SYNC', 'LEGACY_BOOTSTRAP'.
    asserted_by: Mapped[str] = mapped_column(default='USER')
    #: HIGH/MEDIUM/LOW for an automated source, '' for a manual one.
    confidence: Mapped[str] = mapped_column(default='')
    #: Opaque Gmail connection identity (already a digest of local random
    #: credential material -- never an address or token), or ''.
    gmail_account_id: Mapped[str] = mapped_column(default='')
    #: Gmail message identifier, or ''.
    gmail_message_id: Mapped[str] = mapped_column(default='')
    #: `gmail_confirmations.id` of the evidence row, or 0.
    gmail_confirmation_id: Mapped[int] = mapped_column(default=0)
    #: Parser identifier/version, e.g. 'greenhouse-confirmation-v1', or ''.
    parser_id: Mapped[str] = mapped_column(default='')
    #: Bounded tokens only; see `_bounded_tokens()`.
    evidence_tokens: Mapped[list] = mapped_column(JSON, default=list)
    #: Which reconciliation fields agreed, as bounded field names only.
    field_agreement: Mapped[list] = mapped_column(JSON, default=list)
    #: When the asserted change happened.
    occurred_at: Mapped[str] = mapped_column(default='')
    #: When ASTRA wrote this row.
    recorded_at: Mapped[str] = mapped_column(default=now)
    #: One of ACCEPTED_REASONS.
    reason_code: Mapped[str] = mapped_column(default=REASON_USER_ACTION)
    schema_version: Mapped[str] = mapped_column(default=SCHEMA_VERSION)

    __table_args__ = (
        # The history is append-only, and this makes a duplicated append a
        # database error rather than a code-review promise: two concurrent
        # writers cannot both claim the same sequence for one application.
        Index('uq_application_transition_sequence', 'application_id', 'sequence',
              unique=True),
        Index('ix_application_transition_application', 'application_id'),
        Index('ix_application_transition_occurred', 'occurred_at'),
    )


# ---------------------------------------------------------------------------
# Schema
# ---------------------------------------------------------------------------
def initialize_application_state_schema(bind=None):
    """Create this module's tables and indexes. Additive and idempotent.

    Same convention as #44 and #45: new tables only. No existing table,
    column, index or row is altered, so a pre-#46 database upgrades by
    gaining tables and needs no destructive migration. Existing applications
    are bootstrapped lazily on first contact (`ensure_state`), never by a
    bulk rewrite at startup.

    `bind` is an already-open connection to emit the DDL on. It matters:
    SQLite allows one writer, so creating these tables on a *second*
    connection while a caller's transaction is open would deadlock against
    that caller's own write lock. Callers that already hold a transaction
    pass theirs; startup passes nothing and gets its own.
    """
    statements = (
        'CREATE UNIQUE INDEX IF NOT EXISTS uq_application_state_application '
        'ON application_states (application_id)',
        'CREATE INDEX IF NOT EXISTS ix_application_state_current '
        'ON application_states (current_state)',
        'CREATE UNIQUE INDEX IF NOT EXISTS uq_application_transition_sequence '
        'ON application_state_transitions (application_id, sequence)',
        'CREATE INDEX IF NOT EXISTS ix_application_transition_application '
        'ON application_state_transitions (application_id)',
        'CREATE INDEX IF NOT EXISTS ix_application_transition_occurred '
        'ON application_state_transitions (occurred_at)',
    )
    tables = [ApplicationStateRecord.__table__, ApplicationStateTransition.__table__]
    if bind is not None:
        Base.metadata.create_all(bind, tables=tables)
        # create_all() emits __table_args__ indexes only when it creates the
        # table itself; ensure them for a database whose table already existed.
        for statement in statements:
            bind.execute(text(statement))
        return
    Base.metadata.create_all(engine, tables=tables)
    with engine.begin() as connection:
        for statement in statements:
            connection.execute(text(statement))


def schema_ready(bind=None):
    """Whether the canonical tables exist yet (non-destructive check)."""
    from sqlalchemy import inspect
    try:
        inspector = inspect(bind if bind is not None else engine)
        return (inspector.has_table(ApplicationStateRecord.__tablename__)
                and inspector.has_table(ApplicationStateTransition.__tablename__))
    except Exception:
        return False


def purge_all_state():
    """Delete every canonical state row and its history.

    Used only by the privacy controls' explicit deletion scopes. Ordinary
    application operation never removes a history row.
    """
    if not schema_ready():
        return
    with Session.begin() as db:
        db.execute(sql_delete(ApplicationStateTransition))
        db.execute(sql_delete(ApplicationStateRecord))


# ---------------------------------------------------------------------------
# Value hygiene
# ---------------------------------------------------------------------------
def _accepted_tokens():
    """The complete accepted evidence-token vocabulary.

    Built from the modules that actually produce tokens, so the accepted set
    cannot drift from what #45 emits, and an unknown token -- which is what a
    leaked company name or subject line would look like -- is dropped.
    """
    from . import gmail_confirmations as confirmations
    from . import gmail_content as content
    tokens = set(OWN_TOKENS)
    tokens |= set(confirmations.ALL_SIGNALS)
    tokens.add(confirmations.TOKEN_TEMPLATE_WITHOUT_SENDER)
    tokens.add(confirmations.TOKEN_UNSAFE_LINKS_DROPPED)
    # Derived, not transcribed: the authentication vocabulary is exactly the
    # product of `gmail_content`'s own mechanism and verdict tuples, so
    # adding a verdict there cannot leave this set stale.
    tokens |= {f'AUTH_{mechanism.upper()}_{verdict}'
               for mechanism in content.AUTH_MECHANISMS
               for verdict in content.AUTH_VERDICTS}
    tokens |= {'BODY_TRUNCATED', 'MALFORMED_PART_SKIPPED', 'ATTACHMENT_SKIPPED',
               'MIME_DEPTH_EXCEEDED', 'MIME_PART_LIMIT_REACHED',
               'UNSAFE_LINKS_DROPPED', 'OUTSIDE_INITIAL_CONFIRMATION_SCOPE'}
    return tokens


def _bounded_tokens(values):
    """Keep only known tokens, bounded in count and length, sorted."""
    if not values:
        return []
    accepted = _accepted_tokens()
    kept = {value for value in values
            if isinstance(value, str) and len(value) <= MAX_TOKEN_CHARS
            and value in accepted}
    return sorted(kept)[:MAX_EVIDENCE_TOKENS]


def _bounded_parser_id(value):
    """A parser identifier is kept only if it names a parser that exists.

    `gmail_confirmations` writes this field from its own fixed parser list,
    so today it cannot be attacker-controlled. Validating it here anyway
    means the history's parser column stays a closed vocabulary even if some
    future evidence producer is less careful, rather than a free-text field
    that merely happens to be short.
    """
    from . import gmail_confirmations as confirmations
    known = set(confirmations.PARSER_IDS) | {confirmations.GENERIC_PARSER_ID}
    return value if isinstance(value, str) and value in known else ''


def _bounded_identifier(value, limit=MAX_IDENTIFIER_CHARS):
    """An identifier is kept only if it is a short, printable ASCII token."""
    if not isinstance(value, str) or not value:
        return ''
    trimmed = value[:limit]
    if any(character < ' ' or character > '~' for character in trimmed):
        return ''
    return trimmed


def parse_timestamp(value):
    """A timezone-aware datetime for an ISO-8601 string, or `None`.

    Deliberately strict and exception-free: a malformed, absent or
    non-string timestamp from external evidence yields `None` and the caller
    falls back to the recording time with an explicit token, rather than
    raising out of a reconciliation run or storing a broken value.
    """
    if not isinstance(value, str) or not value.strip():
        return None
    text_value = value.strip()
    if text_value.endswith(('Z', 'z')):
        text_value = text_value[:-1] + '+00:00'
    try:
        parsed = datetime.fromisoformat(text_value)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed


def _occurrence(occurred_at, tokens, clock=None):
    """Normalize an asserted occurrence time, recording what happened to it."""
    reference = clock or datetime.now(timezone.utc)
    parsed = parse_timestamp(occurred_at)
    if parsed is None:
        if occurred_at:
            tokens.append(TOKEN_OCCURRED_AT_INVALID)
        return reference.isoformat()
    if parsed > reference + MAX_FUTURE_SKEW:
        tokens.append(TOKEN_OCCURRED_AT_FUTURE)
        return reference.isoformat()
    return parsed.astimezone(timezone.utc).isoformat()


# ---------------------------------------------------------------------------
# Results
# ---------------------------------------------------------------------------
class StateDecision:
    """The outcome of one `assert_state()` call. A value object."""

    __slots__ = ('applied', 'application_id', 'previous_state', 'current_state',
                 'reason_code', 'transition_id', 'sequence')

    def __init__(self, *, applied, application_id, previous_state, current_state,
                 reason_code, transition_id=0, sequence=0):
        self.applied = applied
        self.application_id = application_id
        self.previous_state = previous_state
        self.current_state = current_state
        self.reason_code = reason_code
        self.transition_id = transition_id
        self.sequence = sequence

    def as_dict(self):
        return {'applied': self.applied, 'application_id': self.application_id,
                'previous_state': self.previous_state,
                'current_state': self.current_state,
                'reason_code': self.reason_code,
                'transition_id': self.transition_id, 'sequence': self.sequence}


# ---------------------------------------------------------------------------
# Bootstrap
# ---------------------------------------------------------------------------
def _derive_legacy_state(db, application):
    """`(state, tokens, occurred_at)` truthfully derived from existing rows.

    Only what the existing data actually supports is used, in decreasing
    order of specificity: the campaign stage, then `Application.status`, then
    `Job.status`. Nothing is invented -- no date, no Gmail evidence, no
    confidence, and no intermediate transitions the database never recorded.
    An application whose legacy values say nothing canonical starts at
    DISCOVERED with an explicit `LEGACY_NO_EVIDENCE` token.
    """
    tokens = []
    tracking = application.tracking if isinstance(application.tracking, dict) else {}
    state = canonical_for_legacy(tracking.get('stage'))
    if state is not None:
        tokens.append(TOKEN_LEGACY_STAGE_DERIVED)
    if state is None:
        state = canonical_for_legacy(application.status)
        if state is not None:
            tokens.append(TOKEN_LEGACY_STATUS_DERIVED)
    if state is None and application.job_id:
        job = db.get(Job, application.job_id)
        if job is not None:
            state = canonical_for_legacy(job.status)
            if state is not None:
                tokens.append(TOKEN_LEGACY_JOB_STATUS_DERIVED)
    if state is None:
        state = DISCOVERED
        tokens.append(TOKEN_LEGACY_NO_EVIDENCE)

    # Only an applied_date the record already carries may date the bootstrap,
    # and only for a state at or past APPLIED. Otherwise the row's own
    # creation time is used -- an honest "this is when ASTRA first knew",
    # not a claim about when the application happened.
    occurred_at = ''
    if ORDINAL[state] >= ORDINAL[APPLIED] and application.applied_date:
        if parse_timestamp(application.applied_date) is not None:
            occurred_at = application.applied_date
            tokens.append(TOKEN_APPLIED_DATE_PRESENT)
    return state, tokens, occurred_at or application.created_at or now()


def _write_bootstrap(db, application):
    """Create the projection and its single bootstrap history row."""
    state, tokens, occurred_at = _derive_legacy_state(db, application)
    bounded = _bounded_tokens(tokens)
    transition = ApplicationStateTransition(
        application_id=application.id, sequence=1, previous_state='',
        new_state=state, source_category=SOURCE_LEGACY_MIGRATION,
        asserted_by='LEGACY_BOOTSTRAP', confidence='',
        evidence_tokens=bounded, field_agreement=[],
        occurred_at=_occurrence(occurred_at, []), recorded_at=now(),
        reason_code=REASON_LEGACY_BOOTSTRAP)
    db.add(transition)
    db.flush()
    record = ApplicationStateRecord(
        application_id=application.id, current_state=state,
        state_ordinal=ORDINAL[state], manual_ordinal=-1,
        source_category=SOURCE_LEGACY_MIGRATION,
        entered_at=transition.occurred_at, sequence=1)
    db.add(record)
    db.flush()
    return record


def ensure_schema(bind=None):
    """Create this module's tables if they are missing. Cheap and idempotent.

    The canonical state service is reachable from the pre-existing campaign,
    job-status and browser paths, which a caller can exercise after plain
    `models.initialize()` without ever starting the app's lifespan. Checking
    here -- one `has_table` query on a path that already writes -- means a
    user assertion is never silently dropped because the additive tables had
    not been created yet, and never depends on import order.

    `bind` is the caller's open connection, when it has one; see
    `initialize_application_state_schema()` for why that is not optional
    under an open SQLite write transaction.
    """
    if not schema_ready(bind):
        initialize_application_state_schema(bind)


def ensure_state(db, application):
    """Return the projection for `application`, bootstrapping it if absent.

    Idempotent and safe against a concurrent bootstrap: the unique index on
    `application_id` makes a lost race an `IntegrityError` that resolves by
    re-reading the winner's row, so two callers can never produce two
    projections or two bootstrap history rows.
    """
    record = db.scalar(select(ApplicationStateRecord).where(
        ApplicationStateRecord.application_id == application.id))
    if record is not None:
        return record
    savepoint = db.begin_nested()
    try:
        record = _write_bootstrap(db, application)
        savepoint.commit()
        return record
    except IntegrityError:
        savepoint.rollback()
        return db.scalar(select(ApplicationStateRecord).where(
            ApplicationStateRecord.application_id == application.id))


# ---------------------------------------------------------------------------
# The one place a canonical state changes
# ---------------------------------------------------------------------------
#: Serializes canonical writes inside this process. The unique indexes are
#: the real guarantee; this only avoids gratuitous retry churn between
#: threads in the same interpreter.
_write_lock = threading.RLock()


def assert_state(db, application, new_state, *, source_category,
                 asserted_by='USER', confidence='', reason_code=None,
                 gmail_account_id='', gmail_message_id='',
                 gmail_confirmation_id=0, parser_id='', evidence_tokens=(),
                 field_agreement=(), occurred_at='', clock=None):
    """Attempt one canonical transition. The **only** way state changes.

    Returns a `StateDecision`; it never raises for a refused transition,
    because refusal is a normal, recordable outcome rather than an error.
    The caller decides whether a refusal is worth surfacing.

    Every accepted transition appends exactly one history row and updates the
    projection in the same unit of work, so the database can never hold a new
    current state without the history row that justifies it.

    All gating happens here, in this order, so no caller can bypass it:

    1. The state and source vocabulary must be known.
    2. A self-transition is a no-op.
    3. The transition table must permit `previous -> new`.
    4. An automated source may only set a state in `AUTOMATED_TARGET_STATES`
       and only at `AUTOMATIC_CONFIDENCE`.
    5. An automated source may never reach a state at or below one a manual
       source already asserted.
    """
    if new_state not in STATES:
        return StateDecision(applied=False, application_id=getattr(application, 'id', 0),
                             previous_state='', current_state='',
                             reason_code=REFUSED_UNKNOWN_STATE)
    if source_category not in SOURCE_CATEGORIES:
        return StateDecision(applied=False, application_id=getattr(application, 'id', 0),
                             previous_state='', current_state='',
                             reason_code=REFUSED_UNKNOWN_SOURCE)
    if application is None or not getattr(application, 'id', 0):
        return StateDecision(applied=False, application_id=0, previous_state='',
                             current_state='', reason_code=REFUSED_NO_APPLICATION)

    with _write_lock:
        ensure_schema(db.connection())
        record = ensure_state(db, application)
        previous = record.current_state

        if previous == new_state:
            return StateDecision(applied=False, application_id=application.id,
                                 previous_state=previous, current_state=previous,
                                 reason_code=REFUSED_NO_CHANGE,
                                 sequence=record.sequence)
        if previous in TERMINAL:
            return StateDecision(applied=False, application_id=application.id,
                                 previous_state=previous, current_state=previous,
                                 reason_code=REFUSED_TERMINAL,
                                 sequence=record.sequence)
        if not is_permitted(previous, new_state):
            return StateDecision(applied=False, application_id=application.id,
                                 previous_state=previous, current_state=previous,
                                 reason_code=REFUSED_NOT_PERMITTED,
                                 sequence=record.sequence)

        if source_category in AUTOMATED_SOURCES:
            if new_state not in AUTOMATED_TARGET_STATES:
                return StateDecision(applied=False, application_id=application.id,
                                     previous_state=previous, current_state=previous,
                                     reason_code=REFUSED_STATE_NOT_AUTOMATABLE,
                                     sequence=record.sequence)
            if confidence != AUTOMATIC_CONFIDENCE:
                return StateDecision(applied=False, application_id=application.id,
                                     previous_state=previous, current_state=previous,
                                     reason_code=REFUSED_CONFIDENCE_TOO_LOW,
                                     sequence=record.sequence)
            # Defence in depth beside the transition table: even a permitted
            # forward move is refused when a manual source already asserted
            # an equal or stronger state, so no automated signal can
            # overwrite, supersede or re-assert the user's own record.
            if ORDINAL[new_state] <= record.manual_ordinal:
                return StateDecision(applied=False, application_id=application.id,
                                     previous_state=previous, current_state=previous,
                                     reason_code=REFUSED_WEAKER_THAN_MANUAL,
                                     sequence=record.sequence)

        tokens = list(evidence_tokens or ())
        occurrence = _occurrence(occurred_at, tokens, clock)
        sequence = record.sequence + 1
        transition = ApplicationStateTransition(
            application_id=application.id, sequence=sequence,
            previous_state=previous, new_state=new_state,
            source_category=source_category,
            asserted_by=_bounded_identifier(asserted_by, 64) or 'UNKNOWN',
            confidence=confidence if confidence in CONFIDENCE_LEVELS else '',
            gmail_account_id=_bounded_identifier(gmail_account_id),
            gmail_message_id=_bounded_identifier(gmail_message_id),
            gmail_confirmation_id=int(gmail_confirmation_id or 0),
            parser_id=_bounded_parser_id(parser_id),
            evidence_tokens=_bounded_tokens(tokens),
            field_agreement=_bounded_fields(field_agreement),
            occurred_at=occurrence, recorded_at=now(),
            reason_code=reason_code if reason_code in ACCEPTED_REASONS
            else _default_reason(source_category))
        # The append is the point of no return, so it is the thing guarded.
        # A savepoint keeps the caller's transaction usable when the unique
        # index rejects a duplicate sequence, instead of poisoning it.
        savepoint = db.begin_nested()
        try:
            db.add(transition)
            db.flush()
            savepoint.commit()
        except IntegrityError:
            savepoint.rollback()
            return StateDecision(applied=False, application_id=application.id,
                                 previous_state=previous, current_state=previous,
                                 reason_code=REFUSED_CONCURRENT_UPDATE,
                                 sequence=record.sequence)

        record.current_state = new_state
        record.state_ordinal = ORDINAL[new_state]
        record.source_category = source_category
        record.entered_at = occurrence
        record.sequence = sequence
        record.schema_version = SCHEMA_VERSION
        if source_category in MANUAL_SOURCES:
            record.manual_ordinal = max(record.manual_ordinal, ORDINAL[new_state])
        db.flush()
        return StateDecision(applied=True, application_id=application.id,
                             previous_state=previous, current_state=new_state,
                             reason_code=transition.reason_code,
                             transition_id=transition.id, sequence=sequence)


def _default_reason(source_category):
    return {SOURCE_USER_ACTION: REASON_USER_ACTION,
            SOURCE_USER_CONFIRMED_GMAIL: REASON_GMAIL_USER_CONFIRMED,
            SOURCE_GMAIL_PARSER: REASON_GMAIL_AUTOMATIC,
            SOURCE_LEGACY_MIGRATION: REASON_LEGACY_BOOTSTRAP,
            SOURCE_BROWSER_CONFIRMATION: REASON_BROWSER_CONFIRMED,
            SOURCE_FUTURE_INTEGRATION: REASON_USER_ACTION}.get(
                source_category, REASON_USER_ACTION)


#: Reconciliation field names that may be recorded as agreement evidence.
#: Defined here rather than in the reconciliation module so the history's
#: complete vocabulary is reviewable in one file.
FIELD_COMPANY = 'COMPANY'
FIELD_ROLE = 'ROLE'
FIELD_DATE = 'DATE_PROXIMITY'
FIELD_URL = 'APPLICATION_URL'
FIELD_PLATFORM = 'SOURCE_PLATFORM'
AGREEMENT_FIELDS = (FIELD_COMPANY, FIELD_ROLE, FIELD_DATE, FIELD_URL, FIELD_PLATFORM)


def _bounded_fields(values):
    if not values:
        return []
    return sorted({value for value in values if value in AGREEMENT_FIELDS})


# ---------------------------------------------------------------------------
# Integration helper for the legacy paths
# ---------------------------------------------------------------------------
def prime_state(db, application):
    """Bootstrap an application's canonical state *before* a legacy path
    edits the columns the bootstrap reads.

    Order matters and is easy to get wrong. `campaign.track()` and
    `services.set_status()` write the new stage/status into
    `Application.tracking`, `Application.status` and `Job.status` and only
    then hand the assertion to this module. A first-ever bootstrap at that
    point would derive the state from the value the user's action had just
    written, silently recording their change as `LEGACY_MIGRATION` rather
    than `USER_ACTION` -- losing the provenance, and leaving `manual_ordinal`
    unset so a later automated signal could re-assert the same state.
    Priming first means the bootstrap records where the application actually
    was, and the user's change is recorded as the user's own transition.

    Tolerates `None` (nothing existed to bootstrap) and never raises.
    """
    if application is None or not getattr(application, 'id', 0):
        return None
    ensure_schema(db.connection())
    return ensure_state(db, application)


def record_legacy_assertion(db, application, legacy_value, *, source_category,
                            asserted_by='USER', occurred_at='',
                            reason_code=REASON_USER_ACTION):
    """Project a legacy stage/status change onto the canonical model.

    Called by the pre-existing paths (`campaign.track`, the job status
    action, the browser confirmation path) *after* they have done what they
    already did. It never raises and never changes their behaviour, so
    existing API and frontend compatibility is preserved exactly; it only
    ensures the canonical model sees every publicly reachable state change
    and either records it or records why it could not.

    Returns a `StateDecision`, or `None` when the legacy value carries no
    canonical meaning (`SKIP`, `FAILED`, `NO_RESPONSE`).
    """
    state = canonical_for_legacy(legacy_value)
    if state is None:
        return None
    return assert_state(db, application, state, source_category=source_category,
                        asserted_by=asserted_by, reason_code=reason_code,
                        occurred_at=occurred_at)


# ---------------------------------------------------------------------------
# Bounded read models
# ---------------------------------------------------------------------------
MAX_LISTED_TRANSITIONS = 200


def _public_transition(row):
    """One history row as the API returns it. Bounded fields only."""
    return {'id': row.id, 'application_id': row.application_id,
            'sequence': row.sequence, 'previous_state': row.previous_state,
            'new_state': row.new_state, 'source_category': row.source_category,
            'asserted_by': row.asserted_by, 'confidence': row.confidence,
            'gmail_account_id': row.gmail_account_id,
            'gmail_message_id': row.gmail_message_id,
            'gmail_confirmation_id': row.gmail_confirmation_id,
            'parser_id': row.parser_id,
            'evidence_tokens': list(row.evidence_tokens or []),
            'field_agreement': list(row.field_agreement or []),
            'occurred_at': row.occurred_at, 'recorded_at': row.recorded_at,
            'reason_code': row.reason_code}


def _public_state(row):
    return {'application_id': row.application_id,
            'current_state': row.current_state,
            'state_ordinal': row.state_ordinal,
            'manual_ordinal': row.manual_ordinal,
            'source_category': row.source_category,
            'entered_at': row.entered_at, 'sequence': row.sequence,
            'schema_version': row.schema_version}


def state_of(application_id):
    """Canonical state plus history for one application, or `None`.

    Bootstraps a pre-#46 application on first read, which is where "existing
    applications first encountered after upgrade" is handled: the first
    reader, not a bulk startup migration, creates the truthful legacy entry.
    """
    with Session.begin() as db:
        ensure_schema(db.connection())
        application = db.get(Application, application_id)
        if application is None:
            return None
        record = ensure_state(db, application)
        rows = db.scalars(
            select(ApplicationStateTransition)
            .where(ApplicationStateTransition.application_id == application_id)
            .order_by(ApplicationStateTransition.sequence)
            .limit(MAX_LISTED_TRANSITIONS)).all()
        return {'schema': SCHEMA_VERSION, 'state': _public_state(record),
                'history': [_public_transition(row) for row in rows],
                'history_count': len(rows),
                'legacy': {'application_status': application.status,
                           'campaign_stage': (application.tracking or {}).get('stage', ''),
                           'authoritative_field': 'application_states.current_state'}}


def transition_history(application_id, *, limit=MAX_LISTED_TRANSITIONS):
    """Bounded append-only history for one application."""
    ensure_schema()
    bounded = max(1, min(int(limit), MAX_LISTED_TRANSITIONS))
    with Session() as db:
        rows = db.scalars(
            select(ApplicationStateTransition)
            .where(ApplicationStateTransition.application_id == application_id)
            .order_by(ApplicationStateTransition.sequence)
            .limit(bounded)).all()
        return [_public_transition(row) for row in rows]


def state_summary():
    """Counts per canonical state. The bounded read #47 needs for a dashboard."""
    ensure_schema()
    from sqlalchemy import func
    with Session() as db:
        rows = db.execute(
            select(ApplicationStateRecord.current_state, func.count())
            .group_by(ApplicationStateRecord.current_state)).all()
    counts = {state: 0 for state in STATES}
    for state, count in rows:
        if state in counts:
            counts[state] = count
    return {'schema': SCHEMA_VERSION, 'states': counts,
            'total': sum(counts.values()),
            'authoritative_field': 'application_states.current_state',
            'transition_table': {state: sorted(targets)
                                 for state, targets in PERMITTED.items()}}
