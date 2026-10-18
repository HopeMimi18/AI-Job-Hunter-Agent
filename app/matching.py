"""Explainable skill matching and grounded project evidence (not hiring probabilities)."""
import re
from .cv import SKILL_PHRASES

RELEVANT_TITLE = ('developer', 'engineer', 'cloud', 'backend', 'software', 'python', 'java', 'devops', 'intern')
ENTRY_LEVEL = ('junior', 'graduate', 'intern', 'trainee', 'entry level', 'entry-level', 'associate')


def _skill_mentions(text: str) -> set[str]:
    lowered = text.lower()
    return {skill for skill in SKILL_PHRASES
            if re.search(r'(?<![a-z0-9])' + re.escape(skill) + r'(?![a-z0-9])', lowered)}


def select_project_evidence(cv_text: str, job: dict, limit: int = 2) -> list[dict]:
    """Pick quoted CV project bullets relevant to a vacancy; never invent project details."""
    if not cv_text:
        return []
    lines = [re.sub(r'\s+', ' ', s).strip() for s in cv_text.splitlines()]
    in_projects = False
    projects = []
    current = None
    for line in lines:
        if not line:
            continue
        if re.search(r'\b(SELECTED|ACADEMIC|PERSONAL) PROJECTS\b', line, re.I):
            in_projects = True
            continue
        if not in_projects:
            continue
        if re.match(r'^(?:EXPERIENCE|EDUCATION|SKILLS|CERTIFICATIONS|REFERENCES|AWARDS)\b', line, re.I) and line.upper() == line:
            break
        bullet = re.match(r'^[•●▪*]\s*(.+)$', line)
        if bullet and current is not None:
            current['bullets'].append(bullet.group(1))
        elif current and current['bullets'] and not (' | ' in line or ' — ' in line or ' – ' in line):
            # CV bullet may wrap onto an additional physical line.
            current['bullets'][-1] += ' ' + line
        elif (' | ' in line or ' — ' in line or ' – ' in line) and len(line) >= 13:
            current = {'title': re.split(r'\s+[|—–]\s+', line, maxsplit=1)[0].strip(),
                       'bullets': [], 'heading': line}
            projects.append(current)
    job_terms = _skill_mentions(job.get('title', '') + ' ' + job.get('description', ''))
    words = set(re.findall(r'[a-z]{4,}', job.get('title', '').lower()))
    ranked = []
    for project in projects:
        if not project['bullets']:
            continue
        content = project['heading'] + ' ' + ' '.join(project['bullets'])
        skill_hits = _skill_mentions(content) & job_terms
        title_hits = words & set(re.findall(r'[a-z]{4,}', content.lower()))
        relevance = 3 * len(skill_hits) + len(title_hits)
        if relevance <= 0:
            continue
        # Excerpt is the candidate's own text, not AI-generated claims.
        evidence = project['bullets'][0].strip().rstrip('.')
        ranked.append((relevance, {'title': project['title'], 'cv_quote': evidence[:350],
                                   'matching_skills': sorted(skill_hits)}))
    ranked.sort(key=lambda x: x[0], reverse=True)
    return [item for _, item in ranked[:limit]]


def score_job(job: dict, profile: dict, cv_text: str = '') -> tuple[int, list[str], list[str]]:
    title = (job.get('title') or '').lower()
    desc = (job.get('description') or '').lower()
    loc = (job.get('location') or '').lower()
    requested = _skill_mentions(title + ' ' + desc)
    candidate = {s.lower() for s in (profile.get('skills') or [])}
    matching = sorted(requested & candidate)
    missing = sorted(requested - candidate)
    reasons, blockers = [], []
    score = 10
    if any(x in title for x in RELEVANT_TITLE):
        score += 24
        reasons.append('Relevant technical role')
    if any(x in title for x in ENTRY_LEVEL):
        score += 19
        reasons.append('Entry-level role')
    if requested:
        score += round(40 * len(matching) / len(requested))
    if matching:
        reasons.append('Verified CV skills: ' + ', '.join(matching[:8]))
    if missing:
        reasons.append('Skills not detected in CV (verify): ' + ', '.join(missing[:6]))
    if any(x in loc for x in ('south africa', 'gauteng', 'johannesburg', 'remote')):
        score += 7
    projects = select_project_evidence(cv_text, job, limit=1)
    if projects:
        reasons.append('Relevant CV project: ' + projects[0]['title'])
    # Human checks are intentionally independent of the numerical score.
    if re.search(r'\b(senior|principal|staff engineer|tech lead|lead developer)\b', title):
        blockers.append('Senior role requires human review')
    if re.search(r'\b\d{1,2}(?:\+|\s*[-–]\s*\d{1,2})?\s*(?:years|yrs)\s+(?:of\s+)?experience\b', desc):
        blockers.append('Experience requirement needs manual verification')
    if (re.search(r'\b(?:bachelor(?:\'s|s)?|bsc|university)\s+(?:degree\s+)?(?:is\s+)?(?:required|mandatory|essential)\b', desc)
            or re.search(r'\b(?:required|must have|mandatory)\b.{0,65}\b(?:bachelor(?:\'s|s)?|bsc|university degree)\b', desc)):
        if profile.get('education_in_progress'):
            blockers.append('Completed university degree may be required; CV lists study in progress')
        else:
            blockers.append('Mandatory degree requirement needs manual verification')
    if not desc.strip():
        blockers.append('Job description missing; cannot verify requirements')
    if not requested:
        blockers.append('No explicit technical skills found; review manually')
    if not any(x in title for x in RELEVANT_TITLE):
        blockers.append('Job title outside configured role families')
    return min(100, max(0, score)), reasons, blockers
