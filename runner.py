import asyncio
import contextlib
import json
import os
import secrets
import time
from contextlib import asynccontextmanager

import httpx
import uvicorn
from starlette.applications import Starlette
from starlette.routing import Mount
import app as mail

TOKEN = os.getenv('TELEGRAM_BOT_TOKEN', '').strip()
USERS = {int(x.strip()) for x in os.getenv('TELEGRAM_ALLOWED_USER_IDS', '').split(',') if x.strip()}
if TOKEN and not USERS:
    raise ValueError('Set TELEGRAM_ALLOWED_USER_IDS when enabling Telegram')


async def poll():
    drafts = {}
    async with httpx.AsyncClient(timeout=40) as client:
        async def api(method, payload):
            response = await client.post('https://api.telegram.org/bot' + TOKEN + '/' + method, json=payload)
            response.raise_for_status()
            result = response.json()
            if not result.get('ok'):
                raise RuntimeError('Telegram request failed')
            return result['result']

        async def reply(chat, text):
            await api('sendMessage', {'chat_id': chat, 'text': text[:4000]})

        info = await api('getWebhookInfo', {})
        if info.get('url'):
            raise RuntimeError('Telegram webhook exists; remove it before enabling polling')
        old = await api('getUpdates', {'offset': -1, 'timeout': 0})
        offset = old[-1]['update_id'] + 1 if old else 0
        while True:
            try:
                updates = await api('getUpdates', {'offset': offset, 'timeout': 25, 'allowed_updates': ['message']})
                for update in updates:
                    offset = update['update_id'] + 1
                    message = update.get('message', {})
                    user = message.get('from', {}).get('id')
                    chat = message.get('chat', {})
                    if user not in USERS or chat.get('type') != 'private':
                        continue
                    chat_id = chat['id']
                    text = message.get('text', '')
                    command = text.split(maxsplit=1)[0].split('@')[0] if text else ''
                    if command in {'/start', '/help'}:
                        await reply(chat_id, 'Mailentwurf: /mail Betreff gefolgt von einer neuen Zeile und dem Mailtext. Empfaenger ist MAIL_TO. Danach /send CODE oder /cancel. /status zeigt den Modus. Nur private Chats freigegebener Nutzer sind erlaubt.')
                    elif command == '/status':
                        await reply(chat_id, 'Modus: ' + ('DRY_RUN (kein Versand)' if mail.DRY else 'ECHTER VERSAND') + '\nTransport: ' + mail.MODE)
                    elif command == '/cancel':
                        drafts.pop(user, None)
                        await reply(chat_id, 'Entwurf verworfen.')
                    elif command == '/mail':
                        payload = text.partition(' ')[2]
                        subject, separator, body = payload.partition('\n')
                        if not separator or not subject.strip() or len(subject) > 200 or '\r' in subject or not body.strip() or len(body) > 100000:
                            await reply(chat_id, 'Format: /mail Betreff\nMailtext (Betreff maximal 200 Zeichen).')
                            continue
                        code = secrets.token_hex(4)
                        drafts[user] = (code, subject, body, time.monotonic() + 600)
                        await reply(chat_id, 'An: ' + mail.TO + '\nBetreff: ' + subject + '\n\n' + body[:2500] + ('\n[Textvorschau gekuerzt]' if len(body) > 2500 else '') + '\n\nFreigabe innerhalb 10 Minuten: /send ' + code + '\n/cancel verwirft den Entwurf.')
                    elif command == '/send':
                        draft = drafts.get(user)
                        code = text.partition(' ')[2].strip()
                        if not draft or time.monotonic() > draft[3] or not secrets.compare_digest(code, draft[0]):
                            await reply(chat_id, 'Kein gueltiger Entwurf oder falscher/abgelaufener Code.')
                            continue
                        drafts.pop(user, None)
                        try:
                            result = await mail.send_mail(draft[1], draft[2])
                            await reply(chat_id, 'Ergebnis: ' + result['status'] + '\nBei Fehlern erst Provider pruefen, nicht blind erneut senden.')
                        except Exception:
                            await reply(chat_id, 'Versand abgelehnt oder Status unklar. Konfiguration und Provider pruefen.')
                    else:
                        await reply(chat_id, 'Mit /help die Befehle anzeigen.')
            except asyncio.CancelledError:
                raise
            except Exception:
                await asyncio.sleep(5)


@asynccontextmanager
async def lifespan(application):
    async with mail.inner.router.lifespan_context(mail.inner):
        task = asyncio.create_task(poll()) if TOKEN else None
        if task:
            def done(result):
                if not result.cancelled() and result.exception():
                    print('Telegram stopped: check bot token, user allowlist and webhook configuration.', flush=True)
            task.add_done_callback(done)
        try:
            yield
        finally:
            if task:
                task.cancel()
                with contextlib.suppress(asyncio.CancelledError, Exception):
                    await task


application = Starlette(routes=[Mount('/', app=mail.app)], lifespan=lifespan)

if __name__ == '__main__':
    uvicorn.run(application, host='0.0.0.0', port=8000, access_log=False)
