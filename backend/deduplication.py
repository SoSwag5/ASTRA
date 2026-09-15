"""Conservative, versioned deduplication for issue #40.

Owns exactly one question: "have we already observed the same posting?" --
never eligibility, ranking, or relevance (issue #41's job entirely). See
docs/architecture/adr/0010-job-observation-and-conservative-deduplication.md
for the full rule hierarchy and rationale.

Evaluates the strongest evidence first (Rules 1-3). A hard conflict against
the specific candidate a rule found always overrides that rule's own
evidence and downgrades the result to CANDIDATE -- weak similarity never
wins over a known incompatibility. Only ONE existing Job is ever touched per
resolve() call (the new observation is compared against, and merges into at
most one already-persisted Job) -- two existing Jobs are never merged with
each other here. Canonical lookup keys are derived only from the selected
Job fields, and fingerprint evidence alone is never destructive, preventing
an observation from becoming a transitive bridge between incompatible Jobs.
"""
import hashlib
from dataclasses import dataclass, field

from sqlalchemy import select

from .models import Job, JobObservation
from .normalization import (
    JobObservationInput, NormalizedObservation, content_fingerprint as _content_fingerprint_of,
    employer_key as _employer_key_of, location_key as _location_key_of, normalize,
    title_key as _title_key_of, workplace_key as _workplace_key_of, NORMALIZATION_VERSION,
)

DEDUPE_VERSION = 'dedupe-2'

MATCH = 'MATCH'
DISTINCT = 'DISTINCT'
CANDIDATE = 'CANDIDATE'


@dataclass(frozen=True)
class DedupeDecision:
    decision: str
    method: str
    version: str = DEDUPE_VERSION
    evidence: dict = field(default_factory=dict)
    hard_conflicts: tuple = ()
    selected_job_id: 'int | None' = None
    candidate_job_ids: tuple = ()


def _composite_fingerprint(norm: NormalizedObservation) -> str:
    """Cross-provider candidate evidence: requires ALL of employer/title/
    content evidence to be simultaneously known and exact -- a fingerprint
    is never computed (so never matches anything) from partial evidence.
    Workplace/location compatibility is checked separately so conflicts are
    preserved in the reviewable candidate evidence.
    """
    if not (norm.employer_key and norm.title_key and norm.content_fingerprint):
        return ''
    raw = '|'.join((norm.employer_key, norm.title_key, norm.content_fingerprint))
    return hashlib.sha256(raw.encode('utf-8')).hexdigest()


def composite_fingerprint(observation: JobObservationInput) -> str:
    return _composite_fingerprint(normalize(observation))


def canonical_fingerprint(job: Job) -> str:
    """Fingerprint only the fields currently selected on canonical Job."""
    return composite_fingerprint(JobObservationInput(
        employer_name=job.company, title=job.title, location=job.location,
        workplace=job.remote_status, description=job.description,
        source_url=job.job_url,
    ))


def _same_source_different_native_id(db, observation: JobObservationInput, job: Job):
    """Hard conflict: this exact source instance already reported a
    DIFFERENT native/url-fallback id for `job` -- two distinct postings
    from the same board must never be silently merged just because a
    weaker rule (URL/fingerprint) happened to also match.
    """
    if observation.identity_kind not in ('native', 'url_fallback'):
        return False
    if not observation.provider_job_id or observation.job_source_id is None:
        return False
    sibling = db.scalar(select(JobObservation).where(
        JobObservation.job_id == job.id,
        JobObservation.provider_family == observation.provider_family,
        JobObservation.job_source_id == observation.job_source_id,
        JobObservation.identity_kind == observation.identity_kind,
    ).limit(1))
    return sibling is not None and sibling.provider_job_id != observation.provider_job_id


def _different_documented_requisition(db, observation: JobObservationInput, job: Job):
    if not (observation.requisition_id and observation.requisition_id_authority == 'documented_employer_wide'):
        return False
    sibling = db.scalar(select(JobObservation).where(
        JobObservation.job_id == job.id,
        JobObservation.requisition_id_authority == 'documented_employer_wide',
        JobObservation.requisition_id != '',
    ).limit(1))
    return sibling is not None and sibling.requisition_id != observation.requisition_id


def hard_conflict(db, observation: JobObservationInput, norm: NormalizedObservation, job: Job):
    """Returns a short conflict reason code, or None. Any non-None result
    means the candidate `job` must NOT be automatically matched, regardless
    of how strong the rule that found it looked.
    """
    if _same_source_different_native_id(db, observation, job):
        return 'same_source_instance_different_native_id'
    if _different_documented_requisition(db, observation, job):
        return 'different_documented_requisition_id'
    job_employer = _employer_key_of(job.company)
    if norm.employer_key and job_employer and norm.employer_key != job_employer:
        return 'employer_conflict'
    job_title = _title_key_of(job.title)
    if norm.title_key and job_title and norm.title_key != job_title:
        return 'title_conflict'
    job_content = _content_fingerprint_of(job.description)
    if norm.content_fingerprint and job_content and norm.content_fingerprint != job_content:
        return 'content_conflict'
    job_location = _location_key_of(job.location)
    if norm.location_key and job_location and norm.location_key != job_location:
        return 'location_conflict'
    job_workplace = _workplace_key_of(job.remote_status)
    if norm.workplace_key and job_workplace and norm.workplace_key != job_workplace:
        return 'workplace_conflict'
    return None


def _exact_observation_identity(db, observation: JobObservationInput):
    if observation.identity_kind not in ('native', 'url_fallback') or not observation.provider_job_id:
        return None
    return db.scalar(select(JobObservation).where(
        JobObservation.provider_family == observation.provider_family,
        JobObservation.job_source_id == observation.job_source_id,
        JobObservation.identity_kind == observation.identity_kind,
        JobObservation.provider_job_id == observation.provider_job_id,
    ).order_by(JobObservation.id.desc()))


def _job_specific_url_match(db, norm: NormalizedObservation):
    if not norm.url_identity:
        return None
    return db.scalar(select(Job).where(Job.canonical_url == norm.url_identity))


def _documented_requisition_match(db, observation: JobObservationInput, norm: NormalizedObservation):
    if not (observation.requisition_id and observation.requisition_id_authority == 'documented_employer_wide' and norm.employer_key):
        return None
    sibling = db.scalar(select(JobObservation).where(
        JobObservation.requisition_id == observation.requisition_id,
        JobObservation.requisition_id_authority == 'documented_employer_wide',
    ).order_by(JobObservation.id.desc()))
    if sibling is None:
        return None
    job = db.get(Job, sibling.job_id)
    if job is None:
        return None
    from .normalization import employer_key as _employer_key_of
    if _employer_key_of(job.company) != norm.employer_key:
        return None
    return job


def _fingerprint_match(db, fingerprint: str):
    if not fingerprint:
        return None
    return db.scalar(select(Job).where(Job.dedupe_fingerprint == fingerprint))


def _location_or_workplace_confirmed(norm: NormalizedObservation, job: Job):
    """Positive corroboration flag for fingerprint candidate evidence.

    Two UNKNOWN locations must never be read as corroborating evidence
    (Core Product Rule: "UNKNOWN + UNKNOWN geography is not evidence of
    equality").
    """
    job_location = _location_key_of(job.location)
    job_workplace = _workplace_key_of(job.remote_status)
    location_confirmed = bool(norm.location_key and job_location and norm.location_key == job_location)
    workplace_confirmed = bool(norm.workplace_key and job_workplace and norm.workplace_key == job_workplace)
    return location_confirmed or workplace_confirmed


def _weak_candidates(db, norm: NormalizedObservation, exclude_job_id=None, limit=10):
    """Best-effort CANDIDATE evidence only -- deliberately not exhaustive.
    Under-detecting a weak-similarity pair is safe (conservative); the
    correctness property #40 must uphold is that nothing here ever becomes
    an automatic MATCH. Uses an indexed equality lookup on the persisted
    Job.normalized_employer_key, not an all-Job fuzzy scan (Phase 14).
    """
    if not norm.employer_key:
        return []
    candidates = list(db.scalars(
        select(Job).where(Job.normalized_employer_key == norm.employer_key).limit(limit)
    ))
    return [c for c in candidates if c.id != exclude_job_id]


def resolve(db, observation: JobObservationInput) -> DedupeDecision:
    norm = normalize(observation)
    evidence_base = {
        'employer_key': norm.employer_key, 'title_key': norm.title_key,
        'location_key': norm.location_key, 'workplace_key': norm.workplace_key,
    }

    existing_observation = _exact_observation_identity(db, observation)
    if existing_observation is not None:
        return DedupeDecision(
            MATCH, 'exact_observation_identity', evidence={
                **evidence_base, 'provider_family': observation.provider_family,
                'job_source_id': observation.job_source_id, 'identity_kind': observation.identity_kind,
                'provider_job_id': observation.provider_job_id,
            },
            selected_job_id=existing_observation.job_id,
        )

    url_job = _job_specific_url_match(db, norm)
    if url_job is not None:
        conflict = hard_conflict(db, observation, norm, url_job)
        if conflict:
            return DedupeDecision(CANDIDATE, 'exact_source_url_conflict', evidence=evidence_base,
                                   hard_conflicts=(conflict,), candidate_job_ids=(url_job.id,))
        return DedupeDecision(MATCH, 'exact_source_url', evidence={**evidence_base, 'canonical_url': norm.url_identity},
                               selected_job_id=url_job.id)

    requisition_job = _documented_requisition_match(db, observation, norm)
    if requisition_job is not None:
        conflict = hard_conflict(db, observation, norm, requisition_job)
        if conflict:
            return DedupeDecision(CANDIDATE, 'documented_requisition_id_conflict', evidence=evidence_base,
                                   hard_conflicts=(conflict,), candidate_job_ids=(requisition_job.id,))
        return DedupeDecision(MATCH, 'documented_requisition_id',
                               evidence={**evidence_base, 'requisition_id': observation.requisition_id},
                               selected_job_id=requisition_job.id)

    fingerprint = _composite_fingerprint(norm)
    fingerprint_job = _fingerprint_match(db, fingerprint)
    if fingerprint_job is not None:
        conflict = hard_conflict(db, observation, norm, fingerprint_job)
        if not conflict and not _location_or_workplace_confirmed(norm, fingerprint_job):
            conflict = 'insufficient_location_or_workplace_evidence'
        return DedupeDecision(
            CANDIDATE,
            'cross_provider_fingerprint_conflict' if conflict else 'cross_provider_fingerprint_candidate',
            evidence={**evidence_base, 'fingerprint': fingerprint},
            hard_conflicts=(conflict,) if conflict else (),
            candidate_job_ids=(fingerprint_job.id,),
        )

    weak = _weak_candidates(db, norm)
    if weak:
        return DedupeDecision(CANDIDATE, 'weak_similarity', evidence=evidence_base,
                               candidate_job_ids=tuple(c.id for c in weak))

    return DedupeDecision(DISTINCT, 'no_match', evidence=evidence_base)
