"""Application state machine. Email auto-apply requires multiple safeguards."""
import os
import re
from . import db
from .config import application_allowlist, enabled
from .matching import score_job
from .mailer import send_application_email


def ingest(jobs: list[dict]) -> int:
    candidate = db.profile()
    if not candidate:
        raise ValueError('Upload your CV before importing jobs')
    for job in jobs:
        score, reasons, blockers = score_job(job, candidate)
        db.put_job(job, score, reasons, blockers)
    return len(jobs)


def cover_letter(job: dict, candidate: dict) -> str:
    full_name = candidate.get('name', '').strip()
    if not full_name or not candidate.get('email'):
        raise ValueError('Check candidate name and email in extracted CV profile')
    skill_list = ', '.join((candidate.get('skills') or [])[:7]) or 'software development'
    return (f'Dear {job["company"]} Hiring Team,\n\n'
            f'I would like to apply for the {job["title"]} position. '
            f'I am currently developing my software engineering skills and have hands-on experience '
            f'with {skill_list}, as evidenced in my attached resume. '
            f'I would welcome the opportunity to discuss how my project work and interest in the role could contribute to your team.\n\n'
            f'Thank you for considering my application.\n\nKind regards,\n{full_name}\n{candidate["email"]}')


def prepare(job_id: str):
    job = db.get_job(job_id)
    candidate = db.profile()
    if not job or not candidate:
        raise ValueError('Job or CV missing')
    current = db.get_application(job_id)
    if current and current['status'] == 'email_sent':
        raise ValueError('Already sent: duplicate applications are blocked')
    text = cover_letter(job, candidate)
    db.upsert_application(job_id, 'prepared', cover_letter=text)
    return {'job_id': job_id, 'status': 'prepared', 'cover_letter': text}


def approve(job_id: str):
    current = db.get_application(job_id)
    if not current or current['status'] not in ('prepared', 'approved', 'failed'):
        raise ValueError('Prepare application before approving it')
    if not db.get_job(job_id):
        raise ValueError('Job missing')
    db.upsert_application(job_id, 'approved')
    return {'job_id': job_id, 'status': 'approved'}


def eligibility(job_id: str, automatic=False) -> tuple[dict, dict, dict]:
    job = db.get_job(job_id)
    candidate = db.profile()
    app = db.get_application(job_id)
    if not job or not candidate or not app:
        raise ValueError('Job, candidate or prepared application missing')
    if app['status'] == 'email_sent':
        raise ValueError('Already sent: blocked duplicate')
    if job['apply_method'] != 'email' or not job['email_submission_allowed']:
        raise ValueError('Job is not explicitly marked as accepting applications by email')
    target = (job['apply_email'] or '').lower().strip()
    if not re.fullmatch(r'[^@\s]+@[^@\s]+\.[^@\s]+', target):
        raise ValueError('Invalid employer application email')
    if target not in application_allowlist():
        raise ValueError('Recipient is not in APPROVED_APPLICATION_EMAILS')
    if not app['cover_letter']:
        raise ValueError('No application text prepared')
    if automatic:
        if not enabled('AUTO_APPLY_ENABLED'):
            raise ValueError('Autopilot disabled')
        if job['source'] != 'manual':
            raise ValueError('Automatic email submission requires a manually verified listing')
        if db.submissions_today() >= int(os.getenv('AUTO_APPLY_DAILY_LIMIT', '3')):
            raise ValueError('Daily application limit reached')
        if job['score'] < int(os.getenv('AUTO_APPLY_MIN_SCORE', '90')):
            raise ValueError('Below autopilot threshold')
        import json
        if json.loads(job['blockers_json']):
            raise ValueError('Job requirements need human review')
    else:
        if app['status'] != 'approved':
            raise ValueError('Approve each email application before manually sending')
    return job, candidate, app


def send(job_id: str, automatic=False):
    job, candidate, app = eligibility(job_id, automatic)
    try:
        send_application_email(job, candidate, app['cover_letter'])
    except Exception as exc:
        db.upsert_application(job_id, 'failed', error=f'{type(exc).__name__}: {exc}')
        raise
    db.upsert_application(job_id, 'email_sent', submitted_at=db.now())
    return {'job_id': job_id, 'status': 'email_sent',
            'note': 'Mail server accepted the email. Employer receipt or acceptance is not confirmed.'}


def autopilot():
    outcome = []
    if not enabled('AUTO_APPLY_ENABLED'):
        return outcome
    for j in db.jobs(200):
        if j['source'] != 'manual' or j['apply_method'] != 'email' or not j['email_submission_allowed']:
            continue
        if j['application_status'] == 'email_sent' or j['score'] < int(os.getenv('AUTO_APPLY_MIN_SCORE', '90')):
            continue
        if j['blockers']:
            continue
        if db.submissions_today() >= int(os.getenv('AUTO_APPLY_DAILY_LIMIT', '3')):
            break
        try:
            # Application is prepared using verified CV evidence, not invented experience.
            prepare(j['id'])
            outcome.append(send(j['id'], automatic=True))
        except Exception as exc:
            outcome.append({'job_id': j['id'], 'status': f'skipped / failed: {exc}'})
    return outcome
