import asyncio
import hmac
import os
import re
import smtplib
import ssl
from email.message import EmailMessage
import httpx
import uvicorn
from email_validator import validate_email
from mcp.server.fastmcp import FastMCP
from mcp.server.transport_security import TransportSecuritySettings

def address(value):
    if not isinstance(value, str) or '\r' in value or '\n' in value:
        raise ValueError('Invalid email address')
    return validate_email(value, check_deliverability=False).normalized

def setting_list(name, default):
    return [x.strip() for x in os.getenv(name, default).split(',') if x.strip()]

TOKEN = os.environ['MCP_TOKEN']
if len(TOKEN) < 32 or not TOKEN.isascii():
    raise ValueError('MCP_TOKEN must contain at least 32 random ASCII characters')
FROM = address(os.environ['MAIL_FROM'])
SENDER_DOMAIN = FROM.rsplit('@', 1)[1]
# Legacy placeholder only; never validate or use as a delivery fallback.
TO = os.getenv('MAIL_TO', '')
ALLOWED = {address(x).lower() for x in setting_list('MAIL_ALLOWED_TO', '')}

def resolve_recipient(to):
    if not isinstance(to, str) or not to.strip():
        raise ValueError('An explicit to email address is required for each call')
    recipient = address(to)
    if ALLOWED and recipient.lower() not in ALLOWED:
        raise ValueError('Recipient not allowed')
    return recipient

MODE = os.getenv('MAIL_TRANSPORT', 'smtp')
INITIAL_MODE = MODE
CREDENTIALS = {'smtp': ['SMTP_USERNAME', 'SMTP_PASSWORD'], 'api': ['MAILERSEND_API_TOKEN'], 'cyberpanel': ['CYBERPANEL_API_KEY']}
if MODE not in CREDENTIALS:
    raise ValueError('MAIL_TRANSPORT must be smtp, api or cyberpanel')
DRY = os.getenv('DRY_RUN', 'true').lower()
if DRY not in {'true', 'false'}:
    raise ValueError('DRY_RUN must be true or false')
DRY = DRY == 'true'
if not DRY:
    for key in CREDENTIALS[MODE]:
        if not os.getenv(key):
            raise ValueError('Missing ' + key)
HOST = os.getenv('SMTP_HOST', 'smtp.mailersend.net')
PORT = int(os.getenv('SMTP_PORT', '587'))
if not 1 <= PORT <= 65535:
    raise ValueError('Invalid SMTP_PORT')
CYBERPANEL_SEND_URL = 'https://platform.cyberpersons.com/email/v1/send'

def select_transport(transport=''):
    if not isinstance(transport, str):
        raise ValueError('Transport must be a string')
    selected = transport or MODE
    if selected not in CREDENTIALS:
        raise ValueError('Unknown transport')
    return selected

def set_default_transport(transport):
    global MODE
    if transport not in ('smtp', 'cyberpanel'):
        raise ValueError('Choose smtp or cyberpanel')
    if not DRY and any(not os.getenv(key) for key in CREDENTIALS[transport]):
        raise ValueError('Transport credentials missing')
    MODE = transport
    return MODE

def resolve_sender(sender=''):
    if not isinstance(sender, str):
        raise ValueError('Sender must be a string')
    if sender == '':
        return FROM
    if len(sender) > 64 or not re.fullmatch(r'[A-Za-z0-9_+.-]+', sender):
        raise ValueError('Only an ASCII sender name before @ is allowed')
    result = address(sender + '@' + SENDER_DOMAIN)
    if result.rsplit('@', 1)[1] != SENDER_DOMAIN:
        raise ValueError('Sender domain is fixed')
    return result

mcp = FastMCP('highfishMailsend', stateless_http=True, json_response=True, transport_security=TransportSecuritySettings(
    enable_dns_rebinding_protection=True,
    allowed_hosts=setting_list('MCP_ALLOWED_HOSTS', 'localhost:*,127.0.0.1:*,[::1]:*'),
    allowed_origins=setting_list('MCP_ALLOWED_ORIGINS', 'http://localhost:*,http://127.0.0.1:*')))

def smtp_send(recipient, subject, text, sender=''):
    message = EmailMessage()
    message['From'] = resolve_sender(sender)
    message['To'] = recipient
    message['Subject'] = subject
    message.set_content(text)
    with smtplib.SMTP(HOST, PORT, timeout=20) as client:
        client.ehlo()
        client.starttls(context=ssl.create_default_context())
        client.ehlo()
        client.login(os.environ['SMTP_USERNAME'], os.environ['SMTP_PASSWORD'])
        client.send_message(message)

async def cyberpanel_send(sender_address, recipient, subject, text):
    async with httpx.AsyncClient(timeout=20, follow_redirects=False) as client:
        response = await client.post(CYBERPANEL_SEND_URL, headers={'Authorization': 'Bearer ' + os.environ['CYBERPANEL_API_KEY']}, json={'from': sender_address, 'to': recipient, 'subject': subject, 'text': text})
        response.raise_for_status()
        data = response.json()
        if response.status_code != 202 or not isinstance(data, dict) or data.get('success') is not True or not isinstance(data.get('data'), dict):
            raise ValueError('Unexpected CyberPanel response; check provider before retrying')
        message_id = data['data'].get('message_id')
        return message_id if isinstance(message_id, str) and len(message_id) <= 512 else None

@mcp.tool()
async def send_mail(subject: str, text: str, to: str, sender: str = '', transport: str = '') -> dict:
    '''Send plain text email to the required explicit to address. MAIL_TO is an unused legacy placeholder. sender is only the name BEFORE @; domain fixed by MAIL_FROM. transport is smtp or cyberpanel (legacy api means MailerSend); empty uses current global default. Obtain approval for transport, full sender, recipient, subject and body. DRY_RUN never sends. This call does not change the global default.'''
    recipient = resolve_recipient(to)
    selected = select_transport(transport)
    sender_address = resolve_sender(sender)
    if not subject.strip() or len(subject) > 200 or '\r' in subject or '\n' in subject:
        raise ValueError('Invalid subject')
    if not text.strip() or len(text) > 100000:
        raise ValueError('Body must contain 1 to 100000 characters')
    if DRY:
        return {'status': 'dry_run', 'sent': False, 'transport': selected, 'from': sender_address, 'to': recipient, 'subject': subject, 'text': text}
    message_id = None
    try:
        if selected == 'smtp':
            await asyncio.to_thread(smtp_send, recipient, subject, text, sender)
        elif selected == 'cyberpanel':
            message_id = await cyberpanel_send(sender_address, recipient, subject, text)
        else:
            async with httpx.AsyncClient(timeout=20) as client:
                response = await client.post('https://api.mailersend.com/v1/email', headers={'Authorization': 'Bearer ' + os.environ['MAILERSEND_API_TOKEN']}, json={'from': {'email': sender_address}, 'to': [{'email': recipient}], 'subject': subject, 'text': text})
                response.raise_for_status()
    except Exception:
        return {'status': 'error', 'sent': None, 'transport': selected, 'message': 'Delivery failed or outcome uncertain. Check provider before retrying.'}
    result = {'status': 'accepted', 'transport': selected, 'from': sender_address, 'to': recipient, 'message': 'Provider accepted message; inbox delivery not guaranteed.'}
    if message_id:
        result['message_id'] = message_id
    return result

inner = mcp.streamable_http_app()
async def app(scope, receive, send):
    if scope['type'] != 'http':
        return await inner(scope, receive, send)
    if scope['path'] == '/health' and scope['method'] == 'GET':
        status, body = 200, b'{"status":"ok"}'
    elif not hmac.compare_digest(dict(scope.get('headers', [])).get(b'authorization', b''), ('Bearer ' + TOKEN).encode()):
        status, body = 401, b'{"error":"unauthorized"}'
    else:
        return await inner(scope, receive, send)
    headers = [(b'content-type', b'application/json')]
    if status == 401:
        headers.append((b'www-authenticate', b'Bearer'))
    await send({'type': 'http.response.start', 'status': status, 'headers': headers})
    await send({'type': 'http.response.body', 'body': body})
if __name__ == '__main__':
    uvicorn.run(app, host='0.0.0.0', port=8000, access_log=False)
