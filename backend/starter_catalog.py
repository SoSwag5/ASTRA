"""Additive bundled destinations. Startup never contacts a website."""
import json
from pathlib import Path
from urllib.parse import urlsplit
from sqlalchemy import inspect, select
from .models import JobSource, Settings


def catalog():
    payload = json.loads(Path(__file__).with_name('source_catalog_data.json').read_text(encoding='utf-8-sig'))
    rows = payload['sources']
    seen = set()
    for row in rows:
        identity = (row['name'], row['url'])
        if identity in seen:
            raise ValueError('Duplicate bundled destination')
        seen.add(identity)
        for key in ('url', 'evidence_url'):
            parsed = urlsplit(row[key])
            if parsed.scheme != 'https' or not parsed.hostname or parsed.username or parsed.password:
                raise ValueError('Invalid bundled destination')
        if row['mode'] not in ('MANUAL', 'PUBLIC_FEED'):
            raise ValueError('Unknown destination mode')
        if row['mode'] == 'PUBLIC_FEED' and row['adapter'] not in ('greenhouse', 'ashby'):
            raise ValueError('Unsupported starter feed')
    return rows


def is_fresh_workspace(db):
    return not inspect(db.get_bind()).has_table(Settings.__tablename__) or db.get(Settings, 1) is None


def seed_starter_catalog(db, *, fresh_install=False):
    """Keep existing identifiers, URLs and paused/disabled preferences intact."""
    existing = list(db.scalars(select(JobSource)))
    for item in catalog():
        feed = item['mode'] == 'PUBLIC_FEED'
        adapter = item['adapter'] if feed else 'manual'
        row = next((r for r in existing if
                    (feed and r.adapter == adapter and r.board == item['board']) or
                    (not feed and r.adapter == 'manual' and (r.name == item['name'] or r.url == item['url']))), None)
        if row is not None:
            # A locally edited destination must not inherit somebody else's check.
            if row.url != item['url']:
                continue
            details = dict(row.details or {})
        else:
            row = JobSource(name=item['name'], adapter=adapter, board=item.get('board', ''),
                            url=item['url'], enabled=feed and fresh_install)
            db.add(row)
            existing.append(row)
            details = {'watching': True}
        good = item['route_status'] in ('REACHABLE_PAGE', 'PUBLIC_FEED_OK')
        row.details = {**details, 'catalog_name': item['name'], 'group': item['group'],
                       'market': 'UAE', 'mode': 'PUBLIC_FEED' if feed else 'USER_ASSISTED',
                       'route_status': item['route_status'], 'route_checked_at': item['checked_at'],
                       'last_verified': item['checked_at'][:10] if good else '',
                       'evidence_url': item['evidence_url'], 'verification': item['note'],
                       'permission': 'Documented public posting GET API only' if feed else
                                     'User-controlled browser only; no automated extraction'}
