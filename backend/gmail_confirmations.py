"""Deterministic-first application-confirmation parsing (issue #45).

OD-012 and ADR-0008 fix the shape of this module:

* **Deterministic only.** Detection is regular expressions over a
  message's sender domain, subject structure and body template. There is
  no model, no AI provider call, no network access and no learned
  behaviour anywhere in this file. OD-012 excludes cloud AI from the
  initial classifier outright; evaluating it later would be a separate
  proposal with its own threat-model delta.
* **Multiple independent signals for HIGH.** Five signals are defined
  below and *all five* are required for HIGH. A sender name alone, a
  subject substring alone or a template resemblance alone cannot reach
  it, which is what makes the classifier non-trivial to spoof.
* **Authentication gates HIGH.** Missing or contradictory SPF/DKIM/DMARC
  evidence caps a message at MEDIUM however exactly its content matches
  a known template (ADR-0008).
* **One target signal.** v1.1 detects *application confirmation* only.
  Viewed, assessment, interview, rejection and offer are explicitly
  deferred, and `DEFERRED_STATES` exists so a test can assert this module
  never produces one.
* **No state mutation.** Parsing returns a value. It reads no
  application record, writes none, and reconciliation is a separate
  issue that consumes what this produces.

## Template provenance and its limits

The three platform parsers recognize conservative English confirmation
shapes for Greenhouse, Lever and Workday. Vendor documentation establishes
that these notifications exist and can be customized; it does not establish
a universal exact template. These deliberately narrow shapes are exercised against ASTRA's synthetic corpus in
`tests/gmail_confirmation_fixtures.py`. They have **not** been
calibrated against real received mail, and no claim is made here about
real-world recall or precision. A genuine confirmation whose wording
differs from these templates falls through to the generic fallback and
is tagged LOW -- it is not lost, but it is not HIGH either.
"""
import re
from urllib.parse import urlsplit

from . import gmail_content as content

# ---------------------------------------------------------------------------
# Vocabulary. Every token below is bounded and persisted as-is, so the sets
# here are the complete vocabulary of the evidence records.
# ---------------------------------------------------------------------------
HIGH = 'HIGH'
MEDIUM = 'MEDIUM'
LOW = 'LOW'
CONFIDENCE_LEVELS = (HIGH, MEDIUM, LOW)

#: The only application state this issue detects.
APPLICATION_CONFIRMED = 'APPLICATION_CONFIRMED'
#: A message that reached a parser but carries no confirmation signal. It
#: is reported, counted, and deliberately **not** persisted: an evidence
#: table that also stored non-evidence would be retention without purpose.
NOT_A_CONFIRMATION = 'NOT_A_CONFIRMATION'
#: Explicitly out of scope for v1.1 (issue #45, planning §6.2). Named so a
#: regression test can assert no parser here ever emits one.
DEFERRED_STATES = ('APPLICATION_VIEWED', 'ASSESSMENT_INVITED', 'INTERVIEW_INVITED',
                   'APPLICATION_REJECTED', 'OFFER_EXTENDED')

SIGNAL_SENDER_DOMAIN = 'SENDER_DOMAIN'
SIGNAL_SUBJECT_STRUCTURE = 'SUBJECT_STRUCTURE'
SIGNAL_BODY_TEMPLATE = 'BODY_TEMPLATE'
SIGNAL_FIELD_CONSISTENCY = 'FIELD_CONSISTENCY'
SIGNAL_AUTHENTICATION = 'AUTHENTICATION'

#: ADR-0008: HIGH requires sender identity, structural template match,
#: consistent extracted fields **and** message authentication. All four
#: kinds, five signals, together -- never a subset.
REQUIRED_FOR_HIGH = frozenset({SIGNAL_SENDER_DOMAIN, SIGNAL_SUBJECT_STRUCTURE,
                               SIGNAL_BODY_TEMPLATE, SIGNAL_FIELD_CONSISTENCY,
                               SIGNAL_AUTHENTICATION})
ALL_SIGNALS = REQUIRED_FOR_HIGH

#: Recorded when a message reproduces a platform template but does not
#: come from that platform's domain -- the signature of a spoof. The
#: message still gets a record, through the generic fallback at LOW, and
#: never wears the platform parser's identifier.
TOKEN_TEMPLATE_WITHOUT_SENDER = 'TEMPLATE_WITHOUT_SENDER_MATCH'
#: Recorded when the only links in the message were unsafe or deceptive
#: and were therefore dropped by `gmail_content.safe_url`.
TOKEN_UNSAFE_LINKS_DROPPED = 'UNSAFE_LINKS_DROPPED'

GENERIC_PARSER_ID = 'generic-confirmation-fallback-v1'

MAX_COMPANY_CHARS = 80
MAX_ROLE_CHARS = 100
#: Body text scanned for a template match. Bounded so a padded message
#: cannot drive an unbounded regex scan; the identifying structure of a
#: confirmation is at the top of the message.
MAX_TEMPLATE_SCAN_CHARS = 20_000

_ENTITY = r"[^.\n<>|]{2,80}?"
_ROLE = r"[^.\n<>|]{2,100}?"

_TRAILING = re.compile(r'[\s,.;:!?\-–—’\'"]+$')
_LEADING = re.compile(r'^[\s,.;:!?\-–—\'"]+')
_LEGAL_SUFFIX = re.compile(
    r'[\s,]+(?:inc|llc|l\.l\.c|ltd|limited|gmbh|corp|corporation|co|plc|'
    r's\.a|b\.v|a\.b|oy|pty|ag|nv)\.?$', re.IGNORECASE)
_COMPARABLE = re.compile(r'[^a-z0-9]+')


def _clean_entity(value, limit):
    """Trim an extracted company or role to a storable, comparable form."""
    text = content.sanitize_text(value or '', limit * 2)
    text = _LEADING.sub('', _TRAILING.sub('', text))
    # `the Security Analyst role` -> `Security Analyst`
    text = re.sub(r'^(?:the|a|an)\s+', '', text, flags=re.IGNORECASE)
    text = _TRAILING.sub('', text)
    return text[:limit]


def _comparable(value):
    """Letters and digits only, for comparing two extracted entities."""
    return _COMPARABLE.sub('', _LEGAL_SUFFIX.sub('', (value or '')).lower())


def _entities_agree(first, second):
    """Require equal normalized company names, allowing only an explicit legal suffix."""
    left, right = _comparable(first), _comparable(second)
    if not left or not right:
        return False
    if len(left) < 3 or len(right) < 3:
        return left == right
    return left == right


class DeterministicParser:
    """One platform's confirmation template and its extraction rules."""

    def __init__(self, *, parser_id, platform, sender_domains, url_host_suffixes,
                 subject_patterns, body_patterns):
        self.parser_id = parser_id
        self.platform = platform
        self.sender_domains = tuple(sender_domains)
        self.url_host_suffixes = tuple(url_host_suffixes)
        self.subject_patterns = tuple(subject_patterns)
        self.body_patterns = tuple(body_patterns)

    def matches_sender(self, domain):
        return content.domain_matches(domain, self.sender_domains)

    def match_subject(self, subject):
        """`(matched, company, role)` from the subject line."""
        for pattern in self.subject_patterns:
            found = pattern.search(subject or '')
            if found:
                groups = found.groupdict()
                return True, groups.get('company', ''), groups.get('role', '')
        return False, '', ''

    def match_body(self, text):
        """`(matched, company, role)` from the body template."""
        scanned = (text or '')[:MAX_TEMPLATE_SCAN_CHARS]
        matches = [found.groupdict() for pattern in self.body_patterns for found in pattern.finditer(scanned)]
        if not matches:
            return False, '', ''
        first = matches[0]
        if any(not _entities_agree(first.get('company'), found.get('company'))
               or _comparable(first.get('role')) != _comparable(found.get('role')) for found in matches[1:]):
            return False, '', ''
        return True, first.get('company', ''), first.get('role', '')

    def platform_url(self, urls):
        """The first already-sanitized URL hosted by this platform."""
        for url in urls or ():
            safe = content.safe_url(url)
            if not safe or not content.domain_matches(content.url_host(safe), self.url_host_suffixes):
                continue
            path = urlsplit(safe).path
            if self.platform == 'LEVER':
                # Lever hosted postings use /tenant/UUID, with optional /apply.
                relevant = (content.url_host(safe) in ('jobs.lever.co', 'jobs.eu.lever.co')
                    and re.fullmatch(r'/[A-Za-z0-9_-]+/[0-9a-f]{8}(?:-[0-9a-f]{4}){3}-[0-9a-f]{12}(?:/apply)?/?', path, re.I))
            else:
                relevant = re.search(r'/(?:[^/?]+/)*(?:jobs?|applications?)/[^/?]+', path, re.I)
            if relevant:
                return safe
        return ''


def _subject(*alternatives):
    return tuple(re.compile(pattern, re.IGNORECASE) for pattern in alternatives)


_BODY_FLAGS = re.IGNORECASE | re.DOTALL

GREENHOUSE = DeterministicParser(
    parser_id='greenhouse-confirmation-v1',
    platform='GREENHOUSE',
    sender_domains=('greenhouse.io', 'greenhouse-mail.io'),
    url_host_suffixes=('greenhouse.io',),
    subject_patterns=_subject(
        rf'^\s*thank you for applying to (?P<company>{_ENTITY})\s*[.!]?\s*$',
        rf'^\s*your application to (?P<company>{_ENTITY})\s*[.!]?\s*$',
        rf'^\s*(?P<company>{_ENTITY}) application (?:received|confirmation)\s*[.!]?\s*$',
    ),
    body_patterns=(
        re.compile(rf'thank you for applying (?:to|for) the (?P<role>{_ROLE}) '
                   rf'(?:position|role|opening|job) at (?P<company>{_ENTITY})(?=[.!?\n]|$)', _BODY_FLAGS),
        re.compile(rf'we(?:\'ve| have)? received your application for the (?P<role>{_ROLE}) '
                   rf'(?:position|role|opening|job) at (?P<company>{_ENTITY})(?=[.!?\n]|$)', _BODY_FLAGS),
        re.compile(rf'your application for the (?P<role>{_ROLE}) '
                   rf'(?:position|role|opening|job) at (?P<company>{_ENTITY}) '
                   rf'has been (?:received|submitted)\b', _BODY_FLAGS),
    ),
)

LEVER = DeterministicParser(
    parser_id='lever-confirmation-v1',
    platform='LEVER',
    sender_domains=('lever.co', 'hire.lever.co', 'letters.lever.co'),
    url_host_suffixes=('lever.co',),
    subject_patterns=_subject(
        rf'^\s*thank you for applying to (?P<company>{_ENTITY})\s*[.!]?\s*$',
        rf'^\s*(?P<company>{_ENTITY})\s*[\-–—]\s*'
        rf'(?:application received|thank you for applying)\s*[.!]?\s*$',
        rf'^\s*your application (?:to|at) (?P<company>{_ENTITY}) was (?:sent|received)'
        rf'\s*[.!]?\s*$',
    ),
    body_patterns=(
        re.compile(rf'thanks for applying to the (?P<role>{_ROLE}) '
                   rf'(?:role|position|opening) at (?P<company>{_ENTITY})(?=[.!?\n]|$)', _BODY_FLAGS),
        re.compile(rf'your application (?:to|for) the (?P<role>{_ROLE}) '
                   rf'(?:role|position|opening) at (?P<company>{_ENTITY}) was sent\b',
                   _BODY_FLAGS),
        re.compile(rf'we(?:\'ve| have)? received your application (?:to|for) the '
                   rf'(?P<role>{_ROLE}) (?:role|position|opening) at '
                   rf'(?P<company>{_ENTITY})(?=[.!?\n]|$)', _BODY_FLAGS),
    ),
)

WORKDAY = DeterministicParser(
    parser_id='workday-confirmation-v1',
    platform='WORKDAY',
    sender_domains=('myworkday.com', 'myworkdayjobs.com', 'workday.com'),
    url_host_suffixes=('myworkday.com', 'myworkdayjobs.com'),
    subject_patterns=_subject(
        # Workday confirmations frequently omit the company from the
        # subject, so a company-less structural subject is accepted here
        # and the company must then come from the body; field consistency
        # still requires one.
        r'^\s*thank you for (?:your application|applying)\s*[.!]?\s*$',
        rf'^\s*thank you for applying to (?P<company>{_ENTITY})\s*[.!]?\s*$',
        rf'^\s*your application (?:to|at|with) (?P<company>{_ENTITY})'
        rf'(?: was received)?\s*[.!]?\s*$',
        r'^\s*application (?:received|confirmation)\s*[.!]?\s*$',
    ),
    body_patterns=(
        re.compile(rf'thank you for (?:applying|your application) (?:to|for) the '
                   rf'(?P<role>{_ROLE})(?:\s*\([A-Za-z0-9\-]{{2,20}}\))? '
                   rf'(?:position|role|opening|job) at (?P<company>{_ENTITY})(?=[.!?\n]|$)',
                   _BODY_FLAGS),
        re.compile(rf'we(?:\'ve| have)? received your application for '
                   rf'(?P<role>{_ROLE})(?:\s*\([A-Za-z0-9\-]{{2,20}}\))? at '
                   rf'(?P<company>{_ENTITY})(?=[.!?\n]|$)', _BODY_FLAGS),
        re.compile(rf'your application for (?:the )?(?P<role>{_ROLE})'
                   rf'(?:\s*\([A-Za-z0-9\-]{{2,20}}\))? at (?P<company>{_ENTITY}) '
                   rf'has been (?:received|submitted)\b', _BODY_FLAGS),
    ),
)

#: Order is the resolution order. A message is claimed by the first
#: parser whose *sender domain* matches, so a platform parser can never
#: be applied to a message that did not come from that platform.
PARSERS = (GREENHOUSE, LEVER, WORKDAY)
PARSER_IDS = tuple(parser.parser_id for parser in PARSERS)

# ---------------------------------------------------------------------------
# Generic fallback (non-AI, pattern-based, never HIGH)
# ---------------------------------------------------------------------------
#: Fixed phrases only. No scoring model, no learned weights, no provider
#: call -- a literal phrase list, which is what makes the fallback
#: auditable and its LOW tag honest.
GENERIC_PHRASES = (
    re.compile(r'\bthank(?:s| you) for applying\b', re.IGNORECASE),
    re.compile(r'\bthank(?:s| you) for your application\b', re.IGNORECASE),
    re.compile(r'\byour application (?:has been|was) (?:received|submitted|sent)\b',
               re.IGNORECASE),
    re.compile(r'\bwe(?:\'ve| have)? received your application\b', re.IGNORECASE),
    re.compile(r'\bapplication (?:received|submitted|confirmation)\b', re.IGNORECASE),
    re.compile(r'\byour application was sent to\b', re.IGNORECASE),
)
#: Best-effort company/role recovery for a fallback match. Deliberately
#: weak: whatever it finds is reported at LOW and never mutates anything.
_GENERIC_ROLE_COMPANY = (
    re.compile(rf'appl(?:ying|ication) (?:to|for) (?:the )?(?P<role>{_ROLE}) '
               rf'(?:position|role|opening|job) at (?P<company>{_ENTITY})(?=[.!?\n]|$)', _BODY_FLAGS),
    re.compile(rf'your application (?:to|for) (?P<company>{_ENTITY}) '
               rf'(?:has been|was) (?:received|submitted|sent)\b', _BODY_FLAGS),
)
_GENERIC_SUBJECT_COMPANY = re.compile(
    rf'^\s*thank you for applying to (?P<company>{_ENTITY})\s*[.!]?\s*$', re.IGNORECASE)


class ParseResult:
    """One parse outcome. A value object -- it mutates nothing."""

    __slots__ = ('parser_id', 'platform', 'state', 'confidence', 'company',
                 'role', 'application_url', 'signals', 'evidence_tokens')

    def __init__(self, *, parser_id, platform, state, confidence, company, role,
                 application_url, signals, evidence_tokens):
        self.parser_id = parser_id
        self.platform = platform
        self.state = state
        self.confidence = confidence
        self.company = company
        self.role = role
        self.application_url = application_url
        self.signals = signals
        self.evidence_tokens = evidence_tokens

    @property
    def is_confirmation(self):
        return self.state == APPLICATION_CONFIRMED


def _confidence_for(signals):
    """Map a signal set to a confidence level.

    HIGH needs every signal in `REQUIRED_FOR_HIGH`. MEDIUM needs the
    message to have actually come from the platform (`SENDER_DOMAIN`)
    plus a structural match and at least three signals overall. Anything
    else is LOW. Nothing below the full set can reach HIGH, so a
    single-signal match -- sender alone, subject alone, template alone --
    cannot, and neither can a perfect template whose authentication
    evidence is missing or contradictory.
    """
    present = frozenset(signals)
    if REQUIRED_FOR_HIGH.issubset(present):
        return HIGH
    structural = present & {SIGNAL_SUBJECT_STRUCTURE, SIGNAL_BODY_TEMPLATE}
    if SIGNAL_SENDER_DOMAIN in present and structural and len(present) >= 3:
        return MEDIUM
    return LOW


def _generic(subject, text, urls, evidence_tokens):
    """The controlled fallback: non-AI, phrase-based, never above LOW."""
    haystack = f'{subject}\n{(text or "")[:MAX_TEMPLATE_SCAN_CHARS]}'
    matched = any(phrase.search(haystack) for phrase in GENERIC_PHRASES)
    company = role = ''
    if matched:
        for pattern in _GENERIC_ROLE_COMPANY:
            found = pattern.search(haystack)
            if found:
                groups = found.groupdict()
                company = _clean_entity(groups.get('company', ''), MAX_COMPANY_CHARS)
                role = _clean_entity(groups.get('role', ''), MAX_ROLE_CHARS)
                break
        if not company:
            found = _GENERIC_SUBJECT_COMPANY.search(subject or '')
            if found:
                company = _clean_entity(found.group('company'), MAX_COMPANY_CHARS)
    return ParseResult(
        parser_id=GENERIC_PARSER_ID,
        platform='GENERIC',
        state=APPLICATION_CONFIRMED if matched else NOT_A_CONFIRMATION,
        # The fallback is capped at LOW unconditionally. It has no sender
        # identity, no template structure and no field corroboration to
        # offer, so any higher tag would overstate what it verified.
        confidence=LOW,
        company=company,
        role=role,
        application_url='',
        signals=[],
        evidence_tokens=list(evidence_tokens),
    )


def parse(*, subject, sender_domain, text, urls, authentication,
          unsafe_links_dropped=False):
    """Detect an initial confirmation using a full sender/subject/body match, otherwise LOW fallback.

    HIGH additionally needs consistent fields, a relevant platform link, and aligned
    Gmail authentication. No I/O or application mutation is performed."""
    subject = content.sanitize_text(subject or '', content.MAX_SUBJECT_CHARS)
    # Later-stage messages often quote the original confirmation. They must
    # not become new initial confirmations. No later state is classified.
    excluded = re.search(r'\b(interview|assessment|offer|rejected|rejection|unsuccessful)\b', subject, re.I)
    excluded = excluded or re.search(r'not (?:be )?(?:moving|proceeding)|unfortunately|regret to inform|not (?:been )?(?:received|submitted)', (text or '')[:MAX_TEMPLATE_SCAN_CHARS], re.I)
    if excluded:
        return _generic('', '', [], ['OUTSIDE_INITIAL_CONFIRMATION_SCOPE'])
    authenticated = content.authentication_corroborates(authentication)
    base_tokens = list(content.authentication_tokens(authentication or {}))
    if unsafe_links_dropped:
        base_tokens.append(TOKEN_UNSAFE_LINKS_DROPPED)

    claimed = None
    for parser in PARSERS:
        if not parser.matches_sender(sender_domain):
            continue
        subject_hit, subject_company, subject_role = parser.match_subject(subject)
        body_hit, body_company, body_role = parser.match_body(text)
        if subject_hit and body_hit:
            claimed = (parser, subject_hit, subject_company, subject_role,
                       body_hit, body_company, body_role)
            break

    if claimed is None:
        tokens = list(base_tokens)
        # Record the spoof shape explicitly: the content looks like a
        # known platform's confirmation, but it did not come from that
        # platform's domain.
        for parser in PARSERS:
            if parser.match_subject(subject)[0] or parser.match_body(text)[0]:
                tokens.append(TOKEN_TEMPLATE_WITHOUT_SENDER)
                break
        return _generic(subject, text, urls, tokens)

    (parser, subject_hit, subject_company, subject_role,
     body_hit, body_company, body_role) = claimed

    company = _clean_entity(body_company or subject_company, MAX_COMPANY_CHARS)
    role = _clean_entity(body_role or subject_role, MAX_ROLE_CHARS)
    application_url = parser.platform_url(urls)

    signals = {SIGNAL_SENDER_DOMAIN}
    if subject_hit:
        signals.add(SIGNAL_SUBJECT_STRUCTURE)
    if body_hit:
        signals.add(SIGNAL_BODY_TEMPLATE)
    if authenticated and not unsafe_links_dropped:
        signals.add(SIGNAL_AUTHENTICATION)

    # Field consistency is a genuine cross-check, not a presence test:
    # both fields must be extracted, the two sources must agree when both
    # supplied a company, and the message must link to the platform that
    # supposedly sent it.
    consistent = bool(company and role and application_url and subject_company and body_company)
    if consistent and subject_company and body_company:
        consistent = _entities_agree(subject_company, body_company)
    if consistent:
        signals.add(SIGNAL_FIELD_CONSISTENCY)

    confidence = _confidence_for(signals)
    return ParseResult(
        parser_id=parser.parser_id,
        platform=parser.platform,
        state=APPLICATION_CONFIRMED,
        confidence=confidence,
        company=company,
        role=role,
        application_url=application_url,
        signals=sorted(signals),
        evidence_tokens=base_tokens,
    )
