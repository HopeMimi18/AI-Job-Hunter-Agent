"""Documented, public job-listing API integrations; no LinkedIn scraping."""
import os
import hashlib
import re
import html
import httpx
from .config import csv_env

QUERIES = ('junior python developer', 'junior java developer',
           'junior software developer', 'cloud support intern')


def make_id(source: str, source_id: str) -> str:
    return hashlib.sha256(f'{source}:{source_id}'.encode()).hexdigest()[:22]


def plain(markup: str) -> str:
    cleaned = re.sub(r'<[^>]*>', ' ', markup or '')
    return re.sub(r'\s+', ' ', html.unescape(cleaned)).strip()


def fetch_adzuna(client: httpx.Client) -> list[dict]:
    app_id, key = os.getenv('ADZUNA_APP_ID'), os.getenv('ADZUNA_APP_KEY')
    if not app_id or not key:
        return []
    country = os.getenv('ADZUNA_COUNTRY', 'za').lower()
    results = {}
    for query in QUERIES:
        r = client.get(f'https://api.adzuna.com/v1/api/jobs/{country}/search/1',
                       params={'app_id': app_id, 'app_key': key, 'what': query,
                               'results_per_page': 20, 'content-type': 'application/json'})
        r.raise_for_status()
        for item in r.json().get('results', []):
            job_id = str(item['id'])
            results[job_id] = {
                'id': make_id('adzuna', job_id), 'title': item.get('title', 'Untitled'),
                'company': (item.get('company') or {}).get('display_name', 'Unknown'),
                'location': (item.get('location') or {}).get('display_name', ''),
                'description': plain(item.get('description', '')),
                'url': item.get('redirect_url', ''), 'source': 'adzuna',
                'apply_method': 'website', 'email_submission_allowed': False,
            }
    return list(results.values())


def fetch_greenhouse(client: httpx.Client) -> list[dict]:
    found = []
    for token in csv_env('GREENHOUSE_BOARDS'):
        if not re.fullmatch(r'[a-zA-Z0-9_-]+', token):
            raise ValueError('Invalid Greenhouse board token')
        r = client.get(f'https://boards-api.greenhouse.io/v1/boards/{token}/jobs',
                       params={'content': 'true'})
        r.raise_for_status()
        for job in r.json().get('jobs', []):
            found.append({'id': make_id('greenhouse', f'{token}:{job["id"]}'),
                 'title': job.get('title', 'Untitled'), 'company': token,
                 'location': (job.get('location') or {}).get('name', ''),
                 'description': plain(job.get('content', '')),
                 'url': job.get('absolute_url', ''), 'source': 'greenhouse',
                 'apply_method': 'website', 'email_submission_allowed': False})
    return found


def fetch_lever(client: httpx.Client) -> list[dict]:
    found = []
    for site in csv_env('LEVER_SITES'):
        if not re.fullmatch(r'[a-zA-Z0-9_-]+', site):
            raise ValueError('Invalid Lever site identifier')
        r = client.get(f'https://api.lever.co/v0/postings/{site}', params={'mode': 'json'})
        r.raise_for_status()
        for job in r.json():
            categories = job.get('categories') or {}
            descriptions = [str(x.get('content', '')) for x in job.get('lists', [])]
            descriptions += [job.get('descriptionPlain') or plain(job.get('description', ''))]
            found.append({'id': make_id('lever', f'{site}:{job["id"]}'),
                'title': job.get('text', 'Untitled'), 'company': site,
                'location': categories.get('location', ''),
                'description': plain(' '.join(descriptions)),
                'url': job.get('hostedUrl') or job.get('applyUrl', ''), 'source': 'lever',
                'apply_method': 'website', 'email_submission_allowed': False})
    return found


def discover() -> tuple[list[dict], list[str]]:
    collected = {}
    warnings = []
    with httpx.Client(timeout=15, follow_redirects=True, headers={'Accept': 'application/json'}) as client:
        for name, collector in [('Adzuna', fetch_adzuna),
                                ('Greenhouse', fetch_greenhouse), ('Lever', fetch_lever)]:
            try:
                for job in collector(client):
                    collected[job['id']] = job
            except (ValueError, KeyError, httpx.HTTPError) as exc:
                warnings.append(f'{name}: {type(exc).__name__} — {str(exc)[:150]}')
    if not collected and not warnings:
        warnings.append('No job providers configured. Add Adzuna credentials or Greenhouse/Lever sites in .env.')
    return list(collected.values()), warnings
