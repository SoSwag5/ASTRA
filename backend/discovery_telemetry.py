"""Issue #43: truthful, local-first discovery funnel telemetry.

One authoritative, versioned contract (`discovery-telemetry-v1`) describing
WHERE candidates were lost in a discovery run, per source and per run, so
"N/N sources healthy" is no longer the only headline discovery signal.

Design rules this module exists to enforce:

- It INSTRUMENTS the existing pipeline. It never re-decides anything. Identity
  and deduplication stay #40's (`backend.deduplication`), eligibility/geography/
  relevance stay #41's (`backend.assessment` via `backend.recall.evaluate`), and
  provider health/completion stay #38/#39's (`backend.job_providers.contracts`).
- Monotonicity is a PROPERTY OF STAGE MEMBERSHIP, never of clamping. Stages are
  accumulated as sets of stable identifiers and only serialized as aggregate
  counts at finalization; `validate()` then fails loudly rather than allowing an
  impossible funnel to be published.
- A provider failure is never rendered as "zero relevant jobs". Fetch outcome,
  provider health, completion, completion reason and a bounded error class live
  OUTSIDE the funnel so a failed, skipped, empty and fully-filtered source stay
  distinguishable.
- Telemetry is aggregate operational data. No job description, title, URL,
  provider payload, candidate/profile content, credential, exception trace or
  filesystem path may ever enter it -- `validate()` enforces that too.
- `DISPLAYED`/`SAVED`/`APPLIED` are asynchronous ENGAGEMENT OUTCOMES, reported
  separately from the funnel and never inferred from ranking or existence.
"""
import re
from collections import Counter
from datetime import datetime, timedelta, timezone

TELEMETRY_SCHEMA_VERSION = 'discovery-telemetry-v1'

# Key under which the versioned payload lives inside AutomationRun.report.
REPORT_KEY = 'discovery_telemetry'

# Owner-approved v1.1 retention. Not negotiable here: longer-lived aggregate
# trend retention may only be reconsidered in issue #47, if the dashboard
# demonstrates a genuine requirement.
RETENTION_DAYS = 90

# --------------------------------------------------------------------------
# The monotonic discovery funnel
# --------------------------------------------------------------------------

FETCHED = 'FETCHED'
STRUCTURALLY_VALID = 'STRUCTURALLY_VALID'
CANONICAL_UNIQUE = 'CANONICAL_UNIQUE'
LOCATION_COMPATIBLE = 'LOCATION_COMPATIBLE'
ELIGIBILITY_NOT_INCOMPATIBLE = 'ELIGIBILITY_NOT_INCOMPATIBLE'
RELEVANT = 'RELEVANT'
NEW = 'NEW'

FUNNEL_STAGES = (FETCHED, STRUCTURALLY_VALID, CANONICAL_UNIQUE, LOCATION_COMPATIBLE,
                 ELIGIBILITY_NOT_INCOMPATIBLE, RELEVANT, NEW)

# Where observation-count semantics become canonical-job semantics. FETCHED and
# STRUCTURALLY_VALID count provider OBSERVATIONS (two observations of the same
# posting count twice); every later stage counts distinct canonical `Job`
# identities as resolved by #40, so the same posting counts once.
OBSERVATION_STAGES = (FETCHED, STRUCTURALLY_VALID)
CANONICAL_STAGES = (CANONICAL_UNIQUE, LOCATION_COMPATIBLE, ELIGIBILITY_NOT_INCOMPATIBLE,
                    RELEVANT, NEW)
FUNNEL_BASIS = {**{stage: 'PROVIDER_OBSERVATIONS' for stage in OBSERVATION_STAGES},
                **{stage: 'CANONICAL_JOBS' for stage in CANONICAL_STAGES}}

# --------------------------------------------------------------------------
# Source attempt state / outcome vocabularies (bounded, closed sets)
# --------------------------------------------------------------------------

ATTEMPTED = 'ATTEMPTED'
SKIPPED_NOT_DUE = 'SKIPPED_NOT_DUE'
SKIPPED_NOT_TARGETED = 'SKIPPED_NOT_TARGETED'
SKIPPED_DISABLED = 'SKIPPED_DISABLED'
# The Owner stopped the scan before this source was fetched (manual-only
# scanning: cancellation is honoured between sources, never mid-fetch).
SKIPPED_CANCELLED = 'SKIPPED_CANCELLED'
# A source the Owner confirmed was disabled, edited or deleted after the
# confirmation, so it was deliberately not fetched.
SKIPPED_SCOPE_CHANGED = 'SKIPPED_SCOPE_CHANGED'
ATTEMPT_STATES = (ATTEMPTED, SKIPPED_NOT_DUE, SKIPPED_NOT_TARGETED, SKIPPED_DISABLED,
                  SKIPPED_CANCELLED, SKIPPED_SCOPE_CHANGED)

# What happened at the PROVIDER/COMPATIBILITY BOUNDARY specifically.
FETCH_SUCCEEDED = 'SUCCEEDED'
FETCH_PARTIAL = 'PARTIAL'
FETCH_FAILED = 'FAILED'
FETCH_NOT_ATTEMPTED = 'NOT_ATTEMPTED'
FETCH_OUTCOMES = (FETCH_SUCCEEDED, FETCH_PARTIAL, FETCH_FAILED, FETCH_NOT_ATTEMPTED)

# What happened to the WHOLE source attempt, fetch plus ingestion/assessment.
ATTEMPT_OK = 'OK'
ATTEMPT_PARTIAL = 'PARTIAL'
ATTEMPT_FAILED = 'FAILED'
ATTEMPT_INGESTION_FAILED = 'INGESTION_FAILED'
ATTEMPT_SKIPPED = 'SKIPPED'
ATTEMPT_OUTCOMES = (ATTEMPT_OK, ATTEMPT_PARTIAL, ATTEMPT_FAILED, ATTEMPT_INGESTION_FAILED,
                    ATTEMPT_SKIPPED)

# Bounded normalization of an external failure into a local classification.
# The provider's own error MESSAGE is never carried here -- only a code from
# the closed transport/provider taxonomy, or UNCLASSIFIED.
ERROR_CLASS_FOR_HEALTH = {
    'POLICY_BLOCKED': 'POLICY_BLOCKED',
    'RATE_LIMITED': 'RATE_LIMITED',
    'AUTH_REQUIRED': 'AUTH_REQUIRED',
    'MALFORMED': 'MALFORMED_RESPONSE',
    'UNAVAILABLE': 'SOURCE_UNAVAILABLE',
    'PARTIAL': 'PARTIAL_RESULT',
}
ERROR_CLASS_UNCLASSIFIED = 'UNCLASSIFIED'
ERROR_CLASS_INGESTION = 'INGESTION_ROLLED_BACK'
ERROR_CLASSES = frozenset(set(ERROR_CLASS_FOR_HEALTH.values()) |
                          {ERROR_CLASS_UNCLASSIFIED, ERROR_CLASS_INGESTION})

# Error codes this build can legitimately emit. Anything else (including a code
# invented by an external response) is normalized to UNCLASSIFIED rather than
# copied through -- provider content is untrusted, unbounded input.
_TRANSPORT_ERROR_CODES = frozenset({
    'POLICY_BLOCKED', 'DESTINATION_BLOCKED', 'DNS_FAILURE', 'DNS_QUEUE_SATURATED',
    'CONNECT_FAILED', 'CONNECT_TIMEOUT', 'READ_TIMEOUT', 'READ_FAILED', 'WRITE_FAILED',
    'WRITE_TIMEOUT', 'INVALID_EXTERNAL_URL', 'REMOTE_PROTOCOL_ERROR', 'DEADLINE_EXCEEDED',
    'RATE_LIMITED', 'UPSTREAM_UNAVAILABLE', 'UPSTREAM_ERROR', 'TOO_MANY_REDIRECTS',
    'INVALID_REDIRECT', 'INVALID_JSON', 'UNEXPECTED_CONTENT_TYPE',
    'UNSUPPORTED_CONTENT_ENCODING', 'DECODE_FAILED', 'RESPONSE_TOO_LARGE',
})
_PROVIDER_ERROR_CODES = frozenset({'ALL_RECORDS_REJECTED', 'SOURCE_REQUEST_FAILED'})
ERROR_CODES = _TRANSPORT_ERROR_CODES | _PROVIDER_ERROR_CODES

COMPLETION_VALUES = frozenset({'COMPLETE', 'PARTIAL', 'FAILED', 'CANCELLED'})
COMPLETION_REASONS = frozenset({
    'DETAIL_BUDGET_EXHAUSTED', 'DETAIL_FETCH_INCOMPLETE', 'ALL_RECORDS_REJECTED',
    'SOME_RECORDS_REJECTED', 'TRANSPORT_ERROR', 'PAGINATION_LIMIT_REACHED',
})
HEALTH_VALUES = frozenset({'HEALTHY', 'EMPTY', 'PARTIAL', 'RATE_LIMITED', 'AUTH_REQUIRED',
                           'POLICY_BLOCKED', 'MALFORMED', 'UNAVAILABLE'})

# Numeric/boolean provider diagnostics preserved SEPARATELY from the funnel.
# `records_received` counts rows the provider enumerated before its own
# native-shape validation; it is deliberately NOT the funnel's FETCHED, which
# counts observations actually delivered to discovery orchestration.
PROVIDER_METRIC_FIELDS = (
    'elapsed_seconds', 'requests_attempted', 'requests_succeeded',
    'detail_requests_attempted', 'detail_requests_succeeded', 'retries',
    'encoded_bytes_read', 'decoded_bytes_read', 'records_received',
    'records_accepted', 'records_rejected', 'content_cap_reached', 'errors_count',
)

# --------------------------------------------------------------------------
# Stage-exit classification -- uses ONLY the existing #41 hard-reason contract
# --------------------------------------------------------------------------

# Issue #41's authoritative taxonomy plus the retired legacy codes that
# `backend.recall.evaluate_legacy` still emits under assessment_mode LEGACY, so
# the funnel stays meaningful in every assessment mode.
LOCATION_HARD_CODES = frozenset({'GEO_INCOMPATIBLE', 'NON_UAE', 'REMOTE_NOT_UAE_COMPATIBLE'})
ELIGIBILITY_HARD_CODES = frozenset({'CONFIRMED_ELIGIBILITY_CONFLICT',
                                    'EXPLICIT_NATIONALITY_RESTRICTION'})
KNOWN_HARD_CODES = frozenset({
    'DOMAIN_INCOMPATIBLE', 'GEO_INCOMPATIBLE', 'EXTREME_LEADERSHIP_MISMATCH',
    'INVALID_JOB', 'CONFIRMED_ELIGIBILITY_CONFLICT', 'USER_BLOCKED',
    'NON_UAE', 'REMOTE_NOT_UAE_COMPATIBLE', 'ROLE_NOT_RELEVANT', 'TOO_SENIOR',
    'EXCLUDED_ROLE', 'BLOCKED_COMPANY', 'BLOCKED_DOMAIN',
    'EXPLICIT_NATIONALITY_RESTRICTION', 'EXPERIENCE_GAP', 'EXPIRED',
})
UNSPECIFIED_REASON = 'UNSPECIFIED'

# Structural rejection code used by backend/main.py's discover loop when an
# observation cannot safely satisfy #40's ingestion/persistence contract.
INVALID_OBSERVATION = 'INVALID_JOB'


def classify(decision):
    """Project ONE authoritative #41 decision onto funnel stage membership.

    Never re-derives geography, eligibility or relevance: it reads the exact
    fields `backend.recall.evaluate` already publishes.

    - `location_compatible` is #41's own field (`geography.compatibility !=
      INCOMPATIBLE` in mode NEW). UNKNOWN evidence therefore stays compatible
      and is never silently converted into incompatible.
    - `eligibility_not_incompatible` is true unless the authoritative
      eligibility state is CONFIRMED ineligible. UNKNOWN remains
      not-confirmed-incompatible, exactly as #41 defines it. Missing evidence
      never implies anything about work authorization, sponsorship,
      nationality or residence.
    - `relevant` means the decision was not hard-rejected at all by #41's
      hard-reason taxonomy. Experience gaps, seniority uncertainty and
      imperfect fit are ranking penalties in #41, not rejections, so such a
      job stays RELEVANT and is merely ranked lower.
    """
    decision = decision or {}
    hard = decision.get('hard') or []
    codes = [h.get('code', '') for h in hard if isinstance(h, dict)]
    code_set = set(codes)
    primary = codes[0] if codes else None

    location_compatible = (bool(decision.get('location_compatible', True))
                           and not (code_set & LOCATION_HARD_CODES))
    eligibility_state = (decision.get('eligibility') or {}).get('state', 'UNKNOWN')
    eligibility_ok = (eligibility_state != 'INELIGIBLE'
                      and not (code_set & ELIGIBILITY_HARD_CODES))
    relevant = not bool(decision.get('excluded'))

    if not location_compatible:
        exit_stage, exit_reason = LOCATION_COMPATIBLE, _bounded_reason(
            next((c for c in codes if c in LOCATION_HARD_CODES), primary))
    elif not eligibility_ok:
        exit_stage, exit_reason = ELIGIBILITY_NOT_INCOMPATIBLE, _bounded_reason(
            next((c for c in codes if c in ELIGIBILITY_HARD_CODES), primary))
    elif not relevant:
        exit_stage, exit_reason = RELEVANT, _bounded_reason(primary)
    else:
        exit_stage, exit_reason = None, None

    return {'location_compatible': location_compatible,
            'eligibility_not_incompatible': location_compatible and eligibility_ok,
            'relevant': location_compatible and eligibility_ok and relevant,
            'exit_stage': exit_stage, 'exit_reason': exit_reason}


def _bounded_reason(code):
    return code if code in KNOWN_HARD_CODES else UNSPECIFIED_REASON


# --------------------------------------------------------------------------
# Version metadata
# --------------------------------------------------------------------------

# Evaluation reference metadata. Deliberately declared here as stable literals
# rather than imported from `backend.evaluation`: production discovery must not
# import, rerun or depend on the offline #42 harness, nor on any mutable
# documentation file. `tests/test_discovery_telemetry.py` cross-checks these
# values against #42's own committed constants and report so they cannot drift
# silently.
#
# This is EVIDENCE metadata, never runtime authority: the production ranking
# contract is `assessment_schema_version`/`assessment_ruleset_version` below.
EVALUATION_REFERENCE = {
    'authority': 'OFFLINE_EVALUATION_EVIDENCE_ONLY',
    'harness_issue': '43-references-42',
    'report_schema_version': 'fit-eval-report-3',
    'corpus_schema_version': 'fit-eval-corpus-1',
    'human_label_version': 'labels-v2',
    'quality_gate_schema_version': 'fit-quality-gate-1',
    'quality_gate_status': 'INSUFFICIENT_DATA',
    'quality_gate_approval_state': 'PROPOSED / NOT OWNER-APPROVED',
    'note': 'Offline evaluation evidence for interpreting #41 behaviour. The quality '
            'gate has NOT passed and is not a runtime authority for any decision here.',
}


def versions(cfg=None):
    """Identify the production decision contract that produced a run.

    Reads central version constants already owned by the production modules
    themselves; nothing here is a copy of a documentation file.
    """
    from . import assessment, career_tracks, deduplication, normalization, recall
    from . import experience as experience_module
    from .job_providers import contracts
    return {
        'telemetry_schema_version': TELEMETRY_SCHEMA_VERSION,
        'assessment_schema_version': assessment.SCHEMA_VERSION,
        'assessment_ruleset_version': assessment.RULESET_VERSION,
        'assessment_mode': (cfg or {}).get('assessment_mode', 'NEW'),
        'recall_version': recall.VERSION,
        'taxonomy_version': career_tracks.VERSION,
        'experience_parser_version': experience_module.VERSION,
        'normalization_version': normalization.NORMALIZATION_VERSION,
        'dedupe_version': deduplication.DEDUPE_VERSION,
        'provider_contract_version': contracts.VERSION,
        'evaluation_reference': dict(EVALUATION_REFERENCE),
    }


# --------------------------------------------------------------------------
# Engagement outcomes (never funnel stages)
# --------------------------------------------------------------------------

DISPLAYED = 'DISPLAYED'
SAVED = 'SAVED'
APPLIED = 'APPLIED'
ENGAGEMENT_OUTCOMES = (DISPLAYED, SAVED, APPLIED)

ENGAGEMENT_AVAILABLE = 'AVAILABLE'
ENGAGEMENT_UNAVAILABLE = 'UNAVAILABLE'

# One explicit meaning, never mixed: every available engagement count below is
# "canonical jobs THIS RUN observed whose authoritative persisted state carried
# the outcome at the moment the run was finalized". It is not a during-run event
# count and not a current-state-at-query-time count.
ENGAGEMENT_BASIS = 'RUN_OBSERVED_CANONICAL_JOBS_AT_RUN_FINALIZATION'

ENGAGEMENT_NOTE = (
    'Engagement outcomes are asynchronous and are NOT discovery funnel filters. '
    'They are never inferred from RELEVANT, ranking, API retrieval, database '
    'existence, or application preparation/readiness.'
)

DISPLAYED_UNAVAILABLE_REASON = (
    'ASTRA records no discovery display/impression event. Job.analysis["seen_at"] is a '
    'user-triggered acknowledgement of a single job, not a display event and not '
    'run-scoped, so it is not counted here. DISPLAYED stays explicitly unavailable in '
    'v1.1 rather than being inferred.'
)


def _engagement(job_ids, saved_ids, applied_ids, measured_at):
    job_ids = set(job_ids)
    return {
        'basis': ENGAGEMENT_BASIS,
        'measured_at': measured_at,
        'observed_canonical_jobs': len(job_ids),
        DISPLAYED: {'state': ENGAGEMENT_UNAVAILABLE, 'count': None, 'authority': None,
                    'reason': DISPLAYED_UNAVAILABLE_REASON},
        SAVED: {'state': ENGAGEMENT_AVAILABLE, 'count': len(job_ids & saved_ids),
                'authority': 'Job.analysis.saved', 'reason': None},
        APPLIED: {'state': ENGAGEMENT_AVAILABLE, 'count': len(job_ids & applied_ids),
                  'authority': 'Application.applied_date', 'reason': None},
        'note': ENGAGEMENT_NOTE,
    }


def _engagement_state(db):
    """Authoritative persisted saved/applied state. Read-only: this never
    writes to, or adds a telemetry field to, Application lifecycle authority.
    """
    from sqlalchemy import select
    from .models import Application, Job
    saved = set()
    for job_id, analysis in db.execute(select(Job.id, Job.analysis)):
        if isinstance(analysis, dict) and analysis.get('saved') is True:
            saved.add(job_id)
    applied = {job_id for job_id, applied_date
               in db.execute(select(Application.job_id, Application.applied_date))
               if applied_date}
    return saved, applied


# --------------------------------------------------------------------------
# Accumulators
# --------------------------------------------------------------------------

class TelemetryError(ValueError):
    """An impossible or unpublishable telemetry payload. Raised by validate();
    never allowed to corrupt Job/JobObservation persistence.
    """


class SourceAttempt:
    """Accumulates ONE source attempt as explicit stage membership.

    Counts are derived from sets of stable identifiers -- observation ordinals
    within this attempt, and canonical Job ids -- and only serialized as
    aggregates. Monotonicity is therefore structural, not clamped.
    """

    def __init__(self, source_id, source_name, provider_family, attempt_state=ATTEMPTED):
        self.source_id = source_id
        self.source_name = _bounded_name(source_name)
        self.provider_family = _bounded_family(provider_family)
        self.attempt_state = attempt_state
        self.fetched = 0
        self.invalid = Counter()
        self.structurally_valid_observations = 0
        # canonical Job id -> {'location':bool,'eligibility':bool,'relevant':bool,
        #                      'exit_stage':str|None,'exit_reason':str|None,'created':bool}
        self.jobs = {}
        self.duplicate_observations = 0
        self.completion = None
        self.completion_reason = None
        self.health = None
        self.error_code = None
        self.error_class = None
        self.metrics = None
        self.fetch_outcome = FETCH_NOT_ATTEMPTED if attempt_state != ATTEMPTED else None
        self.rolled_back = False
        self.incomplete_reason = None

    # -- recording -------------------------------------------------------
    def observed(self):
        """One provider observation was delivered to discovery orchestration."""
        self.fetched += 1

    def invalid_observation(self, code=INVALID_OBSERVATION):
        """The observation could not satisfy #40's ingestion contract, so it
        never enters STRUCTURALLY_VALID.
        """
        self.invalid[code if code in KNOWN_HARD_CODES or code == INVALID_OBSERVATION
                     else UNSPECIFIED_REASON] += 1

    def persisted(self, job_id, created):
        """The observation satisfied #40's persistence contract and resolved to
        canonical Job `job_id`. `created` is #40's own answer to "was a new
        canonical row created for this observation", never a timestamp guess.
        """
        self.structurally_valid_observations += 1
        entry = self.jobs.get(job_id)
        if entry is None:
            self.jobs[job_id] = entry = {'location': False, 'eligibility': False,
                                         'relevant': False, 'exit_stage': None,
                                         'exit_reason': None, 'created': False,
                                         'assessed': False}
        else:
            self.duplicate_observations += 1
        entry['created'] = entry['created'] or bool(created)

    def assessed(self, job_id, decision):
        entry = self.jobs.get(job_id)
        if entry is None:
            # A decision for a job that never entered CANONICAL_UNIQUE in this
            # attempt is not counted: a stage can only ever narrow the previous.
            return
        result = classify(decision)
        entry.update(location=result['location_compatible'],
                     eligibility=result['eligibility_not_incompatible'],
                     relevant=result['relevant'], exit_stage=result['exit_stage'],
                     exit_reason=result['exit_reason'], assessed=True)

    def record_fetch(self, outcome):
        """`outcome` is the same bounded dict backend/main.py already builds for
        the per-source report (completion/health/completion_reason/metrics/error).
        """
        outcome = outcome or {}
        self.completion = _enum(outcome.get('completion'), COMPLETION_VALUES)
        self.completion_reason = _enum(outcome.get('completion_reason'), COMPLETION_REASONS)
        self.health = _enum(outcome.get('health'), HEALTH_VALUES)
        error = outcome.get('error') or {}
        self.error_code = _enum(error.get('code'), ERROR_CODES,
                                default=ERROR_CLASS_UNCLASSIFIED if error else None)
        self.metrics = _metrics(outcome.get('metrics'))
        if self.completion == 'PARTIAL':
            self.fetch_outcome = FETCH_PARTIAL
            self.incomplete_reason = self.completion_reason or 'PARTIAL_COMPLETION'
        elif self.completion in ('FAILED', 'CANCELLED'):
            self.fetch_outcome = FETCH_FAILED
            self.incomplete_reason = self.completion_reason or 'FETCH_FAILED'
        else:
            self.fetch_outcome = FETCH_SUCCEEDED
        if self.health in ERROR_CLASS_FOR_HEALTH and self.health != 'PARTIAL':
            self.error_class = ERROR_CLASS_FOR_HEALTH[self.health]
        elif self.health == 'PARTIAL':
            self.error_class = ERROR_CLASS_FOR_HEALTH['PARTIAL']

    def failed(self, outcome):
        """The source attempt raised. Everything this attempt persisted was
        rolled back by the caller, so no canonical stage may keep a member --
        but observations already delivered stay truthfully reported, flagged
        incomplete, rather than being rewritten to zero.

        `completion`/`health` mirror what the existing per-source report
        records for the attempt as a whole (FAILED for any raised source),
        while `fetch_outcome` keeps describing the PROVIDER BOUNDARY itself.
        That is what separates "the fetch never returned trustworthy results"
        (fetch_outcome FAILED) from "valid results were returned and ingestion
        then failed" (fetch_outcome SUCCEEDED/PARTIAL with rolled_back true).
        """
        previous_fetch = self.fetch_outcome
        fetch_had_succeeded = previous_fetch in (FETCH_SUCCEEDED, FETCH_PARTIAL)
        had_canonical = bool(self.jobs)
        self.record_fetch(outcome)
        if fetch_had_succeeded:
            self.fetch_outcome = previous_fetch
            self.rolled_back = True
            self.incomplete_reason = 'SOURCE_TRANSACTION_ROLLED_BACK'
            self.error_class = ERROR_CLASS_INGESTION
        elif had_canonical:
            self.rolled_back = True
        self.jobs = {}
        self.duplicate_observations = 0
        self.structurally_valid_observations = min(self.structurally_valid_observations,
                                                   self.fetched)

    def skipped(self, state):
        """This source was never attempted, so it has no counts at all --
        `counts_complete` stays false and `incomplete_reason` names the skip
        so an all-zero row is never mistaken for a scanned, empty source.
        """
        self.attempt_state = state
        self.fetch_outcome = FETCH_NOT_ATTEMPTED
        self.incomplete_reason = state

    # -- derived ---------------------------------------------------------
    @property
    def attempted(self):
        return self.attempt_state == ATTEMPTED

    def stage_jobs(self, stage):
        """Canonical Job ids in `stage`, built with strict nesting."""
        if not self.attempted:
            return set()
        if stage == CANONICAL_UNIQUE:
            return set(self.jobs)
        if stage == LOCATION_COMPATIBLE:
            return {j for j, e in self.jobs.items() if e['location']}
        if stage == ELIGIBILITY_NOT_INCOMPATIBLE:
            return {j for j, e in self.jobs.items() if e['eligibility']}
        if stage == RELEVANT:
            return {j for j, e in self.jobs.items() if e['relevant']}
        if stage == NEW:
            return {j for j, e in self.jobs.items() if e['relevant'] and e['created']}
        raise TelemetryError(f'Unknown canonical stage {stage!r}')

    def funnel(self):
        if not self.attempted:
            return {stage: 0 for stage in FUNNEL_STAGES}
        counts = {FETCHED: self.fetched,
                  STRUCTURALLY_VALID: self.structurally_valid_observations}
        for stage in CANONICAL_STAGES:
            counts[stage] = len(self.stage_jobs(stage))
        return counts

    def attempt_outcome(self):
        if not self.attempted:
            return ATTEMPT_SKIPPED
        if self.rolled_back and self.fetch_outcome in (FETCH_SUCCEEDED, FETCH_PARTIAL):
            return ATTEMPT_INGESTION_FAILED
        if self.fetch_outcome == FETCH_FAILED:
            return ATTEMPT_FAILED
        if self.fetch_outcome == FETCH_PARTIAL:
            return ATTEMPT_PARTIAL
        return ATTEMPT_OK

    def counts_complete(self):
        return self.attempted and not self.rolled_back and self.fetch_outcome == FETCH_SUCCEEDED

    def exits(self):
        reasons = {stage: Counter() for stage in (LOCATION_COMPATIBLE,
                                                  ELIGIBILITY_NOT_INCOMPATIBLE, RELEVANT)}
        for entry in self.jobs.values():
            if entry['exit_stage']:
                reasons[entry['exit_stage']][entry['exit_reason'] or UNSPECIFIED_REASON] += 1
        return {stage: dict(counter) for stage, counter in reasons.items()}

    def to_dict(self, saved_ids, applied_ids, measured_at):
        funnel = self.funnel()
        exits = self.exits()
        return {
            'source_id': self.source_id,
            'source_name': self.source_name,
            'provider_family': self.provider_family,
            'attempted': self.attempted,
            'attempt_state': self.attempt_state,
            'attempt_outcome': self.attempt_outcome(),
            'fetch_outcome': self.fetch_outcome or FETCH_NOT_ATTEMPTED,
            'health': self.health,
            'completion': self.completion,
            'completion_reason': self.completion_reason,
            'error_code': self.error_code,
            'error_class': self.error_class,
            'counts_complete': self.counts_complete(),
            'incomplete_reason': self.incomplete_reason,
            'rolled_back': self.rolled_back,
            'funnel': funnel,
            'funnel_basis': dict(FUNNEL_BASIS),
            'stage_exits': exits,
            'diagnostics': {
                'invalid_observations': sum(self.invalid.values()),
                'invalid_observation_reasons': dict(self.invalid),
                'duplicate_observations_same_source': self.duplicate_observations,
                # Includes canonical rows created for jobs later hard-rejected;
                # the NEW funnel stage deliberately counts only relevant ones.
                'canonical_jobs_created_all_dispositions':
                    sum(1 for e in self.jobs.values() if e['created']),
                'unassessed_canonical_jobs':
                    sum(1 for e in self.jobs.values() if not e['assessed']),
            },
            'provider_metrics': self.metrics,
            'engagement': _engagement(self.stage_jobs(CANONICAL_UNIQUE), saved_ids,
                                      applied_ids, measured_at),
        }


class RunTelemetry:
    """Accumulates one discovery run and serializes the versioned payload."""

    MAX_SOURCES = 200

    def __init__(self, run_id, trigger, started_at, source_filter=None, cfg=None):
        self.run_id = run_id
        self.trigger = trigger
        self.started_at = started_at
        self.source_filter = source_filter
        self.versions = versions(cfg)
        self.sources = []
        self.truncated = 0

    def _add(self, attempt):
        if len(self.sources) >= self.MAX_SOURCES:
            self.truncated += 1
            return attempt
        self.sources.append(attempt)
        return attempt

    def attempt(self, source):
        return self._add(SourceAttempt(source.id, source.name, source.adapter))

    def skip(self, source, state):
        attempt = SourceAttempt(source.id, source.name, source.adapter, attempt_state=state)
        attempt.skipped(state)
        return self._add(attempt)

    # -- aggregation -----------------------------------------------------
    def run_funnel(self):
        """Run aggregation semantics.

        FETCHED and STRUCTURALLY_VALID are SUMS of per-source observation
        counts: two sources each delivering the same posting genuinely made two
        observations. Every canonical stage is the size of the UNION of the
        per-source canonical id sets, so a job observed by more than one
        provider is counted exactly once for the run. Per-source canonical
        counts are therefore never summed.
        """
        attempted = [s for s in self.sources if s.attempted]
        counts = {FETCHED: sum(s.fetched for s in attempted),
                  STRUCTURALLY_VALID: sum(s.structurally_valid_observations for s in attempted)}
        for stage in CANONICAL_STAGES:
            union = set()
            for source in attempted:
                union |= source.stage_jobs(stage)
            counts[stage] = len(union)
        return counts

    def observed_jobs(self):
        union = set()
        for source in self.sources:
            union |= source.stage_jobs(CANONICAL_UNIQUE)
        return union

    def finalize(self, db, run_status, finished_at=None, duration_seconds=None):
        """Build, validate and return the versioned payload.

        A telemetry defect must never corrupt persistence or fabricate counts:
        any failure here is reported as a bounded telemetry-error payload
        instead of an impossible funnel.
        """
        try:
            return self._finalize(db, run_status, finished_at, duration_seconds)
        except Exception as error:               # noqa: BLE001 -- bounded by design
            return self.error_payload(type(error).__name__)

    def error_payload(self, detail='TELEMETRY_FINALIZATION_FAILED'):
        return {
            'schema_version': TELEMETRY_SCHEMA_VERSION,
            'run_id': self.run_id,
            'status': 'TELEMETRY_ERROR',
            'telemetry_error_code': 'TELEMETRY_FINALIZATION_FAILED',
            'telemetry_error_detail': _bounded_family(detail) or 'UNSPECIFIED',
            'trigger': self.trigger,
            'started_at': self.started_at,
            'versions': self.versions,
            'funnel': None,
            'sources': [],
            'note': 'Discovery telemetry could not be finalized truthfully for this run. '
                    'No counts are reported rather than fabricated ones. Discovery '
                    'ingestion itself is unaffected.',
        }

    def _finalize(self, db, run_status, finished_at, duration_seconds):
        measured_at = _utc_now().isoformat()
        try:
            saved_ids, applied_ids = _engagement_state(db)
        except Exception:                        # noqa: BLE001
            saved_ids, applied_ids = set(), set()
        sources = [s.to_dict(saved_ids, applied_ids, measured_at) for s in self.sources]
        funnel = self.run_funnel()
        attempted = [s for s in self.sources if s.attempted]
        incomplete = [s for s in attempted if not s.counts_complete()]
        payload = {
            'schema_version': TELEMETRY_SCHEMA_VERSION,
            'run_id': self.run_id,
            'run_status': run_status,
            'status': 'OK' if not incomplete else 'INCOMPLETE',
            'telemetry_error_code': None,
            'trigger': self.trigger,
            'started_at': self.started_at,
            'finished_at': finished_at,
            'duration_seconds': duration_seconds,
            'source_filter': self.source_filter,
            'versions': self.versions,
            'funnel': funnel,
            'funnel_basis': dict(FUNNEL_BASIS),
            'funnel_aggregation': {
                'observation_stages': list(OBSERVATION_STAGES),
                'canonical_stages': list(CANONICAL_STAGES),
                'rule': 'Observation stages are summed across sources; canonical stages '
                        'are the size of the union of per-source canonical Job id sets, '
                        'so a job observed by several providers counts once per run.',
            },
            'counts_complete': not incomplete,
            'sources_total': len(self.sources) + self.truncated,
            'sources_attempted': len(attempted),
            'sources_succeeded': sum(s.attempt_outcome() == ATTEMPT_OK for s in attempted),
            'sources_partial': sum(s.attempt_outcome() == ATTEMPT_PARTIAL for s in attempted),
            'sources_failed': sum(s.attempt_outcome() in (ATTEMPT_FAILED, ATTEMPT_INGESTION_FAILED)
                                  for s in attempted),
            'sources_skipped': sum(not s.attempted for s in self.sources),
            'sources_incomplete': len(incomplete),
            'sources_truncated': self.truncated,
            'sources': sources,
            'engagement': _engagement(self.observed_jobs(), saved_ids, applied_ids, measured_at),
            'retention': retention_metadata(self.started_at),
        }
        return validate(payload)


# --------------------------------------------------------------------------
# Retention
# --------------------------------------------------------------------------

RETENTION_POLICY = (
    'Discovery telemetry and verbose discovery decisions are retained for exactly 90 days. '
    'A run whose created_at is strictly older than the UTC cutoff has both removed; a run '
    'exactly at the cutoff is kept. Jobs, job observations, applications, user decisions and '
    'application history are never deleted by this cleanup.'
)


def retention_metadata(started_at):
    started = _parse(started_at)
    expires = (started + timedelta(days=RETENTION_DAYS)).isoformat() if started else None
    return {'retention_days': RETENTION_DAYS, 'expires_at': expires,
            'policy': RETENTION_POLICY}


def retention_cutoff(clock=None):
    return (clock or _utc_now()) - timedelta(days=RETENTION_DAYS)


def prune_expired(db, clock=None, limit=500):
    """Remove expired discovery telemetry and verbose decisions in place.

    Idempotent, bounded, and limited to discovery telemetry: it only ever drops
    the two report keys this feature owns, never a Job, JobObservation,
    Application, user decision or application-history row, and never any other
    operational field an existing behaviour still reads. Safe against a
    malformed legacy report (a non-dict payload is left untouched rather than
    rewritten). Older-than-cutoff is strict, so a run exactly at the boundary is
    preserved.
    """
    from sqlalchemy import select
    from .models import AutomationRun
    cutoff = retention_cutoff(clock).isoformat()
    removed = 0
    rows = db.scalars(select(AutomationRun)
                      .where(AutomationRun.task == 'discover', AutomationRun.created_at < cutoff)
                      .order_by(AutomationRun.id)
                      .limit(max(1, int(limit))))
    for run in rows:
        report = run.report
        if not isinstance(report, dict):
            continue
        expired = [key for key in ('decisions', REPORT_KEY) if key in report]
        if not expired:
            continue
        run.report = {k: v for k, v in report.items() if k not in expired}
        removed += 1
    return {'runs_pruned': removed, 'cutoff': cutoff, 'retention_days': RETENTION_DAYS}


# --------------------------------------------------------------------------
# Validation
# --------------------------------------------------------------------------

# Keys that must never appear anywhere inside a telemetry payload.
FORBIDDEN_KEYS = frozenset({
    'decisions', 'decision', 'description', 'description_observed', 'title', 'title_observed',
    'job_url', 'canonical_url', 'apply_url', 'source_url', 'url', 'company', 'email',
    'raw_text', 'raw_fields', 'provider_facts', 'summary', 'answer', 'answers', 'notes',
    'token', 'credential', 'credentials', 'password', 'traceback', 'stacktrace', 'path',
    'message', 'evidence', 'item', 'profile', 'cv', 'candidate',
})
MAX_STRING = 700
MAX_DEPTH = 8


def validate(payload):
    """Fail loudly rather than publish an impossible or unsafe funnel."""
    if not isinstance(payload, dict):
        raise TelemetryError('Telemetry payload must be an object')
    if payload.get('schema_version') != TELEMETRY_SCHEMA_VERSION:
        raise TelemetryError(f'Unsupported telemetry schema {payload.get("schema_version")!r}')
    if payload.get('status') == 'TELEMETRY_ERROR':
        _assert_safe(payload)
        return payload

    run_funnel = _validate_funnel(payload.get('funnel'), 'run')
    sources = payload.get('sources')
    if not isinstance(sources, list):
        raise TelemetryError('Telemetry sources must be a list')

    observation_totals = {stage: 0 for stage in OBSERVATION_STAGES}
    canonical_sums = {stage: 0 for stage in CANONICAL_STAGES}
    canonical_max = {stage: 0 for stage in CANONICAL_STAGES}
    for source in sources:
        if not isinstance(source, dict):
            raise TelemetryError('Each telemetry source must be an object')
        state = source.get('attempt_state')
        if state not in ATTEMPT_STATES:
            raise TelemetryError(f'Unknown source attempt state {state!r}')
        if source.get('attempt_outcome') not in ATTEMPT_OUTCOMES:
            raise TelemetryError(f'Unknown attempt outcome {source.get("attempt_outcome")!r}')
        if source.get('fetch_outcome') not in FETCH_OUTCOMES:
            raise TelemetryError(f'Unknown fetch outcome {source.get("fetch_outcome")!r}')
        funnel = _validate_funnel(source.get('funnel'), f'source {source.get("source_id")}')
        attempted = bool(source.get('attempted'))
        if attempted != (state == ATTEMPTED):
            raise TelemetryError('Source attempted flag disagrees with its attempt state')
        if not attempted:
            if any(funnel[stage] for stage in FUNNEL_STAGES):
                raise TelemetryError('A source that was not attempted cannot have funnel counts')
            if source.get('fetch_outcome') != FETCH_NOT_ATTEMPTED:
                raise TelemetryError('A skipped source must report fetch_outcome NOT_ATTEMPTED')
        error_class = source.get('error_class')
        if error_class is not None and error_class not in ERROR_CLASSES:
            raise TelemetryError(f'Unbounded telemetry error class {error_class!r}')
        error_code = source.get('error_code')
        if error_code is not None and error_code not in ERROR_CODES | {ERROR_CLASS_UNCLASSIFIED}:
            raise TelemetryError(f'Unbounded telemetry error code {error_code!r}')
        for stage in OBSERVATION_STAGES:
            observation_totals[stage] += funnel[stage]
        for stage in CANONICAL_STAGES:
            canonical_sums[stage] += funnel[stage]
            canonical_max[stage] = max(canonical_max[stage], funnel[stage])

    for stage in OBSERVATION_STAGES:
        if run_funnel[stage] != observation_totals[stage]:
            raise TelemetryError(
                f'Run {stage} must equal the sum of per-source observation counts')
    for stage in CANONICAL_STAGES:
        if not canonical_max[stage] <= run_funnel[stage] <= canonical_sums[stage]:
            raise TelemetryError(
                f'Run {stage} must lie between the largest per-source count and their sum')

    engagement = payload.get('engagement')
    _validate_engagement(engagement)
    for source in sources:
        _validate_engagement(source.get('engagement'))

    retention = payload.get('retention') or {}
    if retention.get('retention_days') != RETENTION_DAYS:
        raise TelemetryError('Discovery telemetry retention must be exactly 90 days')

    _assert_safe(payload)
    return payload


def _validate_funnel(funnel, label):
    if not isinstance(funnel, dict):
        raise TelemetryError(f'Missing {label} funnel')
    counts = {}
    for stage in FUNNEL_STAGES:
        value = funnel.get(stage)
        if type(value) is not int or isinstance(value, bool) or value < 0:
            raise TelemetryError(f'{label} {stage} must be a non-negative integer')
        counts[stage] = value
    if set(funnel) - set(FUNNEL_STAGES):
        raise TelemetryError(f'{label} funnel carries unknown stages')
    for earlier, later in zip(FUNNEL_STAGES, FUNNEL_STAGES[1:]):
        if counts[later] > counts[earlier]:
            raise TelemetryError(
                f'{label} funnel is not monotonic: {later}={counts[later]} > '
                f'{earlier}={counts[earlier]}')
    return counts


def _validate_engagement(engagement):
    if not isinstance(engagement, dict):
        raise TelemetryError('Engagement outcomes must be an object')
    if engagement.get('basis') != ENGAGEMENT_BASIS:
        raise TelemetryError('Engagement outcomes must declare exactly one basis')
    for outcome in ENGAGEMENT_OUTCOMES:
        entry = engagement.get(outcome)
        if not isinstance(entry, dict):
            raise TelemetryError(f'Missing engagement outcome {outcome}')
        state = entry.get('state')
        if state not in (ENGAGEMENT_AVAILABLE, ENGAGEMENT_UNAVAILABLE):
            raise TelemetryError(f'Unknown engagement state for {outcome}')
        count = entry.get('count')
        if state == ENGAGEMENT_UNAVAILABLE and count is not None:
            raise TelemetryError(f'{outcome} is unavailable and must not carry a count')
        if state == ENGAGEMENT_AVAILABLE and (type(count) is not int or count < 0):
            raise TelemetryError(f'{outcome} must carry a non-negative integer count')
    if any(stage in engagement for stage in FUNNEL_STAGES):
        raise TelemetryError('Engagement outcomes must stay outside the discovery funnel')


def _assert_safe(value, depth=0, key=None):
    """No private per-job content, unbounded external text, or nesting bomb."""
    if depth > MAX_DEPTH:
        raise TelemetryError('Telemetry payload is nested too deeply')
    if isinstance(value, dict):
        for child_key, child in value.items():
            if not isinstance(child_key, str):
                raise TelemetryError('Telemetry keys must be strings')
            if child_key.lower() in FORBIDDEN_KEYS:
                raise TelemetryError(f'Telemetry must not carry {child_key!r}')
            _assert_safe(child, depth + 1, child_key)
    elif isinstance(value, (list, tuple)):
        for child in value:
            _assert_safe(child, depth + 1, key)
    elif isinstance(value, str):
        if len(value) > MAX_STRING:
            raise TelemetryError(f'Telemetry string for {key!r} exceeds {MAX_STRING} characters')
    elif value is not None and not isinstance(value, (int, float, bool)):
        raise TelemetryError(f'Unsupported telemetry value type for {key!r}')


# --------------------------------------------------------------------------
# Read model for the local API
# --------------------------------------------------------------------------

SOURCE_VIEW_FIELDS = (
    'source_id', 'source_name', 'provider_family', 'attempted', 'attempt_state',
    'attempt_outcome', 'fetch_outcome', 'health', 'completion', 'completion_reason',
    'error_code', 'error_class', 'counts_complete', 'incomplete_reason', 'rolled_back',
    'funnel', 'funnel_basis', 'stage_exits', 'diagnostics', 'provider_metrics', 'engagement',
)
RUN_VIEW_FIELDS = (
    'schema_version', 'run_id', 'run_status', 'status', 'telemetry_error_code',
    'telemetry_error_detail', 'trigger', 'started_at', 'finished_at', 'duration_seconds',
    'source_filter', 'versions', 'funnel', 'funnel_basis', 'funnel_aggregation',
    'counts_complete', 'sources_total', 'sources_attempted', 'sources_succeeded',
    'sources_partial', 'sources_failed', 'sources_skipped', 'sources_incomplete',
    'sources_truncated', 'engagement', 'retention', 'note',
)

TELEMETRY_UNAVAILABLE = 'TELEMETRY_UNAVAILABLE'
TELEMETRY_OK = 'OK'
RUN_IN_PROGRESS = 'RUN_IN_PROGRESS'
NO_DATA = 'NO_DATA'

LEGACY_RUN_NOTE = (
    'This discovery run predates discovery-telemetry-v1, or its telemetry has passed the '
    '90-day retention boundary. Historical reports are never rewritten to simulate telemetry '
    'that was not captured.'
)


def public_view(run):
    """Project one AutomationRun into the read-only telemetry API shape.

    Whitelist-based on purpose: even a payload written by a different build can
    never leak a verbose decision record or private job content through this
    endpoint, because only known aggregate fields are copied out.
    """
    report = run.report if isinstance(run.report, dict) else {}
    payload = report.get(REPORT_KEY)
    base = {'run_id': run.id, 'run_created_at': run.created_at,
            'run_updated_at': run.updated_at, 'run_status': run.status}
    if run.status == 'RUNNING':
        return {**base, 'telemetry_status': RUN_IN_PROGRESS, 'schema_version': None,
                'telemetry': None,
                'note': 'This discovery run is still in progress; no finalized telemetry exists '
                        'for it yet.'}
    if not isinstance(payload, dict) or payload.get('schema_version') != TELEMETRY_SCHEMA_VERSION:
        return {**base, 'telemetry_status': TELEMETRY_UNAVAILABLE, 'schema_version': None,
                'telemetry': None, 'note': LEGACY_RUN_NOTE}
    view = {field: payload[field] for field in RUN_VIEW_FIELDS if field in payload}
    view['sources'] = [{field: source[field] for field in SOURCE_VIEW_FIELDS if field in source}
                       for source in payload.get('sources', []) if isinstance(source, dict)]
    return {**base, 'telemetry_status': TELEMETRY_OK,
            'schema_version': TELEMETRY_SCHEMA_VERSION, 'telemetry': view, 'note': None}


# --------------------------------------------------------------------------
# Small helpers
# --------------------------------------------------------------------------

def _utc_now():
    return datetime.now(timezone.utc)


def _parse(value):
    try:
        parsed = datetime.fromisoformat(str(value).replace('Z', '+00:00'))
    except (ValueError, TypeError):
        return None
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)


def _enum(value, allowed, default=None):
    if value is None:
        return default
    if hasattr(value, 'value'):
        value = value.value
    return value if value in allowed else default


def _metrics(metrics):
    """Bounded numeric provider diagnostics, kept out of the funnel."""
    if not isinstance(metrics, dict):
        return None
    out = {}
    for field in PROVIDER_METRIC_FIELDS:
        value = metrics.get(field)
        if isinstance(value, bool):
            out[field] = value
        elif isinstance(value, (int, float)):
            out[field] = value
    return out or None


def _bounded_name(value):
    """A user-configured source name may be returned through the local API."""
    return str(value or 'Unnamed source')[:200]


def _bounded_family(value):
    """Never external content: an identifier-shaped token or a safe fallback."""
    text = str(value or '')[:60]
    return text if re.fullmatch(r'[A-Za-z0-9_.-]{1,60}', text) else 'unknown'
