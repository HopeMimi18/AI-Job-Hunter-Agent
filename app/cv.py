"""Parse resume locally. No profile data leaves the computer here."""
from pathlib import Path
import re
from docx import Document
from pypdf import PdfReader

SKILL_PHRASES = (
    'python', 'java', 'javascript', 'c#', 'sql', 'aws', 'amazon bedrock', 'bedrock agentcore',
    'amazon s3', 'docker', 'github', 'git', 'maven', 'junit', 'jdbc', 'fastapi', 'linux',
    'rest api', 'http', 'json', 'tcp sockets', 'unit testing', 'google cloud',
    'gemini', 'react', 'html', 'css', 'typescript', 'postgresql', 'api testing',
)


def read_cv(path: Path) -> str:
    suffix = path.suffix.lower()
    if suffix == '.pdf':
        text = '\n'.join(page.extract_text() or '' for page in PdfReader(str(path)).pages)
    elif suffix == '.docx':
        text = '\n'.join(p.text for p in Document(str(path)).paragraphs)
    else:
        raise ValueError('Only PDF and DOCX are supported')
    if len(text.strip()) < 80:
        raise ValueError('CV contains too little extractable text. Scanned PDFs require OCR.')
    return text


def extract_profile(text: str) -> dict:
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    name_line = next((s for s in lines[:10] if re.fullmatch(r'[A-Za-z]+(?:[ -][A-Za-z]+){1,3}', s)), '')
    email_match = re.search(r'[\w.+-]+@[\w.-]+\.[A-Za-z]{2,}', text)
    phone_match = re.search(r'(?<!\d)(?:\+27\s?\d{2}|0\d{2})[\s-]?\d{3}[\s-]?\d{4}(?!\d)', text)
    lowered = text.lower()
    skills = [skill for skill in SKILL_PHRASES if re.search(r'(?<![a-z0-9])' + re.escape(skill) + r'(?![a-z0-9])', lowered)]
    # Handle common plural and combined API wording without inventing experience.
    if re.search(r'\brest\s+apis?\b|\bhttp\s*/\s*rest\s+apis?\b', lowered) and 'rest api' not in skills:
        skills.append('rest api')
    return {
        'name': name_line.title() if name_line else '',
        'email': email_match.group(0) if email_match else '',
        'phone': phone_match.group(0) if phone_match else '',
        'skills': skills,
        'education_in_progress': bool(re.search(r'(in progress|expected completion|currently studying)', lowered)),
        'cv_excerpt': text[:1600],
        'preferred_roles': ['junior software developer', 'junior python developer', 'junior java developer',
                            'cloud support', 'cloud intern', 'software engineering intern'],
    }
