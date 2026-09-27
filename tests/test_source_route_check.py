"""The #46.2-B route checker, driven only through a fictional transport."""

import json
import socket
from datetime import datetime, timedelta, timezone

import httpx
import pytest

from scripts import source_route_check as src

UA_HEADER = src.USER_AGENT


class FakeTime:
    def __init__(self):
        self.now, self.sleeps = 1000.0, []

    def clock(self):
        return self.now

    def sleep(self, seconds):
        self.sleeps.append(round(seconds, 3))
        self.now += seconds

    def wall(self):
        return datetime(2030, 1, 1, tzinfo=timezone.utc) + timedelta(seconds=self.now)


class Site:
    """Fictional hosts: {(host, path): response or callable(request)}."""

    def __init__(self, routes):
        self.routes, self.requests = routes, []

    def __call__(self, request):
        self.requests.append(request)
        answer = self.routes.get((request.url.host, request.url.raw_path.decode()))
        if answer is None:
            return httpx.Response(404, text='not here')
        return answer(request) if callable(answer) else answer

    def paths(self):
        return [(r.url.host, r.url.raw_path.decode()) for r in self.requests]


@pytest.fixture(autouse=True)
def no_network(monkeypatch):
    def refuse(*args, **kwargs):
        raise AssertionError('network access attempted in a fictional test')
    monkeypatch.setattr(socket, 'create_connection', refuse)
    monkeypatch.setattr(socket, 'getaddrinfo', refuse)


def html(body, **headers):
    return httpx.Response(200, headers={'content-type': 'text/html', **headers}, text=body)


def robots(text, status=200):
    return httpx.Response(status, headers={'content-type': 'text/plain'}, text=text)


def checker(site, fake=None, **kwargs):
    fake = fake or FakeTime()
    return src.RouteChecker(transport=httpx.MockTransport(site), clock=fake.clock, sleep=fake.sleep,
                            wall=fake.wall, resolver=lambda host: ['192.0.2.1'], **kwargs), fake


def plan(*steps, employer='Fictional Employer'):
    return {'employers': [{'employer': employer, 'steps': list(steps)}]}


def page(step_id, url, **extra):
    return {'id': step_id, 'kind': 'page', 'url': url, 'purpose': 'test', **extra}


def entries(report, step_id):
    return [e for e in report['log'] if e.get('step') == step_id]


def test_same_host_contacts_wait_and_are_stamped_after_the_wait():
    site = Site({('careers.example.test', '/robots.txt'): robots('', 404),
                 ('careers.example.test', '/a'): html('<title>A</title>'),
                 ('careers.example.test', '/b'): html('<title>B</title>')})
    check, fake = checker(site)
    report = check.run(plan(page('a', 'https://careers.example.test/a'), page('b', 'https://careers.example.test/b')))

    assert site.paths() == [('careers.example.test', '/robots.txt'), ('careers.example.test', '/a'),
                            ('careers.example.test', '/b')]
    assert fake.sleeps == [2.0, 2.0]
    robots_entry = next(e for e in report['log'] if e.get('purpose') == 'robots')
    a, b = entries(report, 'a')[0], entries(report, 'b')[0]
    assert (robots_entry['since_prev_contact_end_s'], a['since_prev_contact_end_s'], b['since_prev_contact_end_s']) == (None, 2.0, 2.0)
    stamps = [datetime.fromisoformat(e['started_at_utc']) for e in (robots_entry, a, b)]
    assert [(later - earlier).total_seconds() for earlier, later in zip(stamps, stamps[1:])] == [2.0, 2.0]
    assert report['pacing']['all_intervals_at_least_minimum'] is True
    assert report['pacing']['smallest_same_host_interval_s'] == 2.0


def test_elapsed_time_counts_toward_the_interval_and_other_hosts_do_not_wait():
    site = Site({('one.example.test', '/robots.txt'): robots('', 404), ('one.example.test', '/x'): html('x'),
                 ('two.example.test', '/robots.txt'): robots('', 404), ('two.example.test', '/y'): html('y')})
    fake = FakeTime()

    def slow_clock():  # 1.5 s passes between consecutive clock reads
        fake.now += 0.75
        return fake.now
    check = src.RouteChecker(transport=httpx.MockTransport(site), clock=slow_clock, sleep=fake.sleep, wall=fake.wall)
    report = check.run(plan(page('x', 'https://one.example.test/x'), page('y', 'https://two.example.test/y')))

    two_robots = next(e for e in report['log'] if e.get('url') == 'https://two.example.test/robots.txt')
    assert two_robots['since_prev_contact_end_s'] is None
    assert all(i['since_prev_end_s'] >= 2.0 for i in check.intervals)
    assert all(s < 2.0 for s in fake.sleeps)


def test_minimum_interval_cannot_be_lowered():
    with pytest.raises(src.PlanError):
        src.RouteChecker(transport=httpx.MockTransport(Site({})), min_interval=1.0)


@pytest.mark.parametrize('robots_response, requested, kind', [
    (robots('', 404), True, 'UNAVAILABLE_ALLOW'),
    (robots('', 410), True, 'UNAVAILABLE_ALLOW'),
    (robots('', 401), False, 'REFUSED_DISALLOW'),
    (robots('', 403), False, 'REFUSED_DISALLOW'),
    (robots('', 429), False, 'REFUSED_DISALLOW'),
    (robots('', 503), False, 'UNREACHABLE_DISALLOW'),
    (httpx.Response(300, headers={'content-type': 'text/plain'}, text='User-agent: *\nAllow: /\n'), False,
     'UNREACHABLE_DISALLOW'),
    (httpx.Response(302), False, 'UNREACHABLE_DISALLOW'),
    (html('<!doctype html><html><title>Home</title></html>'), False, 'UNREADABLE_DISALLOW'),
    (httpx.Response(200, headers={'content-type': 'text/plain'}, text='<html><body>Home</body></html>'),
     False, 'UNREADABLE_DISALLOW'),
    (httpx.Response(200, headers={'content-type': 'text/plain'}, content='\ufeff<!-- c --><div>Home</div>'.encode()),
     False, 'UNREADABLE_DISALLOW'),
    (httpx.Response(200, content=b'<?xml version="1.0"?><page/>'), False, 'UNREADABLE_DISALLOW'),
    (robots('User-agent: *\nDisallow: /\n'), False, 'PARSED'),
    (robots('User-agent: *\nDisallow: /private\n'), True, 'PARSED'),
    (httpx.Response(200, headers={'content-type': 'text/plain'},
                    content=b'\xef\xbb\xbfUser-agent: *\nDisallow: /careers\n'), False, 'PARSED'),
    (httpx.Response(200, headers={'content-type': 'text/plain'},
                    content=b'\xef\xbb\xbfUser-agent: *\r\nDisallow: /careers\r\n'), False, 'PARSED'),
])
def test_robots_decisions(robots_response, requested, kind):
    site = Site({('jobs.example.test', '/robots.txt'): robots_response,
                 ('jobs.example.test', '/careers'): html('<title>Careers</title>')})
    check, _ = checker(site)
    report = check.run(plan(page('c', 'https://jobs.example.test/careers')))
    assert (('jobs.example.test', '/careers') in site.paths()) is requested
    assert report['robots']['https://jobs.example.test']['kind'] == kind


def test_robots_network_failure_disallows():
    def fail(request):
        raise httpx.ConnectError('connection reset', request=request)
    site = Site({('reset.example.test', '/robots.txt'): fail})
    check, _ = checker(site)
    report = check.run(plan(page('c', 'https://reset.example.test/careers')))
    assert site.paths() == [('reset.example.test', '/robots.txt')]
    assert report['robots']['https://reset.example.test']['kind'] == 'UNREACHABLE_DISALLOW'
    assert entries(report, 'c')[0]['requested'] is False


def test_product_token_group_is_matched_exactly_not_as_a_substring():
    loose = 'User-agent: r\nAllow: /\n\nUser-agent: *\nDisallow: /\n'
    named = 'User-agent: ASTRA-source-research\nAllow: /careers\n\nUser-agent: *\nDisallow: /\n'
    versioned = 'User-agent: ASTRA-Source-Research/1.0\nDisallow: /\n\nUser-agent: *\nAllow: /\n'
    longer = 'User-agent: astra-source-researcher\nDisallow: /\n\nUser-agent: *\nAllow: /\n'
    assert src.robots_allows(src.rules_for(src.parse_robots(loose)), '/careers')[0] is False
    assert src.robots_allows(src.rules_for(src.parse_robots(named)), '/careers')[0] is True
    assert src.robots_allows(src.rules_for(src.parse_robots(named)), '/other')[0] is True  # no matching rule
    assert src.robots_allows(src.rules_for(src.parse_robots(versioned)), '/careers')[0] is False
    assert src.robots_allows(src.rules_for(src.parse_robots(longer)), '/careers')[0] is True


def test_a_bot_protection_page_at_robots_blocks_the_host():
    site = Site({('guard.example.test', '/robots.txt'): httpx.Response(
        403, headers={'content-type': 'text/html'}, text='<title>Attention Required! | Cloudflare</title> Sorry, you have been blocked'),
        ('guard.example.test', '/'): html('<title>Home</title>')})
    check, _ = checker(site)
    report = check.run(plan(page('h', 'https://guard.example.test/')))
    assert site.paths() == [('guard.example.test', '/robots.txt')]
    assert report['robots']['https://guard.example.test']['kind'] == 'CHALLENGE_DISALLOW'
    assert report['blocked_hosts'] == {'guard.example.test': 'Cloudflare'}


@pytest.mark.parametrize('rule, url, sent_path', [
    ('/وظائف', 'https://h.example.test/%D9%88%D8%B8%D8%A7%D8%A6%D9%81', None),
    ('/%D9%88%D8%B8%D8%A7%D8%A6%D9%81', 'https://h.example.test/وظائف', None),
    ('/%d9%88%d8%b8%d8%a7%d8%a6%d9%81', 'https://h.example.test/%D9%88%D8%B8%D8%A7%D8%A6%D9%81', None),
    ('/private', 'https://h.example.test/public/../private/x', None),
    ('/private', 'https://h.example.test/./private', None),
    ('/job%20list', 'https://h.example.test/job list', None),
    ('/careers', 'https://h.example.test/%63areers', None),
])
def test_robots_match_the_normalised_path_that_would_be_sent(rule, url, sent_path):
    site = Site({('h.example.test', '/robots.txt'): robots(f'User-agent: *\nDisallow: {rule}\n')})
    check, _ = checker(site)
    report = check.run(plan(page('p', url)))
    assert site.paths() == [('h.example.test', '/robots.txt')], site.paths()
    assert entries(report, 'p')[0]['decision'].startswith('not requested: disallowed by')


def test_the_sent_path_is_the_matched_path():
    site = Site({('h.example.test', '/robots.txt'): robots('User-agent: *\nDisallow: /private\n'),
                 ('h.example.test', '/public/x'): html('ok')})
    check, _ = checker(site)
    report = check.run(plan(page('p', 'https://h.example.test/private/../public/x')))
    assert site.paths()[-1] == ('h.example.test', '/public/x')
    assert entries(report, 'p')[0]['sent_url'] == 'https://h.example.test/public/x'


def test_host_spellings_share_one_identity_and_odd_urls_are_refused():
    site = Site({('h.example.test', '/robots.txt'): robots('', 404), ('h.example.test', '/a'): html('a'),
                 ('h.example.test', '/b'): html('b')})
    check, fake = checker(site)
    report = check.run(plan(page('a', 'https://h.example.test/a'), page('b', 'https://H.Example.Test.:443/b')))
    assert fake.sleeps == [2.0, 2.0] and report['contacts_by_host'] == {'h.example.test': 3}
    assert len([p for p in site.paths() if p[1] == '/robots.txt']) == 1
    for url in ('https://user:pw@h.example.test/a', 'https://h.example.test:8443/a', 'ftp://h.example.test/a'):
        with pytest.raises(src.RefusedURL):
            src.canonical(url)


def test_longest_match_and_tie_rules():
    rules = src.rules_for(src.parse_robots('User-agent: *\nDisallow: /jobs\nAllow: /jobs/public$\nDisallow: /*.pdf$\n'))
    assert src.robots_allows(rules, '/jobs/1')[0] is False
    assert src.robots_allows(rules, '/jobs/public')[0] is True
    assert src.robots_allows(rules, '/jobs/public/x')[0] is False
    assert src.robots_allows(rules, '/a/b.pdf')[0] is False
    tie = src.rules_for(src.parse_robots('User-agent: *\nDisallow: /x\nAllow: /x\n'))
    assert src.robots_allows(tie, '/x')[0] is True


def test_robots_redirect_loop_is_conservatively_disallowed_and_every_hop_paced():
    site = Site({('loop.example.test', '/robots.txt'): httpx.Response(301, headers={'location': '/robots.txt/'}),
                 ('loop.example.test', '/robots.txt/'): httpx.Response(301, headers={'location': '/robots.txt/'})})
    check, fake = checker(site)
    report = check.run(plan(page('c', 'https://loop.example.test/careers')))
    robots_requests = [p for p in site.paths() if p[1].startswith('/robots.txt')]
    assert len(robots_requests) == 6 and ('loop.example.test', '/careers') not in site.paths()
    assert report['robots']['https://loop.example.test']['kind'] == 'UNREACHABLE_DISALLOW'
    assert 'RFC 9309 would permit' in report['robots']['https://loop.example.test']['reason']
    assert fake.sleeps == [2.0] * 5


def test_redirects_are_logged_not_followed_until_a_step_asks():
    site = Site({('a.example.test', '/robots.txt'): robots('', 404),
                 ('a.example.test', '/careers'): httpx.Response(301, headers={'location': 'https://b.example.test/jobs'}),
                 ('b.example.test', '/robots.txt'): robots('User-agent: *\nDisallow:\n'),
                 ('b.example.test', '/jobs'): html('<title>Jobs</title>')})
    check, _ = checker(site)
    report = check.run(plan(page('c', 'https://a.example.test/careers')))
    assert entries(report, 'c')[0]['redirect_to'] == 'https://b.example.test/jobs'
    assert not any(host == 'b.example.test' for host, _ in site.paths())

    site.requests.clear()
    check, _ = checker(site)
    report = check.run(plan(page('c', 'https://a.example.test/careers'),
                            {'id': 'r', 'kind': 'redirect', 'from': 'c', 'purpose': 'follow'}))
    assert site.paths()[-2:] == [('b.example.test', '/robots.txt'), ('b.example.test', '/jobs')]
    assert entries(report, 'r')[0]['title'] == 'Jobs'


def test_a_challenge_blocks_the_host_for_the_rest_of_the_run():
    site = Site({('bank.example.test', '/robots.txt'): robots('', 404),
                 ('bank.example.test', '/careers'): httpx.Response(
                     403, headers={'content-type': 'text/html'}, text='<title>Attention Required! | Cloudflare</title>'),
                 ('bank.example.test', '/'): html('<title>Home</title>')})
    check, _ = checker(site)
    report = check.run(plan(page('c', 'https://bank.example.test/careers'), page('h', 'https://bank.example.test/')))
    assert 'not bypassed' in entries(report, 'c')[0]['challenge']
    assert ('bank.example.test', '/') not in site.paths()
    assert entries(report, 'h')[0]['requested'] is False
    assert report['blocked_hosts'] == {'bank.example.test': 'Cloudflare'}


def test_no_cookie_is_kept_or_sent():
    site = Site({('c.example.test', '/robots.txt'): httpx.Response(404, headers={'set-cookie': 'a=1; Path=/'}),
                 ('c.example.test', '/one'): html('one', **{'set-cookie': 'b=2; Path=/'}),
                 ('c.example.test', '/two'): html('two')})
    check, _ = checker(site)
    report = check.run(plan(page('one', 'https://c.example.test/one'), page('two', 'https://c.example.test/two')))
    assert all('cookie' not in r.headers for r in site.requests)
    assert all(r.headers['user-agent'] == UA_HEADER for r in site.requests)
    assert entries(report, 'one')[0]['set_cookie_seen'] is True


def test_login_apply_and_non_https_urls_are_refused_without_a_request():
    for url in ('https://x.example.test/apply/123', 'https://x.example.test/en/login', 'http://x.example.test/careers',
                'https://x.example.test/jobs/apply-now', 'https://x.example.test/Login.aspx',
                'https://x.example.test/user/signin?next=/', 'https://x.example.test/jobs?action=apply',
                'https://x.example.test/%61pply/1', 'https://x.example.test/candidate/profile',
                'https://x.example.test/sso', 'https://x.example.test/auth/start'):
        with pytest.raises(src.PlanError):
            src.validate_plan(plan(page('p', url)))
    src.validate_plan(plan(page('p', 'https://x.example.test/about/authority-careers')))
    site = Site({('x.example.test', '/robots.txt'): robots('', 404),
                 ('x.example.test', '/careers'): html('<a href="/account/sign-in">Careers login</a>'
                                                      '<a href="/jobs/list">Open jobs</a>'),
                 ('x.example.test', '/jobs/list'): html('<title>List</title>')})
    check, _ = checker(site)
    report = check.run(plan(page('c', 'https://x.example.test/careers'),
                            {'id': 'l', 'kind': 'links', 'from': 'c', 'match': 'career|job', 'max': 3}))
    assert ('x.example.test', '/account/sign-in') not in site.paths()
    assert ('x.example.test', '/jobs/list') in site.paths()
    refused = [e for e in report['log'] if e.get('decision', '').startswith('refused')]
    assert refused and refused[0]['url'].endswith('/account/sign-in')


def test_links_are_classified_and_permitted_adapter_links_flagged():
    body = ('<a href="https://jobs.lever.co/fictional">Open roles</a>'
            '<a href="https://tenant.fa.ocs.oraclecloud.com/hcmUI/CandidateExperience/en/sites/CX_1">Vacancies</a>'
            '<a href="/about">About</a>')
    site = Site({('e.example.test', '/robots.txt'): robots('', 404), ('e.example.test', '/careers'): html(body)})
    check, _ = checker(site)
    entry = entries(check.run(plan(page('c', 'https://e.example.test/careers'))), 'c')[0]
    classes = {link['href']: link['class'] for link in entry['job_links']}
    assert classes['https://jobs.lever.co/fictional'] == 'permitted_adapter:lever'
    assert classes['https://tenant.fa.ocs.oraclecloud.com/hcmUI/CandidateExperience/en/sites/CX_1'] == 'other_ats:oracle'
    assert 'https://e.example.test/about' not in classes
    assert [l['href'] for l in entry['permitted_adapter_links']] == ['https://jobs.lever.co/fictional']


def test_robots_redirects_that_leave_https_or_reach_login_are_refused():
    site = Site({('a.example.test', '/robots.txt'): httpx.Response(301, headers={'location': 'http://a.example.test/robots.txt'}),
                 ('b.example.test', '/robots.txt'): httpx.Response(302, headers={'location': '/login?robots'})})
    check, _ = checker(site)
    report = check.run(plan(page('a', 'https://a.example.test/careers'), page('b', 'https://b.example.test/careers')))
    assert site.paths() == [('a.example.test', '/robots.txt'), ('b.example.test', '/robots.txt')]
    assert report['robots']['https://a.example.test']['kind'] == 'UNREACHABLE_DISALLOW'
    assert 'robots redirect refused' in report['robots']['https://b.example.test']['reason']


def test_followed_links_obey_the_https_rule_and_a_failed_request_blocks_the_host():
    def boom(request):
        raise httpx.ConnectError('reset', request=request)
    site = Site({('e.example.test', '/robots.txt'): robots('', 404),
                 ('e.example.test', '/careers'): html('<a href="http://jobs.example.test/">Jobs</a>'
                                                     '<a href="https://f.example.test/jobs">More jobs</a>'),
                 ('f.example.test', '/robots.txt'): robots('', 404), ('f.example.test', '/jobs'): boom,
                 ('f.example.test', '/other'): html('x')})
    check, _ = checker(site)
    report = check.run(plan(page('c', 'https://e.example.test/careers'),
                            {'id': 'l', 'kind': 'links', 'from': 'c', 'match': 'job', 'max': 2},
                            page('o', 'https://f.example.test/other')))
    assert not any(host == 'jobs.example.test' for host, _ in site.paths())
    assert entries(report, 'l#1')[0]['decision'] == 'refused: only https is requested'
    assert 'ConnectError' in entries(report, 'l#2')[0]['error']
    assert ('f.example.test', '/other') not in site.paths() and entries(report, 'o')[0]['requested'] is False


@pytest.mark.parametrize('headers, body, name', [
    ({'cf-mitigated': 'challenge'}, 'plain', 'Cloudflare (cf-mitigated header)'),
    ({}, '<title>Just a moment...</title>', 'Cloudflare'),
    ({}, '<title>Request Rejected</title>', 'WAF rejection'),
    ({}, 'Incapsula incident ID', 'Imperva/Incapsula'),
    ({}, 'TSPD_101 challenge', 'F5 challenge'),
    ({}, '<title>Access Denied</title> Reference #18.abc', 'Akamai denial'),
])
def test_every_bot_protection_signature_is_detected(headers, body, name):
    assert src.challenge_in(httpx.Headers(headers), body) == name
    site = Site({('w.example.test', '/robots.txt'): robots('', 404),
                 ('w.example.test', '/careers'): httpx.Response(200, headers={'content-type': 'text/html', **headers}, text=body)})
    check, _ = checker(site)
    report = check.run(plan(page('c', 'https://w.example.test/careers')))
    assert report['blocked_hosts'] == {'w.example.test': name}


def test_only_get_requests_and_verified_tls_without_redirect_following(monkeypatch):
    built = {}
    original = src.httpx.Client

    def capture(*args, **kwargs):
        built.update(kwargs)
        return original(*args, **kwargs)
    monkeypatch.setattr(src.httpx, 'Client', capture)
    site = Site({('g.example.test', '/robots.txt'): robots('', 404), ('g.example.test', '/'): html('x')})
    check, _ = checker(site)
    check.run(plan(page('h', 'https://g.example.test/')))
    assert built['verify'] is True and built['follow_redirects'] is False
    assert {r.method for r in site.requests} == {'GET'}
    assert all(r.headers['user-agent'].startswith('ASTRA-source-research/1.0 (read-only') for r in site.requests)
    with pytest.raises(src.PlanError):
        src.RouteChecker._request_guard(httpx.Request('POST', 'https://g.example.test/'))


def test_a_cookie_about_to_be_sent_stops_the_run():
    site = Site({('k.example.test', '/robots.txt'): robots('', 404)})
    check, _ = checker(site)
    check.client.cookies.set('planted', '1', domain='k.example.test')
    report = check.run(plan(page('h', 'https://k.example.test/')))
    assert report['aborted'] == 'a cookie was about to be sent' and site.requests == []


def test_pacing_rechecks_after_a_short_sleep_and_reports_a_violation():
    fake = FakeTime()
    short = []

    def lazy_sleep(seconds):  # the OS may wake early
        short.append(round(seconds, 3))
        fake.now += seconds / 2
    site = Site({('s.example.test', '/robots.txt'): robots('', 404), ('s.example.test', '/'): html('x')})
    check = src.RouteChecker(transport=httpx.MockTransport(site), clock=fake.clock, sleep=lazy_sleep, wall=fake.wall)
    report = check.run(plan(page('h', 'https://s.example.test/')))
    assert len(short) > 1 and report['pacing']['smallest_same_host_interval_s'] >= 2.0
    check.intervals.append({'host': 's.example.test', 'since_prev_end_s': 1.5})
    assert check.report()['pacing']['all_intervals_at_least_minimum'] is False


def test_tls_certificate_read_skipped_at_the_host_cap(monkeypatch):
    monkeypatch.setattr(src, 'MAX_CONTACTS_PER_HOST', 1)
    check, _ = checker(Site({}), tls_probe=lambda host: {'verified': False, 'error': 'expired'},
                       cert_reader=lambda host: {'read': True})
    entry = entries(check.run(plan({'id': 't', 'kind': 'tls', 'host': 'erp.example.test'})), 't')[0]
    assert entry['error'] == 'expired' and entry['presented_certificate']['read'] is False


def test_tls_diagnostic_is_paced_and_sends_no_http_request():
    site = Site({})
    probes = []
    check, fake = checker(site, tls_probe=lambda host: probes.append(host) or {'verified': False, 'error': 'expired'},
                          cert_reader=lambda host: probes.append(host) or {'read': True, 'not_after': 'Jan  1 00:00:00 2029 GMT'})
    report = check.run(plan({'id': 't', 'kind': 'tls', 'host': 'erp.example.test'}))
    entry = entries(report, 't')[0]
    assert probes == ['erp.example.test', 'erp.example.test'] and site.requests == []
    assert fake.sleeps == [2.0] and entry['presented_certificate']['since_prev_contact_end_s'] == 2.0


def test_dns_step_contacts_no_host():
    site = Site({})
    check, fake = checker(site)
    report = check.run(plan({'id': 'd', 'kind': 'dns', 'host': 'careers.example.test'}))
    assert entries(report, 'd')[0]['addresses'] == ['192.0.2.1']
    assert site.requests == [] and fake.sleeps == [] and report['contacts_by_host'] == {}


def test_host_cap_skips_steps_and_run_cap_stops_the_run(monkeypatch):
    monkeypatch.setattr(src, 'MAX_CONTACTS_PER_HOST', 3)
    site = Site({('cap.example.test', '/robots.txt'): robots('', 404), ('other.example.test', '/robots.txt'): robots('', 404),
                 ('other.example.test', '/z'): html('z')})
    for n in range(5):
        site.routes[('cap.example.test', f'/p{n}')] = html(str(n))
    check, _ = checker(site)
    report = check.run(plan(*[page(f'p{n}', f'https://cap.example.test/p{n}') for n in range(5)],
                            page('z', 'https://other.example.test/z')))
    assert report['aborted'] is None
    assert [p for p in site.paths() if p[0] == 'cap.example.test'] == [
        ('cap.example.test', '/robots.txt'), ('cap.example.test', '/p0'), ('cap.example.test', '/p1')]
    assert entries(report, 'p2')[0]['decision'] == 'not requested: per-host contact cap reached for cap.example.test'
    assert entries(report, 'z')[0]['requested'] is True

    monkeypatch.setattr(src, 'MAX_CONTACTS_PER_RUN', 2)
    site.requests.clear()
    check, _ = checker(site)
    report = check.run(plan(page('p0', 'https://cap.example.test/p0'), page('z', 'https://other.example.test/z')))
    assert report['aborted'] == 'per-run contact cap reached' and len(site.requests) == 2
    assert report['log']  # kept


def test_plan_validation():
    with pytest.raises(src.PlanError):
        src.validate_plan({'employers': []})
    with pytest.raises(src.PlanError):
        src.validate_plan(plan({'id': 'l', 'kind': 'links', 'from': 'later', 'match': 'x'}, page('later', 'https://a.test/')))
    with pytest.raises(src.PlanError):
        src.validate_plan(plan(page('p', 'https://a.test/'), page('p', 'https://a.test/b')))
    with pytest.raises(src.PlanError):
        src.validate_plan(plan({'id': 'x', 'kind': 'post', 'url': 'https://a.test/'}))


def test_validate_only_cli_makes_no_client(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(src.httpx, 'Client', lambda *a, **k: (_ for _ in ()).throw(AssertionError('client built')))
    plan_file = tmp_path / 'plan.json'
    plan_file.write_text(json.dumps(plan(page('p', 'https://a.test/careers'))), encoding='utf-8')
    assert src.main([str(plan_file), '--validate-only']) == 0
    assert json.loads(capsys.readouterr().out) == {'plan_ok': True, 'steps': 1}
    with pytest.raises(SystemExit):
        src.main([str(plan_file)])


def test_tool_identity_ignores_line_endings(tmp_path):
    lf, crlf = tmp_path / 'lf.py', tmp_path / 'crlf.py'
    lf.write_bytes(b'print(1)\nprint(2)\n')
    crlf.write_bytes(b'print(1)\r\nprint(2)\r\n')
    assert src.tool_identity(lf)['git_blob_lf'] == src.tool_identity(crlf)['git_blob_lf']
    assert src.tool_identity(lf)['git_blob_lf'] == 'f2db9da9bd6356a23a45af5297038f7d25c0087e'  # git hash-object


def test_the_backend_never_imports_the_checker():
    import pathlib
    backend = pathlib.Path(src.__file__).resolve().parents[1] / 'backend'
    assert not any('source_route_check' in p.read_text(encoding='utf-8', errors='ignore') for p in backend.rglob('*.py'))


# --- round-two review regressions ------------------------------------------------
@pytest.mark.parametrize('body, name', [
    ('<script src="/cdn-cgi/challenge-platform/scripts/jsd/main.js"></script>', 'Cloudflare'),
    ('<script src="/TSbd/x"></script>', 'F5 challenge'),
    ('<form><div class="g-recaptcha"></div></form>', 'CAPTCHA'),
])
def test_bot_scripts_block_only_on_a_blocking_status(body, name):
    assert src.challenge_in(httpx.Headers({}), body, 200) is None
    assert src.challenge_in(httpx.Headers({}), body, 403) == name
    site = Site({('v.example.test', '/robots.txt'): robots('', 404),
                 ('v.example.test', '/careers'): html(body + '<a href="/jobs">Jobs</a>')})
    check, _ = checker(site)
    entry = entries(check.run(plan(page('c', 'https://v.example.test/careers'))), 'c')[0]
    assert check.blocked_hosts == {} and entry['bot_protection_scripts_seen'] == [name]
    assert entry['job_links'][0]['href'] == 'https://v.example.test/jobs'


def test_the_interval_is_measured_from_the_end_of_the_previous_contact():
    fake = FakeTime()
    arrivals = []

    def slow_server(request):  # each exchange (connect, TLS, response) takes 0.7 s
        arrivals.append(fake.now)
        fake.now += 0.7
        return robots('', 404) if request.url.path == '/robots.txt' else html('x')
    check = src.RouteChecker(transport=httpx.MockTransport(slow_server), clock=fake.clock, sleep=fake.sleep, wall=fake.wall)
    report = check.run(plan(page('a', 'https://t.example.test/a'), page('b', 'https://t.example.test/b')))
    gaps = [later - earlier for earlier, later in zip(arrivals, arrivals[1:])]
    assert all(gap >= 2.0 + 0.7 - 1e-9 for gap in gaps)
    assert fake.sleeps == [2.0, 2.0]
    a = entries(report, 'a')[0]
    assert a['since_prev_contact_end_s'] == 2.0 and a['started_at_utc'] < a['ended_at_utc']


@pytest.mark.parametrize('url', ['https://h.example.test/public/%2E%2E/private/x', 'https://h.example.test/public/.%2e/private/x',
                                 'https://h.example.test/%2e/private', 'https://h.example.test/private%2Fx/../private'])
def test_encoded_dot_segments_are_resolved_before_the_robots_check(url):
    site = Site({('h.example.test', '/robots.txt'): robots('User-agent: *\nDisallow: /private\n')})
    check, _ = checker(site)
    report = check.run(plan(page('p', url)))
    assert site.paths() == [('h.example.test', '/robots.txt')]
    assert entries(report, 'p')[0]['requested'] is False


def test_encoded_dot_segments_in_links_and_locations_cannot_reach_a_disallowed_path():
    site = Site({('h.example.test', '/robots.txt'): robots('User-agent: *\nDisallow: /private\n'),
                 ('h.example.test', '/public'): html('<a href="/public/%2e%2e/private/jobs">Jobs</a>'),
                 ('h.example.test', '/go'): httpx.Response(302, headers={'location': '/public/%2E%2E/private/careers'})})
    check, _ = checker(site)
    check.run(plan(page('p', 'https://h.example.test/public'),
                   {'id': 'l', 'kind': 'links', 'from': 'p', 'match': 'job'},
                   page('g', 'https://h.example.test/go'), {'id': 'r', 'kind': 'redirect', 'from': 'g'}))
    assert not any(path.startswith('/private') for _, path in site.paths())


def test_malformed_locations_and_hrefs_do_not_stop_the_run():
    site = Site({('m.example.test', '/robots.txt'): httpx.Response(301, headers={'location': 'https://[broken/robots.txt'}),
                 ('n.example.test', '/robots.txt'): robots('', 404),
                 ('n.example.test', '/careers'): html('<a href="http://[::1">Jobs</a><a href="/jobs">More jobs</a>'),
                 ('n.example.test', '/move'): httpx.Response(302, headers={'location': 'https://[bad'})})
    check, _ = checker(site)
    report = check.run(plan(page('m', 'https://m.example.test/careers'), page('c', 'https://n.example.test/careers'),
                            page('v', 'https://n.example.test/move')))
    assert report['aborted'] is None
    assert report['robots']['https://m.example.test']['kind'] == 'UNREACHABLE_DISALLOW'
    careers = entries(report, 'c')[0]
    assert careers['unusable_hrefs_skipped'] == 1 and careers['job_links'][0]['href'] == 'https://n.example.test/jobs'
    assert entries(report, 'v')[0]['redirect_error'] == 'unusable Location header'


def test_an_unexpected_error_stops_the_run_with_the_log_kept():
    def resolver(host):
        raise ValueError('resolver bug')
    check = src.RouteChecker(transport=httpx.MockTransport(Site({})), resolver=resolver)
    report = check.run(plan({'id': 'd', 'kind': 'dns', 'host': 'x.example.test'}))
    assert report['aborted'] == 'unexpected error: ValueError: resolver bug'


@pytest.mark.parametrize('url', ['https://login.example.test/', 'https://sso.example.test/careers', 'https://x.example.test/log_in',
                                 'https://x.example.test/sign_in', 'https://x.example.test/Sign-On', 'https://x.example.test/authenticate',
                                 'https://x.example.test/jobs/application/1', 'https://x.example.test/authorize'])
def test_login_hosts_and_underscore_spellings_are_refused(url):
    with pytest.raises(src.RefusedURL):
        src.canonical(url)


def test_the_v7_plan_is_valid_and_refuses_nothing():
    import pathlib
    plan_path = pathlib.Path(src.__file__).resolve().parents[1] / 'docs' / 'evaluation' / 'discovery_46_2b_source_map_v7_plan.json'
    live_plan = json.loads(plan_path.read_text(encoding='utf-8'))
    src.validate_plan(live_plan)
    for employer in live_plan['employers']:
        for step in employer['steps']:
            if step['kind'] == 'page':
                assert src.canonical(step['url'])['url'] == step['url']


def test_tls_step_respects_challenge_blocks_and_canonical_host_names():
    site = Site({('bank.example.test', '/robots.txt'): httpx.Response(
        403, headers={'content-type': 'text/html'}, text='<title>Attention Required! | Cloudflare</title>')})
    probes = []
    check, _ = checker(site, tls_probe=lambda host: probes.append(host) or {'verified': True})
    report = check.run(plan(page('p', 'https://bank.example.test/'), {'id': 't', 'kind': 'tls', 'host': 'BANK.example.test.'},
                            {'id': 'u', 'kind': 'tls', 'host': 'Other.Example.Test.'}))
    assert entries(report, 't')[0]['requested'] is False and probes == ['other.example.test']


def test_a_run_cap_during_the_certificate_read_keeps_the_handshake_entry(monkeypatch):
    monkeypatch.setattr(src, 'MAX_CONTACTS_PER_RUN', 1)
    check, _ = checker(Site({}), tls_probe=lambda host: {'verified': False, 'error': 'expired'},
                       cert_reader=lambda host: {'read': True})
    report = check.run(plan({'id': 't', 'kind': 'tls', 'host': 'erp.example.test'}))
    assert report['aborted'] == 'per-run contact cap reached'
    assert entries(report, 't')[0]['error'] == 'expired' and report['contacts_by_host'] == {'erp.example.test': 1}


def test_a_guard_stopped_request_is_not_counted_as_a_contact():
    site = Site({('k.example.test', '/robots.txt'): robots('', 404)})
    check, _ = checker(site)
    check.client.cookies.set('planted', '1', domain='k.example.test')
    report = check.run(plan(page('h', 'https://k.example.test/')))
    assert report['contacts_by_host'] == {'k.example.test': 0}
    assert any(e.get('decision') == 'not sent: a cookie was about to be sent' for e in report['log'])


@pytest.mark.parametrize('body', [b' ' * 3000 + b'<html><body>x</body></html>', '\u00a0\f<div>Home</div>'.encode(),
                                  b'# comment\n<p>maintenance</p>'])
def test_html_as_robots_is_recognised_behind_whitespace_or_comments(body):
    site = Site({('r.example.test', '/robots.txt'): httpx.Response(200, headers={'content-type': 'text/plain'}, content=body)})
    check, _ = checker(site)
    report = check.run(plan(page('p', 'https://r.example.test/careers')))
    assert report['robots']['https://r.example.test']['kind'] == 'UNREADABLE_DISALLOW'


def test_plan_regexes_are_validated():
    with pytest.raises(src.PlanError):
        src.validate_plan(plan(page('p', 'https://a.test/'), {'id': 'l', 'kind': 'links', 'from': 'p', 'match': '('}))


def test_a_path_the_client_would_rewrite_is_refused(monkeypatch):
    real = src.httpx.URL

    built = []

    class Rewriting(real):  # the second URL built (the one sent) would carry a different path
        def __init__(self, *args, **kwargs):
            super().__init__(*args, **kwargs)
            built.append(self)

        @property
        def raw_path(self):
            path = real.raw_path.fget(self)
            return path.replace(b'/private-free', b'/private') if len(built) > 1 and self is built[1] else path
    monkeypatch.setattr(src.httpx, 'URL', Rewriting)
    with pytest.raises(src.RefusedURL, match='differs from the checked path'):
        src.canonical('https://h.example.test/private-free/x')
