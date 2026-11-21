"""Profile delivery integration; all recipient/sender rules stay in app.py."""
import provider_delivery as delivery
import providers

async def send(mail, subject, text, to, sender='', transport='', provider='', provider_revision=-1):
    value = providers.select(mail,provider,transport)
    if provider_revision != -1 and delivery.revision(value) != provider_revision:
        raise ValueError('Provider changed; create a new preview')
    recipient = mail.resolve_recipient(to)
    sender_address = mail.resolve_sender(sender or value['sender'])
    if not isinstance(subject,str) or not subject.strip() or len(subject)>200 or '\r' in subject or '\n' in subject:
        raise ValueError('Invalid subject')
    if not isinstance(text,str) or not text.strip() or len(text)>100000:
        raise ValueError('Invalid body')
    result = {'transport':value['kind'],'provider':value['id'],'from':sender_address,'to':recipient}
    if mail.DRY:
        return {**result,'status':'dry_run','sent':False,'subject':subject,'text':text}
    if value['kind']=='smtp' and (not value['username'] or not value['password']) or value['kind']!='smtp' and not value['token']:
        raise ValueError('Provider credentials missing')
    try:
        ident = await delivery.deliver(value,sender_address,recipient,subject,text)
    except Exception:
        return {**result,'status':'error','sent':None,'message':'Delivery failed or outcome uncertain. Check provider before retrying.'}
    result.update(status='accepted',message='Provider accepted message; inbox delivery not guaranteed.')
    if ident:
        result['message_id']=ident
    return result
