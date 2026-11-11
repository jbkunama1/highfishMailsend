import os
import unittest
from unittest.mock import patch

os.environ.update(MCP_TOKEN='test-only-abcdefghijklmnopqrstuvwxyz123456', MAIL_FROM='sender@example.com', MAIL_TO='receiver@example.com', MAIL_ALLOWED_TO='', DRY_RUN='true')
import admin
import httpx

class AdminTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        admin.DRAFTS.clear()
        self.client = httpx.AsyncClient(transport=httpx.ASGITransport(app=admin.application), base_url='http://localhost')

    async def asyncTearDown(self):
        await self.client.aclose()

    async def test_auth(self):
        self.assertEqual((await self.client.get('/api/status')).status_code, 401)
        response = await self.client.get('/api/status', headers={'Authorization': 'Bearer ' + admin.mail.TOKEN})
        self.assertEqual(response.status_code, 200)
        self.assertNotIn(admin.mail.TOKEN, response.text)

    async def test_preview_send_once(self):
        self.client.headers['Authorization'] = 'Bearer ' + admin.mail.TOKEN
        with patch.object(admin.mail, 'DRY', True), patch('app.smtp_send', side_effect=AssertionError('No network')):
            response = await self.client.post('/api/preview', json={'subject': 'Test', 'text': 'Hello'})
            self.assertEqual(response.status_code, 200)
            key = response.json()['id']
            result = await self.client.post('/api/send', json={'id': key})
            self.assertEqual(result.json()['status'], 'dry_run')
            self.assertEqual((await self.client.post('/api/send', json={'id': key})).status_code, 400)

    async def test_mode_change_invalidates(self):
        self.client.headers['Authorization'] = 'Bearer ' + admin.mail.TOKEN
        with patch.object(admin.mail, 'DRY', True):
            response = await self.client.post('/api/preview', json={'subject': 'Test', 'text': 'Hello'})
            admin.mail.DRY = False
            self.assertEqual((await self.client.post('/api/send', json={'id': response.json()['id']})).status_code, 400)

    async def test_allowlist(self):
        self.client.headers['Authorization'] = 'Bearer ' + admin.mail.TOKEN
        response = await self.client.post('/api/preview', json={'subject': 'Test', 'text': 'Hello', 'to': 'blocked@example.com'})
        self.assertEqual(response.status_code, 400)
