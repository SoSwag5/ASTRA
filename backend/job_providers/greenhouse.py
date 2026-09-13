"""Greenhouse job-provider (issue #38): fetches one employer board's public
postings and returns validated, provider-native ProviderRecords. Owns
Greenhouse's endpoint/schema/budget rules only -- never ranking,
eligibility, or ASTRA's canonical job schema (issue #40).
"""
import re
import time
from datetime import datetime, timezone
from urllib.parse import urlsplit

from ..adapters import clean
from .contracts import (
    CompletionReason, FetchBatch, FetchCompletion, FetchContext, Provider,
    ProviderCapabilities, ProviderError, ProviderRecord, SourceHealth, SourceMetrics,
    VERSION as PROVIDER_VERSION,
)
from .transport import Budget, TransportError, fetch_json

BOARD_RE = re.compile(r'[a-zA-Z0-9_-]{1,100}')
ID_RE = re.compile(r'\d+')
HYBRID_WORDS = ('hybrid', 'remote', 'distributed', 'in-office', 'on-site', 'onsite')
LOCATION_HINT_RE = re.compile(r'(?:Available Locations?|Work Location|Location)\s*:\s*([^\n]{1,220})', re.I)

_HEALTH_FOR_ERROR = {
    'POLICY_BLOCKED': SourceHealth.POLICY_BLOCKED,
    'DESTINATION_BLOCKED': SourceHealth.POLICY_BLOCKED,
    'DNS_RESOLUTION_FAILED': SourceHealth.UNAVAILABLE,
    'CONNECT_FAILED': SourceHealth.UNAVAILABLE,
    'TIMEOUT': SourceHealth.UNAVAILABLE,
    'DEADLINE_EXCEEDED': SourceHealth.UNAVAILABLE,
    'RATE_LIMITED': SourceHealth.RATE_LIMITED,
    'UPSTREAM_UNAVAILABLE': SourceHealth.UNAVAILABLE,
    'UPSTREAM_ERROR': SourceHealth.UNAVAILABLE,
    'TOO_MANY_REDIRECTS': SourceHealth.UNAVAILABLE,
    'MALFORMED_RESPONSE': SourceHealth.MALFORMED,
    'UNEXPECTED_CONTENT_TYPE': SourceHealth.MALFORMED,
    'UNSUPPORTED_ENCODING': SourceHealth.MALFORMED,
    'RESPONSE_TOO_LARGE': SourceHealth.PARTIAL,
}


class ProviderFetchFailed(ValueError):
    """Raised by the compatibility layer for a FAILED/CANCELLED batch.
    Carries the batch's own completion/health so callers (backend.main's
    per-source exception handler) can report the true outcome instead of
    guessing or falling back to a stale/default value.
    """
    def __init__(self, message, completion, health, error_code=None):
        super().__init__(message)
        self.completion = completion.value if hasattr(completion, 'value') else completion
        self.health = health.value if hasattr(health, 'value') else health
        self.error_code = error_code


def _health_for(error: TransportError) -> SourceHealth:
    return _HEALTH_FOR_ERROR.get(error.code, SourceHealth.UNAVAILABLE)


def _validate_top_level(payload):
    if not isinstance(payload, dict) or not isinstance(payload.get('jobs'), list):
        raise ValueError('Expected a JSON object with a "jobs" list')
    return payload['jobs']


def _valid_url(value):
    if not isinstance(value, str) or not value.strip():
        return False
    parts = urlsplit(value)
    return parts.scheme in ('http', 'https') and bool(parts.hostname)


def _valid_job_id(raw_id):
    return isinstance(raw_id, (str, int)) and not isinstance(raw_id, bool)


def _to_record(row, source_board, retrieved_at):
    """Rejects (returns None for) any row that does not satisfy Greenhouse's
    documented native shape -- never coerces a malformed structured value
    (e.g. a dict id, a non-string title) into a string so it merely looks
    successful.
    """
    if not isinstance(row, dict):
        return None
    raw_id = row.get('id')
    title = row.get('title')
    url = row.get('absolute_url')
    location = row.get('location')
    if not _valid_job_id(raw_id):
        return None
    if not isinstance(title, str) or not title.strip():
        return None
    if not _valid_url(url):
        return None
    if not isinstance(location, dict):
        return None
    location_name = location.get('name')
    if not isinstance(location_name, str) or not location_name.strip():
        return None
    content = row.get('content')
    if content is not None and not isinstance(content, str):
        return None
    description = clean(content or '')
    # Some boards put cities in the description while location says Hybrid.
    if location_name.lower() in HYBRID_WORDS:
        match = LOCATION_HINT_RE.search(description)
        if match:
            location_name = match[1].strip() + ' / ' + location_name
    posted_at = row.get('first_published')
    closing_at = row.get('application_deadline')
    return ProviderRecord(
        provider='greenhouse', source_board=source_board, provider_job_id=str(raw_id),
        title=title, location=location_name, description=description,
        apply_url=url, source_url=url,
        posted_at=posted_at if isinstance(posted_at, str) else '',
        closing_at=closing_at if isinstance(closing_at, str) else '',
        remote_status='UNKNOWN', retrieved_at=retrieved_at, provider_version=PROVIDER_VERSION,
        raw_fields={},
    )


def _to_records(rows, source_board):
    records = []
    rejected = 0
    retrieved_at = datetime.now(timezone.utc).isoformat()
    for row in rows:
        record = _to_record(row, source_board, retrieved_at)
        if record is None:
            rejected += 1
        else:
            records.append(record)
    return records, rejected


def _valid_detail(detail):
    """A detail response is only usable if it is a non-empty dict whose
    optional `content` field, when present, is actually a string. An
    empty dict or a wrong-shaped `content` must never be merged in and
    counted as a successful detail fetch -- that would silently discard
    real board data behind a description that looks empty but was never
    actually fetched.
    """
    if not isinstance(detail, dict) or not detail:
        return False
    content = detail.get('content')
    return content is None or isinstance(content, str)


def _outcome_for(rows, records, completion_reason=None):
    """Distinguishes a genuinely empty board from a response that produced
    rows but none of them were usable -- the latter is a real failure
    (MALFORMED health, FAILED completion, an explicit error), never a
    disguised EMPTY.
    """
    if rows and not records:
        return (FetchCompletion.FAILED, SourceHealth.MALFORMED,
                ProviderError('ALL_RECORDS_REJECTED', 'Every posting in the response failed validation'),
                CompletionReason.ALL_RECORDS_REJECTED.value)
    if not records:
        return FetchCompletion.COMPLETE, SourceHealth.EMPTY, None, None
    if completion_reason:
        return FetchCompletion.PARTIAL, SourceHealth.PARTIAL, None, completion_reason
    return FetchCompletion.COMPLETE, SourceHealth.HEALTHY, None, None


class GreenhouseProvider(Provider):
    def capabilities(self):
        return ProviderCapabilities(provider='greenhouse', supports_cursor=False, supports_detail_fetch=True)

    def fetch(self, context: FetchContext, source_board: str, cursor=None) -> FetchBatch:
        metrics = SourceMetrics()
        started = time.monotonic()
        if not source_board or not BOARD_RE.fullmatch(source_board):
            metrics.elapsed_seconds = time.monotonic() - started
            return FetchBatch('greenhouse', source_board, FetchCompletion.FAILED, SourceHealth.MALFORMED, [], metrics,
                               error=ProviderError('INVALID_BOARD', 'Invalid board identifier'))
        budget = Budget(context.deadline_seconds)
        base = f'https://boards-api.greenhouse.io/v1/boards/{source_board}/jobs'
        try:
            payload = fetch_json(base + '?content=true', budget)
        except TransportError as error:
            if error.code == 'RESPONSE_TOO_LARGE':
                return self._fetch_with_detail_fallback(context, source_board, base, budget, metrics, started)
            return self._failed(source_board, budget, metrics, started, error)
        try:
            rows = _validate_top_level(payload)
        except ValueError as error:
            return self._malformed(source_board, budget, metrics, started, error)
        records, rejected = _to_records(rows, source_board)
        self._copy_budget(metrics, budget)
        metrics.records_received = len(rows)
        metrics.records_accepted = len(records)
        metrics.records_rejected = rejected
        metrics.elapsed_seconds = time.monotonic() - started
        completion, health, error, reason = _outcome_for(rows, records)
        return FetchBatch('greenhouse', source_board, completion, health, records, metrics,
                           error=error, completion_reason=reason)

    def _fetch_with_detail_fallback(self, context, source_board, base, budget, metrics, started):
        """The full content=true payload was too large; fetch the summary
        list instead, then spend a bounded detail-fetch budget on the
        items most likely to matter (context.title_hints, a plain keyword
        list -- never a ranking decision) before the rest. Every summary
        row is still returned; only description completeness for
        non-detailed or invalid-detail rows is partial, reported
        truthfully as PARTIAL with an explicit completion_reason instead
        of being silently dropped or raised away.
        """
        try:
            payload = fetch_json(base, budget)
        except TransportError as error:
            return self._failed(source_board, budget, metrics, started, error)
        try:
            rows = _validate_top_level(payload)
        except ValueError as error:
            return self._malformed(source_board, budget, metrics, started, error)

        hints = tuple(h.strip().lower() for h in context.title_hints if h.strip())

        def matches(row):
            title = str(row.get('title', '')).lower()
            return any(h in title for h in hints) if hints else True

        prioritized = [r for r in rows if isinstance(r, dict) and matches(r)] + \
                      [r for r in rows if isinstance(r, dict) and not matches(r)]
        selected = prioritized[:context.detail_budget]
        capped = len(prioritized) > context.detail_budget
        detail_attempted = 0
        detail_succeeded = 0
        for row in selected:
            raw_id = row.get('id')
            if not _valid_job_id(raw_id) or not ID_RE.fullmatch(str(raw_id)):
                continue
            detail_attempted += 1
            try:
                detail = fetch_json(f'{base}/{raw_id}', budget)
            except TransportError as error:
                if error.code == 'DEADLINE_EXCEEDED':
                    break  # the source deadline is spent; further attempts would only fail identically
                continue  # one posting's detail failure never voids the rest of the board
            if not _valid_detail(detail):
                continue
            row.update(detail)
            detail_succeeded += 1

        records, rejected = _to_records(rows, source_board)
        self._copy_budget(metrics, budget)
        metrics.detail_requests_attempted = detail_attempted
        metrics.detail_requests_succeeded = detail_succeeded
        metrics.records_received = len(rows)
        metrics.records_accepted = len(records)
        metrics.records_rejected = rejected
        metrics.content_cap_reached = capped
        metrics.elapsed_seconds = time.monotonic() - started
        incomplete = capped or detail_succeeded < len(selected)
        reason = (CompletionReason.DETAIL_BUDGET_EXHAUSTED.value if capped
                  else CompletionReason.DETAIL_FETCH_INCOMPLETE.value if incomplete else None)
        completion, health, error, reason = _outcome_for(rows, records, completion_reason=reason)
        return FetchBatch('greenhouse', source_board, completion, health, records, metrics,
                           error=error, completion_reason=reason)

    def _copy_budget(self, metrics, budget):
        metrics.requests_attempted = budget.requests_attempted
        metrics.requests_succeeded = budget.requests_succeeded
        metrics.retries = budget.retries
        metrics.encoded_bytes_read = budget.encoded_bytes_read
        metrics.decoded_bytes_read = budget.decoded_bytes_read
        metrics.errors_count = budget.errors_count

    def _failed(self, source_board, budget, metrics, started, error):
        self._copy_budget(metrics, budget)
        metrics.elapsed_seconds = time.monotonic() - started
        completion = FetchCompletion.CANCELLED if error.code == 'CANCELLED' else FetchCompletion.FAILED
        return FetchBatch('greenhouse', source_board, completion, _health_for(error), [], metrics,
                           error=ProviderError(error.code, str(error)),
                           completion_reason=CompletionReason.TRANSPORT_ERROR.value)

    def _malformed(self, source_board, budget, metrics, started, error):
        self._copy_budget(metrics, budget)
        metrics.elapsed_seconds = time.monotonic() - started
        return FetchBatch('greenhouse', source_board, FetchCompletion.FAILED, SourceHealth.MALFORMED, [], metrics,
                           error=ProviderError('MALFORMED_RESPONSE', str(error)),
                           completion_reason=CompletionReason.TRANSPORT_ERROR.value)
