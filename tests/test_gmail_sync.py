"""Hermetic #45 integration and adversarial parser regressions."""
import copy
import json
import time
from datetime import datetime, timezone

import httpx
import pytest
from sqlalchemy import delete, select

from backend import gmail_accounts as accounts, gmail_oauth as oauth
from backend import gmail_content as content, gmail_confirmations as parsers
from backend import gmail_messages as messages, gmail_sync as sync
from backend.models import Session
from tests.gmail_fixtures import gmail_env, keyring_backend, install_google_double
from tests.gmail_confirmation_fixtures import PLATFORMS, message, encoded

pytestmark = pytest.mark.usefixtures('gmail_env', 'no_unexpected_network')


@pytest.fixture(autouse=True)
def clean_confirmations():
    sync.initialize_sync_schema()
    with Session.begin() as db:
        db.execute(delete(sync.GmailConfirmation))


def connect(monkeypatch):
    install_google_double(monkeypatch)
    accounts._bind_credential('PRIMARY', {'authorized_email': 'tester@example.com',
        'identity_key': 'tester@example.com', 'identity_kind': 'GMAIL_PROFILE_EMAIL'},
        [oauth.GMAIL_READONLY_SCOPE], oauth.Secret('fictional-refresh-value'))


def parse(value):
    return sync._process_message(value, slot='PRIMARY', account_id='fictional-account')


@pytest.mark.parametrize('platform', PLATFORMS)
def test_positive_extracts_all_fields(platform):
    result, row = parse(message(platform))
    assert result.confidence == 'HIGH'
    assert result.parser_id == platform + '-confirmation-v1'
    assert row['detected_company'] == 'Example Robotics'
    assert row['detected_role'] == 'Security Analyst'
    assert row['detected_state'] == 'APPLICATION_CONFIRMED'
    assert row['gmail_message_id'] == 'a1'
    assert row['gmail_account_id'] == 'fictional-account'
    assert row['sender'].startswith('noreply@') and row['received_at']
    assert row['subject'] == 'Thank you for applying to Example Robotics'
    assert row['application_url'].startswith('https://')
    assert parsers.REQUIRED_FOR_HIGH <= set(row['evidence_signals'])


@pytest.mark.parametrize('platform', PLATFORMS)
@pytest.mark.parametrize('attack', ['sender', 'subject', 'body', 'missing_auth', 'failed_auth',
    'foreign_auth', 'misaligned', 'duplicate_auth', 'contradictory', 'arc_only',
    'wrong_company', 'duplicate_from', 'bad_date', 'no_url', 'unsafe_url'])
def test_independent_signals_are_required(platform, attack):
    value = message(platform)
    headers = value['payload']['headers']
    if attack == 'sender': headers[0]['value'] = 'noreply@attacker.example'
    if attack == 'subject': headers[1]['value'] = 'Monthly newsletter'
    if attack == 'body': value['payload']['parts'][0]['body']['data'] = encoded('No application evidence.')
    if attack == 'missing_auth': headers.pop()
    if attack == 'failed_auth': headers[2]['value'] = headers[2]['value'].replace('dmarc=pass','dmarc=fail')
    if attack == 'foreign_auth': headers[2]['value'] = headers[2]['value'].replace('mx.google.com','attacker.example')
    if attack == 'misaligned': headers[2]['value'] = headers[2]['value'].split('header.from=')[0]+'header.from=attacker.example'
    if attack == 'duplicate_auth': headers.append(copy.deepcopy(headers[2]))
    if attack == 'contradictory': headers[2]['value'] += '; dmarc=fail'
    if attack == 'arc_only': headers[2]['name'] = 'ARC-Authentication-Results'
    if attack == 'wrong_company': headers[1]['value'] = 'Thank you for applying to Example Robotics Fraud'
    if attack == 'duplicate_from': headers.append({'name':'From','value':'noreply@evil.example'})
    if attack == 'bad_date': value['internalDate'] = 'invalid'
    if attack == 'no_url':
        value['payload']['parts'][0]['body']['data'] = encoded('Thank you for applying to the Security Analyst position at Example Robotics.')
    if attack == 'unsafe_url':
        value['payload']['parts'][1]['body']['data'] = encoded('<a href="javascript:alert(1)">Apply</a>')
    assert parse(value)[0].confidence != 'HIGH'


@pytest.mark.parametrize('platform', PLATFORMS)
@pytest.mark.parametrize('kept', ['sender', 'subject', 'body'])
def test_one_signal_never_high(platform, kept):
    value = message(platform)
    headers = value['payload']['headers']
    headers.pop()
    if kept != 'sender': headers[0]['value'] = 'fictional@unknown.example'
    if kept != 'subject': headers[1]['value'] = 'Hello'
    if kept != 'body': value['payload']['parts'] = []
    assert parse(value)[0].confidence != 'HIGH'


def test_generic_and_nonconfirmation_are_explicit():
    value = message()
    value['payload']['headers'][0]['value'] = 'hr@example.com'
    result, _ = parse(value)
    assert result.is_confirmation and result.confidence == 'LOW'
    assert result.parser_id == parsers.GENERIC_PARSER_ID
    value['payload']['headers'][1]['value'] = 'Weekly newsletter'
    value['payload']['parts'] = []
    result, _ = parse(value)
    assert not result.is_confirmation and result.parser_id == parsers.GENERIC_PARSER_ID


@pytest.mark.parametrize('subject', ['Interview invitation', 'Assessment invitation', 'Offer extended', 'Application rejection'])
def test_later_stage_quoted_confirmations_are_excluded(subject):
    value = message()
    value['payload']['headers'][1]['value'] = subject
    assert not parse(value)[0].is_confirmation


@pytest.mark.parametrize('bad', ['@@@', '%%%%', 'ééé', 'A', 'A'*400000], ids=['symbols','percent','unicode','short','oversized'])
def test_malformed_and_oversized_encoding(bad):
    value = content.extract_content({'mimeType':'text/plain','body':{'data':bad}})
    assert not value.text and value.malformed_parts == 1


def test_mime_depth_parts_and_byte_budget():
    part = {'mimeType':'text/plain','body':{'data':encoded('x'*200000)}}
    combined = content.extract_content({'mimeType':'multipart/mixed','parts':[part]*1000})
    assert len(combined.text) <= content.MAX_DECODED_BODY_BYTES
    assert combined.parts_seen <= content.MAX_MIME_PARTS and combined.truncated
    nested = part
    for _ in range(100): nested = {'mimeType':'multipart/mixed','parts':[nested]}
    assert content.extract_content(nested).depth_exceeded
    attachment = {'mimeType':'multipart/mixed','filename':'secret.eml','parts':[part]}
    assert not content.extract_content(attachment).text


@pytest.mark.parametrize('url', ['javascript:alert(1)', 'data:text/html,x', 'http://example.com/jobs/1',
    'https://greenhouse.io@evil.example/jobs/1', 'https://127.0.0.1/a', 'https://[::1]/a',
    'https://localhost/a', 'https://2130706433/a', 'https://example.com:bad/a',
    'https://example.com:8443/a', 'https://xn--evil.com/a', 'https://exam\u202eple.com/a',
    'https://example.com/\\evil', 'https://example.com/%0aevil'])
def test_dangerous_urls_rejected(url):
    assert content.safe_url(url) == ''


def test_html_is_text_and_no_active_links_survive():
    markup = '<script>evil()</script><img src="https://tracker.example/pixel"><p>Safe</p><a href="javascript:x">x</a>'
    extracted = content.extract_content({'mimeType':'text/html','body':{'data':encoded(markup)}})
    assert 'evil' not in extracted.text and '<' not in extracted.text
    assert not extracted.urls and extracted.unsafe_urls_dropped == 1
    assert content.safe_url('https://example.com/jobs/123?email=tester%40example.com#token') == 'https://example.com/jobs/123'


def install_messages(monkeypatch, data):
    seen = []
    def listing(access, *, query, page_token=None, page_size=25, **kw):
        seen.append(('list', query, page_token))
        start = int(page_token or 0)
        ids = list(data)[start:start+page_size]
        end = start+len(ids)
        return ids, str(end) if end < len(data) else None
    def fetch(access, identifier, **kw):
        seen.append(('get', identifier))
        return copy.deepcopy(data[identifier])
    monkeypatch.setattr(messages,'list_message_ids',listing)
    monkeypatch.setattr(messages,'fetch_message',fetch)
    return seen


def test_incremental_idempotency_and_empty_window(monkeypatch):
    connect(monkeypatch)
    seen = install_messages(monkeypatch, {'a1':message()})
    first = sync.sync_account()
    second = sync.sync_account()
    assert first['confirmations_recorded'] == 1 and first['complete']
    assert second['skipped_already_recorded'] == 1 and second['messages_fetched'] == 0
    assert second['cursor_state'] == 'INCREMENTAL'
    assert seen[0][1] != seen[-1][1]
    assert sync.list_confirmations()['count'] == 1
    install_messages(monkeypatch, {})
    assert sync.sync_account()['complete']


def test_pagination_resumes_frozen_window_without_skipping(monkeypatch):
    connect(monkeypatch)
    data = {f'a{i}':message(identifier=f'a{i}', timestamp=time.time()-i*1000-60) for i in range(140)}
    seen = install_messages(monkeypatch,data)
    first = sync.sync_account()
    assert first['messages_fetched'] == 100 and first['messages_listed'] == 100
    assert not first['complete'] and not first['cursor_advanced']
    checkpoint = accounts.read_sync_state('PRIMARY')
    assert checkpoint['page_token'] == '100' and 'completed_through' not in checkpoint
    second = sync.sync_account()
    assert second['messages_fetched'] == 40 and second['complete']
    assert len({call[1] for call in seen if call[0]=='list'}) == 1
    assert sync.list_confirmations(limit=200)['count'] == 140


@pytest.mark.parametrize('state', [[], {'version':'old'}, {'version':sync.SYNC_STATE_VERSION,'completed_through':True},
    {'version':sync.SYNC_STATE_VERSION,'completed_through':10**100},
    {'version':sync.SYNC_STATE_VERSION,'completed_through':1},
    {'version':sync.SYNC_STATE_VERSION,'after':1,'before':2,'page_token':'abc'}])
def test_invalid_state_is_bounded(state):
    after,before,token,kind = sync.plan_window(state)
    assert before-after == 30*86400 and token is None
    assert kind in (sync.CURSOR_INITIAL,sync.CURSOR_RESET_CONSERVATIVE)


def test_failures_do_not_advance_cursor_and_clear_access(monkeypatch):
    connect(monkeypatch)
    install_messages(monkeypatch, {'a1':message()})
    tokens = []
    def fail(access, identifier, **kw):
        tokens.append(access)
        raise messages.GmailReadError('GMAIL_READ_UNAUTHORIZED','private error')
    monkeypatch.setattr(messages,'fetch_message',fail)
    with pytest.raises(messages.GmailReadError) as caught: sync.sync_account()
    assert 'private error' not in str(caught.value)
    checkpoint = accounts.read_sync_state('PRIMARY')
    assert checkpoint['page_token'] is None and 'completed_through' not in checkpoint
    with pytest.raises(ValueError, match='cleared'):
        tokens[0].reveal()


def test_disconnect_and_reconnect_cannot_write_old_account(monkeypatch):
    connect(monkeypatch)
    seen = install_messages(monkeypatch, {'a1':message()})
    original = messages.fetch_message
    def changed(access, identifier, **kw):
        result = original(access,identifier,**kw)
        connect(monkeypatch)
        return result
    monkeypatch.setattr(messages,'fetch_message',changed)
    with pytest.raises(oauth.OAuthError): sync.sync_account()
    assert sync.list_confirmations()['count'] == 0
    assert accounts.read_sync_state('PRIMARY') == {}


def test_secondary_disabled_and_no_connection_refused(monkeypatch):
    with pytest.raises(oauth.OAuthError): sync.sync_account('SECONDARY')
    with pytest.raises(oauth.OAuthError) as caught: sync.sync_account()
    assert caught.value.code == 'ACCOUNT_NOT_CONNECTED'


def mock_transport(monkeypatch, handler):
    monkeypatch.setattr(oauth, '_client', lambda timeout: httpx.Client(
        transport=httpx.MockTransport(handler), trust_env=False, follow_redirects=False))


def test_actual_wire_methods_queries_and_size(monkeypatch):
    requests = []
    def handler(request):
        requests.append(request)
        data = {'messages':[{'id':'a1'}]} if request.url.path.endswith('/messages') else message()
        return httpx.Response(200, content=iter([json.dumps(data).encode()]), headers={'content-type':'application/json'})
    mock_transport(monkeypatch,handler)
    query = messages.build_query(int(time.time())-86400,int(time.time()))
    token = oauth.Secret('fictional-token')
    assert messages.list_message_ids(token,query=query)[0] == ['a1']
    messages.fetch_message(token,'a1')
    assert all(r.method=='GET' and r.url.host=='gmail.googleapis.com' for r in requests)
    assert requests[0].url.params['q'] == query
    assert requests[1].url.params['format'] == 'full'
    assert 'includeSpamTrash' not in requests[0].url.params


@pytest.mark.parametrize('query', ['', 'in:anywhere', 'after:1', 'from:greenhouse.io', '*'])
def test_client_cannot_enumerate_mailbox(query):
    with pytest.raises(messages.GmailReadError): messages.list_message_ids(oauth.Secret('x'),query=query)


@pytest.mark.parametrize('payload', [{'messages':'wrong'}, {'messages':[{}]}, {'nextPageToken':'bad token'},
    {'messages':[{'id':'a'}]*26}])
def test_invalid_list_never_silently_completes(monkeypatch,payload):
    mock_transport(monkeypatch,lambda req:httpx.Response(200,content=iter([json.dumps(payload).encode()]),headers={'content-type':'application/json'}))
    with pytest.raises(messages.GmailReadError):
        messages.list_message_ids(oauth.Secret('x'),query=messages.build_query(int(time.time())-100,int(time.time())))


@pytest.mark.parametrize('status,expected', [(429,3),(503,3),(401,1),(403,1),(404,1),(302,1)])
def test_bounded_retries(monkeypatch,status,expected):
    calls = []
    def handler(req):
        calls.append(req)
        return httpx.Response(status,content=iter([b'{}']),headers={'content-type':'application/json','location':'https://evil.example'})
    mock_transport(monkeypatch,handler)
    monkeypatch.setattr(messages.time,'sleep',lambda _:None)
    with pytest.raises(messages.GmailReadError): messages.fetch_message(oauth.Secret('x'),'a1')
    assert len(calls) == expected


def test_invalid_page_checkpoint_resets_without_widening(monkeypatch):
    connect(monkeypatch)
    install_messages(monkeypatch,{f'a{i}':message(identifier=f'a{i}') for i in range(101)})
    sync.sync_account()
    def expired(*args,**kwargs):
        raise messages.GmailReadError('GMAIL_RESPONSE_INVALID','expired private payload')
    monkeypatch.setattr(messages,'list_message_ids',expired)
    with pytest.raises(messages.GmailReadError): sync.sync_account()
    assert sync.plan_window(accounts.read_sync_state('PRIMARY'))[3]==sync.CURSOR_RESET_CONSERVATIVE


def test_page_count_bound_and_repeated_token(monkeypatch):
    connect(monkeypatch)
    calls=[]
    def empty_pages(*args,**kwargs):
        calls.append(1)
        return [],str(len(calls))
    monkeypatch.setattr(messages,'list_message_ids',empty_pages)
    result=sync.sync_account()
    assert len(calls)==messages.MAX_PAGES and not result['complete']
    monkeypatch.setattr(messages,'list_message_ids',lambda *a,**k:([],k['page_token']))
    with pytest.raises(messages.GmailReadError): sync.sync_account()


def test_deadline_does_not_commit_half_page(monkeypatch):
    from types import SimpleNamespace
    connect(monkeypatch)
    install_messages(monkeypatch,{'a1':message(),'a2':message(identifier='a2')})
    clock=[0.0]
    monkeypatch.setattr(sync,'time',SimpleNamespace(monotonic=lambda:clock[0]))
    original=messages.fetch_message
    def slow(*args,**kwargs):
        clock[0]=121.0
        return original(*args,**kwargs)
    monkeypatch.setattr(messages,'fetch_message',slow)
    result=sync.sync_account()
    assert not result['complete'] and 'TIME_LIMIT_REACHED' in result['limits_reached']
    checkpoint = accounts.read_sync_state('PRIMARY')
    assert checkpoint['page_token'] is None and 'completed_through' not in checkpoint
    later = datetime.fromtimestamp(checkpoint['before'] + 3 * 86400, timezone.utc)
    assert sync.plan_window(checkpoint, later)[:3] == (checkpoint['after'], checkpoint['before'], None)


@pytest.mark.parametrize('scopes', [[], ['openid'], [oauth.GMAIL_READONLY_SCOPE,'openid']])
def test_refresh_scope_mismatch_blocks_before_mailbox(monkeypatch,scopes):
    connect(monkeypatch)
    access=oauth.Secret('fictional-access')
    monkeypatch.setattr(oauth,'refresh_access_token',lambda **kw:{'access_token':access,'granted_scopes':scopes})
    with pytest.raises(oauth.OAuthError): sync.sync_account()
    with pytest.raises(ValueError,match='cleared'):access.reveal()


def test_multiple_contradictory_body_templates_cannot_be_high():
    value=message()
    value['payload']['parts'][1]['body']['data']=encoded(
        '<p>Thank you for applying to the Accountant position at Other Fictional Firm.</p>')
    assert parse(value)[0].confidence!='HIGH'


@pytest.mark.parametrize('fault', ['invalid_utf8', 'unknown_charset', 'binary_codec', 'malformed_part'])
def test_malformed_text_never_establishes_high(fault):
    import base64
    value = message()
    part = value['payload']['parts'][0]
    if fault == 'invalid_utf8':
        raw = base64.urlsafe_b64decode(part['body']['data'] + '=' * (-len(part['body']['data']) % 4))
        part['body']['data'] = base64.urlsafe_b64encode(raw + b'\xff').decode()
    elif fault == 'malformed_part':
        value['payload']['parts'].append('not a MIME object')
    else:
        charset = 'made-up-charset' if fault == 'unknown_charset' else 'base64_codec'
        part['headers'] = [{'name': 'Content-Type', 'value': 'text/plain; charset=' + charset}]
    result, row = parse(value)
    assert result.is_confirmation and result.confidence != 'HIGH'
    assert 'MALFORMED_PART_SKIPPED' in row['evidence_signals']


@pytest.mark.parametrize('host', ['jobs.lever.co', 'jobs.eu.lever.co'])
@pytest.mark.parametrize('ending', ['', '/apply'])
def test_lever_hosted_posting_shape(host, ending):
    url = 'https://' + host + '/example/12345678-1234-1234-1234-123456789abc' + ending
    assert parsers.LEVER.platform_url([url + '?tracking=omitted']) == url
    assert not parsers.LEVER.platform_url(['https://' + host + '/example'])
    assert not parsers.LEVER.platform_url(['https://' + host + '/example/jobs/123'])


def test_first_page_interruption_replays_same_window_days_later(monkeypatch):
    from types import SimpleNamespace
    connect(monkeypatch)
    reference = datetime.now(timezone.utc)
    earliest = reference.timestamp() - 30 * 86400 + 30
    seen = install_messages(monkeypatch, {'a1': message(), 'a2': message(identifier='a2', timestamp=earliest)})
    clock = [0.0]
    monkeypatch.setattr(sync, 'time', SimpleNamespace(monotonic=lambda: clock[0]))
    original = messages.fetch_message
    def interrupted(*args, **kwargs):
        clock[0] = 121.0
        return original(*args, **kwargs)
    monkeypatch.setattr(messages, 'fetch_message', interrupted)
    assert not sync.sync_account(reference=reference)['complete']
    first_query = seen[0][1]
    monkeypatch.setattr(messages, 'fetch_message', original)
    later = datetime.fromtimestamp(reference.timestamp() + 3 * 86400, timezone.utc)
    assert sync.sync_account(reference=later)['complete']
    assert all(call[1] == first_query for call in seen if call[0] == 'list')
    assert sync.list_confirmations()['count'] == 2


def test_gmail_id_response_must_match_request(monkeypatch):
    mock_transport(monkeypatch,lambda req:httpx.Response(200,content=iter([json.dumps(message(identifier='other')).encode()]),headers={'content-type':'application/json'}))
    with pytest.raises(messages.GmailReadError):messages.fetch_message(oauth.Secret('x'),'a1')


def test_oversized_message_skipped_and_outside_window_not_recorded(monkeypatch):
    connect(monkeypatch)
    install_messages(monkeypatch,{'a1':message(),'a2':message(identifier='a2',timestamp=time.time()-100*86400)})
    original=messages.fetch_message
    def fetch(access,identifier,**kwargs):
        if identifier=='a1':raise messages.GmailReadError('GMAIL_MESSAGE_TOO_LARGE','oversized')
        return original(access,identifier,**kwargs)
    monkeypatch.setattr(messages,'fetch_message',fetch)
    result=sync.sync_account()
    assert result['messages_skipped_unreadable']==1 and result['out_of_window']==1
    assert result['messages_fetched']==2 and sync.list_confirmations()['count']==0
