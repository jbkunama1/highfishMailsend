import asyncio
import json
import os
import tempfile
import types
import unittest
from pathlib import Path
from unittest.mock import patch, AsyncMock
from cryptography.fernet import Fernet
import providers
import provider_delivery as delivery
import provider_mail

class ProviderTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        self.path=str(Path(self.tmp.name)/'profiles.db')
        self.key=Fernet.generate_key().decode()
        self.store=providers.Store(self.path,self.key)
        self.data=dict(name='Office',kind='smtp',sender='shop',host='smtp.example.com',port=587,tls='starttls',username='secret-user',password='secret-pass')
        self.mail=types.SimpleNamespace(MODE='smtp',HOST='smtp.example.com',PORT=587,DRY=True,
            select_transport=lambda x:x or 'smtp',resolve_sender=lambda x:(x or 'info')+'@example.com',
            resolve_recipient=self.recipient)
    def recipient(self,to):
        if to!='allowed@example.com':
            raise ValueError('Recipient rejected')
        return to
    def tearDown(self):
        self.store.close()
        self.tmp.cleanup()
    def save(self):
        return self.store.save(self.data)
    def test_secret_redaction(self):
        public=self.save()
        self.assertNotIn('password',public)
        self.assertNotIn('username',public)
        self.assertTrue(public['password_configured'])
        self.assertNotIn('secret-pass',json.dumps(self.store.public()))
    def test_encrypted_disk_and_restart(self):
        public=self.save()
        other=providers.Store(self.path,self.key)
        self.assertEqual(other.get(public['id'])['password'],'secret-pass')
        other.close()
        self.assertNotIn(b'secret-pass',Path(self.path).read_bytes())
        self.assertNotIn(b'secret-user',Path(self.path).read_bytes())
    def test_wrong_key(self):
        self.save()
        with self.assertRaises(ValueError):
            providers.Store(self.path,Fernet.generate_key().decode())
    def test_invalid_key(self):
        with self.assertRaises(ValueError):
            providers.Store(self.path,'bad')
    def test_edit_preserves_secrets(self):
        p=self.save()
        updated=self.store.save(dict(id=p['id'],revision=p['revision'],name='New',password=''))
        self.assertEqual(updated['revision'],2)
        self.assertEqual(self.store.get(p['id'])['password'],'secret-pass')
    def test_stale_edit(self):
        p=self.save()
        self.store.save(dict(id=p['id'],revision=1,name='New'))
        with self.assertRaises(ValueError):
            self.store.save(dict(id=p['id'],revision=1,name='Old'))
    def test_no_plain_smtp(self):
        for tls in ('none','ssl-insecure',''):
            with self.subTest(tls=tls),self.assertRaises(ValueError):
                self.store.save(dict(self.data,tls=tls))
    def test_bad_fields(self):
        for field,value in [('sender','evil@other.com'),('port',True),('port',0),('host','https://example.com'),('enabled','false'),('password','a\nb')]:
            with self.subTest(field=field),self.assertRaises(ValueError):
                self.store.save(dict(self.data,**{field:value}))
    def test_no_arbitrary_api(self):
        with self.assertRaises(ValueError):
            self.store.save(dict(name='API',kind='api',token='secret',url='http://127.0.0.1'))
    def test_api_profiles(self):
        for kind in ('api','cyberpanel'):
            p=self.store.save(dict(name=kind,kind=kind,token='api-secret'))
            self.assertTrue(p['token_configured'])
            self.assertNotIn('api-secret',json.dumps(p))
    def test_default_survives_restart(self):
        p=self.save()
        self.store.set_default(p['id'])
        other=providers.Store(self.path,self.key)
        self.assertEqual(other.default(),p['id'])
        other.close()
    def test_disable_default_rejected(self):
        p=self.save()
        self.store.set_default(p['id'])
        with self.assertRaises(ValueError):
            self.store.save(dict(id=p['id'],revision=1,enabled=False))
    def test_unknown_default_rejected(self):
        with self.assertRaises(ValueError):
            self.store.set_default('missing')
    def test_disabled_selection(self):
        p=self.save()
        self.store.save(dict(id=p['id'],revision=1,enabled=False))
        with patch.object(providers,'storage',return_value=self.store), self.assertRaises(ValueError):
            providers.select(self.mail,p['id'])
    def test_conflicting_transport(self):
        p=self.save()
        with patch.object(providers,'storage',return_value=self.store),self.assertRaises(ValueError):
            providers.select(self.mail,p['id'],'api')
    def test_explicit_transport_overrides_default(self):
        with patch.object(providers,'default_id',side_effect=AssertionError('Must not read default')):
            self.assertEqual(providers.select(self.mail,transport='api')['id'],'env:api')
    def test_dry_run_no_network(self):
        p=self.save()
        with patch.object(providers,'storage',return_value=self.store),patch.object(delivery,'deliver',new_callable=AsyncMock) as send:
            result=asyncio.run(provider_mail.send(self.mail,'subject','body','allowed@example.com',provider=p['id']))
            self.assertEqual(result['status'],'dry_run')
            self.assertEqual(result['from'],'shop@example.com')
            send.assert_not_awaited()
    def test_recipient_required_and_allowlist(self):
        p=self.save()
        for to in ('','bad','other@example.com'):
            with patch.object(providers,'storage',return_value=self.store), self.assertRaises(ValueError):
                asyncio.run(provider_mail.send(self.mail,'subject','body',to,provider=p['id']))
    def test_stale_preview_rejected(self):
        p=self.save()
        self.store.save(dict(id=p['id'],revision=1,name='edited'))
        with patch.object(providers,'storage',return_value=self.store),self.assertRaises(ValueError):
            asyncio.run(provider_mail.send(self.mail,'subject','body','allowed@example.com',provider=p['id'],provider_revision=1))
    def test_send_error_not_retried(self):
        p=self.save()
        self.mail.DRY=False
        with patch.object(providers,'storage',return_value=self.store),patch.object(delivery,'deliver',new_callable=AsyncMock,side_effect=TimeoutError) as send:
            result=asyncio.run(provider_mail.send(self.mail,'subject','body','allowed@example.com',provider=p['id']))
            self.assertIsNone(result['sent'])
            self.assertEqual(send.await_count,1)
    def test_api_probe_label(self):
        with patch.object(delivery,'tls_probe') as probe:
            result=asyncio.run(delivery.check({'kind':'api'}))
            self.assertIn('NICHT geprüft',result['message'])
            probe.assert_called_once_with('api.mailersend.com')
    def test_smtp_probe_never_submits(self):
        with patch.object(delivery,'smtp') as smtp:
            asyncio.run(delivery.check({'kind':'smtp'}))
            smtp.assert_called_once_with({'kind':'smtp'})
    def test_blocked_networks(self):
        for ip in ('127.0.0.1','169.254.169.254','0.0.0.0','::1','10.0.0.1'):
            row=(2,1,6,'',(ip,587))
            with patch.object(delivery.socket,'getaddrinfo',return_value=[row]),patch.dict(os.environ,{'SMTP_TRUSTED_PRIVATE_HOSTS':''}),self.assertRaises(ValueError):
                delivery.target('smtp.example.com',587)
    def test_private_opt_in_still_blocks_metadata(self):
        for ip,allowed in [('10.0.0.1',True),('169.254.169.254',False)]:
            with patch.object(delivery.socket,'getaddrinfo',return_value=[(2,1,6,'',(ip,587))]),patch.dict(os.environ,{'SMTP_TRUSTED_PRIVATE_HOSTS':'smtp.internal'}):
                if allowed:
                    self.assertEqual(delivery.target('smtp.internal',587),ip)
                else:
                    with self.assertRaises(ValueError):
                        delivery.target('smtp.internal',587)
    def test_missing_key_blocks_management(self):
        with patch.dict(os.environ,{'PROVIDER_ENCRYPTION_KEY':''}),patch.object(providers,'_store',None),patch.object(providers,'_error',None),self.assertRaises(ValueError):
            providers.storage()
    def test_key_reuse_blocked(self):
        with patch.dict(os.environ,{'PROVIDER_ENCRYPTION_KEY':self.key,'MCP_TOKEN':self.key}),patch.object(providers,'_store',None),patch.object(providers,'_error',None),self.assertRaises(ValueError):
            providers.storage()
    def test_env_default_without_storage(self):
        with patch.dict(os.environ,{'PROVIDER_ENCRYPTION_KEY':''}):
            self.assertEqual(providers.default_id(self.mail),'env:smtp')
    def test_bad_subject_before_delivery(self):
        p=self.save()
        for subject in ('','a\nb','a\rb','x'*201):
            with patch.object(providers,'storage',return_value=self.store),self.assertRaises(ValueError):
                asyncio.run(provider_mail.send(self.mail,subject,'body','allowed@example.com',provider=p['id']))
    def test_env_revision_change(self):
        value=providers.builtin(self.mail,'smtp')
        first=delivery.revision(value)
        self.assertEqual(first,delivery.revision(value))
        self.assertNotEqual(first,delivery.revision(dict(value,password='changed')))

if __name__=='__main__':
    unittest.main()
