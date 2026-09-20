"""Local campaign, factual outcomes and user-reported application history."""
from collections import Counter,defaultdict
from datetime import datetime,timedelta,timezone
from statistics import median
from zoneinfo import ZoneInfo
from fastapi import APIRouter,HTTPException
from pydantic import BaseModel,Field
from sqlalchemy import select
from .models import *
from .search_workspace import parse_date
from .policy import norm

router=APIRouter(prefix='/api/campaign')
RANKING_VERSION='uae-evidence-v2'
STAGES=['DISCOVERED','SHORTLISTED','PREPARING','APPLIED','RECRUITER_CONTACT','SCREENING','ASSESSMENT','INTERVIEW','FINAL_INTERVIEW','OFFER','HIRED','REJECTED','WITHDRAWN','NO_RESPONSE','ARCHIVED']
TERMINAL_STAGES={'HIRED','REJECTED','WITHDRAWN','ARCHIVED'}
EMIRATES=['Dubai','Abu Dhabi','Sharjah','Ajman','Ras Al Khaimah','Fujairah','Umm Al Quwain','Al Ain']

def emirate(location):
    for place in reversed(EMIRATES):
        if norm(place) in norm(location): return place
    if 'remote' in location.lower() and any(x in location.lower() for x in ['uae','united arab emirates']): return 'Remote UAE'
    return 'UAE-wide' if any(x in location.lower() for x in ['uae','united arab emirates']) else 'Unknown / other'

def fit(job):
    if job.analysis.get('recall'):
        return 'WEAK' if job.analysis['recall']['excluded'] else job.analysis['recall']['fit_band']
    if job.analysis.get('hard_blockers') or job.recommendation=='SKIP': return 'WEAK'
    if job.analysis.get('needs_review'): return 'POSSIBLE'
    return 'EXCELLENT' if job.match_score>=90 else 'STRONG' if job.match_score>=75 else 'POSSIBLE' if job.match_score>=55 else 'WEAK'

def role_family(title):
    value=title.lower()
    for family,words in [('SOC / Security Operations',['soc','security operations','monitoring','siem']),('Graduate Cybersecurity',['graduate','intern']),('Threat / Detection',['threat','detection','incident','forensic']),('GRC',['grc','governance','compliance','risk']),('Security Engineering',['engineer']),('Information Security',['information security'])]:
        if any(word in value for word in words): return family
    return 'Cybersecurity Analyst' if 'analyst' in value else 'Other'

def review_signals(job):
    import re
    warnings=[]
    if re.search(r'(?:pay|payment|transfer|deposit).{0,45}(?:recruitment fee|processing fee|visa fee|registration fee)|(?:recruitment|processing|visa|registration) fee.{0,35}(?:required|pay|transfer)',job.description,re.I):warnings.append('Potential warning: payment or recruitment fee language. Verify through the official employer before proceeding.')
    if re.search(r'(?:send|share|provide).{0,35}(?:password|one.time password|otp|bank login)',job.description,re.I):warnings.append('Potential warning: the listing requests credentials. Review carefully.')
    return warnings

def remote_scope(job):
    text=(job.location+' '+job.remote_status).lower()
    if not any(w in text for w in ['remote','worldwide','global','anywhere','emea','mena','gcc']):return 'On-site / unspecified'
    for scope,words in [('Worldwide',['worldwide','global','anywhere']),('UAE',['uae','united arab emirates','dubai','abu dhabi']),('GCC',['gcc']),('MENA',['mena','middle east']),('EMEA',['emea'])]:
        if any(w in text for w in words):return scope+' — verify eligibility'
    return 'Country-specific / unknown — verify eligibility'

def campaign_settings(db):
    cfg=settings(db)
    return { 'name':'UAE Job Search 2026','start_date':datetime.now(ZoneInfo('Asia/Dubai')).date().isoformat(),'review_date':'','status':'ACTIVE','weekly_target':5,'observation_days':14,'primary_emirates':['Dubai','Abu Dhabi'],'secondary_emirates':EMIRATES[2:],'adjacent_roles':[],'target_country':'United Arab Emirates','target_cities':EMIRATES,'remote_preference':'UAE-compatible','relocation_preference':'UNKNOWN','employment_types':['Full-time','Graduate','Internship'],'seniority':['Graduate','Junior','Associate'],'languages':[],'preferred_salary':'','keywords':[],**cfg.get('campaign',{})}

def pending(db):
    row=db.get(WorkbookSync,1)
    if not row: row=WorkbookSync(id=1,revision=0,exported_revision=0);db.add(row)
    row.revision=(row.revision or 0)+1

def record_event(db,app,event_type,notes='',when=None,source='USER',stage=''):
    db.add(ApplicationEvent(job_id=app.job_id,application_id=app.id,event_type=event_type,occurred_at=when or now(),source=source,stage=stage or app.tracking.get('stage',app.status),message=notes or event_type.replace('_',' ').title()))
    pending(db)

def application_rows(db):
    jobs={j.id:j for j in db.scalars(select(Job))}
    events=defaultdict(list)
    for event in db.scalars(select(ApplicationEvent).where(ApplicationEvent.application_id.is_not(None)).order_by(ApplicationEvent.occurred_at,ApplicationEvent.id)):
        events[event.application_id].append(serialize(event))
    follows={f.application_id:serialize(f) for f in db.scalars(select(FollowUp))}
    interviews=defaultdict(list)
    for interview in db.scalars(select(Interview)): interviews[interview.application_id].append(serialize(interview))
    result=[]
    for app in db.scalars(select(Application).order_by(Application.id.desc())):
        job=jobs.get(app.job_id)
        if not job:continue
        result.append({**serialize(app),'stage':app.tracking.get('stage',app.status),'job':serialize(job),'emirate':app.tracking.get('emirate') or emirate(job.location),'role_family':app.tracking.get('role_family') or role_family(job.title),'events':events[app.id],'followup':follows.get(app.id),'interviews':interviews[app.id]})
    return result

def analytics(rows,observation_days=14,clock=None):
    clock=clock or datetime.now(timezone.utc)
    submitted=[r for r in rows if parse_date(r['applied_date']) and parse_date(r['applied_date'])<=clock]
    responded=set();interviewed=set();offers=set();delays=[]
    for row in submitted:
        dates=[parse_date(e['occurred_at']) for e in row['events'] if e['event_type']=='MEANINGFUL_RESPONSE']
        dates=[d for d in dates if d and parse_date(row['applied_date'])<=d<=clock]
        if dates:responded.add(row['id']);delays.append((min(dates)-parse_date(row['applied_date'])).total_seconds()/86400)
        valid_events=[e for e in row['events'] if parse_date(e['occurred_at']) and parse_date(e['occurred_at'])<=clock]
        if row['stage'] in ('INTERVIEW','FINAL_INTERVIEW') or any(e['event_type'] in ('INTERVIEW','FINAL_INTERVIEW') for e in valid_events):interviewed.add(row['id'])
        if row['stage'] in ('OFFER','HIRED') or any(e['event_type']=='OFFER' for e in valid_events):offers.add(row['id'])
    mature=[r for r in submitted if parse_date(r['applied_date'])<=clock-timedelta(days=observation_days)]
    rate=lambda n,d: n/d if d else None
    local=clock.astimezone(ZoneInfo('Asia/Dubai'));week=local.date()-timedelta(days=local.weekday())
    grouped={}
    for label,key in [('source',lambda r:r['tracking'].get('source_at_application') or r['job']['source']),('emirate',lambda r:r['emirate']),('role',lambda r:r['role_family']),('cv',lambda r:r['tracking'].get('cv_version') or 'Not recorded'),('fit',lambda r:r['tracking'].get('fit_at_application') or 'Not recorded')]:
        groups=defaultdict(list)
        for r in submitted:groups[key(r)].append(r)
        grouped[label]=[{'name':name,'applications':len(group),'responses':sum(r['id'] in responded for r in group),'interviews':sum(r['id'] in interviewed for r in group),'offers':sum(r['id'] in offers for r in group)} for name,group in groups.items()]
    weeks=Counter((parse_date(r['applied_date']).astimezone(ZoneInfo('Asia/Dubai')).date()-timedelta(days=parse_date(r['applied_date']).astimezone(ZoneInfo('Asia/Dubai')).weekday())).isoformat() for r in submitted)
    recent=[r for r in submitted if parse_date(r['applied_date']).astimezone(ZoneInfo('Asia/Dubai')).date()>=week]
    return {'total':len(submitted),'active':sum(r['stage'] not in TERMINAL_STAGES for r in submitted),'this_week':len(recent),'quality_this_week':sum(r['tracking'].get('fit_at_application') in ('EXCELLENT','STRONG') for r in recent),'this_month':sum(parse_date(r['applied_date']).astimezone(ZoneInfo('Asia/Dubai')).strftime('%Y-%m')==local.strftime('%Y-%m') for r in submitted),'responses':len(responded),'interviews':len(interviewed),'offers':len(offers),'response_rate':rate(sum(r['id'] in responded for r in mature),len(mature)),'mature_count':len(mature),'observation_days':observation_days,'all_response_rate':rate(len(responded),len(submitted)),'interview_rate':rate(len(interviewed),len(submitted)),'offer_rate':rate(len(offers),len(submitted)),'interview_offer_rate':rate(len(offers&interviewed),len(interviewed)),'median_response_days':median(delays) if delays else None,'response_sample':len(delays),'groups':grouped,'weeks':[{'week':w,'applications':n} for w,n in sorted(weeks.items())],'pipeline':dict(Counter(r['stage'] for r in rows))}

@router.get('')
def overview():
    with Session() as db:
        rows=application_rows(db);cfg=campaign_settings(db);clock=datetime.now(timezone.utc)
        jobs=list(db.scalars(select(Job)));tracked={r['job_id'] for r in rows if r['applied_date']}
        strong=[{**serialize(j),'fit_band':fit(j),'emirate':emirate(j.location)} for j in jobs if fit(j) in ('EXCELLENT','STRONG') and j.id not in tracked and not j.analysis.get('seen_at') and j.analysis.get('recall',{}).get('daily',True) and j.analysis.get('feedback',{}).get('decision')!='NOT_FOR_ME']
        strong.sort(key=lambda j:(0 if j['emirate'] in cfg['primary_emirates'] else 1,-j['match_score'],-(parse_date(j['date_found']).timestamp() if parse_date(j['date_found']) else 0)))
        due=[r for r in rows if r['stage'] not in TERMINAL_STAGES and r.get('followup') and not r['followup']['done'] and parse_date(r['followup']['due_date']) and parse_date(r['followup']['due_date'])<=clock+timedelta(days=7)]
        upcoming=[{**i,'company':r['job']['company'],'role':r['job']['title']} for r in rows for i in r['interviews'] if parse_date(i['date']) and clock<=parse_date(i['date'])<=clock+timedelta(days=14)]
        sync=db.get(WorkbookSync,1)
        next_actions=[r for r in rows if r['stage'] not in TERMINAL_STAGES and r['tracking'].get('next_action') and parse_date(r['tracking'].get('next_action_date')) and parse_date(r['tracking']['next_action_date'])<=clock+timedelta(days=7)]
        recent_events=[e for r in rows for e in r['events'] if parse_date(e['occurred_at']) and clock-timedelta(days=7)<=parse_date(e['occurred_at'])<=clock]
        review={key:len({e['application_id'] for e in recent_events if e['event_type']==key}) for key in ['SHORTLISTED','APPLIED','MEANINGFUL_RESPONSE','INTERVIEW','REJECTED','FOLLOWUP_COMPLETED']}
        review['followups_pending']=sum(bool(r['followup'] and not r['followup']['done']) for r in rows)
        from .discovery import discovery_reason
        relevant=[j for j in jobs if fit(j)!='WEAK' and not discovery_reason(serialize(j),settings(db))]
        employers=Counter(norm(j.company) for j in relevant)
        coverage={'jobs':len(jobs),'employers':len({norm(j.company) for j in jobs}),'relevant_jobs':len(relevant),'relevant_employers':len(employers),'top_two_employer_share':sum(n for _,n in employers.most_common(2))/len(relevant) if relevant else None,'locations':dict(Counter(emirate(j.location) for j in relevant)),'fresh_24h':sum(bool(parse_date(j.date_posted) and clock-timedelta(days=1)<=parse_date(j.date_posted)<=clock) for j in relevant),'old_postings_90d':sum(bool(parse_date(j.date_posted) and parse_date(j.date_posted)<clock-timedelta(days=90)) for j in relevant),'posting_date_unknown':sum(not bool(parse_date(j.date_posted)) for j in relevant)}
        last_run=db.scalar(select(AutomationRun).where(AutomationRun.task=='discover',AutomationRun.status!='RUNNING').order_by(AutomationRun.id.desc()))
        health={'last':last_run.updated_at,'healthy':sum(not r.get('error') for r in last_run.report.get('sources',[])),'attempted':len(last_run.report.get('sources',[])),'new':last_run.report.get('discovered',0),'errors':last_run.report.get('failures',0)} if last_run else {}
        return {'discovery_health':health,'campaign':cfg,'metrics':analytics(rows,cfg['observation_days']),'applications':rows,'strong_new':strong[:10],'saved':[serialize(j) for j in jobs if j.analysis.get('saved') and j.id not in tracked],'followups':due,'next_actions':next_actions,'weekly_review':review,'upcoming':sorted(upcoming,key=lambda i:i['date']),'excel':serialize(sync) if sync else {},'ranking_version':RANKING_VERSION,'coverage':coverage}

@router.put('/settings')
def save_settings(data:dict):
    with Session.begin() as db:
        cfg=campaign_settings(db)
        for key,value in data.items():
            if key not in cfg:continue
            if key in ('weekly_target','observation_days'):
                if type(value) is not int or not 0<=value<=365:raise ValueError('Use a whole number from 0 to 365')
            elif isinstance(cfg[key],list):
                if not isinstance(value,list) or len(value)>100 or any(not isinstance(v,str) or len(v)>200 for v in value):raise ValueError('Enter a short list of search preferences')
            elif not isinstance(value,str) or len(value)>500:raise ValueError('Invalid campaign preference')
            cfg[key]=value
        row=db.get(Settings,1);row.value={**row.value,'campaign':cfg};pending(db)
        return cfg

class TrackInput(BaseModel):
    stage:str=''
    event_type:str=''
    date:str=''
    notes:str=Field(default='',max_length=20000)
    cv_version:str=Field(default='',max_length=300)
    next_action:str=Field(default='',max_length=500)
    next_action_date:str=''
    followup_date:str=''
    rejection_reason:str=Field(default='',max_length=300)
    application_method:str=Field(default='',max_length=100)
    meeting_date:str=''
    meeting_url:str=Field(default='',max_length=2000)

@router.post('/jobs/{job_id}/track')
def track(job_id:int,data:TrackInput):
    if data.stage and data.stage not in STAGES:raise ValueError('Choose a valid stage')
    if data.event_type and data.event_type not in ('MEANINGFUL_RESPONSE','AUTOMATED_CONFIRMATION','NOTE','FOLLOWUP_COMPLETED'):raise ValueError('Choose a valid event')
    for value in (data.date,data.next_action_date,data.followup_date,data.meeting_date):
        if value and not parse_date(value):raise ValueError('Choose a valid date')
    if data.meeting_url:
        from urllib.parse import urlsplit
        url=urlsplit(data.meeting_url)
        if url.scheme!='https' or not url.hostname or url.username or url.password:raise ValueError('Use an HTTPS meeting link')
    if data.date and parse_date(data.date)>datetime.now(timezone.utc)+timedelta(minutes=5):raise ValueError('Record events that have happened; use the meeting date for future appointments')
    with Session.begin() as db:
        job=db.get(Job,job_id)
        if not job:raise HTTPException(404)
        app=db.scalar(select(Application).where(Application.job_id==job_id))
        # Issue #46: capture where this application is BEFORE the lines below
        # overwrite the legacy fields the canonical bootstrap reads. An
        # application that already exists is primed now; one created on this
        # request is bootstrapped from `before` when its transition is
        # recorded, because priming it here would read the freshly created
        # row's defaults rather than the job's actual state.
        from .application_state import prime_state,pre_action_state
        before=pre_action_state(db,job,app)
        if not app:app=Application(job_id=job_id,tracking={});db.add(app);db.flush()
        else:prime_state(db,app)
        details=dict(app.tracking or {});old=details.get('stage',app.status)
        when=parse_date(data.date).isoformat() if data.date else now()
        if data.stage=='APPLIED' and not app.applied_date:
            if not data.cv_version.strip():raise ValueError('Record the CV version used, or enter Not recorded')
            if parse_date(when)>datetime.now(timezone.utc)+timedelta(minutes=5):raise ValueError('An application date cannot be in the future')
            app.applied_date=when;app.confirmation='USER REPORTED — receipt not independently verified'
            details.update(fit_at_application=fit(job),ranking_version=RANKING_VERSION,score_at_application=job.match_score,cv_version=data.cv_version,source_at_application=job.source,role_family=role_family(job.title),emirate=emirate(job.location))
        elif data.cv_version.strip() and data.cv_version!=details.get('cv_version'):
            details['cv_version']=data.cv_version
            record_event(db,app,'CV_VERSION_RECORDED','User recorded CV version: '+data.cv_version)
        if data.stage:
            details['stage']=data.stage;app.status=data.stage;job.status=data.stage
            if data.stage=='SHORTLISTED':job.analysis={**job.analysis,'saved':True};details.setdefault('date_shortlisted',when)
            if data.stage in TERMINAL_STAGES|{'OFFER'}:details['outcome']=data.stage
        for key in ('next_action','next_action_date','rejection_reason','application_method'):
            if key in data.model_fields_set:details[key]=getattr(data,key)
        details['last_activity']=now();app.tracking=details
        if data.stage and old!=data.stage:record_event(db,app,data.stage,data.notes,when,stage=data.stage)
        if data.stage:
            # Issue #46: the campaign stage remains the compatibility field the
            # existing UI reads; the authoritative canonical state is derived
            # from this same user assertion by the state service, which owns
            # the transition rules and the append-only history. A stage with no
            # canonical meaning (NO_RESPONSE) asserts nothing and is skipped.
            from .application_state import record_legacy_assertion,SOURCE_USER_ACTION
            record_legacy_assertion(db,app,data.stage,source_category=SOURCE_USER_ACTION,asserted_by='USER',occurred_at=when,bootstrap_from=before)
        if data.event_type:record_event(db,app,data.event_type,data.notes,when)
        elif data.notes and (not data.stage or old==data.stage):record_event(db,app,'NOTE',data.notes,when)
        follow_date=data.followup_date or ((parse_date(when)+timedelta(days=settings(db)['followup_days'])).isoformat() if data.stage=='APPLIED' and not db.scalar(select(FollowUp).where(FollowUp.application_id==app.id)) else '')
        if follow_date:
            follow=db.scalar(select(FollowUp).where(FollowUp.application_id==app.id))
            if not follow:follow=FollowUp(application_id=app.id);db.add(follow)
            follow.due_date=parse_date(follow_date).isoformat();follow.done=False
            record_event(db,app,'FOLLOWUP_SCHEDULED',when=now())
        if data.event_type=='FOLLOWUP_COMPLETED':
            follow=db.scalar(select(FollowUp).where(FollowUp.application_id==app.id))
            if follow:follow.done=True
        if data.meeting_date:
            meeting=datetime.fromisoformat(data.meeting_date)
            date=(meeting if meeting.tzinfo else meeting.replace(tzinfo=ZoneInfo('Asia/Dubai'))).isoformat()
            if not db.scalar(select(Interview.id).where(Interview.application_id==app.id,Interview.date==date,Interview.stage==(data.stage or 'INTERVIEW'))):
                db.add(Interview(application_id=app.id,date=date,stage=data.stage or 'INTERVIEW',meeting_url=data.meeting_url,notes=data.notes))
                record_event(db,app,'MEETING_SCHEDULED',data.notes,source='USER')
        pending(db);db.flush();return serialize(app)

@router.post('/jobs/{job_id}/seen')
def seen(job_id:int):
    with Session.begin() as db:
        job=db.get(Job,job_id)
        if not job:raise HTTPException(404)
        job.analysis={**job.analysis,'seen_at':now(),'last_shown':now()};return {'seen':True}

@router.post('/backup')
def backup():
    from .reliability import backup_database
    from .main import task_lock
    if not task_lock.acquire(False):raise HTTPException(409,'Wait for discovery or workbook sync to finish')
    try:return {'backup':backup_database(force=True)}
    finally:task_lock.release()

def windows_schedule(action='Status',hours=6):
    import subprocess,os,json
    if os.name!='nt':return {'supported':False,'message':'Windows scheduling is available on Windows only'}
    command=Path(__file__).resolve().parents[1]/'scripts'/'schedule-discovery.ps1'
    result=subprocess.run(['powershell.exe','-NoProfile','-NonInteractive','-File',str(command),'-Action',action,'-Hours',str(hours)],capture_output=True,text=True,timeout=25,creationflags=subprocess.CREATE_NO_WINDOW)
    if result.returncode:raise ValueError('Windows could not update the scheduled task. Open Task Scheduler to review permissions; no elevated service was installed.')
    try:return {'supported':True,**json.loads(result.stdout)}
    except ValueError:return {'supported':True,'message':'Scheduled task updated. Open Windows Task Scheduler to view details.'}

@router.get('/windows-schedule')
def get_windows_schedule():return windows_schedule()

@router.post('/windows-schedule')
def set_windows_schedule(data:dict):
    if data.get('action') not in ('Enable','Disable','Remove','RunNow') or data.get('hours',6) not in (3,6,12,24):raise ValueError('Choose enable or disable and a supported interval')
    result=windows_schedule(data['action'],data.get('hours',6))
    if data['action']=='Enable':
        with Session.begin() as db:
            row=db.get(Settings,1);row.value={**row.value,'discovery_interval_hours':data.get('hours',6)}
        from .main import configure_schedule
        configure_schedule()
    return result
