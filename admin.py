import hmac
import json
import secrets
import time
from pathlib import Path
from starlette.applications import Starlette
from starlette.responses import HTMLResponse, JSONResponse
from starlette.routing import Route
import app as mail
import providers
import provider_delivery
START = time.monotonic()
DRAFTS = {}
TELEGRAM = {'state':'disabled'}

def status():
    import os
    listing = providers.listing(mail)
    return {'project':'highfishMailsend','uptime_seconds':int(time.monotonic()-START),
            'dry_run':mail.DRY,'transport':mail.MODE,'startup_transport':mail.INITIAL_MODE,
            'from':mail.FROM,'sender_domain':mail.SENDER_DOMAIN,'default_to':'','mail_to_placeholder':mail.TO,
            'recipient_required':True,'allowed_to':sorted(mail.ALLOWED),'telegram':dict(TELEGRAM),
            'smtp_host':mail.HOST,'smtp_port':mail.PORT,
            'smtp_username_configured':bool(os.getenv('SMTP_USERNAME')),
            'smtp_password_configured':bool(os.getenv('SMTP_PASSWORD')),
            'api_token_configured':bool(os.getenv('MAILERSEND_API_TOKEN')),
            'cyberpanel_key_configured':bool(os.getenv('CYBERPANEL_API_KEY')),
            'default_scope':'persistent provider default; legacy transport until restart',**listing}

def draft(subject,text,to='',sender='',transport='',provider=''):
    if not all(isinstance(x,str) for x in (subject,text,to,sender,transport,provider)):
        raise ValueError('Text required')
    recipient = mail.resolve_recipient(to)
    value = providers.select(mail,provider,transport)
    sender = sender or value['sender']
    mail.resolve_sender(sender)
    if not subject.strip() or len(subject)>200 or '\r' in subject or '\n' in subject or not text.strip() or len(text)>100000:
        raise ValueError('Invalid message')
    if not mail.DRY and (value['kind']=='smtp' and (not value['username'] or not value['password']) or value['kind']!='smtp' and not value['token']):
        raise ValueError('Missing credentials')
    return {'subject':subject,'text':text,'to':recipient,'sender':sender,'transport':value['kind'],
            'provider':value['id'],'provider_revision':provider_delivery.revision(value)}

async def page(request):
    return HTMLResponse(Path(__file__).with_name('admin.html').read_text(),headers={
        'Cache-Control':'no-store','X-Frame-Options':'DENY',
        'Content-Security-Policy':"default-src 'self'; script-src 'unsafe-inline'; style-src 'unsafe-inline'; connect-src 'self'; frame-ancestors 'none'; base-uri 'none'; form-action 'none'"})

async def api(request):
    headers={'Cache-Control':'no-store'}
    if not hmac.compare_digest(request.headers.get('authorization','').encode(),('Bearer '+mail.TOKEN).encode()):
        return JSONResponse({'error':'Nicht autorisiert'},status_code=401,headers={**headers,'WWW-Authenticate':'Bearer'})
    action = request.path_params.get('action','status')
    if request.method=='GET':
        return JSONResponse(status(),headers=headers)
    if request.headers.get('content-type','').split(';')[0]!='application/json':
        return JSONResponse({'error':'JSON erforderlich'},status_code=415,headers=headers)
    body=bytearray()
    async for chunk in request.stream():
        body.extend(chunk)
        if len(body)>500000:
            return JSONResponse({'error':'Anfrage zu groß'},status_code=413,headers=headers)
    try:
        data=json.loads(body)
        if not isinstance(data,dict):
            raise ValueError('Object required')
        if action=='provider-save':
            result=providers.storage().save(data)
            DRAFTS.clear()
            return JSONResponse(result,headers=headers)
        if action=='provider-check':
            if data.get('confirm') is not True:
                raise ValueError('Confirmation required')
            value=providers.select(mail,data.get('id',''))
            return JSONResponse(await provider_delivery.check(value),headers=headers)
        if action=='default':
            if data.get('confirm') is not True:
                raise ValueError('Confirmation required')
            if 'provider' in data:
                value=providers.select(mail,data['provider'])
                providers.storage().set_default(value['id'])
            else:
                mail.set_default_transport(data.get('transport',''))
                if providers.listing(mail)['writable']:
                    providers.storage().set_default('env:'+mail.MODE)
            return JSONResponse(status(),headers=headers)
        if action=='dryrun':
            mail.DRY=True
            DRAFTS.clear()
            return JSONResponse(status(),headers=headers)
        if action=='preview':
            item=draft(*(data.get(k,'') for k in ('subject','text','to','sender','transport','provider')))
            now=time.monotonic()
            for key in list(DRAFTS):
                if DRAFTS[key][0]<now:
                    del DRAFTS[key]
            if len(DRAFTS)>=100:
                return JSONResponse({'error':'Zu viele Entwürfe'},status_code=429,headers=headers)
            key=secrets.token_urlsafe(24)
            DRAFTS[key]=(now+600,item,mail.DRY)
            return JSONResponse({'id':key,'dry_run':mail.DRY,'from':mail.resolve_sender(item['sender']),**item},headers=headers)
        if action=='send':
            if not isinstance(data.get('id'),str):
                raise ValueError('Invalid id')
            item=DRAFTS.pop(data['id'],None)
            if not item or item[0]<time.monotonic() or item[2]!=mail.DRY:
                raise ValueError('Expired preview')
            return JSONResponse(await mail.send_mail(**item[1]),headers=headers)
        raise ValueError('Unknown action')
    except (ValueError,TypeError):
        return JSONResponse({'error':'Ungültige Eingabe, geändertes Profil, fehlende Zugangsdaten oder abgelaufene Vorschau. Neu laden und prüfen.'},status_code=400,headers=headers)
application=Starlette(routes=[Route('/',page),Route('/api/status',api),Route('/api/{action}',api,methods=['POST'])])
