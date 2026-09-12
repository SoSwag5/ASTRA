"""Add campaign metadata without changing historical applications."""
import sys,json,sqlite3
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from backend.models import *
from backend.campaign import campaign_settings,pending
from backend.source_catalog import seed_catalog
from backend.reliability import backup_database
from sqlalchemy import select

def old_records():
    with sqlite3.connect(engine.url.database) as db:
        db.row_factory=sqlite3.Row
        return [dict(r) for r in db.execute('SELECT a.id,a.job_id,a.status,a.applied_date,a.confirmation,a.created_at,a.updated_at,j.company,j.title,j.notes,j.date_found FROM applications a JOIN jobs j ON a.job_id=j.id ORDER BY a.id')]

before=old_records();backup=backup_database(force=True)
initialize()
with Session.begin() as db:
    cfg=db.get(Settings,1)
    cfg.value={**cfg.value,'campaign':campaign_settings(db),'campaign_workbook':True}
    seed_catalog(db);pending(db)
    for app in db.scalars(select(Application)):
        if not db.scalar(select(ApplicationEvent.id).where(ApplicationEvent.application_id==app.id,ApplicationEvent.event_type=='HISTORY_IMPORTED')):
            db.add(ApplicationEvent(application_id=app.id,job_id=app.job_id,event_type='HISTORY_IMPORTED',occurred_at=now(),source='IMPORT',stage=app.status,message='Existing application retained during campaign upgrade. Original status: '+app.status+'. Original applied date: '+(app.applied_date or 'Not recorded')+'. Earlier events were not inferred.'))
assert before==old_records(),'Historical application changed; review backup before continuing'
print(json.dumps({'preserved_applications':len(before),'ids':[r['id'] for r in before],'backup':backup,'migration':'additive'}))
