"""Bounded, read-only check of employers' official careers routes (#46.2-B).

This is a research tool, not part of ASTRA. Nothing in ``backend`` imports it,
it never opens ASTRA's database or source configuration, and it makes no
request unless it is run with an explicit plan file. Tests drive it through a
fictional transport with no network.

Rules it enforces, from the #46.2-B source-map protocol:

- one descriptive read-only User-Agent, GET only, and no cookie kept or sent;
- https on the default port only, with no user information in the URL; host
  names are compared in one canonical form (lower case, no trailing dot);
- at least ``MIN_INTERVAL`` seconds between contacts with one host (HTTP
  requests and TLS handshakes), counted from the *end* of the previous contact
  (its response closed, or its handshake returned) to the start of the next, so
  connection set-up time cannot shorten the gap the server sees. The wait uses a
  monotonic clock, and the log records each contact's start and end times and
  the measured interval, in milliseconds;
- robots.txt per origin with an RFC 9309 matcher. Paths and rules are compared
  after RFC 9309 section 2.2.2 percent-encoding normalisation, on the exact
  path that is sent. 404 and other 4xx answers mean robots is unavailable
  (allowed), except 401, 403 and 429, which mean disallow all. Disallow all is
  also the answer for 5xx, a network or TLS failure, a bot-protection page, an
  HTML page served as robots.txt, a 3xx without a usable redirect, and more
  than five redirects. That last reading is conservative: RFC 9309 permits,
  but does not require, treating it as unavailable. The stricter 4xx rule
  follows the v4 map, which treated a bot-protection 403 on robots.txt as
  "do not fetch this host";
- page redirects are never followed automatically. Each hop is logged, and
  only a plan step may request the target, after that host's own robots check.
  robots.txt redirects are followed, paced and logged, up to five hops, as
  RFC 9309 expects; a 3xx without a usable Location ends the robots check;
- a bot-protection page on any request blocks that host for the rest of the
  run. Interstitial or block pages count at any status; scripts that ordinary
  pages also load (a CAPTCHA widget, a bot-detection script) count only on a
  401, 403, 429 or 503 response, and are otherwise just logged;
- certificates are verified for every HTTP request and TLS diagnostic, and a
  TLS failure makes the host unreadable. After a failed verified handshake, the
  TLS diagnostic may make one more handshake without verification, only to
  read the presented certificate's dates; it sends no HTTP request;
- login, apply, registration and account URLs and host names are refused
  without a request, and the path that would be sent must equal the path that
  was checked;
- hard caps on contacts per host and per run.
"""
import argparse
import hashlib
import json
import re
import socket
import ssl
import string
import sys
import time
from datetime import datetime, timezone
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import unquote, urljoin, urlsplit

import httpx

USER_AGENT = 'ASTRA-source-research/1.0 (read-only official careers-page check; robots.txt honoured)'
PRODUCT_TOKEN = 'astra-source-research'
MIN_INTERVAL = 2.0
MAX_CONTACTS_PER_HOST = 8
MAX_CONTACTS_PER_RUN = 80
MAX_BODY_BYTES = 2 * 1024 * 1024
MAX_REDIRECTS = 5
TIMEOUT = 20.0
REDIRECT_STATUSES = (301, 302, 303, 307, 308)
ROBOTS_REFUSAL_STATUSES = (401, 403, 429)

REFUSED = re.compile(
    r'apply|application|log[-_ ]?(?:in|on)|sign[-_ ]?(?:in|on|up)|regist(?:er|ration)|account|oauth|'
    r'authenticat|authori[sz]|password|passwd|checkout|candidate/profile|/sso(?:[/?.]|$)|/auth(?:[/?.]|$)', re.I)
REFUSED_HOST_LABEL = re.compile(
    r'apply|login|logon|signin|signon|sso|auth|idp|id|identity|account|accounts|myaccount|register', re.I)
JOB_WORDS = re.compile(r'career|job|vacanc|recruit|join us|join our|hiring|talent|employment|'
                       r'candidateexperience|وظائف|وظيفة|التوظيف|الشواغر|انضم', re.I)
PERMITTED_ADAPTER_HOSTS = {
    'boards.greenhouse.io': 'greenhouse', 'job-boards.greenhouse.io': 'greenhouse',
    'boards-api.greenhouse.io': 'greenhouse', 'jobs.lever.co': 'lever', 'api.lever.co': 'lever',
    'jobs.ashbyhq.com': 'ashby', 'api.ashbyhq.com': 'ashby',
}
OTHER_ATS = [
    ('oracle', re.compile(r'\.oraclecloud\d*\.com$')), ('taleo', re.compile(r'taleo\.net$')),
    ('successfactors', re.compile(r'successfactors\.(?:com|eu)$|sapsf\.')), ('workday', re.compile(r'myworkdayjobs\.com$')),
    ('icims', re.compile(r'icims\.com$')), ('avature', re.compile(r'avature\.net$')),
    ('smartrecruiters', re.compile(r'smartrecruiters\.com$')), ('interfolio', re.compile(r'interfolio\.com$')),
    ('linkedin', re.compile(r'(?:^|\.)linkedin\.com$')),
]
STRONG_CHALLENGES = [  # an interstitial or block page, whatever the status
    ('Cloudflare', re.compile(r'Attention Required! \| Cloudflare|<title>\s*Just a moment\.\.\.|_cf_chl_opt|'
                              r'Sorry, you have been blocked', re.I)),
    ('WAF rejection', re.compile(r'<title>\s*Request Rejected', re.I)),
    ('Imperva/Incapsula', re.compile(r'Incapsula incident|_Incapsula_Resource', re.I)),
    ('F5 challenge', re.compile(r'TSPD_101', re.I)),
    ('Akamai denial', re.compile(r'<title>\s*Access Denied\s*</title>.*Reference\s*#', re.I | re.S)),
]
WEAK_CHALLENGES = [  # scripts ordinary pages also load; a challenge only on a blocking status
    ('Cloudflare', re.compile(r'challenge-platform|cf-chl-', re.I)),
    ('F5 challenge', re.compile(r'/TSbd/', re.I)),
    ('CAPTCHA', re.compile(r'g-recaptcha|h-captcha|hcaptcha\.com/1/api|captcha-delivery', re.I)),
]
BLOCKING_STATUSES = (401, 403, 429, 503)
UNRESERVED = frozenset(string.ascii_letters + string.digits + '-._~')
HEX = frozenset(b'0123456789abcdefABCDEF')


class PlanError(ValueError):
    pass


class HostCapReached(PlanError):
    """This host has had its quota of contacts; the step is skipped, the run goes on."""


class RefusedURL(PlanError):
    """A URL this tool never requests."""


# --- URLs ----------------------------------------------------------------------
def normalise(raw):
    """RFC 9309 s2.2.2: percent-encode octets outside printable ASCII, decode
    %XX of unreserved characters, and upper-case the remaining hex."""
    data = raw.encode('utf-8') if isinstance(raw, str) else raw
    out, i = [], 0
    while i < len(data):
        octet = data[i]
        if octet == 0x25 and i + 2 < len(data) and data[i + 1] in HEX and data[i + 2] in HEX:
            value = int(data[i + 1:i + 3], 16)
            out.append(chr(value) if chr(value) in UNRESERVED else f'%{value:02X}')
            i += 3
            continue
        out.append(f'%{octet:02X}' if octet <= 0x20 or octet >= 0x7f or chr(octet) in '"<>\\^`{|}' else chr(octet))
        i += 1
    return ''.join(out)


def _remove_dot_segments(path):
    """RFC 3986 section 5.2.4."""
    output, segments = [], path.split('/')
    for index, segment in enumerate(segments):
        last = index == len(segments) - 1
        if segment == '.':
            if last:
                output.append('')
        elif segment == '..':
            if len(output) > 1:
                output.pop()
            if last:
                output.append('')
        else:
            output.append(segment)
    result = '/'.join(output)
    return result if result.startswith('/') else '/' + result


def canonical(url):
    """The exact https URL this tool would send, its host key and its match path.

    Raises RefusedURL for anything other than https on the default port, for
    user information, and for login, apply, registration or account URLs."""
    try:
        parsed = httpx.URL(url)
    except (httpx.InvalidURL, TypeError) as exc:
        raise RefusedURL(f'refused: not a valid URL ({exc})') from exc
    if parsed.scheme != 'https':
        raise RefusedURL('refused: only https is requested')
    if parsed.userinfo:
        raise RefusedURL('refused: user information in the URL')
    if parsed.port not in (None, 443):
        raise RefusedURL('refused: only the default https port is requested')
    host = parsed.raw_host.decode('ascii').lower().rstrip('.')
    if not host:
        raise RefusedURL('refused: no host')
    if any(REFUSED_HOST_LABEL.fullmatch(label) for label in host.split('.')):
        raise RefusedURL('refused: login, apply, registration or account host')
    raw_path = parsed.raw_path.decode('ascii')
    path, _, query = raw_path.partition('?')
    path = _remove_dot_segments(normalise(path or '/'))
    target = path + (('?' + normalise(query)) if query else '')
    if REFUSED.search(unquote(target)):
        raise RefusedURL('refused: login, apply, registration or account URL')
    url = f'https://{host}{target}'
    sent = httpx.URL(url).raw_path.decode('ascii')
    if sent != target:
        raise RefusedURL(f'refused: the path that would be sent ({sent}) differs from the checked path ({target})')
    return {'url': url, 'host': host, 'origin': f'https://{host}', 'match_path': target}


def canonical_host(host):
    return canonical(f'https://{host}/')['host']


# --- RFC 9309 ------------------------------------------------------------------
def parse_robots(text):
    """Groups of user-agent lines and their allow/disallow rules."""
    groups, current, in_rules = [], None, False
    for raw in text.lstrip('\ufeff').splitlines():
        line = raw.split('#', 1)[0].strip()
        if ':' not in line:
            continue
        key, value = (part.strip() for part in line.split(':', 1))
        key = key.lower()
        if key == 'user-agent':
            if current is None or in_rules:
                current = {'agents': [], 'rules': []}
                groups.append(current)
                in_rules = False
            current['agents'].append(value.lower())
        elif key in ('allow', 'disallow') and current is not None:
            in_rules = True
            current['rules'].append((key, value))
    return groups


def _names_us(agent, token):
    return agent == token or agent.startswith(token + '/')


def rules_for(groups, token=PRODUCT_TOKEN):
    """Rules of every group naming this product token (case-insensitive, with or
    without a /version), else of the '*' group."""
    token = token.lower()
    mine = [g for g in groups if any(_names_us(agent, token) for agent in g['agents'])]
    if not mine:
        mine = [g for g in groups if '*' in g['agents']]
    return [rule for group in mine for rule in group['rules']]


def _pattern_regex(pattern):
    anchored = pattern.endswith('$')
    body = pattern[:-1] if anchored else pattern
    return '^' + '.*'.join(re.escape(normalise(part)) for part in body.split('*')) + ('$' if anchored else '')


def robots_allows(rules, path):
    """Longest match wins; on a tie, allow wins; no match allows. Both sides are normalised."""
    path, best = normalise(path), None
    for kind, pattern in rules:
        if pattern and re.match(_pattern_regex(pattern), path):
            rank = (len(normalise(pattern)), kind == 'allow')
            if best is None or rank > best[0]:
                best = (rank, kind, pattern)
    if best is None:
        return True, 'no matching rule'
    return best[1] == 'allow', f"{best[1]} '{best[2]}'"


def looks_like_html(content_type, body):
    if 'html' in (content_type or '').lower():
        return True
    head = body[:65536].decode('utf-8', 'replace').lstrip('\ufeff').lstrip()
    return head.startswith('<') or re.search(
        r'<(?:!doctype|html|head|body|script|meta|link|title|div|span|a|p)\b', head, re.I) is not None


# --- page reading --------------------------------------------------------------
class _Links(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.links, self.title, self._href, self._text, self._in_title = [], '', None, [], False

    def handle_starttag(self, tag, attrs):
        if tag == 'a':
            self._href, self._text = dict(attrs).get('href'), []
        elif tag == 'title':
            self._in_title = True

    def handle_endtag(self, tag):
        if tag == 'a' and self._href is not None:
            self.links.append((self._href, ' '.join(''.join(self._text).split())))
            self._href = None
        elif tag == 'title':
            self._in_title = False

    def handle_data(self, data):
        if self._href is not None:
            self._text.append(data)
        if self._in_title:
            self.title += data


def classify_host(host):
    host = (host or '').lower().rstrip('.')
    if host in PERMITTED_ADAPTER_HOSTS:
        return 'permitted_adapter:' + PERMITTED_ADAPTER_HOSTS[host]
    for name, pattern in OTHER_ATS:
        if pattern.search(host):
            return 'other_ats:' + name
    return None


def challenge_in(response_headers, body_text, status=200):
    if response_headers.get('cf-mitigated'):
        return 'Cloudflare (cf-mitigated header)'
    head = body_text[:40000]
    for name, pattern in STRONG_CHALLENGES:
        if pattern.search(head):
            return name
    if status in BLOCKING_STATUSES:
        for name, pattern in WEAK_CHALLENGES:
            if pattern.search(head):
                return name
    return None


def bot_scripts_seen(body_text):
    return sorted({name for name, pattern in WEAK_CHALLENGES if pattern.search(body_text[:40000])})


def _utc_ms(moment):
    return moment.astimezone(timezone.utc).isoformat(timespec='milliseconds')


def tool_identity(path=None):
    data = Path(path or __file__).read_bytes()
    normalised = data.replace(b'\r\n', b'\n')
    return {'file': 'scripts/source_route_check.py',
            'sha256_lf': hashlib.sha256(normalised).hexdigest(),
            'git_blob_lf': hashlib.sha1(b'blob %d\0' % len(normalised) + normalised).hexdigest()}


# --- the checker ---------------------------------------------------------------
class RouteChecker:
    def __init__(self, transport=None, clock=time.monotonic, sleep=time.sleep,
                 wall=lambda: datetime.now(timezone.utc), resolver=None, tls_probe=None, cert_reader=None,
                 min_interval=MIN_INTERVAL):
        if min_interval < MIN_INTERVAL:
            raise PlanError(f'min_interval may not be below {MIN_INTERVAL} s')
        self.min_interval = min_interval
        self.clock, self.sleep, self.wall = clock, sleep, wall
        self.resolver = resolver or (lambda host: sorted({info[4][0] for info in socket.getaddrinfo(host, 443)}))
        self.tls_probe = tls_probe or _tls_probe
        self.cert_reader = cert_reader or _read_presented_certificate
        self.client = httpx.Client(transport=transport, follow_redirects=False, timeout=TIMEOUT, verify=True,
                                   headers={'User-Agent': USER_AGENT,
                                            'Accept': 'text/html,application/xhtml+xml,text/plain;q=0.9,*/*;q=0.5'},
                                   event_hooks={'request': [self._request_guard]})
        self.log, self.robots, self.blocked_hosts = [], {}, {}
        self.last_end, self.contacts, self.intervals = {}, {}, []
        self.results, self.aborted = {}, None

    # pacing ------------------------------------------------------------------
    def _pace(self, host):
        """Wait until MIN_INTERVAL has passed since this host's previous contact *ended*
        (its response closed, or its handshake returned), then stamp the new contact."""
        if sum(self.contacts.values()) >= MAX_CONTACTS_PER_RUN:
            raise PlanError('per-run contact cap reached')
        if self.contacts.get(host, 0) >= MAX_CONTACTS_PER_HOST:
            raise HostCapReached(f'per-host contact cap reached for {host}')
        last_end = self.last_end.get(host)
        if last_end is not None:
            remaining = self.min_interval - (self.clock() - last_end)
            while remaining > 0:
                self.sleep(remaining)
                remaining = self.min_interval - (self.clock() - last_end)
        now = self.clock()
        since = None if last_end is None else round(now - last_end, 3)
        if since is not None:
            self.intervals.append({'host': host, 'since_prev_end_s': since})
        self.contacts[host] = self.contacts.get(host, 0) + 1
        return {'started_at_utc': _utc_ms(self.wall()), 'since_prev_contact_end_s': since}

    def _done(self, host, stamp):
        self.last_end[host] = self.clock()
        stamp['ended_at_utc'] = _utc_ms(self.wall())

    def _unpace(self, host, stamp):
        """A contact that a guard stopped before anything was sent."""
        self.contacts[host] -= 1
        if stamp['since_prev_contact_end_s'] is not None and self.intervals and self.intervals[-1]['host'] == host:
            self.intervals.pop()

    @staticmethod
    def _request_guard(request):
        if request.method != 'GET':
            raise PlanError(f'refusing a {request.method} request')
        if 'cookie' in request.headers:
            raise PlanError('a cookie was about to be sent')

    def _get(self, target):
        """One paced GET of a canonical target; the body is capped; cookies are discarded."""
        host = target['host']
        stamp = self._pace(host)
        try:
            with self.client.stream('GET', target['url']) as response:
                body = b''
                for chunk in response.iter_bytes():
                    body += chunk
                    if len(body) >= MAX_BODY_BYTES:
                        body = body[:MAX_BODY_BYTES]
                        break
                result = {'status': response.status_code, 'headers': response.headers, 'body': body,
                          'set_cookie_seen': 'set-cookie' in response.headers}
        except PlanError as exc:  # a request guard stopped it before anything was sent
            self.client.cookies.clear()
            self._unpace(host, stamp)
            self.log.append({'url': target['url'], 'requested': False, 'decision': f'not sent: {exc}',
                             'decided_at_utc': _utc_ms(self.wall())})
            raise
        except (httpx.HTTPError, httpx.InvalidURL) as exc:
            result = {'error': _error_text(exc)}
        self.client.cookies.clear()
        self._done(host, stamp)
        return stamp, result

    # robots --------------------------------------------------------------------
    def robots_for(self, origin):
        if origin in self.robots:
            return self.robots[origin]
        url, hops = origin + '/robots.txt', 0
        while True:
            entry = {'url': url, 'purpose': 'robots'}
            try:
                target = canonical(url)
            except RefusedURL as exc:
                target, refusal = None, f'robots redirect {exc}'
            else:
                refusal = (f"host blocked earlier: {self.blocked_hosts[target['host']]}"
                           if target['host'] in self.blocked_hosts else None)
            if refusal:
                decision = {'kind': 'UNREACHABLE_DISALLOW', 'reason': refusal}
                entry.update(requested=False, decision=refusal, decided_at_utc=_utc_ms(self.wall()))
                break
            stamp, got = self._get(target)
            entry = {**stamp, **entry, 'url': target['url']}
            if 'error' in got:
                entry['error'] = got['error']
                decision = {'kind': 'UNREACHABLE_DISALLOW', 'reason': got['error']}
                self.blocked_hosts[target['host']] = 'network or TLS failure'
                break
            status, body, headers = got['status'], got['body'], got['headers']
            text = body.decode('utf-8-sig', 'replace')
            entry.update(status=status, content_type=headers.get('content-type'), set_cookie_seen=got['set_cookie_seen'])
            challenge = challenge_in(headers, text, status)
            if challenge:
                entry['challenge'] = f'{challenge}: not bypassed; host blocked for the rest of the run'
                self.blocked_hosts[target['host']] = challenge
                decision = {'kind': 'CHALLENGE_DISALLOW', 'reason': f'bot-protection page at robots.txt ({challenge})'}
                break
            location = _join(target['url'], headers.get('location')) if status in REDIRECT_STATUSES else None
            if location:
                entry['redirect_to'] = location
                self.log.append({**entry, 'robots_result': 'REDIRECT'})
                hops += 1
                if hops > MAX_REDIRECTS:
                    decision = {'kind': 'UNREACHABLE_DISALLOW',
                                'reason': 'more than five redirects (conservative; RFC 9309 would permit "unavailable")'}
                    entry = {'url': entry['redirect_to'], 'purpose': 'robots', 'requested': False,
                             'decision': decision['reason'], 'decided_at_utc': _utc_ms(self.wall())}
                    break
                url = entry['redirect_to']
                continue
            if 300 <= status < 400:
                decision = {'kind': 'UNREACHABLE_DISALLOW', 'reason': f'HTTP {status} without a usable redirect'}
            elif status in ROBOTS_REFUSAL_STATUSES:
                decision = {'kind': 'REFUSED_DISALLOW',
                            'reason': f'HTTP {status}: the server refused robots.txt (v4 conservative rule)'}
            elif 400 <= status < 500:
                decision = {'kind': 'UNAVAILABLE_ALLOW', 'reason': f'HTTP {status}'}
            elif status >= 500:
                decision = {'kind': 'UNREACHABLE_DISALLOW', 'reason': f'HTTP {status}'}
            elif looks_like_html(headers.get('content-type'), body) or (not parse_robots(text) and '<' in text):
                decision = {'kind': 'UNREADABLE_DISALLOW',
                            'reason': 'HTML served as robots.txt (unreadable; treated as disallow all)'}
            else:
                rules = rules_for(parse_robots(text))
                decision = {'kind': 'PARSED', 'reason': f'{len(rules)} applicable rules', 'rules': rules}
                entry['applicable_rules'] = [f'{k}: {v}' for k, v in rules][:20]
            break
        entry['robots_result'] = decision['kind']
        self.log.append(entry)
        self.robots[origin] = decision
        return decision

    # plan steps ------------------------------------------------------------------
    def page(self, step, employer, url=None):
        url = url or step['url']
        entry = {'step': step['id'], 'employer': employer, 'purpose': step.get('purpose', ''), 'url': url}
        try:
            target = canonical(url)
        except RefusedURL as exc:
            return self._skip(entry, str(exc))
        if target['url'] != url:
            entry['sent_url'] = target['url']
        if target['host'] in self.blocked_hosts:
            return self._skip(entry, f"not requested: host blocked earlier ({self.blocked_hosts[target['host']]})")
        decision = self.robots_for(target['origin'])
        entry['robots'] = decision['kind']
        if decision['kind'] not in ('PARSED', 'UNAVAILABLE_ALLOW'):
            return self._skip(entry, f"not requested: robots {decision['kind']} ({decision['reason']})")
        if decision['kind'] == 'PARSED':
            allowed, why = robots_allows(decision['rules'], target['match_path'])
            entry['robots_rule'] = why
            if not allowed:
                return self._skip(entry, f'not requested: disallowed by {why}')
        stamp, got = self._get(target)
        entry = {**stamp, **entry, 'requested': True}
        if 'error' in got:
            entry['error'] = got['error']
            self.blocked_hosts[target['host']] = 'network or TLS failure'
            return self._record(entry)
        headers, body = got['headers'], got['body']
        text = body.decode('utf-8', 'replace')
        entry.update(status=got['status'], content_type=headers.get('content-type'), bytes=len(body),
                     set_cookie_seen=got['set_cookie_seen'])
        challenge = challenge_in(headers, text, got['status'])
        if challenge:
            entry['challenge'] = f'{challenge}: not bypassed; host blocked for the rest of the run'
            self.blocked_hosts[target['host']] = challenge
            return self._record(entry)
        scripts = bot_scripts_seen(text)
        if scripts:
            entry['bot_protection_scripts_seen'] = scripts
        if 300 <= got['status'] < 400:
            if headers.get('location'):
                location = _join(target['url'], headers['location'])
                if location:
                    entry['redirect_to'] = location
                    entry['redirect_to_class'] = classify_host(_hostname(location))
                else:
                    entry['redirect_error'] = 'unusable Location header'
            return self._record(entry)
        if looks_like_html(headers.get('content-type'), body):
            parser = _Links()
            try:
                parser.feed(text)
            except Exception:  # malformed HTML still yields what was parsed
                pass
            entry['title'] = ' '.join(parser.title.split())[:160]
            links, unusable = [], 0
            for href, label in parser.links:
                if not href or href.startswith(('javascript:', '#', 'mailto:', 'tel:')):
                    continue
                absolute = _join(target['url'], href)
                if not absolute:
                    unusable += 1
                    continue
                kind = classify_host(_hostname(absolute))
                if kind or JOB_WORDS.search(absolute) or JOB_WORDS.search(label or ''):
                    links.append({'text': (label or '')[:100], 'href': absolute, 'class': kind})
            entry['job_links'] = list({(l['href'], l['text']): l for l in links}.values())[:60]
            if unusable:
                entry['unusable_hrefs_skipped'] = unusable
            entry['permitted_adapter_links'] = [l for l in entry['job_links'] if (l['class'] or '').startswith('permitted_adapter')]
        if step.get('find'):
            entry['found'] = sorted(set(m.group(0)[:200] for m in re.finditer(step['find'], text)))[:20]
        return self._record(entry)

    def _source_not_requested(self, step, employer):
        source = self.results.get(step['from']) or {}
        if source.get('requested') is False:
            return self._skip({'step': step['id'], 'employer': employer, 'purpose': step.get('purpose', ''),
                               'url': None}, f"not requested: source step {step['from']} was not requested")
        return None

    def links(self, step, employer):
        if self._source_not_requested(step, employer):
            return None
        source = self.results.get(step['from']) or {}
        pattern = re.compile(step['match'], re.I)
        picked = [l['href'] for l in source.get('job_links', []) if pattern.search(l['text'] + ' ' + l['href'])]
        picked = list(dict.fromkeys(picked))[:step.get('max', 2)]
        if not picked:
            return self._skip({'step': step['id'], 'employer': employer, 'purpose': step.get('purpose', ''),
                               'url': None}, f"no link from {step['from']} matched {step['match']!r}")
        for number, href in enumerate(picked, 1):
            self.page({**step, 'id': f"{step['id']}#{number}"}, employer, href)

    def redirect(self, step, employer):
        if self._source_not_requested(step, employer):
            return None
        source = self.results.get(step['from']) or {}
        target = source.get('redirect_to')
        if not target:
            return self._skip({'step': step['id'], 'employer': employer, 'purpose': step.get('purpose', ''),
                               'url': None}, f"{step['from']} did not redirect")
        return self.page(step, employer, target)

    def tls(self, step, employer):
        """Verified handshake only. If it fails, a second, separately paced handshake
        reads the presented certificate's dates. Neither sends an HTTP request."""
        base = {'step': step['id'], 'employer': employer, 'host': step['host'],
                'purpose': step.get('purpose', 'TLS handshake-only diagnostic (no HTTP request)')}
        try:
            host = canonical_host(step['host'])
        except RefusedURL as exc:
            return self._skip(base, str(exc))
        if self.blocked_hosts.get(host, 'network or TLS failure') != 'network or TLS failure':
            return self._skip(base, f'not requested: host blocked earlier ({self.blocked_hosts[host]})')
        stamp = self._pace(host)
        probe = self.tls_probe(host)
        self._done(host, stamp)
        entry = self._record({**stamp, **base, 'host': host, **probe})
        if not entry.get('verified') and step.get('read_presented_certificate', True):
            try:
                second = self._pace(host)
            except HostCapReached as exc:
                entry['presented_certificate'] = {'read': False, 'reason': str(exc)}
                return entry
            reading = self.cert_reader(host)
            self._done(host, second)
            entry['presented_certificate'] = {**second, **reading}
        return entry

    def dns(self, step, employer):
        entry = {'step': step['id'], 'employer': employer, 'host': step['host'],
                 'purpose': step.get('purpose', 'DNS resolution only (no contact with the host)'),
                 'resolved_at_utc': _utc_ms(self.wall())}
        try:
            entry['addresses'] = self.resolver(step['host'])
        except OSError as exc:
            entry['error'] = _error_text(exc)
        return self._record(entry)

    def _skip(self, entry, reason):
        entry.update(requested=False, decision=reason, decided_at_utc=_utc_ms(self.wall()))
        return self._record(entry)

    def _record(self, entry):
        self.log.append(entry)
        self.results[entry['step']] = entry
        return entry

    def run(self, plan):
        validate_plan(plan)
        try:
            for employer in plan['employers']:
                for step in employer['steps']:
                    try:
                        getattr(self, step['kind'])(step, employer['employer'])
                    except HostCapReached as exc:  # skip this step only
                        self._skip({'step': step['id'], 'employer': employer['employer'],
                                    'purpose': step.get('purpose', ''), 'url': step.get('url')}, f'not requested: {exc}')
        except PlanError as exc:  # the run cap or a request guard stops the run; the log is kept
            self.aborted = str(exc)
        except Exception as exc:  # anything unexpected also stops the run with the log kept
            self.aborted = f'unexpected error: {_error_text(exc)}'
        return self.report()

    def report(self):
        by_host = {}
        for item in self.intervals:
            by_host.setdefault(item['host'], []).append(item['since_prev_end_s'])
        return {'aborted': self.aborted, 'log': self.log,
                'robots': {origin: {k: v for k, v in d.items() if k != 'rules'} for origin, d in self.robots.items()},
                'blocked_hosts': self.blocked_hosts,
                'pacing': {'min_interval_s': self.min_interval,
                           'measured_from': 'end of the previous contact with the host to the start of the next',
                           'same_host_intervals': len(self.intervals),
                           'smallest_same_host_interval_s': min((i['since_prev_end_s'] for i in self.intervals), default=None),
                           'all_intervals_at_least_minimum': all(i['since_prev_end_s'] >= self.min_interval for i in self.intervals),
                           'by_host': by_host},
                'contacts_by_host': self.contacts}


def _join(base, href):
    """urljoin that returns None for a value it cannot use."""
    href = (href or '').strip()
    if not href:
        return None
    try:
        joined = urljoin(base, href)
        urlsplit(joined).hostname  # raises on a malformed authority
        return joined or None
    except ValueError:
        return None


def _hostname(url):
    try:
        return urlsplit(url).hostname
    except ValueError:
        return None


def _error_text(exc):
    inner = exc
    while inner.__cause__ or inner.__context__:
        inner = inner.__cause__ or inner.__context__
    return f'{type(inner).__name__}: {inner}'


def _tls_context():
    """Certificate- and host-verifying context that refuses TLS 1.0 and 1.1."""
    context = ssl.create_default_context()
    context.minimum_version = ssl.TLSVersion.TLSv1_2
    return context


def _tls_probe(host):
    """Verified TLS handshake only; no HTTP request."""
    context = _tls_context()
    try:
        with socket.create_connection((host, 443), timeout=TIMEOUT) as raw, context.wrap_socket(raw, server_hostname=host) as tls:
            cert = tls.getpeercert()
            return {'verified': True, 'not_after': cert.get('notAfter'),
                    'issuer': dict(x[0] for x in cert.get('issuer', ())).get('commonName')}
    except (OSError, ssl.SSLError) as exc:
        return {'verified': False, 'error': _error_text(exc)}


def _read_presented_certificate(host):
    """Read the certificate a host presents, to report its dates. No HTTP request is
    sent and nothing from the host is used; this is a diagnostic, not access."""
    try:
        pem = ssl.get_server_certificate((host, 443), timeout=TIMEOUT)
        decoder = getattr(ssl._ssl, '_test_decode_cert', None)  # CPython helper; absent elsewhere
        if not decoder:
            return {'read': False, 'reason': 'no certificate decoder in this Python'}
        import os
        import tempfile
        with tempfile.NamedTemporaryFile('w', suffix='.pem', delete=False) as handle:
            handle.write(pem)
        try:
            info = decoder(handle.name)
        finally:
            os.unlink(handle.name)
        return {'read': True, 'not_before': info.get('notBefore'), 'not_after': info.get('notAfter'),
                'subject': dict(x[0] for x in info.get('subject', ())).get('commonName'),
                'issuer': dict(x[0] for x in info.get('issuer', ())).get('commonName'),
                'subject_alt_names': [value for _, value in info.get('subjectAltName', ())][:5]}
    except (OSError, ssl.SSLError, ValueError) as exc:
        return {'read': False, 'reason': _error_text(exc)}


KINDS = {'page': ('url',), 'links': ('from', 'match'), 'redirect': ('from',), 'tls': ('host',), 'dns': ('host',)}


def validate_plan(plan):
    seen = set()
    if not plan.get('employers'):
        raise PlanError('plan has no employers')
    for employer in plan['employers']:
        for step in employer.get('steps', []):
            kind = step.get('kind')
            if kind not in KINDS:
                raise PlanError(f'unknown step kind {kind!r}')
            missing = [k for k in ('id', *KINDS[kind]) if not step.get(k)]
            if missing:
                raise PlanError(f"step {step.get('id')!r} lacks {missing}")
            if step['id'] in seen:
                raise PlanError(f"duplicate step id {step['id']!r}")
            if kind in ('links', 'redirect') and step['from'] not in seen:
                raise PlanError(f"step {step['id']!r} refers to a later or unknown step {step['from']!r}")
            if kind == 'page':
                try:
                    canonical(step['url'])
                except RefusedURL as exc:
                    raise PlanError(f"step {step['id']!r}: {exc}") from exc
            for key in ('match', 'find'):
                if step.get(key):
                    try:
                        re.compile(step[key])
                    except re.error as exc:
                        raise PlanError(f"step {step['id']!r}: bad {key} pattern ({exc})") from exc
            seen.add(step['id'])


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('plan', help='JSON plan: {"employers": [{"employer": ..., "steps": [...]}]}')
    parser.add_argument('--out', help='write the JSON log here (required for a live run)')
    parser.add_argument('--validate-only', action='store_true', help='check the plan and exit without any request')
    args = parser.parse_args(argv)
    plan_bytes = Path(args.plan).read_bytes()
    plan = json.loads(plan_bytes)
    validate_plan(plan)
    if args.validate_only:
        print(json.dumps({'plan_ok': True, 'steps': sum(len(e['steps']) for e in plan['employers'])}))
        return 0
    if not args.out:
        parser.error('--out is required for a live run')
    started = datetime.now(timezone.utc)
    report = RouteChecker().run(plan)
    report = {'tool': tool_identity(), 'user_agent': USER_AGENT,
              'client': {'python': sys.version.split()[0], 'httpx': httpx.__version__, 'openssl': ssl.OPENSSL_VERSION},
              'plan_sha256': hashlib.sha256(plan_bytes.replace(b'\r\n', b'\n')).hexdigest(), 'plan': plan,
              'started_at_utc': _utc_ms(started), 'finished_at_utc': _utc_ms(datetime.now(timezone.utc)), **report}
    with open(args.out, 'w', encoding='utf-8', newline='\n') as handle:
        json.dump(report, handle, ensure_ascii=False, indent=1)
        handle.write('\n')
    print(json.dumps({'out': args.out, 'aborted': report['aborted'],
                      'pacing_ok': report['pacing']['all_intervals_at_least_minimum'],
                      'contacts': sum(report['contacts_by_host'].values())}))
    return 0


if __name__ == '__main__':
    sys.exit(main())
