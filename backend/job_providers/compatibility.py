"""Narrow compatibility seam: new provider architecture -> existing ASTRA
discovery ingestion. This is deliberately NOT issue #40's canonical job
model -- it only reshapes a FetchBatch into the plain dict list
backend.adapters.discover() has always returned, so backend.main.py's
ingestion (backend.services.add_job) needs no change.
"""
from dataclasses import asdict

from .contracts import FetchCompletion


class ProviderItems(list):
    """A plain list of legacy-shaped job dicts (so every existing caller
    and test keeps working unchanged) that additionally carries `.health`
    -- truthful completion/metrics telemetry callers may read if they know
    to look, without changing the list's own public contract.
    """
    health = None


def _record_to_dict(record):
    return {
        'company': record.source_board,
        'title': record.title,
        'location': record.location,
        'job_url': record.apply_url,
        'description': record.description,
        'source': 'Greenhouse',
        'source_job_id': record.provider_job_id,
        'date_posted': record.posted_at,
        'closing_date': record.closing_at,
    }


def to_legacy_items(batch):
    """Translate a FetchBatch into the existing discover()-shaped list.

    Raises ValueError on FAILED/CANCELLED, matching discover()'s existing
    contract (backend.main.py's per-source try/except already treats a
    raised exception as that source's failure) -- callers that want the
    richer truthful completion/metrics data read it from the returned
    list's `.health` attribute instead of only inferring success from "did
    not raise".
    """
    items = ProviderItems(_record_to_dict(r) for r in batch.records)
    items.health = {
        'completion': batch.completion.value,
        'health': batch.health.value,
        'metrics': asdict(batch.metrics),
        'error': {'code': batch.error.code, 'message': batch.error.message} if batch.error else None,
    }
    if batch.completion in (FetchCompletion.FAILED, FetchCompletion.CANCELLED):
        message = batch.error.message if batch.error else 'Provider fetch failed'
        raise ValueError(message)
    return items
