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
into unbounded work (Codex remediation round, finding 2):

- the shared per-fetch `Budget` deadline (already enforced by
  `transport.fetch_json` on every request) is the ultimate bound;
- LEVER_MAX_PAGES caps the number of list requests one fetch will make;
- LEVER_MAX_RECORDS is enforced BEFORE a page's rows are added to the
  result, not after -- a page that returns more rows than the remaining
  capacity (e.g. a board that ignores `limit` entirely) is truncated to
  exactly that remaining capacity, never accepted in full and trimmed
  later;
- posting identity is tracked in a single set across ALL pages, not just
  the immediately previous one, so a repeated page anywhere in the
  sequence (an exact repeat, a non-consecutive cycle like A -> B -> A, or
  a page that is a pure subset of previously-seen postings) is detected
  the moment it produces zero new identities, rather than only catching
  the narrower case of two *consecutive* identical pages.

LEVER_PAGE_SIZE=100 keeps each page well under the transport's response
size cap even for verbose postings; LEVER_MAX_PAGES=10 combined with that
page size gives LEVER_MAX_RECORDS=1000 as the practical per-run ceiling,
matching the order of magnitude ASTRA's own planning already treats as a
reasonable bound for a single board/run. Reaching either cap ends
pagination and reports FetchCompletion.PARTIAL with an explicit
completion_reason -- never a silently truncated COMPLETE. A page that
fails after earlier pages already succeeded preserves those earlier
records as PARTIAL rather than discarding them.

createdAt (audit finding, issue #38 legacy code; Codex remediation round,
finding 5): confirmed against Lever's own postings-api README schema
table and github.com/lever/postings-api/issues/35 that `createdAt` is NOT
part of Lever's documented posting schema, despite being present on real
responses. The Owner decision for #39 is that this MUST NOT be promoted
to the authoritative legacy `date_posted` field a downstream freshness/
staleness decision would otherwise trust as a source fact: `posted_at`
therefore always stays '' for Lever. A present, parseable value is kept
only as a labelled best-effort OBSERVATION in `raw_fields`
('createdAt_observed'), never in the authoritative field; absence is
neutral, and a malformed value is flagged and otherwise ignored --
never crashing, never fabricated from fetch time, never promoted.

Source-deadline coverage over transformation (Codex remediation round,
finding 3): the shared Budget bounds transport requests already, but a
per-record transformation step (here, HTML description cleaning) is CPU
work `transport.fetch_json` never sees and previously was not checked
against the deadline at all -- a fetch could return COMPLETE/HEALTHY
after the configured deadline had already passed if enough per-record
transformation time was spent between the last network read and the
final result. `_to_records` now checks the budget before and after each
record's transformation and once more after the whole page is
transformed; hitting the deadline preserves whatever records were
already built (PARTIAL) rather than silently returning success late, and
returns FAILED only if nothing had been built yet.
"""
import re
import time
from datetime import datetime, timezone

from .contracts import (
    CompletionReason, FetchBatch, FetchCompletion, FetchContext, Provider, ProviderCapabilities,
    ProviderError, ProviderRecord, SourceHealth, SourceMetrics, health_for_error_code,
    outcome_for, valid_downstream_url, VERSION as PROVIDER_VERSION,
)
from .transport import Budget, TransportError, fetch_json

BOARD_RE = re.compile(r'[a-zA-Z0-9_-]{1,100}')
LEVER_PAGE_SIZE = 100
LEVER_MAX_PAGES = 10
LEVER_MAX_RECORDS = 1000


def _health_for(error: TransportError) -> SourceHealth:
    return health_for_error_code(error.code)


def _normalize_id(raw_id):
    """Single normalization point for Lever's provider-native id (Codex
    remediation round 2, Blocker B): the exact same normalized value
    must be used for pagination dedup/cycle detection AND for the final
    ProviderRecord.provider_job_id, or two representations Lever's own
    API could return for what is really the same posting -- e.g. the
    integer 1 and the string '1' -- pass dedup as if they were distinct
    (int 1 != str '1' as raw values / set members) yet collide once
    both are stringified for the final record, breaking provider-local
    uniqueness. Returns None for anything that is not a valid scalar
    Lever id (a non-empty stripped string, or a non-bool int) -- never
    a composite/list/dict value, and never unsafely coerced.
    """
    if isinstance(raw_id, bool):
        return None
    if isinstance(raw_id, str):
        stripped = raw_id.strip()
        return stripped or None
    if isinstance(raw_id, int):
        return str(raw_id)
    return None


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


def _observe_created_at(row, raw_fields):
    """Records createdAt as a labelled, best-effort OBSERVATION only --
    never the authoritative `posted_at` (see module docstring, Codex
    finding 5). Absence is neutral; a malformed value is flagged and
    otherwise ignored -- never crashes, never fabricated from fetch time.
    """
    value = row.get('createdAt')
    if value is None:
        return
    try:
        ms = float(value)
        if ms <= 0 or isinstance(value, bool):
            raise ValueError('non-positive or boolean createdAt')
        observed = datetime.fromtimestamp(ms / 1000, timezone.utc).isoformat()
    except (TypeError, ValueError, OSError, OverflowError):
        raw_fields['createdAt_malformed'] = True
        return
    raw_fields['createdAt_observed'] = observed
    raw_fields['posted_at_provenance'] = 'undocumented_createdAt_field_not_promoted_to_date_posted'


def _to_record(row, source_board, retrieved_at):
    if not isinstance(row, dict):
        return None
    normalized_id = _normalize_id(row.get('id'))
    title = row.get('text')
    hosted_url = row.get('hostedUrl')
    if normalized_id is None:
        return None
    if not isinstance(title, str) or not title.strip():
        return None
    if not valid_downstream_url(hosted_url):
        return None
    apply_url = row.get('applyUrl')
    apply_url = apply_url if valid_downstream_url(apply_url) else hosted_url
    raw_fields = {}
    _observe_created_at(row, raw_fields)
    workplace_type = row.get('workplaceType')
    remote_status = workplace_type if isinstance(workplace_type, str) and workplace_type.strip() else 'UNKNOWN'
    return ProviderRecord(
        # posted_at is intentionally always '' for Lever -- see
        # _observe_created_at and the module docstring (Codex finding 5).
        provider='lever', source_board=source_board, provider_job_id=normalized_id,
        title=title, location=_location(row), description=_description(row),
        apply_url=apply_url, source_url=hosted_url, posted_at='', closing_at='',
        remote_status=remote_status, retrieved_at=retrieved_at, provider_version=PROVIDER_VERSION,
        raw_fields=raw_fields,
    )


def _to_records(rows, source_board, budget):
    """Transforms every row, bounded by `budget` (Codex finding 3): a
    per-record transformation step is CPU work the transport layer never
    sees, so it must be checked against the deadline itself. Returns
    (records, rejected, deadline_error) -- deadline_error is None unless
    the budget expired during transformation, in which case whatever was
    already built is still returned rather than discarded.
    """
    records = []
    rejected = 0
    retrieved_at = datetime.now(timezone.utc).isoformat()
    for row in rows:
        try:
            budget.check()
            record = _to_record(row, source_board, retrieved_at)
            budget.check()
        except TransportError as error:
            return records, rejected, error
        if record is None:
            rejected += 1
        else:
            records.append(record)
    try:
        budget.check()
    except TransportError as error:
        return records, rejected, error
    return records, rejected, None


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
        records, rejected, deadline_error = _to_records(rows, source_board, budget)
        self._copy_budget(metrics, budget)
        metrics.records_received = len(rows)
        metrics.records_accepted = len(records)
        metrics.records_rejected = rejected
        metrics.errors_count = budget.errors_count + rejected
        metrics.content_cap_reached = pause_reason == CompletionReason.PAGINATION_LIMIT_REACHED.value
        metrics.elapsed_seconds = time.monotonic() - started
        if deadline_error is not None:
            if not records:
                return self._failed(source_board, budget, metrics, started, deadline_error)
            return FetchBatch('lever', source_board, FetchCompletion.PARTIAL, SourceHealth.PARTIAL, records, metrics,
                               error=ProviderError(deadline_error.code, str(deadline_error)),
                               completion_reason=CompletionReason.TRANSPORT_ERROR.value)
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

        `seen_ids` tracks every valid posting id seen across ALL pages
        (Codex finding 2), not just the immediately previous page, so a
        non-consecutive repeat (A -> B -> A) or a page that is a pure
        subset of earlier pages is caught the moment it adds nothing new
        -- not only an exact repeat of the last page. A row without a
        valid id is never deduplicated against (there is nothing
        meaningful to compare); it is left for the normal per-row
        validation in _to_record to reject.

        LEVER_MAX_RECORDS is enforced by truncating a page's NEW rows to
        the remaining capacity BEFORE they are added to `rows` (Codex
        finding 1: previously rows were extended first and only checked
        afterward, so a board that ignored `limit` and returned more
        than the remaining capacity in one response was accepted in full).
        """
        skip = 0
        rows = []
        seen_ids = set()
        pages = 0
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
            pages += 1
            page_len = len(page)
            new_rows = []
            for item in page:
                raw_ident = item.get('id') if isinstance(item, dict) else None
                # Codex remediation round 2 (Blocker B): dedup on the SAME
                # normalized id that will become provider_job_id, never on
                # the raw value -- otherwise integer 1 and string '1' pass
                # this check as if distinct, yet collide once _to_record
                # stringifies both, breaking provider-local uniqueness.
                normalized = _normalize_id(raw_ident)
                if normalized is not None:
                    if normalized in seen_ids:
                        continue
                    seen_ids.add(normalized)
                new_rows.append(item)
            if not new_rows:
                # Every identifiable posting in this page has already
                # been seen -- an exact repeat, a non-consecutive cycle,
                # or a page composed entirely of earlier postings. No
                # further progress is possible; stop rather than keep
                # paging up to LEVER_MAX_PAGES making no progress.
                return rows, CompletionReason.PAGINATION_LIMIT_REACHED.value, None
            remaining_capacity = LEVER_MAX_RECORDS - len(rows)
            if len(new_rows) > remaining_capacity:
                rows.extend(new_rows[:remaining_capacity])
                return rows, CompletionReason.PAGINATION_LIMIT_REACHED.value, None
            rows.extend(new_rows)
            if page_len < LEVER_PAGE_SIZE:
                return rows, None, None
            if pages >= LEVER_MAX_PAGES or len(rows) >= LEVER_MAX_RECORDS:
                return rows, CompletionReason.PAGINATION_LIMIT_REACHED.value, None
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
