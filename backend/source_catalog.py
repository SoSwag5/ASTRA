"""Official careers destinations; manual entries never run as discovery adapters."""
from datetime import datetime,timezone,timedelta
from urllib.parse import urlsplit,urlencode
from fastapi import HTTPException
from sqlalchemy import select
from .models import JobSource,Session,serialize,now,settings
from .campaign import router
from . import career_tracks

VERIFIED='2026-09-11'
CATALOG=[
 ('LinkedIn','Major UAE portals','https://www.linkedin.com/jobs/search/','https://www.linkedin.com/legal/user-agreement'),
 ('Indeed UAE','Major UAE portals','https://ae.indeed.com/','https://co.indeed.com/legal?hl=en'),
 ('Bayt','Major UAE portals','https://www.bayt.com/en/uae/jobs/','https://www.bayt.com/en/pages/terms/'),
 ('GulfTalent','Major UAE portals','https://www.gulftalent.com/uae/jobs','https://www.gulftalent.com/terms'),
 ('Naukrigulf','Major UAE portals','https://www.naukrigulf.com/jobs-in-uae','https://www.naukrigulf.com/terms-and-conditions'),
 ('Federal Government','Government','https://www.fahr.gov.ae/en/about-us/jobs/','https://u.ae/en/resources/government-jobs'),
 ('Abu Dhabi Government','Government','https://www.tamm.abudhabi/journeys/find-a-job/','https://pages.dmt.gov.ae/en/Careers'),
 ('Dubai Careers','Government','https://jobs.dubaicareers.ae/careersection/dubaicareers/default.ftl?lang=en','https://u.ae/en/resources/government-jobs'),
 ('Sharjah Government','Government','https://dhr.gov.ae/en/e-services/services-for-job-seekers','https://u.ae/en/resources/government-jobs'),
 ('Ajman Kawader','Government','https://www.ajmanhrd.gov.ae/kawader/home','https://www.ajman.ae/en/happiness-bundle/kawader-ajman/job-vacancies'),
 ('Ras Al Khaimah Government','Government','https://www.rak.ae/wps/portal/rak/home/citizens/employment','https://u.ae/en/resources/government-jobs'),
 ('CPX','Company careers','https://careers.g42.ai/cpx/global/en/home',''),
 ('Core42','Company careers','https://careers.g42.ai/core42/global/en/search-results',''),
 ('G42','Company careers','https://www.g42.ai/careers',''),
 ('Presight','Company careers','https://www.presight.ai/our-people',''),
 ('Help AG','Company careers','https://www.helpag.com/careers/',''),
 ('e&','Company careers','https://www.eand.com/en/careers.html',''),
 ('du','Company careers','https://www.du.ae/careers','https://www.du.ae/corporate/sitemap'),
 ('Emirates Group','Company careers','https://www.emiratesgroupcareers.com/search-and-apply/',''),
 ('Etihad Airways','Company careers','https://careers.etihad.com/',''),
 ('ADNOC','Company careers','https://jobs.adnoc.ae/us/en/',''),
 ('Mubadala','Company careers','https://www.mubadala.com/ar/careers',''),
 ('DP World','Company careers','https://www.dpworld.com/en/careers',''),
 ('Emirates NBD','Company careers','https://www.emiratesnbd.com/en/careers',''),
 ('First Abu Dhabi Bank','Company careers','https://www.bankfab.com/en-ae/about-fab/careers',''),
 ('Mashreq','Company careers','https://www.mashreq.com/en/uae/about-us/careers/jobs/',''),
 ('Deloitte','Company careers','https://www.deloitte.com/middle-east/en/careers.html',''),
 ('PwC','Company careers','https://www.pwc.com/m1/en/careers.html',''),
 ('EY','Company careers','https://careers.ey.com/home/?locale=en_US',''),
 ('KPMG','Company careers','https://kpmg.com/ae/en/careers.html',''),
 ('Accenture','Company careers','https://www.accenture.com/ae-en/careers/life-at-accenture/internships-students',''),
 ('IBM','Company careers','https://www.ibm.com/in-en/careers/search?field_keyword_05%5B0%5D=UAE',''),
 ('Microsoft','Company careers','https://careers.microsoft.com/v2/global/en/locations/dubai.html',''),
 ('Amazon / AWS','Company careers','https://www.amazon.jobs/en/search?base_query=&loc_group_id=united+arab+emirates+&loc_query=United+Arab+Emirates+',''),
 ('Oracle','Company careers','https://careers.oracle.com/en/sites/jobsearch/jobs',''),
 ('Cisco','Company careers','https://careers.cisco.com/global/en/home',''),
 ('Palo Alto Networks','Company careers','https://jobs.paloaltonetworks.com/en/',''),
 ('Fortinet','Company careers','https://www.fortinet.com/corporate/careers',''),
 ('Check Point careers','Company careers','https://www.checkpoint.com/careers/','')]

def seed_catalog(db):
    for name,group,url,evidence in CATALOG:
        if db.scalar(select(JobSource).where(JobSource.adapter=='manual',JobSource.name==name)):continue
        db.add(JobSource(name=name,adapter='manual',url=url,enabled=False,details={'group':group,'market':'UAE','mode':'USER_ASSISTED','last_verified':VERIFIED,'evidence_url':evidence or url,'permission':'User-controlled browser only; no automated extraction','verification':'Official destination found; availability and eligibility may require browser review','watching':True}))

@router.get('/portals')
def portals():
    with Session() as db:
        cfg=settings(db)
        sources=[serialize(s) for s in db.scalars(select(JobSource).where(JobSource.adapter=='manual'))]
        roles=[r for r in cfg['target_roles'] if r.strip()]
        role=roles[datetime.now(timezone.utc).timetuple().tm_yday%len(roles)] if roles else 'graduate roles'
        for s in sources:
            if s['name']=='LinkedIn':s['url']='https://www.linkedin.com/jobs/search/?'+urlencode({'keywords':role,'location':'United Arab Emirates'})
            if s['name']=='Indeed UAE':s['url']='https://ae.indeed.com/jobs?'+urlencode({'q':role,'l':'United Arab Emirates'})
        clock=datetime.now(timezone.utc)
        from .recall import date
        queries=career_tracks.search_queries(cfg) or roles or ['Graduate roles']
        for index,s in enumerate(sources):
            tier=s['details'].get('cadence','DAILY' if s['details'].get('group')=='Major UAE portals' or s['name'] in ('CPX','Core42','Help AG') else 'WEEKLY' if s['details'].get('group')=='Government' else 'ROTATING')
            days={'DAILY':1,'ROTATING':3,'WEEKLY':7}.get(tier,3)
            checked=date(s['details'].get('last_checked'));due=checked+timedelta(days=days) if checked else clock
            query=queries[(clock.timetuple().tm_yday+index)%len(queries)]
            s['cadence']=tier;s['next_check']=due.isoformat();s['due']=due<=clock;s['query']=query+' - UAE'
            if s['name']=='LinkedIn':s['url']='https://www.linkedin.com/jobs/search/?'+urlencode({'keywords':query,'location':'United Arab Emirates'})
            if s['name']=='Indeed UAE':s['url']='https://ae.indeed.com/jobs?'+urlencode({'q':query,'l':'United Arab Emirates'})
        active=[s for s in sources if s['details'].get('watching',True) and s['due']]
        active.sort(key=lambda s:(s['details'].get('last_checked',''),s['name']))
        daily=[]
        for group,limit in [('Major UAE portals',2),('Government',1),('Company careers',3),('Recruitment agencies',2)]:
            choices=[s for s in active if s['details'].get('group')==group]
            if group=='Company careers':
                core=[s for s in choices if s['cadence']=='DAILY'][:2]
                rotating=[s for s in choices if s['cadence']!='DAILY'][:max(0,limit-len(core))]
                chosen=core+rotating;chosen_ids={s['id'] for s in chosen}
                choices=chosen+[s for s in choices if s['id'] not in chosen_ids]
            daily.extend(choices[:limit])
        selected={s['id'] for s in daily}
        daily.extend([s for s in active if s['id'] not in selected][:max(0,8-len(daily))])
        return {'sources':sources,'daily':daily,'query_role':role}

@router.post('/portals/{source_id}/checked')
def checked(source_id:int):
    with Session.begin() as db:
        row=db.get(JobSource,source_id)
        if not row or row.adapter!='manual':raise HTTPException(404)
        row.details={**row.details,'last_checked':now()};return serialize(row)

@router.post('/portals')
def add_portal(data:dict):
    name=data.get('name','').strip();url=data.get('url','').strip();p=urlsplit(url)
    if not name or len(name)>200 or p.scheme!='https' or not p.hostname or p.username or p.password or len(url)>2000:raise ValueError('Enter a name and HTTPS careers link')
    with Session.begin() as db:
        row=db.scalar(select(JobSource).where(JobSource.adapter=='manual',JobSource.url==url))
        if row:return serialize(row)
        row=JobSource(name=name,url=url,adapter='manual',enabled=False,details={'group':'Company careers','mode':'USER_ASSISTED','market':'UAE','watching':True,'verification':'User-added; not independently verified'})
        db.add(row);db.flush();return serialize(row)


@router.put('/portals/{source_id}')
def configure_portal(source_id:int,data:dict):
    if data.get('cadence') not in ('DAILY','ROTATING','WEEKLY') or type(data.get('watching')) is not bool:raise ValueError('Choose a check cadence and watchlist state')
    with Session.begin() as db:
        row=db.get(JobSource,source_id)
        if not row or row.adapter!='manual':raise HTTPException(404)
        row.details={**row.details,'cadence':data['cadence'],'watching':data['watching']}
        return serialize(row)
