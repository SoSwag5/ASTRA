"""Read-only discovery overview and personal tracking actions."""
from datetime import datetime, timedelta, timezone
from urllib.parse import urlsplit
from fastapi import APIRouter, HTTPException
from sqlalchemy import select
from .models import Session, Job, JobSource, Application, FollowUp, AutomationRun, settings, serialize, log

router=APIRouter(prefix='/api/search')

def parse_date(value):
    try:
        date=datetime.fromisoformat(value.replace('Z','+00:00'))
        return date if date.tzinfo else date.replace(tzinfo=timezone.utc)
    except (ValueError,TypeError,AttributeError): return None

@router.get('/overview')
def overview():
    from .main import task_lock
    with Session() as db:
        cfg=settings(db)
        runs=list(db.scalars(select(AutomationRun).where(AutomationRun.task=='discover').order_by(AutomationRun.id.desc()).limit(100)))
        sources=[]
        for source in db.scalars(select(JobSource).where(JobSource.adapter!='manual').order_by(JobSource.name)):
            result=None; checked=None
            for run in runs:
                result=next((s for s in run.report.get('sources',[]) if s.get('id')==source.id or ('id' not in s and s.get('name')==source.name)),None)
                if result is not None: checked=run.updated_at; break
            sources.append({**serialize(source),'last_scan':checked,'result':result})
        # Discovery is manual-only: there is never a scheduled next scan, and
        # 'enabled' (automatic scanning) is always False whatever legacy
        # settings are stored. See backend/scan_control.py.
        return {'running':task_lock.locked(),'enabled':False,'scan_mode':'MANUAL_ONLY',
                'interval_hours':cfg['discovery_interval_hours'],'next_scan':None,
                'sources':sources,'runs':[{**serialize(r),'report':{k:v for k,v in r.report.items() if k!='decisions'}} for r in runs[:20]]}

MAX_TELEMETRY_RUNS=20
DEFAULT_TELEMETRY_RUNS=5

def _telemetry_runs(db,limit,offset=0):
    """Discovery runs inside the 90-day retention window, newest first.

    Bounded twice over: the query is limited to the retention window and the
    caller's page size is clamped, so this endpoint can never return an
    unbounded history or a payload that grows with the job database.
    """
    from . import discovery_telemetry as telemetry
    cutoff=telemetry.retention_cutoff().isoformat()
    return list(db.scalars(select(AutomationRun)
                           .where(AutomationRun.task=='discover',AutomationRun.created_at>=cutoff)
                           .order_by(AutomationRun.id.desc())
                           .offset(max(0,offset)).limit(limit)))

@router.get('/telemetry')
def telemetry_latest():
    """Issue #43: the latest completed or partial discovery run's funnel.

    Read-only, local-boundary only (the application's loopback/origin guard and
    optional access key already gate every /api route). Never returns verbose
    decision records, job descriptions, titles, URLs, provider payloads or any
    other private per-job content -- `public_view` is a whitelist projection.
    """
    from . import discovery_telemetry as telemetry
    with Session() as db:
        runs=_telemetry_runs(db,MAX_TELEMETRY_RUNS)
        if not runs:
            return {'schema_version':telemetry.TELEMETRY_SCHEMA_VERSION,
                    'status':telemetry.NO_DATA,'run':None,
                    'note':'No discovery run has been recorded within the 90-day telemetry '
                           'retention window.'}
        finished=[r for r in runs if r.status!='RUNNING']
        latest=next((r for r in finished if telemetry.REPORT_KEY in (r.report or {})),None)
        run=latest or runs[0]
        view=telemetry.public_view(run)
        return {'schema_version':telemetry.TELEMETRY_SCHEMA_VERSION,
                'status':view['telemetry_status'],'run':view,'note':view['note']}

@router.get('/telemetry/runs')
def telemetry_history(limit:int=DEFAULT_TELEMETRY_RUNS,offset:int=0):
    from . import discovery_telemetry as telemetry
    if type(limit) is not int or type(offset) is not int or limit<1 or offset<0:
        raise ValueError('Choose a positive page size and a non-negative offset')
    limit=min(limit,MAX_TELEMETRY_RUNS)
    with Session() as db:
        runs=_telemetry_runs(db,limit,offset)
        return {'schema_version':telemetry.TELEMETRY_SCHEMA_VERSION,
                'retention_days':telemetry.RETENTION_DAYS,'limit':limit,'offset':offset,
                'maximum_runs':MAX_TELEMETRY_RUNS,'returned':len(runs),
                'runs':[telemetry.public_view(run) for run in runs]}

@router.get('/telemetry/runs/{run_id}')
def telemetry_run(run_id:int):
    from . import discovery_telemetry as telemetry
    if run_id<1: raise HTTPException(404,'Discovery run not found')
    with Session() as db:
        run=db.get(AutomationRun,run_id)
        if run is None or run.task!='discover': raise HTTPException(404,'Discovery run not found')
        cutoff=telemetry.retention_cutoff().isoformat()
        if (run.created_at or '')<cutoff: raise HTTPException(404,'Discovery run not found')
        view=telemetry.public_view(run)
        return {'schema_version':telemetry.TELEMETRY_SCHEMA_VERSION,
                'status':view['telemetry_status'],'run':view,'note':view['note']}

@router.post('/scan')
def scan(data:dict={}):
    """Retired one-click start. Scans now start only after the Owner reviews
    the scope and workload and confirms (POST /api/scan/preview, then
    /api/scan/start), so this endpoint starts nothing."""
    raise ValueError('Scans start only from Start Scan in Discovery: review the scope, then confirm.')

@router.post('/sources')
def add_source(data:dict):
    """Derive public board identifiers from a pasted company board URL."""
    url=data.get('url','').strip(); name=data.get('name','').strip()
    p=urlsplit(url); parts=[x for x in p.path.split('/') if x]
    hosts={'jobs.lever.co':'lever','jobs.ashbyhq.com':'ashby','job-boards.greenhouse.io':'greenhouse','boards.greenhouse.io':'greenhouse','jobs.smartrecruiters.com':'smartrecruiters'}
    if p.scheme!='https' or p.hostname not in hosts or p.username or p.password or p.port not in (None,443) or not parts:
        raise ValueError('Paste a Greenhouse, Lever, Ashby or SmartRecruiters company board URL')
    import re
    board=parts[0]
    if not re.fullmatch(r'[a-zA-Z0-9_-]{1,100}',board) or not name or len(name)>200: raise ValueError('Enter a company name and valid board URL')
    kind=hosts[p.hostname]
    with Session.begin() as db:
        row=db.scalar(select(JobSource).where(JobSource.adapter==kind,JobSource.board==board))
        if row: return {**serialize(row),'exists':True}
        row=JobSource(name=name,adapter=kind,board=board,url=f'https://{p.hostname}/{board}',enabled=True)
        db.add(row); db.flush(); log(db,f'Public discovery source added: {name}')
        return serialize(row)

@router.post('/jobs/{job_id}/notes')
def notes(job_id:int,data:dict):
    value=data.get('notes','')
    if not isinstance(value,str) or len(value)>20000: raise ValueError('Notes must be under 20,000 characters')
    with Session.begin() as db:
        job=db.get(Job,job_id)
        if not job: raise HTTPException(404)
        job.notes=value; log(db,'Personal notes updated',job_id)
        return {'notes':value}

@router.post('/jobs/{job_id}/save')
def save_job(job_id:int,data:dict):
    if type(data.get('saved')) is not bool: raise ValueError('Choose whether to save this job')
    with Session.begin() as db:
        job=db.get(Job,job_id)
        if not job: raise HTTPException(404)
        job.analysis={**job.analysis,'saved':data['saved']}
        return {'saved':data['saved']}

@router.get('/tracking')
def tracking():
    with Session() as db:
        rows=[]
        for app in db.scalars(select(Application).order_by(Application.id.desc())):
            job=db.get(Job,app.job_id)
            follow=db.scalar(select(FollowUp).where(FollowUp.application_id==app.id))
            date=parse_date(follow.due_date) if follow else None
            actionable=app.status not in ('OFFER','REJECTED','WITHDRAWN')
            rows.append({**serialize(app),'job':serialize(job),'followup':serialize(follow) if follow else None,
                         'due':bool(follow and not follow.done and date and date<=datetime.now(timezone.utc) and actionable)})
        return rows

@router.post('/tracking/{app_id}/followup')
def save_followup(app_id:int,data:dict):
    date=parse_date(data.get('due_date'))
    if not date: raise ValueError('Choose a valid follow-up date')
    if type(data.get('done',False)) is not bool: raise ValueError('Invalid completion value')
    with Session.begin() as db:
        app=db.get(Application,app_id)
        if not app: raise HTTPException(404)
        follow=db.scalar(select(FollowUp).where(FollowUp.application_id==app_id))
        if not follow: follow=FollowUp(application_id=app_id); db.add(follow)
        follow.due_date=date.isoformat(); follow.done=data.get('done',False)
        log(db,'Follow-up completed' if follow.done else 'Follow-up scheduled',app.job_id)
        db.flush(); return serialize(follow)
