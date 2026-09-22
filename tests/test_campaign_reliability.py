import os,subprocess,sys
from pathlib import Path
import pytest
from backend.policy import duplicate

def isolated(tmp_path,script):
    data=tmp_path/'data';env={**os.environ,'HUNTER_DATA_DIR':str(data),'DATABASE_URL':f'sqlite:///{data/"isolated.db"}','APP_TOKEN':''}
    result=subprocess.run([sys.executable,'-c',script],capture_output=True,text=True,env=env,timeout=90)
    assert result.returncode==0,result.stdout+result.stderr

def test_distinct_requisitions_stay_distinct():
    base={'company':'Example','title':'SOC Analyst','location':'Dubai','source':'Lever'}
    assert not duplicate({**base,'source_job_id':'A'},{**base,'source_job_id':'B'})

def test_process_lock_and_backup_restore(tmp_path):
    isolated(tmp_path,r'''
import subprocess,sys,sqlite3,shutil
from backend.models import *
from backend.reliability import ProcessLock,backup_database
initialize()
with Session.begin() as db:
    j=Job(company='Synthetic',title='SOC',notes='Keep Arabic العربية');db.add(j);db.flush();db.add(Application(job_id=j.id,status='APPLIED',applied_date='2026-08-01'))
lock=ProcessLock();assert lock.acquire(False)
child=subprocess.run([sys.executable,'-c','from backend.reliability import ProcessLock; p=ProcessLock(); print(p.acquire(False))'],capture_output=True,text=True)
assert child.stdout.strip()=='False';lock.release();assert lock.acquire(False);lock.release()
name=backup_database(True);restored=DATA/'backups'/'restored-test.db';shutil.copy2(DATA/'backups'/name,restored)
with sqlite3.connect(restored) as db:
    assert db.execute('PRAGMA integrity_check').fetchone()[0]=='ok'
    assert db.execute('SELECT notes FROM jobs').fetchone()[0]=='Keep Arabic العربية'
    assert db.execute('SELECT COUNT(*) FROM applications').fetchone()[0]==1
''')

def test_retry_after_excel_lock_and_committed_tracking(tmp_path):
    isolated(tmp_path,r'''
from backend.models import *
from backend.campaign import track,TrackInput
import backend.workbook as wb
initialize()
with Session.begin() as db:
    cfg=db.get(Settings,1);cfg.value={**cfg.value,'campaign_workbook':True}
    j=Job(company='Synthetic',title='SOC Analyst',location='Dubai');db.add(j);db.flush();job_id=j.id
original=wb.export_workbook
def locked(*args):raise PermissionError('Synthetic lock')
wb.export_workbook=locked
track(job_id,TrackInput(stage='APPLIED',cv_version='SOC',date='2026-08-01'))
wb.retry_sync()
with Session() as db:
    assert db.query(Application).count()==1
    s=db.get(WorkbookSync,1);assert s.revision>s.exported_revision and s.error
wb.export_workbook=original;wb.retry_sync()
with Session() as db:
    s=db.get(WorkbookSync,1);assert s.revision==s.exported_revision and not s.error
''')

def test_meeting_followup_history_and_future_validation(tmp_path):
    isolated(tmp_path,r'''
from backend.models import *
from backend.campaign import track,TrackInput
from sqlalchemy import select
initialize()
with Session.begin() as db:
    j=Job(company='Synthetic',title='SOC Analyst');db.add(j);db.flush();jid=j.id
track(jid,TrackInput(stage='APPLIED',cv_version='Master',date='2026-08-01'))
track(jid,TrackInput(stage='ASSESSMENT',meeting_date='2027-01-01T09:00',meeting_url='https://example.com/meeting'))
track(jid,TrackInput(event_type='FOLLOWUP_COMPLETED'))
with Session() as db:
    meeting=db.scalar(select(Interview));assert meeting.date.endswith('+04:00')
    assert db.scalar(select(FollowUp)).done
try:track(jid,TrackInput(stage='OFFER',date='2999-01-01'))
except ValueError:pass
else:raise AssertionError('Future employer outcome accepted')
''')

@pytest.mark.parametrize('location',['Remote United States','Remote Germany','Remote Canada'])
def test_country_remote_not_uae(location):
    from backend.discovery import discovery_reason
    from backend.models import DEFAULTS
    assert discovery_reason({'title':'SOC Analyst','location':location},DEFAULTS)=='Outside target locations'

def test_scheduled_source_cadence_and_manual_boundary(tmp_path):
    isolated(tmp_path,r'''
from backend.models import *
from backend.main import task
import backend.main as main
initialize()
with Session.begin() as db:
    db.add(JobSource(name='Manual',adapter='manual',enabled=True,url='https://www.linkedin.com/jobs'))
    db.add(JobSource(name='Recent',adapter='lever',board='synthetic',enabled=True,details={'last_success':now(),'interval_hours':24}))
def forbidden(*args):raise AssertionError('Should not contact a source')
main.discover=forbidden
result=task('discover',scheduled_run=True)
# Discovery is manual-only: a scheduled call is refused and nothing is fetched or recorded.
assert result.get('refused') is True,result
with Session() as db: assert db.query(AutomationRun).count()==0
''')
