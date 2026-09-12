import sys,shutil
from sqlalchemy import select
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from backend.models import *
from backend.services import import_cv,import_tracker
initialize()
print('Local database initialized. Existing records are preserved. Upload a CV explicitly in the workspace; setup never imports personal files automatically.')
