"""One bounded headless discovery. Exit 0 success/no-op, 1 failed, 2 partial, 3 busy."""
import sys,argparse
from pathlib import Path
from datetime import datetime,timedelta,timezone
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from sqlalchemy import select
from backend.models import initialize,Session,AutomationRun,settings
from backend.main import task
from backend.search_workspace import parse_date
from backend.reliability import backup_database
from backend.workbook import retry_sync

def main():
 parser=argparse.ArgumentParser();parser.add_argument('--force',action='store_true');parser.add_argument('--trigger',choices=['MANUAL','SCHEDULED','CATCHUP'],default='SCHEDULED');args=parser.parse_args()
 initialize();backup_database()
 with Session() as db:
  cfg=settings(db)
  previous=next((r for r in db.scalars(select(AutomationRun).where(AutomationRun.task=='discover',AutomationRun.status.in_(['COMPLETED','PARTIAL'])).order_by(AutomationRun.id.desc())) if r.report.get('source_id') is None),None)
  due=not previous or not parse_date(previous.updated_at) or parse_date(previous.updated_at)+timedelta(hours=cfg['discovery_interval_hours'])<=datetime.now(timezone.utc)
 if not cfg['discovery_enabled'] or cfg['autopilot']=='OFF':print('Discovery paused');return 0
 if not due and not args.force:print('Not due; one current scan is enough');retry_sync();return 0
 trigger='CATCHUP' if due and previous and args.trigger=='SCHEDULED' and parse_date(previous.updated_at)+timedelta(hours=cfg['discovery_interval_hours']*2)<datetime.now(timezone.utc) else args.trigger
 result=task('discover',scheduled_run=not args.force,trigger=trigger)
 if result.get('busy'):print('Another discovery or sync owns the lock');return 3
 retry_sync();print('Discovery:',result.get('status','FAILED'))
 return {'COMPLETED':0,'PARTIAL':2}.get(result.get('status'),1)
if __name__=='__main__':sys.exit(main())
