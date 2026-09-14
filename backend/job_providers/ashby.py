"""Ashby job-provider (issue #39): fetches one employer board's public
postings and returns validated, provider-native ProviderRecords. Owns
Ashby's endpoint/schema rules only -- never ranking, eligibility, or
ASTRA's canonical job schema (issue #40).

Ashby's public `posting-api/job-board/{board}` endpoint returns every
listed posting in one response -- there is no pagination/cursor for this
endpoint (verified against Ashby's own public API documentation), unlike
Lever.

Identity (audit finding, issue #38 legacy code; canonicalization added in
the Codex remediation round, finding 6): Ashby's own public documentation
for this endpoint does not document or guarantee an `id` field on a
posting object at all -- the example response in
https://developers.ashbyhq.com/docs/public-job-posting-api has no `id`
field. In practice, real boards do return a stable-looking UUID `id`
(verified live against a real public board), so it is used as the
primary identity when present, but never assumed present the way legacy
`backend/adapters.py` did (`x['id']`, a hard KeyError on absence). When
`id` is missing or malformed, `jobUrl` -- which the documentation DOES
show -- is used as a documented, stable fallback identity instead of
inventing one from unstable text like the title. That fallback identity
is derived from a CANONICALIZED form of the URL (lowercased scheme/host,
path kept, query string and fragment stripped) so the same posting
reached through two different tracking query parameters or a fragment
never gets treated as two different jobs; the ORIGINAL, uncanonicalized
URL is still what is stored as source_url/apply_url for navigation and
provenance -- canonicalization only ever affects the derived identity,
never the link a user would actually follow.

jobUrl itself must always be valid (Codex remediation round 2, Blocker
A): a valid native `id` or a valid `applyUrl` never excuses or replaces
an invalid `jobUrl` -- the row is rejected outright if jobUrl fails
downstream URL validation (credentials embedded, unsupported scheme,
missing hostname, over the length limit), regardless of what else is
present. `source_url` is always the row's own (validated) jobUrl; it is
never silently substituted with `applyUrl`. `applyUrl` is a distinct
fact, validated separately, and only ever falls back to the
already-valid `source_url` when it is itself absent or invalid -- never
the other direction.

Workplace semantics (audit finding, issue #38 legacy code): legacy code
mapped every posting to 'Remote' if `isRemote` was true and 'On-site'
otherwise, silently collapsing Ashby's documented `workplaceType`
Hybrid value into On-site. This provider prefers the documented
`workplaceType` enum ('OnSite'/'Remote'/'Hybrid') when present, and
never infers On-site merely from `isRemote` being false or absent --
an unrecognized/missing workplaceType with no remote evidence stays
'UNKNOWN' rather than becoming a false On-site claim.

Source-deadline coverage over transformation (Codex remediation round,
finding 3): see backend/job_providers/lever.py's module docstring for
the full rationale -- the shared Budget bounds transport requests, but
per-record transformation is CPU work the transport layer never checks
against the deadline on its own. `_to_records` here checks the budget
before and after each record's transformation and once more after the
whole page is transformed, preserving already-built records as PARTIAL
rather than silently returning a late COMPLETE/HEALTHY.
"""
import re
import time
from datetime import datetime, timezone
from urllib.parse import urlsplit, urlunsplit

from .contracts import (
    CompletionReason, FetchBatch, FetchCompletion, FetchContext, Provider, ProviderCapabilities,
    ProviderError, ProviderRecord, SourceHealth, SourceMetrics, health_for_error_code,
    outcome_for, valid_downstream_url, VERSION as PROVIDER_VERSION,
)
from .transport import Budget, TransportError, fetch_json

BOARD_RE = re.compile(r'[a-zA-Z0-9_-]{1,100}')
WORKPLACE_TYPES = {'OnSite': 'On-site', 'Remote': 'Remote', 'Hybrid': 'Hybrid'}


def _health_for(error: TransportError) -> SourceHealth:
    return health_for_error_code(error.code)


def _validate_top_level(payload):
    if not isinstance(payload, dict) or not isinstance(payload.get('jobs'), list):
        raise ValueError('Expected a JSON object with a "jobs" list')
    return payload['jobs']


def _canonicalize_for_identity(url):
    """Deterministic provider-local identity from a documented, stable
    URL when no native id exists (Codex finding 6): lowercases the
    scheme and host, keeps the path, and strips the query string and
    fragment -- so tracking query params or a fragment never change the
    derived identity. Never touches the ORIGINAL url used for
    navigation/provenance; only the caller's separately-stored
    provider_job_id is affected.
    """
    parts = urlsplit(url)
    return urlunsplit((parts.scheme.lower(), parts.netloc.lower(), parts.path, '', ''))


def _identity(row, raw_fields, source_url):
    """Returns the provider_job_id given an already-validated `source_url`
    (see _to_record -- a row is rejected before this is ever called if
    its jobUrl is not itself valid, so `source_url` here is always a
    real, downstream-safe URL). A native `id` takes precedence; absent
    that, a deterministic canonicalized identity is derived from
    `source_url` -- never from unstable text (title/description).
    """
    raw_id = row.get('id')
    if isinstance(raw_id, str) and raw_id.strip():
        return raw_id.strip()
    raw_fields['identity_fallback'] = 'jobUrl'
    return _canonicalize_for_identity(source_url)


def _workplace_status(row):
    workplace_type = row.get('workplaceType')
    if workplace_type in WORKPLACE_TYPES:
        return WORKPLACE_TYPES[workplace_type]
    if row.get('isRemote') is True:
        return 'Remote'
    return 'UNKNOWN'


def _string_field(row, key, raw_fields):
    value = row.get(key)
    if value is None:
        return ''
    if isinstance(value, str):
        return value
    raw_fields[f'{key}_malformed'] = True
    return ''


def _to_record(row, source_board, retrieved_at):
    """Rejects (returns None for) any row missing a usable title, or
    whose jobUrl itself is not downstream-safe -- never coerces a
    malformed value into looking successful. Optional fields
    (timestamps, location) degrade gracefully instead of failing the
    whole record.

    Codex remediation round 2 (Blocker A): a valid native `id` or a
    valid `applyUrl` never excuses/replaces an invalid `jobUrl`. jobUrl
    IS source_url -- the row is rejected outright if it fails
    valid_downstream_url, rather than silently substituting applyUrl as
    the "original" posting URL.
    """
    if not isinstance(row, dict):
        return None
    title = row.get('title')
    if not isinstance(title, str) or not title.strip():
        return None
    job_url = row.get('jobUrl')
    if not valid_downstream_url(job_url):
        return None
    source_url = job_url
    raw_fields = {}
    provider_job_id = _identity(row, raw_fields, source_url)
    apply_url = row.get('applyUrl')
    apply_url = apply_url if valid_downstream_url(apply_url) else source_url
    location = row.get('location')
    location = location if isinstance(location, str) and location.strip() else 'UNKNOWN'
    description = _string_field(row, 'descriptionPlain', raw_fields)
    posted_at = _string_field(row, 'publishedAt', raw_fields)
    return ProviderRecord(
        provider='ashby', source_board=source_board, provider_job_id=provider_job_id,
        title=title, location=location, description=description,
        apply_url=apply_url, source_url=source_url, posted_at=posted_at, closing_at='',
        remote_status=_workplace_status(row), retrieved_at=retrieved_at, provider_version=PROVIDER_VERSION,
        raw_fields=raw_fields,
    )


def _filter_listed(rows):
    """Filters out explicitly-unlisted rows (`isListed: false`) before
    validation/counting -- these are a legitimate documented signal from
    the source that a posting should not be shown, not malformed data,
    so they are excluded the same way Greenhouse's API never returns a
    draft/closed posting at all, rather than counted as rejected.
    """
    return [r for r in rows if isinstance(r, dict) and r.get('isListed', True)]


def _to_records(listed, source_board, budget):
    """Transforms every listed row, bounded by `budget` (Codex finding
    3). Returns (records, rejected, deadline_error) -- deadline_error is
    None unless the budget expired during transformation, in which case
    whatever was already built is still returned rather than discarded.
    """
    records = []
    rejected = 0
    retrieved_at = datetime.now(timezone.utc).isoformat()
    for row in listed:
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


class AshbyProvider(Provider):
    def capabilities(self):
        return ProviderCapabilities(provider='ashby', supports_cursor=False, supports_detail_fetch=False)

    def fetch(self, context: FetchContext, source_board: str, cursor=None) -> FetchBatch:
        metrics = SourceMetrics()
        started = time.monotonic()
        if not source_board or not BOARD_RE.fullmatch(source_board):
            metrics.errors_count = 1
            metrics.elapsed_seconds = time.monotonic() - started
            return FetchBatch('ashby', source_board, FetchCompletion.FAILED, SourceHealth.MALFORMED, [], metrics,
                               error=ProviderError('INVALID_BOARD', 'Invalid board identifier'))
        budget = Budget(context.deadline_seconds)
        url = f'https://api.ashbyhq.com/posting-api/job-board/{source_board}?includeCompensation=false'
        try:
            payload = fetch_json(url, budget)
        except TransportError as error:
            return self._failed(source_board, budget, metrics, started, error)
        try:
            rows = _validate_top_level(payload)
        except ValueError as error:
            return self._malformed(source_board, budget, metrics, started, error)
        listed = _filter_listed(rows)
        records, rejected, deadline_error = _to_records(listed, source_board, budget)
        self._copy_budget(metrics, budget)
        metrics.records_received = len(listed)
        metrics.records_accepted = len(records)
        metrics.records_rejected = rejected
        metrics.errors_count = budget.errors_count + rejected
        metrics.elapsed_seconds = time.monotonic() - started
        if deadline_error is not None:
            if not records:
                return self._failed(source_board, budget, metrics, started, deadline_error)
            return FetchBatch('ashby', source_board, FetchCompletion.PARTIAL, SourceHealth.PARTIAL, records, metrics,
                               error=ProviderError(deadline_error.code, str(deadline_error)),
                               completion_reason=CompletionReason.TRANSPORT_ERROR.value)
        completion, health, error, reason = outcome_for(listed, records, rejected)
        return FetchBatch('ashby', source_board, completion, health, records, metrics,
                           error=error, completion_reason=reason)

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
        return FetchBatch('ashby', source_board, completion, _health_for(error), [], metrics,
                           error=ProviderError(error.code, str(error)),
                           completion_reason=CompletionReason.TRANSPORT_ERROR.value)

    def _malformed(self, source_board, budget, metrics, started, error):
        budget.errors_count += 1
        self._copy_budget(metrics, budget)
        metrics.elapsed_seconds = time.monotonic() - started
        return FetchBatch('ashby', source_board, FetchCompletion.FAILED, SourceHealth.MALFORMED, [], metrics,
                           error=ProviderError('INVALID_JSON', str(error)),
                           completion_reason=CompletionReason.TRANSPORT_ERROR.value)
