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

``POST /api/scan/cancel`` asks the running scan to stop. Stop and each
source's admission to its provider are ordered under one lock: a source not
yet admitted when Stop is accepted is never fetched, and the source already
admitted finishes within its bounded provider budget and is named in the Stop
response and the final report. Once the last source is done, Stop is refused,
so an accepted Stop always ends the run CANCELLED.
Tokens live in memory only, so a restart invalidates every pending
confirmation: a page left open across a restart cannot start a scan without a
fresh preview.

The scope a preview DISPLAYS and the scope its token BINDS are built from one
read of sources and settings inside a single SQLite read transaction, so a
concurrent edit can never make the page show one scope while the token holds
another.

``confirm()`` turns a valid token into a ``ScanConfirmation``: the only object
``main.task('discover')`` accepts. It is single use, carries the confirmed
source ids, their definitions and the settings, and only this module can
create one.
"""
import hashlib
import json
import secrets
import statistics
import threading
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

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
# Serialize writes to the active run's report with progress/finalization in
# main.py. A read-refresh-write sequence alone can overwrite a Stop recorded
# by another request between the refresh and commit. It also orders Stop
# against provider admission (ScanStop).
_report_guard = threading.Lock()
_previews = {}      # token -> {'scope': dict, 'expires': datetime, 'run_id': int|None}
_cancel = {}        # run_id -> ScanStop for scans started in this process


class ScanStop:
    """Stop for one scan, ordered against each source's provider entry.

    ``admit()`` (the worker's last step before calling a provider) and Stop
    acceptance (``cancel()``) both hold ``_report_guard``. So a Stop is
    accepted either before a source's admission, and that source is never
    fetched, or after it, and Stop names that source as in flight. There is no
    window in which a Stop is accepted after the check has passed but the
    source still counts as not started. ``close()`` ends admission when the
    last source is done; a later Stop is refused, so the final status cannot
    disagree with an accepted Stop.

    A caller of ``admit()``, ``done()`` or ``close()`` must hold no database
    write transaction, because ``cancel()`` writes the run while holding the
    same lock.
    """

    def __init__(self):
        self._event = threading.Event()
        self.in_flight = None           # {'id', 'name'} from admission until the source is accounted for
        self.in_flight_at_stop = None   # the source in flight when Stop was accepted, if any
        self.closed = False

    def is_set(self):
        """Whether Stop was accepted. An early, unordered skip only: admit() decides."""
        return self._event.is_set()

    def admit(self, source_id, name):
        """The provider-entry checkpoint. True admits this source to its provider."""
        with _report_guard:
            if self.closed or self._event.is_set():
                return False
            self.in_flight = {'id': source_id, 'name': name}
            return True

    def done(self):
        """The admitted source is accounted for."""
        with _report_guard:
            self.in_flight = None

    def close(self):
        """Admit nothing more and refuse any later Stop. True if a Stop was accepted."""
        with _report_guard:
            self.closed = True
            self.in_flight = None
            return self._event.is_set()

    def _accept(self):
        """Record the Stop. The caller holds _report_guard and has committed cancel_requested_at."""
        if not self._event.is_set():
            self.in_flight_at_stop = self.in_flight
            self._event.set()


class PreviewRequest(BaseModel):
    model_config = ConfigDict(extra='forbid')
    source_id: int | None = Field(default=None, ge=1)


class StartRequest(BaseModel):
    model_config = ConfigDict(extra='forbid')
    token: str = Field(min_length=16, max_length=200)


class CancelRequest(BaseModel):
    model_config = ConfigDict(extra='forbid')
    run_id: int = Field(ge=1)


def source_definition(source):
    """What a source IS, for scope binding. Excludes run bookkeeping
    (details, timestamps) that every scan itself rewrites."""
    return {'name': source.name, 'adapter': source.adapter, 'board': source.board,
            'url': source.url, 'enabled': bool(source.enabled)}


def _digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, default=str).encode()).hexdigest()


def _read_snapshot(db):
    """Open an explicit SQLite read transaction on this session's connection.

    The pysqlite driver runs each SELECT in its own implicit snapshot, so two
    reads could otherwise straddle a concurrent commit. Inside BEGIN (WAL
    mode) every read sees the same committed state until the session closes
    and rolls the read transaction back.
    """
    db.connection().exec_driver_sql('BEGIN')


def _digests(defs, cfg):
    return _digest({str(k): v for k, v in defs.items()}), _digest(cfg)


def _binding(db, source_ids):
    """Current definitions of the scoped sources plus the full settings, read
    in one snapshot."""
    _read_snapshot(db)
    rows = {s.id: s for s in db.scalars(select(JobSource).where(JobSource.id.in_(source_ids)))}
    defs = {sid: source_definition(rows[sid]) if sid in rows else None for sid in source_ids}
    cfg = settings(db)
    return (defs, cfg) + _digests(defs, cfg)


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
    """Scope, workload and binding from ONE read of sources and settings.

    What the page displays (scope) and what the token binds (defs, cfg) are
    derived from the same objects, read in the same snapshot, so they cannot
    disagree.
    """
    _read_snapshot(db)
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
    defs = {s.id: source_definition(s) for s in sources}
    return scope, _estimate(db, sources), defs, cfg


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
        scope, workload, defs, cfg = _scope(db, data.source_id)
    defs_digest, cfg_digest = _digests(defs, cfg)
    token = secrets.token_urlsafe(32)
    expires = _utc() + PREVIEW_TTL
    with _guard:
        _prune(_utc())
        # The confirmation binds to exactly what was previewed: these source
        # definitions and these settings. Held server-side, never returned.
        _previews[token] = {'scope': scope, 'expires': expires, 'run_id': None,
                            'source_defs': defs, 'cfg': cfg,
                            'defs_digest': defs_digest, 'cfg_digest': cfg_digest}
    return {'token': token, 'expires_at': expires.isoformat(), 'manual_only': True,
            'scope': scope, 'workload': workload}


_ISSUER = object()


class ScanConfirmation:
    """Proof that the Owner confirmed one previewed scope.

    Only ``confirm()`` creates one; ``main.task('discover')`` refuses to run
    without it, and ``claim()`` makes it single use. Whoever holds a
    confirmation also holds ``task_lock``: ``confirm()`` acquires it and the
    task releases it.
    """

    def __init__(self, issuer, run_id, source_ids, source_defs, cfg, cancel, single_source):
        if issuer is not _ISSUER:
            raise PermissionError('Only a confirmed Start Scan can authorise discovery')
        self.run_id = run_id
        self.source_ids = tuple(source_ids)
        self.source_defs = dict(source_defs)
        self.cfg = cfg
        self.cancel = cancel
        self.single_source = single_source
        self.trigger = TRIGGER
        self._claimed = False
        self._claim_lock = threading.Lock()

    def claim(self):
        with self._claim_lock:
            if self._claimed:
                return False
            self._claimed = True
            return True


def missing_source(source_id, definition):
    """Stand-in for a confirmed source deleted after confirmation, so the run
    still reports it by id and by its confirmed name."""
    definition = definition or {}
    return SimpleNamespace(id=source_id, name=definition.get('name') or 'Deleted source %d' % source_id,
                           adapter=definition.get('adapter') or 'unknown')


def _run(confirmation):
    from .main import task
    try:
        task('discover', confirmation=confirmation)
    finally:
        with _guard:
            _cancel.pop(confirmation.run_id, None)


@router.post('/start')
def start(data: StartRequest):
    """Start exactly one scan for one confirmed preview."""
    confirmation = confirm(data.token)
    if not isinstance(confirmation, ScanConfirmation):
        return confirmation
    try:
        threading.Thread(target=_run, args=(confirmation,),
                         name='astra-manual-scan-%d' % confirmation.run_id, daemon=True).start()
    except Exception as error:
        _abandon(data.token, confirmation, error)
        return JSONResponse({'detail': 'The scan could not be started, and nothing was fetched. '
                                       'Review the scope again and retry.',
                             'start_failed': True, 'run_id': confirmation.run_id}, 500)
    return {'started': True, 'run_id': confirmation.run_id}


def _abandon(token, confirmation, error):
    """Undo a confirmation whose worker never started, so nothing stays stuck.

    The RUNNING run is closed as FAILED (nothing was fetched), the confirmation
    is claimed so it can never run, the preview token and cancel event are
    dropped, and task_lock (acquired by confirm()) is released. Each step runs
    even if an earlier one fails, and the lock is always released last.
    """
    from .main import task_lock
    try:
        confirmation.claim()
        with _guard:
            _previews.pop(token, None)
            _cancel.pop(confirmation.run_id, None)
        with Session.begin() as db:
            run = db.get(AutomationRun, confirmation.run_id)
            if run is not None and run.status == 'RUNNING':
                run.status = 'FAILED'
                run.report = {**(run.report or {}), 'finished_at': now(), 'sources_attempted': 0,
                              'error': 'The scan worker could not start (%s); nothing was fetched.'
                                       % type(error).__name__}
    finally:
        task_lock.release()


def confirm(token):
    """Turn a valid preview token into a ScanConfirmation.

    Returns a 409 JSONResponse instead when the token is unknown, expired or
    already used, when the scope changed since the preview, or when a scan is
    running. On success, task_lock is held and a RUNNING AutomationRun exists.
    """
    from .main import task_lock
    with _guard:
        _prune(_utc())
        pending = _previews.get(token)
        if pending is None:
            return JSONResponse({'detail': 'This scan preview has expired or is unknown. '
                                           'Review the scope again before starting.'}, 409)
        if pending['run_id'] is not None:
            return JSONResponse({'detail': 'This scan was already started.',
                                 'already_started': True, 'run_id': pending['run_id']}, 409)
        with Session() as db:
            _, _, defs_digest, cfg_digest = _binding(db, pending['scope']['source_ids'])
        if (defs_digest, cfg_digest) != (pending['defs_digest'], pending['cfg_digest']):
            # Sources or settings changed since the preview. The Owner confirmed
            # the previewed scope, not this one, so nothing starts.
            del _previews[token]
            return JSONResponse({'detail': 'Your sources or search settings changed after this preview. '
                                           'Review the scope again before starting.',
                                 'scope_changed': True}, 409)
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
            stop = ScanStop()
            _cancel[run_id] = stop
            return ScanConfirmation(_ISSUER, run_id, scope['source_ids'], pending['source_defs'],
                                    pending['cfg'], stop, scope['single_source'])
        except Exception:
            task_lock.release()
            raise


@router.post('/cancel')
def cancel(data: CancelRequest):
    """Stop the running scan at its next provider admission.

    Accepted under the same lock as admission, and only after
    cancel_requested_at is committed: a source not yet admitted is never
    fetched, and the response names the source already in flight, which
    finishes within its bounded provider budget. Refused once the last source
    is done."""
    with _guard:
        stop = _cancel.get(data.run_id)
    if stop is None:
        return JSONResponse({'detail': 'There is no running scan with that id in this session.'}, 409)
    with _report_guard:
        if stop.closed:
            return JSONResponse({'detail': 'This scan has finished fetching; there is nothing left to stop.',
                                 'finished': True}, 409)
        with Session.begin() as db:
            run = db.get(AutomationRun, data.run_id)
            if run is None or run.status != 'RUNNING':
                return JSONResponse({'detail': 'This scan has already finished.'}, 409)
            if not (run.report or {}).get('cancel_requested_at'):
                run.report = {**(run.report or {}), 'cancel_requested_at': now()}
        stop._accept()
        in_flight = stop.in_flight_at_stop
    return {'cancelling': True, 'run_id': data.run_id,
            'source_in_flight': in_flight['name'] if in_flight else None}


def _view(run):
    report = run.report or {}
    return {'id': run.id, 'status': run.status, 'created_at': run.created_at,
            'updated_at': run.updated_at, 'trigger': report.get('trigger'),
            'progress': report.get('progress'), 'scope': report.get('scope'),
            'cancel_requested_at': report.get('cancel_requested_at'),
            'cancelled': report.get('cancelled'), 'error': report.get('error'),
            'discovered': report.get('discovered'), 'duplicates': report.get('duplicates'),
            'failures': report.get('failures'),
            'scope_changed_sources': report.get('scope_changed_sources', []),
            'scope_accounting': report.get('scope_accounting')}


@router.get('/status')
def status():
    with Session() as db:
        running = _active_run(db)
        last = db.scalar(select(AutomationRun)
                         .where(AutomationRun.task == 'discover', AutomationRun.status != 'RUNNING')
                         .order_by(AutomationRun.id.desc()))
        with _guard:
            stop = _cancel.get(running.id) if running is not None else None
        cancellable = stop is not None and not stop.closed
        return {'manual_only': True, 'active': _view(running) if running else None,
                'cancellable': cancellable, 'last': _view(last) if last else None}
