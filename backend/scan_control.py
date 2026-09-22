"""Manual-only scan control.

Discovery never starts on its own: not when Windows starts, not when the
server starts, not on a timer, not as a catch-up and not as a resume after a
restart. The only way to start it is this two-step flow:

1. ``POST /api/scan/preview`` resolves the scope (which enabled sources, which
   roles, which locations) and an estimated workload from local history, and
   returns a single-use confirmation token. Nothing is fetched.
2. ``POST /api/scan/start`` with that token starts exactly one run in a
   background thread. The token is consumed, so a repeated or double click
   cannot start a second run.

``POST /api/scan/cancel`` asks the running scan to stop; it is honoured before
each source fetch, so no further source is fetched after a stop request.
Tokens live in memory only, so a restart invalidates every pending
confirmation: a page left open across a restart cannot start a scan without a
fresh preview.
"""
import secrets
import statistics
import threading
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select

from .models import AutomationRun, JobSource, Session, now, settings

router = APIRouter(prefix='/api/scan')

PREVIEW_TTL = timedelta(minutes=10)
MAX_PENDING_PREVIEWS = 20
TRIGGER = 'MANUAL_START'

_guard = threading.Lock()
_previews = {}      # token -> {'scope': dict, 'expires': datetime, 'run_id': int|None}
_cancel = {}        # run_id -> threading.Event for scans started in this process


class PreviewRequest(BaseModel):
    model_config = ConfigDict(extra='forbid')
    source_id: int | None = Field(default=None, ge=1)


class StartRequest(BaseModel):
    model_config = ConfigDict(extra='forbid')
    token: str = Field(min_length=16, max_length=200)


class CancelRequest(BaseModel):
    model_config = ConfigDict(extra='forbid')
    run_id: int = Field(ge=1)


def _utc():
    return datetime.now(timezone.utc)


def _prune(at):
    for token in [t for t, p in _previews.items() if p['expires'] < at]:
        del _previews[token]
    while len(_previews) > MAX_PENDING_PREVIEWS:
        _previews.pop(next(iter(_previews)))


def _active_run(db):
    return db.scalar(select(AutomationRun)
                     .where(AutomationRun.task == 'discover', AutomationRun.status == 'RUNNING')
                     .order_by(AutomationRun.id.desc()))


def _estimate(db, sources):
    """Workload from this installation's own history; UNKNOWN where none."""
    runs = list(db.scalars(select(AutomationRun)
                           .where(AutomationRun.task == 'discover',
                                  AutomationRun.status.in_(['COMPLETED', 'PARTIAL']))
                           .order_by(AutomationRun.id.desc()).limit(20)))
    per_source = [r.report['duration_seconds'] / r.report['sources_attempted'] for r in runs
                  if (r.report or {}).get('sources_attempted') and
                  isinstance(r.report.get('duration_seconds'), (int, float))]
    known = [s for s in sources if isinstance(s.details.get('jobs_fetched'), int)]
    seconds = round(statistics.median(per_source) * len(sources)) if per_source and sources else None
    return {
        'sources': len(sources),
        'postings_last_seen': sum(s.details['jobs_fetched'] for s in known) if known else None,
        'sources_without_history': len(sources) - len(known),
        'estimated_seconds': seconds,
        'estimate_basis': ('median seconds per source over the last %d finished scans' % len(per_source)
                           if per_source else 'no finished scan on this installation yet'),
        'requests': ('At least one public request per source. SmartRecruiters sources also make one '
                     'request per UAE posting, and Greenhouse sources may fetch posting details, '
                     'each within its existing per-source budget. Nothing is submitted anywhere.'),
    }


def _scope(db, source_id):
    cfg = settings(db)
    query = select(JobSource).where(JobSource.enabled == True, JobSource.adapter != 'manual')  # noqa: E712
    if source_id is not None:
        query = query.where(JobSource.id == source_id)
    sources = list(db.scalars(query.order_by(JobSource.name)))
    if not sources:
        raise ValueError('Enable this source before scanning' if source_id is not None
                         else 'Add and enable a source first')
    scope = {
        'source_ids': [s.id for s in sources],
        'sources': [{'id': s.id, 'name': s.name, 'adapter': s.adapter,
                     'last_scan': s.details.get('last_success'),
                     'postings_last_seen': s.details.get('jobs_fetched')} for s in sources],
        'career_tracks': list(cfg.get('career_tracks', [])),
        'target_roles': len(cfg.get('target_roles', [])) + len(cfg.get('custom_target_roles', [])),
        'locations': list(cfg.get('locations', [])),
        'single_source': source_id is not None,
    }
    return scope, _estimate(db, sources)


def _busy(run):
    return JSONResponse({'detail': 'A scan is already running. Stop it or wait for it to finish.',
                         'busy': True, 'run_id': run.id if run else None}, 409)


@router.post('/preview')
def preview(data: PreviewRequest):
    """Resolve scope and workload. Fetches nothing and starts nothing."""
    with Session() as db:
        running = _active_run(db)
        if running is not None:
            return _busy(running)
        scope, workload = _scope(db, data.source_id)
    token = secrets.token_urlsafe(32)
    expires = _utc() + PREVIEW_TTL
    with _guard:
        _prune(_utc())
        _previews[token] = {'scope': scope, 'expires': expires, 'run_id': None}
    return {'token': token, 'expires_at': expires.isoformat(), 'manual_only': True,
            'scope': scope, 'workload': workload}


def _run(run_id, source_ids, event):
    from .main import task
    try:
        task('discover', trigger=TRIGGER, run_id=run_id, cancel=event, lock_held=True,
             source_ids=set(source_ids))
    finally:
        with _guard:
            _cancel.pop(run_id, None)


@router.post('/start')
def start(data: StartRequest):
    """Start exactly one scan for one confirmed preview."""
    from .main import task_lock
    with _guard:
        _prune(_utc())
        pending = _previews.get(data.token)
        if pending is None:
            return JSONResponse({'detail': 'This scan preview has expired or is unknown. '
                                           'Review the scope again before starting.'}, 409)
        if pending['run_id'] is not None:
            return JSONResponse({'detail': 'This scan was already started.',
                                 'already_started': True, 'run_id': pending['run_id']}, 409)
        if not task_lock.acquire(False):
            with Session() as db:
                return _busy(_active_run(db))
        try:
            scope = pending['scope']
            with Session.begin() as db:
                run = AutomationRun(task='discover', status='RUNNING', report={
                    'trigger': TRIGGER, 'started_at': now(),
                    'scope': {k: scope[k] for k in ('source_ids', 'career_tracks', 'target_roles',
                                                    'locations', 'single_source')},
                    'progress': {'sources_total': len(scope['source_ids']), 'sources_done': 0,
                                 'current_source': None, 'postings_seen': 0}})
                db.add(run)
                db.flush()
                run_id = run.id
            pending['run_id'] = run_id
            event = threading.Event()
            _cancel[run_id] = event
            threading.Thread(target=_run, args=(run_id, scope['source_ids'], event),
                             name='astra-manual-scan-%d' % run_id, daemon=True).start()
        except Exception:
            task_lock.release()
            raise
    return {'started': True, 'run_id': run_id}


@router.post('/cancel')
def cancel(data: CancelRequest):
    """Stop the running scan before its next source fetch."""
    with _guard:
        event = _cancel.get(data.run_id)
    if event is None:
        return JSONResponse({'detail': 'There is no running scan with that id in this session.'}, 409)
    event.set()
    with Session.begin() as db:
        run = db.get(AutomationRun, data.run_id)
        if run is not None and not (run.report or {}).get('cancel_requested_at'):
            run.report = {**(run.report or {}), 'cancel_requested_at': now()}
    return {'cancelling': True, 'run_id': data.run_id}


def _view(run):
    report = run.report or {}
    return {'id': run.id, 'status': run.status, 'created_at': run.created_at,
            'updated_at': run.updated_at, 'trigger': report.get('trigger'),
            'progress': report.get('progress'), 'scope': report.get('scope'),
            'cancel_requested_at': report.get('cancel_requested_at'),
            'cancelled': report.get('cancelled'), 'error': report.get('error'),
            'discovered': report.get('discovered'), 'duplicates': report.get('duplicates'),
            'failures': report.get('failures')}


@router.get('/status')
def status():
    with Session() as db:
        running = _active_run(db)
        last = db.scalar(select(AutomationRun)
                         .where(AutomationRun.task == 'discover', AutomationRun.status != 'RUNNING')
                         .order_by(AutomationRun.id.desc()))
        with _guard:
            cancellable = running is not None and running.id in _cancel
        return {'manual_only': True, 'active': _view(running) if running else None,
                'cancellable': cancellable, 'last': _view(last) if last else None}
