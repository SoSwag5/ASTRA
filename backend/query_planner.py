"""Discovery v2 query planner (issue #37): user intent -> bounded search plan.

Deterministic and rule-based only. Does not rank, filter eligibility, or
retrieve postings -- those are later Discovery v2 stages.

Governing principle: when confidence is high, expand; when parsing is
ambiguous, preserve the exact query and avoid expansion. Concretely:

- Expansion is limited to an explicit, curated role-relation table
  (exact alias lookup, never fuzzy/substring matching). An unrecognized
  title returns only itself -- a seniority-looking word is never stripped
  unless the stripped result is a known role, so words that are actually
  part of a role's identity (Architect, Lead, Manager, ...) are never
  destructively removed from an unrecognized title.
- Numeric level/tier and categorical seniority (junior/senior words) are
  tracked as separate constraints. A numbered level only implies a
  categorical seniority where a specific role rule documents that
  (tier_one_implies_junior); level 2+ never implies junior. When an
  explicit categorical word and a numeric level are both present, that is
  treated as a conflict: both signals are preserved in constraints
  (seniority_conflict=True), but no seniority/level-derived expansion row
  is generated for that plan.
- A location wrapped in common delimiters (parentheses, brackets, commas,
  hyphens, irregular whitespace) is recognized and cleanly removed from
  the parsing representation without leaving punctuation debris; the raw
  exact query is never altered beyond outer whitespace trimming. A
  location preceded by an explicit negation word -- allowing the same
  delimiter wrapping in between (`not (Dubai)`, `excluding [Sharjah]`) --
  is never turned into an affirmative constraint; the whole query is
  instead treated as ambiguous and returned exact-only.
- Location and negation matching use a plain bounded literal search
  followed by a linear, bounded scan of only the delimiter characters
  immediately adjacent to a confirmed match. This is deliberate: an
  earlier revision wrapped the location literal in an unbounded
  `[delimiters]*` regex quantifier on both sides, which is O(n^2) via
  backtracking against long punctuation runs that never contain a real
  location. Never reintroduce that pattern; any surrounding-delimiter
  cleanup must be bounded to the characters next to an actual match, not
  attempted at every non-matching position in the input.

`priority` on a returned row is a relative ordering signal only (lower
sorts first); after deduplication its values may have gaps and must not
be treated as a contiguous 0..n-1 index.
"""
import re

VERSION = 'query-planner-4'
MAX_EXPANSIONS = 10
MAX_QUERY_LENGTH = 1024

_JUNIOR_WORDS = sorted(['entry level', 'entry-level', 'junior', 'graduate'], key=len, reverse=True)
_SENIOR_WORDS = sorted(['senior', 'principal', 'director', 'architect', 'manager', 'lead', 'head'], key=len, reverse=True)
_LEVEL_RE = re.compile(r'\b(?:level|tier)\s*-?\s*(1|2|3|i{1,3})\b', re.I)
_ROMAN = {'i': 1, 'ii': 2, 'iii': 3}
_NEGATION_WORDS = ['excluding', 'except', 'not', 'no']

_LOCATIONS = sorted(['United Arab Emirates', 'Abu Dhabi', 'Ras Al Khaimah', 'Umm Al Quwain',
                     'Dubai', 'Sharjah', 'Ajman', 'Fujairah', 'Al Ain', 'UAE'], key=len, reverse=True)
_LOCATION_PATTERNS = [(loc, re.compile(r'\b' + re.escape(loc) + r'\b', re.I)) for loc in _LOCATIONS]
_LOC_DELIM_CHARS = set(' \t\n\r,;/-()[]')

_ROLE_RELATIONS = [
    {'id': 'soc_analyst', 'aliases': ['soc analyst'], 'canonical': 'SOC Analyst',
     'synonyms': ['Security Operations Analyst'], 'broader': ['Cybersecurity Analyst'],
     'tier_one_implies_junior': True},
    {'id': 'cybersecurity_analyst',
     'aliases': ['cybersecurity analyst', 'cyber security analyst', 'cybersecurity', 'cyber security'],
     'canonical': 'Cybersecurity Analyst', 'synonyms': [], 'broader': [], 'tier_one_implies_junior': False},
    {'id': 'security_analyst', 'aliases': ['security analyst'], 'canonical': 'Security Analyst',
     'synonyms': [], 'broader': ['Information Security Analyst'], 'tier_one_implies_junior': False},
]
_ROLE_INDEX = {alias: entry for entry in _ROLE_RELATIONS for alias in entry['aliases']}

def _collapse(text):
    return ' '.join(text.split())

def _normalize_whitespace(text):
    return re.sub(r'\s+', ' ', text)

def _validate_max_expansions(value):
    if isinstance(value, bool) or not isinstance(value, int):
        raise TypeError('max_expansions must be an int, not a bool or other type')
    if value < 1:
        raise ValueError('max_expansions must be >= 1')

def _validate_query_length(raw_query):
    if len(raw_query) > MAX_QUERY_LENGTH:
        raise ValueError(f'raw_query must be at most {MAX_QUERY_LENGTH} characters')

_MAX_NEGATION_WORD_LEN = max(len(w) for w in _NEGATION_WORDS)

def _negated_before(text, match_start):
    """Bounded backward scan: skip only delimiter chars immediately before the match,
    then check a small constant-size window for a preceding negation word.

    Slicing `text[:i]` here (the whole prefix, up to O(n) long) instead of a
    bounded window would make this function O(n) per call; with one call
    per location occurrence, a query repeating the same location many
    times would make the overall scan O(n^2) again -- exactly the class of
    bug this module exists to avoid. The window includes one extra
    leading character (when available) so `\\b` at the window's start
    still reflects genuine context instead of an artifact of where the
    window happens to begin (e.g. distinguishing `not Dubai` from
    `cannot Dubai`, where "not" is a whole word only in the first case).
    """
    i = match_start
    while i > 0 and text[i - 1] in _LOC_DELIM_CHARS:
        i -= 1
    window_start = max(0, i - _MAX_NEGATION_WORD_LEN - 1)
    window = text[window_start:i]
    for word in _NEGATION_WORDS:
        if re.search(r'\b' + word + r'\b\s*$', window, re.I):
            return True
    return False

def _scan_locations(text):
    """Find non-negated locations and strip them cleanly; report if any occurrence was negated.

    Every occurrence of every supported location is inspected for a
    preceding negation, not just the first -- a query can affirm a
    location once and then explicitly exclude the same location later
    (`SOC Analyst Dubai not Dubai`), and that later occurrence must not
    be silently skipped.

    Uses a plain bounded literal search per location (`finditer`, not an
    unbounded delimiter-consuming regex) plus a linear scan of only the
    delimiter characters touching a confirmed match. All matches across
    all locations are collected and negation-checked against the
    original, unmodified text first; only if none are negated is the
    text rebuilt, in a single linear pass over the collected spans --
    never by repeated whole-string slicing per occurrence, which would
    reintroduce quadratic behavior when a location repeats many times.

    Adjacent matches are widened in left-to-right order, each one capped
    at the previous match's already-widened end: two locations separated
    by a single shared delimiter run (`Dubai, Sharjah`) would otherwise
    both greedily claim that run from opposite directions and overlap,
    which would incorrectly drop the second location.
    """
    raw_matches = []
    for loc, pattern in _LOCATION_PATTERNS:
        for m in pattern.finditer(text):
            if _negated_before(text, m.start()):
                return [], text, True
            raw_matches.append((m.start(), m.end(), loc))

    if not raw_matches:
        return [], text, False

    raw_matches.sort(key=lambda s: s[0])
    spans = []
    prev_end = 0
    for start, end, loc in raw_matches:
        widened_start = start
        while widened_start > prev_end and text[widened_start - 1] in _LOC_DELIM_CHARS:
            widened_start -= 1
        widened_end = end
        while widened_end < len(text) and text[widened_end] in _LOC_DELIM_CHARS:
            widened_end += 1
        spans.append((widened_start, widened_end, loc))
        prev_end = widened_end

    found = []
    seen = set()
    pieces = []
    cursor = 0
    for start, end, loc in spans:
        pieces.append(text[cursor:start])
        pieces.append(' ')
        cursor = end
        if loc not in seen:
            seen.add(loc)
            found.append(loc)
    pieces.append(text[cursor:])
    return found, _collapse(''.join(pieces)), False

def _extract_level(text):
    m = _LEVEL_RE.search(text)
    if not m:
        return None, text
    raw = m.group(1).lower()
    level = int(raw) if raw.isdigit() else _ROMAN[raw]
    return level, _collapse(text[:m.start()] + ' ' + text[m.end():])

def _extract_category(text):
    for word in _JUNIOR_WORDS:
        m = re.search(r'\b' + re.escape(word) + r'\b', text, re.I)
        if m:
            return 'junior', _collapse(text[:m.start()] + ' ' + text[m.end():])
    for word in _SENIOR_WORDS:
        m = re.search(r'\b' + re.escape(word) + r'\b', text, re.I)
        if m:
            return 'senior', _collapse(text[:m.start()] + ' ' + text[m.end():])
    return None, text

def _resolve_role(text):
    """Look up a matched role only when confident; never commit a destructive strip that misses."""
    plain_key = text.casefold()
    entry = _ROLE_INDEX.get(plain_key)
    if entry is not None:
        return entry, None
    category, stripped = _extract_category(text)
    if category is not None:
        entry = _ROLE_INDEX.get(stripped.casefold())
        if entry is not None:
            return entry, category
    return None, None

def _row(query, priority, reason, source_rule, constraints):
    return {'query': query, 'priority': priority, 'reason': reason, 'source_rule': source_rule, 'constraints': constraints}

def _dedupe_and_cap(rows, max_expansions):
    seen = set()
    result = []
    for row in sorted(rows, key=lambda r: r['priority']):
        key = _collapse(row['query']).casefold()
        if key in seen:
            continue
        seen.add(key)
        result.append(row)
        if len(result) >= max_expansions:
            break
    return result

def plan(raw_query, max_expansions=MAX_EXPANSIONS):
    """Expand raw_query into a bounded, deduplicated, explainable search plan."""
    _validate_max_expansions(max_expansions)
    if not isinstance(raw_query, str):
        return []
    _validate_query_length(raw_query)
    original = raw_query.strip()
    if not original:
        return []

    parsing_text = _normalize_whitespace(original)
    locations, working, any_negated = _scan_locations(parsing_text)

    if any_negated:
        constraints = {'locations': [], 'seniority': None, 'level': None, 'role': None, 'seniority_conflict': False}
        return [_row(original, 0,
                     'Query contains a negated location; parsing is ambiguous, so only the exact query is used.',
                     'ambiguous_negation_exact_only', constraints)]

    level, working = _extract_level(working)
    entry, category = _resolve_role(working)

    if entry is None:
        constraints = {'locations': locations, 'seniority': None, 'level': None, 'role': None, 'seniority_conflict': False}
        return [_row(original, 0,
                     'No curated role rule recognized this title; only the exact query is used to avoid '
                     'destructively altering unrecognized role-identity words.',
                     'exact_only_unrecognized', constraints)]

    conflict = category is not None and level is not None
    if category is not None:
        seniority = category
    elif level == 1 and entry['tier_one_implies_junior']:
        seniority = 'junior'
    else:
        seniority = None

    constraints = {'locations': locations, 'seniority': seniority, 'level': level,
                   'role': entry['canonical'], 'seniority_conflict': conflict}
    primary = entry['canonical']
    rows = [_row(original, 0, "User's original query, always preserved and ranked highest.", 'exact_query', constraints)]
    rank = 1

    if not conflict:
        if level is not None:
            rows.append(_row(f'{primary} Tier {level}', rank,
                              f"Numbered seniority in '{original}' normalized to the canonical Tier {level} form of '{primary}'.",
                              f"level_normalization:{entry['id']}", constraints))
            rank += 1
        if seniority == 'junior':
            rows.append(_row(f'Junior {primary}', rank,
                              f"Junior-level phrasing of '{primary}'.", f"seniority_normalization:{entry['id']}", constraints))
            rank += 1
        elif seniority == 'senior':
            rows.append(_row(f'Senior {primary}', rank,
                              f"Senior-level phrasing of '{primary}'.", f"seniority_normalization:{entry['id']}", constraints))
            rank += 1

    rows.append(_row(primary, rank,
                      f"Base title for '{primary}' without a seniority qualifier.", f"title_normalization:{entry['id']}", constraints))
    rank += 1

    for synonym in entry['synonyms']:
        rows.append(_row(synonym, rank,
                          f"'{synonym}' is an established synonym for '{primary}'.", f"role_synonym:{entry['id']}", constraints))
        rank += 1

    for broader in entry['broader']:
        if not conflict and seniority == 'junior':
            rows.append(_row(f'Junior {broader}', rank,
                              f"'{broader}' is an approved broader/adjacent title for '{primary}'; junior-level phrasing preserved.",
                              f"approved_broader_relation:{entry['id']}", constraints))
            rank += 1
        elif not conflict and seniority == 'senior':
            rows.append(_row(f'Senior {broader}', rank,
                              f"'{broader}' is an approved broader/adjacent title for '{primary}'; senior-level phrasing preserved.",
                              f"approved_broader_relation:{entry['id']}", constraints))
            rank += 1
        rows.append(_row(broader, rank,
                          f"'{broader}' is an approved broader/adjacent title for '{primary}'.",
                          f"approved_broader_relation:{entry['id']}", constraints))
        rank += 1

    return _dedupe_and_cap(rows, max_expansions)
