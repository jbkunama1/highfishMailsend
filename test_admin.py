import os
import unittest
from unittest.mock import patch
os.environ.update(MCP_TOKEN='test-only-abcdefghijklmnopqrstuvwxyz123456', MAIL_FROM='sender@example.com', MAIL_TO='placeholder', MAIL_ALLOWED_TO='', DRY_RUN='true')
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
            response = await self.client.post('/api/preview', json={'subject': 'Test', 'text': 'Hello', 'to': 'receiver@example.com'})
            self.assertEqual(response.status_code, 200, response.text)
            key = response.json()['id']
            result = await self.client.post('/api/send', json={'id': key})
            self.assertEqual(result.json()['status'], 'dry_run')
            self.assertEqual(result.json()['to'], 'receiver@example.com')
            self.assertEqual((await self.client.post('/api/send', json={'id': key})).status_code, 400)
    async def test_mode_change_invalidates(self):
        self.client.headers['Authorization'] = 'Bearer ' + admin.mail.TOKEN
        with patch.object(admin.mail, 'DRY', True):
            response = await self.client.post('/api/preview', json={'subject': 'Test', 'text': 'Hello', 'to': 'receiver@example.com'})
            self.assertEqual(response.status_code, 200, response.text)
            admin.mail.DRY = False
            self.assertEqual((await self.client.post('/api/send', json={'id': response.json()['id']})).status_code, 400)
    async def test_allowlist(self):
        self.client.headers['Authorization'] = 'Bearer ' + admin.mail.TOKEN
        with patch.object(admin.mail, 'ALLOWED', {'receiver@example.com'}), patch.object(admin.mail, 'DRY', True):
            response = await self.client.post('/api/preview', json={'subject': 'Test', 'text': 'Hello', 'to': 'blocked@example.com'})
            self.assertEqual(response.status_code, 400)
            response = await self.client.post('/api/preview', json={'subject': 'Test', 'text': 'Hello', 'to': 'receiver@example.com'})
            self.assertEqual(response.status_code, 200, response.text)
    async def test_explicit_recipient_required(self):
        self.client.headers['Authorization'] = 'Bearer ' + admin.mail.TOKEN
        with patch.object(admin.mail, 'DRY', True), patch.object(admin.mail, 'TO', 'placeholder'), patch.object(admin.mail, 'ALLOWED', set()):
            for to in ['', ' ', 'placeholder', 'bad\n@example.com']:
                response = await self.client.post('/api/preview', json={'subject': 'Test', 'text': 'Hello', 'to': to})
                self.assertEqual(response.status_code, 400)
            response = await self.client.post('/api/preview', json={'subject': 'Test', 'text': 'Hello'})
            self.assertEqual(response.status_code, 400)
            response = await self.client.post('/api/preview', json={'subject': 'Test', 'text': 'Hello', 'to': 'dynamic@example.com'})
            self.assertEqual(response.status_code, 200, response.text)
