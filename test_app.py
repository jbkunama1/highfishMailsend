import asyncio
import os
import unittest
from unittest.mock import AsyncMock, patch

os.environ.update(MCP_TOKEN='test-only-abcdefghijklmnopqrstuvwxyz123456', MAIL_FROM='sender@example.com', MAIL_TO='receiver@example.com', MAIL_ALLOWED_TO='', DRY_RUN='true')
import app
import httpx
from mcp.server.transport_security import TransportSecurityMiddleware, TransportSecuritySettings
from starlette.requests import Request


class Tests(unittest.IsolatedAsyncioTestCase):
    async def test_dry_run_no_network(self):
        with patch('app.smtp_send', side_effect=AssertionError('Network forbidden')), patch('app.httpx.AsyncClient', side_effect=AssertionError('Network forbidden')):
            result = await app.send_mail('Test', 'Hello')
        self.assertFalse(result['sent'])
        self.assertEqual(result['to'], 'receiver@example.com')

    async def test_validation(self):
        for args in [('Test', 'Hello', 'blocked@example.com'), ('bad\r\nBcc: x', 'Hello', ''), ('', 'Hello', ''), ('Test', '', ''), ('Test', 'Hello', 'a\n@example.com')]:
            with self.assertRaises(ValueError):
                await app.send_mail(*args)

    async def test_auth_and_health(self):
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app.app), base_url='http://localhost') as client:
            self.assertEqual((await client.get('/health')).status_code, 200)
            self.assertEqual((await client.post('/mcp')).status_code, 401)
            self.assertEqual((await client.post('/mcp', headers={'Authorization': 'Bearer wrong'})).status_code, 401)

    async def test_smtp_success_and_failure(self):
        with patch.object(app, 'DRY', False), patch.object(app, 'MODE', 'smtp'), patch('app.smtp_send') as send:
            self.assertEqual((await app.send_mail('Test', 'Hello'))['status'], 'accepted')
            send.assert_called_once()
        with patch.object(app, 'DRY', False), patch.object(app, 'MODE', 'smtp'), patch('app.smtp_send', side_effect=TimeoutError):
            self.assertIsNone((await app.send_mail('Test', 'Hello'))['sent'])

    async def test_mcp_host_protection(self):
        guard = TransportSecurityMiddleware(TransportSecuritySettings(
            enable_dns_rebinding_protection=True,
            allowed_hosts=['localhost:*'],
            allowed_origins=['http://localhost:*'],
        ))
        for host, expected in [('localhost:8000', None), ('localhost', 421), ('untrusted.example:8000', 421), ('localhost.attacker.example:8000', 421)]:
            with self.subTest(host=host):
                request = Request({'type': 'http', 'method': 'POST', 'scheme': 'http', 'path': '/mcp', 'query_string': b'', 'headers': [(b'host', host.encode()), (b'content-type', b'application/json')]})
                response = await guard.validate_request(request, is_post=True)
                if expected is None:
                    self.assertIsNone(response)
                else:
                    self.assertEqual(response.status_code, expected)

    async def test_mcp_initialize(self):
        async with app.inner.router.lifespan_context(app.inner):
            async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app.app), base_url='http://localhost:8000', headers={'Authorization': 'Bearer ' + app.TOKEN, 'Accept': 'application/json, text/event-stream'}) as client:
                response = await client.post('/mcp', json={'jsonrpc': '2.0', 'id': 1, 'method': 'initialize', 'params': {'protocolVersion': '2025-03-26', 'capabilities': {}, 'clientInfo': {'name': 'test', 'version': '1'}}})
                self.assertEqual(response.status_code, 200, response.text)
                self.assertIn('result', response.json())
                response = await client.post('/mcp', json={'jsonrpc': '2.0', 'id': 2, 'method': 'tools/list', 'params': {}})
                self.assertEqual(response.status_code, 200, response.text)
                self.assertEqual(response.json()['result']['tools'][0]['name'], 'send_mail')
                response = await client.post('/mcp', json={'jsonrpc': '2.0', 'id': 3, 'method': 'tools/call', 'params': {'name': 'send_mail', 'arguments': {'subject': 'Test', 'text': 'Hello'}}})
                self.assertEqual(response.status_code, 200, response.text)
                self.assertFalse(response.json()['result'].get('isError', False))


if __name__ == '__main__':
    unittest.main()
