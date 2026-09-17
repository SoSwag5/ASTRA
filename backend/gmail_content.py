"""Bounded hostile MIME extraction. No I/O, rendering, execution or retention.

Only transient plain text, safe public-path URLs and normalized authentication
evidence reach the deterministic parser. Headers and bodies never reach storage."""
import base64
import binascii
import codecs
import html as html_module
import ipaddress
from html.parser import HTMLParser
import re
from datetime import datetime, timezone
from urllib.parse import urlsplit

# ---------------------------------------------------------------------------
# Bounds. Each one caps work an email sender would otherwise control.
# ---------------------------------------------------------------------------
#: Decoded text accepted from one message, across all of its parts
#: combined. Reaching it truncates rather than failing: a confirmation's
#: identifying structure is at the top of the message, so a padded body
#: cannot hide it, and refusing the whole message would let a sender
#: suppress detection by appending filler.
MAX_DECODED_BODY_BYTES = 262_144
#: Depth of MIME nesting walked. `multipart/alternative` inside
#: `multipart/mixed` inside `multipart/related` is normal; eight levels is
#: far past anything legitimate and stops a nesting bomb.
MAX_MIME_DEPTH = 8
#: Parts visited per message, counting containers.
MAX_MIME_PARTS = 64
#: Headers read, and characters kept from one header value.
MAX_HEADERS = 128
MAX_HEADER_VALUE_CHARS = 2_000
#: Characters kept for a subject or a sender once sanitized.
MAX_SUBJECT_CHARS = 512
MAX_SENDER_CHARS = 320
#: Links collected from one message, and the longest single URL accepted.
MAX_URLS = 20
MAX_URL_CHARS = 2_048

#: Base64 expands by 4/3, so an encoded part longer than this cannot fit
#: the decoded cap and is rejected before any decode work happens.
_MAX_ENCODED_PART_CHARS = (MAX_DECODED_BODY_BYTES * 4) // 3 + 8

# ---------------------------------------------------------------------------
# Character-level neutralization
# ---------------------------------------------------------------------------
#: C0 controls except tab/newline/carriage return, DEL, and the C1 block.
#: Control characters in a subject or sender are a log-injection and
#: display-spoofing vector, and ASTRA's security-event log already strips
#: them for the same reason.
_CONTROL = re.compile(r'[\x00-\x08\x0b\x0c\x0e-\x1f\x7f-\x9f]')
#: Zero-width and bidirectional-override characters. These are invisible
#: when displayed but change what a human reads -- the classic way to make
#: `evil.com` look like `greenhouse.io`, or to hide text inside a company
#: name. Removed entirely rather than escaped.
_INVISIBLE = re.compile('[​-‏‪-‮⁠-⁤⁦-⁩﻿]')
_WHITESPACE = re.compile(r'[ \t\r\f\v]+')
_BLANK_LINES = re.compile(r'\n{3,}')


def sanitize_text(value, limit):
    """Neutralize control, invisible and bidirectional characters; cap length.

    The result is plain text safe to store, log and later display. It is
    never HTML, never markup and never a URL.
    """
    if not isinstance(value, str):
        return ''
    cleaned = _INVISIBLE.sub('', _CONTROL.sub(' ', value[:limit * 4]))
    cleaned = cleaned.replace('<', '').replace('>', '').replace('\n', ' ')
    cleaned = _WHITESPACE.sub(' ', cleaned)
    return cleaned.strip()[:limit]


def sanitize_block(value, limit):
    """Like `sanitize_text` but keeps paragraph structure for parsing."""
    if not isinstance(value, str):
        return ''
    cleaned = _INVISIBLE.sub('', _CONTROL.sub(' ', value))
    cleaned = _WHITESPACE.sub(' ', cleaned)
    cleaned = _BLANK_LINES.sub('\n\n', cleaned)
    return cleaned.strip()[:limit]


# ---------------------------------------------------------------------------
# HTML
# ---------------------------------------------------------------------------
_BARE_URL = re.compile(r'https?://[^\s<>"\'\]\)]{1,2048}', re.IGNORECASE)


class _InertHTML(HTMLParser):
    """Read HTML as data, with no browser, resource loader or active markup."""
    ACTIVE = frozenset({'script', 'style', 'iframe', 'object', 'embed', 'template',
                        'noscript', 'svg', 'math', 'head'})

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.chunks, self.links, self.hidden = [], [], []
        self.anchor = None
        self.anchor_text = []

    def handle_starttag(self, tag, attrs):
        if tag in self.ACTIVE:
            self.hidden.append(tag)
        if self.hidden:
            return
        if tag == 'a':
            self.anchor = dict(attrs).get('href', '')
            self.anchor_text = []
        if tag in ('p', 'br', 'div', 'li', 'tr'):
            self.chunks.append('\n')

    def handle_endtag(self, tag):
        if self.hidden:
            if tag == self.hidden[-1]:
                self.hidden.pop()
            return
        if tag == 'a' and self.anchor is not None:
            if len(self.links) < MAX_URLS:
                target = self.anchor
                visible = ''.join(self.anchor_text).strip()
                if visible.startswith(('https://', 'http://')) and url_host(visible) != url_host(target):
                    target = ''  # a deceptive visible destination
                self.links.append(target)
            self.anchor = None
        if tag in ('p', 'div', 'li', 'tr'):
            self.chunks.append('\n')

    def handle_data(self, value):
        if not self.hidden:
            self.chunks.append(value.replace('<', '').replace('>', ''))
            if self.anchor is not None:
                self.anchor_text.append(value)


def _read_html(markup):
    parser = _InertHTML()
    parser.feed((markup or '')[:MAX_DECODED_BODY_BYTES])
    parser.close()
    if parser.anchor is not None and len(parser.links) < MAX_URLS:
        parser.links.append('')  # unterminated anchor is not trusted
    return parser


def html_to_text(markup):
    if not isinstance(markup, str):
        return ''
    return sanitize_block(''.join(_read_html(markup).chunks), MAX_DECODED_BODY_BYTES)


# ---------------------------------------------------------------------------
# URLs
# ---------------------------------------------------------------------------
#: Schemes that must never survive extraction. The check below is an
#: allowlist (`https` only), so this set exists to make the intent
#: explicit and to be asserted directly by the hostile-content tests.
UNSAFE_SCHEMES = frozenset({'javascript', 'data', 'vbscript', 'file', 'about',
                            'blob', 'jar', 'view-source', 'chrome', 'ms-msdt',
                            'mailto', 'tel', 'ftp', 'ws', 'wss', 'gopher'})
_ASCII_HOST = re.compile(r'^[A-Za-z0-9.-]{1,253}$')
_IPV4_HOST = re.compile(r'^\d{1,3}(?:\.\d{1,3}){3}$')


def safe_url(raw):
    """Allow HTTPS public-domain paths only; discard queries/fragments and reject deceptive forms."""
    if not isinstance(raw, str):
        return ''
    candidate = raw.strip()
    if not candidate or len(candidate) > MAX_URL_CHARS:
        return ''
    if _CONTROL.search(candidate) or _INVISIBLE.search(candidate) or any(char.isspace() for char in candidate):
        return ''
    if '\\' in candidate:
        return ''
    try:
        parts = urlsplit(candidate)
    except ValueError:
        return ''
    if parts.scheme.lower() != 'https':
        return ''
    authority = parts.netloc
    if '@' in authority or not authority:
        return ''
    host = parts.hostname or ''
    if not host or not _ASCII_HOST.fullmatch(host) or _IPV4_HOST.fullmatch(host):
        return ''
    try:
        if parts.port not in (None, 443):
            return ''
        ipaddress.ip_address(host)
        return ''
    except ValueError:
        if ':' in authority:
            return ''
    if '.' not in host or any(label.startswith(('xn--', '-')) or label.endswith('-')
                              for label in host.lower().split('.')):
        return ''
    if host.endswith(('.localhost', '.local', '.internal', '.test', '.invalid')):
        return ''
    if any(char in candidate for char in '<>"\'') or re.search(r'%0[ad]|%5c', candidate, re.I):
        return ''
    if host.startswith('.') or host.endswith('.') or '..' in host:
        return ''
    # Query strings and fragments may carry recipient addresses, tracking or
    # login tokens. Only a public path can become evidence.
    from urllib.parse import unquote
    path = unquote(parts.path)
    if '@' in path or any(char in path for char in '<>"\\'):
        return ''
    return 'https://' + host.lower() + parts.path


def extract_urls(plain_text, markup):
    """`(safe_urls, dropped_count)` from one message.

    Anchor `href` values are read first because they are the links a
    human would actually follow, then bare URLs in the plain-text part.
    Every candidate passes `safe_url`, so an unsafe or deceptive link is
    dropped rather than stored, and the count of what was dropped is
    returned so the caller can record that neutralization happened. No
    candidate is ever requested.
    """
    found = []
    seen = set()
    dropped = 0

    def offer(candidate):
        nonlocal dropped
        url = safe_url(html_module.unescape(candidate))
        if not url:
            dropped += 1
            return
        if url not in seen:
            seen.add(url)
            found.append(url)

    for target in _read_html(markup).links:
        if len(found) >= MAX_URLS:
            return found, dropped
        offer(target)
    for match in _BARE_URL.finditer(plain_text or ''):
        if len(found) >= MAX_URLS:
            return found, dropped
        offer(match.group(0))
    return found, dropped


# ---------------------------------------------------------------------------
# Headers
# ---------------------------------------------------------------------------
def headers_of(payload):
    """Read only bounded parser headers. Duplicate/truncated relevant headers cap confidence."""
    result = {}
    raw = payload.get('headers') if isinstance(payload, dict) else None
    if not isinstance(raw, list):
        return result
    for entry in raw[:MAX_HEADERS]:
        if not isinstance(entry, dict):
            continue
        name = entry.get('name')
        value = entry.get('value')
        if not isinstance(name, str) or not isinstance(value, str):
            continue
        key = sanitize_text(name, 64).lower()
        if key in result:
            result['_ambiguous'] = True
            continue
        if key in ('from', 'subject', 'authentication-results', 'content-type'):
            if len(value) > MAX_HEADER_VALUE_CHARS:
                result['_ambiguous'] = True
            # From brackets and auth punctuation are needed for parsing. This
            # bounded map is transient and is never stored or displayed.
            result[key] = value[:MAX_HEADER_VALUE_CHARS]
    if len(raw) > MAX_HEADERS:
        result['_ambiguous'] = True
    return result


_ADDRESS = re.compile(r'<([^<>@\s]{1,64}@[A-Za-z0-9.-]{1,253})>')
_BARE_ADDRESS = re.compile(r'^([^<>@\s]{1,64}@[A-Za-z0-9.-]{1,253})$')


def sender_address(from_header):
    """The bare address from a `From:` header, lowercased, or `''`.

    Only the address is taken; the display name is dropped. A display
    name is free text the sender chooses and is the easiest part of an
    email to forge, so it is never used as an identity signal and never
    persisted as the sender.
    """
    value = from_header.strip() if isinstance(from_header, str) else ''
    if len(value) > MAX_SENDER_CHARS or _CONTROL.search(value) or _INVISIBLE.search(value):
        return ''
    match = re.fullmatch(r'[^<>@,\r\n]*' + _ADDRESS.pattern, value)
    if match:
        return match.group(1).lower()
    match = _BARE_ADDRESS.match(value.strip())
    return match.group(1).lower() if match else ''


def sender_domain(address):
    """The domain of a bare address, lowercased, or `''`."""
    _, _, domain = (address or '').rpartition('@')
    domain = domain.strip().lower().rstrip('.')
    return domain if domain and _ASCII_HOST.match(domain) else ''


def url_host(url):
    """The lowercased hostname of an already-sanitized URL, or `''`."""
    try:
        return (urlsplit(url or '').hostname or '').lower()
    except ValueError:
        return ''


def domain_matches(domain, suffixes):
    """Whether `domain` is one of `suffixes` or a subdomain of one.

    Suffix matching is anchored on a dot boundary, so `evilgreenhouse.io`
    does not match `greenhouse.io` and `greenhouse.io.evil.example` does
    not either.
    """
    if not domain:
        return False
    return any(domain == suffix or domain.endswith('.' + suffix)
               for suffix in suffixes)


# ---------------------------------------------------------------------------
# Authentication evidence (ADR-0008)
# ---------------------------------------------------------------------------
#: The only tokens ASTRA records per mechanism. Gmail's
#: `Authentication-Results` header carries far more -- selectors, signing
#: domains, envelope addresses, client IPs -- and none of it is kept:
#: ADR-0008 permits only "the minimum normalized evidence", which is one
#: verdict per mechanism.
AUTH_VERDICTS = ('PASS', 'FAIL', 'SOFTFAIL', 'NEUTRAL', 'NONE', 'POLICY',
                 'PERMERROR', 'TEMPERROR', 'UNKNOWN', 'ABSENT')
AUTH_MECHANISMS = ('spf', 'dkim', 'dmarc')
_AUTH_RESULT = re.compile(r'\b(spf|dkim|dmarc)\s*=\s*([A-Za-z]{1,12})', re.IGNORECASE)
_VERDICT_MAP = {'pass': 'PASS', 'fail': 'FAIL', 'softfail': 'SOFTFAIL',
                'neutral': 'NEUTRAL', 'none': 'NONE', 'policy': 'POLICY',
                'permerror': 'PERMERROR', 'temperror': 'TEMPERROR',
                'bestguesspass': 'NEUTRAL'}


def authentication_evidence(headers):
    """Normalize one Gmail Authentication-Results header and check explicit From alignment.

    Trust is limited to the Gmail API delivery path and mx.google.com authserv-id.
    Duplicate/ambiguous headers, ARC-only copies and foreign issuers fail closed.
    This is receiver evidence, not independent SPF/DKIM cryptographic verification."""
    verdicts = {name: 'ABSENT' for name in AUTH_MECHANISMS}
    header = headers.get('authentication-results', '')
    evidence = {'source': 'ABSENT', 'aligned': False, **verdicts}
    # Do not trust ARC copies, arbitrary authserv-ids, duplicate headers,
    # comments containing fake verdicts or inconsistent mechanism clauses.
    if headers.get('_ambiguous') or not re.match(r'^mx\.google\.com\s*;', header, re.I):
        return evidence
    clean = re.sub(r'\([^()]*\)', '', header)
    if '(' in clean or ')' in clean:
        return evidence
    mechanisms = [match.group(1).lower() for match in _AUTH_RESULT.finditer(clean)]
    if len(mechanisms) != len(set(mechanisms)):
        return evidence
    clauses = clean.split(';')[1:]
    seen = set()
    from_domain = sender_domain(sender_address(headers.get('from', '')))
    aligned = False
    for clause in clauses:
        match = re.match(r'\s*(spf|dkim|dmarc)\s*=\s*([a-z]+)\b', clause, re.I)
        if not match:
            continue
        mechanism, verdict = (part.lower() for part in match.groups())
        if mechanism in seen:
            return evidence
        seen.add(mechanism)
        verdicts[mechanism] = _VERDICT_MAP.get(verdict, 'UNKNOWN')
        if mechanism == 'dmarc':
            identities = re.findall(r'\bheader\.from=([A-Za-z0-9.-]+)(?=\s|$)', clause, re.I)
            aligned = len(identities) == 1 and identities[0].lower() == from_domain and bool(from_domain)
    return {'source': 'GMAIL_AUTHENTICATION_RESULTS', 'aligned': aligned, **verdicts}


def authentication_corroborates(evidence):
    """Require aligned DMARC PASS and SPF or DKIM PASS, with no adverse/unknown verdict."""
    if not isinstance(evidence, dict):
        return False
    if evidence.get('source') != 'GMAIL_AUTHENTICATION_RESULTS' or not evidence.get('aligned'):
        return False
    if evidence.get('dmarc') != 'PASS':
        return False
    if evidence.get('spf') != 'PASS' and evidence.get('dkim') != 'PASS':
        return False
    return all(evidence.get(name) in ('PASS', 'ABSENT') for name in AUTH_MECHANISMS)


def authentication_tokens(evidence):
    """Bounded evidence tokens such as `AUTH_DMARC_PASS`, for storage."""
    return [f'AUTH_{name.upper()}_{evidence.get(name) if evidence.get(name) in AUTH_VERDICTS else "UNKNOWN"}'
            for name in AUTH_MECHANISMS]


# ---------------------------------------------------------------------------
# MIME traversal
# ---------------------------------------------------------------------------
_CHARSET = re.compile(r'charset\s*=\s*"?([A-Za-z0-9_.:+-]{1,40})"?', re.IGNORECASE)


def _charset_of(headers, part):
    """The declared charset, validated, defaulting to UTF-8."""
    declared = part.get('mimeType') if isinstance(part, dict) else ''
    source = headers.get('content-type') or (declared if isinstance(declared, str) else '')
    match = _CHARSET.search(source or '')
    if not match:
        return 'utf-8'
    try:
        return codecs.lookup(match.group(1)).name
    except (LookupError, ValueError):
        return None


def _decode_part_data(data):
    """base64url-decode one part's payload, or `None` when malformed.

    Gmail omits padding, so it is restored before decoding. A malformed
    or oversized payload returns `None` and the caller skips that part --
    one bad part must not abort the whole message.
    """
    if not isinstance(data, str) or not data:
        return None
    if len(data) > _MAX_ENCODED_PART_CHARS:
        return None
    padded = data + '=' * (-len(data) % 4)
    try:
        return base64.b64decode(padded.encode('ascii', 'strict'), altchars=b'-_', validate=True)
    except (binascii.Error, ValueError, UnicodeEncodeError):
        return None


class ExtractedContent:
    """The bounded plain-text view of one message, plus what was refused.

    Holds no raw payload, no HTML, no attachment and no Gmail response.
    `text` is the concatenated, sanitized plain text used for parsing and
    is discarded by the caller once parsing returns.
    """

    __slots__ = ('text', 'urls', 'unsafe_urls_dropped', 'truncated',
                 'malformed_parts', 'attachments_skipped', 'parts_seen',
                 'depth_exceeded')

    def __init__(self, *, text, urls, unsafe_urls_dropped, truncated,
                 malformed_parts, attachments_skipped, parts_seen, depth_exceeded):
        self.text = text
        self.urls = urls
        self.unsafe_urls_dropped = unsafe_urls_dropped
        self.truncated = truncated
        self.malformed_parts = malformed_parts
        self.attachments_skipped = attachments_skipped
        self.parts_seen = parts_seen
        self.depth_exceeded = depth_exceeded

    def limits(self):
        """Bounded tokens describing which limits this message hit."""
        tokens = []
        if self.truncated:
            tokens.append('BODY_TRUNCATED')
        if self.malformed_parts:
            tokens.append('MALFORMED_PART_SKIPPED')
        if self.attachments_skipped:
            tokens.append('ATTACHMENT_SKIPPED')
        if self.depth_exceeded:
            tokens.append('MIME_DEPTH_EXCEEDED')
        if self.parts_seen >= MAX_MIME_PARTS:
            tokens.append('MIME_PART_LIMIT_REACHED')
        if self.unsafe_urls_dropped:
            tokens.append('UNSAFE_LINKS_DROPPED')
        return tokens


def extract_content(payload):
    """Iteratively visit at most 64 parts, depth 8, and decode at most 256 KiB.

    Attachments, attached messages and non-text leaves are ignored. Malformed text
    is flagged; incomplete evidence cannot receive HIGH confidence."""
    plain_chunks = []
    html_chunks = []
    total = 0
    parts_seen = 0
    malformed = 0
    attachments = 0
    truncated = False
    depth_exceeded = False

    stack = [(payload, 0)] if isinstance(payload, dict) else []
    while stack:
        if parts_seen >= MAX_MIME_PARTS:
            break
        part, depth = stack.pop()
        if not isinstance(part, dict):
            malformed += 1
            continue
        parts_seen += 1
        if depth > MAX_MIME_DEPTH:
            depth_exceeded = True
            continue
        mime = part.get('mimeType')
        mime = mime.lower() if isinstance(mime, str) else ''
        filename = part.get('filename')
        body = part.get('body') if isinstance(part.get('body'), dict) else {}
        if (isinstance(filename, str) and filename.strip()) or body.get('attachmentId'):
            attachments += 1
            continue
        children = part.get('parts')
        if mime.startswith('multipart/') and isinstance(children, list):
            for child in reversed(children[:MAX_MIME_PARTS]):
                stack.append((child, depth + 1))
        if mime not in ('text/plain', 'text/html'):
            continue
        if total >= MAX_DECODED_BODY_BYTES:
            truncated = True
            break
        raw = _decode_part_data(body.get('data'))
        if raw is None:
            if body.get('data'):
                malformed += 1
            continue
        remaining = MAX_DECODED_BODY_BYTES - total
        if len(raw) > remaining:
            raw = raw[:remaining]
            truncated = True
        total += len(raw)
        charset = _charset_of(headers_of(part), part)
        try:
            # Validate before replacement so malformed text cannot establish
            # HIGH confidence merely because the intact template still matches.
            decoded = raw.decode(charset, errors='strict')
        except (LookupError, ValueError, TypeError, UnicodeError):
            malformed += 1
            decoded = raw.decode('utf-8', errors='replace')
        if mime == 'text/html':
            html_chunks.append(decoded)
        else:
            plain_chunks.append(decoded)

    markup = '\n'.join(html_chunks)
    plain = sanitize_block('\n'.join(plain_chunks), MAX_DECODED_BODY_BYTES)
    from_html = html_to_text(markup) if markup else ''
    combined = sanitize_block('\n'.join(part for part in (plain, from_html) if part),
                              MAX_DECODED_BODY_BYTES)
    urls, dropped = extract_urls(plain, markup)
    return ExtractedContent(text=combined,
                            urls=urls,
                            unsafe_urls_dropped=dropped,
                            truncated=truncated,
                            malformed_parts=malformed,
                            attachments_skipped=attachments,
                            parts_seen=parts_seen,
                            depth_exceeded=depth_exceeded)


# ---------------------------------------------------------------------------
# Timestamps
# ---------------------------------------------------------------------------
def received_at(message):
    """UTC ISO-8601 receipt time from Gmail's own `internalDate`.

    Normal SMTP delivery uses Google's receipt time. API-imported mail can
    supply this timestamp, so it is not cryptographic receipt evidence.
    The sender's `Date:` header is not used. Invalid values yield `''`.
    """
    raw = message.get('internalDate') if isinstance(message, dict) else None
    if isinstance(raw, (int, float)):
        raw = str(int(raw))
    if not isinstance(raw, str) or not raw.strip().isdigit():
        return ''
    try:
        milliseconds = int(raw.strip())
    except ValueError:
        return ''
    # Bounded to a sane epoch range so an absurd value cannot overflow the
    # conversion or produce a nonsense sort key.
    if not 0 <= milliseconds <= 4_102_444_800_000:
        return ''
    try:
        return datetime.fromtimestamp(milliseconds / 1000, timezone.utc).isoformat()
    except (OverflowError, OSError, ValueError):
        return ''


def internal_date_ms(message):
    """Gmail's `internalDate` as an int, or `0` when unusable."""
    raw = message.get('internalDate') if isinstance(message, dict) else None
    if isinstance(raw, (int, float)):
        raw = str(int(raw))
    if not isinstance(raw, str) or not raw.strip().isdigit():
        return 0
    try:
        value = int(raw.strip())
    except ValueError:
        return 0
    return value if 0 <= value <= 4_102_444_800_000 else 0
