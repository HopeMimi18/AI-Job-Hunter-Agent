"""Offline tests. They NEVER contact job sites or send emails."""
from pathlib import Path
import pytest
from app import db
from app.cv import extract_profile
from app.matching import score_job
from app.sources import make_id
from app import workflow


@pytest.fixture
def store(tmp_path, monkeypatch):
    monkeypatch.setattr(db, 'DB_PATH', tmp_path / 'test.sqlite3')
    monkeypatch.delenv('AUTO_APPLY_ENABLED', raising=False)
    monkeypatch.delenv('APPROVED_APPLICATION_EMAILS', raising=False)
    db.init_db()
    resume = tmp_path / 'resume.pdf'
    resume.write_bytes(b'mock pdf; email transport is stubbed')
    db.set_profile({'name':'Test Candidate','email':'test@example.org','phone':'',
                    'skills':['python','java','sql','aws'],'education_in_progress': True},
                   'TEST CANDIDATE\nPython, Java, SQL, AWS', str(resume))
    return tmp_path


def email_job(email='jobs@example.org'):
    return {'id':make_id('manual',f'job:{email}'), 'title':'Junior Python Developer',
            'company':'Demo Employer', 'location':'Johannesburg, South Africa',
            'description':'Junior Python developer using Python, Java, SQL and AWS. '
                          'Please send your CV and cover letter by email to the careers team.',
            'url':'https://example.org/jobs/1', 'source':'manual', 'apply_method':'email',
            'apply_email':email, 'email_submission_allowed': True}


def test_cv_extract():
    profile = extract_profile('HOPE LEKGEU\nhope@example.com\nPython Java Docker AWS SQL\n'
                              'Software engineering in progress')
    assert profile['name'] == 'Hope Lekgeu'
    assert profile['email'] == 'hope@example.com'
    assert 'python' in profile['skills']
    assert profile['education_in_progress'] is True


def test_senior_degree_role_flagged():
    job = {'title':'Senior Java Engineer', 'location':'London',
           'description':'Bachelor\'s degree required. 5+ years experience with Java and SQL.'}
    score, reasons, blockers = score_job(job, {'skills':['java','sql']})
    assert score >= 0
    assert len(blockers) >= 2


def test_import_and_no_duplicate(store):
    j = email_job()
    workflow.ingest([j, j])
    assert len(db.jobs()) == 1
    assert db.jobs()[0]['score'] >= 90


def test_requires_approval_and_allowlist(store, monkeypatch):
    job = email_job()
    workflow.ingest([job])
    workflow.prepare(job['id'])
    with pytest.raises(ValueError, match='Recipient is not'):
        workflow.send(job['id'])
    monkeypatch.setenv('APPROVED_APPLICATION_EMAILS', 'jobs@example.org')
    with pytest.raises(ValueError, match='Approve'):
        workflow.send(job['id'])


def test_approved_submission_stub_and_duplicates(store, monkeypatch):
    job = email_job()
    workflow.ingest([job])
    workflow.prepare(job['id'])
    workflow.approve(job['id'])
    monkeypatch.setenv('APPROVED_APPLICATION_EMAILS', 'jobs@example.org')
    observed = []
    monkeypatch.setattr(workflow, 'send_application_email',
                        lambda j,p,t: observed.append((j['apply_email'],p['email'],t)))
    result = workflow.send(job['id'])
    assert result['status'] == 'email_sent'
    assert len(observed) == 1
    assert db.get_application(job['id'])['status'] == 'email_sent'
    with pytest.raises(ValueError, match='duplicate'):
        workflow.send(job['id'])


def test_autopilot_off_by_default(store, monkeypatch):
    job = email_job()
    workflow.ingest([job])
    assert workflow.autopilot() == []
    assert db.get_application(job['id']) is None


def test_autopilot_with_explicit_permissions(store, monkeypatch):
    job = email_job()
    workflow.ingest([job])
    monkeypatch.setenv('APPROVED_APPLICATION_EMAILS', 'jobs@example.org')
    monkeypatch.setenv('AUTO_APPLY_ENABLED', 'true')
    monkeypatch.setenv('AUTO_APPLY_MIN_SCORE', '90')
    monkeypatch.setenv('AUTO_APPLY_DAILY_LIMIT', '1')
    observed = []
    monkeypatch.setattr(workflow, 'send_application_email',
                        lambda j,p,t: observed.append(j['apply_email']))
    sent = workflow.autopilot()
    assert len(sent) == 1 and sent[0]['status'] == 'email_sent'
    assert observed == ['jobs@example.org']
    assert workflow.autopilot() == []  # no duplicates on repeat


def test_never_auto_apply_unverified_provider(store, monkeypatch):
    job = email_job()
    job['source'] = 'adzuna'
    workflow.ingest([job])
    monkeypatch.setenv('AUTO_APPLY_ENABLED', 'true')
    monkeypatch.setenv('APPROVED_APPLICATION_EMAILS', 'jobs@example.org')
    assert workflow.autopilot() == []


def test_autopilot_respects_daily_cap(store, monkeypatch):
    first = email_job('jobs1@example.org')
    second = email_job('jobs2@example.org')
    workflow.ingest([first, second])
    monkeypatch.setenv('APPROVED_APPLICATION_EMAILS', 'jobs1@example.org,jobs2@example.org')
    monkeypatch.setenv('AUTO_APPLY_ENABLED', 'true')
    monkeypatch.setenv('AUTO_APPLY_DAILY_LIMIT', '1')
    observed = []
    monkeypatch.setattr(workflow, 'send_application_email',
                        lambda j,p,t: observed.append(j['apply_email']))
    result = workflow.autopilot()
    assert len(result) == 1
    assert len(observed) == 1
    assert db.submissions_today() == 1


def test_employer_email_has_resume_attachment(store, monkeypatch):
    from app import mailer
    job = email_job()
    person = db.profile()
    captures = []
    monkeypatch.setattr(mailer, 'smtp_send', lambda msg: captures.append(msg))
    mailer.send_application_email(job, person, 'Dear hiring team, please review my CV.')
    assert len(captures) == 1
    email = captures[0]
    assert email['To'] == 'jobs@example.org'
    assert email['Reply-To'] == 'test@example.org'
    assert len(list(email.iter_attachments())) == 1
    assert list(email.iter_attachments())[0].get_filename().endswith('.pdf')
