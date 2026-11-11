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
from starlette.responses import RedirectResponse
from starlette.routing import Mount, Route
import app as mail
import admin

TOKEN = os.getenv('TELEGRAM_BOT_TOKEN', '').strip()
USERS = {int(x.strip()) for x in os.getenv('TELEGRAM_ALLOWED_USER_IDS', '').split(',') if x.strip()}
if TOKEN and not USERS:
    raise ValueError('Set TELEGRAM_ALLOWED_USER_IDS when enabling Telegram')

MENU = {'inline_keyboard': [[{'text': 'Status', 'callback_data': 'status'}, {'text': 'Konfiguration', 'callback_data': 'config'}], [{'text': 'Testmodus einschalten', 'callback_data': 'dryrun'}], [{'text': 'Hilfe', 'callback_data': 'help'}]]}
HELP = '/admin: Menue\n/config: Konfiguration ohne Secrets\n/status: Status\n/dryrun: Testmodus einschalten\n/mail Betreff gefolgt von neuer Zeile und Mailtext\n/send CODE: Entwurf bestaetigen\n/cancel: Entwurf verwerfen. Live-Modus und Zugangsdaten in Portainer verwalten.'

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

        async def reply(chat, text, keyboard=None):
            payload = {'chat_id': chat, 'text': text[:4000]}
            if keyboard:
                payload['reply_markup'] = keyboard
            await api('sendMessage', payload)

        info = await api('getWebhookInfo', {})
        if info.get('url'):
            raise RuntimeError('Telegram webhook exists')
        old = await api('getUpdates', {'offset': -1, 'timeout': 0})
        offset = old[-1]['update_id'] + 1 if old else 0
        admin.TELEGRAM['state'] = 'polling'
        while True:
            try:
                updates = await api('getUpdates', {'offset': offset, 'timeout': 25, 'allowed_updates': ['message', 'callback_query']})
                admin.TELEGRAM['state'] = 'polling'
                for update in updates:
                    offset = update['update_id'] + 1
                    callback = update.get('callback_query')
                    message = callback.get('message', {}) if callback else update.get('message', {})
                    user = (callback if callback else message).get('from', {}).get('id')
                    chat = message.get('chat', {})
                    if user not in USERS or chat.get('type') != 'private':
                        continue
                    chat_id = chat['id']
                    text = message.get('text', '') if not callback else '/' + callback.get('data', '')
                    if callback:
                        await api('answerCallbackQuery', {'callback_query_id': callback['id']})
                    command = text.split(maxsplit=1)[0].split('@')[0] if text else ''
                    if command in {'/start', '/admin'}:
                        await reply(chat_id, 'highfishMailsend Administration', MENU)
                    elif command == '/help':
                        await reply(chat_id, HELP, MENU)
                    elif command in {'/config', '/status'}:
                        await reply(chat_id, json.dumps(admin.status(), indent=2), MENU)
                    elif command == '/dryrun':
                        mail.DRY = True
                        admin.DRAFTS.clear()
                        drafts.clear()
                        await reply(chat_id, 'Testmodus fuer MCP, Web und Telegram eingeschaltet (bis Neustart). Kein echter Mailversand.', MENU)
                    elif command == '/cancel':
                        drafts.pop(user, None)
                        await reply(chat_id, 'Entwurf verworfen.', MENU)
                    elif command == '/mail':
                        subject, separator, body = text.partition(' ')[2].partition('\n')
                        try:
                            if not separator:
                                raise ValueError('Missing body')
                            item = admin.draft(subject, body)
                        except ValueError:
                            await reply(chat_id, 'Format: /mail Betreff\nMailtext. Empfaenger und Inhalt muessen gueltig sein.')
                            continue
                        code = secrets.token_hex(4)
                        drafts[user] = (code, item, time.monotonic() + 600, mail.DRY)
                        await reply(chat_id, ('TESTMODUS' if mail.DRY else 'LIVE-VERSAND') + '\nAn: ' + mail.TO + '\nBetreff: ' + subject + '\n\n' + body[:2500] + ('\n[Textvorschau gekuerzt]' if len(body) > 2500 else '') + '\n\nFreigabe innerhalb 10 Minuten: /send ' + code + '\n/cancel verwirft.')
                    elif command == '/send':
                        item = drafts.get(user)
                        code = text.partition(' ')[2].strip()
                        if not item or time.monotonic() > item[2] or item[3] != mail.DRY or not secrets.compare_digest(code, item[0]):
                            await reply(chat_id, 'Kein gueltiger Entwurf, Modus geaendert oder Code falsch/abgelaufen.')
                            continue
                        drafts.pop(user, None)
                        try:
                            result = await mail.send_mail(**item[1])
                            await reply(chat_id, 'Ergebnis: ' + result['status'] + '\nBei Fehlern Provider pruefen, nicht blind wiederholen.', MENU)
                        except Exception:
                            await reply(chat_id, 'Versand abgelehnt oder Status unklar; Provider pruefen.')
                    else:
                        await reply(chat_id, HELP, MENU)
            except asyncio.CancelledError:
                raise
            except Exception:
                admin.TELEGRAM['state'] = 'retrying'
                await asyncio.sleep(5)

@asynccontextmanager
async def lifespan(application):
    async with mail.inner.router.lifespan_context(mail.inner):
        admin.TELEGRAM['state'] = 'starting' if TOKEN else 'disabled'
        task = asyncio.create_task(poll()) if TOKEN else None
        if task:
            def done(result):
                if not result.cancelled() and result.exception():
                    admin.TELEGRAM['state'] = 'stopped_error'
                    print('Telegram stopped: check token, allowlist and webhook configuration.', flush=True)
            task.add_done_callback(done)
        try:
            yield
        finally:
            if task:
                task.cancel()
                with contextlib.suppress(asyncio.CancelledError, Exception):
                    await task

async def home(request):
    return RedirectResponse('/admin/')

application = Starlette(routes=[Route('/', home), Mount('/admin', app=admin.application), Mount('/', app=mail.app)], lifespan=lifespan)

if __name__ == '__main__':
    uvicorn.run(application, host='0.0.0.0', port=8000, access_log=False)
