"""Persistent, encrypted provider profiles. No production networking at import."""
import json
import os
import re
import sqlite3
import threading
import uuid
from contextlib import contextmanager
from cryptography.fernet import Fernet, InvalidToken

KINDS = ('smtp', 'api', 'cyberpanel')
SECRET_FIELDS = ('username', 'password', 'token')

class Store:
    def __init__(self, path, key):
        try:
            self.cipher = Fernet(key.encode())
        except Exception:
            raise ValueError('Invalid PROVIDER_ENCRYPTION_KEY') from None
        self.lock = threading.RLock()
        self.db = sqlite3.connect(path, check_same_thread=False, timeout=5)
        self.db.execute('PRAGMA foreign_keys=ON')
        with self.tx() as db:
            db.execute('CREATE TABLE IF NOT EXISTS profiles (id TEXT PRIMARY KEY, data TEXT NOT NULL, secret BLOB NOT NULL, revision INTEGER NOT NULL)')
            db.execute('CREATE TABLE IF NOT EXISTS settings (key TEXT PRIMARY KEY, value TEXT NOT NULL)')
            row = db.execute("SELECT value FROM settings WHERE key='key_check'").fetchone()
            if row:
                try:
                    if self.cipher.decrypt(row[0].encode()) != b'highfish-providers-v1':
                        raise ValueError()
                except (InvalidToken, ValueError):
                    raise ValueError('Provider storage key mismatch') from None
            else:
                db.execute('INSERT INTO settings VALUES (?,?)', ('key_check', self.cipher.encrypt(b'highfish-providers-v1').decode()))

    @contextmanager
    def tx(self):
        with self.lock:
            self.db.execute('BEGIN IMMEDIATE')
            try:
                yield self.db
                self.db.commit()
            except BaseException:
                self.db.rollback()
                raise

    def close(self):
        self.db.close()

    def get(self, ident):
        with self.lock:
            row = self.db.execute('SELECT data,secret,revision FROM profiles WHERE id=?', (ident,)).fetchone()
        if not row:
            raise ValueError('Unknown provider')
        try:
            return dict(json.loads(row[0]), **json.loads(self.cipher.decrypt(row[1])), id=ident, revision=row[2], builtin=False)
        except (InvalidToken, TypeError, ValueError):
            raise ValueError('Provider storage unavailable') from None

    def public(self):
        with self.lock:
            ids = [r[0] for r in self.db.execute('SELECT id FROM profiles ORDER BY id')]
            return [redact(self.get(i)) for i in ids]

    def default(self):
        with self.lock:
            row = self.db.execute("SELECT value FROM settings WHERE key='default'").fetchone()
            return row[0] if row else ''

    def set_default(self, ident):
        with self.tx() as db:
            if ident and not ident.startswith('env:') and not self.get(ident)['enabled']:
                raise ValueError('Provider disabled')
            if ident.startswith('env:') and ident[4:] not in KINDS:
                raise ValueError('Unknown provider')
            db.execute("INSERT OR REPLACE INTO settings VALUES ('default',?)", (ident,))

    def save(self, data):
        if not isinstance(data, dict):
            raise ValueError('Object required')
        allowed = {'id','revision','name','kind','sender','enabled','host','port','tls', *SECRET_FIELDS}
        if set(data) - allowed:
            raise ValueError('Unknown field')
        ident = data.get('id') or uuid.uuid4().hex
        if not isinstance(ident, str) or not re.fullmatch('[a-f0-9]{32}', ident):
            raise ValueError('Invalid id')
        with self.tx() as db:
            exists = db.execute('SELECT 1 FROM profiles WHERE id=?', (ident,)).fetchone()
            old = self.get(ident) if exists else {}
            if exists and (type(data.get('revision')) is not int or data.get('revision') != old['revision']):
                raise ValueError('Provider changed; reload')
            value = {**old, **data}
            if value.get('kind') not in KINDS or not isinstance(value.get('name'), str) or not 1 <= len(value['name'].strip()) <= 80:
                raise ValueError('Invalid name/type')
            if exists and value['kind'] != old['kind']:
                raise ValueError('Create a new profile to change type')
            if type(value.get('enabled', True)) is not bool:
                raise ValueError('Invalid enabled flag')
            value.setdefault('enabled', True)
            sender = value.get('sender', '')
            if not isinstance(sender, str) or len(sender) > 64 or sender and not re.fullmatch(r'[A-Za-z0-9_+.-]+', sender):
                raise ValueError('Only sender local-part allowed')
            value['sender'] = sender
            for field in SECRET_FIELDS:
                candidate = data.get(field)
                if candidate is not None and not isinstance(candidate, str):
                    raise ValueError('Invalid credential')
                value[field] = candidate if candidate else old.get(field, '')
                if len(value[field]) > 8192 or '\r' in value[field] or '\n' in value[field]:
                    raise ValueError('Invalid credential')
            if value['kind'] == 'smtp':
                host = value.get('host', '')
                if not isinstance(host, str) or len(host) > 253 or not re.fullmatch(r'[a-zA-Z0-9.:_-]+', host):
                    raise ValueError('Invalid SMTP host')
                if type(value.get('port')) is not int or not 1 <= value['port'] <= 65535 or value.get('tls') not in ('starttls','tls'):
                    raise ValueError('Verified SMTP TLS required')
                if not value['username'] or not value['password']:
                    raise ValueError('SMTP credentials required')
            elif not value['token']:
                raise ValueError('API token required')
            if self.default() == ident and not value['enabled']:
                raise ValueError('Choose another default before disabling')
            revision = old.get('revision', 0) + 1
            public = {k: value[k] for k in ('name','kind','sender','enabled','host','port','tls') if k in value}
            secret = self.cipher.encrypt(json.dumps({k: value[k] for k in SECRET_FIELDS}).encode())
            db.execute('INSERT OR REPLACE INTO profiles VALUES (?,?,?,?)', (ident,json.dumps(public),secret,revision))
            return redact(self.get(ident))

def redact(value):
    return {**{k:v for k,v in value.items() if k not in SECRET_FIELDS}, **{k+'_configured':bool(value.get(k)) for k in SECRET_FIELDS}}

_store = None
_error = None

def storage():
    global _store, _error
    if _store is not None:
        return _store
    if _error:
        raise ValueError(_error)
    key = os.getenv('PROVIDER_ENCRYPTION_KEY', '')
    if not key or key in (os.getenv('MCP_TOKEN'), os.getenv('WEB_ADMIN_PASSWORD')):
        raise ValueError('Set a separate PROVIDER_ENCRYPTION_KEY for provider management')
    try:
        _store = Store(os.getenv('PROVIDER_DB_PATH', '/data/providers.sqlite3'), key)
    except Exception:
        _error = 'Provider storage unavailable; check volume permissions and encryption key'
        raise ValueError(_error) from None
    return _store

def builtin(mail, kind):
    if kind not in KINDS:
        raise ValueError('Unknown transport')
    return dict(id='env:'+kind, name='ENV / '+kind, kind=kind, sender='', enabled=True, builtin=True, revision=0,
                host=mail.HOST, port=mail.PORT, tls='starttls', username=os.getenv('SMTP_USERNAME',''),
                password=os.getenv('SMTP_PASSWORD',''), token=os.getenv('MAILERSEND_API_TOKEN' if kind=='api' else 'CYBERPANEL_API_KEY',''))

def default_id(mail):
    if not os.getenv('PROVIDER_ENCRYPTION_KEY'):
        return 'env:'+mail.MODE
    return storage().default() or 'env:'+mail.MODE

def select(mail, provider='', transport='', revision=None):
    if not isinstance(provider,str) or not isinstance(transport,str):
        raise ValueError('Invalid provider')
    ident = provider or ('env:'+mail.select_transport(transport) if transport else default_id(mail))
    value = builtin(mail,ident[4:]) if ident.startswith('env:') else storage().get(ident)
    if not value['enabled'] or transport and transport != value['kind']:
        raise ValueError('Disabled provider or conflicting transport')
    if revision is not None and (type(revision) is not int or revision != value['revision']):
        raise ValueError('Provider changed; create a new preview')
    return value

def listing(mail):
    values = [redact(builtin(mail,k)) for k in KINDS]
    try:
        store = storage()
        return dict(providers=values+store.public(), default=store.default() or 'env:'+mail.MODE, writable=True, error='')
    except ValueError:
        return dict(providers=values, default='env:'+mail.MODE, writable=False, error='Anbieterverwaltung nicht verfügbar: Volume und separaten Schlüssel prüfen.')
