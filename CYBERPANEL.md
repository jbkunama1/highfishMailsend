# CyberPanel Email REST API

Zusaetzlicher Versandtransport fuer MCP, Web und Telegram im bestehenden Container. Quelle: https://cyberpanel.net/KnowledgeBase/sending-email-rest-api/ . Der Apiary-Link https://cyberpanel.docs.apiary.io/ dokumentiert die andere CyberPanel-Verwaltungs-API mit Admin-Login, nicht diesen Email-Versand. Keine Panel-Admin-Zugangsdaten fuer dieses Projekt verwenden.

## Portainer

MAIL_TRANSPORT=cyberpanel
CYBERPANEL_API_KEY=DEIN_API_KEY_NUR_IN_PORTAINER
MAIL_FROM=info@kleintierstr.eu
MAIL_TO=DEINE_EMPFAENGERADRESSE
DRY_RUN=true

MCP_TOKEN, MCP_ALLOWED_HOSTS und optionale Telegram-Variablen weiter setzen. SMTP_USERNAME und SMTP_PASSWORD sind fuer cyberpanel nicht erforderlich. MAILERSEND_API_TOKEN gehoert nur zu MAIL_TRANSPORT=api (bestehender MailerSend-Modus). SMTP bleibt MAIL_TRANSPORT=smtp, fuer deinen SMTP-Server SMTP_HOST=mail.cyberpersons.com und SMTP_PORT=587 setzen. Kein stiller Wechsel zwischen Transporten bei Fehlern.

## API-Vertrag

POST https://platform.cyberpersons.com/email/v1/send
Authorization: Bearer DEIN_KEY
JSON-Felder: from, to, subject, text (Strings). Versand bleibt Plaintext. Erwartet HTTP 202 mit success=true und data-Objekt. message_id wird bei Vorhandensein zurueckgegeben. Provider-Annahme ist keine Garantie fuer Postfachzustellung. API-Key benoetigt can_send; Domain muss dem Account gehoeren und verifiziert sein. Domain-/IP-Beschraenkungen des Keys beachten.

## Verhalten

Absenderdomain bleibt aus MAIL_FROM fix. sender=shop ergibt shop@kleintierstr.eu. Bestehende Vorschau- und Empfaengerregeln bleiben unveraendert. DRY_RUN=true macht keinen API-Aufruf und prueft daher weder Key noch Domainfreigabe. Bei echtem Versand fehlt der Key: Startabbruch mit Variablennamen, ohne Secret-Ausgabe.

API-Aufruf mit HTTPS, Zertifikatspruefung, 20 Sekunden Timeout und ohne Redirect-Folgen. Keine automatischen Retries oder SMTP-Fallbacks. Bei Fehlern, unerwarteter Antwort oder Timeout wird sent=null gemeldet: erst Provider-Logs pruefen, nicht blind erneut senden. Provider-Antworttexte und Key werden nicht an den Client durchgereicht.

Admin-Status zeigt transport=cyberpanel. Das bisherige Feld api_token_configured bezieht sich weiterhin nur auf MAILERSEND_API_TOKEN und ist keine Aussage zum CyberPanel-Key.

## Tests und Deployment

python -m unittest -v

Neue Tests verwenden ausschliesslich httpx-MockTransport: Auth/Payload/Absender, Erfolgsantwort, Dry-run ohne Netzwerk, HTTP-Fehler, unerwartetes JSON und Timeout ohne Wiederholung. Kein echter Versandtest. Nach erfolgreichem Actions-Build neues GHCR-Image ziehen, Stack mit neuem Compose und Key redeployen; zuerst Dry-run. Fuer echten Versand bewusst DRY_RUN=false setzen. Keine echten Keys im Repository, in Testdateien oder im Chat hinterlegen.
