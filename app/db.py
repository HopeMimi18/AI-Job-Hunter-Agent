"""SQLite persists discovered jobs and application history locally."""
import sqlite3
import json
from datetime import datetime, timezone
from .config import DB_PATH


def now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec='seconds')


def connect():
    db = sqlite3.connect(DB_PATH)
    db.row_factory = sqlite3.Row
    db.execute('PRAGMA journal_mode=WAL')
    return db


def init_db():
    with connect() as db:
        db.executescript('''
            CREATE TABLE IF NOT EXISTS profile (
                id INTEGER PRIMARY KEY CHECK (id = 1), data_json TEXT NOT NULL,
                raw_text TEXT NOT NULL, resume_path TEXT NOT NULL, updated_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS jobs (
                id TEXT PRIMARY KEY, title TEXT NOT NULL, company TEXT NOT NULL,
                location TEXT, description TEXT, url TEXT, source TEXT NOT NULL,
                apply_method TEXT NOT NULL DEFAULT 'website', apply_email TEXT,
                email_submission_allowed INTEGER NOT NULL DEFAULT 0,
                score INTEGER NOT NULL DEFAULT 0, reasons_json TEXT NOT NULL DEFAULT '[]',
                blockers_json TEXT NOT NULL DEFAULT '[]', updated_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS applications (
                job_id TEXT PRIMARY KEY REFERENCES jobs(id), status TEXT NOT NULL,
                cover_letter TEXT, error TEXT, submitted_at TEXT, updated_at TEXT NOT NULL
            );
        ''')
        # Upgrade existing local SQLite databases without dropping profiles or applications.
        columns = {r[1] for r in db.execute('PRAGMA table_info(applications)')}
        if 'generator' not in columns:
            db.execute("ALTER TABLE applications ADD COLUMN generator TEXT NOT NULL DEFAULT 'template'")
        if 'analysis_json' not in columns:
            db.execute("ALTER TABLE applications ADD COLUMN analysis_json TEXT NOT NULL DEFAULT '{}'")


def profile():
    with connect() as db:
        r = db.execute('SELECT * FROM profile WHERE id = 1').fetchone()
    return ({**json.loads(r['data_json']), 'resume_path': r['resume_path']} if r else None)


def cv_text() -> str:
    with connect() as con:
        r = con.execute('SELECT raw_text FROM profile WHERE id=1').fetchone()
    return r['raw_text'] if r else ''


def set_profile(data: dict, raw_text: str, resume_path: str):
    with connect() as db:
        db.execute('''INSERT INTO profile VALUES(1, ?, ?, ?, ?)
            ON CONFLICT(id) DO UPDATE SET data_json=excluded.data_json, raw_text=excluded.raw_text,
            resume_path=excluded.resume_path, updated_at=excluded.updated_at''',
            (json.dumps(data), raw_text, resume_path, now()))


def put_job(item: dict, score: int, reasons: list[str], blockers: list[str]):
    with connect() as db:
        db.execute('''INSERT INTO jobs
            (id,title,company,location,description,url,source,apply_method,apply_email,
             email_submission_allowed,score,reasons_json,blockers_json,updated_at)
            VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)
            ON CONFLICT(id) DO UPDATE SET
              title=excluded.title, company=excluded.company, location=excluded.location,
              description=excluded.description, url=excluded.url, source=excluded.source,
              apply_method=excluded.apply_method, apply_email=excluded.apply_email,
              email_submission_allowed=excluded.email_submission_allowed, score=excluded.score,
              reasons_json=excluded.reasons_json, blockers_json=excluded.blockers_json,
              updated_at=excluded.updated_at''',
            (item['id'], item['title'], item['company'], item.get('location', ''),
             item.get('description', ''), item.get('url', ''), item.get('source', 'manual'),
             item.get('apply_method', 'website'), item.get('apply_email', ''),
             int(item.get('email_submission_allowed', False)), score, json.dumps(reasons),
             json.dumps(blockers), now()))


def get_job(job_id: str):
    with connect() as db:
        r = db.execute('SELECT * FROM jobs WHERE id=?', (job_id,)).fetchone()
    return dict(r) if r else None


def jobs(limit=100):
    with connect() as db:
        rows = db.execute('''SELECT j.*, a.status AS application_status FROM jobs j
             LEFT JOIN applications a ON j.id=a.job_id
             ORDER BY j.score DESC, j.updated_at DESC LIMIT ?''', (limit,)).fetchall()
    result = []
    for r in rows:
        item = dict(r)
        item['reasons'] = json.loads(item.pop('reasons_json'))
        item['blockers'] = json.loads(item.pop('blockers_json'))
        item['email_submission_allowed'] = bool(item['email_submission_allowed'])
        result.append(item)
    return result


def upsert_application(job_id: str, status: str, cover_letter: str | None = None,
                       error: str | None = None, submitted_at: str | None = None,
                       generator: str | None = None, analysis: dict | None = None):
    with connect() as con:
        con.execute('''INSERT INTO applications
            (job_id,status,cover_letter,error,submitted_at,updated_at,generator,analysis_json)
            VALUES(?,?,?,?,?,?,?,?) ON CONFLICT(job_id) DO UPDATE SET
            status=excluded.status,
            cover_letter=COALESCE(excluded.cover_letter, applications.cover_letter),
            error=excluded.error,
            submitted_at=COALESCE(excluded.submitted_at, applications.submitted_at),
            generator=COALESCE(?, applications.generator),
            analysis_json=COALESCE(?, applications.analysis_json),
            updated_at=excluded.updated_at''',
            (job_id, status, cover_letter, error, submitted_at, now(),
             generator or 'template', json.dumps(analysis or {}),
             generator, json.dumps(analysis) if analysis is not None else None))


def get_application(job_id: str):
    with connect() as con:
        r = con.execute('SELECT * FROM applications WHERE job_id=?', (job_id,)).fetchone()
    if not r:
        return None
    item = dict(r)
    item['analysis'] = json.loads(item.pop('analysis_json', '{}'))
    return item


def submissions_today():
    with connect() as db:
        r = db.execute("SELECT COUNT(*) FROM applications WHERE status='email_sent' AND substr(submitted_at,1,10)=?",
                       (now()[:10],)).fetchone()
    return r[0]
