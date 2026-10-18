"""Local-first API. Run on 127.0.0.1; do not publicly expose without authentication and hardening."""
from contextlib import asynccontextmanager
from pathlib import Path
import secrets
import uuid
from fastapi import FastAPI, Depends, File, Header, HTTPException, UploadFile
from fastapi.responses import HTMLResponse
from pydantic import BaseModel, Field
from . import db
from .config import ROOT, RUNTIME, TOKEN
from .cv import read_cv, extract_profile
from .matching import score_job
from .sources import discover, make_id
from .workflow import ingest, prepare, approve, send, autopilot
from .mailer import send_digest
import os


@asynccontextmanager
async def lifespan(_):
    db.init_db()
    yield


app = FastAPI(title='AI Job Hunter', version='0.1.0', lifespan=lifespan)


def authenticated(x_admin_token: str | None = Header(default=None)):
    # Local development convenience. MUST configure a token before any non-local deployment.
    if TOKEN and not secrets.compare_digest(x_admin_token or '', TOKEN):
        raise HTTPException(status_code=401, detail='Missing/invalid X-Admin-Token')


class JobIn(BaseModel):
    title: str = Field(min_length=3, max_length=160)
    company: str = Field(min_length=2, max_length=160)
    location: str = Field(default='', max_length=160)
    description: str = Field(min_length=30, max_length=30000)
    url: str = Field(default='', max_length=1000)
    apply_method: str = Field(default='website', pattern='^(website|email)$')
    apply_email: str = Field(default='', max_length=320)
    email_submission_allowed: bool = False


@app.get('/', response_class=HTMLResponse)
def dashboard():
    return (ROOT / 'app' / 'dashboard.html').read_text(encoding='utf-8')


@app.get('/api/health')
def health():
    return {'ok': True, 'version': '0.1.0', 'autopilot_enabled': os.getenv('AUTO_APPLY_ENABLED', 'false').lower() in ('1','true','yes')}


@app.get('/api/profile', dependencies=[Depends(authenticated)])
def profile():
    person = db.profile()
    if person:
        person.pop('resume_path', None)  # no path disclosure
    return {'profile': person}


@app.post('/api/profile/upload', dependencies=[Depends(authenticated)])
async def upload(file: UploadFile = File(...)):
    suffix = Path(file.filename or '').suffix.lower()
    if suffix not in ('.pdf', '.docx'):
        raise HTTPException(status_code=400, detail='Upload a PDF or DOCX resume')
    contents = await file.read(5 * 1024 * 1024 + 1)
    if len(contents) > 5 * 1024 * 1024:
        raise HTTPException(status_code=400, detail='Resume exceeds 5 MB')
    # A fresh private filename prevents unsafe supplied paths and accidental commits.
    destination = RUNTIME / f'cv_{uuid.uuid4().hex}{suffix}'
    destination.write_bytes(contents)
    try:
        text = read_cv(destination)
        person = extract_profile(text)
        db.set_profile(person, text, str(destination))
        # A new CV changes job-fit scores. Preserve application history while rescoring.
        for existing in db.jobs(100000):
            score, reasons, blockers = score_job(existing, person)
            db.put_job(existing, score, reasons, blockers)
    except Exception as exc:
        destination.unlink(missing_ok=True)
        raise HTTPException(status_code=400, detail=f'CV parsing failed: {exc}')
    return {'profile': person, 'note': 'CV processed locally and stored in runtime/. Review extracted details before enabling applications.'}


@app.get('/api/jobs', dependencies=[Depends(authenticated)])
def list_jobs():
    return {'jobs': db.jobs()}


@app.post('/api/jobs/search', dependencies=[Depends(authenticated)])
def search_jobs():
    found, warnings = discover()
    if found and not db.profile():
        raise HTTPException(status_code=400, detail='Upload your CV first')
    count = ingest(found) if found else 0
    return {'count': count, 'warnings': warnings, 'jobs': db.jobs()[:30]}


@app.post('/api/jobs/import', dependencies=[Depends(authenticated)])
def import_job(payload: JobIn):
    job = payload.model_dump()
    if job['apply_method'] == 'email':
        if not job['email_submission_allowed']:
            raise HTTPException(status_code=400, detail='Confirm the advertisement explicitly allows email applications')
        if not job['apply_email']:
            raise HTTPException(status_code=400, detail='Application email address required')
    else:
        job['apply_email'] = ''
        job['email_submission_allowed'] = False
    job['source'] = 'manual'
    job['id'] = make_id('manual', job['url'] or f'{job["company"]}:{job["title"]}:{job["apply_email"]}')
    try:
        ingest([job])
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    return {'job': db.get_job(job['id'])}


@app.get('/api/applications/{job_id}', dependencies=[Depends(authenticated)])
def get_application(job_id: str):
    return {'application': db.get_application(job_id)}


@app.post('/api/applications/{job_id}/prepare', dependencies=[Depends(authenticated)])
def prepare_application(job_id: str):
    try:
        return prepare(job_id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@app.post('/api/applications/{job_id}/approve', dependencies=[Depends(authenticated)])
def approve_application(job_id: str):
    try:
        return approve(job_id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@app.post('/api/applications/{job_id}/submit', dependencies=[Depends(authenticated)])
def submit_application(job_id: str):
    try:
        return send(job_id, automatic=False)
    except (ValueError, RuntimeError) as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f'Mail submission failed: {exc}')


@app.post('/api/daily/run', dependencies=[Depends(authenticated)])
def daily_run():
    if not db.profile():
        raise HTTPException(status_code=400, detail='Upload your CV before running the daily workflow')
    found, warnings = discover()
    ingest(found)
    results = autopilot()
    notification = 'not configured'
    if os.getenv('NOTIFY_EMAIL'):
        try:
            send_digest(os.environ['NOTIFY_EMAIL'], db.jobs()[:10], results)
            notification = 'Email accepted by SMTP server'
        except Exception as exc:
            notification = f'Failed: {exc}'
    return {'discovered': len(found), 'applications': results,
            'digest': notification, 'warnings': warnings}
