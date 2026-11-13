import json
import os
import unittest
from unittest.mock import patch
os.environ.update(MCP_TOKEN='test-only-abcdefghijklmnopqrstuvwxyz123456', MAIL_FROM='sender@example.com', MAIL_TO='placeholder', MAIL_ALLOWED_TO='', DRY_RUN='true')
import app
import httpx

class CyberPanelTests(unittest.IsolatedAsyncioTestCase):
    async def test_success_payload_and_sender(self):
        seen = []
        def handler(request):
            seen.append(request)
            self.assertEqual(str(request.url), 'https://platform.cyberpersons.com/email/v1/send')
            self.assertEqual(request.headers['Authorization'], 'Bearer fake-test-key')
            self.assertEqual(json.loads(request.content), {'from': 'shop@example.com', 'to': 'receiver@example.com', 'subject': 'Test', 'text': 'Hello'})
            return httpx.Response(202, json={'success': True, 'data': {'message_id': 'mock-message'}})
        real_client = httpx.AsyncClient
        with patch.object(app, 'MODE', 'cyberpanel'), patch.object(app, 'DRY', False), patch.dict(os.environ, CYBERPANEL_API_KEY='fake-test-key'), patch('app.httpx.AsyncClient', side_effect=lambda **kwargs: real_client(transport=httpx.MockTransport(handler), **kwargs)):
            result = await app.send_mail('Test', 'Hello', to='receiver@example.com', sender='shop')
        self.assertEqual(result['status'], 'accepted')
        self.assertEqual(result['message_id'], 'mock-message')
        self.assertEqual(len(seen), 1)
    async def test_dry_run_no_network(self):
        with patch.object(app, 'MODE', 'cyberpanel'), patch.object(app, 'DRY', True), patch('app.httpx.AsyncClient', side_effect=AssertionError('Network forbidden')):
            self.assertFalse((await app.send_mail('Test', 'Hello', to='receiver@example.com'))['sent'])
    async def test_failures_without_retry_or_fallback(self):
        cases = [(403, {'error': 'forbidden'}), (429, {'error': 'rate_limit_exceeded'}), (503, {}), (202, {'success': False}), (202, {'success': True, 'data': None}), (200, {'success': True, 'data': {}})]
        real_client = httpx.AsyncClient
        for code, payload in cases:
            with self.subTest(code=code, payload=payload):
                seen = []
                def handler(request):
                    seen.append(request)
                    return httpx.Response(code, json=payload)
                with patch.object(app, 'MODE', 'cyberpanel'), patch.object(app, 'DRY', False), patch.dict(os.environ, CYBERPANEL_API_KEY='fake-test-key'), patch('app.smtp_send', side_effect=AssertionError('No fallback')), patch('app.httpx.AsyncClient', side_effect=lambda **kwargs: real_client(transport=httpx.MockTransport(handler), **kwargs)):
                    result = await app.send_mail('Test', 'Hello', to='receiver@example.com')
                self.assertEqual(result['status'], 'error')
                self.assertIsNone(result['sent'])
                self.assertEqual(len(seen), 1)
    async def test_timeout(self):
        def handler(request):
            raise httpx.ReadTimeout('mock timeout', request=request)
        real_client = httpx.AsyncClient
        with patch.object(app, 'MODE', 'cyberpanel'), patch.object(app, 'DRY', False), patch.dict(os.environ, CYBERPANEL_API_KEY='fake-test-key'), patch('app.httpx.AsyncClient', side_effect=lambda **kwargs: real_client(transport=httpx.MockTransport(handler), **kwargs)):
            self.assertIsNone((await app.send_mail('Test', 'Hello', to='receiver@example.com'))['sent'])
