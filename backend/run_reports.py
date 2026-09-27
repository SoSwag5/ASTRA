"""Automation-run summaries without the per-posting decision audit.

A finished discovery run keeps every checked posting's decision audit in
`report['decisions']`: several megabytes per run, the bulk of the table. The
table stores `report` before `created_at` and `updated_at`, so even reading a
run's timestamps walks its whole report. Pages that poll every few seconds
need only the summary fields, and reading them straight from the table made
each poll decode the entire run history, starving a running scan of CPU.

`summaries()` returns each run's status, timestamps and report without
`decisions`. SQLite removes the audit before Python decodes the row. The
result is kept until the run changes: a changed status, or any committed
write to that run through the application's Session (a status-preserving
rewrite such as telemetry retention included), makes the next call read it
again. A RUNNING run is always re-read; its stored report stays small until
the run finishes. The audit itself is untouched and still served by the
endpoints that show it.
"""
import json
import threading

from sqlalchemy import event, func, select

from .models import AutomationRun, Session

MAX_CACHED = 1000
_TOUCHED = 'astra_run_reports_touched'
_cache = {}                 # (database, run id) -> summary dict
_generation = [0]           # bumped by every invalidation; guards a load racing a commit
_guard = threading.Lock()


def _database(db):
    return str(db.get_bind().url)


def summaries(db, ids):
    """Map each existing run id to {'status', 'created_at', 'updated_at', 'report'}.

    `report` excludes 'decisions'. Only runs that are RUNNING, not yet read,
    changed status or were written since they were read are loaded.
    """
    ids = list(dict.fromkeys(ids))
    if not ids:
        return {}
    database = _database(db)
    statuses = dict(db.execute(select(AutomationRun.id, AutomationRun.status).where(AutomationRun.id.in_(ids))).all())
    with _guard:
        generation = _generation[0]
        stale = [rid for rid, status in statuses.items()
                 if status == 'RUNNING' or _cache.get((database, rid), {}).get('status') != status]
    loaded = {}
    if stale:
        if db.get_bind().dialect.name == 'sqlite':
            rows = db.execute(select(AutomationRun.id, AutomationRun.status, AutomationRun.created_at,
                                     AutomationRun.updated_at, func.json_remove(AutomationRun.report, '$.decisions'))
                              .where(AutomationRun.id.in_(stale)))
            for rid, status, created, updated, text in rows:
                loaded[rid] = {'status': status, 'created_at': created, 'updated_at': updated,
                               'report': json.loads(text) if text else {}}
        else:
            for run in db.scalars(select(AutomationRun).where(AutomationRun.id.in_(stale))):
                loaded[run.id] = {'status': run.status, 'created_at': run.created_at, 'updated_at': run.updated_at,
                                  'report': {k: v for k, v in (run.report or {}).items() if k != 'decisions'}}
    with _guard:
        if _generation[0] == generation:
            for rid, summary in loaded.items():
                if summary['status'] != 'RUNNING':
                    _cache[(database, rid)] = summary
            while len(_cache) > MAX_CACHED:
                _cache.pop(next(iter(_cache)))
        found = {rid: loaded.get(rid) or _cache.get((database, rid)) for rid in ids if rid in statuses}
    return {rid: {**summary, 'report': dict(summary['report'])} for rid, summary in found.items() if summary}


def clear():
    with _guard:
        _cache.clear()
        _generation[0] += 1


@event.listens_for(Session, 'after_flush')
def _collect(session, flush_context):
    touched = [obj.id for obj in (*session.new, *session.dirty, *session.deleted) if isinstance(obj, AutomationRun)]
    if touched:
        session.info.setdefault(_TOUCHED, set()).update(touched)


@event.listens_for(Session, 'after_commit')
def _invalidate(session):
    touched = session.info.pop(_TOUCHED, None)
    if touched:
        database = _database(session)
        with _guard:
            for rid in touched:
                _cache.pop((database, rid), None)
            _generation[0] += 1


@event.listens_for(Session, 'after_rollback')
def _discard(session):
    session.info.pop(_TOUCHED, None)
