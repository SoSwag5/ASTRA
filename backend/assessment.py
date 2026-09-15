"""Issue #41: deterministic, local, explainable fit assessment.

Score means RANKING PRIORITY -- never an interview, hiring, or success
probability. No LLM/network call is authoritative for a decision made here.
See docs/architecture/FIT_ASSESSMENT.md for the full model.
"""
import hashlib
import json
import re
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone

from . import career_tracks
from . import experience as experience_module
from .experience import REQUIRED, PREFERRED, OVERALL

SCHEMA_VERSION = 'fit-assessment-1'
RULESET_VERSION = 'fit-rules-1'
SCORE_KIND = 'RANKING_PRIORITY'

STRONG, GOOD, STRETCH, LOW, REJECTED = 'STRONG', 'GOOD', 'STRETCH', 'LOW', 'REJECTED'
BUCKET_FLOORS = [(80, STRONG), (65, GOOD), (45, STRETCH), (0, LOW)]

DOMAIN_INCOMPATIBLE = 'DOMAIN_INCOMPATIBLE'
GEO_INCOMPATIBLE = 'GEO_INCOMPATIBLE'
EXTREME_LEADERSHIP_MISMATCH = 'EXTREME_LEADERSHIP_MISMATCH'
INVALID_JOB = 'INVALID_JOB'
CONFIRMED_ELIGIBILITY_CONFLICT = 'CONFIRMED_ELIGIBILITY_CONFLICT'
USER_BLOCKED = 'USER_BLOCKED'
HARD_REASONS = {DOMAIN_INCOMPATIBLE, GEO_INCOMPATIBLE, EXTREME_LEADERSHIP_MISMATCH,
                INVALID_JOB, CONFIRMED_ELIGIBILITY_CONFLICT, USER_BLOCKED}

CORE, ADJACENT, CONTEXTUAL, AMBIGUOUS, OUTSIDE, CUSTOM = 'CORE', 'ADJACENT', 'CONTEXTUAL', 'AMBIGUOUS', 'OUTSIDE', 'CUSTOM'

ENTRY, MID, SENIOR_IC, LEAD, MANAGER, EXECUTIVE, TITLE_UNKNOWN = \
    'ENTRY', 'MID', 'SENIOR_IC', 'LEAD', 'MANAGER', 'EXECUTIVE', 'UNKNOWN'
NONE_EVIDENCED, TECHNICAL, TEAM, MULTI_TEAM, ORGANIZATIONAL, SCOPE_UNKNOWN = \
    'NONE_EVIDENCED', 'TECHNICAL', 'TEAM', 'MULTI_TEAM', 'ORGANIZATIONAL', 'UNKNOWN'

COMPATIBLE, INCOMPATIBLE, GEO_UNKNOWN = 'COMPATIBLE', 'INCOMPATIBLE', 'UNKNOWN'

POSITIVE, PENALTY, UNCERTAINTY = 'POSITIVE', 'PENALTY', 'UNCERTAINTY'

WEIGHTS = {'domain': 25, 'career_track': 15, 'profile_evidence': 20, 'experience': 15,
           'seniority': 10, 'geography': 10, 'freshness': 5}
assert sum(WEIGHTS.values()) == 100


def _has(text, phrase):
    return bool(re.search(r'(?<!\w)' + re.escape(phrase) + r'(?!\w)', text or '', re.I))


def _any(text, phrases):
    return [p for p in phrases if _has(text, p)]


@dataclass
class Signal:
    code: str
    label: str
    polarity: str
    component: str
    points_delta: float
    evidence_refs: list = field(default_factory=list)
    explanation: str = ''
    confidence: float = 0.5

    def to_dict(self):
        return asdict(self)


def signal(code, label, polarity, component, points_delta=0.0, evidence_refs=None, explanation='', confidence=0.5):
    return Signal(code, label, polarity, component, points_delta, list(evidence_refs or []), explanation[:600], confidence)


# ---------------------------------------------------------------------------
# Domain / role assessment
# ---------------------------------------------------------------------------

def assess_domain(title, description, cfg):
    title = title or ''
    description = description or ''
    cfg = cfg or {}
    custom_roles = [r.strip() for r in cfg.get('custom_target_roles', []) if r.strip()]
    custom_hit = [r for r in custom_roles if _has(title, r)]
    if custom_hit:
        return {'match_type': CUSTOM, 'matched_tracks': [], 'primary_track': 'Custom target',
                'role_family': 'Custom target', 'title_evidence': custom_hit, 'body_evidence': [],
                'contradictory_evidence': [], 'confidence': 0.9, 'hard_incompatible': False}

    families = career_tracks.families(cfg)
    for family, aliases in families.items():
        hits = _any(title, aliases)
        if hits:
            return {'match_type': CORE, 'matched_tracks': [family], 'primary_track': family,
                    'role_family': family, 'title_evidence': hits, 'body_evidence': [],
                    'contradictory_evidence': [], 'confidence': 0.9, 'hard_incompatible': False}

    adjacent = career_tracks.adjacent_roles(cfg)
    core_skills = career_tracks.core_skills(cfg)
    body_hits = _any(description, core_skills)
    if any(_has(title, role) for role in adjacent) and len(body_hits) >= 2:
        return {'match_type': ADJACENT, 'matched_tracks': [], 'primary_track': 'Adjacent target paths',
                'role_family': 'Adjacent target paths', 'title_evidence': [], 'body_evidence': body_hits,
                'contradictory_evidence': [], 'confidence': 0.7, 'hard_incompatible': False}

    unrelated_title = _any(title, career_tracks.UNRELATED_PROFESSIONS)
    physical_security = _any(title + ' ' + description, career_tracks.PHYSICAL_SECURITY_SIGNALS)
    technical_context = _any(title + ' ' + description, career_tracks.TECHNICAL_SECURITY_CONTEXT)

    # Contextual/ambiguous technical roles: title alone is inconclusive, but
    # responsibility text carries real signal either way. "Security Officer"
    # with SIEM/IAM/SOC duties is technical; the same title with patrol/
    # premises duties and no technical evidence is physical security.
    if technical_context and not unrelated_title:
        return {'match_type': CONTEXTUAL, 'matched_tracks': [], 'primary_track': 'Contextual technical role',
                'role_family': 'Contextual technical role', 'title_evidence': [], 'body_evidence': technical_context,
                'contradictory_evidence': physical_security, 'confidence': 0.55, 'hard_incompatible': False}

    if physical_security and not technical_context:
        strong_unrelated = True
    elif unrelated_title and not body_hits and not technical_context:
        strong_unrelated = True
    else:
        strong_unrelated = False

    if body_hits:
        return {'match_type': AMBIGUOUS, 'matched_tracks': [], 'primary_track': 'Other',
                'role_family': 'Other', 'title_evidence': [], 'body_evidence': body_hits,
                'contradictory_evidence': [], 'confidence': 0.3, 'hard_incompatible': False}

    return {'match_type': OUTSIDE, 'matched_tracks': [], 'primary_track': 'Other', 'role_family': 'Other',
            'title_evidence': unrelated_title or physical_security, 'body_evidence': [],
            'contradictory_evidence': [], 'confidence': 0.6 if strong_unrelated else 0.2,
            'hard_incompatible': strong_unrelated}


# ---------------------------------------------------------------------------
# Seniority assessment
# ---------------------------------------------------------------------------

_TITLE_LEVELS = [
    (ENTRY, [r'\bintern\b', r'\bgraduate\b', r'\btrainee\b', r'\bjunior\b', r'entry.level', r'\bassociate\b']),
    (EXECUTIVE, [r'\bvice president\b', r'\bvp\b', r'\bchief\b', r'\bciso\b', r'\bcto\b', r'\bcio\b', r'\bhead of\b']),
    (MANAGER, [r'\bmanager\b', r'\bhead\b', r'\bdirector\b']),
    (LEAD, [r'\blead\b', r'\bprincipal\b', r'\barchitect\b', r'\bstaff\b']),
    (SENIOR_IC, [r'\bsenior\b', r'\bsr\.?\b', r'\bdistinguished\b']),
]

_STRONG_PEOPLE_EVIDENCE = re.compile(
    r'direct reports?|manage(?:s|d)? a team of \d+|team of \d{2,}|hiring and firing|'
    r'performance (?:review|management)|p&l ownership|budget ownership|department (?:budget|ownership)|'
    r'organi[sz]ational (?:ownership|strategy)|responsible for the (?:department|division) budget', re.I)
_ENTERPRISE_ARCHITECTURE_EVIDENCE = re.compile(
    r'enterprise[- ]wide architecture|architecture strategy across the (?:organi[sz]ation|company|business)|'
    r'technology strategy for the (?:organi[sz]ation|company|business)|enterprise architecture (?:authority|ownership)', re.I)
_TEAM_EVIDENCE = re.compile(r'manage(?:s|d)? a team|leads? a team|team lead(?:ership)?|\bdirect reports?\b', re.I)
_MULTI_TEAM_EVIDENCE = re.compile(r'multiple teams|cross.team leadership|leads? multiple squads|several teams', re.I)
_TECHNICAL_SCOPE_EVIDENCE = re.compile(r'technical leadership|owns? the architecture|leads? the design', re.I)

_SENIORITY_POINTS = {ENTRY: 10, MID: 9, SENIOR_IC: 7, TITLE_UNKNOWN: 8}


def assess_seniority(title, description, exp_req):
    title = title or ''
    description = description or ''
    title_level = MID
    title_signals = []
    for level, patterns in _TITLE_LEVELS:
        hits = [p.strip('\\b') for p in patterns if re.search(p, title, re.I)]
        if hits:
            title_level = level
            title_signals = hits
            break

    if _MULTI_TEAM_EVIDENCE.search(description):
        leadership_scope, responsibility_signals = MULTI_TEAM, ['multiple teams evidenced']
    elif _STRONG_PEOPLE_EVIDENCE.search(description) or re.search(r'organi[sz]ational (?:ownership|strategy)', description, re.I):
        leadership_scope, responsibility_signals = ORGANIZATIONAL, ['organizational ownership evidenced']
    elif _TEAM_EVIDENCE.search(description):
        leadership_scope, responsibility_signals = TEAM, ['team leadership evidenced']
    elif _TECHNICAL_SCOPE_EVIDENCE.search(description):
        leadership_scope, responsibility_signals = TECHNICAL, ['technical scope evidenced']
    else:
        leadership_scope, responsibility_signals = NONE_EVIDENCED, []

    strong_people_evidence = bool(_STRONG_PEOPLE_EVIDENCE.search(description))
    enterprise_architecture = bool(_ENTERPRISE_ARCHITECTURE_EVIDENCE.search(description))
    mandatory_experience = exp_req.effective_required_minimum

    extreme = False
    conflicting_signals = []
    if title_level in (MANAGER, EXECUTIVE) and leadership_scope == ORGANIZATIONAL and strong_people_evidence:
        extreme = True
    elif title_level == LEAD and mandatory_experience is not None and mandatory_experience >= 10 and enterprise_architecture:
        extreme = True
    elif title_level in (MANAGER, EXECUTIVE) and leadership_scope in (NONE_EVIDENCED, SCOPE_UNKNOWN):
        conflicting_signals.append('Management-shaped title with no confirmed people/organizational responsibility evidence')

    if title_level == EXECUTIVE:
        points = 1 if extreme else (2 if leadership_scope == ORGANIZATIONAL else 4)
    elif title_level == MANAGER:
        points = 2 if extreme else (4 if leadership_scope in (TEAM, MULTI_TEAM, ORGANIZATIONAL) else 6)
    elif title_level == LEAD:
        points = 4 if extreme else (5 if leadership_scope in (TEAM, MULTI_TEAM, ORGANIZATIONAL) else 6)
    else:
        points = _SENIORITY_POINTS.get(title_level, 8)

    return {'title_level': title_level, 'leadership_scope': leadership_scope,
            'title_signals': title_signals, 'responsibility_signals': responsibility_signals,
            'conflicting_signals': conflicting_signals, 'mandatory_experience': mandatory_experience,
            'confidence': 0.7 if title_signals else 0.4, 'fit_points': points,
            'extreme_leadership_mismatch': extreme}


# ---------------------------------------------------------------------------
# Geography assessment
# ---------------------------------------------------------------------------

UAE_WORDS = ['uae', 'u.a.e', 'united arab emirates', 'dubai', 'abu dhabi', 'sharjah', 'ajman',
             'ras al khaimah', 'fujairah', 'umm al quwain', 'al ain']
_GLOBAL_SCOPE_RE = re.compile(r'\bworldwide\b|\bglobal\b|\banywhere\b|\bemea\b|\bmena\b|\bgcc\b|middle east', re.I)
_US_ONLY_RE = re.compile(r'\bus[- ]only\b|\busa[- ]only\b|united states only|remote.{0,15}(?:us|usa|united states)\b.{0,15}only|only.{0,15}(?:us|usa|united states)\b|\bunited states\b|\bu\.s\.\b|\busa\b', re.I)
_UK_ONLY_RE = re.compile(r'\buk[- ]only\b|united kingdom only|remote.{0,15}uk\b.{0,15}only|\bunited kingdom\b|\bu\.k\.\b', re.I)
_RELOCATION_RE = re.compile(r'relocation (?:assistance|package|support)|visa sponsorship for relocation|'
                             r'willing to relocate candidates|relocate to (?:the )?(?:uae|dubai|abu dhabi)', re.I)
# A bare workplace-type word with no place name at all is genuinely
# ambiguous territory (could be onsite anywhere, or remote-from-anywhere) --
# UNKNOWN, not a concrete foreign location. Any other non-empty text that
# isn't UAE/global-scope is treated as a specific named place (a real city
# or country), which defaults to INCOMPATIBLE (foreign onsite-only) below.
_AMBIGUOUS_WORKPLACE_TYPES = {'remote', 'hybrid', 'distributed', 'in-office', 'in office',
                               'on-site', 'onsite', 'on site', 'office', ''}


def assess_geography(location, remote_status, description, cfg):
    location = location or ''
    remote_status = remote_status or ''
    description = description or ''
    text = f'{location} {remote_status}'
    cfg = cfg or {}
    configured = [w for w in cfg.get('locations', []) if w.strip()]
    uae = _any(text, UAE_WORDS) or _any(text, [w.lower() for w in configured])
    global_scope = bool(_GLOBAL_SCOPE_RE.search(text))
    us_only = bool(_US_ONLY_RE.search(text))
    uk_only = bool(_UK_ONLY_RE.search(text))
    ambiguous_workplace = text.strip().lower() in _AMBIGUOUS_WORKPLACE_TYPES or text.strip().lower() == 'unknown'
    relocation_evidence = bool(_RELOCATION_RE.search(description))

    evidence = []
    uncertainty = []
    if uae:
        compatibility = COMPATIBLE
        evidence.append('Workplace location includes the UAE')
    elif global_scope and not (us_only or uk_only):
        compatibility = COMPATIBLE
        evidence.append('Worldwide/global/regional remote scope stated')
    elif ambiguous_workplace:
        compatibility = GEO_UNKNOWN
        uncertainty.append('Location is a generic workplace type with no place name; territory is not established')
    else:
        # A concrete, specific place (city/country) that is neither the UAE
        # nor a stated global/regional remote scope -- foreign onsite-only
        # by default, per docs/architecture/FIT_ASSESSMENT.md's geography
        # table (an explicit US/UK-only restriction is one case of this).
        compatibility = INCOMPATIBLE
        evidence.append('Workplace location is a specific place outside the UAE with no global/regional remote scope stated')

    if compatibility == INCOMPATIBLE and relocation_evidence and not (us_only or uk_only):
        compatibility = GEO_UNKNOWN
        evidence.append('Explicit relocation support evidence found; not treated as a hard rejection')

    return {'workplace_location': location, 'workplace_type': remote_status,
            'remote_scope': 'GLOBAL' if global_scope else ('RESTRICTED' if (us_only or uk_only or compatibility == INCOMPATIBLE) else 'UNSPECIFIED'),
            'relocation': relocation_evidence, 'compatibility': compatibility,
            'work_authorization': 'UNKNOWN', 'evidence': evidence, 'uncertainty': uncertainty,
            'confidence': 0.8 if compatibility != GEO_UNKNOWN else 0.3}


# ---------------------------------------------------------------------------
# Hard-reject: user-configured blocks and confirmed eligibility conflicts
# ---------------------------------------------------------------------------

# Seniority vocabulary that must never drive a hard rejection by itself, even
# when it also happens to appear in a user's `excluded_roles` list (a legacy
# setting whose default value bundles seniority words with real exclusions).
_SENIORITY_VOCABULARY = {'senior', 'sr', 'lead', 'principal', 'staff', 'distinguished', 'manager',
                          'director', 'head', 'chief', 'ciso', 'architect'}


def assess_user_blocked(item, cfg):
    from .policy import norm, host
    cfg = cfg or {}
    reasons = []
    company = item.get('company', '')
    if norm(company) and norm(company) in [norm(c) for c in cfg.get('blocked_companies', [])]:
        reasons.append('Blocked company: ' + company)
    domain = host(item.get('job_url', ''))
    if domain and domain in cfg.get('blocked_domains', []):
        reasons.append('Blocked domain: ' + domain)
    excluded = [w for w in cfg.get('excluded_roles', [])
                if w.strip() and w.strip().lower() not in _SENIORITY_VOCABULARY and _has(item.get('title', ''), w)]
    if excluded:
        reasons.append('User-excluded role match: ' + ', '.join(excluded))
    return reasons


def assess_eligibility_conflict(title, description, profile):
    from .recall import eligibility
    return eligibility((title or '') + '\n' + (description or ''), profile or {})


# ---------------------------------------------------------------------------
# Scoring components
# ---------------------------------------------------------------------------

def _domain_points(domain):
    base = {CUSTOM: 25, CORE: 25, ADJACENT: 16, CONTEXTUAL: 10, AMBIGUOUS: 5, OUTSIDE: 0}[domain['match_type']]
    return round(base * domain['confidence']) if domain['match_type'] in (CONTEXTUAL, AMBIGUOUS) else base


def _career_track_points(domain):
    return {CUSTOM: 15, CORE: 15, ADJACENT: 9, CONTEXTUAL: 4, AMBIGUOUS: 0, OUTSIDE: 0}[domain['match_type']]


def _profile_evidence(title, description, cfg, profile):
    profile = profile or {}
    known = career_tracks.matching_skills(cfg)
    full = (title or '') + ' ' + (description or '')
    fields = ('skills', 'employments', 'projects', 'education', 'certifications')
    has_facts = any(profile.get(key) for key in fields) or bool(profile.get('raw_text'))
    evidence_text = ' '.join(str(f.get('text', '')) for key in fields for f in profile.get(key, [])) or profile.get('raw_text', '')
    requested = [s for s in known if _has(full, s)]
    matches = [s for s in requested if _has(evidence_text, s)]
    missing = [s for s in requested if s not in matches]
    if not has_facts:
        return 12, matches, missing, ['Candidate profile is not yet imported/confirmed; skill evidence is UNKNOWN, not absent']
    if not requested:
        return 14, matches, missing, []
    ratio = len(matches) / len(requested)
    points = 20 * (0.4 + 0.6 * ratio)
    uncertainty = [] if matches or not requested else ['Requested skills are not evidenced in the confirmed profile']
    return points, matches, missing, uncertainty


_EXPERIENCE_TIERS = [(3, 15), (5, 11), (7, 7), (99, 4)]


def _experience_points(exp_req, candidate_years):
    required = exp_req.effective_required_minimum
    preferred = exp_req.effective_preferred_minimum
    uncertainty = []
    if required is None:
        points = 12.0
    elif candidate_years is not None and candidate_years >= required:
        points = 15.0
    elif candidate_years is None:
        # Unknown candidate years must never become zero; use the posting's
        # own tier as a neutral baseline with explicit uncertainty.
        points = next(p for ceiling, p in _EXPERIENCE_TIERS if required <= ceiling)
        uncertainty.append('Candidate relevant experience is not confirmed; treated as neutral, not zero')
    else:
        points = next(p for ceiling, p in _EXPERIENCE_TIERS if required <= ceiling)
    if preferred is not None and (candidate_years is None or candidate_years < preferred):
        points = max(0.0, points - 2.0)
        uncertainty.append('Preferred (non-mandatory) experience shortfall applied at most a 2-point reduction')
    return points, uncertainty


def _geography_points(geography):
    if geography['compatibility'] == COMPATIBLE:
        return 10.0
    if geography['compatibility'] == GEO_UNKNOWN:
        return 6.0
    return 0.0


def _freshness_points(posted_at, clock):
    if not posted_at:
        return 3.0, 'Posted date unknown; treated as neutral, not stale'
    try:
        posted = datetime.fromisoformat(str(posted_at).replace('Z', '+00:00'))
        if not posted.tzinfo:
            posted = posted.replace(tzinfo=timezone.utc)
    except (ValueError, TypeError):
        return 3.0, 'Posted date unparseable; treated as neutral'
    age_days = (clock - posted).total_seconds() / 86400
    if age_days < 0:
        return 3.0, 'Posted date is in the future; freshness unverified'
    if age_days <= 7:
        return 5.0, ''
    if age_days <= 30:
        return 4.0, ''
    if age_days <= 90:
        return 2.0, ''
    return 1.0, 'Posted over 90 days ago'


def _bucket(score):
    for floor, name in BUCKET_FLOORS:
        if score >= floor:
            return name
    return LOW


# ---------------------------------------------------------------------------
# Deterministic input digest
# ---------------------------------------------------------------------------

def input_digest(item, cfg, profile, versions):
    cfg = cfg or {}
    profile = profile or {}
    payload = {
        'job': {k: item.get(k, '') for k in ('company', 'title', 'location', 'remote_status', 'description',
                                              'experience_requirement', 'date_posted', 'closing_date', 'job_url')},
        'observation_authority': item.get('_observation_authority', {}),
        'candidate_facts': profile.get('declarations', {}),
        'candidate_facts_revision': profile.get('updated_at', ''),
        'career_tracks': sorted(cfg.get('career_tracks', [])),
        'custom_target_roles': sorted(cfg.get('custom_target_roles', [])),
        'excluded_roles': sorted(cfg.get('excluded_roles', [])),
        'blocked_companies': sorted(cfg.get('blocked_companies', [])),
        'blocked_domains': sorted(cfg.get('blocked_domains', [])),
        'locations': sorted(cfg.get('locations', [])),
        'versions': versions,
    }
    return hashlib.sha256(json.dumps(payload, sort_keys=True, default=str).encode()).hexdigest()[:32]


# ---------------------------------------------------------------------------
# Top-level assessment
# ---------------------------------------------------------------------------

def assess(item, cfg, profile=None, clock=None):
    """Assess one structurally valid job posting. Never touches identity or
    dedupe (issue #40 owns both); operates purely on already-resolved
    canonical/observation fields.
    """
    cfg = cfg or {}
    profile = profile or {}
    clock = clock or datetime.now(timezone.utc)
    title = item.get('title', '')
    description = item.get('description', '')

    exp_req = experience_module.parse(title + '\n' + description + '\n' + item.get('experience_requirement', ''))
    candidate_years = experience_module.candidate_years(profile)
    domain = assess_domain(title, description, cfg)
    seniority = assess_seniority(title, description, exp_req)
    geography = assess_geography(item.get('location', ''), item.get('remote_status', ''), description, cfg)
    eligibility = assess_eligibility_conflict(title, description, profile)
    blocked = assess_user_blocked(item, cfg)

    hard_reject = None
    if blocked:
        hard_reject = signal(USER_BLOCKED, 'User-configured exclusion', PENALTY, 'hard',
                              evidence_refs=blocked, explanation='; '.join(blocked), confidence=0.95)
    elif eligibility['state'] == 'INELIGIBLE':
        hard_reject = signal(CONFIRMED_ELIGIBILITY_CONFLICT, 'Confirmed eligibility conflict', PENALTY, 'hard',
                              evidence_refs=eligibility['evidence'],
                              explanation='Listing requires an eligibility fact the confirmed profile contradicts',
                              confidence=0.9)
    elif geography['compatibility'] == INCOMPATIBLE:
        hard_reject = signal(GEO_INCOMPATIBLE, 'Geography incompatible', PENALTY, 'hard',
                              evidence_refs=geography['evidence'],
                              explanation='Workplace geography is explicitly incompatible with UAE-based discovery',
                              confidence=geography['confidence'])
    elif seniority['extreme_leadership_mismatch']:
        hard_reject = signal(EXTREME_LEADERSHIP_MISMATCH, 'Extreme leadership mismatch', PENALTY, 'hard',
                              evidence_refs=seniority['title_signals'] + seniority['responsibility_signals'],
                              explanation='Title and organizational/architecture-authority evidence together indicate '
                                          'a scope far beyond an individual-contributor/early-career target',
                              confidence=seniority['confidence'])
    elif domain['hard_incompatible']:
        hard_reject = signal(DOMAIN_INCOMPATIBLE, 'Domain incompatible', PENALTY, 'hard',
                              evidence_refs=domain['title_evidence'],
                              explanation='Strong unrelated-profession evidence with no credible enabled-track, '
                                          'custom-role, or contextual technical evidence',
                              confidence=domain['confidence'])

    positives, penalties, uncertainty = [], [], []

    domain_points = _domain_points(domain)
    track_points = _career_track_points(domain)
    profile_points, matched_skills, missing_skills, profile_uncertainty = _profile_evidence(title, description, cfg, profile)
    experience_points, experience_uncertainty = _experience_points(exp_req, candidate_years)
    seniority_points = seniority['fit_points']
    geography_points = _geography_points(geography)
    freshness_points, freshness_note = _freshness_points(item.get('date_posted', ''), clock)

    components = {'domain': domain_points, 'career_track': track_points, 'profile_evidence': profile_points,
                  'experience': experience_points, 'seniority': seniority_points,
                  'geography': geography_points, 'freshness': freshness_points}

    if domain['match_type'] in (CORE, CUSTOM):
        positives.append(signal('DOMAIN_CORE_MATCH', 'Core enabled role match', POSITIVE, 'domain', domain_points,
                                 domain['title_evidence'], 'Title matches an enabled career track or custom target role', domain['confidence']))
    elif domain['match_type'] == ADJACENT:
        positives.append(signal('DOMAIN_ADJACENT_MATCH', 'Adjacent technical role', POSITIVE, 'domain', domain_points,
                                 domain['body_evidence'], 'Adjacent entry route with overlapping technical duties', domain['confidence']))
    elif domain['match_type'] == CONTEXTUAL:
        uncertainty.append('Role is contextually technical but title alone is ambiguous')
    elif domain['match_type'] in (AMBIGUOUS, OUTSIDE) and not hard_reject:
        uncertainty.append('Domain relevance could not be confirmed from title/description')

    if matched_skills:
        positives.append(signal('SKILLS_EVIDENCED', 'Confirmed matching skills', POSITIVE, 'profile_evidence',
                                 profile_points, matched_skills, 'Skills requested by the posting are evidenced in the confirmed profile', 0.8))
    uncertainty.extend(profile_uncertainty)

    if experience_points < 15 and exp_req.effective_required_minimum is not None:
        penalties.append(signal('EXPERIENCE_SHORTFALL', 'Experience below stated requirement', PENALTY, 'experience',
                                 experience_points - 15, exp_req.original_texts,
                                 f"Listing requests {exp_req.effective_required_minimum:g}+ years; treated as a ranking penalty, not a rejection", 0.6))
    uncertainty.extend(experience_uncertainty)

    if seniority['title_level'] in (LEAD, MANAGER, EXECUTIVE) and not hard_reject:
        penalties.append(signal('SENIORITY_SCOPE', 'Seniority/leadership scope above target', PENALTY, 'seniority',
                                 seniority_points - 10, seniority['title_signals'],
                                 'Title/responsibility evidence suggests a broader scope than an individual-contributor/early-career target', seniority['confidence']))
    if seniority['conflicting_signals']:
        uncertainty.extend(seniority['conflicting_signals'])

    if geography['compatibility'] == GEO_UNKNOWN:
        uncertainty.extend(geography['uncertainty'])
    elif geography['compatibility'] == COMPATIBLE:
        positives.append(signal('GEOGRAPHY_COMPATIBLE', 'Geography compatible', POSITIVE, 'geography',
                                 geography_points, geography['evidence'], 'Workplace geography is compatible', geography['confidence']))

    if eligibility['state'] == 'UNKNOWN':
        uncertainty.append('Eligibility/nationality wording is unconfirmed: ' + '; '.join(eligibility['evidence']))

    if freshness_note:
        uncertainty.append(freshness_note)

    versions = {'schema': SCHEMA_VERSION, 'ruleset': RULESET_VERSION, 'taxonomy': career_tracks.VERSION,
                'experience_parser': experience_module.VERSION}
    digest = input_digest(item, cfg, profile, versions)

    score = None if hard_reject else max(0, min(100, round(sum(components.values()))))
    bucket = REJECTED if hard_reject else _bucket(score)

    return {
        'schema_version': SCHEMA_VERSION, 'ruleset_version': RULESET_VERSION, 'score_kind': SCORE_KIND,
        'score': score, 'bucket': bucket, 'hard_reject': hard_reject.to_dict() if hard_reject else None,
        'matched_tracks': domain['matched_tracks'], 'primary_track': domain['primary_track'],
        'role_family': domain['role_family'], 'match_type': domain['match_type'],
        'components': {k: round(v, 1) for k, v in components.items()}, 'component_weights': WEIGHTS,
        'experience': exp_req.to_dict(), 'seniority': {k: v for k, v in seniority.items()},
        'geography': geography, 'query_expansion_match': 'UNKNOWN', 'query_expansion_weight': 0,
        'matched_skills': matched_skills, 'missing_skills': missing_skills,
        'positives': [s.to_dict() for s in positives], 'penalties': [s.to_dict() for s in penalties],
        'uncertainty': list(dict.fromkeys(uncertainty)),
        'explanation': _explain(domain, seniority, geography, exp_req, hard_reject, bucket),
        'versions': versions, 'input_digest': digest, 'assessed_at': clock.isoformat(),
    }


def _explain(domain, seniority, geography, exp_req, hard_reject, bucket):
    if hard_reject:
        return hard_reject.explanation
    bits = [f"{domain['match_type'].title()} match on {domain['role_family']}"]
    if exp_req.effective_required_minimum is not None:
        bits.append(f"requests {exp_req.effective_required_minimum:g}+ years (ranking signal, not a rejection)")
    if seniority['title_level'] not in (ENTRY, MID):
        bits.append(f"seniority scope: {seniority['title_level'].lower()}")
    if geography['compatibility'] != COMPATIBLE:
        bits.append(f"geography: {geography['compatibility'].lower()}")
    bits.append(f'ranking priority bucket: {bucket}')
    return '; '.join(bits)
