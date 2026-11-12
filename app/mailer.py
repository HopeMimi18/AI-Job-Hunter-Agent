"""SMTP notifications and employer-email submissions."""
import os
import smtplib
import ssl
from email.message import EmailMessage
from pathlib import Path


def smtp_send(message: EmailMessage):
    host = os.getenv('SMTP_HOST', '').strip()
    username = os.getenv('SMTP_USERNAME', '').strip()
    password = os.getenv('SMTP_PASSWORD', '').strip()
    sender = os.getenv('SMTP_FROM', '').strip()
    if not all((host, username, password, sender)):
        raise RuntimeError('SMTP configuration is incomplete. Nothing has been sent.')
    port = int(os.getenv('SMTP_PORT', '587'))
    message['From'] = sender
    if port == 465:
        with smtplib.SMTP_SSL(host, port, timeout=20, context=ssl.create_default_context()) as smtp:
            smtp.login(username, password)
            smtp.send_message(message)
    elif port == 587:
        with smtplib.SMTP(host, port, timeout=20) as smtp:
            smtp.starttls(context=ssl.create_default_context())
            smtp.login(username, password)
            smtp.send_message(message)
    else:
        raise RuntimeError('Only TLS SMTP ports 465 and 587 are supported')


def send_application_email(job: dict, profile: dict, cover_letter: str):
    recipient = job['apply_email']
    msg = EmailMessage()
    msg['To'] = recipient
    msg['Reply-To'] = profile['email']
    msg['Subject'] = f'Application: {job["title"]} — {profile["name"]}'
    msg.set_content(f'{cover_letter}\n\nApplicant: {profile["name"]}\nEmail: {profile["email"]}\n')
    cv_path = Path(profile['resume_path'])
    if not cv_path.is_file():
        raise RuntimeError('Resume file missing; cannot submit')
    media = 'application/pdf' if cv_path.suffix.lower() == '.pdf' else 'application/vnd.openxmlformats-officedocument.wordprocessingml.document'
    major, minor = media.split('/')
    msg.add_attachment(cv_path.read_bytes(), maintype=major, subtype=minor,
                       filename='Applicant_Resume' + cv_path.suffix.lower())
    smtp_send(msg)


def send_digest(email: str, jobs: list[dict], outcome: list[dict]):
    if not email:
        raise RuntimeError('NOTIFY_EMAIL has not been configured')
    msg = EmailMessage()
    msg['To'] = email
    msg['Subject'] = 'AI Job Hunter — job matches and application report'
    lines = ['Your latest jobs, bursaries, apprenticeships and other opportunities:', '']
    for job in jobs[:15]:
        lines += [f'{job["score"]}/100  [{job.get("opportunity_type", "job").replace("_", " " ).title()}] {job["title"]} — {job["company"]}',
                  f'Location: {job.get("location", "")}',
                  f'View announcement: {job.get("url", "")}', 'Verify eligibility and deadline with the original provider.', '']
    lines += ['Applications attempted (email transport confirmation only):']
    for result in outcome:
        lines.append(f'{result["job_id"]}: {result["status"]}')
    if not outcome:
        lines.append('None; no eligible authorised email jobs found or autopilot disabled.')
    msg.set_content('\n'.join(lines))
    smtp_send(msg)


def digest_selection(jobs: list[dict], limit: int = 12) -> list[dict]:
    """Include bursaries and work-based learning alongside highest-fit jobs."""
    allocations = {'job': 4, 'internship': 2, 'bursary': 2,
                   'learnership': 1, 'apprenticeship': 1,
                   'graduate_programme': 1, 'training': 1}
    selected = []
    identifiers = set()
    for kind, cap in allocations.items():
        candidates = [x for x in jobs if x.get('opportunity_type', 'job') == kind]
        for job in candidates[:cap]:
            if job['id'] not in identifiers:
                selected.append(job)
                identifiers.add(job['id'])
    for job in jobs:
        if len(selected) >= limit:
            break
        if job['id'] not in identifiers:
            selected.append(job)
            identifiers.add(job['id'])
    return selected[:limit]
