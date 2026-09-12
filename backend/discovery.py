"""Conservative pre-import screening; uncertain remote eligibility stays for review."""
import re

def discovery_reason(item,cfg):
    title=item.get('title','')
    def has(text,word): return bool(re.search(r'(?<!\w)'+re.escape(word)+r'(?!\w)',text,re.I))
    from .recall import role
    security=role(title,item.get('description',''),cfg)['kind']!='UNRELATED'
    configured=any(has(title,role) for role in cfg['target_roles']+cfg.get('campaign',{}).get('adjacent_roles',[]) if role.strip())
    if not security and not configured: return 'Unrelated role'
    if any(has(title,role) for role in cfg['excluded_roles'] if role.strip()): return 'Excluded role or seniority'
    if re.search(r'physical security|security guard|loss prevention',title,re.I): return 'Physical security role'
    location=item.get('location','')
    campaign=cfg.get('campaign',{})
    if campaign.get('target_country') and campaign['target_country'].lower() not in ('uae','united arab emirates'):
        if has(location,campaign['target_country']):return None
    if any(has(location,x) for x in cfg['locations'] if x.strip()): return None
    if any(x.strip().lower() in ('uae','united arab emirates') for x in cfg['locations']) and re.search(r'\b(?:Sharjah|Ajman|Fujairah|Ras Al Khaimah|Umm Al Quwain|Al Ain)\b',location,re.I): return None
    # Keep globally remote or unspecified locations for explicit eligibility review.
    if location.strip().lower() in ('','unknown','remote','worldwide','global','anywhere'):
        if cfg.get('remote_uae',True): return None
    if cfg.get('remote_uae',True) and re.search(r'\b(?:EMEA|Middle East|worldwide|global|anywhere)\b',location,re.I): return None
    return 'Outside target locations'
