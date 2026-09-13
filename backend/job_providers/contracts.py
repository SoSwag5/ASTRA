"""Typed contract every job-discovery provider implements (issue #38).

Kept to the minimum Greenhouse genuinely needs while staying shape-
compatible with a plausible future Lever/Ashby migration (a JSON list
endpoint, an optional per-item detail endpoint, no true pagination cursor
today). Do not add fields here for a provider ASTRA does not yet have --
extend this contract when that provider is actually being migrated.
"""
from dataclasses import dataclass, field
from enum import Enum

VERSION = 'job-providers-1'


class FetchCompletion(str, Enum):
    """What fraction of the source's postings this fetch actually covers.

    EMPTY is not a value here on purpose: a healthy board with zero open
    roles is a COMPLETE fetch that happens to have zero records, never
    treated the same as a failure. See SourceHealth.EMPTY for that case.
    """
    COMPLETE = 'COMPLETE'
    PARTIAL = 'PARTIAL'
    FAILED = 'FAILED'
    CANCELLED = 'CANCELLED'


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
    elapsed_seconds: float = 0.0
    requests: int = 0
    detail_requests: int = 0
    retries: int = 0
    bytes_read: int = 0
    records_received: int = 0
    records_accepted: int = 0
    records_rejected: int = 0
    coverage_cap_reached: bool = False


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


class Provider:
    """Base contract. A provider owns retrieval semantics only -- never
    ranking, eligibility, canonical normalization, application tracking,
    or UI.
    """
    def capabilities(self) -> ProviderCapabilities:
        raise NotImplementedError

    def fetch(self, context: FetchContext, source_board: str, cursor=None) -> FetchBatch:
        raise NotImplementedError
