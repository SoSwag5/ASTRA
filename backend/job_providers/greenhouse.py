"""Greenhouse job-provider (issue #38): fetches one employer board's public
postings and returns validated, provider-native ProviderRecords. Owns
Greenhouse's endpoint/schema knowledge only -- never ranking, eligibility,
or ASTRA's canonical job schema (issue #40).
"""
import re
import time
from datetime import datetime, timezone

from ..adapters import clean
from .contracts import (
    FetchBatch, FetchCompletion, FetchContext, Provider, ProviderCapabilities,
    ProviderError, ProviderRecord, SourceHealth, SourceMetrics, VERSION as PROVIDER_VERSION,
)
from .transport import Budget, TransportError, fetch_json

BOARD_RE = re.compile(r'[a-zA-Z0-9_-]{1,100}')
ID_RE = re.compile(r'\d+')
HYBRID_WORDS = ('hybrid', 'remote', 'distributed', 'in-office', 'on-site', 'onsite')
LOCATION_HINT_RE = re.compile(r'(?:Available Locations?|Work Location|Location)\s*:\s*([^\n]{1,220})', re.I)

_HEALTH_FOR_ERROR = {
    'DESTINATION_BLOCKED': SourceHealth.POLICY_BLOCKED,
    'DNS_RESOLUTION_FAILED': SourceHealth.UNAVAILABLE,
    'TIMEOUT': SourceHealth.UNAVAILABLE,
    'DEADLINE_EXCEEDED': SourceHealth.UNAVAILABLE,
    'RATE_LIMITED': SourceHealth.RATE_LIMITED,
    'UPSTREAM_UNAVAILABLE': SourceHealth.UNAVAILABLE,
    'UPSTREAM_ERROR': SourceHealth.UNAVAILABLE,
    'TOO_MANY_REDIRECTS': SourceHealth.UNAVAILABLE,
    'MALFORMED_RESPONSE': SourceHealth.MALFORMED,
    'UNEXPECTED_CONTENT_TYPE': SourceHealth.MALFORMED,
    'RESPONSE_TOO_LARGE': SourceHealth.PARTIAL,
}


def _health_for(error: TransportError) -> SourceHealth:
    return _HEALTH_FOR_ERROR.get(error.code, SourceHealth.UNAVAILABLE)


def _validate_top_level(payload):
    if not isinstance(payload, dict) or not isinstance(payload.get('jobs'), list):
        raise ValueError('Expected a JSON object with a "jobs" list')
    return payload['jobs']


def _to_record(row, source_board, retrieved_at):
    if not isinstance(row, dict):
        return None
    raw_id = row.get('id')
    title = row.get('title')
    url = row.get('absolute_url')
    location = row.get('location')
    if not isinstance(title, str) or not title.strip():
        return None
    if not isinstance(url, str) or not url.strip():
        return None
    if raw_id is None or isinstance(raw_id, bool):
        return None
    location_name = location.get('name', '') if isinstance(location, dict) else ''
    if not isinstance(location_name, str):
        location_name = ''
    content = row.get('content', '')
    description = clean(content if isinstance(content, str) else '')
    # Some boards put cities in the description while location says Hybrid.
    if location_name.lower() in HYBRID_WORDS:
        match = LOCATION_HINT_RE.search(description)
        if match:
            location_name = match[1].strip() + ' / ' + location_name
    posted_at = row.get('first_published')
    closing_at = row.get('application_deadline')
    return ProviderRecord(
        provider='greenhouse', source_board=source_board, provider_job_id=str(raw_id),
        title=title, location=location_name or 'UNKNOWN', description=description,
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
            metrics.requests = budget.requests
            metrics.elapsed_seconds = time.monotonic() - started
            return FetchBatch('greenhouse', source_board, FetchCompletion.FAILED, SourceHealth.MALFORMED, [], metrics,
                               error=ProviderError('MALFORMED_RESPONSE', str(error)))
        records, rejected = _to_records(rows, source_board)
        metrics.requests = budget.requests
        metrics.records_received = len(rows)
        metrics.records_accepted = len(records)
        metrics.records_rejected = rejected
        metrics.elapsed_seconds = time.monotonic() - started
        health = SourceHealth.EMPTY if not records else SourceHealth.HEALTHY
        return FetchBatch('greenhouse', source_board, FetchCompletion.COMPLETE, health, records, metrics)

    def _fetch_with_detail_fallback(self, context, source_board, base, budget, metrics, started):
        """The full content=true payload was too large; fetch the summary
        list instead, then spend a bounded detail-fetch budget on the
        items most likely to matter (context.title_hints, a plain keyword
        list -- never a ranking decision) before the rest. Every summary
        row is still returned; only description completeness for
        non-detailed rows is partial, reported truthfully as PARTIAL
        instead of being silently dropped or raised away.
        """
        try:
            payload = fetch_json(base, budget)
        except TransportError as error:
            return self._failed(source_board, budget, metrics, started, error)
        try:
            rows = _validate_top_level(payload)
        except ValueError as error:
            metrics.requests = budget.requests
            metrics.elapsed_seconds = time.monotonic() - started
            return FetchBatch('greenhouse', source_board, FetchCompletion.FAILED, SourceHealth.MALFORMED, [], metrics,
                               error=ProviderError('MALFORMED_RESPONSE', str(error)))

        hints = tuple(h.strip().lower() for h in context.title_hints if h.strip())

        def matches(row):
            title = str(row.get('title', '')).lower()
            return any(h in title for h in hints) if hints else True

        prioritized = [r for r in rows if isinstance(r, dict) and matches(r)] + \
                      [r for r in rows if isinstance(r, dict) and not matches(r)]
        selected = prioritized[:context.detail_budget]
        capped = len(prioritized) > context.detail_budget
        detailed = 0
        for row in selected:
            raw_id = row.get('id')
            if raw_id is None or not ID_RE.fullmatch(str(raw_id)):
                continue
            try:
                detail = fetch_json(f'{base}/{raw_id}', budget)
            except TransportError:
                # One posting's detail failure never voids the rest of the board.
                continue
            if isinstance(detail, dict):
                row.update(detail)
                detailed += 1

        records, rejected = _to_records(rows, source_board)
        metrics.requests = budget.requests
        metrics.retries = budget.retries
        metrics.bytes_read = budget.bytes_read
        metrics.detail_requests = detailed
        metrics.records_received = len(rows)
        metrics.records_accepted = len(records)
        metrics.records_rejected = rejected
        metrics.coverage_cap_reached = capped
        metrics.elapsed_seconds = time.monotonic() - started
        incomplete = capped or detailed < len(selected)
        completion = FetchCompletion.PARTIAL if incomplete else FetchCompletion.COMPLETE
        if not records:
            health = SourceHealth.EMPTY
        elif incomplete:
            health = SourceHealth.PARTIAL
        else:
            health = SourceHealth.HEALTHY
        return FetchBatch('greenhouse', source_board, completion, health, records, metrics)

    def _failed(self, source_board, budget, metrics, started, error):
        metrics.requests = budget.requests
        metrics.retries = budget.retries
        metrics.bytes_read = budget.bytes_read
        metrics.elapsed_seconds = time.monotonic() - started
        return FetchBatch('greenhouse', source_board, FetchCompletion.FAILED, _health_for(error), [], metrics,
                           error=ProviderError(error.code, str(error)))
