import asyncio
import hmac
import os
import smtplib
import ssl
from email.message import EmailMessage

import httpx
import uvicorn
from email_validator import validate_email
from mcp.server.fastmcp import FastMCP
from mcp.server.transport_security import TransportSecuritySettings


def address(value):
    if '\r' in value or '\n' in value:
        raise ValueError('Invalid email address')
    return validate_email(value, check_deliverability=False).normalized


def setting_list(name, default):
    return [x.strip() for x in os.getenv(name, default).split(',') if x.strip()]


TOKEN = os.environ['MCP_TOKEN']
if len(TOKEN) < 32 or not TOKEN.isascii():
    raise ValueError('MCP_TOKEN must contain at least 32 random ASCII characters')
FROM = address(os.environ['MAIL_FROM'])
TO = address(os.environ['MAIL_TO'])
ALLOWED = {address(x).lower() for x in setting_list('MAIL_ALLOWED_TO', '')} or {TO.lower()}
MODE = os.getenv('MAIL_TRANSPORT', 'smtp')
if MODE not in {'smtp', 'api'}:
    raise ValueError('MAIL_TRANSPORT must be smtp or api')
DRY = os.getenv('DRY_RUN', 'true').lower()
if DRY not in {'true', 'false'}:
    raise ValueError('DRY_RUN must be true or false')
DRY = DRY == 'true'
if not DRY:
    required = ['SMTP_USERNAME', 'SMTP_PASSWORD'] if MODE == 'smtp' else ['MAILERSEND_API_TOKEN']
    for key in required:
        if not os.getenv(key):
            raise ValueError('Missing ' + key)
HOST = os.getenv('SMTP_HOST', 'smtp.mailersend.net')
PORT = int(os.getenv('SMTP_PORT', '587'))
if not 1 <= PORT <= 65535:
    raise ValueError('Invalid SMTP_PORT')

mcp = FastMCP(
    'highfishMailsend', stateless_http=True, json_response=True,
    transport_security=TransportSecuritySettings(
        enable_dns_rebinding_protection=True,
        allowed_hosts=setting_list('MCP_ALLOWED_HOSTS', 'localhost:*,127.0.0.1:*,[::1]:*'),
        allowed_origins=setting_list('MCP_ALLOWED_ORIGINS', 'http://localhost:*,http://127.0.0.1:*'),
    ),
)


def smtp_send(recipient, subject, text):
    message = EmailMessage()
    message['From'] = FROM
    message['To'] = recipient
    message['Subject'] = subject
    message.set_content(text)
    with smtplib.SMTP(HOST, PORT, timeout=20) as client:
        client.ehlo()
        client.starttls(context=ssl.create_default_context())
        client.ehlo()
        client.login(os.environ['SMTP_USERNAME'], os.environ['SMTP_PASSWORD'])
        client.send_message(message)


@mcp.tool()
async def send_mail(subject: str, text: str, to: str = '') -> dict:
    '''Send plain text email. Ask the user to approve recipient, subject and complete body before calling. DRY_RUN returns a preview without sending.'''
    recipient = address(to) if to else TO
    if recipient.lower() not in ALLOWED:
        raise ValueError('Recipient not allowed')
    if not subject.strip() or len(subject) > 200 or '\r' in subject or '\n' in subject:
        raise ValueError('Invalid subject')
    if not text.strip() or len(text) > 100000:
        raise ValueError('Body must contain 1 to 100000 characters')
    if DRY:
        return {'status': 'dry_run', 'sent': False, 'from': FROM, 'to': recipient, 'subject': subject, 'text': text}
    try:
        if MODE == 'smtp':
            await asyncio.to_thread(smtp_send, recipient, subject, text)
        else:
            async with httpx.AsyncClient(timeout=20) as client:
                response = await client.post(
                    'https://api.mailersend.com/v1/email',
                    headers={'Authorization': 'Bearer ' + os.environ['MAILERSEND_API_TOKEN']},
                    json={'from': {'email': FROM}, 'to': [{'email': recipient}], 'subject': subject, 'text': text},
                )
                response.raise_for_status()
    except Exception:
        return {'status': 'error', 'sent': None, 'message': 'Delivery failed or outcome uncertain. Check provider before retrying.'}
    return {'status': 'accepted', 'to': recipient, 'message': 'Provider accepted message; inbox delivery not guaranteed.'}


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
