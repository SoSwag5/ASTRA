"""Fictional English template shapes, never copied from private mail."""
import base64
import time

BODY_SENTINEL = 'fictional-body-only-8de044972ee947619430'
HTML_SENTINEL = 'fictional-html-only-a18f41c68e4a4d79ac15'
RAW_SENTINEL = 'fictional-response-only-fd7311e66f9045189b43'
AUTH_SENTINEL = 'fictional-auth-only-736c876432114b90a731'
PLATFORMS = ('greenhouse', 'lever', 'workday')
DOMAINS = {'greenhouse': 'greenhouse.io', 'lever': 'hire.lever.co', 'workday': 'myworkday.com'}
URLS = {'greenhouse': 'https://boards.greenhouse.io/example/jobs/123',
        'lever': 'https://jobs.lever.co/example/12345678-1234-1234-1234-123456789abc',
        'workday': 'https://example.myworkdayjobs.com/en-US/careers/job/123'}


def encoded(value):
    return base64.urlsafe_b64encode(value.encode()).decode().rstrip('=')


def message(platform='greenhouse', identifier='a1', timestamp=None):
    domain = DOMAINS[platform]
    body = ('Thanks' if platform == 'lever' else 'Thank you') + (
        ' for applying to the Security Analyst position at Example Robotics.\n'
        + BODY_SENTINEL + '\n' + URLS[platform])
    headers = [
        {'name': 'From', 'value': 'Fictional Recruiting <noreply@' + domain + '>'},
        {'name': 'Subject', 'value': 'Thank you for applying to Example Robotics'},
        {'name': 'Authentication-Results', 'value':
         f'mx.google.com; dkim=pass header.i=@{domain}; spf=pass smtp.mailfrom=noreply@{domain}; '
         f'dmarc=pass header.from={domain} ({AUTH_SENTINEL})'},
    ]
    return {'id': identifier, 'internalDate': str(int((timestamp or time.time()-60)*1000)),
            'snippet': RAW_SENTINEL, 'payload': {'mimeType': 'multipart/alternative',
            'headers': headers, 'parts': [
                {'mimeType': 'text/plain', 'body': {'data': encoded(body)}},
                {'mimeType': 'text/html', 'body': {'data': encoded('<p>'+HTML_SENTINEL+'</p>')}},
            ]}}
