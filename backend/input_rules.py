"""Positive validation for legacy configuration and record editing surfaces."""
import json
import math
import re
from urllib.parse import urlsplit


def settings_input(cfg, defaults):
    for key, default in defaults.items():
        value=cfg[key]
        if type(value) is not type(default): raise ValueError('Invalid setting type: '+key)
        if isinstance(value,str) and len(value)>2000: raise ValueError('Setting is too long: '+key)
        if isinstance(value,list) and (len(value)>100 or any(not isinstance(v,str) or len(v)>500 for v in value)):
            raise ValueError('Use at most 100 short text values: '+key)
    for key in ('minimum_score','high_priority','maybe_score'):
        if not 0<=cfg[key]<=100:raise ValueError('Scores must be from 0 to 100')
    if not 0<=cfg['followup_days']<=365 or not 0<=cfg['salary_minimum']<=1_000_000_000:
        raise ValueError('Invalid follow-up interval or salary preference')
    if not 1<=cfg['wizard_step']<=10:raise ValueError('Invalid setup step')
    if cfg['cover_letter'] not in ('required','always') or cfg['cv_template']!='ATS':raise ValueError('Unsupported document option')
    if cfg['assessment_mode'] not in ('NEW','SHADOW','LEGACY'):raise ValueError('Unsupported assessment mode')
    if set(cfg['schedule'])!=set(defaults['schedule']):raise ValueError('Invalid scheduled task set')
    if any(type(v) not in (int,float) or not math.isfinite(v) or not 0<=v<=10000 for v in cfg['weights'].values()):
        raise ValueError('Weights must be finite nonnegative numbers no greater than 10,000')


def record_input(kind,data,model):
    data=dict(data)
    columns={c.name:c for c in model.__table__.columns}
    if not data.get('id'):
        for key,column in columns.items():
            if not column.nullable and not column.primary_key and column.default is None and key not in data:
                raise ValueError('Missing required record field: '+key)
    # UI roundtrips include timestamps; these never become writable attributes.
    for key,value in data.items():
        if key in ('created_at','updated_at','normalized_question'):continue
        if key not in columns:raise ValueError('Unknown record field')
        expected=columns[key].type.python_type
        if value is None and columns[key].nullable:continue
        if type(value) is not expected:raise ValueError('Invalid record field type: '+key)
        if expected is str and len(value)>20000:raise ValueError('Record text exceeds 20,000 characters')
        if expected is dict and len(json.dumps(value,allow_nan=False))>30000:raise ValueError('Record configuration is too large')
        if expected is int and value<=0:raise ValueError('Record IDs must be positive integers')
    for key in ('url','meeting_url'):
        if data.get(key):
            url=urlsplit(data[key])
            if url.scheme not in ('https','http') or not url.hostname or url.username or url.password or len(data[key])>2000:
                raise ValueError('Use a web link without credentials')
    for key in ('date','due_date'):
        if key in data:
            from .search_workspace import parse_date
            if not parse_date(data[key]):raise ValueError('Use a valid date')
    if kind=='sources':
        if 'adapter' in data and data['adapter'] not in ('manual','generic','greenhouse','lever','ashby','smartrecruiters'):
            raise ValueError('Unsupported source adapter')
        if data.get('board') and not re.fullmatch(r'[a-zA-Z0-9_-]{1,100}',data['board']):raise ValueError('Invalid public board identifier')
    if kind=='answers' and ('question' in data and not data['question'].strip()):raise ValueError('Enter a question')
    if kind=='interviews' and data.get('timezone'):
        from zoneinfo import ZoneInfo,ZoneInfoNotFoundError
        try:ZoneInfo(data['timezone'])
        except (ValueError,ZoneInfoNotFoundError):raise ValueError('Choose an IANA timezone') from None
    return data
