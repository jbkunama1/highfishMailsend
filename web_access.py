import hashlib
import hmac
import json
import os
import secrets
import time
from http.cookies import SimpleCookie
from urllib.parse import urlsplit
from starlette.responses import JSONResponse

COOKIE = 'highfish_admin'
TTL = 3600

class WebAccess:
    def __init__(self, inner, internal_token):
        self.inner = inner
        self.internal_token = internal_token
        self.sessions = {}
        self.attempts = {}

    def configured(self):
        password = os.getenv('WEB_ADMIN_PASSWORD', '')
        return bool(os.getenv('WEB_ADMIN_USERNAME', 'admin')) and len(password) >= 16 and not hmac.compare_digest(password.encode(), self.internal_token.encode())

    async def __call__(self, scope, receive, send):
        path = scope.get('path', '')
        if scope['type'] != 'http' or not path.startswith('/admin/api/'):
            return await self.inner(scope, receive, send)
        headers = {k.lower(): v for k, v in scope.get('headers', [])}
        def response(data, status=200):
            return JSONResponse(data, status_code=status, headers={'Cache-Control': 'no-store'})
        if not self.configured():
            return await response({'error': 'Webzugang nicht eingerichtet: eigenes Passwort mit mindestens 16 Zeichen setzen.'}, 503)(scope, receive, send)
        now = time.monotonic()
        self.sessions = {k: v for k, v in self.sessions.items() if v > now}
        secure = scope.get('scheme') == 'https'
        if scope['method'] != 'GET':
            if headers.get(b'x-web-admin') != b'1':
                return await response({'error': 'Web-Anfrage abgelehnt'}, 403)(scope, receive, send)
            origin = headers.get(b'origin')
            if origin:
                try:
                    parsed = urlsplit(origin.decode('ascii'))
                    valid = parsed.scheme == scope.get('scheme') and parsed.netloc.lower() == headers.get(b'host', b'').decode('ascii').lower() and parsed.path == '' and not parsed.query and not parsed.fragment and not parsed.username
                except (UnicodeError, ValueError):
                    valid = False
                if not valid:
                    return await response({'error': 'Fremder Ursprung abgelehnt'}, 403)(scope, receive, send)
        if path == '/admin/api/login':
            if scope['method'] != 'POST':
                return await response({'error': 'POST erforderlich'}, 405)(scope, receive, send)
            if headers.get(b'content-type', b'').split(b';')[0] != b'application/json':
                return await response({'error': 'JSON erforderlich'}, 415)(scope, receive, send)
            self.attempts = {k: v for k, v in self.attempts.items() if v[0] > now}
            peer = (scope.get('client') or ('unknown',))[0]
            deadline, count = self.attempts.get(peer, (now + 60, 0))
            if count >= 10 or len(self.attempts) >= 1000 and peer not in self.attempts:
                return await response({'error': 'Zu viele Anmeldeversuche. Eine Minute warten.'}, 429)(scope, receive, send)
            self.attempts[peer] = (deadline, count + 1)
            body = bytearray()
            while True:
                message = await receive()
                if message['type'] == 'http.disconnect':
                    return
                body.extend(message.get('body', b''))
                if len(body) > 4096:
                    return await response({'error': 'Anfrage zu gross'}, 413)(scope, receive, send)
                if not message.get('more_body', False):
                    break
            try:
                data = json.loads(body)
                username, password = data['username'], data['password']
                valid = isinstance(username, str) and isinstance(password, str)
                valid = valid and hmac.compare_digest(username.encode(), os.getenv('WEB_ADMIN_USERNAME', 'admin').encode()) & hmac.compare_digest(password.encode(), os.getenv('WEB_ADMIN_PASSWORD', '').encode())
            except (ValueError, TypeError, KeyError):
                valid = False
            if not valid:
                return await response({'error': 'Anmeldung fehlgeschlagen'}, 401)(scope, receive, send)
            if len(self.sessions) >= 256:
                return await response({'error': 'Zu viele Sitzungen'}, 503)(scope, receive, send)
            token = secrets.token_urlsafe(32)
            self.sessions[hashlib.sha256(token.encode()).hexdigest()] = now + TTL
            result = response({'authenticated': True, 'expires_in': TTL})
            result.set_cookie(COOKIE, token, max_age=TTL, path='/admin', httponly=True, secure=secure, samesite='strict')
            return await result(scope, receive, send)
        try:
            cookies = SimpleCookie()
            cookies.load(headers.get(b'cookie', b'').decode('latin1'))
            token = cookies[COOKIE].value
        except Exception:
            token = ''
        key = hashlib.sha256(token.encode()).hexdigest()
        if not token or self.sessions.get(key, 0) <= now:
            return await response({'error': 'Bitte mit Web-Benutzername und Passwort anmelden.'}, 401)(scope, receive, send)
        if path == '/admin/api/logout':
            if scope['method'] != 'POST':
                return await response({'error': 'POST erforderlich'}, 405)(scope, receive, send)
            self.sessions.pop(key, None)
            result = response({'authenticated': False})
            result.delete_cookie(COOKIE, path='/admin', httponly=True, secure=secure, samesite='strict')
            return await result(scope, receive, send)
        forwarded = dict(scope)
        forwarded['headers'] = [(k, v) for k, v in scope.get('headers', []) if k.lower() != b'authorization'] + [(b'authorization', ('Bearer ' + self.internal_token).encode())]
        return await self.inner(forwarded, receive, send)
