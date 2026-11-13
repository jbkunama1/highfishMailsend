import asyncio
import contextlib
import logging
import os
from contextlib import asynccontextmanager
import httpx
import uvicorn
import runner
from web_access import WebAccess

# HTTP client info logs include Telegram token URLs; never log them.
logging.getLogger('httpx').setLevel(logging.WARNING)
logging.getLogger('httpcore').setLevel(logging.WARNING)

async def notify_startup():
    if not runner.TOKEN or not runner.USERS:
        return
    mode = 'TESTMODUS - kein E-Mail-Versand' if runner.mail.DRY else 'LIVE - E-Mails nur nach explizitem Aufruf'
    text = ('highfishMailsend gestartet\nModus: ' + mode + '\nStandard-Versandweg: ' + runner.mail.MODE + '\nWeb-Admin: ' + ('eingerichtet' if application.configured() else 'gesperrt - Zugangsdaten fehlen oder ungueltig') + '\nMCP: aktiviert')
    async with httpx.AsyncClient(timeout=10, follow_redirects=False) as client:
        for user in sorted(runner.USERS):
            try:
                result = await client.post('https://api.telegram.org/bot' + runner.TOKEN + '/sendMessage', json={'chat_id': user, 'text': text})
                result.raise_for_status()
                if result.json().get('ok') is not True:
                    raise ValueError('Telegram refused notification')
            except asyncio.CancelledError:
                raise
            except Exception:
                print('Telegram-Startmeldung fehlgeschlagen; kein automatischer Wiederholungsversuch.', flush=True)

original_lifespan = runner.application.router.lifespan_context

@asynccontextmanager
async def lifespan(app):
    async with original_lifespan(app):
        task = asyncio.create_task(notify_startup())
        try:
            yield
        finally:
            if not task.done():
                task.cancel()
            with contextlib.suppress(asyncio.CancelledError, Exception):
                await task

runner.application.router.lifespan_context = lifespan
application = WebAccess(runner.application, runner.mail.TOKEN)

if __name__ == '__main__':
    uvicorn.run(application, host='0.0.0.0', port=8000, access_log=False, proxy_headers=False)
