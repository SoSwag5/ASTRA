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
 """Legacy-shaped experience summary, now backed by backend.experience's
 scoped clause parser (issue #41). Kept for callers that still expect the
 old flattened dict shape (a single 'minimum', not scoped clauses) --
 backend.assessment consumes backend.experience.parse() directly instead.
 """
 from . import experience as _experience_module
 req=_experience_module.parse(text)
 requirements=[{'minimum':c.minimum_years,'maximum':c.maximum_years,'plus':c.plus,'preferred':c.necessity==_experience_module.PREFERRED,'evidence':c.original_text} for c in req.clauses]
 return {'requirements':requirements,'minimum':req.effective_required_minimum if req.effective_required_minimum is not None else 0,'stated':req.stated,'preferred_minimum':req.effective_preferred_minimum if req.effective_preferred_minimum is not None else 0}

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

def evaluate_legacy(item,cfg,p=None,clock=None):
 """Pre-issue-#41 authoritative evaluator. Retained ONLY for #42 shadow
 comparison and rollback (assessment_mode == 'LEGACY') -- see
 docs/architecture/FIT_ASSESSMENT.md. Its TOO_SENIOR/EXPERIENCE_GAP/
 ROLE_NOT_RELEVANT hard-rejection behavior is exactly the over-aggressive
 false-positive pattern issue #41 was written to retire; nothing new should
 call this expecting authoritative product behavior.
 """
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
 # Code sets include both issue #41's hard-reject taxonomy and the retired
 # legacy codes (only ever produced by evaluate_legacy/assessment_mode
 # LEGACY), so this funnel stays meaningful in every assessment mode.
 for label,codes in [('UAE or location worth verifying',{'NON_UAE','REMOTE_NOT_UAE_COMPATIBLE','GEO_INCOMPATIBLE'}),('Target-track role or adjacent duties',{'ROLE_NOT_RELEVANT','EXCLUDED_ROLE','DOMAIN_INCOMPATIBLE'}),('Seniority plausible',{'TOO_SENIOR','EXTREME_LEADERSHIP_MISMATCH'}),('Experience plausible under policy',{'EXPERIENCE_GAP'}),('No confirmed eligibility conflict',{'EXPLICIT_NATIONALITY_RESTRICTION','CONFIRMED_ELIGIBILITY_CONFLICT'}),('Not closed or blocked',{'EXPIRED','BLOCKED_COMPANY','BLOCKED_DOMAIN','USER_BLOCKED'})]:
  remaining=[r for r in remaining if not any(e['code'] in codes for e in r['decision']['hard'])];stages[label]=len(remaining)
 stages['Daily review candidates']=sum(r['decision']['daily'] for r in remaining)
 stages['New daily review candidates']=sum(r['decision']['daily'] and r.get('disposition')=='NEW' for r in remaining)
 return {'counts':f,'stages':stages,'primary_exclusions':dict(reasons),'signal_counts':dict(Counter(r['code'] for row in decisions for r in row['decision']['hard']+row['decision']['soft'])),'definition':'Attribute counts overlap; stages are successive. Primary exclusions are mutually exclusive. plausible + excluded = fetched. new + duplicates = persisted plausible rows on successful sources; errors are explicit.'}

def _legacy_shape(new,item,cfg,clock):
 """Project a backend.assessment FitAssessment dict into the pre-#41 decision
 shape every existing caller (recall_api, services.score, main.py's discover
 loop, funnel()) already knows how to read, so #41 does not require a
 simultaneous rewrite of every consumer. `fit_assessment` carries the full
 structured record for anything that wants the richer #41 data directly.
 """
 hard=[{'code':new['hard_reject']['code'],'evidence':new['hard_reject']['explanation'][:600]}] if new['hard_reject'] else []
 # Deliberately excludes new['uncertainty'] (e.g. "posted date unknown"):
 # an absence of information must stay informational, never gate a
 # confident recommendation the way a real penalty does (non-negotiable
 # outcomes #5/#6/#14) -- see docs/architecture/FIT_ASSESSMENT.md.
 soft=[{'code':p['code'],'evidence':p['explanation'][:600]} for p in new['penalties']]
 band={'STRONG':'STRONG','GOOD':'STRONG','STRETCH':'STRETCH','LOW':'POSSIBLE','REJECTED':'EXCLUDED'}[new['bucket']]
 role_kind={'CORE':'DIRECT','CUSTOM':'DIRECT','ADJACENT':'ADJACENT','CONTEXTUAL':'ADJACENT','AMBIGUOUS':'ADJACENT','OUTSIDE':'UNRELATED'}[new['match_type']]
 geo=new['geography'];excluded=bool(new['hard_reject'])
 elig_code=new['hard_reject']['code'] if new['hard_reject'] else None
 elig_state='INELIGIBLE' if elig_code=='CONFIRMED_ELIGIBILITY_CONFLICT' else ('UNKNOWN' if any('ligibility' in u for u in new['uncertainty']) else 'ELIGIBLE')
 posted=date(item.get('date_posted'));closing=date(item.get('closing_date'));age=(clock-posted).total_seconds()/86400 if posted else None
 if closing and closing<clock and not excluded:soft.append({'code':'EXPIRED','evidence':'Explicit closing date: '+str(item.get('closing_date'))})
 if age is not None and age<0:age=None
 freshness='POSTED_24H' if age is not None and 0<=age<=1 else 'POSTED_3D' if age is not None and age<=3 else 'POSTED_7D' if age is not None and age<=7 else 'OLDER' if age is not None else 'DATE_UNKNOWN'
 return {'version':VERSION,'policy':cfg.get('discovery_policy','BALANCED'),'priority':new['score'] if new['score'] is not None else 0,
  'fit_band':band,'role':{'family':new['role_family'],'kind':role_kind,'signals':new['matched_tracks'] or new['matched_skills'][:5]},
  'experience':{'requirements':[{'minimum':c['minimum_years'],'maximum':c['maximum_years'],'plus':c['plus'],'preferred':c['necessity']=='PREFERRED','evidence':c['original_text']} for c in new['experience']['clauses']],
   'minimum':new['experience']['effective_required_minimum'] or 0,'stated':new['experience']['stated'],'preferred_minimum':new['experience']['effective_preferred_minimum'] or 0},
  'verified_years':None,'eligibility':{'state':elig_state,'scope':'Issue #41 assessment','evidence':new['hard_reject']['evidence_refs'] if elig_code=='CONFIRMED_ELIGIBILITY_CONFLICT' else []},
  'hard':hard,'soft':soft,'excluded':excluded,'near_miss':not excluded and new['bucket']=='STRETCH',
  'daily':not excluded and new['bucket'] in ('STRONG','GOOD'),'uae':geo['compatibility']=='COMPATIBLE',
  'location_compatible':geo['compatibility']!='INCOMPATIBLE','seniority_compatible':new['seniority']['title_level'] not in ('LEAD','MANAGER','EXECUTIVE'),
  'age_days':round(age,1) if age is not None else None,'freshness':freshness,'why_review':new['explanation'],
  'matched_core_skills':new['matched_skills'],'fit_assessment':new}

def evaluate(item,cfg,p=None,clock=None):
 """Issue #41 authoritative evaluator. Deterministic, local, explainable --
 see backend.assessment. Retains the pre-#41 decision dict shape so every
 existing caller keeps working unchanged; the full structured result is
 available under the returned dict's 'fit_assessment' key.

 assessment_mode (Settings, default NEW):
 - NEW: this engine is authoritative; evaluate_legacy() is also computed and
   attached as 'legacy_shadow' for #42 comparison, never for a product decision.
 - SHADOW: evaluate_legacy() is authoritative; this engine still runs and is
   attached under 'fit_assessment' for diagnostics only.
 - LEGACY: rollback path -- evaluate_legacy() only, unchanged.
 """
 cfg=cfg or {};p=p or {};clock=clock or datetime.now(timezone.utc)
 mode=cfg.get('assessment_mode','NEW')
 if mode=='LEGACY':return evaluate_legacy(item,cfg,p,clock)
 from . import assessment
 new=assessment.assess(item,cfg,p,clock)
 if mode=='SHADOW':
  legacy=evaluate_legacy(item,cfg,p,clock);legacy['fit_assessment']=new;return legacy
 result=_legacy_shape(new,item,cfg,clock)
 result['legacy_shadow']=evaluate_legacy(item,cfg,p,clock)
 return result
