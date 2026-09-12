"""Small discovery controls, audit views and local feedback; no external fetching."""
from collections import Counter,defaultdict
from datetime import datetime,timedelta,timezone
from fastapi import APIRouter,HTTPException
from sqlalchemy import select
from .models import *
from .recall import evaluate,FAMILIES,POLICIES,VERSION,date
router=APIRouter(prefix='/api/recall')

@router.get('')
def overview():
 from .services import candidate
 with Session() as db:
  cfg=settings(db);jobs=list(db.scalars(select(Job)));apps=list(db.scalars(select(Application)))
  runs=list(db.scalars(select(AutomationRun).where(AutomationRun.task=='discover').order_by(AutomationRun.id.desc()).limit(120)))
  latest=next((r for r in runs if r.status!='RUNNING' and r.report.get('funnel')),None)
  shortlist=[];near=[];adjacent=[]
  applied={a.job_id for a in apps if a.applied_date};closed={a.job_id for a in apps if a.status in ('REJECTED','WITHDRAWN','ARCHIVED','HIRED')};profile=candidate(db) if db.scalar(select(CandidateProfile)) else {}
  for j in jobs:
   d=evaluate(serialize(j),cfg,profile)
   row={**serialize(j),'decision':d}
   if j.id in applied|closed or j.analysis.get('feedback',{}).get('decision')=='NOT_FOR_ME' or d['excluded']:continue
   if d['role']['kind']=='ADJACENT':adjacent.append(row)
   elif d['daily']:shortlist.append(row)
   if d['near_miss']:near.append(row)
  key=lambda r:(0 if r['decision']['uae'] else 1,{'POSTED_24H':0,'POSTED_3D':1,'POSTED_7D':2,'DATE_UNKNOWN':4,'OLDER':3}[r['decision']['freshness']],-r['decision']['priority'],r['id']*-1)
  for rows in [shortlist,near,adjacent]:rows.sort(key=key)
  scorecards=[]
  for s in db.scalars(select(JobSource).where(JobSource.adapter!='manual')):
   results=[(r,next((x for x in r.report.get('sources',[]) if x.get('id')==s.id),None)) for r in runs];results=[(r,x) for r,x in results if x]
   last=results[0][1] if results else {};owned=[j for j in jobs if j.analysis.get('discovery',{}).get('source_id')==s.id]
   scorecards.append({'id':s.id,'name':s.name,'enabled':s.enabled,'adapter':s.adapter,'health':'ERROR' if last.get('error') else 'HEALTHY' if results else 'UNTESTED','last_result':last,'stored_unique':len(owned),'reviewed':sum(bool(j.analysis.get('last_reviewed') or j.analysis.get('seen_at')) for j in owned),'applications':sum(j.id in applied for j in owned),'error_runs':sum(bool(x.get('error')) for _,x in results),'sample_runs':len(results)})
  cutoff=datetime.now(timezone.utc)-timedelta(days=7)
  observations=[{'job_id':j.id,'company':j.company,'title':j.title,'source':j.source,'source_type':j.analysis.get('source_type','AUTOMATIC' if j.analysis.get('discovery') else 'MANUAL'),'first_seen':j.analysis.get('first_seen',j.date_found),'feedback':j.analysis.get('feedback',{}),'applied':j.id in applied,'fit':j.analysis.get('recall',{}).get('fit_band','NOT_RECORDED')} for j in jobs if (date(j.date_found) and date(j.date_found)>=cutoff) or (date(j.analysis.get('feedback',{}).get('at')) and date(j.analysis['feedback']['at'])>=cutoff)]
  counts=Counter(j.company for j in jobs if not j.analysis.get('discovery'));known={s.name.casefold() for s in db.scalars(select(JobSource))}
  for row in observations:
   row['quality_label']=row['feedback'].get('quality_label','NOT_LABELLED')
   row['coverage_check']='Manual discovery; check whether an allowed feed should cover it' if row['source_type']!='AUTOMATIC' else 'Automatic source'
  return {'version':VERSION,'policy':cfg.get('discovery_policy','BALANCED'),'families':FAMILIES,'recommendations':shortlist,'near_misses':near,'adjacent':adjacent,'latest':{**serialize(latest),'report':{k:v for k,v in latest.report.items() if k!='decisions'}} if latest else None,'scorecards':scorecards,'observation':observations,'potential_employers':[{'company':c,'manual_jobs':n} for c,n in counts.items() if n>=2 and c.casefold() not in known],'feedback_summary':dict(Counter(j.analysis.get('feedback',{}).get('reason','Other') for j in jobs if j.analysis.get('feedback'))),'learning':'Feedback is local evidence. No automatic retuning or rejection-based learning.'}

@router.get('/audit/{run_id}')
def audit(run_id:int,disposition:str='',limit:int=20,offset:int=0):
 with Session() as db:
  run=db.get(AutomationRun,run_id)
  if not run:raise HTTPException(404)
  rows=run.report.get('decisions',[])
  if disposition:rows=[r for r in rows if r['disposition']==disposition]
  return {'total':len(rows),'rows':rows[max(0,offset):max(0,offset)+min(max(limit,1),100)],'funnel':run.report.get('funnel',{})}

@router.put('/policy')
def policy(data:dict):
 name=data.get('policy')
 if name not in POLICIES:raise ValueError('Choose STRICT, BALANCED or EXPLORATORY')
 with Session.begin() as db:
  row=db.get(Settings,1);row.value={**row.value,'discovery_policy':name}
  # Policy changes update current discovery decisions, never historical application snapshots.
  from .services import candidate
  p=candidate(db) if db.scalar(select(CandidateProfile)) else {}
  for j in db.scalars(select(Job)):j.analysis={**j.analysis,'recall':evaluate(serialize(j),settings(db),p)}
 return {'policy':name}

@router.post('/jobs/{job_id}/feedback')
def feedback(job_id:int,data:dict):
 if data.get('decision') not in ('INTERESTED','NOT_FOR_ME'):raise ValueError('Choose interested or not for me')
 if data.get('reason','') not in ('','too senior','wrong field','wrong location','nationality restriction','salary','company','other'):raise ValueError('Choose a supported feedback reason')
 if data.get('quality_label','') not in ('','FALSE_NEGATIVE','FALSE_POSITIVE'):raise ValueError('Choose a supported review label')
 with Session.begin() as db:
  j=db.get(Job,job_id)
  if not j:raise HTTPException(404)
  event={'decision':data['decision'],'reason':data.get('reason',''),'quality_label':data.get('quality_label',''),'at':now()}
  j.analysis={**j.analysis,'feedback':event,'last_reviewed':now(),'seen_at':now()};log(db,'Discovery feedback: '+event['decision']+' '+event['reason'],j.id)
  return event

@router.post('/paste-preview')
def paste_preview(data:dict):
 import re
 text=data.get('text','')
 if not isinstance(text,str) or len(text)>100000:raise ValueError('Paste under 100,000 characters')
 values={'description':text};mapping={'title':'title','job title':'title','company':'company','employer':'company','location':'location','source':'source','url':'job_url','job url':'job_url'}
 for line in text.splitlines():
  key,sep,value=line.partition(':')
  if sep and key.strip().lower() in mapping:values[mapping[key.strip().lower()]]=value.strip()
 if 'title' not in values:
  first=next((l.strip() for l in text.splitlines() if l.strip()),'')
  if len(first)<=200:values['title']=first
 urls=re.findall(r'https?://[^\s<>]+',text)
 if urls and 'job_url' not in values:values['job_url']=urls[0][:2000]
 return {'fields':values,'requires_confirmation':True,'network_requests':0}

@router.put('/jobs/{job_id}/source')
def preferred_source(job_id:int,data:dict):
 from urllib.parse import urlsplit
 url=data.get('preferred_application_url','');p=urlsplit(url)
 if url and (p.scheme!='https' or not p.hostname or p.username or p.password or len(url)>2000):raise ValueError('Use an HTTPS official application link without credentials')
 with Session.begin() as db:
  j=db.get(Job,job_id)
  if not j:raise HTTPException(404)
  j.analysis={**j.analysis,'discovered_via':j.analysis.get('discovered_via',j.source),'preferred_application_url':url}
  return {'saved':True}
