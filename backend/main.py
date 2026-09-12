import os,json,shutil,csv,io,threading,tempfile,asyncio,secrets
from contextlib import asynccontextmanager
from datetime import datetime,timedelta,timezone
from zoneinfo import ZoneInfo
from collections import Counter
from urllib.parse import urlsplit
from fastapi import FastAPI,HTTPException,UploadFile,File,Request
from fastapi.responses import FileResponse,JSONResponse
from fastapi.staticfiles import StaticFiles
from starlette.middleware.trustedhost import TrustedHostMiddleware
from pydantic import BaseModel,Field,ConfigDict
from sqlalchemy import select
from apscheduler.schedulers.background import BackgroundScheduler
from .models import *
from .services import *
from .adapters import discover,parse_url
from .providers import provider
from .browser import run_browser,browser_test
from .discovery import discovery_reason
from . import career_tracks

from .reliability import ProcessLock
scheduler=BackgroundScheduler(timezone='Asia/Dubai'); task_lock=ProcessLock()
def task(name, source_id=None, scheduled_run=False, trigger=None):
    if not task_lock.acquire(blocking=False): return {'busy':True}
    try:
        with Session() as db:
            cfg=settings(db); run=AutomationRun(task=name); db.add(run); db.commit(); report={'discovered':0,'duplicates':0,'prepared':0,'submitted':0,'failures':0,'trigger':trigger or ('APP' if scheduled_run else 'MANUAL'),'started_at':now()}
            try:
                if name=='discover':
                    from .recall import evaluate,funnel
                    report.update(scanned=0,filtered=0,sources=[],source_id=source_id,decisions=[])
                    profile=candidate(db) if db.scalar(select(CandidateProfile)) else {}
                    for source in list(db.scalars(select(JobSource).where(JobSource.enabled==True))):
                        if source.adapter=='manual':continue
                        if source_id is not None and source.id != source_id: continue
                        if scheduled_run and source.details.get('last_success'):
                            from .search_workspace import parse_date
                            last=parse_date(source.details['last_success'])
                            interval=source.details.get('interval_hours',cfg['discovery_interval_hours'])
                            if last and interval in (3,6,12,24) and last+timedelta(hours=interval)>datetime.now(timezone.utc):continue
                        source_report={'id':source.id,'name':source.name,'scanned':0,'imported':0,'duplicates':0,'filtered':{},'error':''}
                        source_decisions=[]
                        try:
                            source.details={**source.details,'last_attempted':now(),'mode':'AUTOMATIC','market':'UAE campaign','interval_hours':source.details.get('interval_hours',cfg['discovery_interval_hours'])}
                            if source.adapter=='generic':
                                raise ValueError('Generic page scanning is disabled pending destination and platform review; use a public board API or paste the description')
                            items=discover(source.adapter,source.board,source.url)
                            for item in items:
                                report['scanned']+=1; source_report['scanned']+=1
                                item['company']=source.name
                                decision=evaluate(item,cfg,profile)
                                audit={'source_id':source.id,'item':{k:str(item.get(k,''))[:(2200 if k=='description' else 2000)] for k in ('title','company','location','job_url','source_job_id','source','date_posted','closing_date','description')},'decision':decision,'disposition':'EXCLUDED' if decision['excluded'] else 'PENDING'}
                                source_decisions.append(audit)
                            report['decisions'].extend(source_decisions)
                            source_report['filtered']=dict(Counter(a['decision']['hard'][0]['code'] for a in source_decisions if a['decision']['excluded']))
                            report['filtered']+=sum(source_report['filtered'].values())
                            for item,audit in zip(items,source_decisions):
                                decision=audit['decision']
                                if decision['excluded']:
                                    continue
                                j,d=add_job(db,item)
                                if not d and profile:analyze(db,j)
                                # Rescoring a discovery never changes historical application fields or stages.
                                j.analysis={**j.analysis,'recall':decision,'first_seen':j.analysis.get('first_seen',j.date_found),'last_seen':now(),'discovery':{**j.analysis.get('discovery',{}),'source_id':source.id,'last_seen':now()}}
                                audit.update(job_id=j.id,disposition='DUPLICATE' if d else 'NEW',already_seen=bool(j.analysis.get('seen_at')))
                                report['duplicates' if d else 'discovered']+=1
                                source_report['duplicates' if d else 'imported']+=1
                            source_report['funnel']=funnel(source_decisions)
                            source.details={**source.details,'last_success':now(),'last_verified':now()[:10],'jobs_fetched':source_report['scanned'],'new_jobs':source_report['imported'],'updated_jobs':source_report['duplicates'],'last_error':''}
                            db.commit()
                        except Exception as e:
                            db.rollback(); report['discovered']-=source_report['imported']; report['duplicates']-=source_report['duplicates']
                            source_report['imported']=source_report['duplicates']=0
                            for audit in report.get('decisions',[]):
                                if audit['source_id']==source.id and audit['disposition'] in ('NEW','DUPLICATE','PENDING'):audit['disposition']='SOURCE_ERROR';audit.pop('job_id',None)
                            source_report['funnel']=funnel(source_decisions)
                            source.details={**source.details,'last_attempted':now(),'last_error':'Request failed; retry or review source configuration'}
                            report['failures']+=1; source_report['error']='Source request failed ('+type(e).__name__+'). Check the source URL or retry later.'; log(db,source_report['error'],level='ERROR'); db.commit()
                        report['sources'].append(source_report)
                elif name in ('analyze','prepare','process'):
                    for j in list(db.scalars(select(Job).where(Job.status.not_in(TERMINAL|{'SKIP'})))):
                        try:
                            if name=='analyze': analyze(db,j)
                            elif name=='prepare' and j.recommendation in ('APPLY','HIGH_PRIORITY'):
                                if not db.scalar(select(Application).where(Application.job_id==j.id)): prepare(db,j); report['prepared']+=1
                            elif False:  # External submission is disabled; legacy settings cannot re-enable it.
                                site=db.scalar(select(SiteAdapter).where(SiteAdapter.domain==host(j.job_url)))
                                if site and site.enabled and site.auto_submit and site.permitted and not linkedin(j.job_url) and j.status=='READY_TO_APPLY':
                                    run_browser(db,j,'AUTO_ALLOWED',False); report['submitted']+=int(j.status=='APPLIED')
                            db.commit()
                        except Exception as e: db.rollback(); report['failures']+=1; log(db,'Task could not finish ('+type(e).__name__+')',j.id,'ERROR'); db.commit()
                elif name=='sync': report.update(sync_tracker(db))
                elif name=='report': report.update(metrics(db))
                else: raise ValueError('Unknown task')
                report['finished_at']=now();report['duration_seconds']=round((datetime.fromisoformat(report['finished_at'])-datetime.fromisoformat(report['started_at'])).total_seconds(),3)
                if name=='discover':
                    for stored in db.scalars(select(Job)):
                        stored.analysis={**stored.analysis,'recall':evaluate(serialize(stored),cfg,profile)}
                    report['funnel']=funnel(report['decisions']);report['sources_attempted']=len(report['sources']);report['sources_successful']=sum(not s['error'] for s in report['sources'])
                    # Bound verbose decision retention to the requested 90-day campaign; keep aggregate history.
                    cutoff=(datetime.now(timezone.utc)-timedelta(days=90)).isoformat()
                    for old in db.scalars(select(AutomationRun).where(AutomationRun.created_at<cutoff)):
                        if 'decisions' in old.report:old.report={k:v for k,v in old.report.items() if k!='decisions'}
                run=db.get(AutomationRun,run.id); run.status='PARTIAL' if report['failures'] else 'COMPLETED'; run.report=report; db.commit()
            except Exception as e:
                db.rollback(); run=db.get(AutomationRun,run.id); run.status='FAILED'
                report['finished_at']=now();report['duration_seconds']=round((datetime.fromisoformat(report['finished_at'])-datetime.fromisoformat(report['started_at'])).total_seconds(),3)
                run.report={**report,'error':'Task failed ('+type(e).__name__+'); no success is recorded.'}; db.commit()
            return serialize(run)
    finally: task_lock.release()
def scheduled(name):
    trigger='APP'
    with Session() as db:
        cfg=settings(db)
        if cfg['autopilot']=='OFF' or (name=='sync' and not cfg['auto_sync']) or (name=='discover' and not cfg['discovery_enabled']): return
        if name=='discover':
            from .search_workspace import parse_date
            recent=db.scalars(select(AutomationRun).where(AutomationRun.task=='discover',AutomationRun.status.in_(['COMPLETED','PARTIAL'])).order_by(AutomationRun.id.desc()).limit(100))
            last=next((r for r in recent if r.report.get('source_id') is None),None)
            checked=parse_date(last.updated_at) if last else None
            if checked and checked+timedelta(hours=cfg['discovery_interval_hours']*2)<datetime.now(timezone.utc):trigger='CATCHUP'
    task(name,scheduled_run=True,trigger=trigger)
def configure_schedule():
    with Session() as db:
        cfg=settings(db)
        recent=list(db.scalars(select(AutomationRun).where(AutomationRun.task=='discover',AutomationRun.status.in_(['COMPLETED','PARTIAL'])).order_by(AutomationRun.id.desc()).limit(100)))
        last=next((r for r in recent if r.report.get('source_id') is None),None)
        interval=timedelta(hours=cfg['discovery_interval_hours'])
        next_scan=datetime.now(timezone.utc)+interval
        if last:
            from .search_workspace import parse_date
            checked=parse_date(last.updated_at)
            if checked: next_scan=max(checked+interval,datetime.now(timezone.utc)+timedelta(seconds=10))
    scheduler.remove_all_jobs()
    for name,time in cfg['schedule'].items():
        if name=='discover': continue
        hour,minute=map(int,time.split(':')); scheduler.add_job(scheduled,'cron',args=[name],id=name,hour=hour,minute=minute,timezone=cfg.get('application_profile',{}).get('timezone','Asia/Dubai'),misfire_grace_time=1800,coalesce=True,max_instances=1)
    scheduler.add_job(scheduled,'interval',hours=cfg['discovery_interval_hours'],args=['discover'],id='discover',next_run_time=next_scan,misfire_grace_time=1800,coalesce=True,max_instances=1)
    from .workbook import retry_sync
    scheduler.add_job(retry_sync,'interval',seconds=30,id='workbook_retry',coalesce=True,max_instances=1)
    from .reliability import backup_database
    scheduler.add_job(backup_database,'interval',hours=24,id='daily_backup',coalesce=True,max_instances=1)
@asynccontextmanager
async def lifespan(app):
    initialize()
    if os.getenv('BIND_HOST','127.0.0.1') not in ('127.0.0.1','localhost') and not os.getenv('APP_TOKEN'): raise RuntimeError('APP_TOKEN required for public binding')
    # A process restart cannot finish an earlier in-memory scan.
    if task_lock.acquire(False):
        try:
            with Session.begin() as db:
                for run in db.scalars(select(AutomationRun).where(AutomationRun.status=='RUNNING')):
                    run.status='INTERRUPTED'; run.report={**run.report,'error':'App stopped before this run finished; scan again.'}
        finally:task_lock.release()
    configure_schedule(); scheduler.start()
    yield
    scheduler.shutdown(wait=False)
app=FastAPI(title='ASTRA',lifespan=lifespan)
app.add_middleware(TrustedHostMiddleware,allowed_hosts=['localhost','127.0.0.1','testserver'])
mutation_lock=asyncio.Lock()
@app.middleware('http')
async def guard(req:Request,call_next):
    import ipaddress
    from .security_events import record as security_event
    peer=req.client.host if req.client else ''
    if peer!='testclient':
        try: local=ipaddress.ip_address(peer).is_loopback
        except ValueError: local=False
        if not local:
            security_event('PEER_BLOCKED','Non-loopback network peer rejected',peer=peer,path=req.url.path)
            return JSONResponse({'detail':'This workspace accepts connections only from this device'},403)
    origin=req.headers.get('origin')
    port=os.getenv('HUNTER_PORT','8787')
    if origin and origin not in (f'http://localhost:{port}',f'http://127.0.0.1:{port}','http://localhost:5173'):
        security_event('INVALID_ORIGIN_BLOCKED','Cross-origin request rejected',origin=origin,path=req.url.path)
        return JSONResponse({'detail':'Origin blocked'},403)
    if req.headers.get('sec-fetch-site')=='cross-site':
        security_event('CSRF_REJECTED','Sec-Fetch-Site cross-site rejected',path=req.url.path,method=req.method)
        return JSONResponse({'detail':'Cross-site access blocked'},403)
    token=os.getenv('APP_TOKEN','')
    if token and req.url.path.startswith('/api') and not secrets.compare_digest(req.headers.get('authorization',''),'Bearer '+token): return JSONResponse({'detail':'Enter your access token'},401)
    try: length=int(req.headers.get('content-length','0'))
    except ValueError: return JSONResponse({'detail':'Invalid content length'},400)
    if length<0 or length>11_000_000: return JSONResponse({'detail':'Upload limit is 10 MB'},413)
    if req.method not in ('GET','HEAD','OPTIONS') and (req.headers.get('transfer-encoding') or 'content-length' not in req.headers):
        return JSONResponse({'detail':'Send a bounded request with Content-Length; streaming uploads are unsupported'},411)
    try:
        if req.method not in ('GET','HEAD','OPTIONS'):
            if not req.headers.get('content-type','').startswith(('application/json','multipart/form-data')) and length:
                return JSONResponse({'detail':'Use JSON or a supported file upload'},415)
            async with mutation_lock: response=await call_next(req)
        else: response=await call_next(req)
    except Exception:
        # Catch before ServerErrorMiddleware re-raises to Uvicorn: database
        # exception parameter dumps can contain private profile/answer values.
        response=JSONResponse({'detail':'The operation could not finish. No success is recorded. Check the input or local storage, then retry.'},500)
    response.headers['X-Content-Type-Options']='nosniff'; response.headers['Referrer-Policy']='no-referrer'; response.headers['X-Frame-Options']='DENY'
    response.headers['Cache-Control']='no-store'
    response.headers['Permissions-Policy']='geolocation=(), camera=(), microphone=(), payment=(), usb=(), interest-cohort=()'
    response.headers['Content-Security-Policy']="default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; img-src 'self' data: blob:; connect-src 'self'; font-src 'self'; frame-ancestors 'none'; object-src 'none'; base-uri 'none'; form-action 'self'"
    return response
@app.exception_handler(ValueError)
async def value_error(req,exc): return JSONResponse({'detail':str(exc)},400)
@app.exception_handler(Exception)
async def unexpected_error(req,exc):
    return JSONResponse({'detail':'The operation could not finish. No success is recorded. Retry or check local storage availability.'},500)
def get_job(db,id):
    j=db.get(Job,id)
    if not j: raise HTTPException(404,'Job not found')
    return j
@app.get('/api/health')
def health(): return {'ok':True,'scheduler':scheduler.running,'version':'campaign-2026-09','pid':os.getpid()}
def metrics(db):
    jobs=list(db.scalars(select(Job))); apps=list(db.scalars(select(Application))); counts=Counter(a.status for a in apps); applied=[a for a in apps if a.applied_date]; today=datetime.now(ZoneInfo('Asia/Dubai')).date(); dates=[]
    for a in applied:
        try: dates.append(datetime.fromisoformat(a.applied_date).astimezone(ZoneInfo('Asia/Dubai')).date())
        except ValueError: pass
    interviews=counts['INTERVIEW']+counts['OFFER']; responses=interviews+counts['REJECTED']
    return {'jobs':len(jobs),'high_priority':sum(j.priority=='HIGH' for j in jobs),'ready':sum(a.status=='READY_TO_APPLY' for a in apps),'applied':len(applied),'today':sum(d==today for d in dates),'week':sum(d>=today-timedelta(days=today.weekday()) for d in dates),'interviews':interviews,'offers':counts['OFFER'],'rejections':counts['REJECTED'],'response_rate':round(responses/max(len(applied),1)*100),'interview_rate':round(interviews/max(len(applied),1)*100),'average_score':round(sum(j.match_score for j in jobs)/max(len(jobs),1)),'overdue_followups':sum(not f.done and f.due_date<now() for f in db.scalars(select(FollowUp))),'by_status':dict(counts),'by_source':dict(Counter(j.source for j in jobs)),'by_location':dict(Counter(j.location for j in jobs)),'by_week':dict(Counter(d.strftime('%Y-W%W') for d in dates)),'scores':dict(Counter(str(j.match_score//10*10) for j in jobs)),'missing':dict(Counter(s for j in jobs for s in j.missing_skills).most_common(10)),'best':[serialize(j) for j in sorted(jobs,key=lambda j:j.match_score,reverse=True) if j.status not in TERMINAL|{'SKIP'}][:5]}
@app.get('/api/dashboard')
def dashboard():
    with Session() as db: return metrics(db)
@app.get('/api/profile')
def profile():
    with Session() as db: return candidate(db) if db.scalar(select(CandidateProfile)) else None
@app.put('/api/profile')
def update_profile(data:dict):
    with Session.begin() as db:
        p=db.scalar(select(CandidateProfile))
        if not p: raise ValueError('Import CV first')
        for k in ('name','email','phone','location','summary'):
            if k in data and (not isinstance(data[k],str) or len(data[k])>20000): raise ValueError('Profile text must be under 20,000 characters')
        if 'confirmed' in data and type(data['confirmed']) is not bool: raise ValueError('Confirmation must be true or false')
        if 'declarations' in data and (not isinstance(data['declarations'],dict) or len(json.dumps(data['declarations']))>30000): raise ValueError('Invalid profile declarations')
        changed=[k for k in ('name','email','phone','location','summary') if k in data and data[k]!=getattr(p,k)]
        for k in ('name','email','phone','location','summary','declarations','confirmed'):
            if k in data: setattr(p,k,data[k])
        if changed and data.get('confirmed') is not True: p.confirmed=False
        p.declarations={**p.declarations,'field_sources':{**p.declarations.get('field_sources',{}),**{k:{'state':'USER PROVIDED','updated_at':now()} for k in changed}},'extraction_state':'VERIFIED' if p.confirmed else 'EXTRACTED — NEEDS CONFIRMATION'}
        log(db,'Candidate profile updated by user'); return serialize(p)
@app.post('/api/import/cv')
def cv_upload(file:UploadFile=File(...)):
    from .document_security import validate_document,MAX_FILE
    content=validate_document(file.file.read(MAX_FILE+1),file.filename,'pdf',file.content_type)
    with tempfile.TemporaryDirectory(prefix='.import-',dir=DATA) as folder:
        path=Path(folder)/'cv.pdf'; path.write_bytes(content)
        master=DATA/'master.pdf'; backup=Path(folder)/'previous.pdf'
        if master.exists(): shutil.copy2(master,backup)
        try:
            with Session.begin() as db: result=serialize(import_cv(db,path))
            return result
        except Exception:
            if backup.exists(): os.replace(backup,master)
            elif master.exists(): master.unlink()
            raise

@app.put('/api/profile/facts/{kind}/{fact_id}')
def correct_fact(kind:str,fact_id:int,data:dict):
    types={'skills':Skill,'employments':Employment,'education':Education,'certifications':Certification,'projects':Project}
    if kind not in types: raise HTTPException(404)
    value=data.get('text')
    if not isinstance(value,str) or not value.strip() or len(value)>20000: raise ValueError('Enter a fact under 20,000 characters')
    with Session.begin() as db:
        fact=db.get(types[kind],fact_id)
        if not fact: raise HTTPException(404)
        fact.text=value; fact.provenance='USER PROVIDED '+now()
        profile=db.get(CandidateProfile,fact.candidate_id); profile.confirmed=False
        log(db,'Candidate corrected a source fact; confirmation required')
        return serialize(fact)
@app.post('/api/import/tracker')
def tracker_upload(file:UploadFile=File(...)):
    from .document_security import validate_document,MAX_FILE
    content=validate_document(file.file.read(MAX_FILE+1),file.filename,'xlsx',file.content_type)
    with tempfile.TemporaryDirectory(prefix='.import-',dir=DATA) as folder:
        path=Path(folder)/'tracker.xlsx'; path.write_bytes(content)
        target=DATA/'tracker.xlsx'; backup=Path(folder)/'previous.xlsx'
        if target.exists(): shutil.copy2(target,backup)
        try:
            with Session.begin() as db:
                result=import_tracker(db,path)
                if backup.exists(): shutil.copy2(backup,DATA/'tracker_previous.xlsx')
                os.replace(path,target)
            return result
        except Exception:
            if backup.exists(): os.replace(backup,target)
            elif target.exists(): target.unlink()
            raise
@app.post('/api/import/csv')
def csv_upload(file:UploadFile=File(...)):
    from .document_security import validate_document,MAX_FILE
    from itertools import islice
    content=validate_document(file.file.read(MAX_FILE+1),file.filename,'csv',file.content_type)
    rows=list(islice(csv.DictReader(io.StringIO(content.decode('utf-8-sig'))),10001)); imported=0; duplicates=0
    if len(rows)>10000: raise ValueError('CSV supports up to 10,000 rows')
    with Session.begin() as db:
        for row in rows:
            data={HEADERS.get(k,k):v for k,v in row.items() if v and HEADERS.get(k,k) in ('company','title','location','job_url','description','source','salary','remote_status')}
            _,dupe=add_job(db,data); imported+=not bool(dupe); duplicates+=bool(dupe)
    return {'imported':imported,'duplicates':duplicates}
@app.get('/api/jobs')
def jobs():
    with Session() as db: return [serialize(j) for j in db.scalars(select(Job).order_by(Job.id.desc()))]
class JobInput(BaseModel):
    company:str=Field(min_length=1,max_length=200)
    title:str=Field(min_length=1,max_length=300)
    location:str='UNKNOWN'
    job_url:str=''
    description:str=Field(default='',max_length=100000)
    source:str='Manual'
    salary:str='UNKNOWN'
    remote_status:str='UNKNOWN'
    employment_type:str='UNKNOWN'
    experience_requirement:str=Field(default='UNKNOWN',max_length=1000)
    notes:str=Field(default='',max_length=20000)
    date_found:str=''
@app.post('/api/jobs')
def create_job(data:JobInput):
    with Session.begin() as db:
        values=data.model_dump()
        if not values.get('date_found'):values.pop('date_found',None)
        elif not __import__('backend.search_workspace',fromlist=['parse_date']).parse_date(values['date_found']):raise ValueError('Choose a valid discovery date')
        j,d=add_job(db,values)
        if not d:
            agency=any(token in (data.source+' '+data.job_url).lower() for token in ['michaelpage','michael page','hays','charterhouse','roberthalf','robert half','cooperfitch','cooper fitch','guildhall','mackenzie'])
            j.analysis={**j.analysis,'source_type':'RECRUITMENT_AGENCY' if agency else 'MANUAL','discovered_via':data.source,'first_seen':j.date_found}
        if not d and db.scalar(select(CandidateProfile)):analyze(db,j)
        return {**serialize(j),'duplicate':d}
@app.post('/api/import/url')
def import_url(data:dict):
    url=data.get('url','')
    if linkedin(url): raise ValueError('LinkedIn: use Add job and paste the description; this URL will not be fetched')
    raise ValueError('Arbitrary webpage imports are disabled pending platform and destination review. Add a public company board in Discovery, or paste the job description using Add job.')
@app.get('/api/jobs/{id}')
def job_detail(id:int):
    with Session() as db:
        j=get_job(db,id); a=db.scalar(select(Application).where(Application.job_id==id))
        from .campaign import fit,review_signals,remote_scope
        history=[{'id':x.id,'title':other.title,'status':x.tracking.get('stage',x.status),'date':x.applied_date} for x,other in db.execute(select(Application,Job).join(Job,Application.job_id==Job.id)) if norm(other.company)==norm(j.company) and x.job_id!=j.id]
        return {**serialize(j),'fit_band':fit(j),'review_signals':review_signals(j),'remote_scope':remote_scope(j),'company_history':history,'application':serialize(a) if a else None,'resumes':[serialize(x) for x in db.scalars(select(ResumeVersion).where(ResumeVersion.job_id==id))],'letters':[serialize(x) for x in db.scalars(select(CoverLetter).where(CoverLetter.job_id==id))],'events':[serialize(x) for x in db.scalars(select(ApplicationEvent).where(ApplicationEvent.job_id==id))],'questions':[serialize(x) for x in db.scalars(select(ApplicationQuestion).where(ApplicationQuestion.application_id==a.id))] if a else [],'browser_runs':[serialize(x) for x in db.scalars(select(BrowserRun).where(BrowserRun.application_id==a.id))] if a else []}
@app.post('/api/jobs/{id}/{action}')
def job_action(id:int,action:str,data:dict={}):
    with Session() as db:
        j=get_job(db,id)
        if action=='analyze': result=analyze(db,j)
        elif action=='cv': result=serialize(generate_cv(db,j))
        elif action=='cover': result=serialize(cover(db,j))
        elif action=='prepare': result=serialize(prepare(db,j))
        elif action=='status': result=serialize(set_status(db,j,data.get('status','')))
        elif action=='browser': result=run_browser(db,j,data.get('mode','ASSISTED'),data.get('dry_run',True))
        elif action=='ai':
            p=candidate(db)
            if not p['confirmed']: raise ValueError('Confirm profile facts before requesting model advice')
            facts={str(s['id']):s['text'] for s in p['skills']}; result=provider(settings(db)['provider'],consent=data.get('allow_cloud') is True).advise(j.description,facts).model_dump(); j.analysis={**j.analysis,'ai_advice':result}
        else: raise HTTPException(404)
        db.commit(); return result
@app.post('/api/bulk/prepare')
def bulk(data:dict):
    result=[]
    for id in data.get('ids',[])[:100]:
        try: result.append({'id':id,'result':job_action(id,'prepare')})
        except Exception as e: result.append({'id':id,'error':str(e)[:300]})
    return result
COLLECTIONS={'applications':Application,'answers':ApprovedAnswer,'interviews':Interview,'followups':FollowUp,'sources':JobSource,'sites':SiteAdapter,'logs':ApplicationEvent,'runs':AutomationRun,'documents':ResumeVersion,'recruiters':Recruiter}
@app.get('/api/records/{kind}')
def records(kind:str):
    if kind not in COLLECTIONS: raise HTTPException(404)
    with Session() as db: return [serialize(x) for x in db.scalars(select(COLLECTIONS[kind]).order_by(COLLECTIONS[kind].id.desc()))]
@app.post('/api/records/{kind}')
def save_record(kind:str,data:dict):
    if kind not in ('answers','interviews','followups','sources','sites','recruiters'): raise ValueError('Read-only collection')
    model=COLLECTIONS[kind]
    if kind=='answers': data['normalized_question']=norm(data.get('question',''))
    if kind=='sites':
        domain=data.get('domain','').lower().strip().rstrip('.')
        if not re.fullmatch(r'[a-z0-9.-]+',domain) or linkedin('https://'+domain): raise ValueError('Invalid domain or LinkedIn is blocked')
        data['domain']=domain
    if kind=='sources' and (data.get('adapter')=='linkedin' or linkedin(data.get('url',''))): raise ValueError('LinkedIn cannot be monitored')
    with Session.begin() as db:
        row=db.get(model,data['id']) if data.get('id') else model()
        if row is None: raise ValueError('Record not found')
        for k,v in data.items():
            if k in model.__table__.columns.keys() and k not in ('id','created_at','updated_at'): setattr(row,k,v)
        db.add(row); db.flush(); return serialize(row)
@app.get('/api/career-tracks')
def career_tracks_list():
    return career_tracks.public_tracks()
@app.get('/api/profile/career-suggestions')
def career_suggestions():
    with Session() as db:
        p=candidate(db) if db.scalar(select(CandidateProfile)) else None
        if not p: return []
        text=' '.join([p.get('raw_text',''),p.get('summary','')]+[s['text'] for s in p.get('skills',[])])
        return career_tracks.suggest(text)
@app.post('/api/settings/career-focus')
def set_career_focus(data:dict):
    ids=[x for x in data.get('career_tracks',[]) if isinstance(x,str)]
    if any(x not in career_tracks.TRACKS for x in ids): raise ValueError('Unknown career track')
    custom=[x.strip() for x in data.get('custom_target_roles',[]) if isinstance(x,str) and x.strip()][:20]
    if any(len(x)>200 for x in custom): raise ValueError('Target role titles must be under 200 characters')
    if not ids and not custom: raise ValueError('Choose at least one career track or add a custom target role')
    with Session.begin() as db:
        cfg={**settings(db),'career_tracks':ids,'custom_target_roles':custom}
        cfg['target_roles']=career_tracks.target_role_titles(cfg)
        cfg['search_focus_confirmed']=True
        cfg['career_profile_version']=career_tracks.VERSION
        db.get(Settings,1).value=cfg
        return cfg
@app.get('/api/settings')
def get_settings():
    with Session() as db: return settings(db)
@app.put('/api/settings')
def put_settings(data:dict):
    with Session.begin() as db:
        cfg={**settings(db),**{k:v for k,v in data.items() if k in DEFAULTS}}
        if cfg['autopilot'] not in ('OFF','PREPARE_ONLY'): raise ValueError('Automatic submission is disabled. Choose OFF or PREPARE_ONLY.')
        cfg['dry_run']=True
        if cfg['provider'] not in ('rules','ollama','openai'): raise ValueError('Unknown model provider')
        if type(cfg['discovery_enabled']) is not bool or type(cfg['discovery_interval_hours']) is not int or cfg['discovery_interval_hours'] not in (3,6,12,24): raise ValueError('Choose scans every 3, 6, 12 or 24 hours')
        if not 0<=int(cfg['daily_limit'])<=100 or not 0<=int(cfg['max_retries'])<=5: raise ValueError('Invalid limits')
        if set(cfg['weights'])!=set(DEFAULTS['weights']) or any(not isinstance(v,(int,float)) or v<0 for v in cfg['weights'].values()) or sum(cfg['weights'].values())<=0: raise ValueError('Invalid scoring weights')
        for name,t in cfg['schedule'].items():
            if name not in DEFAULTS['schedule'] or not re.fullmatch(r'(?:[01]\d|2[0-3]):[0-5]\d',t): raise ValueError('Schedules must use HH:MM')
        db.get(Settings,1).value=cfg
    configure_schedule(); return cfg
@app.post('/api/sync')
def sync():
    with Session() as db:campaign_enabled=settings(db).get('campaign_workbook')
    if campaign_enabled:
        from .campaign import pending
        from .workbook import retry_sync
        with Session.begin() as db:pending(db)
        retry_sync()
        with Session() as db:
            state=db.get(WorkbookSync,1)
            return {'path':'tracker.xlsx','pending':state.revision>state.exported_revision,'message':state.error or ('Excel update pending' if state.revision>state.exported_revision else 'Excel tracker synchronized')}
    with Session.begin() as db: return sync_tracker(db)
@app.post('/api/tasks/{name}')
def run_task(name:str): return task(name)
@app.post('/api/browser/test')
def test_browser(): return browser_test()
@app.post('/api/browser/rehearsal')
def test_rehearsal():
    from .rehearsal import rehearse
    return rehearse()
@app.get('/api/files/{path:path}')
def file_download(path:str):
    target=(DATA/path).resolve()
    if not target.is_relative_to(DATA.resolve()) or not target.is_file() or target.suffix not in ('.pdf','.docx','.xlsx','.png'): raise HTTPException(404)
    return FileResponse(target,filename=target.name)
from .search_workspace import router as search_router
app.include_router(search_router)
from .campaign import router as campaign_router
from . import source_catalog
app.include_router(campaign_router)
from .privacy import router as privacy_router
app.include_router(privacy_router)
from .recall_api import router as recall_router
app.include_router(recall_router)
dist=Path(__file__).resolve().parents[1]/'frontend'/'dist'
@app.get('/demo',include_in_schema=False)
def demo_page():
    if not dist.exists(): raise HTTPException(404)
    return FileResponse(dist/'index.html')
if dist.exists(): app.mount('/',StaticFiles(directory=dist,html=True),name='ui')
