"""Privacy, retention, deletion and boundary regressions for #46.

Fictional data only. These tests assert what the canonical state model and
the Gmail reconciliation link may durably hold, what leaves through the
export, backup, API and log paths, and what each deletion scope removes.
"""
import io
import json
import logging
import zipfile
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import delete, select

from backend import application_reconciliation as reconciliation
from backend import application_state as states
from backend import gmail_sync as sync
from backend.models import (Application, ApplicationEvent, FollowUp, Job,
                            JobObservation, Session, engine)
from tests.gmail_fixtures import gmail_env, keyring_backend, SENTINEL_ACCESS, SENTINEL_REFRESH
from tests.gmail_confirmation_fixtures import (AUTH_SENTINEL, BODY_SENTINEL,
                                               HTML_SENTINEL, RAW_SENTINEL)

pytestmark = pytest.mark.usefixtures('gmail_env')

#: Content classes that must never reach durable storage or a public output.
FORBIDDEN = (BODY_SENTINEL, HTML_SENTINEL, RAW_SENTINEL, AUTH_SENTINEL,
             SENTINEL_ACCESS, SENTINEL_REFRESH)


def clean(blob):
    if not isinstance(blob, bytes):
        blob = str(blob).encode()
    for sentinel in FORBIDDEN:
        assert sentinel.encode() not in blob


@pytest.fixture(autouse=True)
def fresh():
    from backend.models import initialize
    initialize()
    reconciliation.initialize_reconciliation_schema()
    with Session.begin() as db:
        db.execute(delete(reconciliation.GmailApplicationLink))
        db.execute(delete(states.ApplicationStateTransition))
        db.execute(delete(states.ApplicationStateRecord))
        db.execute(delete(sync.GmailConfirmation))
        db.execute(delete(ApplicationEvent))
        db.execute(delete(FollowUp))
        db.execute(delete(Application))
        # models.initialize() backfills one JobObservation per Job, so these
        # must go before the jobs they reference.
        db.execute(delete(JobObservation))
        db.execute(delete(Job))
    yield


def seed(*, confidence='HIGH', hostile=False, index=1):
    """One fictional application plus one matching piece of Gmail evidence.

    With `hostile=True` the evidence carries the non-retention sentinels in
    every field a hostile message could influence, so the assertions below
    prove the sentinels are absent because #46 does not store them -- not
    merely because the fixture never contained them.
    """
    from backend.normalization import employer_key
    company = 'Northwind Analytics'
    role = 'SOC Analyst'
    url = 'https://boards.greenhouse.io/northwind/jobs/4821'
    with Session.begin() as db:
        job = Job(company=company, title=role, source='Greenhouse',
                  apply_url=url, job_url=url,
                  normalized_employer_key=employer_key(company) or '',
                  date_found='2026-08-01T09:00:00+00:00', status='FOUND')
        db.add(job)
        db.flush()
        application = Application(job_id=job.id, status='FOUND',
                                  applied_date='2026-08-01T09:00:00+00:00')
        db.add(application)
        db.flush()
        row = sync.GmailConfirmation(
            account_slot='PRIMARY', gmail_account_id='fictional-account-id',
            gmail_message_id=f'fictional-message-{index}',
            sender='noreply@greenhouse.io',
            subject='Thank you for applying to ' + company,
            received_at='2026-08-01T09:04:00+00:00',
            detected_company=company, detected_role=role,
            detected_state='APPLICATION_CONFIRMED', confidence=confidence,
            parser_id=(RAW_SENTINEL if hostile else 'greenhouse-confirmation-v1'),
            evidence_signals=([BODY_SENTINEL, AUTH_SENTINEL, 'SENDER_DOMAIN']
                              if hostile else
                              ['SENDER_DOMAIN', 'SUBJECT_STRUCTURE',
                               'BODY_TEMPLATE', 'FIELD_CONSISTENCY',
                               'AUTHENTICATION']),
            application_url=url)
        db.add(row)
        db.flush()
        return application.id, job.id, row.id


def reconcile(evidence_id):
    with Session.begin() as db:
        return reconciliation.reconcile_confirmation(
            db, db.get(sync.GmailConfirmation, evidence_id))


# ---------------------------------------------------------------------------
# Retention
# ---------------------------------------------------------------------------
def test_transition_history_has_no_column_for_message_content():
    # The columns are enumerated exactly, so adding one to either table is a
    # deliberate, reviewed act rather than something a substring check might
    # wave through. `evidence_tokens` and `field_agreement` are JSON lists of
    # members of a fixed vocabulary, asserted elsewhere in this file.
    assert {column.name for column
            in states.ApplicationStateTransition.__table__.columns} == {
        'id', 'created_at', 'updated_at', 'application_id', 'sequence',
        'previous_state', 'new_state', 'source_category', 'asserted_by',
        'confidence', 'gmail_account_id', 'gmail_message_id',
        'gmail_confirmation_id', 'parser_id', 'evidence_tokens',
        'field_agreement', 'occurred_at', 'recorded_at', 'reason_code',
        'schema_version'}
    assert {column.name for column
            in reconciliation.GmailApplicationLink.__table__.columns} == {
        'id', 'created_at', 'updated_at', 'gmail_confirmation_id',
        'application_id', 'decision', 'reason_code', 'confidence',
        'matched_fields', 'candidate_count', 'strong_candidate_count',
        'transition_id', 'resolved_at', 'revisit_sequence', 'schema_version'}
    # The scheduler row is operational rotation state only: a counter and a
    # two-value queue token. It can hold nothing derived from a message.
    assert {column.name for column
            in reconciliation.ReconciliationScheduler.__table__.columns} == {
        'id', 'created_at', 'updated_at', 'attempt_sequence', 'next_queue',
        'schema_version'}
    assert {column.name for column
            in states.ApplicationStateRecord.__table__.columns} == {
        'id', 'created_at', 'updated_at', 'application_id', 'current_state',
        'state_ordinal', 'manual_ordinal', 'source_category', 'entered_at',
        'sequence', 'schema_version'}


def test_hostile_evidence_tokens_never_reach_durable_storage(tmp_path, monkeypatch,
                                                             caplog, capsys):
    """#46 copies evidence fields into its own history; it must copy only the
    declared vocabulary.

    The fixture plants the non-retention sentinels in the two fields #46
    actually reads from a #45 evidence row -- `evidence_signals` and
    `parser_id`. The assertions then check #46's own rows and #46's own
    outputs. (The #45 evidence row itself still holds what #45 stored; that
    table's retention is #45's claim and is covered by its own suite.)
    """
    from backend import doctor, models, privacy, reliability
    caplog.set_level(logging.DEBUG)
    for module in (privacy, reliability, models):
        monkeypatch.setattr(module, 'DATA', tmp_path)
    application_id, _, evidence_id = seed(hostile=True)
    result = reconcile(evidence_id)
    assert result.decision == reconciliation.DECISION_LINKED

    with Session() as db:
        transitions = db.execute(
            select(states.ApplicationStateTransition.__table__)).mappings().all()
        links = db.execute(
            select(reconciliation.GmailApplicationLink.__table__)).mappings().all()
        records = db.execute(
            select(states.ApplicationStateRecord.__table__)).mappings().all()
    latest = [row for row in transitions
              if row['application_id'] == application_id][-1]
    # Unknown tokens and an unknown parser id are dropped, not truncated:
    # only the declared vocabulary survives into history.
    assert list(latest['evidence_tokens']) == ['SENDER_DOMAIN']
    assert latest['parser_id'] == '', 'an unknown parser id is dropped'
    for rows in (transitions, links, records):
        clean(json.dumps([dict(row) for row in rows], default=str))

    # #46's own read models, API-facing shapes and operational outputs.
    clean(states.state_of(application_id))
    clean(states.transition_history(application_id))
    clean(states.state_summary())
    clean(reconciliation.needs_review())
    clean(reconciliation.reconciliation_status())
    clean(reconciliation.link_for(evidence_id))
    clean(result.as_dict())
    clean(doctor.run_checks())
    clean(caplog.text)
    clean(capsys.readouterr())
    # Nothing #46 wrote reached the security-event log or any other file it
    # owns under the data directory.
    for path in tmp_path.rglob('*'):
        if path.is_file():
            clean(path.read_bytes())


def test_export_and_backup_carry_no_46_sourced_sentinels(tmp_path, monkeypatch):
    """The private export and the SQLite backup include #46's tables; the
    rows they carry must hold only bounded tokens."""
    from backend import models, privacy, reliability
    for module in (privacy, reliability, models):
        monkeypatch.setattr(module, 'DATA', tmp_path)
    _, _, evidence_id = seed(hostile=True)
    reconcile(evidence_id)
    exported = privacy._export_data()
    with zipfile.ZipFile(io.BytesIO(exported.body)) as archive:
        records = json.loads(archive.read('records.json'))
    for table in ('application_states', 'application_state_transitions',
                  'gmail_application_links'):
        assert records[table], table
        clean(json.dumps(records[table]))
    backup = reliability.backup_database(force=True)
    assert (tmp_path / 'backups' / backup).exists()


def test_security_events_record_only_bounded_tokens(tmp_path, monkeypatch):
    from backend import models, security_events
    monkeypatch.setattr(models, 'DATA', tmp_path)
    seed(index=1)
    # A second application makes the evidence ambiguous, which is the event.
    seed(index=2)
    with Session() as db:
        evidence_id = db.scalar(select(sync.GmailConfirmation.id)
                                .order_by(sync.GmailConfirmation.id))
    reconcile(evidence_id)
    events = [event for event in security_events.tail(200)
              if event['event'].startswith('APPLICATION_')]
    assert events, 'a reconciliation conflict must be observable'
    for event in events:
        assert event['reason'] in security_events.REASONS.values()
        assert set(event['fields']) <= {'result'}
        assert event['fields'].get('result') in security_events._application_bounded()['result']
        blob = json.dumps(event)
        for forbidden in ('Northwind', 'SOC Analyst', 'greenhouse.io',
                          'boards.greenhouse.io', 'noreply@'):
            assert forbidden not in blob


def test_unknown_security_event_fields_are_dropped(tmp_path, monkeypatch):
    from backend import models, security_events
    monkeypatch.setattr(models, 'DATA', tmp_path)
    security_events.record('APPLICATION_RECONCILIATION_CONFLICT',
                           result='AMBIGUOUS_MATCH', company='Northwind Analytics',
                           url='https://boards.greenhouse.io/x?token=abc',
                           detail='Northwind Analytics SOC Analyst')
    entry = [event for event in security_events.tail(50)
             if event['event'] == 'APPLICATION_RECONCILIATION_CONFLICT'][-1]
    assert entry['fields'] == {'result': 'AMBIGUOUS_MATCH'}
    assert 'Northwind' not in json.dumps(entry)


# ---------------------------------------------------------------------------
# Export and backup
# ---------------------------------------------------------------------------
def test_export_includes_the_new_minimized_tables(tmp_path, monkeypatch):
    from backend import models, privacy
    for module in (privacy, models):
        monkeypatch.setattr(module, 'DATA', tmp_path)
    application_id, _, evidence_id = seed()
    reconcile(evidence_id)
    exported = privacy._export_data()
    with zipfile.ZipFile(io.BytesIO(exported.body)) as archive:
        records = json.loads(archive.read('records.json'))
    for table in ('application_states', 'application_state_transitions',
                  'gmail_application_links'):
        assert table in records, table
        assert records[table], f'{table} was exported empty'
    assert records['application_states'][0]['current_state'] == states.APPLIED
    assert records['gmail_application_links'][0]['decision'] == reconciliation.DECISION_LINKED


def test_privacy_counts_cover_the_new_tables(tmp_path, monkeypatch):
    from backend import models, privacy
    for module in (privacy, models):
        monkeypatch.setattr(module, 'DATA', tmp_path)
    _, _, evidence_id = seed()
    reconcile(evidence_id)
    counts = privacy.privacy_info()['counts']
    assert counts['application_states'] == 1
    assert counts['application_state_transitions'] >= 2
    assert counts['gmail_application_links'] == 1


# ---------------------------------------------------------------------------
# Deletion scopes
# ---------------------------------------------------------------------------
def test_history_deletion_removes_state_history_and_links_not_evidence(tmp_path,
                                                                       monkeypatch):
    from backend import models, privacy
    for module in (privacy, models):
        monkeypatch.setattr(module, 'DATA', tmp_path)
    _, _, evidence_id = seed()
    reconcile(evidence_id)
    privacy.delete_data(privacy.DeleteRequest(
        scope='history', confirmation='DELETE APPLICATION HISTORY'))
    with Session() as db:
        assert db.scalars(select(states.ApplicationStateRecord)).all() == []
        assert db.scalars(select(states.ApplicationStateTransition)).all() == []
        assert db.scalars(select(reconciliation.GmailApplicationLink)).all() == []
        assert db.scalars(select(Application)).all() == []
        # #45's lifecycle is unchanged: the evidence itself survives, and the
        # job it referred to survives too.
        assert len(db.scalars(select(sync.GmailConfirmation)).all()) == 1
        assert len(db.scalars(select(Job)).all()) == 1


def test_unlinked_evidence_decisions_survive_history_deletion(tmp_path, monkeypatch):
    from backend import models, privacy
    for module in (privacy, models):
        monkeypatch.setattr(module, 'DATA', tmp_path)
    # Evidence for an employer with no application: never linked.
    with Session.begin() as db:
        db.add(sync.GmailConfirmation(
            account_slot='PRIMARY', gmail_account_id='fictional-account-id',
            gmail_message_id='fictional-message-unmatched',
            sender='noreply@greenhouse.io', subject='Thank you for applying',
            received_at='2026-08-01T09:04:00+00:00',
            detected_company='Unaffiliated Holdings', detected_role='Analyst',
            detected_state='APPLICATION_CONFIRMED', confidence='HIGH',
            parser_id='greenhouse-confirmation-v1', evidence_signals=[],
            application_url=''))
    reconciliation.reconcile_pending()
    with Session() as db:
        assert len(db.scalars(select(reconciliation.GmailApplicationLink)).all()) == 1
    privacy.delete_data(privacy.DeleteRequest(
        scope='history', confirmation='DELETE APPLICATION HISTORY'))
    with Session() as db:
        links = db.scalars(select(reconciliation.GmailApplicationLink)).all()
        assert len(links) == 1 and links[0].application_id is None


def test_cv_deletion_leaves_application_state_untouched(tmp_path, monkeypatch):
    from backend import models, privacy
    for module in (privacy, models):
        monkeypatch.setattr(module, 'DATA', tmp_path)
    application_id, _, evidence_id = seed()
    reconcile(evidence_id)
    privacy.delete_data(privacy.DeleteRequest(scope='cv',
                                              confirmation='DELETE CV'))
    with Session() as db:
        record = db.scalar(select(states.ApplicationStateRecord).where(
            states.ApplicationStateRecord.application_id == application_id))
        assert record is not None and record.current_state == states.APPLIED
        assert len(db.scalars(select(reconciliation.GmailApplicationLink)).all()) == 1


def test_full_erase_removes_state_history_links_and_evidence(tmp_path, monkeypatch):
    from backend import models, privacy
    for module in (privacy, models):
        monkeypatch.setattr(module, 'DATA', tmp_path)
    _, _, evidence_id = seed()
    reconcile(evidence_id)
    privacy.delete_data(privacy.DeleteRequest(
        scope='all', confirmation='DELETE ALL LOCAL DATA'))
    with Session() as db:
        assert db.scalars(select(states.ApplicationStateRecord)).all() == []
        assert db.scalars(select(states.ApplicationStateTransition)).all() == []
        assert db.scalars(select(reconciliation.GmailApplicationLink)).all() == []
        assert db.scalars(select(sync.GmailConfirmation)).all() == []
        assert db.scalars(select(Application)).all() == []
        assert db.scalars(select(Job)).all() == []


def test_disconnect_preserves_evidence_state_and_history(tmp_path, monkeypatch):
    """ADR-0008: disconnect removes the token and cursor, never the evidence.
    #46 adds nothing to that path, and its records survive alongside it."""
    from backend import gmail_accounts as accounts, gmail_oauth as oauth, models
    monkeypatch.setattr(models, 'DATA', tmp_path)
    from tests.gmail_fixtures import install_google_double
    install_google_double(monkeypatch)
    accounts._bind_credential(
        'PRIMARY', {'authorized_email': 'tester@example.com',
                    'identity_key': 'tester@example.com',
                    'identity_kind': 'GMAIL_PROFILE_EMAIL'},
        [oauth.GMAIL_READONLY_SCOPE], oauth.Secret('fictional-refresh-value'))
    application_id, _, evidence_id = seed()
    reconcile(evidence_id)
    accounts.disconnect('PRIMARY')
    with Session() as db:
        assert len(db.scalars(select(sync.GmailConfirmation)).all()) == 1
        assert len(db.scalars(select(reconciliation.GmailApplicationLink)).all()) == 1
    result = states.state_of(application_id)
    assert result['state']['current_state'] == states.APPLIED
    assert any(row['gmail_confirmation_id'] == evidence_id
               for row in result['history'])


# ---------------------------------------------------------------------------
# API boundary
# ---------------------------------------------------------------------------
API_PATHS = ['/api/applications/state/summary',
             '/api/applications/state/reconciliation',
             '/api/applications/state/needs-review',
             '/api/applications/1/state',
             '/api/applications/1/state/history']
WRITE_PATHS = ['/api/applications/state/reconcile',
               '/api/applications/state/needs-review/1/confirm',
               '/api/applications/state/needs-review/1/reject']


@pytest.mark.parametrize('path', API_PATHS + WRITE_PATHS)
@pytest.mark.parametrize('headers', [{'origin': 'https://evil.example'},
                                     {'sec-fetch-site': 'cross-site'},
                                     {'host': 'evil.example'},
                                     {'sec-fetch-dest': 'document'}])
def test_new_routes_inherit_browser_guards(path, headers):
    from backend.main import app
    with TestClient(app) as client:
        response = (client.post(path, json={}, headers=headers)
                    if path in WRITE_PATHS else client.get(path, headers=headers))
        assert response.status_code in (400, 403)


def test_reads_are_no_store_and_writes_reject_get():
    from backend.main import app
    seed()
    with TestClient(app) as client:
        for path in API_PATHS:
            response = client.get(path)
            assert response.status_code in (200, 404)
            assert response.headers['cache-control'] == 'no-store'
        for path in WRITE_PATHS:
            assert client.get(path).status_code in (404, 405)


def test_demo_mode_denies_every_new_route(monkeypatch):
    from backend.main import app
    with TestClient(app) as client:
        monkeypatch.setenv('ASTRA_DEMO_ONLY', '1')
        for path in API_PATHS:
            assert client.get(path).status_code == 404
        for path in WRITE_PATHS:
            assert client.post(path, json={}).status_code == 404


def test_access_key_protects_every_new_route(monkeypatch):
    from backend.main import app
    with TestClient(app) as client:
        monkeypatch.setenv('APP_TOKEN', 'fictional-access-key')
        for path in API_PATHS:
            assert client.get(path).status_code == 401
        for path in WRITE_PATHS:
            assert client.post(path, json={}).status_code == 401


def test_api_rejects_out_of_range_identifiers_and_batch_sizes():
    from backend.main import app
    with TestClient(app) as client:
        assert client.get('/api/applications/0/state').status_code == 404
        assert client.get('/api/applications/-1/state').status_code in (404, 422)
        assert client.get('/api/applications/state/needs-review?limit=0'
                          ).status_code == 422
        assert client.get('/api/applications/state/needs-review?limit=201'
                          ).status_code == 422
        assert client.post('/api/applications/state/reconcile',
                           json={'limit': 0}).status_code == 400
        assert client.post('/api/applications/state/reconcile',
                           json={'limit': 10_000}).status_code == 400


def test_api_round_trip_confirms_a_review_item():
    from backend.main import app
    application_id, _, evidence_id = seed(confidence='MEDIUM')
    with TestClient(app) as client:
        run = client.post('/api/applications/state/reconcile', json={})
        assert run.status_code == 200 and run.json()['needs_review'] == 1
        queue = client.get('/api/applications/state/needs-review').json()
        assert queue['count'] == 1
        link_id = queue['items'][0]['id']
        confirmed = client.post(
            f'/api/applications/state/needs-review/{link_id}/confirm', json={})
        assert confirmed.status_code == 200 and confirmed.json()['applied'] is True
        result = client.get(f'/api/applications/{application_id}/state').json()
        assert result['state']['current_state'] == states.APPLIED
        assert result['legacy']['authoritative_field'] == (
            'application_states.current_state')
        assert result['history'][-1]['source_category'] == (
            states.SOURCE_USER_CONFIRMED_GMAIL)


def test_no_route_sets_a_state_directly():
    """#46 exposes reads plus the user's confirm/reject only. A caller must not
    be able to name a target state over the API."""
    from backend.application_state_api import router
    for route in router.routes:
        for method in route.methods:
            if method in ('POST', 'PUT', 'PATCH', 'DELETE'):
                assert 'reconcile' in route.path or 'needs-review' in route.path, route.path


# ---------------------------------------------------------------------------
# Remediation: the new conflict outcome stays bounded
# ---------------------------------------------------------------------------
def test_url_conflict_security_event_is_bounded(tmp_path, monkeypatch):
    """A contradictory requisition URL is worth an event, but the event may
    name neither the employer, the role, nor either URL."""
    from backend import models, security_events
    monkeypatch.setattr(models, 'DATA', tmp_path)
    from backend.normalization import employer_key
    company = 'Northwind Analytics'
    with Session.begin() as db:
        job = Job(company=company, title='SOC Analyst', source='Greenhouse',
                  apply_url='https://boards.greenhouse.io/northwind/jobs/111',
                  job_url='https://boards.greenhouse.io/northwind/jobs/111',
                  normalized_employer_key=employer_key(company) or '',
                  date_found='2026-08-01T09:00:00+00:00', status='FOUND')
        db.add(job)
        db.flush()
        db.add(Application(job_id=job.id, status='FOUND',
                           applied_date='2026-08-01T09:00:00+00:00'))
        db.flush()
        row = sync.GmailConfirmation(
            account_slot='PRIMARY', gmail_account_id='fictional-account-id',
            gmail_message_id='fictional-url-conflict', sender='noreply@greenhouse.io',
            subject='Thank you for applying to ' + company,
            received_at='2026-08-01T09:04:00+00:00', detected_company=company,
            detected_role='SOC Analyst', detected_state='APPLICATION_CONFIRMED',
            confidence='HIGH', parser_id='greenhouse-confirmation-v1',
            evidence_signals=['SENDER_DOMAIN'],
            application_url='https://boards.greenhouse.io/northwind/jobs/999')
        db.add(row)
        db.flush()
        evidence_id = row.id

    result = reconcile(evidence_id)
    assert result.reason_code == reconciliation.REASON_URL_CONFLICT

    events = [event for event in security_events.tail(200)
              if event['event'] == 'APPLICATION_RECONCILIATION_CONFLICT']
    assert events, 'the conflict must be observable'
    latest = events[-1]
    assert latest['fields'] == {'result': 'URL_IDENTITY_CONFLICT'}
    assert latest['reason'] in security_events.REASONS.values()
    blob = json.dumps(latest)
    for forbidden in (company, 'SOC Analyst', 'greenhouse.io', 'jobs/111',
                      'jobs/999', 'noreply@'):
        assert forbidden not in blob


def test_review_queue_exposes_no_field_beyond_45s_minimized_evidence():
    """Unlinkable evidence is now queued rather than dropped, so the queue's
    own shape is worth pinning."""
    seed(confidence='MEDIUM')
    with Session() as db:
        evidence_id = db.scalar(select(sync.GmailConfirmation.id))
    reconcile(evidence_id)
    queue = reconciliation.needs_review()
    assert queue['count'] == 1
    item = queue['items'][0]
    assert set(item) == {'id', 'gmail_confirmation_id', 'application_id',
                         'decision', 'reason_code', 'confidence',
                         'matched_fields', 'candidate_count',
                         'strong_candidate_count', 'transition_id',
                         'resolved_at', 'evidence'}
    assert set(item['evidence']) == {'detected_company', 'detected_role',
                                     'detected_state', 'received_at',
                                     'parser_id', 'application_url',
                                     'subject', 'sender'}
    clean(queue)


# ---------------------------------------------------------------------------
# Remediation: durable scheduler state stays bounded and non-personal
# ---------------------------------------------------------------------------
def test_scheduler_row_holds_only_bounded_operational_values(tmp_path, monkeypatch):
    from backend import models, privacy
    for module in (privacy, models):
        monkeypatch.setattr(module, 'DATA', tmp_path)
    _, _, evidence_id = seed(hostile=True)
    reconciliation.reconcile_pending(limit=4)
    with Session() as db:
        scheduler = db.get(reconciliation.ReconciliationScheduler, 1)
        assert scheduler is not None
        assert isinstance(scheduler.attempt_sequence, int)
        assert scheduler.next_queue in reconciliation.QUEUES
        assert scheduler.schema_version == reconciliation.SCHEMA_VERSION
        clean(json.dumps({'attempt_sequence': scheduler.attempt_sequence,
                          'next_queue': scheduler.next_queue,
                          'schema_version': scheduler.schema_version}))
        # The rotation stamp is a bare integer; it can encode nothing.
        stamps = db.scalars(select(
            reconciliation.GmailApplicationLink.revisit_sequence)).all()
        assert all(isinstance(stamp, int) for stamp in stamps)


def test_export_and_counts_include_the_scheduler_table(tmp_path, monkeypatch):
    from backend import models, privacy
    for module in (privacy, models):
        monkeypatch.setattr(module, 'DATA', tmp_path)
    _, _, evidence_id = seed()
    reconcile(evidence_id)
    counts = privacy.privacy_info()['counts']
    assert counts['reconciliation_scheduler'] == 1
    exported = privacy._export_data()
    with zipfile.ZipFile(io.BytesIO(exported.body)) as archive:
        records = json.loads(archive.read('records.json'))
    assert 'reconciliation_scheduler' in records
    assert records['reconciliation_scheduler'][0]['next_queue'] in (
        reconciliation.QUEUES)
    clean(json.dumps(records['reconciliation_scheduler']))
    clean(json.dumps(records['gmail_application_links']))


def test_history_deletion_leaves_the_scheduler_counter_alone(tmp_path, monkeypatch):
    """The counter is operational state, not application history."""
    from backend import models, privacy
    for module in (privacy, models):
        monkeypatch.setattr(module, 'DATA', tmp_path)
    _, _, evidence_id = seed()
    reconciliation.reconcile_pending(limit=4)
    with Session() as db:
        before = db.get(reconciliation.ReconciliationScheduler, 1).attempt_sequence
    assert before > 0
    privacy.delete_data(privacy.DeleteRequest(
        scope='history', confirmation='DELETE APPLICATION HISTORY'))
    with Session() as db:
        scheduler = db.get(reconciliation.ReconciliationScheduler, 1)
        assert scheduler is not None and scheduler.attempt_sequence == before


def test_full_erase_resets_the_scheduler_with_the_links(tmp_path, monkeypatch):
    from backend import models, privacy
    for module in (privacy, models):
        monkeypatch.setattr(module, 'DATA', tmp_path)
    seed()
    reconciliation.reconcile_pending(limit=4)
    with Session() as db:
        assert db.get(reconciliation.ReconciliationScheduler, 1).attempt_sequence > 0
    privacy.delete_data(privacy.DeleteRequest(
        scope='all', confirmation='DELETE ALL LOCAL DATA'))
    with Session() as db:
        assert db.scalars(select(reconciliation.GmailApplicationLink)).all() == []
        scheduler = db.get(reconciliation.ReconciliationScheduler, 1)
        # Reset, not orphaned: the counter never outlives the stamps it made.
        assert scheduler.attempt_sequence == 0
        assert scheduler.next_queue == reconciliation.QUEUE_PENDING


def test_reconciliation_schema_upgrade_is_additive_and_idempotent():
    """A database that predates the scheduler gains the column, index, table
    and seed row without losing a decision."""
    from sqlalchemy import inspect, text
    from backend.models import engine
    _, _, evidence_id = seed()
    reconcile(evidence_id)
    with Session() as db:
        before = db.scalar(select(reconciliation.GmailApplicationLink.decision))
    with engine.begin() as connection:
        connection.execute(text('DROP TABLE IF EXISTS reconciliation_scheduler'))
        # SQLite refuses to drop a column an index depends on, which is also
        # why the real upgrade adds the column before creating the index.
        connection.execute(text(
            'DROP INDEX IF EXISTS ix_gmail_application_link_rotation'))
        connection.execute(text(
            'ALTER TABLE gmail_application_links DROP COLUMN revisit_sequence'))
    assert 'revisit_sequence' not in {
        column['name'] for column
        in inspect(engine).get_columns('gmail_application_links')}

    for _ in range(2):  # idempotent
        reconciliation.initialize_reconciliation_schema()
    columns = {column['name'] for column
               in inspect(engine).get_columns('gmail_application_links')}
    assert 'revisit_sequence' in columns
    assert inspect(engine).has_table('reconciliation_scheduler')
    with Session() as db:
        scheduler = db.get(reconciliation.ReconciliationScheduler, 1)
        assert scheduler.attempt_sequence == 0
        assert scheduler.next_queue == reconciliation.QUEUE_PENDING
        # The pre-existing decision survived untouched and starts unrotated.
        link = db.scalar(select(reconciliation.GmailApplicationLink))
        assert link.decision == before
        assert link.revisit_sequence == 0
