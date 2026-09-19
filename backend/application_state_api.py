"""Bounded local API for canonical application state and reconciliation (#46).

Every route is mounted on the same FastAPI app as the rest of ASTRA's private
API and therefore inherits the existing boundary controls unchanged
(`backend/main.py::guard`): loopback-only peers, the TrustedHost allowlist,
the Origin allowlist, `Sec-Fetch-Site: cross-site` rejection, the
`Sec-Fetch-Dest` browser-navigation block, the optional access-key session,
the bounded request size, the mutation lock on non-GET requests,
`ASTRA_DEMO_ONLY` denial and `Cache-Control: no-store`. No control is
weakened or bypassed for this router.

Scope rules, matching #46's explicit non-goal of having no UI:

* Reads expose exactly what #47 will need: the canonical state, the
  append-only history, reconciliation decisions and the Needs Review queue.
* The only writes are the user's own confirm/reject of a review item, which
  the backend workflow cannot be completed without.
* There is no route that sets a state directly. Canonical state changes
  arrive through the existing job/campaign paths or through reconciliation,
  all of which funnel into `application_state.assert_state()`.
* Path and query inputs are integers with explicit bounds; every response
  field is a bounded token, an identifier or a timestamp.
"""
from fastapi import APIRouter, HTTPException, Query

from . import application_reconciliation as reconciliation
from . import application_state as states

router = APIRouter(prefix='/api/applications')

MAX_APPLICATION_ID = 2_147_483_647


def _identifier(value):
    if not isinstance(value, int) or value <= 0 or value > MAX_APPLICATION_ID:
        raise HTTPException(404)
    return value


@router.get('/state/summary')
def summary():
    """Counts per canonical state, plus the declared transition table."""
    return states.state_summary()


@router.get('/state/reconciliation')
def reconciliation_status():
    """Fixed reconciliation parameters and decision counts."""
    return reconciliation.reconciliation_status()


@router.get('/state/needs-review')
def review_queue(limit: int = Query(default=50, ge=1, le=200)):
    """Reconciliation decisions awaiting the user's confirmation."""
    return reconciliation.needs_review(limit=limit)


@router.get('/{application_id}/state')
def application_state(application_id: int):
    """Canonical state, append-only history and the legacy compatibility view."""
    result = states.state_of(_identifier(application_id))
    if result is None:
        raise HTTPException(404)
    return result


@router.get('/{application_id}/state/history')
def application_history(application_id: int,
                        limit: int = Query(default=200, ge=1, le=200)):
    """The append-only transition history for one application."""
    return {'application_id': _identifier(application_id),
            'history': states.transition_history(application_id, limit=limit)}


@router.post('/state/reconcile')
def reconcile(data: dict = None):
    """Explicitly reconcile Gmail evidence that has no decision yet.

    Coordinates with discovery, export, deletion and Gmail sync through the
    existing cross-process task lock, so reconciliation cannot interleave
    with a deletion or an export half-way through.
    """
    from .main import task_lock
    requested = (data or {}).get('limit', reconciliation.MAX_RUN_EVIDENCE)
    if not isinstance(requested, int) or not 1 <= requested <= reconciliation.MAX_RUN_EVIDENCE:
        raise ValueError('Choose a reconciliation batch size from 1 to '
                         f'{reconciliation.MAX_RUN_EVIDENCE}')
    if not task_lock.acquire(False):
        raise HTTPException(409, 'Wait for the current scan or task to finish')
    try:
        return reconciliation.reconcile_pending(limit=requested)
    finally:
        task_lock.release()


@router.post('/state/needs-review/{link_id}/confirm')
def confirm(link_id: int, data: dict = None):
    """Confirm a review item as the user's own assertion."""
    chosen = (data or {}).get('application_id')
    if chosen is not None:
        chosen = _identifier(chosen)
    return reconciliation.confirm_review(_identifier(link_id),
                                         application_id=chosen)


@router.post('/state/needs-review/{link_id}/reject')
def reject(link_id: int):
    """Reject a review item. Never changes application state."""
    return reconciliation.reject_review(_identifier(link_id))
