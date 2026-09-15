"""Narrow compatibility seam: new provider architecture -> existing ASTRA
discovery ingestion. This is deliberately NOT issue #40's canonical job
model -- it only reshapes a FetchBatch into the plain dict list
backend.adapters.discover() has always returned, so backend.main.py's
ingestion (backend.services.add_job) needs no change.
"""
from dataclasses import asdict

from .contracts import FetchCompletion, ProviderFetchFailed

# Provider-native identity -> the legacy display string backend.adapters.discover()
# has always returned in the 'source' field (issue #39: this was hardcoded to
# 'Greenhouse' when that was the only migrated provider; now that Lever/Ashby
# share this seam too, each provider must report its own true source).
_DISPLAY_NAME = {
    'greenhouse': 'Greenhouse',
    'lever': 'Lever',
    'ashby': 'Ashby',
}


class ProviderItems(list):
    """A plain list of legacy-shaped job dicts (so every existing caller
    and test keeps working unchanged) that additionally carries `.health`
    -- truthful completion/metrics telemetry callers may read if they know
    to look, without changing the list's own public contract.
    """
    health = None


class LegacyJobDict(dict):
    """Exactly a plain dict as far as equality/iteration/serialization is
    concerned (dict.__eq__ only ever compares items, never subclass
    identity or extra attributes) -- every existing caller/test that treats
    a discover() item as a plain dict keeps working unchanged. Additionally
    carries the source ProviderRecord (issue #40) so backend.services.
    add_job() can build a full-provenance JobObservation instead of the
    field-poor legacy ingestion dict alone, WITHOUT widening this seam's
    own dict shape. `item['company']=source.name` (backend/main.py's
    discover loop) still works exactly as before -- only the extra
    `.provider_record` attribute is new.
    """
    def __init__(self, data, record):
        super().__init__(data)
        self.provider_record = record


def _record_to_dict(record):
    return {
        'company': record.source_board,
        'title': record.title,
        'location': record.location,
        # Codex remediation round, finding 4: legacy discover() always
        # returned the ORIGINAL/canonical posting URL in job_url (Lever's
        # hostedUrl, Ashby's jobUrl), not an application URL. This seam
        # briefly mapped job_url from apply_url instead, which changed
        # "open original posting" / canonical-URL / export / domain-policy
        # behavior for Lever and Ashby. apply_url remains available on
        # the provider-native record for #40 to model separately; legacy
        # job_url stays source_url, matching pre-#39 behavior exactly for
        # every provider (Greenhouse already set apply_url == source_url,
        # so this is a no-op for it).
        'job_url': record.source_url,
        'description': record.description,
        'source': _DISPLAY_NAME.get(record.provider, record.provider.capitalize()),
        'source_job_id': record.provider_job_id,
        'date_posted': record.posted_at,
        'closing_date': record.closing_at,
        # issue #39: previously missing here entirely, which was invisible
        # for Greenhouse (always 'UNKNOWN') but silently dropped Lever's
        # and Ashby's real remote/workplace data once they routed through
        # this same seam -- backend.services.add_job() only keeps columns
        # present in the dict, so an absent key defaults to the Job
        # model's own 'UNKNOWN', not the provider's actual value.
        'remote_status': record.remote_status,
    }


def to_legacy_items(batch):
    """Translate a FetchBatch into the existing discover()-shaped list.

    Raises ProviderFetchFailed (a ValueError subclass, so it matches
    discover()'s existing exception-on-failure contract for callers that
    only check "did this raise") on FAILED/CANCELLED -- but unlike a plain
    ValueError, it carries the batch's own truthful `completion`/`health`
    so backend.main.py's per-source exception handler can report what
    actually happened instead of falling back to a stale or default
    'COMPLETE' value.
    """
    items = ProviderItems(LegacyJobDict(_record_to_dict(r), r) for r in batch.records)
    items.health = {
        'completion': batch.completion.value,
        'health': batch.health.value,
        'completion_reason': batch.completion_reason,
        'metrics': asdict(batch.metrics),
        'error': {'code': batch.error.code, 'message': batch.error.message} if batch.error else None,
    }
    if batch.completion in (FetchCompletion.FAILED, FetchCompletion.CANCELLED):
        message = batch.error.message if batch.error else 'Provider fetch failed'
        raise ProviderFetchFailed(message, batch.completion, batch.health,
                                   completion_reason=batch.completion_reason,
                                   error_code=batch.error.code if batch.error else None,
                                   metrics=items.health['metrics'])
    return items
