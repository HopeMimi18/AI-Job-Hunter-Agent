"""Environment-driven settings. Never put credentials or the real CV in the repository."""
import os
from pathlib import Path
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[1]
load_dotenv(ROOT / '.env')
RUNTIME = (ROOT / os.getenv('RUNTIME_DIR', 'runtime')).resolve()
RUNTIME.mkdir(parents=True, exist_ok=True)
DB_PATH = RUNTIME / 'job_hunter.sqlite3'
TOKEN = os.getenv('JOB_HUNTER_ADMIN_TOKEN', '').strip()


def enabled(name: str, default: str = 'false') -> bool:
    return os.getenv(name, default).lower() in ('1', 'true', 'yes', 'on')


def csv_env(name: str) -> list[str]:
    return [x.strip() for x in os.getenv(name, '').split(',') if x.strip()]


def application_allowlist() -> set[str]:
    return {x.lower() for x in csv_env('APPROVED_APPLICATION_EMAILS')}
