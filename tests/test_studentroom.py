"""StudentRoom RSS tests: local fixtures only. No site requests or applications."""
import pytest
from app import db, workflow, sources
from app.mailer import digest_selection
from app.matching import score_job

RSS = b'''<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0"><channel><title>StudentRoom</title>
<item><title>Technology Foundation Bursaries 2027</title><link>https://www.studentroom.co.za/technology-bursaries-2027/</link><pubDate>Sun, 18 Oct 2026 08:00:00 +0200</pubDate><description><![CDATA[<p>Financial assistance for computing and software engineering students. Check the programme requirements.</p>]]></description></item>
<item><title>Cloud Internships 2026</title><link>https://www.studentroom.co.za/cloud-internships/</link><description>Entry-level software and cloud internships.</description></item>
<item><title>Electrical Apprenticeships 2026</title><link>https://www.studentroom.co.za/electrical-apprenticeships/</link><description>Electrical training.</description></item>
<item><title>IT Learnerships 2026</title><link>https://www.studentroom.co.za/it-learnerships/</link><description>IT work-integrated learning.</description></item>
<item><title>Offsite Bursaries</title><link>https://unauthorised.example.com/offsite/</link><description>Must reject link.</description></item>
</channel></rss>'''


def test_classifications_and_feed_security():
    results = sources.parse_studentroom_feed(RSS)
    assert len(results) == 4
    assert {i['opportunity_type'] for i in results} == {'bursary', 'internship', 'apprenticeship', 'learnership'}
    assert results[0]['published_at'] == '2026-10-18'
    assert results[0]['description'].startswith('Financial assistance')
    assert '<p>' not in results[0]['description']
    assert all(i['apply_method'] == 'website' and not i['email_submission_allowed'] for i in results)
    assert sources.parse_studentroom_feed(RSS, 2) == results[:2]
    assert sources.parse_studentroom_feed(RSS) == sources.parse_studentroom_feed(RSS)


def test_feed_disabled_by_default(monkeypatch):
    monkeypatch.delenv('STUDENTROOM_ENABLED', raising=False)
    class NeverClient:
        def get(self, *args, **kwargs):
            raise AssertionError('No site request allowed when disabled')
    assert sources.fetch_studentroom(NeverClient()) == []


def test_feed_opt_in_single_rss_request(monkeypatch):
    monkeypatch.setenv('STUDENTROOM_ENABLED', 'true')
    calls = []
    class Response:
        content = RSS
        def raise_for_status(self):
            pass
    class Client:
        def get(self, url, **kw):
            calls.append((url, kw))
            return Response()
    output = sources.fetch_studentroom(Client())
    assert len(output) == 4
    assert len(calls) == 1
    assert calls[0][0] == 'https://www.studentroom.co.za/feed/'


def test_bursary_never_drafted_as_standard_job(tmp_path, monkeypatch):
    monkeypatch.setattr(db, 'DB_PATH', tmp_path/'database.sqlite3')
    db.init_db()
    db.set_profile({'name':'Test Person','email':'test@example.org','skills':['java'], 'education_in_progress':True},
                   'Test Person\nJava software engineering in progress', str(tmp_path/'resume.pdf'))
    record = sources.parse_studentroom_feed(RSS)[0]
    workflow.ingest([record])
    saved = db.get_job(record['id'])
    assert saved['opportunity_type'] == 'bursary'
    assert saved['published_at'] == '2026-10-18'
    assert db.jobs()[0]['opportunity_type'] == 'bursary' or any(j['opportunity_type']=='bursary' for j in db.jobs())
    score, reasons, blockers = score_job(record, db.profile())
    assert 0 <= score <= 95
    assert any('eligib' in b.lower() or 'course' in b.lower() for b in blockers)
    with pytest.raises(ValueError, match='specific application process'):
        workflow.prepare(record['id'])
    assert workflow.autopilot() == []
    db.init_db()  # repeat migration
    assert db.get_job(record['id'])['opportunity_type'] == 'bursary'


def test_digest_includes_bursaries_even_after_many_jobs():
    jobs = [{'id':f'j{i}', 'opportunity_type':'job','score':99} for i in range(40)]
    bursary = {'id':'b1', 'opportunity_type':'bursary','score':70}
    selected = digest_selection(jobs+[bursary])
    assert bursary in selected
    assert len(selected) <= 12


def test_unsafe_xml_is_rejected():
    payload = b'<!DOCTYPE foo [<!ENTITY xxe SYSTEM "file:///etc/passwd">]><rss>&xxe;</rss>'
    with pytest.raises(Exception):
        sources.parse_studentroom_feed(payload)


def test_existing_job_db_migrates_without_losing_jobs(tmp_path, monkeypatch):
    import sqlite3
    path = tmp_path/'old.sqlite3'
    con = sqlite3.connect(path)
    con.execute('''CREATE TABLE jobs (id TEXT PRIMARY KEY, title TEXT NOT NULL,
                 company TEXT NOT NULL, location TEXT, description TEXT, url TEXT,
                 source TEXT NOT NULL, apply_method TEXT NOT NULL DEFAULT 'website',
                 apply_email TEXT, email_submission_allowed INTEGER DEFAULT 0,
                 score INTEGER DEFAULT 0, reasons_json TEXT DEFAULT '[]',
                 blockers_json TEXT DEFAULT '[]', updated_at TEXT NOT NULL)''')
    con.execute("INSERT INTO jobs (id,title,company,source,updated_at) VALUES ('oldjob','Junior Java Developer','Example','adzuna','2026-10-17')")
    con.commit()
    con.close()
    monkeypatch.setattr(db, 'DB_PATH', path)
    db.init_db()
    old = db.get_job('oldjob')
    assert old['opportunity_type'] == 'job'
    assert old['published_at'] == ''
    assert old['title'] == 'Junior Java Developer'
    db.init_db()
