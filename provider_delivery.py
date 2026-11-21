"""Bounded provider transports. No automatic retry, no SMTP fallback."""
import asyncio
import hashlib
import hmac
import secrets
import ipaddress
import json
import os
import smtplib
import socket
import ssl
from email.message import EmailMessage
import httpx

REVISION_KEY = secrets.token_bytes(32)
API_HOSTS = {'api':'api.mailersend.com', 'cyberpanel':'platform.cyberpersons.com'}

def revision(value):
    if not value['builtin']:
        return value['revision']
    raw = json.dumps(value, sort_keys=True).encode()
    return int.from_bytes(hmac.new(REVISION_KEY,raw,hashlib.sha256).digest()[:6], 'big')

def target(host, port):
    trusted = {v.strip().lower() for v in os.getenv('SMTP_TRUSTED_PRIVATE_HOSTS','').split(',') if v.strip()}
    addresses = socket.getaddrinfo(host, port, type=socket.SOCK_STREAM)
    if not addresses:
        raise ValueError('No SMTP address')
    for row in addresses:
        ip = ipaddress.ip_address(row[4][0])
        if ip.is_loopback or ip.is_link_local or ip.is_multicast or ip.is_unspecified or ip.is_reserved:
            raise ValueError('SMTP destination blocked')
        if not ip.is_global and host.lower() not in trusted:
            raise ValueError('Private SMTP requires explicit trusted hostname')
    return addresses[0][4][0]

class PinnedSMTP(smtplib.SMTP):
    def _get_socket(self, host, port, timeout):
        return socket.create_connection((target(host,port),port), timeout, self.source_address)

class PinnedSSL(smtplib.SMTP_SSL):
    def _get_socket(self, host, port, timeout):
        raw = socket.create_connection((target(host,port),port),timeout,self.source_address)
        try:
            return self.context.wrap_socket(raw,server_hostname=host)
        except BaseException:
            raw.close()
            raise

def smtp(value, message=None):
    context = ssl.create_default_context()
    cls = PinnedSSL if value['tls']=='tls' else PinnedSMTP
    kwargs = {'context':context} if value['tls']=='tls' else {}
    with cls(value['host'], value['port'], timeout=10, **kwargs) as client:
        client.ehlo()
        if value['tls']=='starttls':
            client.starttls(context=context)
            client.ehlo()
        client.login(value['username'],value['password'])
        if message is not None:
            client.send_message(message)

def tls_probe(host):
    with socket.create_connection((host,443),timeout=10) as raw:
        with ssl.create_default_context().wrap_socket(raw,server_hostname=host):
            return

async def check(value):
    try:
        if value['kind']=='smtp':
            await asyncio.to_thread(smtp,value)
            return {'ok':True,'message':'TLS und SMTP-Anmeldung erfolgreich; keine Mail versendet.'}
        await asyncio.to_thread(tls_probe,API_HOSTS[value['kind']])
        return {'ok':True,'message':'HTTPS-Server erreichbar. API-Key und Domain NICHT geprüft; keine Mail versendet.'}
    except Exception:
        return {'ok':False,'message':'Verbindungsprüfung fehlgeschlagen; keine Mail versendet. Konfiguration prüfen.'}

async def deliver(value, sender, to, subject, text):
    if value['kind']=='smtp':
        message = EmailMessage()
        message['From'],message['To'],message['Subject'] = sender,to,subject
        message.set_content(text)
        await asyncio.to_thread(smtp,value,message)
        return None
    kind = value['kind']
    url = 'https://'+API_HOSTS[kind]+('/v1/email' if kind=='api' else '/email/v1/send')
    payload = {'from':{'email':sender},'to':[{'email':to}],'subject':subject,'text':text} if kind=='api' else {'from':sender,'to':to,'subject':subject,'text':text}
    async with httpx.AsyncClient(timeout=20,follow_redirects=False,trust_env=False) as client:
        response = await client.post(url,headers={'Authorization':'Bearer '+value['token']},json=payload)
        response.raise_for_status()
        if kind=='cyberpanel':
            data = response.json()
            if response.status_code!=202 or not isinstance(data,dict) or data.get('success') is not True or not isinstance(data.get('data'),dict):
                raise ValueError('Uncertain provider response')
            ident = data['data'].get('message_id')
            return ident if isinstance(ident,str) and len(ident)<=512 else None
    return None
