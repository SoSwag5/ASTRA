"""Read public job feeds without submitting data or applications."""
import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from backend.adapters import discover
from backend.discovery import discovery_reason
from backend.models import DEFAULTS
for board in ['capital','binance','safe','crypto']:
    try:
        jobs=discover('lever',board)
        kept=[{'title':j['title'],'location':j['location']} for j in jobs if not discovery_reason(j,DEFAULTS)]
        print({'board':board,'scanned':len(jobs),'matches':kept[:15]})
    except Exception as e: print({'board':board,'error':str(e)})
