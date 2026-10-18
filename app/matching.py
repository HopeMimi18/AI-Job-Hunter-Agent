"""Transparent early-stage matching. The score is NOT a hiring probability."""
import re
from .cv import SKILL_PHRASES

RELEVANT_TITLE = ('developer', 'engineer', 'cloud', 'backend', 'software', 'python', 'java', 'devops', 'intern')
ENTRY_LEVEL = ('junior', 'graduate', 'intern', 'trainee', 'entry level', 'entry-level', 'associate')


def score_job(job: dict, profile: dict) -> tuple[int, list[str], list[str]]:
    title = (job.get('title') or '').lower()
    desc = (job.get('description') or '').lower()
    loc = (job.get('location') or '').lower()
    text = f'{title} {desc}'
    candidate = set(profile.get('skills') or [])
    required_skills = {s for s in SKILL_PHRASES if re.search(r'(?<![a-z0-9])' + re.escape(s) + r'(?![a-z0-9])', text)}
    matching = sorted(required_skills & candidate)
    missing = sorted(required_skills - candidate)
    reasons = []
    blockers = []
    score = 10
    if any(x in title for x in RELEVANT_TITLE):
        score += 24
        reasons.append('Relevant technical role')
    if any(x in title for x in ENTRY_LEVEL):
        score += 19
        reasons.append('Entry-level role')
    if required_skills:
        score += round(40 * (len(matching) / len(required_skills)))
    if matching:
        reasons.append('CV evidence: ' + ', '.join(matching[:8]))
    if missing:
        reasons.append('Skills to verify: ' + ', '.join(missing[:6]))
    if 'south africa' in loc or 'gauteng' in loc or 'johannesburg' in loc or 'remote' in loc:
        score += 7
    # Conservative review flags, not automatic judgments of qualification.
    if re.search(r'\b(senior|principal|staff engineer|tech lead|lead developer)\b', title):
        blockers.append('Senior role requires human review')
    if re.search(r'\b\d{1,2}(?:\+|\s*-\s*\d{1,2})?\s*(?:years|yrs)\s+(?:of\s+)?experience\b', desc):
        blockers.append('Experience requirement needs manual verification')
    if re.search(r'\b(?:bachelor.?s? degree|bsc degree|university degree)\s+(?:is\s+)?(?:required|mandatory|essential)\b', desc):
        blockers.append('Completed degree appears mandatory; verify eligibility')
    if not desc.strip():
        blockers.append('Job description missing; cannot verify requirements')
    if not required_skills:
        blockers.append('No explicit technical skills found; review manually')
    if not any(x in title for x in RELEVANT_TITLE):
        blockers.append('Job title outside configured role families')
    return min(100, max(0, score)), reasons, blockers
