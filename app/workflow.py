"""Application state machine. Email auto-apply requires multiple safeguards."""
import os
import re
from . import db
from .config import application_allowlist, enabled
from .matching import score_job, select_project_evidence
from .mailer import send_application_email


def ingest(jobs: list[dict]) -> int:
    candidate = db.profile()
    if not candidate:
        raise ValueError('Upload your CV before importing jobs')
    for job in jobs:
        score, reasons, blockers = score_job(job, candidate, db.cv_text())
        db.put_job(job, score, reasons, blockers)
    return len(jobs)


def cover_letter(job: dict, candidate: dict, cv_text: str = '') -> str:
    """Offline, evidence-based letter for when Bedrock is off (no invented qualifications)."""
    full_name = candidate.get('name', '').strip()
    email = candidate.get('email', '').strip()
    if not full_name or not email:
        raise ValueError('Check candidate name and email in extracted CV profile')
    from .matching import _skill_mentions
    relevant_skills = sorted(_skill_mentions(job.get('title', '') + ' ' + job.get('description', ''))
                             & set(candidate.get('skills') or []))
    skill_text = ', '.join(relevant_skills[:5]) if relevant_skills else 'software engineering'
    projects = select_project_evidence(cv_text, job, limit=2)
    paragraphs = [
        f'I am applying for the {job["title"]} position at {job["company"]}. '
        f'My CV documents practical work in {skill_text}, which relates to this opportunity.'
    ]
    for index, project in enumerate(projects):
        intro = "One relevant CV project" if index == 0 else "Another relevant project"
        paragraphs.append(f'{intro} is {project["title"]}. My documented work includes: '
                          f'{project["cv_quote"].rstrip(".")}.')
    if candidate.get('education_in_progress'):
        paragraphs.append('I am continuing my studies while developing practical engineering skills. '
                          'I would welcome the opportunity to contribute to your team and keep learning.')
    else:
        paragraphs.append('I would welcome the opportunity to discuss how my documented skills '
                          'and projects align with this role.')
    return (f'Dear {job["company"]} Hiring Team,\n\n'
            + '\n\n'.join(paragraphs)
            + f'\n\nThank you for considering my application.\n\nKind regards,\n{full_name}\n{email}')


def prepare(job_id: str):
    job = db.get_job(job_id)
    candidate = db.profile()
    if not job or not candidate:
        raise ValueError('Job or CV missing')
    current = db.get_application(job_id)
    if current and current['status'] == 'email_sent':
        raise ValueError('Already sent: duplicate applications are blocked')
    if len((job.get('description') or '').strip()) < 30:
        raise ValueError('Job description too short to draft a tailored application')
    score, reasons, blockers = score_job(job, candidate, db.cv_text())
    analysis = {'method': 'local', 'match_score': score, 'reasons': reasons,
                'gaps_to_review': blockers, 'warning': 'Human review required.'}
    generator = 'template'
    if enabled('BEDROCK_ENABLED'):
        from .ai import draft_with_bedrock
        draft = draft_with_bedrock(job, candidate, db.cv_text())
        body = draft['body'].strip()
        full_name, email = candidate.get('name', '').strip(), candidate.get('email', '').strip()
        if not full_name or not email:
            raise ValueError('Verify name and email in CV before preparing a letter')
        text = f'Dear {job["company"]} Hiring Team,\n\n{body}\n\nKind regards,\n{full_name}\n{email}'
        analysis.update(draft['analysis'])
        generator = 'bedrock'
    else:
        text = cover_letter(job, candidate, db.cv_text())
    db.upsert_application(job_id, 'prepared', cover_letter=text,
                          generator=generator, analysis=analysis)
    return {'job_id': job_id, 'status': 'prepared', 'cover_letter': text,
            'generator': generator, 'analysis': analysis}


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
        if enabled('BEDROCK_ENABLED') or app.get('generator') == 'bedrock':
            raise ValueError('AI-drafted letters require individual review and manual sending')
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
    if not enabled('AUTO_APPLY_ENABLED') or enabled('BEDROCK_ENABLED'):
        # No unattended AI-generated submissions. Review each Bedrock draft.
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
