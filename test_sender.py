import os
import unittest
from unittest.mock import patch
os.environ.update(MCP_TOKEN='test-only-abcdefghijklmnopqrstuvwxyz123456', MAIL_FROM='sender@example.com', MAIL_TO='placeholder', MAIL_ALLOWED_TO='', DRY_RUN='true')
import app
import admin
import httpx

class SenderTests(unittest.IsolatedAsyncioTestCase):
    def test_fixed_domain(self):
        self.assertEqual(app.resolve_sender('shop'), 'shop@example.com')
        self.assertEqual(app.resolve_sender(), app.FROM)
        for value in ['shop@other.com', 'shop@example.com', 'x\r\nBcc:y', 'a b', '.bad', 'bad..name', 'x' * 65, None]:
            with self.assertRaises(ValueError):
                app.resolve_sender(value)
    async def test_dry_run(self):
        with patch.object(app, 'DRY', True), patch('app.smtp_send', side_effect=AssertionError('No send')):
            result = await app.send_mail('Test', 'Hello', to='receiver@example.com', sender='shop')
            self.assertEqual(result['from'], 'shop@example.com')
            self.assertFalse(result['sent'])
    def test_smtp_header(self):
        with patch.dict(os.environ, SMTP_USERNAME='test', SMTP_PASSWORD='test'), patch('app.smtplib.SMTP') as smtp:
            app.smtp_send('receiver@example.com', 'Test', 'Hello', 'shop')
            msg = smtp.return_value.__enter__.return_value.send_message.call_args.args[0]
            self.assertEqual(msg['From'], 'shop@example.com')
            self.assertEqual(msg['To'], 'receiver@example.com')
    async def test_api_sender(self):
        def handle(request):
            import json
            self.assertEqual(json.loads(request.content)['from']['email'], 'shop@example.com')
            return httpx.Response(202)
        real_client = httpx.AsyncClient
        with patch.object(app, 'DRY', False), patch.object(app, 'MODE', 'api'), patch.dict(os.environ, MAILERSEND_API_TOKEN='test'), patch('app.httpx.AsyncClient', side_effect=lambda **kwargs: real_client(transport=httpx.MockTransport(handle), **kwargs)):
            self.assertEqual((await app.send_mail('Test', 'Hello', to='receiver@example.com', sender='shop'))['status'], 'accepted')
    async def test_web_snapshot(self):
        admin.DRAFTS.clear()
        with patch.object(app, 'DRY', True):
            async with httpx.AsyncClient(transport=httpx.ASGITransport(app=admin.application), base_url='http://localhost', headers={'Authorization': 'Bearer ' + app.TOKEN}) as client:
                result = await client.post('/api/preview', json={'subject': 'Test', 'text': 'Hello', 'to': 'receiver@example.com', 'sender': 'shop'})
                self.assertEqual(result.status_code, 200, result.text)
                self.assertEqual(result.json()['from'], 'shop@example.com')
                sent = await client.post('/api/send', json={'id': result.json()['id'], 'sender': 'other', 'to': 'other@example.com'})
                self.assertEqual(sent.json()['from'], 'shop@example.com')
                self.assertEqual(sent.json()['to'], 'receiver@example.com')
                invalid = await client.post('/api/preview', json={'subject': 'Test', 'text': 'Hello', 'to': 'receiver@example.com', 'sender': 'x@other.com'})
                self.assertEqual(invalid.status_code, 400)
