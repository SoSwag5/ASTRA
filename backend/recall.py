"""Versioned, local role families and inspectable discovery policy. No network calls."""
import re
from datetime import datetime,timezone
from .policy import norm,host
from . import career_tracks
VERSION='uae-recall-1'
FAMILIES=career_tracks.families(None)
ADJACENT=career_tracks.adjacent_roles(None)
UAE=['uae','u.a.e','united arab emirates','dubai','abu dhabi','sharjah','ajman','ras al khaimah','fujairah','umm al quwain','al ain','الإمارات','دبي','أبوظبي','أبو ظبي','الشارقة']
SENIOR=['senior','sr','lead','principal','staff','distinguished','manager','director','head','chief','ciso','architect','مدير','رئيس']
POLICIES={'STRICT':{'max_gap':0,'recommendation_bar':75,'near_margin':10},'BALANCED':{'max_gap':3,'recommendation_bar':70,'near_margin':15},'EXPLORATORY':{'max_gap':4,'recommendation_bar':65,'near_margin':20}}
def has(text,word):return bool(re.search(r'(?<!\w)'+re.escape(word)+r'(?!\w)',text,re.I))
def date(value):
 try:
  d=datetime.fromisoformat(str(value).replace('Z','+00:00'));return d if d.tzinfo else d.replace(tzinfo=timezone.utc)
 except (ValueError,TypeError):return None

def experience(text):
 """Retain lower/upper bounds, preference and supporting clause; never sum tenures."""
 output=[]
 for clause in re.split(r'[\n;.!?]|,(?=\s*(?:more than|at least|over)?\s*\d+\s*(?:years?|yrs?))',text):
  if not re.search(r'experience|required|preferred|desirable|minimum|at least|years?\s+(?:in|of)|خبرة',clause,re.I):continue
  if re.search(r'company|founded|in business|our history',clause,re.I) and not re.search(r'you|candidate|applicant',clause,re.I):continue
  if re.search(r'years?\s+of\s+(?:behavioral|historical|training|customer|industry|security)?\s*data',clause,re.I) and not re.search(r'experience',clause,re.I):continue
  for m in re.finditer(r'(\d{1,2})\s*(?:[-–—]|to)?\s*(\d{1,2})?\s*(\+)?\s*(?:years?|yrs?)\b',clause,re.I):
   low=int(m[1]);high=int(m[2]) if m[2] else None
   if high is not None and high<low:continue
   output.append({'minimum':low,'maximum':high,'plus':bool(m[3]),'preferred':bool(re.search(r'preferred|desirable|nice.to.have|bonus|advantage|a plus',clause,re.I)),'evidence':clause.strip()[:500]})
 mandatory=[r['minimum'] for r in output if not r['preferred']]
 return {'requirements':output,'minimum':max(mandatory,default=0),'stated':bool(output),'preferred_minimum':max((r['minimum'] for r in output if r['preferred']),default=0)}

def role(title,description='',cfg=None):
 if re.search(r'physical security|security guard|loss prevention|\bgsoc\b',title,re.I):return {'family':'Physical security','kind':'UNRELATED','signals':[]}
 if re.search(r'corporate counsel|legal counsel|attorney',title,re.I):return {'family':'Legal','kind':'UNRELATED','signals':[]}
 for family,aliases in career_tracks.families(cfg).items():
  hits=[w for w in aliases if has(title,w)]
  if hits:return {'family':family,'kind':'DIRECT','signals':hits}
 configured=[r for r in (cfg or {}).get('target_roles',[]) if r.strip() and has(title,r)]
 if configured:return {'family':'Configured target','kind':'DIRECT','signals':configured}
 hits=[w for w in career_tracks.core_skills(cfg) if has(description,w)]
 if any(has(title,w) for w in career_tracks.adjacent_roles(cfg)) and len(hits)>=2:return {'family':'Adjacent target paths','kind':'ADJACENT','signals':hits}
 if any(has(title,w) for w in (cfg or {}).get('campaign',{}).get('adjacent_roles',[]) if w.strip()):return {'family':'Configured adjacent','kind':'ADJACENT','signals':hits}
 return {'family':'Other','kind':'UNRELATED','signals':[]}

def eligibility(text,p):
 evidence=[]
 general=re.search(r'\bnationality\s*[:\n]\s*([^\n]{1,300})',text,re.I)
 if general and not re.search(r'any nationality|all nationalities|not specified|unknown',general[1],re.I) and not re.search(r'uae|emirati|united arab emirates',general[1],re.I):
  return {'state':'UNKNOWN','scope':'Listing nationality criteria require manual review','evidence':[general[1].strip()]}
 for sentence in re.split(r'[\n.!?;]',text):
  if re.search(r'(?:uae|emirati|united arab emirates).{0,20}(?:national|citizen)|(?:nationality|required nationality).{0,20}uae\s+only|\bemirati\b|مواطن',sentence,re.I):
   if re.search(r'all nationalities|any nationality|priority|preferred|encourag',sentence,re.I) and not re.search(r'only|must|required|exclusiv',sentence,re.I):continue
   evidence.append(sentence.strip()[:500])
 if not evidence:return {'state':'ELIGIBLE','scope':'No explicit nationality restriction detected; not a work-permit determination','evidence':[]}
 d=p.get('declarations',{})
 citizen=d.get('uae_citizen') if d.get('uae_citizenship_confirmed') is True else None
 return {'state':'ELIGIBLE' if citizen is True else 'INELIGIBLE' if citizen is False else 'UNKNOWN','scope':'UAE nationality restriction','evidence':evidence}

def evaluate(item,cfg,p=None,clock=None):
 p=p or {};clock=clock or datetime.now(timezone.utc);policy_name=cfg.get('discovery_policy','BALANCED');policy={**POLICIES.get(policy_name,POLICIES['BALANCED']),**cfg.get('recall_thresholds',{})}
 title=item.get('title','');desc=item.get('description','');loc=item.get('location','');text=title+'\n'+desc+'\n'+item.get('experience_requirement','')
 family=role(title,desc,cfg);exp=experience(text);elig=eligibility(text,p)
 d=p.get('declarations',{});verified=d.get('verified_relevant_experience_years') if d.get('verified_relevant_experience_years_confirmed') is True else None
 years=float(verified) if isinstance(verified,(float,int)) and 0<=verified<=60 else 0
 hard=[];soft=[]
 def add(code,evidence,blocking=False): (hard if blocking else soft).append({'code':code,'evidence':evidence[:600]})
 uae=any(has(loc,w) for w in UAE);primary=any(has(loc,w) for w in ['dubai','abu dhabi','دبي','أبو ظبي'])
 remote=bool(re.search(r'remote|worldwide|global|anywhere|emea|mena|gcc',loc+' '+item.get('remote_status',''),re.I))
 global_scope=bool(re.search(r'\bworldwide\b|\bglobal\b|\banywhere\b|\bemea\b|\bmena\b|\bgcc\b|middle east',loc,re.I))
 country_restricted=bool(re.search(r'\b(united states|usa|us only|canada|germany|united kingdom|uk only|india|singapore|australia|europe only)\b',loc,re.I))
 target=any(has(loc,w) for w in cfg.get('locations',[]) if w.strip()) or uae
 if not target:
  if cfg.get('remote_uae',True) and not country_restricted and (global_scope or loc.strip().lower() in ('','unknown','remote','worldwide','global','anywhere','hybrid','distributed','in-office','on-site','onsite')):add('REMOTE_ELIGIBILITY_UNKNOWN','Location scope does not establish a UAE workplace or permission to work remotely from UAE.')
  else:add('REMOTE_NOT_UAE_COMPATIBLE' if remote else 'NON_UAE',loc or 'Unknown location',True)
 if family['kind']=='UNRELATED':add('ROLE_NOT_RELEVANT',title,True)
 senior=any(has(title,w) for w in SENIOR)
 if senior and cfg.get('career_level','EARLY')=='EARLY':add('TOO_SENIOR',title,True)
 excluded=[w for w in cfg.get('excluded_roles',[]) if has(title,w) and w.lower() not in SENIOR]
 if excluded:add('EXCLUDED_ROLE',', '.join(excluded),True)
 if norm(item.get('company','')) in [norm(c) for c in cfg.get('blocked_companies',[])]:add('BLOCKED_COMPANY',item.get('company',''),True)
 if host(item.get('job_url','')) in cfg.get('blocked_domains',[]):add('BLOCKED_DOMAIN',host(item.get('job_url','')),True)
 if re.search(r'unpaid|commission.only',text,re.I):add('EXCLUDED_ROLE','Unpaid or commission-only',True)
 if elig['state']=='INELIGIBLE':add('EXPLICIT_NATIONALITY_RESTRICTION','; '.join(elig['evidence']),True)
 elif elig['state']=='UNKNOWN':add('ELIGIBILITY_UNKNOWN','Nationality is unconfirmed. '+ '; '.join(elig['evidence']))
 gap=max(0,exp['minimum']-years)
 if gap:
  add('EXPERIENCE_GAP',f"Listing minimum {exp['minimum']} years; verified direct professional years: {verified if verified is not None else 'not recorded'}. Policy {policy_name}, allowed review gap {policy['max_gap']} years.",gap>policy['max_gap'])
 if exp['preferred_minimum']>years:add('PREFERRED_EXPERIENCE','Preferred experience exceeds recorded profile; preference is not mandatory.')
 if not exp['stated'] and verified is None and re.search(r'production.quality|experienced|hands.on.{0,45}(?:required|experience)',desc,re.I) and not re.search(r'graduate|junior|entry|\bl1\b',title,re.I):add('EXPERIENCE_SCOPE_UNKNOWN','Professional hands-on experience is requested without a clear year range; verify the scope against your internships and projects.')
 if not desc.strip():add('DESCRIPTION_MISSING','Paste the full job description before deciding.')
 if family['kind']=='ADJACENT':add('ADJACENT_ROLE','Substantial overlapping duties in an adjacent entry route; direct target-track roles rank first.')
 posted=date(item.get('date_posted'));closing=date(item.get('closing_date'));age=(clock-posted).total_seconds()/86400 if posted else None
 if closing and closing<clock:add('EXPIRED','Explicit closing date: '+item['closing_date'],True)
 if age is not None and age<0:add('POSTING_DATE_INVALID','Future posting date; freshness is unverified.');age=None
 if age is not None and age>90:add('STALE','Posted over 90 days ago; check availability. Kept outside daily recommendations.')
 evidence=' '.join(str(f.get('text','')) for k in ['skills','employments','projects','certifications'] for f in p.get(k,[])) or p.get('raw_text','')
 core=career_tracks.core_skills(cfg)
 requested=[w for w in core if has(text,w)];matches=[w for w in requested if has(evidence,w)]
 credentials=[]
 for sentence in re.split(r'[\n.!?;]',text):
  if re.search(r'required|mandatory|must hold|preferred|advantage|possession|certifications?',sentence,re.I):
   mentioned=[c for c in career_tracks.credentials(cfg) if has(sentence,c)]
   if not (re.search(r'\bor\b|such as|like|/',sentence,re.I) and any(has(evidence,c) for c in mentioned)):
    credentials.extend(c for c in mentioned if not has(evidence,c))
 if credentials:add('CREDENTIAL_REVIEW','Credential not evidenced; confirm requirement: '+', '.join(sorted(set(credentials))))
 priority=65+(min(15,len(matches)*3))+(5 if re.search(r'junior|graduate|entry|\bl1\b|tier\s*1|associate',title,re.I) else 0)+(5 if primary else 0)
 priority-=min(18,gap*4);priority-=6 if exp['preferred_minimum']>years else 0;priority-=15 if family['kind']=='ADJACENT' else 0
 if credentials:priority-=5
 if not matches:priority-=10
 if not desc.strip():priority-=15
 threshold=policy['recommendation_bar']
 if not hard and priority<threshold:add('BELOW_SCORE_THRESHOLD',f'Priority {priority} is below {threshold}; policy {policy_name}.')
 near=not hard and 1<=len(soft)<=2 and (priority>=threshold-policy['near_margin'])
 band='EXCLUDED' if hard else 'STRETCH' if gap else 'POSSIBLE' if soft else 'STRONG' if priority>=threshold else 'POSSIBLE'
 return {'version':VERSION,'policy':policy_name,'priority':max(0,min(priority,100)),'fit_band':band,'role':family,'experience':exp,'verified_years':verified,'eligibility':elig,'hard':hard,'soft':soft,'excluded':bool(hard),'near_miss':near,'daily':not hard and not any(r['code'] in ('STALE','BELOW_SCORE_THRESHOLD','DESCRIPTION_MISSING') for r in soft),'uae':uae,'location_compatible':not any(r['code'] in ('NON_UAE','REMOTE_NOT_UAE_COMPATIBLE') for r in hard),'seniority_compatible':not senior,'age_days':round(age,1) if age is not None else None,'freshness':'POSTED_24H' if age is not None and 0<=age<=1 else 'POSTED_3D' if age is not None and age<=3 else 'POSTED_7D' if age is not None and age<=7 else 'OLDER' if age is not None else 'DATE_UNKNOWN','why_review':'Core role or security duties align; verify the stated gap before applying.' if not hard else 'Hard restriction must be resolved before recommendation.','matched_core_skills':matches}

def funnel(decisions):
 from collections import Counter
 f={'fetched':len(decisions),'uae':0,'role_relevant':0,'seniority_compatible':0,'location_compatible':0,'eligibility_not_incompatible':0,'fresh_7d':0,'date_unknown':0,'plausible':0,'strong':0,'stretch':0,'possible':0,'excluded':0,'new':0,'duplicates':0,'already_seen':0,'near_misses':0};reasons=Counter()
 for row in decisions:
  d=row['decision'];f['uae']+=d['uae'];f['role_relevant']+=d['role']['kind']!='UNRELATED';f['seniority_compatible']+=d['seniority_compatible'];f['location_compatible']+=d['location_compatible'];f['eligibility_not_incompatible']+=d['eligibility']['state']!='INELIGIBLE';f['fresh_7d']+=d['freshness'] in ('POSTED_24H','POSTED_3D','POSTED_7D');f['date_unknown']+=d['age_days'] is None;f['excluded']+=d['excluded'];f['plausible']+=not d['excluded'];f['near_misses']+=d['near_miss'];f['new']+=row.get('disposition')=='NEW';f['duplicates']+=row.get('disposition')=='DUPLICATE';f['already_seen']+=bool(row.get('already_seen'))
  if d['fit_band'].lower() in f:f[d['fit_band'].lower()]+=1 if d['fit_band']!='EXCLUDED' else 0
  if d['hard']:reasons[d['hard'][0]['code']]+=1
 stages={'Fetched':len(decisions)};remaining=decisions
 for label,codes in [('UAE or location worth verifying',{'NON_UAE','REMOTE_NOT_UAE_COMPATIBLE'}),('Target-track role or adjacent duties',{'ROLE_NOT_RELEVANT','EXCLUDED_ROLE'}),('Seniority plausible',{'TOO_SENIOR'}),('Experience plausible under policy',{'EXPERIENCE_GAP'}),('No confirmed eligibility conflict',{'EXPLICIT_NATIONALITY_RESTRICTION'}),('Not closed or blocked',{'EXPIRED','BLOCKED_COMPANY','BLOCKED_DOMAIN'})]:
  remaining=[r for r in remaining if not any(e['code'] in codes for e in r['decision']['hard'])];stages[label]=len(remaining)
 stages['Daily review candidates']=sum(r['decision']['daily'] for r in remaining)
 stages['New daily review candidates']=sum(r['decision']['daily'] and r.get('disposition')=='NEW' for r in remaining)
 return {'counts':f,'stages':stages,'primary_exclusions':dict(reasons),'signal_counts':dict(Counter(r['code'] for row in decisions for r in row['decision']['hard']+row['decision']['soft'])),'definition':'Attribute counts overlap; stages are successive. Primary exclusions are mutually exclusive. plausible + excluded = fetched. new + duplicates = persisted plausible rows on successful sources; errors are explicit.'}
