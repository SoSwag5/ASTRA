"""Conservative multi-field reconciliation of Gmail evidence (#46).

This module is the only bridge between #45's minimized Gmail evidence
(`gmail_confirmations`) and #46's authoritative application state
(`application_state`). It decides, for one piece of evidence, **which
existing application it is about** -- and refuses to guess.

Design rules, each of which is a test:

* **Multiple independent fields, always.** A single agreeing field never
  merges anything. A strong match needs the employer to agree *and* at least
  two further independent corroborations among role, application date
  proximity, application-URL identity and source platform.
* **Deterministic comparison only.** Normalized-key equality, a fixed date
  window and URL identity -- reusing `backend/normalization.py`'s existing
  keys so ASTRA has one definition of "the same employer" rather than two.
  There is no AI, no embedding similarity, no web lookup and no mailbox
  search anywhere in this file.
* **Ambiguity never mutates.** More than one strong candidate is a review
  item, not a coin flip.
* **Nothing is ever created.** Reconciliation links evidence to an existing
  application or leaves it unmatched. It never fabricates a `Job` or an
  `Application`, so an unsolicited or spoofed message cannot conjure a
  record, and an existing manually recorded application cannot be duplicated.
* **Idempotent by construction.** One link row per Gmail confirmation,
  enforced by a unique index rather than by the code path that writes it, so
  a replayed sync or a concurrent run cannot produce two links, two
  applications or two transitions.

Confidence gating lives in `application_state.assert_state()`, not here, so
there is exactly one place that decides whether a state may change.
`gmail_confirmations` currently detects only `APPLICATION_CONFIRMED`, so the
only canonical state this module ever proposes is `APPLIED`.
"""
from datetime import timedelta

from sqlalchemy import ForeignKey, Index, JSON, delete as sql_delete, select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Mapped, mapped_column

from . import application_state as states
from . import gmail_confirmations as confirmations
# Imported at module scope, not lazily: `GmailApplicationLink` carries a real
# foreign key to `gmail_confirmations`, so that table must be registered on
# `Base.metadata` before any `create_all()` over the whole metadata runs.
from . import gmail_sync
from .gmail_sync import GmailConfirmation
from .application_state import (AGREEMENT_FIELDS, FIELD_COMPANY, FIELD_DATE,
                                FIELD_PLATFORM, FIELD_ROLE, FIELD_URL)
from .models import Application, Base, Job, JobObservation, Record, Session, engine, now
from .normalization import employer_key, normalize_url_for_identity, title_key
from .security_events import record as security_event

SCHEMA_VERSION = 'application-reconciliation-v1'

# ---------------------------------------------------------------------------
# Matching parameters
# ---------------------------------------------------------------------------
#: How far apart a recorded application date and a confirmation's received
#: timestamp may be and still corroborate each other. Wide enough for a
#: delayed acknowledgement, narrow enough that two unrelated applications to
#: the same employer months apart do not agree by accident.
DATE_PROXIMITY = timedelta(days=14)
#: Corroborating fields required *in addition to* an agreeing employer for a
#: match to be strong enough to act on. Two, so a strong match always rests
#: on at least three independent fields.
REQUIRED_CORROBORATIONS = 2
#: Upper bound on candidates considered for one piece of evidence. The
#: employer key is indexed (`jobs.normalized_employer_key`), so this bounds
#: the work a single crafted company name can cause.
MAX_CANDIDATES = 50
#: Upper bound on evidence rows one reconciliation run will process.
MAX_RUN_EVIDENCE = 200

#: The #45 parser platforms mapped onto the provider families and legacy
#: `Job.source` labels ASTRA already uses. Absent from this map means the
#: platform cannot corroborate anything -- never that it disagrees.
PLATFORM_FAMILIES = {
    'GREENHOUSE': frozenset({'greenhouse'}),
    'LEVER': frozenset({'lever'}),
    'WORKDAY': frozenset({'workday'}),
}
PARSER_PLATFORMS = {parser.parser_id: parser.platform for parser in confirmations.PARSERS}

# ---------------------------------------------------------------------------
# Bounded decision vocabulary
# ---------------------------------------------------------------------------
DECISION_LINKED = 'LINKED'
DECISION_NEEDS_REVIEW = 'NEEDS_REVIEW'
DECISION_NO_ACTION = 'NO_ACTION'
DECISION_USER_CONFIRMED = 'USER_CONFIRMED'
DECISION_USER_REJECTED = 'USER_REJECTED'
DECISIONS = (DECISION_LINKED, DECISION_NEEDS_REVIEW, DECISION_NO_ACTION,
             DECISION_USER_CONFIRMED, DECISION_USER_REJECTED)

REASON_HIGH_UNIQUE_MATCH = 'HIGH_CONFIDENCE_UNIQUE_STRONG_MATCH'
REASON_MEDIUM_NEEDS_REVIEW = 'MEDIUM_CONFIDENCE_NEEDS_USER_REVIEW'
REASON_AMBIGUOUS = 'AMBIGUOUS_MULTIPLE_STRONG_MATCHES'
REASON_LOW_CONFIDENCE = 'LOW_CONFIDENCE_NEVER_MUTATES'
REASON_NO_STRONG_MATCH = 'NO_SUFFICIENTLY_STRONG_MATCH'
REASON_SINGLE_FIELD_ONLY = 'SINGLE_FIELD_AGREEMENT_ONLY'
REASON_NO_CANDIDATES = 'NO_CANDIDATE_APPLICATION'
REASON_STATE_UNSUPPORTED = 'DETECTED_STATE_NOT_SUPPORTED'
REASON_EVIDENCE_INVALID = 'EVIDENCE_FIELDS_UNUSABLE'
REASON_TRANSITION_REFUSED = 'STATE_SERVICE_REFUSED_TRANSITION'
REASON_USER_CONFIRMED = 'USER_CONFIRMED_EVIDENCE'
REASON_USER_REJECTED = 'USER_REJECTED_EVIDENCE'
REASON_LINK_NOT_REVIEWABLE = 'LINK_NOT_IN_REVIEW_STATE'
#: Both sides named a job-specific requisition URL and they are different
#: postings. That is positive evidence of two distinct applications, not
#: merely absent agreement, so it blocks automatic linking outright.
REASON_URL_CONFLICT = 'CONTRADICTORY_APPLICATION_URL_IDENTITY'
REASON_CODES = (REASON_HIGH_UNIQUE_MATCH, REASON_MEDIUM_NEEDS_REVIEW,
                REASON_AMBIGUOUS, REASON_LOW_CONFIDENCE, REASON_NO_STRONG_MATCH,
                REASON_SINGLE_FIELD_ONLY, REASON_NO_CANDIDATES,
                REASON_STATE_UNSUPPORTED, REASON_EVIDENCE_INVALID,
                REASON_TRANSITION_REFUSED,
                REASON_USER_CONFIRMED, REASON_USER_REJECTED,
                REASON_LINK_NOT_REVIEWABLE, REASON_URL_CONFLICT)

#: Detected states this module knows how to act on, mapped to the canonical
#: state they propose. #45 produces only the first; the deferred later-stage
#: states are deliberately absent, so there is no code path by which a
#: later-stage message -- if one were ever parsed -- could silently acquire
#: a transition without this map being changed under review.
DETECTED_STATE_TO_CANONICAL = {
    confirmations.APPLICATION_CONFIRMED: states.APPLIED,
}


# ---------------------------------------------------------------------------
# Table
# ---------------------------------------------------------------------------
class GmailApplicationLink(Record, Base):
    """One durable reconciliation decision per Gmail confirmation.

    The row exists whatever the outcome -- linked, needs review, or no
    action -- because a decision that was not recorded is a decision that
    will be taken again, and re-taking it is exactly the non-idempotency
    #46 forbids. The unique index on `gmail_confirmation_id` is what makes
    replay and concurrency safe in the database rather than only in code.

    No column here can hold message content. `matched_fields` holds only
    members of `AGREEMENT_FIELDS`; `reason_code` only members of
    `REASON_CODES`.
    """
    __tablename__ = 'gmail_application_links'

    gmail_confirmation_id: Mapped[int] = mapped_column(
        ForeignKey('gmail_confirmations.id'), unique=True)
    #: Null until (and unless) the evidence is linked to an application.
    application_id: Mapped[int | None] = mapped_column(
        ForeignKey('applications.id'), nullable=True)
    decision: Mapped[str] = mapped_column(default=DECISION_NO_ACTION)
    reason_code: Mapped[str] = mapped_column(default=REASON_NO_CANDIDATES)
    confidence: Mapped[str] = mapped_column(default='')
    matched_fields: Mapped[list] = mapped_column(JSON, default=list)
    #: How many candidate applications reached a strong match. Explains an
    #: ambiguous outcome without naming any of them.
    candidate_count: Mapped[int] = mapped_column(default=0)
    strong_candidate_count: Mapped[int] = mapped_column(default=0)
    #: `application_state_transitions.id` created by this decision, or 0.
    transition_id: Mapped[int] = mapped_column(default=0)
    resolved_at: Mapped[str] = mapped_column(default=now)
    schema_version: Mapped[str] = mapped_column(default=SCHEMA_VERSION)

    __table_args__ = (
        Index('uq_gmail_application_link_confirmation', 'gmail_confirmation_id',
              unique=True),
        Index('ix_gmail_application_link_application', 'application_id'),
        Index('ix_gmail_application_link_decision', 'decision'),
    )


def initialize_reconciliation_schema():
    """Create the link table and indexes. Additive and idempotent.

    The evidence and canonical-state schemas are ensured first, because this
    table references both and SQLite enforces foreign keys at insert time
    (`PRAGMA foreign_keys=ON` in `backend/models.py`).
    """
    gmail_sync.initialize_sync_schema()
    states.initialize_application_state_schema()
    Base.metadata.create_all(engine, tables=[GmailApplicationLink.__table__])
    with engine.begin() as connection:
        connection.execute(text(
            'CREATE UNIQUE INDEX IF NOT EXISTS uq_gmail_application_link_confirmation '
            'ON gmail_application_links (gmail_confirmation_id)'))
        connection.execute(text(
            'CREATE INDEX IF NOT EXISTS ix_gmail_application_link_application '
            'ON gmail_application_links (application_id)'))
        connection.execute(text(
            'CREATE INDEX IF NOT EXISTS ix_gmail_application_link_decision '
            'ON gmail_application_links (decision)'))


def schema_ready():
    from sqlalchemy import inspect
    try:
        return inspect(engine).has_table(GmailApplicationLink.__tablename__)
    except Exception:
        return False


def purge_all_links():
    """Delete every reconciliation link.

    Called by the privacy controls before Gmail evidence itself is purged,
    so the foreign key to `gmail_confirmations` is released in a safe order.
    Deleting links never deletes evidence: #45's lifecycle is unchanged --
    disconnect preserves evidence, full local erase removes it.
    """
    if not schema_ready():
        return
    with Session.begin() as db:
        db.execute(sql_delete(GmailApplicationLink))


def purge_links_for_applications():
    """Delete links that belong to an application, keeping unmatched ones.

    Used by the 'history' deletion scope: application-linked reconciliation
    records go with the application history, while evidence that was never
    linked to one is not application history and is left alone, as is the
    Gmail evidence itself.
    """
    if not schema_ready():
        return
    with Session.begin() as db:
        db.execute(sql_delete(GmailApplicationLink).where(
            GmailApplicationLink.application_id.is_not(None)))


# ---------------------------------------------------------------------------
# Field agreement
# ---------------------------------------------------------------------------
class Candidate:
    """One existing application considered for one piece of evidence."""

    __slots__ = ('application_id', 'job_id', 'fields', 'conflicts')

    def __init__(self, application_id, job_id, fields, conflicts=()):
        self.application_id = application_id
        self.job_id = job_id
        self.fields = fields
        #: Fields on which the two records positively **contradict** each
        #: other. Distinct from a field that simply did not agree: absence of
        #: agreement is no information, a contradiction is information.
        self.conflicts = set(conflicts)

    @property
    def corroborations(self):
        return sorted(self.fields - {FIELD_COMPANY})

    @property
    def corroborated(self):
        """The employer agrees and at least two other independent fields
        agree with it. One field alone is never enough, and the employer
        alone is never enough either. This is the *agreement* test; it says
        nothing about contradictions."""
        return (FIELD_COMPANY in self.fields
                and len(self.corroborations) >= REQUIRED_CORROBORATIONS)

    @property
    def strong(self):
        """Strong enough for ASTRA to link the records by itself.

        Requires corroboration **and** the absence of any contradiction. A
        contradictory requisition URL is decisive: no amount of agreement on
        employer, title, date or platform can outweigh two records naming
        different postings, because those four fields are exactly what two
        genuinely separate applications to the same employer would share.
        """
        return self.corroborated and not self.conflicts

    @property
    def confirmable(self):
        """Strong enough for the *user* to link the records.

        A contradiction blocks automatic linking but must not make the
        review item unactionable -- the user is the only party who can say
        whether two postings are the same application, and a review queue
        whose items cannot be resolved is the defect this distinction
        exists to avoid.
        """
        return self.corroborated


def _platform_for(row):
    """The #45 platform that produced this evidence, or '' for the fallback."""
    return PARSER_PLATFORMS.get(row.parser_id, '')


def _job_platform_families(db, job):
    """Provider families ASTRA already associates with this job.

    Uses the legacy `Job.source` label and every #40 `JobObservation`
    provenance row, so a job discovered through a provider adapter and a job
    imported by hand are both comparable without inventing a platform for
    either.
    """
    families = set()
    if job.source:
        families.add(job.source.strip().lower())
    for observation in db.scalars(select(JobObservation).where(
            JobObservation.job_id == job.id).limit(10)):
        if observation.provider_family:
            families.add(observation.provider_family.strip().lower())
    return families


def _job_url_identities(job):
    """Every URL identity this job is known by, as matching keys."""
    identities = set()
    for value in (job.apply_url, job.job_url, job.canonical_url):
        identity = normalize_url_for_identity(value) if value else None
        if identity:
            identities.add(identity)
    return identities


def compare_fields(db, row, application, job):
    """`(agreeing, conflicting)` fields between evidence and one record.

    Every comparison is exact equality of a deterministic key, or a fixed
    date window. A field whose value is missing or unusable on either side
    contributes nothing -- it never counts as agreement and never counts as
    disagreement, so absent information cannot manufacture a match.

    Exactly one field can *contradict*: the application URL. Both sides must
    produce a job-specific identity for that to happen, which is what keeps
    the comparison conservative. `normalize_url_for_identity()` returns
    `None` for a generic careers root, a login/portal page or a search page,
    so such a URL establishes no identity and therefore contradicts nothing.
    Two spellings of the same posting normalize to the same key and agree.

    Company, role, date and platform are deliberately *not* treated as
    contradictions. Two different applications to the same employer routinely
    differ in title or date without either record being wrong, so a
    mismatch there is weak evidence, not a contradiction.
    """
    fields = set()
    conflicts = set()

    evidence_company = employer_key(row.detected_company or '')
    job_company = employer_key(job.company or '')
    if evidence_company and job_company and evidence_company == job_company:
        fields.add(FIELD_COMPANY)

    evidence_role = title_key(row.detected_role or '')
    job_role = title_key(job.title or '')
    if evidence_role and job_role and evidence_role == job_role:
        fields.add(FIELD_ROLE)

    received = states.parse_timestamp(row.received_at)
    recorded = (states.parse_timestamp(application.applied_date)
                or states.parse_timestamp(job.date_found))
    if received is not None and recorded is not None:
        if abs(received - recorded) <= DATE_PROXIMITY:
            fields.add(FIELD_DATE)

    evidence_url = (normalize_url_for_identity(row.application_url)
                    if row.application_url else None)
    job_urls = _job_url_identities(job)
    if evidence_url and job_urls:
        # Both records establish a requisition identity, so this comparison
        # is decisive either way.
        if evidence_url in job_urls:
            fields.add(FIELD_URL)
        else:
            conflicts.add(FIELD_URL)

    platform = _platform_for(row)
    expected = PLATFORM_FAMILIES.get(platform)
    if expected and expected & _job_platform_families(db, job):
        fields.add(FIELD_PLATFORM)

    return fields, conflicts


def agreeing_fields(db, row, application, job):
    """Only the agreeing fields. Retained for callers that do not need to
    distinguish a contradiction from a simple absence of agreement."""
    return compare_fields(db, row, application, job)[0]


def find_candidates(db, row):
    """Existing applications that could be the subject of this evidence.

    The employer key is the indexed entry point, because an agreeing
    employer is a precondition of every strong match. A candidate set is
    therefore never a full table scan, and a message with no usable employer
    produces no candidates at all rather than everything.
    """
    evidence_company = employer_key(row.detected_company or '')
    if not evidence_company:
        return []
    pairs = db.execute(
        select(Application, Job)
        .join(Job, Application.job_id == Job.id)
        .where(Job.normalized_employer_key == evidence_company)
        .order_by(Application.id)
        .limit(MAX_CANDIDATES)).all()
    candidates = []
    for application, job in pairs:
        fields, conflicts = compare_fields(db, row, application, job)
        candidates.append(Candidate(application.id, job.id, fields, conflicts))
    return candidates


# ---------------------------------------------------------------------------
# One decision
# ---------------------------------------------------------------------------
class ReconciliationResult:
    """What reconciliation decided about one piece of evidence."""

    __slots__ = ('gmail_confirmation_id', 'decision', 'reason_code', 'confidence',
                 'application_id', 'matched_fields', 'candidate_count',
                 'strong_candidate_count', 'transition_id', 'link_id')

    def __init__(self, **values):
        for name in self.__slots__:
            setattr(self, name, values.get(name))

    def as_dict(self):
        return {name: getattr(self, name) for name in self.__slots__}


def _claim(db, row):
    """Claim this confirmation for reconciliation, or report who already has it.

    Returns `(link, claimed)`. The unique index on `gmail_confirmation_id` is
    what decides: exactly one writer inserts the row, every other writer loses
    the race and reads the winner's decision instead.

    Claiming happens **before** any matching or state change, which is what
    makes concurrency safe rather than merely detected. A writer that did not
    claim the evidence never asks the state service for a transition at all,
    so two runs cannot both append to one application's history for the same
    message and then disagree about the result.
    """
    link = GmailApplicationLink(
        gmail_confirmation_id=row.id, application_id=None,
        decision=DECISION_NO_ACTION, reason_code=REASON_NO_CANDIDATES,
        confidence=row.confidence, matched_fields=[], candidate_count=0,
        strong_candidate_count=0, transition_id=0, resolved_at=now())
    savepoint = db.begin_nested()
    try:
        db.add(link)
        db.flush()
        savepoint.commit()
        return link, True
    except IntegrityError:
        savepoint.rollback()
        return db.scalar(select(GmailApplicationLink).where(
            GmailApplicationLink.gmail_confirmation_id == row.id)), False


def _resolve(db, link, *, decision, reason_code, application_id=None,
             matched_fields=(), candidate_count=0, strong_candidate_count=0,
             transition_id=0):
    """Record the outcome on an already-claimed link, in the same transaction.

    The claim and its outcome are never separately visible: both happen inside
    the caller's single unit of work, so the evidence is never consumed without
    a durable decision.
    """
    link.decision = decision
    link.reason_code = reason_code
    link.application_id = application_id
    link.matched_fields = sorted(set(matched_fields) & set(AGREEMENT_FIELDS))
    link.candidate_count = candidate_count
    link.strong_candidate_count = strong_candidate_count
    link.transition_id = transition_id
    link.resolved_at = now()
    db.flush()
    return link


def _result(row, link):
    return ReconciliationResult(
        gmail_confirmation_id=row.id, decision=link.decision,
        reason_code=link.reason_code, confidence=link.confidence,
        application_id=link.application_id,
        matched_fields=list(link.matched_fields or []),
        candidate_count=link.candidate_count,
        strong_candidate_count=link.strong_candidate_count,
        transition_id=link.transition_id, link_id=link.id)


def reconcile_confirmation(db, row):
    """Decide, atomically, what one piece of Gmail evidence means.

    The claim, the state change, its history row, the current-state projection
    and this link are written in one unit of work (the caller's transaction),
    so a failure can neither leave a new current state without its history nor
    consume the evidence without recording a decision.
    """
    link, claimed = _claim(db, row)
    if not claimed:
        # Replay, or a concurrent run that got here first. The existing
        # decision is returned unchanged: no second transition, no second
        # link, no re-evaluation.
        return _result(row, link)

    target = DETECTED_STATE_TO_CANONICAL.get(row.detected_state)
    if target is None:
        return _result(row, _resolve(db, link, decision=DECISION_NO_ACTION,
                                     reason_code=REASON_STATE_UNSUPPORTED))

    if row.confidence not in states.CONFIDENCE_LEVELS:
        return _result(row, _resolve(db, link, decision=DECISION_NO_ACTION,
                                     reason_code=REASON_EVIDENCE_INVALID))

    return _decide(db, row, link, target)


def _unlinkable_reason(candidates, conflicted, best):
    """The bounded reason why nothing could be linked automatically."""
    if conflicted:
        # Positive evidence of two distinct postings outweighs the agreement
        # on employer, title, date and platform that any two applications to
        # the same employer would share.
        return REASON_URL_CONFLICT
    if not candidates:
        return REASON_NO_CANDIDATES
    if best is not None and len(best.fields) <= 1:
        return REASON_SINGLE_FIELD_ONLY
    return REASON_NO_STRONG_MATCH


def _decide(db, row, link, target):
    """Evaluate this evidence against current records and record the outcome.

    Also used to revisit an unresolved review item, so a decision reached
    before the matching application existed is not final.
    """
    candidates = find_candidates(db, row)
    strong = [candidate for candidate in candidates if candidate.strong]
    conflicted = [candidate for candidate in candidates
                  if candidate.corroborated and candidate.conflicts]
    best = max((candidate for candidate in candidates),
               key=lambda candidate: len(candidate.fields), default=None)
    observed = sorted(best.fields) if best else []

    # LOW never mutates state and never enters the review queue: #45 caps the
    # generic fallback at LOW precisely because it verified nothing.
    if row.confidence == states.LOW:
        return _result(row, _resolve(
            db, link, decision=DECISION_NO_ACTION,
            reason_code=REASON_LOW_CONFIDENCE, matched_fields=observed,
            candidate_count=len(candidates), strong_candidate_count=len(strong)))

    if len(strong) > 1:
        # Several existing applications match equally well. Choosing one
        # would be a guess, so nothing is mutated and nothing is created.
        security_event('APPLICATION_RECONCILIATION_CONFLICT',
                       result='AMBIGUOUS_MATCH')
        return _result(row, _resolve(
            db, link, decision=DECISION_NEEDS_REVIEW,
            reason_code=REASON_AMBIGUOUS, matched_fields=observed,
            candidate_count=len(candidates), strong_candidate_count=len(strong)))

    if not strong:
        reason = _unlinkable_reason(candidates, conflicted, best)
        if reason == REASON_URL_CONFLICT:
            security_event('APPLICATION_RECONCILIATION_CONFLICT',
                           result='URL_IDENTITY_CONFLICT')
        # A single corroborated-but-contradicted candidate is offered to the
        # user as the proposed target; only they can say whether two postings
        # are one application. Anything less specific is left unattached.
        proposed = conflicted[0] if len(conflicted) == 1 else None
        # HIGH and MEDIUM evidence that could not be linked stays **visible
        # and resolvable** rather than being consumed as an unrecoverable
        # NO_ACTION: the matching application may simply not exist yet, and
        # `confirm_review()` re-evaluates candidates at confirmation time.
        # Nothing is mutated and nothing is created here either way.
        return _result(row, _resolve(
            db, link, decision=DECISION_NEEDS_REVIEW, reason_code=reason,
            application_id=proposed.application_id if proposed else None,
            matched_fields=sorted(proposed.fields) if proposed else observed,
            candidate_count=len(candidates), strong_candidate_count=0))

    match = strong[0]
    if row.confidence != states.HIGH:
        # MEDIUM with a unique strong match is still a review item: the user
        # confirms it. Nothing about the application changes until they do.
        return _result(row, _resolve(
            db, link, decision=DECISION_NEEDS_REVIEW,
            reason_code=REASON_MEDIUM_NEEDS_REVIEW,
            application_id=match.application_id,
            matched_fields=sorted(match.fields),
            candidate_count=len(candidates), strong_candidate_count=1))

    return _apply_match(db, row, link, match, target,
                        source_category=states.SOURCE_GMAIL_PARSER,
                        asserted_by='GMAIL_SYNC',
                        reason_code=states.REASON_GMAIL_AUTOMATIC,
                        decision_reason=REASON_HIGH_UNIQUE_MATCH,
                        candidate_count=len(candidates))


def _apply_match(db, row, link, match, target, *, source_category, asserted_by,
                 reason_code, decision_reason, candidate_count):
    """Ask the state service for the transition and record what it answered."""
    application = db.get(Application, match.application_id)
    decision = states.assert_state(
        db, application, target,
        source_category=source_category, asserted_by=asserted_by,
        confidence=row.confidence if source_category in states.AUTOMATED_SOURCES else '',
        reason_code=reason_code,
        gmail_account_id=row.gmail_account_id,
        gmail_message_id=row.gmail_message_id,
        gmail_confirmation_id=row.id,
        parser_id=row.parser_id,
        evidence_tokens=list(row.evidence_signals or []),
        field_agreement=sorted(match.fields),
        occurred_at=row.received_at)
    if not decision.applied:
        # The state service refused. The evidence still gets a durable,
        # explainable decision, and the application is untouched -- this is
        # where a stale, contradictory or already-satisfied signal lands.
        security_event('APPLICATION_STATE_TRANSITION_REJECTED',
                       result=decision.reason_code
                       if decision.reason_code in states.REFUSAL_REASONS else 'UNKNOWN')
        return _result(row, _resolve(
            db, link, decision=DECISION_NO_ACTION,
            reason_code=REASON_TRANSITION_REFUSED,
            application_id=match.application_id,
            matched_fields=sorted(match.fields),
            candidate_count=candidate_count, strong_candidate_count=1))
    linked = (DECISION_USER_CONFIRMED
              if source_category == states.SOURCE_USER_CONFIRMED_GMAIL
              else DECISION_LINKED)
    return _result(row, _resolve(
        db, link, decision=linked, reason_code=decision_reason,
        application_id=match.application_id,
        matched_fields=sorted(match.fields),
        candidate_count=candidate_count, strong_candidate_count=1,
        transition_id=decision.transition_id))


# ---------------------------------------------------------------------------
# Runs and review operations
# ---------------------------------------------------------------------------
def revisit_confirmation(db, row, link):
    """Re-evaluate one unresolved review item against current records.

    A decision reached when no matching application existed must not be
    final: the user may save or record that application afterwards. Only
    items still awaiting review **and not yet attached to an application**
    are revisited, so a decision the user is already looking at cannot be
    swapped underneath them.

    Re-evaluation goes through exactly the same `_decide()` path as the
    first pass, so the automatic-linking rules are identical -- HIGH with a
    unique uncontradicted match links, MEDIUM proposes a target for the user
    to confirm, and a contradiction still blocks automatic linking. It
    updates the one existing link row and never creates a second, so repeated
    runs cannot duplicate links, transitions or review items.
    """
    target = DETECTED_STATE_TO_CANONICAL.get(row.detected_state)
    if target is None:
        return _result(row, link)
    return _decide(db, row, link, target)


def reconcile_pending(*, limit=MAX_RUN_EVIDENCE):
    """Reconcile undecided confirmations and revisit unresolved review items.

    Explicitly invoked, exactly like #45's sync: there is no scheduler and no
    background reconciliation. Each piece of evidence is decided in its own
    transaction, so one failure cannot roll back decisions already durably
    recorded for earlier evidence.
    """
    initialize_reconciliation_schema()
    bounded = max(1, min(int(limit), MAX_RUN_EVIDENCE))
    summary = {'schema': SCHEMA_VERSION, 'considered': 0, 'revisited': 0,
               'linked': 0, 'needs_review': 0, 'no_action': 0,
               'by_reason': {}}
    with Session() as db:
        pending = db.scalars(
            select(GmailConfirmation.id)
            .outerjoin(GmailApplicationLink,
                       GmailApplicationLink.gmail_confirmation_id == GmailConfirmation.id)
            .where(GmailApplicationLink.id.is_(None))
            .order_by(GmailConfirmation.id)
            .limit(bounded)).all()
        unresolved = db.scalars(
            select(GmailApplicationLink.gmail_confirmation_id)
            .where(GmailApplicationLink.decision == DECISION_NEEDS_REVIEW,
                   GmailApplicationLink.application_id.is_(None))
            .order_by(GmailApplicationLink.id)
            .limit(bounded)).all()

    def tally(result, revisited):
        summary['revisited' if revisited else 'considered'] += 1
        if result.decision in (DECISION_LINKED, DECISION_USER_CONFIRMED):
            summary['linked'] += 1
        elif result.decision == DECISION_NEEDS_REVIEW:
            summary['needs_review'] += 1
        else:
            summary['no_action'] += 1
        summary['by_reason'][result.reason_code] = summary['by_reason'].get(
            result.reason_code, 0) + 1

    for confirmation_id in pending:
        with Session.begin() as db:
            row = db.get(GmailConfirmation, confirmation_id)
            if row is None:
                continue
            result = reconcile_confirmation(db, row)
        tally(result, revisited=False)

    for confirmation_id in unresolved:
        with Session.begin() as db:
            row = db.get(GmailConfirmation, confirmation_id)
            link = db.scalar(select(GmailApplicationLink).where(
                GmailApplicationLink.gmail_confirmation_id == confirmation_id))
            if row is None or link is None or link.decision != DECISION_NEEDS_REVIEW:
                continue
            result = revisit_confirmation(db, row, link)
        tally(result, revisited=True)
    return summary


MAX_LISTED_REVIEW = 200


def _public_link(link, row=None):
    """One reconciliation decision as the API returns it.

    The evidence fields echoed here are #45's already-minimized, already
    sanitized ones; nothing new is exposed and no message content exists to
    expose.
    """
    public = {'id': link.id, 'gmail_confirmation_id': link.gmail_confirmation_id,
              'application_id': link.application_id, 'decision': link.decision,
              'reason_code': link.reason_code, 'confidence': link.confidence,
              'matched_fields': list(link.matched_fields or []),
              'candidate_count': link.candidate_count,
              'strong_candidate_count': link.strong_candidate_count,
              'transition_id': link.transition_id,
              'resolved_at': link.resolved_at}
    if row is not None:
        public['evidence'] = {'detected_company': row.detected_company,
                              'detected_role': row.detected_role,
                              'detected_state': row.detected_state,
                              'received_at': row.received_at,
                              'parser_id': row.parser_id,
                              'application_url': row.application_url,
                              'subject': row.subject,
                              'sender': row.sender}
    return public


def needs_review(*, limit=50):
    """The Needs Review queue: bounded, most recent first."""
    if not schema_ready():
        return {'schema': 'NOT_INITIALIZED', 'items': [], 'count': 0}
    bounded = max(1, min(int(limit), MAX_LISTED_REVIEW))
    with Session() as db:
        pairs = db.execute(
            select(GmailApplicationLink, GmailConfirmation)
            .join(GmailConfirmation,
                  GmailConfirmation.id == GmailApplicationLink.gmail_confirmation_id)
            .where(GmailApplicationLink.decision == DECISION_NEEDS_REVIEW)
            .order_by(GmailApplicationLink.id.desc())
            .limit(bounded)).all()
        items = [_public_link(link, row) for link, row in pairs]
    return {'schema': SCHEMA_VERSION, 'items': items, 'count': len(items)}


def link_for(confirmation_id):
    """The durable decision for one confirmation, or `None`."""
    if not schema_ready():
        return None
    with Session() as db:
        link = db.scalar(select(GmailApplicationLink).where(
            GmailApplicationLink.gmail_confirmation_id == confirmation_id))
        return _public_link(link) if link else None


def confirm_review(link_id, *, application_id=None):
    """The user confirms a Needs Review item.

    This is a **user-confirmed** transition, not an automated one: its source
    category is `USER_CONFIRMED_GMAIL_EVIDENCE`, it carries the user's
    authority, and its history row still references the original Gmail
    evidence -- account, message, parser and tokens -- so the provenance
    chain back to the message that prompted it stays intact.

    `application_id` may name the application the user chose when the item
    was ambiguous, or the application that did not exist when the evidence
    was first reconciled. It must be a candidate that actually corroborates
    -- the employer plus at least two further independent fields -- so the
    user resolves an ambiguity or a contradiction rather than bypassing
    matching altogether. When the item names no target and exactly one
    corroborating candidate exists, that one is used.

    A candidate whose requisition URL contradicts the evidence is offered
    here even though it is never linked automatically: deciding whether two
    postings are one application is precisely the judgement only the user
    can make.
    """
    initialize_reconciliation_schema()
    with Session.begin() as db:
        link = db.get(GmailApplicationLink, link_id)
        if link is None:
            return {'ok': False, 'reason_code': REASON_LINK_NOT_REVIEWABLE}
        if link.decision != DECISION_NEEDS_REVIEW:
            return {'ok': False, 'reason_code': REASON_LINK_NOT_REVIEWABLE,
                    'link': _public_link(link)}
        row = db.get(GmailConfirmation, link.gmail_confirmation_id)
        if row is None:
            return {'ok': False, 'reason_code': REASON_EVIDENCE_INVALID}
        target = DETECTED_STATE_TO_CANONICAL.get(row.detected_state)
        if target is None:
            return {'ok': False, 'reason_code': REASON_STATE_UNSUPPORTED}

        candidates = {candidate.application_id: candidate
                      for candidate in find_candidates(db, row)
                      if candidate.confirmable}
        chosen = application_id or link.application_id
        if chosen is None and len(candidates) == 1:
            chosen = next(iter(candidates))
        match = candidates.get(chosen)
        if match is None:
            return {'ok': False, 'reason_code': REASON_NO_STRONG_MATCH,
                    'link': _public_link(link)}

        application = db.get(Application, match.application_id)
        decision = states.assert_state(
            db, application, target,
            source_category=states.SOURCE_USER_CONFIRMED_GMAIL,
            asserted_by='USER', confidence='',
            reason_code=states.REASON_GMAIL_USER_CONFIRMED,
            gmail_account_id=row.gmail_account_id,
            gmail_message_id=row.gmail_message_id,
            gmail_confirmation_id=row.id, parser_id=row.parser_id,
            evidence_tokens=list(row.evidence_signals or []),
            field_agreement=sorted(match.fields),
            occurred_at=row.received_at)
        # The review item is resolved either way: a refusal here means the
        # application already holds an equal or stronger state, which is a
        # legitimate resolution, not a failure to record one.
        link.decision = DECISION_USER_CONFIRMED
        link.reason_code = (REASON_USER_CONFIRMED if decision.applied
                            else REASON_TRANSITION_REFUSED)
        link.application_id = match.application_id
        link.matched_fields = sorted(match.fields)
        link.transition_id = decision.transition_id
        link.resolved_at = now()
        return {'ok': True, 'applied': decision.applied,
                'state': decision.as_dict(), 'link': _public_link(link)}


def reject_review(link_id):
    """The user rejects a Needs Review item. No state change, ever."""
    initialize_reconciliation_schema()
    with Session.begin() as db:
        link = db.get(GmailApplicationLink, link_id)
        if link is None:
            return {'ok': False, 'reason_code': REASON_LINK_NOT_REVIEWABLE}
        if link.decision != DECISION_NEEDS_REVIEW:
            return {'ok': False, 'reason_code': REASON_LINK_NOT_REVIEWABLE,
                    'link': _public_link(link)}
        link.decision = DECISION_USER_REJECTED
        link.reason_code = REASON_USER_REJECTED
        link.application_id = None
        link.transition_id = 0
        link.resolved_at = now()
        return {'ok': True, 'applied': False, 'link': _public_link(link)}


def reconciliation_status():
    """Fixed parameters and decision counts. No evidence content."""
    if not schema_ready():
        return {'schema': 'NOT_INITIALIZED', 'decisions': {}}
    from sqlalchemy import func
    with Session() as db:
        rows = db.execute(select(GmailApplicationLink.decision, func.count())
                          .group_by(GmailApplicationLink.decision)).all()
    counts = {decision: 0 for decision in DECISIONS}
    for decision, count in rows:
        if decision in counts:
            counts[decision] = count
    return {'schema': SCHEMA_VERSION, 'decisions': counts,
            'creates_applications': False, 'uses_ai': False,
            'limits': {'date_proximity_days': DATE_PROXIMITY.days,
                       'required_corroborations': REQUIRED_CORROBORATIONS,
                       'max_candidates': MAX_CANDIDATES,
                       'max_run_evidence': MAX_RUN_EVIDENCE},
            'agreement_fields': list(AGREEMENT_FIELDS),
            'automated_target_states': sorted(states.AUTOMATED_TARGET_STATES)}
