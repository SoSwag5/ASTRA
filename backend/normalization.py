"""Deterministic normalization for issue #40.

Turns provider-native observation facts (title, employer, location,
workplace, description, URL) into separate MATCHING representations that
backend.deduplication.py consumes. Never mutates or replaces the original
DISPLAY values a Job/JobObservation stores -- normalization only derives
extra keys used for comparison.

Guarantees (see docs/architecture/adr/0010-job-observation-and-conservative-
deduplication.md):
- deterministic: same input always produces the same output.
- idempotent: normalizing an already-normalized value is a no-op.
- order-independent: does not depend on any other observation.
- Unicode-safe: NFKC-normalizes text before comparison.
- locale-conservative: no locale-specific casing/collation tricks.
- network-free: never resolves DNS, fetches a URL, or inspects remote
  content.
- bounded: every derived value has a fixed maximum size.
- versioned: NORMALIZATION_VERSION changes whenever a rule changes, so a
  future algorithm change can tell old normalized values from new ones
  apart instead of silently comparing incompatible representations.
"""
import hashlib
import unicodedata
from dataclasses import dataclass, field
from urllib.parse import urlsplit

from .policy import canonical as _canonical_url
from .policy import norm as _word_norm

NORMALIZATION_VERSION = 'normalization-1'

UNKNOWN = 'UNKNOWN'

# Identity kinds a JobObservation may carry. 'native' and 'url_fallback' are
# provider-issued identity; 'manual' is a user-pasted/entered job; 'legacy_incomplete'
# marks a #40-migration backfill row for a pre-#40 Job with no real provenance.
IDENTITY_KINDS = ('native', 'url_fallback', 'manual', 'legacy_incomplete')

# A URL whose last path segment is one of these generic words is a careers
# root, a login/portal page, or a listing/search page -- never a single
# job-specific posting -- so it must never be treated as identity evidence
# (Rule 2 / Rule 4 both require a job-specific URL).
_GENERIC_LAST_SEGMENTS = {
    '', 'jobs', 'job', 'careers', 'career', 'opening', 'openings', 'position',
    'positions', 'apply', 'application', 'applications', 'login', 'signin',
    'sign-in', 'log-in', 'search', 'index', 'home', 'board', 'boards',
    'postings', 'posting', 'vacancies', 'vacancy', 'listing', 'listings',
    'current-openings', 'current-vacancies',
}

_WORKPLACE_CANON = {
    'remote': 'REMOTE',
    'hybrid': 'HYBRID',
    'on site': 'ONSITE',
    'onsite': 'ONSITE',
    'on-site': 'ONSITE',
}

_CONTENT_FINGERPRINT_MIN_LENGTH = 40
_CONTENT_FINGERPRINT_MAX_INPUT = 50_000


def is_job_specific_url(url):
    """True only for a URL that plausibly identifies ONE posting, never a
    generic careers root, login/portal page, or search/listing page. Purely
    syntactic (path shape) -- never fetches the URL or inspects its content.
    """
    if not url or not isinstance(url, str):
        return False
    try:
        parts = urlsplit(url)
    except ValueError:
        return False
    if parts.scheme not in ('http', 'https') or not parts.hostname:
        return False
    segments = [s for s in parts.path.rstrip('/').split('/') if s]
    if not segments:
        return False
    return segments[-1].lower() not in _GENERIC_LAST_SEGMENTS


def normalize_url_for_identity(url):
    """The deterministic matching form of a job-specific source URL, or
    None when the URL is missing or not job-specific (a generic root/
    login/portal/search page must never become identity evidence).
    Reuses backend.policy.canonical() -- the same tracking-parameter/
    scheme/host normalization already used for Job.canonical_url -- so
    there is exactly one definition of "the same URL" in ASTRA, not two.
    """
    if not is_job_specific_url(url):
        return None
    return _canonical_url(url) or None


def employer_key(name):
    """Matching key for an employer display name, or None for empty/UNKNOWN
    (an unknown employer is never treated as equal to another unknown one).
    """
    if not name or name == UNKNOWN:
        return None
    n = _word_norm(name)
    return n or None


def title_key(title):
    """Matching key for a job title. Deliberately exact (Unicode-normalize
    + casefold + collapse whitespace/punctuation) -- it never strips
    seniority words (Junior/Senior/Lead/Principal/Manager), so 'SOC Analyst'
    and 'Senior SOC Analyst' remain different keys. Title similarity is
    never, on its own, sufficient evidence for an automatic merge --
    backend.deduplication.py only ever compares this key for exact equality.
    """
    if not title:
        return None
    n = _word_norm(title)
    return n or None


def location_key(location):
    """Matching key for a location, or None for empty/UNKNOWN. Two UNKNOWN
    locations are never treated as evidence of equality -- callers must
    treat `None` as "no comparable information", not as a wildcard match.
    """
    if not location or location == UNKNOWN:
        return None
    n = _word_norm(location)
    return n or None


def workplace_key(value):
    """Canonical REMOTE/HYBRID/ONSITE token, or None when the value is
    empty/UNKNOWN/unrecognized. Missing workplace information is never
    inferred to be On-site.
    """
    if not value or value == UNKNOWN:
        return None
    return _WORKPLACE_CANON.get(_word_norm(value))


def content_fingerprint(description):
    """A bounded, deterministic exact-content fingerprint. Harmless
    whitespace/HTML-formatting differences collapse to the same
    fingerprint (the caller is expected to have already stripped markup --
    see backend.adapters.clean() -- this only normalizes remaining
    whitespace/case/Unicode form). Returns None when the description is too
    short to be a meaningful signal, rather than fingerprinting near-empty
    text that would collide across unrelated postings. This is an EXACT
    fingerprint only -- #40 intentionally does not implement fuzzy semantic
    similarity as an automatic-merge criterion.
    """
    if not description:
        return None
    text = unicodedata.normalize('NFKC', description)
    collapsed = ' '.join(text.split()).strip().lower()
    if len(collapsed) < _CONTENT_FINGERPRINT_MIN_LENGTH:
        return None
    bounded = collapsed[:_CONTENT_FINGERPRINT_MAX_INPUT]
    return hashlib.sha256(bounded.encode('utf-8')).hexdigest()


@dataclass(frozen=True)
class JobObservationInput:
    """Everything one provider/manual observation of a posting reported,
    before normalization. Constructed by backend.services.add_job() (or a
    provider-specific bridge) from either a rich ProviderRecord or a plain
    legacy ingestion dict; never persisted directly -- see
    backend.models.JobObservation for the persisted shape.
    """
    provider_family: str = 'manual'
    identity_kind: str = 'manual'
    provider_job_id: str = ''
    job_source_id: 'int | None' = None
    board_key: str = ''
    requisition_id: str = ''
    requisition_id_authority: str = ''
    employer_name: str = UNKNOWN
    title: str = ''
    location: str = UNKNOWN
    workplace: str = UNKNOWN
    description: str = ''
    source_url: str = ''
    apply_url: str = ''
    posted_at: str = ''
    posted_at_authority: str = 'none'
    closing_at: str = ''
    retrieved_at: str = ''
    provider_version: str = ''
    provider_facts: dict = field(default_factory=dict)
    anomaly_flags: tuple = ()


@dataclass(frozen=True)
class NormalizedObservation:
    """Matching-only representations derived from a JobObservationInput.
    Every field is None when the underlying fact is unknown/not job-specific
    -- callers must never treat None as a wildcard equal to another None.
    """
    employer_key: 'str | None'
    title_key: 'str | None'
    location_key: 'str | None'
    workplace_key: 'str | None'
    url_identity: 'str | None'
    content_fingerprint: 'str | None'


def normalize(observation: JobObservationInput) -> NormalizedObservation:
    return NormalizedObservation(
        employer_key=employer_key(observation.employer_name),
        title_key=title_key(observation.title),
        location_key=location_key(observation.location),
        workplace_key=workplace_key(observation.workplace),
        url_identity=normalize_url_for_identity(observation.source_url),
        content_fingerprint=content_fingerprint(observation.description),
    )


@dataclass(frozen=True)
class CanonicalJobView:
    """The compatibility-facing field values one observation would
    contribute to Job if used to fill an UNKNOWN/empty field (Phase 9's
    canonical-field policy). Never used to overwrite an already-known
    value -- see backend.services.apply_canonical_updates().
    """
    company: str
    title: str
    location: str
    remote_status: str
    job_url: str
    canonical_url: str
    apply_url: str
    date_posted: str
    closing_date: str
    description: str


def canonical_view(observation: JobObservationInput) -> CanonicalJobView:
    return CanonicalJobView(
        company=observation.employer_name or UNKNOWN,
        title=observation.title or '',
        location=observation.location or UNKNOWN,
        remote_status=observation.workplace or UNKNOWN,
        job_url=observation.source_url or '',
        canonical_url=_canonical_url(observation.source_url or ''),
        apply_url=observation.apply_url or '',
        date_posted=observation.posted_at if observation.posted_at_authority == 'documented_provider_field' else '',
        closing_date=observation.closing_at or '',
        description=observation.description or '',
    )


@dataclass(frozen=True)
class FieldEvidence:
    """Bounded, reviewable evidence for one canonical-field decision or one
    dedupe match -- answers "why does the canonical Job contain this value"
    and "why did these observations merge". Stored as a plain dict (JSON)
    on JobObservation.match_evidence; never a separate relational table
    (Phase 17 -- no proven implementation blocker requires one).
    """
    field: str
    raw_field: str
    transformation: str
    authority: str
    observed_value: str
    canonical_value: str
