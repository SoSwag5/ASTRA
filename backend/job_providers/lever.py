"""Lever job-provider (issue #39): fetches one employer board's public
postings and returns validated, provider-native ProviderRecords. Owns
Lever's endpoint/schema/pagination rules only -- never ranking,
eligibility, or ASTRA's canonical job schema (issue #40).

Pagination (audit finding, issue #38 legacy code): Lever's own public API
documentation (github.com/lever/postings-api) documents `skip`/`limit` as
the supported pagination mechanism, but legacy `backend/adapters.py` made
exactly one unpaginated request and silently truncated any board with
more than one page of postings. This provider paginates, bounded on
every axis so a hostile or misbehaving board can never turn one source
into unbounded work:

- the shared per-fetch `Budget` deadline (already enforced by
  `transport.fetch_json` on every request) is the ultimate bound;
- LEVER_MAX_PAGES caps the number of list requests one fetch will make;
- LEVER_MAX_RECORDS caps total postings collected before stopping early;
- two consecutive pages returning the exact same set of posting ids (a
  misbehaving board that ignores `skip` and keeps returning the same
  page) stops pagination immediately rather than burning through the
  full page budget making no progress.

LEVER_PAGE_SIZE=100 keeps each page well under the transport's response
size cap even for verbose postings; LEVER_MAX_PAGES=10 combined with that
page size gives LEVER_MAX_RECORDS=1000 as the practical per-run ceiling,
matching the order of magnitude ASTRA's own planning already treats as a
reasonable bound for a single board/run. Reaching either cap ends
pagination and reports FetchCompletion.PARTIAL with an explicit
completion_reason -- never a silently truncated COMPLETE. A page that
fails after earlier pages already succeeded preserves those earlier
records as PARTIAL rather than discarding them.

createdAt (audit finding, issue #38 legacy code): confirmed against
Lever's own postings-api README schema table and
github.com/lever/postings-api/issues/35 that `createdAt` is NOT part of
Lever's documented posting schema, despite being present on real
responses. It is preserved as a best-effort `posted_at` observation when
present and parseable, with its uncertain provenance flagged in
`raw_fields` rather than presented as a guaranteed source fact; absence
is neutral (not an error), and a malformed value degrades to '' rather
than crashing or being invented from fetch time.
"""
import re
import time
from datetime import datetime, timezone
from urllib.parse import urlsplit

from .contracts import (
    CompletionReason, FetchBatch, FetchCompletion, FetchContext, Provider, ProviderCapabilities,
    ProviderError, ProviderRecord, SourceHealth, SourceMetrics, health_for_error_code,
    outcome_for, VERSION as PROVIDER_VERSION,
)
from .transport import Budget, TransportError, fetch_json

BOARD_RE = re.compile(r'[a-zA-Z0-9_-]{1,100}')
LEVER_PAGE_SIZE = 100
LEVER_MAX_PAGES = 10
LEVER_MAX_RECORDS = 1000


def _health_for(error: TransportError) -> SourceHealth:
    return health_for_error_code(error.code)


def _valid_url(value):
    if not isinstance(value, str) or not value.strip():
        return False
    try:
        parts = urlsplit(value)
    except ValueError:
        return False
    return parts.scheme in ('http', 'https') and bool(parts.hostname)


def _valid_job_id(raw_id):
    if isinstance(raw_id, bool):
        return False
    if isinstance(raw_id, str):
        return bool(raw_id.strip())
    return isinstance(raw_id, int)


def _location(row):
    categories = row.get('categories')
    if not isinstance(categories, dict):
        return 'UNKNOWN'
    all_locations = categories.get('allLocations')
    if isinstance(all_locations, list):
        names = [loc for loc in all_locations if isinstance(loc, str) and loc.strip()]
        if names:
            return ' / '.join(names)
    single = categories.get('location')
    return single if isinstance(single, str) and single.strip() else 'UNKNOWN'


def _description(row):
    parts = []
    base = row.get('description')
    if isinstance(base, str):
        parts.append(base)
    lists = row.get('lists')
    if isinstance(lists, list):
        for item in lists:
            if isinstance(item, dict) and isinstance(item.get('content'), str):
                parts.append(item['content'])
    from ..adapters import clean
    return clean(' '.join(parts))


def _posted_at(row, raw_fields):
    """Best-effort only -- createdAt is not part of Lever's documented
    schema (see module docstring). Absence is neutral; a malformed value
    never crashes and is never invented from fetch time.
    """
    value = row.get('createdAt')
    if value is None:
        return ''
    try:
        ms = float(value)
        if ms <= 0 or isinstance(value, bool):
            raise ValueError('non-positive or boolean createdAt')
        posted = datetime.fromtimestamp(ms / 1000, timezone.utc).isoformat()
    except (TypeError, ValueError, OSError, OverflowError):
        raw_fields['createdAt_malformed'] = True
        return ''
    raw_fields['posted_at_provenance'] = 'undocumented_createdAt_field'
    return posted


def _to_record(row, source_board, retrieved_at):
    if not isinstance(row, dict):
        return None
    raw_id = row.get('id')
    title = row.get('text')
    hosted_url = row.get('hostedUrl')
    if not _valid_job_id(raw_id):
        return None
    if not isinstance(title, str) or not title.strip():
        return None
    if not _valid_url(hosted_url):
        return None
    apply_url = row.get('applyUrl')
    apply_url = apply_url if _valid_url(apply_url) else hosted_url
    raw_fields = {}
    workplace_type = row.get('workplaceType')
    remote_status = workplace_type if isinstance(workplace_type, str) and workplace_type.strip() else 'UNKNOWN'
    return ProviderRecord(
        provider='lever', source_board=source_board, provider_job_id=str(raw_id),
        title=title, location=_location(row), description=_description(row),
        apply_url=apply_url, source_url=hosted_url, posted_at=_posted_at(row, raw_fields), closing_at='',
        remote_status=remote_status, retrieved_at=retrieved_at, provider_version=PROVIDER_VERSION,
        raw_fields=raw_fields,
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


class LeverProvider(Provider):
    def capabilities(self):
        return ProviderCapabilities(provider='lever', supports_cursor=True, supports_detail_fetch=False)

    def fetch(self, context: FetchContext, source_board: str, cursor=None) -> FetchBatch:
        metrics = SourceMetrics()
        started = time.monotonic()
        if not source_board or not BOARD_RE.fullmatch(source_board):
            metrics.errors_count = 1
            metrics.elapsed_seconds = time.monotonic() - started
            return FetchBatch('lever', source_board, FetchCompletion.FAILED, SourceHealth.MALFORMED, [], metrics,
                               error=ProviderError('INVALID_BOARD', 'Invalid board identifier'))
        budget = Budget(context.deadline_seconds)
        base = f'https://api.lever.co/v0/postings/{source_board}'
        try:
            rows, pause_reason, pause_error = self._fetch_pages(base, budget)
        except TransportError as error:
            return self._failed(source_board, budget, metrics, started, error)
        except ValueError as error:
            return self._malformed(source_board, budget, metrics, started, error)
        records, rejected = _to_records(rows, source_board)
        self._copy_budget(metrics, budget)
        metrics.records_received = len(rows)
        metrics.records_accepted = len(records)
        metrics.records_rejected = rejected
        metrics.errors_count = budget.errors_count + rejected
        metrics.content_cap_reached = pause_reason == CompletionReason.PAGINATION_LIMIT_REACHED.value
        metrics.elapsed_seconds = time.monotonic() - started
        completion, health, error, reason = outcome_for(rows, records, rejected, completion_reason=pause_reason)
        return FetchBatch('lever', source_board, completion, health, records, metrics,
                           error=error or pause_error, completion_reason=reason)

    def _fetch_pages(self, base, budget):
        """Bounded pagination loop. Returns (rows, pause_reason, pause_error).
        pause_reason/pause_error are both None when pagination reached a
        genuine last page (fewer than LEVER_PAGE_SIZE rows) on its own.
        Raises only when NO page has been fetched yet; once at least one
        page has succeeded, a later failure preserves what was already
        fetched (returned, never raised) instead of discarding it.
        """
        skip = 0
        rows = []
        pages = 0
        previous_ids = None
        while True:
            try:
                page = fetch_json(f'{base}?mode=json&skip={skip}&limit={LEVER_PAGE_SIZE}', budget)
            except TransportError as error:
                if not rows:
                    raise
                budget.record_error(error)
                return rows, CompletionReason.TRANSPORT_ERROR.value, ProviderError(error.code, str(error))
            if not isinstance(page, list):
                if not rows:
                    raise ValueError('Expected a JSON array of postings')
                return rows, CompletionReason.TRANSPORT_ERROR.value, ProviderError('INVALID_JSON', 'A later page was not a JSON array')
            current_ids = tuple(p.get('id') for p in page if isinstance(p, dict))
            if previous_ids is not None and current_ids and current_ids == previous_ids:
                # The board returned the same page again instead of
                # advancing past `skip` -- stop making no progress rather
                # than loop until LEVER_MAX_PAGES.
                return rows, CompletionReason.PAGINATION_LIMIT_REACHED.value, None
            rows.extend(page)
            pages += 1
            if len(page) < LEVER_PAGE_SIZE:
                return rows, None, None
            if pages >= LEVER_MAX_PAGES or len(rows) >= LEVER_MAX_RECORDS:
                return rows, CompletionReason.PAGINATION_LIMIT_REACHED.value, None
            previous_ids = current_ids
            skip += LEVER_PAGE_SIZE

    def _copy_budget(self, metrics, budget):
        metrics.requests_attempted = budget.requests_attempted
        metrics.requests_succeeded = budget.requests_succeeded
        metrics.retries = budget.retries
        metrics.encoded_bytes_read = budget.encoded_bytes_read
        metrics.decoded_bytes_read = budget.decoded_bytes_read
        metrics.errors_count = budget.errors_count

    def _failed(self, source_board, budget, metrics, started, error):
        budget.record_error(error)
        self._copy_budget(metrics, budget)
        metrics.elapsed_seconds = time.monotonic() - started
        completion = FetchCompletion.CANCELLED if error.code == 'CANCELLED' else FetchCompletion.FAILED
        return FetchBatch('lever', source_board, completion, _health_for(error), [], metrics,
                           error=ProviderError(error.code, str(error)),
                           completion_reason=CompletionReason.TRANSPORT_ERROR.value)

    def _malformed(self, source_board, budget, metrics, started, error):
        budget.errors_count += 1
        self._copy_budget(metrics, budget)
        metrics.elapsed_seconds = time.monotonic() - started
        return FetchBatch('lever', source_board, FetchCompletion.FAILED, SourceHealth.MALFORMED, [], metrics,
                           error=ProviderError('INVALID_JSON', str(error)),
                           completion_reason=CompletionReason.TRANSPORT_ERROR.value)
