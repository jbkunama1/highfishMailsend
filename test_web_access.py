import os
import unittest
from unittest.mock import patch
import httpx
from starlette.responses import JSONResponse
from web_access import WebAccess

class WebAccessTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.env = patch.dict(os.environ, WEB_ADMIN_USERNAME='admin', WEB_ADMIN_PASSWORD='separate-web-password-for-tests')
        self.env.start()
        async def backend(scope, receive, send):
            headers = dict(scope.get('headers', []))
            result = JSONResponse({'authorization': headers.get(b'authorization', b'').decode(), 'path': scope['path']})
            await result(scope, receive, send)
        self.app = WebAccess(backend, 'mcp-secret-for-tests')
        self.client = httpx.AsyncClient(transport=httpx.ASGITransport(app=self.app), base_url='https://localhost')
    async def asyncTearDown(self):
        await self.client.aclose()
        self.env.stop()
    async def login(self):
        return await self.client.post('/admin/api/login', json={'username': 'admin', 'password': 'separate-web-password-for-tests'}, headers={'X-Web-Admin': '1'})
    async def test_separation_and_logout(self):
        self.assertEqual((await self.client.get('/admin/api/status', headers={'Authorization': 'Bearer mcp-secret-for-tests'})).status_code, 401)
        result = await self.login()
        self.assertEqual(result.status_code, 200)
        cookie = result.headers['set-cookie'].lower()
        for flag in ['httponly', 'secure', 'samesite=strict', 'path=/admin']:
            self.assertIn(flag, cookie)
        result = await self.client.get('/admin/api/status')
        self.assertEqual(result.status_code, 200)
        self.assertEqual(result.json()['authorization'], 'Bearer mcp-secret-for-tests')
        self.assertEqual((await self.client.get('/mcp')).json()['authorization'], '')
        old_cookie = self.client.cookies.get('highfish_admin')
        self.assertEqual((await self.client.post('/admin/api/logout', json={}, headers={'X-Web-Admin': '1'})).status_code, 200)
        self.assertEqual((await self.client.get('/admin/api/status', headers={'Cookie': 'highfish_admin=' + old_cookie})).status_code, 401)
    async def test_bad_credentials_csrf_and_limits(self):
        self.assertEqual((await self.client.post('/admin/api/login', json={})).status_code, 403)
        self.assertEqual((await self.client.post('/admin/api/login', json={}, headers={'X-Web-Admin': '1', 'Origin': 'https://evil.example'})).status_code, 403)
        for _ in range(10):
            result = await self.client.post('/admin/api/login', json={'username': 'admin', 'password': 'wrong'}, headers={'X-Web-Admin': '1'})
            self.assertEqual(result.status_code, 401)
        self.assertEqual((await self.login()).status_code, 429)
    async def test_missing_and_reused_password(self):
        for password in ['', 'short', 'mcp-secret-for-tests']:
            with patch.dict(os.environ, WEB_ADMIN_PASSWORD=password):
                self.assertEqual((await self.client.get('/admin/api/status')).status_code, 503)
                self.assertEqual((await self.client.get('/health')).status_code, 200)
    async def test_expiry_and_restart(self):
        await self.login()
        for key in self.app.sessions:
            self.app.sessions[key] = 0
        self.assertEqual((await self.client.get('/admin/api/status')).status_code, 401)
        await self.login()
        self.app.sessions.clear()
        self.assertEqual((await self.client.get('/admin/api/status')).status_code, 401)

if __name__ == '__main__':
    unittest.main()
