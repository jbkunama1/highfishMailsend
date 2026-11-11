# Direkter Zugriff und Telegram

Diese Anleitung ergaenzt die README und ersetzt deren Proxy-/Loopback-Vorgabe: Ein Container enthaelt MCP-Maildienst und optional den Telegram-Poller. Kein Reverse-Proxy notwendig.

## Direkter MCP-Zugriff

Compose bindet standardmaessig 0.0.0.0:8095. Client-URL http://SERVER-IP:8095/mcp, Header Authorization: Bearer DEIN_MCP_TOKEN. MCP_ALLOWED_HOSTS muss in Portainer explizit gesetzt werden, z.B. 192.168.1.10:8095; mehrere tatsaechlich verwendete LAN-/externe Hosts kommagetrennt eintragen. Externen Port nach einer eventuellen Portweiterleitung beachten. Kein globales Wildcard. MCP_ALLOWED_ORIGINS nur fuer benoetigte Browser-Origins setzen. Firewall/Routerfreigaben werden nicht automatisch eingerichtet.

HTTP verschluesselt weder Bearer-Token noch Mailtext! Key-Authentifizierung ersetzt kein TLS. Direkte Internetfreigabe ohne HTTPS/VPN ist nicht sicher. Fuer unverschluesseltes HTTP auf vertrauenswuerdiges LAN/VPN beschraenken. Dieses Update implementiert kein direktes HTTPS. SMTP bleibt STARTTLS, Telegram API und MailerSend API verwenden ausgehend HTTPS.

## Telegram im selben Container

Zusaetzliche Portainer-Variablen: TELEGRAM_BOT_TOKEN und TELEGRAM_ALLOWED_USER_IDS (numerische persoenliche Telegram-Benutzer-IDs, kommagetrennt; keine Bot-ID). Niemals echte Tokens im Repo speichern. Ohne Bot-Token bleibt Telegram aus. Mit Token ist eine Benutzer-Allowlist verpflichtend. Nur private Chats werden akzeptiert.

Long Polling: ausgehende HTTPS-Verbindungen zu Telegram, kein eingehender Webhook-Port notwendig. Pro Bot nur einen Poller betreiben. Bestehende Webhooks werden nicht automatisch geloescht; bei gesetztem Webhook startet der Poller nicht. Alte wartende Updates werden beim Start uebersprungen, Entwuerfe sind nur im Arbeitsspeicher und gehen beim Neustart verloren.

Befehle:

- /help: Hilfe
- /status: Dry-run/echter Versand und Transport
- /mail Betreff gefolgt von einer neuen Zeile und dem Mailtext: Entwurf an MAIL_TO
- /send CODE: angezeigten Entwurf innerhalb 10 Minuten freigeben
- /cancel: Entwurf verwerfen

Telegram verwendet denselben Mailversand und dieselbe Empfaenger-Allowlist wie MCP. DRY_RUN=true sendet auch ueber Telegram keine Mail. Kein LLM im Telegram-Bot: Betreff und Text werden unveraendert verwendet. Der Entwurf wird vor dem Versand bestaetigt; Vorschau ist bei langen Texten gekuerzt. Keine Anhaenge. /send-Codes sind einmalig, es gibt keine persistente Exactly-once-Garantie.

Healthcheck meldet nur HTTP-Liveness, nicht die Funktion des Telegram-Pollers oder Mailzustellung. Bei Poller-Startfehler steht eine generische Meldung ohne Token im Containerlog. Kein erfolgreicher Build, Telegram-Test oder echter Versand wird mit diesem Commit behauptet. Nach GHCR-Build Stack aktualisieren und zuerst Dry-run pruefen. Die alten .env.example-Werte BIND_ADDRESS und MCP_ALLOWED_HOSTS gegebenenfalls an diese direkte Anbindung anpassen.
