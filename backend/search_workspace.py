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
    from .main import scheduler, task_lock
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
        job=scheduler.get_job('discover')
        active=cfg['autopilot']!='OFF' and cfg['discovery_enabled']
        return {'running':task_lock.locked(),'enabled':active,'interval_hours':cfg['discovery_interval_hours'],
                'next_scan':job.next_run_time.isoformat() if job and scheduler.running and active else None,
                'sources':sources,'runs':[{**serialize(r),'report':{k:v for k,v in r.report.items() if k!='decisions'}} for r in runs[:20]]}

@router.post('/scan')
def scan(data:dict={}):
    from .main import task, task_lock
    import threading
    source_id=data.get('source_id')
    with Session() as db:
        if source_id is not None:
            source=db.get(JobSource,source_id)
            if not source or not source.enabled: raise ValueError('Enable this source before scanning')
        elif not db.scalar(select(JobSource.id).where(JobSource.enabled==True)):
            raise ValueError('Add and enable a source first')
    if task_lock.locked(): return {'busy':True}
    threading.Thread(target=task,args=('discover',source_id),daemon=True).start()
    return {'started':True}

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
