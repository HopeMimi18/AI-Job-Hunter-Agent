"""Offline regression tests: mock Bedrock, never access AWS or submit applications."""
import json
from pathlib import Path
import pytest
from app import ai, db, workflow
from app.matching import score_job, select_project_evidence


@pytest.fixture
def store(tmp_path, monkeypatch):
    monkeypatch.setattr(db, 'DB_PATH', tmp_path / 'test.sqlite3')
    monkeypatch.delenv('BEDROCK_ENABLED', raising=False)
    monkeypatch.delenv('AUTO_APPLY_ENABLED', raising=False)
    db.init_db()
    cv = ("Test Candidate\ntest@example.com\nSoftware Engineering programme in progress\n"
          "Technical skills: Java, Python, SQL, JDBC, Maven\n"
          "SELECTED PROJECTS\n"
          "Java Persistence | Java, JDBC, SQL, Maven\n"
          "• Implemented Java persistence using JDBC and SQL prepared statements.\n"
          "Python Automation | Python, AWS\n"
          "• Built Python automation tools for daily reporting.\n")
    file = tmp_path/'resume.pdf'
    file.write_text(cv)
    db.set_profile({'name':'Test Candidate', 'email':'test@example.com',
                    'skills':['java','python','jdbc','sql','maven'],
                    'education_in_progress':True}, cv, str(file))
    return cv


def job():
    return {'id':'job-1','title':'Junior Java Developer','company':'Example Ltd',
            'location':'Johannesburg', 'source':'manual',
            'description':'We need an entry-level Java software developer experienced with JDBC, SQL and Maven. ' 
                          'Please share examples of Java project work.',
            'apply_method':'website', 'email_submission_allowed':False}


def test_local_letter_uses_relevant_cv_projects(store):
    workflow.ingest([job()])
    result=workflow.prepare('job-1')
    assert result['generator']=='template'
    assert 'Java Persistence' in result['cover_letter']
    assert 'JDBC and SQL prepared statements' in result['cover_letter']
    assert 'Python Automation' not in result['cover_letter']
    assert 'Matched requirements' not in result['cover_letter']
    assert db.get_application('job-1')['analysis']['method']=='local'


def test_project_match_is_grounded_and_degree_flag(store):
    projects=select_project_evidence(store, job())
    assert projects and projects[0]['title']=='Java Persistence'
    senior=dict(job(), title='Senior Java Engineer', description="Bachelor's degree required. 5 years experience with Java.")
    _,_,blockers=score_job(senior,db.profile(),store)
    assert any('degree' in x.lower() for x in blockers)
    assert any('experience' in x.lower() for x in blockers)


def test_bedrock_mock_produces_analysis_and_draft(store, monkeypatch):
    job_data=job()
    workflow.ingest([job_data])
    monkeypatch.setenv('BEDROCK_ENABLED','true')
    calls=[]
    class FakeBedrock:
        def converse(self, **kw):
            calls.append(kw)
            draft={'body':'I am applying for the Junior Java Developer role at Example Ltd. '
                          'My Java persistence project used JDBC and SQL prepared statements. '
                          'I would welcome the opportunity to contribute to your engineering team.',
                   'evidence_quotes':['Implemented Java persistence using JDBC and SQL prepared statements.'],
                   'matched_requirements':['Java with JDBC persistence'], 'gaps':['Employment experience not stated']}
            return {'output':{'message':{'content':[{'text':json.dumps(draft)}]}}}
    monkeypatch.setattr('boto3.client',lambda *a,**kw: FakeBedrock())
    result=workflow.prepare('job-1')
    assert result['generator']=='bedrock'
    assert 'Junior Java Developer role' in result['cover_letter']
    assert 'test@example.com' in result['cover_letter']
    assert calls and calls[0]['modelId']=='amazon.nova-lite-v1:0'
    prompt=calls[0]['messages'][0]['content'][0]['text']
    assert 'test@example.com' not in prompt
    assert 'Test Candidate' not in prompt
    assert 'Java Persistence' in prompt
    assert db.get_application('job-1')['generator']=='bedrock'
    assert db.get_application('job-1')['analysis']['gaps_to_review']==['Employment experience not stated']


def test_bedrock_rejects_made_up_quotes(store, monkeypatch):
    monkeypatch.setenv('BEDROCK_ENABLED','true')
    workflow.ingest([job()])
    class BadBedrock:
        def converse(self,**kwargs):
            return {'output':{'message':{'content':[{'text':json.dumps({
                'body':'I have fifteen years at NASA and twenty certifications. '+('Fake data. '*20),
                'evidence_quotes':['Won 12 world championships in Java'],
                'matched_requirements':[], 'gaps':[]})}]}}}
    monkeypatch.setattr('boto3.client',lambda *a,**kw: BadBedrock())
    with pytest.raises(RuntimeError, match='evidence not found'):
        workflow.prepare('job-1')
    assert db.get_application('job-1') is None


def test_ai_mode_never_auto_sends(store, monkeypatch):
    data=job()
    data.update(apply_method='email', apply_email='careers@example.org',email_submission_allowed=True)
    workflow.ingest([data])
    monkeypatch.setenv('BEDROCK_ENABLED','true')
    monkeypatch.setenv('AUTO_APPLY_ENABLED','true')
    monkeypatch.setenv('APPROVED_APPLICATION_EMAILS','careers@example.org')
    monkeypatch.setattr(workflow,'send_application_email',lambda *args: pytest.fail('Must not send'))
    assert workflow.autopilot()==[]
    assert db.get_application('job-1') is None


def test_sqlite_schema_migrates_without_losing_data(tmp_path,monkeypatch):
    import sqlite3
    monkeypatch.setattr(db, 'DB_PATH', tmp_path/'legacy.db')
    db.init_db()
    db.set_profile({'name':'Candidate','email':'a@b.com'},'resume content','resume.pdf')
    db.init_db()  # Migration is idempotent.
    assert db.profile()['name']=='Candidate'
    with db.connect() as con:
        cols={row[1] for row in con.execute('PRAGMA table_info(applications)')}
    assert {'generator','analysis_json'}.issubset(cols)
