"""Typed contract every job-discovery provider implements (issue #38).

Kept to the minimum Greenhouse genuinely needs while staying shape-
compatible with a plausible future Lever/Ashby migration (a JSON list
endpoint, an optional per-item detail endpoint, no true pagination cursor
today). Do not add fields here for a provider ASTRA does not yet have --
extend this contract when that provider is actually being migrated.
"""
from dataclasses import dataclass, field
from enum import Enum
from urllib.parse import urlsplit

VERSION = 'job-providers-2'


class FetchCompletion(str, Enum):
    """What fraction of the source's postings this fetch actually covers.

    EMPTY is not a value here on purpose: a healthy board with zero open
    roles is a COMPLETE fetch that happens to have zero records, never
    treated the same as a failure. See SourceHealth.EMPTY for that case.

    PARTIAL describes incomplete content/details in the accepted records.
    Enumerated rows are accounted for either as accepted records or as
    validation rejections; malformed rows need not appear in records.
    See completion_reason and records_rejected for the distinction.

    These are three independent axes, not one scale -- COMPLETE does not
    imply perfect source fidelity:
    - enumeration completeness: did every posting the source listed end
      up counted (in `records` or as a validation rejection)? Always yes.
    - content/detail completeness: PARTIAL + completion_reason
      DETAIL_BUDGET_EXHAUSTED/DETAIL_FETCH_INCOMPLETE.
    - record validity: some/all listed rows failed native-shape
      validation -- see SourceHealth.PARTIAL (some rejected, still
      COMPLETE + completion_reason SOME_RECORDS_REJECTED) versus FAILED +
      SourceHealth.MALFORMED (all rejected, completion_reason
      ALL_RECORDS_REJECTED).
    """
    COMPLETE = 'COMPLETE'
    PARTIAL = 'PARTIAL'
    FAILED = 'FAILED'
    CANCELLED = 'CANCELLED'


class CompletionReason(str, Enum):
    """Why `FetchBatch.completion`/`health` is not a plain
    COMPLETE+HEALTHY. None when there is nothing to explain. Can
    accompany COMPLETE (SOME_RECORDS_REJECTED: enumeration and detail
    fetching both finished normally, but some listed rows were invalid)
    as well as PARTIAL/FAILED/CANCELLED.
    """
    DETAIL_BUDGET_EXHAUSTED = 'DETAIL_BUDGET_EXHAUSTED'
    DETAIL_FETCH_INCOMPLETE = 'DETAIL_FETCH_INCOMPLETE'
    ALL_RECORDS_REJECTED = 'ALL_RECORDS_REJECTED'
    SOME_RECORDS_REJECTED = 'SOME_RECORDS_REJECTED'
    TRANSPORT_ERROR = 'TRANSPORT_ERROR'
    PAGINATION_LIMIT_REACHED = 'PAGINATION_LIMIT_REACHED'


class SourceHealth(str, Enum):
    HEALTHY = 'HEALTHY'
    EMPTY = 'EMPTY'
    PARTIAL = 'PARTIAL'
    RATE_LIMITED = 'RATE_LIMITED'
    AUTH_REQUIRED = 'AUTH_REQUIRED'
    POLICY_BLOCKED = 'POLICY_BLOCKED'
    MALFORMED = 'MALFORMED'
    UNAVAILABLE = 'UNAVAILABLE'


@dataclass(frozen=True)
class ProviderCapabilities:
    provider: str
    supports_cursor: bool = False
    supports_detail_fetch: bool = True


@dataclass(frozen=True)
class FetchContext:
    """Bounded orchestration input a provider MAY use to prioritize which
    items are worth a bounded detail-fetch budget. This is a plain keyword
    hint, never a ranking or eligibility signal -- a provider must not
    import recall/ranking logic to interpret it, and must produce a
    complete, truthful result whether or not hints are supplied.
    """
    title_hints: tuple = ()
    detail_budget: int = 100
    deadline_seconds: float = 45.0


@dataclass(frozen=True)
class ProviderError:
    code: str
    message: str


@dataclass
class ProviderRecord:
    """A validated, provider-native posting. Not ASTRA's canonical job
    record (issue #40 owns that) -- just enough to answer "where did this
    come from" and to compatibility-translate into the existing ingestion
    dict shape.
    """
    provider: str
    source_board: str
    provider_job_id: str
    title: str
    location: str
    description: str
    apply_url: str
    source_url: str
    posted_at: str
    closing_at: str
    remote_status: str
    retrieved_at: str
    provider_version: str
    raw_fields: dict = field(default_factory=dict)


@dataclass
class SourceMetrics:
    """`requests_*` count every HTTP request the transport made for this
    fetch -- list and detail calls combined, including a redirect hop or a
    retried attempt as a separate request. `detail_requests_*` are the
    logical per-posting detail operations (success requires a valid merge),
    not physical HTTP requests. Retries and redirects belong to the general
    request/retry counters. Each failed transport operation, rejected source
    row or malformed detail counts once in errors_count; an aggregate
    all-rejected outcome does not count the same row errors again.
    `encoded_bytes_read` is wire (possibly compressed) bytes;
    `decoded_bytes_read` is usable content bytes after decompression --
    they differ only when the response was compressed.
    """
    elapsed_seconds: float = 0.0
    requests_attempted: int = 0
    requests_succeeded: int = 0
    detail_requests_attempted: int = 0
    detail_requests_succeeded: int = 0
    retries: int = 0
    encoded_bytes_read: int = 0
    decoded_bytes_read: int = 0
    records_received: int = 0
    records_accepted: int = 0
    records_rejected: int = 0
    content_cap_reached: bool = False
    errors_count: int = 0


@dataclass
class FetchBatch:
    provider: str
    source_board: str
    completion: FetchCompletion
    health: SourceHealth
    records: list
    metrics: SourceMetrics
    error: 'ProviderError | None' = None
    cursor: 'str | None' = None
    completion_reason: 'str | None' = None


class Provider:
    """Base contract. A provider owns retrieval semantics only -- never
    ranking, eligibility, canonical normalization, application tracking,
    or UI.
    """
    def capabilities(self) -> ProviderCapabilities:
        raise NotImplementedError

    def fetch(self, context: FetchContext, source_board: str, cursor=None) -> FetchBatch:
        raise NotImplementedError


class ProviderFetchFailed(ValueError):
    """Raised by the compatibility layer for a FAILED/CANCELLED batch.
    Carries the batch's own bounded completion/health/error/metrics so
    callers (backend.main's per-source exception handler) can report the
    true outcome instead of guessing or falling back to a stale/default
    value. Provider-agnostic (issue #39): originally lived in
    greenhouse.py, moved here once Lever/Ashby needed the same type
    without importing it from an unrelated provider module.
    """
    def __init__(self, message, completion, health, completion_reason=None, error_code=None, metrics=None):
        super().__init__(message)
        self.completion = completion.value if hasattr(completion, 'value') else completion
        self.health = health.value if hasattr(health, 'value') else health
        self.completion_reason = completion_reason
        self.error_code = error_code
        self.metrics = metrics


# Transport failure code -> SourceHealth. Provider-agnostic (issue #39):
# every provider maps the same fixed set of backend.job_providers.transport
# TransportError codes to a health value the same way, so this lives here
# once instead of being copy-pasted into every provider module.
_HEALTH_FOR_ERROR = {
    'POLICY_BLOCKED': SourceHealth.POLICY_BLOCKED,
    'DESTINATION_BLOCKED': SourceHealth.POLICY_BLOCKED,
    'DNS_FAILURE': SourceHealth.UNAVAILABLE,
    'DNS_QUEUE_SATURATED': SourceHealth.UNAVAILABLE,
    'CONNECT_FAILED': SourceHealth.UNAVAILABLE,
    'CONNECT_TIMEOUT': SourceHealth.UNAVAILABLE,
    'READ_TIMEOUT': SourceHealth.UNAVAILABLE,
    'READ_FAILED': SourceHealth.UNAVAILABLE,
    'WRITE_FAILED': SourceHealth.UNAVAILABLE,
    'WRITE_TIMEOUT': SourceHealth.UNAVAILABLE,
    'INVALID_EXTERNAL_URL': SourceHealth.MALFORMED,
    'REMOTE_PROTOCOL_ERROR': SourceHealth.MALFORMED,
    'DEADLINE_EXCEEDED': SourceHealth.UNAVAILABLE,
    'RATE_LIMITED': SourceHealth.RATE_LIMITED,
    'UPSTREAM_UNAVAILABLE': SourceHealth.UNAVAILABLE,
    'UPSTREAM_ERROR': SourceHealth.UNAVAILABLE,
    'TOO_MANY_REDIRECTS': SourceHealth.UNAVAILABLE,
    'INVALID_REDIRECT': SourceHealth.MALFORMED,
    'INVALID_JSON': SourceHealth.MALFORMED,
    'UNEXPECTED_CONTENT_TYPE': SourceHealth.MALFORMED,
    'UNSUPPORTED_CONTENT_ENCODING': SourceHealth.MALFORMED,
    'DECODE_FAILED': SourceHealth.MALFORMED,
    'RESPONSE_TOO_LARGE': SourceHealth.PARTIAL,
}


def health_for_error_code(code: str) -> SourceHealth:
    return _HEALTH_FOR_ERROR.get(code, SourceHealth.UNAVAILABLE)


MAX_DOWNSTREAM_URL_LENGTH = 2000


def valid_downstream_url(value) -> bool:
    """A URL usable by backend.services.add_job() -- scheme http/https, a
    real hostname, no embedded userinfo credentials, and within the
    length ingestion accepts (matching add_job's own check exactly:
    `url.scheme not in ('http','https') or not url.hostname or
    url.username or url.password or len(...)>2000`).

    Provider-agnostic (issue #39 Codex finding 1): every provider must
    reject a record whose URL fails this BEFORE accepting it as a valid
    record. A record that passes provider-native validation but fails
    this check used to reach backend.services.add_job() inside
    backend.main's per-source transaction, raise a plain ValueError, and
    roll back every other valid job already committed in that same
    source's run -- a malformed/hostile external URL must never be able
    to do that. This is intentionally the same check every provider
    applies, since it is ingestion's requirement, not a provider-specific
    one -- providers must not each invent their own version of it.
    """
    if not isinstance(value, str) or not value.strip():
        return False
    if len(value) > MAX_DOWNSTREAM_URL_LENGTH:
        return False
    try:
        parts = urlsplit(value)
    except ValueError:
        return False
    return (parts.scheme in ('http', 'https') and bool(parts.hostname)
            and not parts.username and not parts.password)


def outcome_for(rows, records, rejected, completion_reason=None):
    """Shared COMPLETE/EMPTY/FAILED/PARTIAL classification (issue #39,
    moved here from greenhouse.py which had no provider-specific logic in
    it). `rows` is every row the source enumerated (pre-validation),
    `records` the accepted subset, `rejected` the count that failed
    native-shape validation. `completion_reason` lets a caller force a
    PARTIAL outcome for a reason with no bearing on row validity (e.g. a
    detail-fetch or pagination budget being exhausted).

    A genuinely empty board (`rows` was empty to begin with) is never
    confused with a response that produced rows none of which were
    usable (`rows` non-empty, `records` empty -> FAILED/ALL_RECORDS_REJECTED).
    """
    if rows and not records:
        return (FetchCompletion.FAILED, SourceHealth.MALFORMED,
                ProviderError('ALL_RECORDS_REJECTED', 'Every posting in the response failed validation'),
                CompletionReason.ALL_RECORDS_REJECTED.value)
    if not records:
        return FetchCompletion.COMPLETE, SourceHealth.EMPTY, None, None
    if completion_reason:
        return FetchCompletion.PARTIAL, SourceHealth.PARTIAL, None, completion_reason
    if rejected:
        return FetchCompletion.COMPLETE, SourceHealth.PARTIAL, None, CompletionReason.SOME_RECORDS_REJECTED.value
    return FetchCompletion.COMPLETE, SourceHealth.HEALTHY, None, None
