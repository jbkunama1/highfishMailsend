import hmac
import json
import os
import secrets
import time
from pathlib import Path
from starlette.applications import Starlette
from starlette.responses import HTMLResponse, JSONResponse
from starlette.routing import Route
import app as mail
START = time.monotonic()
DRAFTS = {}
TELEGRAM = {'state': 'disabled'}

def status():
    return {'project': 'highfishMailsend', 'uptime_seconds': int(time.monotonic() - START), 'dry_run': mail.DRY, 'transport': mail.MODE, 'startup_transport': mail.INITIAL_MODE, 'default_scope': 'global until restart; existing drafts unchanged', 'from': mail.FROM, 'sender_domain': mail.SENDER_DOMAIN, 'default_to': '', 'mail_to_placeholder': mail.TO, 'recipient_required': True, 'allowed_to': sorted(mail.ALLOWED), 'smtp_host': mail.HOST, 'smtp_port': mail.PORT, 'smtp_username_configured': bool(os.getenv('SMTP_USERNAME')), 'smtp_password_configured': bool(os.getenv('SMTP_PASSWORD')), 'api_token_configured': bool(os.getenv('MAILERSEND_API_TOKEN')), 'cyberpanel_key_configured': bool(os.getenv('CYBERPANEL_API_KEY')), 'telegram': dict(TELEGRAM)}

def draft(subject, text, to='', sender='', transport=''):
    if not all(isinstance(x, str) for x in (subject, text, to, sender, transport)):
        raise ValueError('Textfelder erforderlich')
    recipient = mail.resolve_recipient(to)
    mail.resolve_sender(sender)
    selected = mail.select_transport(transport)
    if not mail.DRY and any(not os.getenv(key) for key in mail.CREDENTIALS[selected]):
        raise ValueError('Zugangsdaten fehlen')
    if not subject.strip() or len(subject) > 200 or '\r' in subject or '\n' in subject or not text.strip() or len(text) > 100000:
        raise ValueError('Empfaenger, Betreff oder Text ungueltig')
    return {'subject': subject, 'text': text, 'to': recipient, 'sender': sender, 'transport': selected}

async def page(request):
    return HTMLResponse(Path(__file__).with_name('admin.html').read_text(), headers={'Cache-Control': 'no-store', 'X-Frame-Options': 'DENY', 'Content-Security-Policy': "default-src 'self'; script-src 'unsafe-inline'; style-src 'unsafe-inline'; connect-src 'self'; frame-ancestors 'none'; base-uri 'none'; form-action 'none'"})

async def api(request):
    if not hmac.compare_digest(request.headers.get('authorization', '').encode(), ('Bearer ' + mail.TOKEN).encode()):
        return JSONResponse({'error': 'Nicht autorisiert'}, status_code=401, headers={'Cache-Control': 'no-store', 'WWW-Authenticate': 'Bearer'})
    headers = {'Cache-Control': 'no-store'}
    if request.method == 'GET':
        return JSONResponse(status(), headers=headers)
    if request.headers.get('content-type', '').split(';')[0] != 'application/json':
        return JSONResponse({'error': 'JSON erforderlich'}, status_code=415, headers=headers)
    body = bytearray()
    async for chunk in request.stream():
        body.extend(chunk)
        if len(body) > 500000:
            return JSONResponse({'error': 'Anfrage zu gross'}, status_code=413, headers=headers)
    try:
        data = json.loads(body)
        if not isinstance(data, dict):
            raise ValueError('JSON-Objekt erforderlich')
        action = request.path_params['action']
        if action == 'dryrun':
            mail.DRY = True
            DRAFTS.clear()
            return JSONResponse(status(), headers=headers)
        if action == 'default':
            if data.get('confirm') is not True or not isinstance(data.get('transport'), str):
                raise ValueError('Bestaetigung erforderlich')
            mail.set_default_transport(data['transport'])
            return JSONResponse(status(), headers=headers)
        if action == 'preview':
            item = draft(data.get('subject', ''), data.get('text', ''), data.get('to', ''), data.get('sender', ''), data.get('transport', ''))
            now = time.monotonic()
            for key in list(DRAFTS):
                if DRAFTS[key][0] < now:
                    del DRAFTS[key]
            if len(DRAFTS) >= 100:
                return JSONResponse({'error': 'Zu viele offene Entwuerfe'}, status_code=429, headers=headers)
            key = secrets.token_urlsafe(24)
            DRAFTS[key] = (now + 600, item, mail.DRY)
            return JSONResponse({'id': key, 'dry_run': mail.DRY, 'from': mail.resolve_sender(item['sender']), **item}, headers=headers)
        if action == 'send':
            key = data.get('id', '')
            if not isinstance(key, str):
                raise ValueError('Ungueltiger Entwurf')
            item = DRAFTS.pop(key, None)
            if not item or item[0] < time.monotonic() or item[2] != mail.DRY:
                raise ValueError('Entwurf abgelaufen oder Testmodus geaendert')
            return JSONResponse(await mail.send_mail(**item[1]), headers=headers)
        raise ValueError('Unbekannte Aktion')
    except (ValueError, TypeError):
        return JSONResponse({'error': 'Ungueltige Eingabe, fehlende Zugangsdaten oder abgelaufener Entwurf'}, status_code=400, headers=headers)
application = Starlette(routes=[Route('/', page), Route('/api/status', api), Route('/api/{action}', api, methods=['POST'])])
