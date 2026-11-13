import os
import subprocess
import sys
import unittest
from unittest.mock import patch
os.environ.update(MCP_TOKEN='test-only-abcdefghijklmnopqrstuvwxyz123456', MAIL_FROM='sender@example.com', MAIL_TO='placeholder', MAIL_ALLOWED_TO='', DRY_RUN='true')
import app
import httpx
from mcp.server.transport_security import TransportSecurityMiddleware, TransportSecuritySettings
from starlette.requests import Request

class Tests(unittest.IsolatedAsyncioTestCase):
    async def test_dry_run_no_network(self):
        with patch.object(app, 'DRY', True), patch.object(app, 'ALLOWED', set()), patch.object(app, 'TO', 'placeholder'), patch('app.smtp_send', side_effect=AssertionError('Network forbidden')), patch('app.httpx.AsyncClient', side_effect=AssertionError('Network forbidden')):
            result = await app.send_mail('Test', 'Hello', to='receiver@example.com')
        self.assertFalse(result['sent'])
        self.assertEqual(result['to'], 'receiver@example.com')
    async def test_validation(self):
        cases = [('bad\r\nBcc: x', 'Hello', 'receiver@example.com'), ('', 'Hello', 'receiver@example.com'), ('Test', '', 'receiver@example.com'), ('Test', 'Hello', 'a\n@example.com'), ('Test', 'Hello', ''), ('Test', 'Hello', 'placeholder')]
        with patch.object(app, 'ALLOWED', set()), patch('app.smtp_send', side_effect=AssertionError('No send')), patch('app.httpx.AsyncClient', side_effect=AssertionError('No network')):
            for args in cases:
                with self.subTest(args=args), self.assertRaises(ValueError):
                    await app.send_mail(*args)
            with self.assertRaises(TypeError):
                await app.send_mail('Test', 'Hello')
    async def test_allowlist(self):
        with patch.object(app, 'DRY', True), patch.object(app, 'ALLOWED', {'receiver@example.com'}):
            with self.assertRaises(ValueError):
                await app.send_mail('Test', 'Hello', to='blocked@example.com')
            self.assertEqual((await app.send_mail('Test', 'Hello', to='receiver@example.com'))['to'], 'receiver@example.com')
        with patch.object(app, 'DRY', True), patch.object(app, 'ALLOWED', set()):
            self.assertEqual((await app.send_mail('Test', 'Hello', to='dynamic@example.com'))['to'], 'dynamic@example.com')
    def test_startup_placeholder(self):
        code = "from unittest.mock import patch\nwith patch('socket.socket.connect', side_effect=AssertionError('Network forbidden')), patch('smtplib.SMTP', side_effect=AssertionError('No send')):\n import app\n import os\n assert app.TO == os.getenv('MAIL_TO', '')\n assert app.ALLOWED == set()\n"
        for value in ['placeholder', '', None]:
            env = dict(os.environ, MCP_TOKEN='test-only-abcdefghijklmnopqrstuvwxyz123456', MAIL_FROM='sender@example.com', MAIL_ALLOWED_TO='', DRY_RUN='true')
            if value is None:
                env.pop('MAIL_TO', None)
            else:
                env['MAIL_TO'] = value
            result = subprocess.run([sys.executable, '-c', code], env=env, capture_output=True, text=True, timeout=30)
            self.assertEqual(result.returncode, 0, result.stderr)
    async def test_auth_and_health(self):
        with patch('app.smtp_send', side_effect=AssertionError('No send')), patch('app.cyberpanel_send', side_effect=AssertionError('No send')):
            async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app.app), base_url='http://localhost') as client:
                self.assertEqual((await client.get('/health')).status_code, 200)
                self.assertEqual((await client.post('/mcp')).status_code, 401)
                self.assertEqual((await client.post('/mcp', headers={'Authorization': 'Bearer wrong'})).status_code, 401)
    async def test_smtp_success_and_failure(self):
        with patch.object(app, 'DRY', False), patch.object(app, 'MODE', 'smtp'), patch('app.smtp_send') as send:
            self.assertEqual((await app.send_mail('Test', 'Hello', to='receiver@example.com'))['status'], 'accepted')
            send.assert_called_once()
        with patch.object(app, 'DRY', False), patch.object(app, 'MODE', 'smtp'), patch('app.smtp_send', side_effect=TimeoutError):
            self.assertIsNone((await app.send_mail('Test', 'Hello', to='receiver@example.com'))['sent'])
    async def test_mcp_host_protection(self):
        guard = TransportSecurityMiddleware(TransportSecuritySettings(enable_dns_rebinding_protection=True, allowed_hosts=['localhost:*'], allowed_origins=['http://localhost:*']))
        for host, expected in [('localhost:8000', None), ('localhost', 421), ('untrusted.example:8000', 421), ('localhost.attacker.example:8000', 421)]:
            with self.subTest(host=host):
                request = Request({'type': 'http', 'method': 'POST', 'scheme': 'http', 'path': '/mcp', 'query_string': b'', 'headers': [(b'host', host.encode()), (b'content-type', b'application/json')]})
                response = await guard.validate_request(request, is_post=True)
                if expected is None:
                    self.assertIsNone(response)
                else:
                    self.assertEqual(response.status_code, expected)
    async def test_mcp_initialize(self):
        with patch.object(app, 'DRY', True):
            async with app.inner.router.lifespan_context(app.inner):
                async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app.app), base_url='http://localhost:8000', headers={'Authorization': 'Bearer ' + app.TOKEN, 'Accept': 'application/json, text/event-stream'}) as client:
                    response = await client.post('/mcp', json={'jsonrpc': '2.0', 'id': 1, 'method': 'initialize', 'params': {'protocolVersion': '2025-03-26', 'capabilities': {}, 'clientInfo': {'name': 'test', 'version': '1'}}})
                    self.assertEqual(response.status_code, 200, response.text)
                    self.assertIn('result', response.json())
                    response = await client.post('/mcp', json={'jsonrpc': '2.0', 'id': 2, 'method': 'tools/list', 'params': {}})
                    self.assertEqual(response.status_code, 200, response.text)
                    tool = response.json()['result']['tools'][0]
                    self.assertEqual(tool['name'], 'send_mail')
                    self.assertIn('to', tool['inputSchema']['required'])
                    response = await client.post('/mcp', json={'jsonrpc': '2.0', 'id': 3, 'method': 'tools/call', 'params': {'name': 'send_mail', 'arguments': {'subject': 'Test', 'text': 'Hello', 'to': 'receiver@example.com'}}})
                    self.assertEqual(response.status_code, 200, response.text)
                    self.assertFalse(response.json()['result'].get('isError', False))
                    response = await client.post('/mcp', json={'jsonrpc': '2.0', 'id': 4, 'method': 'tools/call', 'params': {'name': 'send_mail', 'arguments': {'subject': 'Test', 'text': 'Hello'}}})
                    self.assertTrue(response.json()['result'].get('isError', False))

if __name__ == '__main__':
    unittest.main()
