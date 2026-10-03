import sys,shutil
from sqlalchemy import select
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from backend.models import *
from backend.services import import_cv,import_tracker
from backend.starter_catalog import is_fresh_workspace,seed_starter_catalog
# The installer creates the Settings row, so freshness must be read before it does.
# Only a truly new workspace enables the starter feeds; existing ones get them paused.
with Session() as db: fresh_install=is_fresh_workspace(db)
initialize()
with Session.begin() as db: seed_starter_catalog(db,fresh_install=fresh_install)
print('Local database initialized. Existing records are preserved. Upload a CV explicitly in the workspace; setup never imports personal files automatically.')
