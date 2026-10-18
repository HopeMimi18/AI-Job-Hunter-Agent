"""Schedule with Windows Task Scheduler initially; later deploy to AWS."""
import json
import os
from app import db
from app.sources import discover
from app.workflow import ingest, autopilot
from app.mailer import send_digest


def main():
    db.init_db()
    if not db.profile():
        raise SystemExit('Upload your CV via dashboard before scheduling this task.')
    vacancies, warnings = discover()
    ingest(vacancies)
    applications = autopilot()
    digest_status = 'not configured'
    if os.getenv('NOTIFY_EMAIL'):
        try:
            send_digest(os.environ['NOTIFY_EMAIL'], db.jobs(10), applications)
            digest_status = 'accepted by SMTP'
        except Exception as exc:
            digest_status = f'failed: {exc}'
    print(json.dumps({'discovered': len(vacancies), 'applications': applications,
                      'digest': digest_status, 'warnings': warnings}, indent=2))


if __name__ == '__main__':
    main()
