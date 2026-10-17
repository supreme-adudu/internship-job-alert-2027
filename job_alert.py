"""Internship alert MVP: public feeds + optional official ATS boards."""
import hashlib
import html
import json
import os
import re
import smtplib
import sqlite3
import sys
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from email.message import EmailMessage
from pathlib import Path

ROOT = Path(__file__).resolve().parent
CONFIG = json.loads((ROOT / 'config.json').read_text(encoding='utf-8'))
DB = Path(os.environ.get('JOB_ALERT_DB', str(ROOT / 'seen_jobs.sqlite3')))
HEADERS = {'User-Agent': 'InternshipJobAlert/1.0 (personal educational project)', 'Accept': 'application/json'}


def get_json(url):
    req = urllib.request.Request(url, headers=HEADERS)
    with urllib.request.urlopen(req, timeout=25) as response:
        return json.load(response)


def clean(value):
    return re.sub(r'\s+', ' ', html.unescape(re.sub(r'<[^>]+>', ' ', str(value or '')))).strip()


def normalize(company, title, location, url, description='', source=''):
    if not url:
        return None
    return {'company': clean(company), 'title': clean(title), 'location': clean(location),
            'url': str(url), 'description': clean(description)[:5000], 'source': source}


def arbeitnow():
    """Public jobs API; mostly European jobs, not exclusively internships."""
    jobs = []
    for page in (1, 2, 3):
        data = get_json(f'https://www.arbeitnow.com/api/job-board-api?page={page}')
        for x in data.get('data', []):
            job = normalize(x.get('company_name'), x.get('title'), x.get('location'),
                            x.get('url'), x.get('description'), 'Arbeitnow')
            if job:
                jobs.append(job)
        if not data.get('links', {}).get('next'):
            break
    return jobs


def remotive():
    """Public remote-jobs API; remote listings may not be eligible for internships."""
    jobs = []
    data = get_json('https://remotive.com/api/remote-jobs?limit=1000')
    for x in data.get('jobs', []):
        job = normalize(x.get('company_name'), x.get('title'), x.get('candidate_required_location'),
                        x.get('url'), x.get('description'), 'Remotive')
        if job:
            jobs.append(job)
    return jobs


def greenhouse(board):
    jobs = []
    slug = urllib.parse.quote(board, safe='')
    data = get_json(f'https://boards-api.greenhouse.io/v1/boards/{slug}/jobs?content=true')
    for x in data.get('jobs', []):
        job = normalize(board, x.get('title'), (x.get('location') or {}).get('name'),
                        x.get('absolute_url'), x.get('content'), 'Greenhouse')
        if job:
            jobs.append(job)
    return jobs


def lever(site):
    jobs = []
    slug = urllib.parse.quote(site, safe='')
    for x in get_json(f'https://api.lever.co/v0/postings/{slug}?mode=json'):
        job = normalize(site, x.get('text'), (x.get('categories') or {}).get('location'),
                        x.get('hostedUrl'), x.get('descriptionPlain', ''), 'Lever')
        if job:
            jobs.append(job)
    return jobs


def score(job):
    title = job['title'].lower()
    body = (job['title'] + ' ' + job['description']).lower()
    location = job['location'].lower()
    company = job['company'].lower()
    # Require internship in title, to avoid sending full-time jobs mentioning internships in the description.
    if not any(term in title for term in CONFIG['internship_terms']):
        return -100, []
    if any(term in title for term in CONFIG['exclude_terms']):
        return -100, []
    if re.search(r'\b(bac\s*\+\s*5|master\s*2|m2 required)\b', body):
        return -100, []
    company_match = any(c.lower() in company for c in CONFIG['companies'])
    if CONFIG['only_watchlisted_companies'] and not company_match:
        return -100, []
    matched = [s for s in CONFIG['skills'] if s in body]
    location_match = any(l in location for l in CONFIG['locations'])
    # Locations can be unspecified or remote, so don't discard those automatically.
    points = 3 + min(len(matched), 4) + (3 if company_match else 0) + (1 if location_match else 0)
    if '2027' in body and ('june' in body or 'juin' in body):
        points += 2
    if '3 mois' in body or '3 months' in body:
        points += 2
    return points, matched


def db_connect():
    DB.parent.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(DB)
    con.execute('CREATE TABLE IF NOT EXISTS seen (id TEXT PRIMARY KEY, first_seen TEXT NOT NULL)')
    return con


def job_id(job):
    # URL is the stable identity; normalize tracking parameters.
    p = urllib.parse.urlsplit(job['url'])
    canonical = urllib.parse.urlunsplit((p.scheme, p.netloc.lower(), p.path.rstrip('/'), '', ''))
    return hashlib.sha256(canonical.encode()).hexdigest()


def send_email(jobs):
    host = os.environ.get('SMTP_HOST')
    user = os.environ.get('SMTP_USER')
    password = os.environ.get('SMTP_PASSWORD')
    recipient = os.environ.get('ALERT_TO')
    if not all((host, user, password, recipient)):
        print('SMTP not configured. Matching new jobs are printed only.')
        return False
    msg = EmailMessage()
    msg['Subject'] = f'Internship Job Alert: {len(jobs)} new match(es)'
    msg['From'] = os.environ.get('ALERT_FROM', user)
    msg['To'] = recipient
    lines = ['New internship listings (verify degree, duration, dates and work authorization):', '']
    for j in jobs:
        lines += [f"[{j['score']}] {j['title']} — {j['company']}",
                  f"Location: {j['location'] or 'not stated'} | Source: {j['source']}",
                  f"Skills: {', '.join(j['matched_skills']) or 'not specified'}", j['url'], '']
    msg.set_content('\n'.join(lines))
    with smtplib.SMTP_SSL(host, int(os.environ.get('SMTP_PORT', '465')), timeout=30) as smtp:
        smtp.login(user, password)
        smtp.send_message(msg)
    return True


def send_telegram(jobs):
    """Send compact push messages through Telegram Bot API; raise on failure."""
    token = os.environ.get('TELEGRAM_BOT_TOKEN')
    chat_id = os.environ.get('TELEGRAM_CHAT_ID')
    if not token or not chat_id:
        print('Telegram not configured; matching jobs printed only.')
        return False
    endpoint = f'https://api.telegram.org/bot{token}/sendMessage'
    for job in jobs:
        title = job['title'][:150]
        message = (f"🔔 NEW INTERNSHIP\n"
                   f"🏢 {job['company']}\n"
                   f"💻 {title}\n"
                   f"📍 {job['location'] or 'Not specified'}\n"
                   f"⭐ Match score: {job['score']} (heuristic, not %)\n"
                   f"🔗 {job['url']}\n\n"
                   f"Check degree, dates, duration and work authorization manually.")
        payload = urllib.parse.urlencode({'chat_id': chat_id, 'text': message,
                                          'disable_web_page_preview': 'true'}).encode()
        request = urllib.request.Request(endpoint, data=payload, method='POST')
        with urllib.request.urlopen(request, timeout=25) as response:
            result = json.load(response)
            if not result.get('ok'):
                raise RuntimeError('Telegram rejected the message')
    return True


def main():
    collected = []
    sources = [('Arbeitnow', arbeitnow), ('Remotive', remotive)]
    sources += [(f'Greenhouse:{board}', lambda b=board: greenhouse(b)) for board in CONFIG['greenhouse_boards']]
    sources += [(f'Lever:{site}', lambda s=site: lever(s)) for site in CONFIG['lever_sites']]
    successes = 0
    for name, fetch in sources:
        try:
            batch = fetch()
            collected.extend(batch)
            successes += 1
            print(f'{name}: {len(batch)} listings')
        except Exception as exc:
            print(f'WARNING {name}: {exc}', file=sys.stderr)
    if not successes:
        print('All sources failed; nothing marked as seen.', file=sys.stderr)
        sys.exit(1)
    unique = {job_id(j): j for j in collected}
    con = db_connect()
    selected = []
    for jid, job in unique.items():
        points, skills = score(job)
        if points < CONFIG['minimum_score']:
            continue
        if con.execute('SELECT 1 FROM seen WHERE id=?', (jid,)).fetchone():
            continue
        job['score'], job['matched_skills'] = points, skills
        selected.append((jid, job))
    selected.sort(key=lambda pair: pair[1]['score'], reverse=True)
    selected = selected[:50]  # avoid unbounded email length
    jobs = [job for _, job in selected]
    for job in jobs:
        print(f"[{job['score']}] {job['company']} | {job['title']} | {job['location']} | {job['url']}")
    if jobs:
        telegram_configured = bool(os.environ.get('TELEGRAM_BOT_TOKEN') and os.environ.get('TELEGRAM_CHAT_ID'))
        smtp_configured = all(os.environ.get(k) for k in ('SMTP_HOST', 'SMTP_USER', 'SMTP_PASSWORD', 'ALERT_TO'))
        if telegram_configured:
            delivered = send_telegram(jobs)
        elif smtp_configured:
            delivered = send_email(jobs)
        else:
            print('No notification channel configured; results printed only.')
            delivered = False
        # Do not mark messages as seen if a configured channel fails.
        if delivered or not (telegram_configured or smtp_configured):
            now = datetime.now(timezone.utc).isoformat()
            con.executemany('INSERT OR IGNORE INTO seen VALUES (?, ?)', [(jid, now) for jid, _ in selected])
            con.commit()
    else:
        print('No new matches.')
    con.close()


if __name__ == '__main__':
    main()
