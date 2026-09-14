"""Typed contract every job-discovery provider implements (issue #38).

Kept to the minimum Greenhouse genuinely needs while staying shape-
compatible with a plausible future Lever/Ashby migration (a JSON list
endpoint, an optional per-item detail endpoint, no true pagination cursor
today). Do not add fields here for a provider ASTRA does not yet have --
extend this contract when that provider is actually being migrated.
"""
from dataclasses import dataclass, field
from enum import Enum

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
