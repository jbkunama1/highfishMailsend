import os
import unittest
from unittest.mock import patch, AsyncMock
os.environ.update(MCP_TOKEN='test-only-abcdefghijklmnopqrstuvwxyz123456', MAIL_FROM='sender@example.com', MAIL_TO='receiver@example.com', MAIL_ALLOWED_TO='', DRY_RUN='true')
import app
import admin
import httpx

class TransportSelectionTests(unittest.IsolatedAsyncioTestCase):
    async def test_explicit_transport_does_not_change_default(self):
        with patch.object(app, 'MODE', 'smtp'), patch.object(app, 'DRY', True):
            result = await app.send_mail('Test', 'Hello', transport='cyberpanel')
            self.assertEqual(result['transport'], 'cyberpanel')
            self.assertEqual(app.MODE, 'smtp')

    async def test_dispatch_without_fallback(self):
        with patch.object(app, 'MODE', 'smtp'), patch.object(app, 'DRY', False), patch('app.smtp_send') as smtp, patch('app.cyberpanel_send', new_callable=AsyncMock) as cyber:
            cyber.return_value = 'mock-id'
            self.assertEqual((await app.send_mail('Test', 'Hello', transport='cyberpanel'))['message_id'], 'mock-id')
            smtp.assert_not_called()
            cyber.side_effect = TimeoutError()
            self.assertIsNone((await app.send_mail('Test', 'Hello', transport='cyberpanel'))['sent'])
            smtp.assert_not_called()

    async def test_global_default_and_snapshot(self):
        admin.DRAFTS.clear()
        with patch.object(app, 'MODE', 'smtp'), patch.object(app, 'DRY', True):
            async with httpx.AsyncClient(transport=httpx.ASGITransport(app=admin.application), base_url='http://localhost', headers={'Authorization': 'Bearer ' + app.TOKEN}) as client:
                old = (await client.post('/api/preview', json={'subject': 'Test', 'text': 'Hello'})).json()
                self.assertEqual(old['transport'], 'smtp')
                denied = await client.post('/api/default', json={'transport': 'cyberpanel'})
                self.assertEqual(denied.status_code, 400)
                self.assertEqual(app.MODE, 'smtp')
                changed = await client.post('/api/default', json={'transport': 'cyberpanel', 'confirm': True})
                self.assertEqual(changed.status_code, 200)
                self.assertEqual((await app.send_mail('Test', 'Hello'))['transport'], 'cyberpanel')
                result = (await client.post('/api/send', json={'id': old['id'], 'transport': 'cyberpanel'})).json()
                self.assertEqual(result['transport'], 'smtp')
                new = (await client.post('/api/preview', json={'subject': 'Test', 'text': 'Hello'})).json()
                self.assertEqual(new['transport'], 'cyberpanel')

    async def test_unknown_transport(self):
        with self.assertRaises(ValueError):
            await app.send_mail('Test', 'Hello', transport='unknown')
