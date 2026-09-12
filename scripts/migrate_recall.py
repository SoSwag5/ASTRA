"""Idempotent source changes backed by the research references; no vacancy ingestion."""
import sys,json
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from sqlalchemy import select
from backend.models import *
EXTRA=[
 ('Michael Page UAE','Recruitment agencies','https://www.michaelpage.ae/jobs/technology/united-arab-emirates','Official technology jobs'),
 ('Hays UAE','Recruitment agencies','https://www.hays.ae/jobs','Official job search'),
 ('Charterhouse Middle East','Recruitment agencies','https://www.charterhouseme.ae/jobs','Official destination; research access returned 403, manual check required'),
 ('Robert Half UAE','Recruitment agencies','https://www.roberthalf.com/ae/en','Official UAE page redirects to international contact; no live job feed verified'),
 ('Cooper Fitch','Recruitment agencies','https://cooperfitch.ae/job-seekers/','Official job-seeker guidance'),
 ('Guildhall','Recruitment agencies','https://guildhall.agency/jobs/','Official jobs page'),
 ('Mackenzie Jones','Recruitment agencies','https://www.mackenziejones.com/','Official company announcement confirms URL; direct availability needs browser review'),
 ('ENOC','Company careers','https://careers.enoc.com/','Official careers; no documented public API verified'),
 ('ADIB','Company careers','https://www.adib.com/careers','Official careers; no documented public API verified'),
 ('Mastercard','Company careers','https://careers.mastercard.com/us/en/dubai-united-arab-emirates','Official Dubai careers; no documented public API verified'),
 ('F5','Company careers','https://www.f5.com/company/careers','Official careers; no documented public API verified'),
 ('Intertec Systems','Company careers','https://www.intertecsystems.com/job-opening','Official UAE employer jobs; manual custom website'),
 ('Spire Solutions','Company careers','https://www.spiresolutions.com/','Official company root; careers endpoint unverified; weekly manual research only')]

def migrate():
 with Session.begin() as db:
  for name,group,url,verification in EXTRA:
   if db.scalar(select(JobSource).where(JobSource.name==name)):continue
   db.add(JobSource(name=name,adapter='manual',url=url,enabled=False,details={'group':group,'market':'UAE','mode':'USER_ASSISTED','watching':name!='Spire Solutions','cadence':'ROTATING' if group=='Recruitment agencies' else 'WEEKLY','last_verified':now()[:10],'verification':verification,'evidence_url':url,'permission':'Manual browser only; no extraction'}))
  for name,kind,board,url,evidence in [('Cloudflare','greenhouse','cloudflare','https://job-boards.greenhouse.io/cloudflare','https://www.cloudflare.com/careers/jobs/'),('Visa','smartrecruiters','Visa','https://jobs.smartrecruiters.com/Visa','https://www.visa.com/en-ae/careers')]:
   if not db.scalar(select(JobSource).where(JobSource.adapter==kind,JobSource.board==board)):
    db.add(JobSource(name=name,adapter=kind,board=board,url=url,enabled=True,details={'evidence_url':evidence,'permission':'Documented public posting GET API only','interval_hours':12,'last_verified':now()[:10]}))
  backpack=db.scalar(select(JobSource).where(JobSource.adapter=='ashby',JobSource.board=='backpack'))
  if backpack:
   backpack.enabled=False;backpack.details={**backpack.details,'last_error':'Public Ashby posting endpoint returned HTTP 404 on 2026-09-11. Paused; no replacement endpoint verified.','disposition':'PAUSED_NOT_FOUND','last_verified':now()[:10]}
  row=db.get(Settings,1);row.value={**row.value,'discovery_policy':row.value.get('discovery_policy','BALANCED'),'observation_started':row.value.get('observation_started',now())}
if __name__=='__main__':
 initialize();migrate();print('Source registry updated; no applications or vacancies created.')
