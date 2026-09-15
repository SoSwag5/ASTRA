"""Deterministic, local candidate-experience-requirement parsing (issue #41).

Produces a typed ExperienceRequirement made of scoped ExperienceClause records
instead of a single flattened minimum. A listing's clauses are never summed
("7+ years overall, 2+ years in cloud" stays two clauses, never seven-plus
cloud years) and an absence of evidence is UNKNOWN, never zero. See
docs/architecture/FIT_ASSESSMENT.md.
"""
import re
from dataclasses import dataclass, field, asdict

VERSION = 'experience-1'

REQUIRED = 'REQUIRED'
PREFERRED = 'PREFERRED'
UNKNOWN = 'UNKNOWN'

OVERALL = 'OVERALL'
DOMAIN = 'DOMAIN'
SKILL = 'SKILL'

_WRITTEN = {'no': 0, 'zero': 0, 'one': 1, 'two': 2, 'three': 3, 'four': 4, 'five': 5,
            'six': 6, 'seven': 7, 'eight': 8, 'nine': 9, 'ten': 10}
_WRITTEN_ALT = '|'.join(_WRITTEN)

_PREFERRED_RE = re.compile(r'preferred|desirable|nice.to.have|\bbonus\b|\badvantage\b|a plus\b|is a plus', re.I)
_NOT_REQUIRED_RE = re.compile(r'preferred but not required|not required but preferred|nice.to.have', re.I)
_REQUIRED_RE = re.compile(r'\brequired\b|\bmandatory\b|must have|minimum of|at least|no less than|\bmust\b', re.I)
_NO_EXP_RE = re.compile(r'no experience (?:is )?required|no prior experience (?:is )?(?:required|necessary)|'
                         r'\bgraduate\b|entry.level|entry level|no experience necessary', re.I)
_OR_EQUIVALENT_RE = re.compile(r'or equivalent(?:\s+experience)?', re.I)
_COMPANY_HISTORY_RE = re.compile(r'company|founded|in business|our history|established in', re.I)
_TRAINING_RE = re.compile(r'\btraining\b|\bcourse\b|\bonboarding\b|\bcertification exam\b', re.I)
# Deliberately excludes the bare word "experience": every relevant clause
# already contains it (see `_relevant_clause`), so including it here would
# defeat the company-history exclusion it is meant to support.
_CANDIDATE_RE = re.compile(r'\byou\b|\bcandidates?\b|\bapplicants?\b', re.I)
_DATA_HISTORY_RE = re.compile(r'years?\s+of\s+(?:behavioral|historical|training|customer|industry|security)?\s*data', re.I)

_NUMERIC_RANGE_RE = re.compile(
    r'(?:minimum\s+of\s+|at least\s+|no less than\s+)?'
    r'(\d{1,2})\s*(?:[-–—]|to)?\s*(\d{1,2})?\s*(\+|or more|or greater)?\s*'
    r'(?:years?|yrs?)\b', re.I)
_WRITTEN_RANGE_RE = re.compile(
    r'\b(' + _WRITTEN_ALT + r')\b\s*(?:[-–—]|to)?\s*(' + _WRITTEN_ALT + r')?\s*(\+)?\s*(?:years?|yrs?)\b', re.I)
_SCOPE_RE = re.compile(r'(?:years?|yrs?)\s+(?:of|in|with)\s+([a-zA-Z][a-zA-Z0-9 /&+.-]{2,40})', re.I)


@dataclass
class ExperienceClause:
    minimum_years: float | None
    maximum_years: float | None
    plus: bool
    necessity: str
    scope: str
    scope_text: str
    original_text: str
    explicit: bool
    confidence: float
    or_equivalent: bool = False

    def to_dict(self):
        return asdict(self)


@dataclass
class ExperienceRequirement:
    clauses: list = field(default_factory=list)
    effective_required_minimum: float | None = None
    effective_preferred_minimum: float | None = None
    no_experience_required: bool = False
    original_texts: list = field(default_factory=list)
    confidence: float = 0.0

    @property
    def stated(self):
        return bool(self.clauses) or self.no_experience_required

    def to_dict(self):
        return {'clauses': [c.to_dict() for c in self.clauses],
                'effective_required_minimum': self.effective_required_minimum,
                'effective_preferred_minimum': self.effective_preferred_minimum,
                'no_experience_required': self.no_experience_required,
                'original_texts': self.original_texts, 'confidence': self.confidence,
                'stated': self.stated, 'version': VERSION}


def _relevant_clause(clause):
    if not re.search(r'experience|required|preferred|desirable|minimum|at least|\bbonus\b|\badvantage\b|a plus\b|'
                      r'years?\s+(?:in|of)|خبرة', clause, re.I):
        return False
    if _COMPANY_HISTORY_RE.search(clause) and not _CANDIDATE_RE.search(clause):
        return False
    if _DATA_HISTORY_RE.search(clause) and not re.search(r'experience', clause, re.I):
        return False
    if _TRAINING_RE.search(clause) and not re.search(r'experience', clause, re.I):
        return False
    return True


def _necessity(clause):
    if _NOT_REQUIRED_RE.search(clause):
        return PREFERRED
    if _PREFERRED_RE.search(clause):
        return PREFERRED
    if _REQUIRED_RE.search(clause):
        return REQUIRED
    # A bare "X years experience" line with no explicit cue reads as a
    # mandatory requirement in ordinary listing usage -- matches the prior
    # recall.py default this module replaces.
    return REQUIRED


def _scope(clause):
    m = _SCOPE_RE.search(clause)
    if not m:
        return OVERALL, ''
    text = m.group(1).strip().rstrip('.').strip()
    if not text or text.lower() in ('experience', 'the industry', 'the field'):
        return OVERALL, ''
    return DOMAIN, text[:80]


def _numbers_in(clause):
    found = []
    for m in _NUMERIC_RANGE_RE.finditer(clause):
        low = int(m[1])
        high = int(m[2]) if m[2] else None
        if high is not None and high < low:
            continue
        if low > 60 or (high or 0) > 60:
            continue
        found.append((float(low), float(high) if high is not None else None, bool(m[3]), m.span()))
    if found:
        return found
    for m in _WRITTEN_RANGE_RE.finditer(clause):
        low = _WRITTEN[m[1].lower()]
        high = _WRITTEN[m[2].lower()] if m[2] else None
        found.append((float(low), float(high) if high is not None else None, bool(m[3]), m.span()))
    return found


def parse(text):
    """Parse a job posting's free text into an ExperienceRequirement.

    Never sums scoped clauses and never promotes "no confirmed evidence" to
    a numeric zero -- callers must keep `UNKNOWN` distinct from `0`.
    """
    text = text or ''
    clauses = []
    no_experience_required = bool(_NO_EXP_RE.search(text))
    for raw in re.split(r'[\n;.!?]|,(?=\s*(?:more than|at least|over)?\s*\d+\s*(?:years?|yrs?))', text):
        clause = raw.strip()
        if not clause or not _relevant_clause(clause):
            continue
        necessity = _necessity(clause)
        scope, scope_text = _scope(clause)
        or_equivalent = bool(_OR_EQUIVALENT_RE.search(clause))
        for low, high, plus, _span in _numbers_in(clause):
            clauses.append(ExperienceClause(
                minimum_years=low, maximum_years=high, plus=plus, necessity=necessity,
                scope=scope, scope_text=scope_text, original_text=clause[:500],
                explicit=True, confidence=0.9, or_equivalent=or_equivalent))
    required_overall = [c.minimum_years for c in clauses if c.necessity == REQUIRED and c.scope == OVERALL]
    required_any = [c.minimum_years for c in clauses if c.necessity == REQUIRED]
    preferred_any = [c.minimum_years for c in clauses if c.necessity == PREFERRED]
    effective_required = max(required_overall) if required_overall else (max(required_any) if required_any else None)
    effective_preferred = max(preferred_any) if preferred_any else None
    confidence = 0.9 if clauses else (0.6 if no_experience_required else 0.0)
    return ExperienceRequirement(
        clauses=clauses, effective_required_minimum=effective_required,
        effective_preferred_minimum=effective_preferred,
        no_experience_required=no_experience_required and not clauses,
        original_texts=[c.original_text for c in clauses], confidence=confidence)


def candidate_years(profile):
    """Confirmed candidate relevant-experience years, or None (UNKNOWN).

    Mirrors the declaration ASTRA has always required before trusting a
    number: `verified_relevant_experience_years_confirmed` must be exactly
    True. Missing/unconfirmed data is UNKNOWN, never 0.
    """
    d = (profile or {}).get('declarations', {})
    value = d.get('verified_relevant_experience_years')
    if d.get('verified_relevant_experience_years_confirmed') is True and isinstance(value, (int, float)) and 0 <= value <= 60:
        return float(value)
    return None
