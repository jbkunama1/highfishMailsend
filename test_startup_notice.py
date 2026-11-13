import ast
import pathlib
import types
import unittest
from unittest.mock import AsyncMock, patch
import httpx

class StartupNoticeTests(unittest.IsolatedAsyncioTestCase):
    def notifier(self, token='test-bot-token', users=None):
        source = pathlib.Path(__file__).with_name('service.py').read_text()
        node = next(n for n in ast.parse(source).body if isinstance(n, ast.AsyncFunctionDef) and n.name == 'notify_startup')
        runner = types.SimpleNamespace(TOKEN=token, USERS={123, 456} if users is None else users, mail=types.SimpleNamespace(DRY=True, MODE='smtp'))
        import asyncio
        env = {'runner': runner, 'application': types.SimpleNamespace(configured=lambda: True), 'httpx': httpx, 'asyncio': asyncio}
        exec(compile(ast.Module(body=[node], type_ignores=[]), 'service.py', 'exec'), env)
        return env['notify_startup']
    async def test_one_notice_per_user_without_secrets(self):
        notify = self.notifier()
        client = AsyncMock()
        response = types.SimpleNamespace(raise_for_status=lambda: None, json=lambda: {'ok': True})
        client.post.return_value = response
        with patch('httpx.AsyncClient') as factory:
            factory.return_value.__aenter__ = AsyncMock(return_value=client)
            factory.return_value.__aexit__ = AsyncMock(return_value=False)
            await notify()
        self.assertEqual(client.post.await_count, 2)
        calls = client.post.await_args_list
        self.assertEqual([c.kwargs['json']['chat_id'] for c in calls], [123, 456])
        for call in calls:
            text = call.kwargs['json']['text']
            self.assertIn('TESTMODUS', text)
            self.assertNotIn('test-bot-token', text)
    async def test_failure_no_retry_and_disabled(self):
        notify = self.notifier(users={123})
        client = AsyncMock()
        client.post.side_effect = httpx.ReadTimeout('uncertain')
        with patch('httpx.AsyncClient') as factory:
            factory.return_value.__aenter__ = AsyncMock(return_value=client)
            factory.return_value.__aexit__ = AsyncMock(return_value=False)
            await notify()
        self.assertEqual(client.post.await_count, 1)
        with patch('httpx.AsyncClient', side_effect=AssertionError('No network')):
            await self.notifier(token='')()
            await self.notifier(users=set())()
